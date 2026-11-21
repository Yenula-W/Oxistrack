"""Ripple impact analysis: traverse the knowledge graph from a changed fact or requirement.

Analysis never changes project data. Changes are applied only by `apply()`, after user approval.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Contradiction, Decision, Document, ExtractedFact, GraphNode, ImpactItem, ImpactReport, Requirement,
    Task, User, utcnow,
)
from . import graph
from .common import add_event, log_activity
from .textutil import NUMBER_WORDS, find_dates, find_money, fmt_number, parse_number

TERMINAL = {"document", "deliverable", "task", "decision"}
MAX_DEPTH = 4
REPORTED = {"document", "deliverable", "requirement", "contradiction", "decision", "task"}


class ImpactError(Exception):
    pass


@dataclass
class Visit:
    node: GraphNode
    distance: int
    via_reference: bool
    parent: "Visit | None"
    relation: str

    def path(self) -> str:
        parts, v = [], self
        while v is not None:
            parts.append(v.node.label if v.parent is None else f"→ {v.relation.replace('_', ' ')} → {v.node.label}")
            v = v.parent
        return " ".join(reversed(parts))


def _norm_value(value: str) -> str:
    v = value.strip()
    if d := find_dates(v):
        return d[0][1].isoformat()
    if m := find_money(v):
        return fmt_number(m[0][1])
    first = v.split()[0] if v.split() else ""
    n = parse_number(first)
    return fmt_number(n) if n is not None else v.lower()


def analyze(db: Session, project_id: int, target_type: str, target_id: int, new_value: str,
            user_id: int | None, previous_value: str | None = None,
            source_of_change: str | None = None) -> ImpactReport:
    new_value = new_value.strip()
    if not new_value:
        raise ImpactError("Enter the new value to analyse.")
    nodes, edges = graph.sync(db, project_id)
    by_key = {(n.node_type, n.ref_key): n for n in nodes}
    by_id = {n.id: n for n in nodes}

    if target_type == "requirement":
        req = db.get(Requirement, target_id)
        if not req or req.project_id != project_id:
            raise ImpactError("Requirement not found in this project.")
        subject, label = req.subject_key, f"{req.code} {req.title}"
        previous_value = previous_value or req.expected_value or req.description
        roots = [by_key.get(("requirement", str(req.id))), by_key.get(("topic", subject))]
        subject_label = req.title.lower()
    elif target_type == "fact":
        fact = db.get(ExtractedFact, target_id)
        if not fact or fact.project_id != project_id:
            raise ImpactError("Fact not found in this project.")
        subject, label = fact.subject_key, fact.subject or fact.text[:80]
        previous_value = previous_value or fact.value_text or fact.text
        roots = [by_key.get(("topic", subject)) if subject else None, by_key.get(("fact", str(fact.id)))]
        subject_label = (fact.subject or "this statement").lower()
    else:
        raise ImpactError("Impact analysis supports facts and requirements.")
    roots = [r for r in roots if r is not None]
    if not roots:
        raise ImpactError("This item is not connected to anything in the knowledge graph yet.")

    adj: dict[int, list[tuple[int, str, bool]]] = defaultdict(list)  # node -> (neighbour, relation, forward)
    for e in edges:
        adj[e.source_id].append((e.target_id, e.relation, True))
        adj[e.target_id].append((e.source_id, e.relation, False))

    visits: dict[int, Visit] = {r.id: Visit(r, 0, False, None, "") for r in roots}
    queue = deque(visits.values())
    while queue:
        cur = queue.popleft()
        if cur.distance >= MAX_DEPTH or (cur.node.node_type in TERMINAL and cur.distance > 0):
            continue
        for nid, rel, forward in adj[cur.node.id]:
            if nid in visits:
                continue
            is_ref = rel == "references"
            if is_ref and (forward or cur.via_reference):
                continue  # only "who mentions this topic", and at most one such hop
            nxt = by_id[nid]
            if nxt.node_type == "topic" and cur.via_reference is False and cur.distance > 0 and not is_ref \
                    and cur.node.node_type != "fact":
                continue
            v = Visit(nxt, cur.distance + 1, cur.via_reference or is_ref, cur, rel)
            visits[nid] = v
            queue.append(v)

    facts = {str(f.id): f for f in db.scalars(select(ExtractedFact).where(ExtractedFact.project_id == project_id))}
    reqs = {str(r.id): r for r in db.scalars(select(Requirement).where(Requirement.project_id == project_id))}
    cons = {str(c.id): c for c in db.scalars(select(Contradiction).where(Contradiction.project_id == project_id))}
    decs = {str(d.id): d for d in db.scalars(select(Decision).where(Decision.project_id == project_id))}
    new_norm = _norm_value(new_value)
    root_ids = {r.id for r in roots}

    report = ImpactReport(
        project_id=project_id, target_type=target_type, target_id=target_id, target_label=label[:255],
        subject_key=subject, previous_value=(previous_value or "")[:300] or None, new_value=new_value[:300],
        source_of_change=(source_of_change or "Proposed by user (what-if analysis)")[:255], created_by=user_id,
    )
    items: dict[tuple[str, str], ImpactItem] = {}
    for v in sorted(visits.values(), key=lambda x: (x.distance, x.node.id)):
        n = v.node
        if n.id in root_ids or n.node_type not in REPORTED:
            continue
        direct = not v.via_reference and v.distance <= 2
        conf = max(0.35, (0.92 if direct else 0.68) - 0.08 * max(0, v.distance - 1))
        reason = action = ""
        parent_fact = facts.get(v.parent.node.ref_key) if v.parent and v.parent.node.node_type == "fact" else None
        if n.node_type == "document":
            if parent_fact is None:
                continue
            if parent_fact.subject_key == subject and parent_fact.value_norm:
                if parent_fact.value_norm == new_norm:
                    continue  # already consistent with the new value
                reason = (f"States {subject_label} as “{parent_fact.value_text}”"
                          f"{f' ({parent_fact.location})' if parent_fact.location else ''}, which differs from the new value.")
                action = "Update this document, or mark its statement as superseded."
            else:
                reason = f"Contains a statement that depends on {subject_label}: “{parent_fact.text}”"
                action = "Review this passage; it may need to be reworded for the new value."
        elif n.node_type == "requirement":
            r = reqs.get(n.ref_key)
            if r is None:
                continue
            if r.subject_key == subject:
                reason = f"Defines the same topic (expected value: {r.expected_value or 'not set'})."
                action = f"Update the expected value to {new_value} and re-run verification."
            else:
                reason = f"Refers to {subject_label}: “{r.description}”"
                action = "Check whether this requirement still holds, then re-run verification."
        elif n.node_type == "contradiction":
            c = cons.get(n.ref_key)
            if c is None:
                continue
            if c.status in ("open", "under_review"):
                reason = "An unresolved contradiction already exists for this topic."
                action = "Resolve it; choosing the source that matches the new value would settle the disagreement."
            else:
                reason = "A contradiction on this topic was closed earlier, possibly with a different value."
                action = "Confirm the earlier resolution is still correct, or reopen it."
        elif n.node_type == "decision":
            d = decs.get(n.ref_key)
            if d is None or (d.decided_value and _norm_value(d.decided_value) == new_norm):
                continue
            reason = f"An earlier decision confirmed “{d.decided_value}”."
            action = "Record a new decision if the change is approved."
        elif n.node_type == "deliverable":
            reason = f"Was verified against {v.parent.node.label}; that result may no longer be valid."
            action = "Update the deliverable if needed and re-run verification."
        elif n.node_type == "task":
            reason = f"Linked to {v.parent.node.label}, which is affected by this change."
            action = "Review the task's scope before continuing work on it."
        key = (n.node_type, n.ref_key)
        if key not in items:
            items[key] = ImpactItem(
                item_type=n.node_type, item_ref=n.ref_key, label=n.label, level="direct" if direct else "indirect",
                distance=v.distance, path=v.path(), reason=reason, recommended_action=action, confidence=round(conf, 2))
    report.items = list(items.values())
    n_direct = sum(1 for i in report.items if i.level == "direct")
    n_ind = len(report.items) - n_direct
    report.confidence = round(sum(i.confidence for i in report.items) / len(report.items), 2) if report.items else 0.5
    report.summary = (
        f"Changing {subject_label} from “{report.previous_value}” to “{new_value}” directly affects {n_direct} "
        f"item{'s' if n_direct != 1 else ''} and may indirectly affect {n_ind} more. Indirect items were found by "
        "following statements that mention this topic, so they are less certain." if report.items else
        f"No connected documents, requirements or tasks reference {subject_label}; nothing else appears affected.")
    db.add(report)
    log_activity(db, project_id, user_id, "impact.analyzed", f"Impact analysis: {label} → {new_value}")
    db.commit()
    db.refresh(report)
    return report


def _replace_value(description: str, previous: str | None, new: str) -> str:
    """Rewrite the old value inside a requirement description (digits or number words)."""
    if not previous:
        return description
    candidates = [previous]
    n = parse_number(previous.split()[0]) if previous.split() else None
    if n is not None:
        candidates += [w for w, val in NUMBER_WORDS.items() if val == n] + [fmt_number(n)]
    for cand in candidates:
        pat = re.compile(rf"\b{re.escape(cand)}\b", re.I)
        if pat.search(description):
            return pat.sub(new, description, count=1)
    return description


def apply(db: Session, report: ImpactReport, user: User) -> ImpactReport:
    """User-approved: update the affected requirement value, record the decision and suggest follow-ups."""
    if report.status != "draft":
        raise ImpactError("This impact report has already been applied or discarded.")
    new_norm = _norm_value(report.new_value)
    q = select(Requirement).where(Requirement.project_id == report.project_id)
    q = q.where(Requirement.id == report.target_id) if report.target_type == "requirement" else \
        q.where(Requirement.subject_key == report.subject_key, Requirement.subject_key != "")
    for r in db.scalars(q):
        old = r.expected_value
        if r.verification_method == "numeric" or parse_number(new_norm) is not None and r.expected_value is not None:
            r.expected_value = new_norm
        if r.blocked_by_contradiction_id:
            r.description = f"The application must support {report.new_value} {r.title.lower()}."
            r.blocked_by_contradiction_id = None
        else:
            r.description = _replace_value(r.description, old or report.previous_value, report.new_value)
        r.status, r.user_edited = "not_checked", True
    title = f"{report.target_label}: changed to {report.new_value}"
    db.add(Decision(project_id=report.project_id, title=title[:255], subject_key=report.subject_key,
                    description=f"Change approved by {user.name} after impact analysis. Source: {report.source_of_change}.",
                    decided_value=report.new_value, decided_by=user.id))
    add_event(db, report.project_id, "confirmed_change", title, subject_key=report.subject_key,
              description=f"Approved by {user.name} after reviewing {len(report.items)} affected item(s).",
              previous_value=report.previous_value, new_value=report.new_value,
              resolution="Change approved; follow-up tasks suggested.", source=report.source_of_change)
    created = 0
    for it in sorted(report.items, key=lambda i: (i.level != "direct", i.distance)):
        if it.item_type in ("decision", "task", "contradiction") or it.level != "direct" or created >= 5:
            continue
        key = f"impact:{report.id}:{it.item_type}:{it.item_ref}"
        ref = int(it.item_ref) if it.item_ref.isdigit() else None
        verb = {"document": "Update", "deliverable": "Re-verify", "requirement": "Review",
                "contradiction": "Resolve"}.get(it.item_type, "Review")
        db.add(Task(
            project_id=report.project_id, title=f"{verb} {it.label}"[:255], description=it.recommended_action,
            reason=f"Ripple impact of changing {report.target_label} to {report.new_value}: {it.reason}",
            origin="impact", priority="high" if it.level == "direct" else "medium", status="suggested",
            related_document_id=ref if it.item_type in ("document", "deliverable") else None,
            related_requirement_id=ref if it.item_type == "requirement" else None,
            related_contradiction_id=ref if it.item_type == "contradiction" else None,
            related_impact_report_id=report.id, dedupe_key=key))
        created += 1
    report.status, report.applied_at = "applied", utcnow()
    log_activity(db, report.project_id, user.id, "impact.applied", f"Change applied: {title}")
    db.commit()
    from . import tasks

    tasks.generate_suggestions(db, report.project_id)
    return report
