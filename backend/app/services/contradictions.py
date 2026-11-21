"""Cross-document contradiction detection and resolution."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..models import (
    Contradiction, ContradictionSource, Decision, Document, ExtractedFact, Requirement, TimelineEvent, User, utcnow,
)
from .common import add_event, log_activity, next_code
from .rules import META_KEYS
from .textutil import humanize, subject_key

COMPARABLE_TYPES = ("date", "number", "money", "presence", "text")
META_SUBJECT_KEYS = {subject_key(k) for k in META_KEYS}
STATUSES = ("open", "under_review", "resolved", "superseded")
_UPDATE_HINT = re.compile(r"\b(updated|revised|new|now|changed to|moved to|amended|latest|supersedes?)\b", re.I)


def comparable_facts(db: Session, project_id: int) -> list[ExtractedFact]:
    rows = db.scalars(
        select(ExtractedFact).join(Document, Document.id == ExtractedFact.document_id).where(
            ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True),
            Document.kind == "source", ExtractedFact.value_type.in_(COMPARABLE_TYPES),
            ExtractedFact.subject_key != "",
        ).order_by(ExtractedFact.id)
    ).all()
    return [f for f in rows if f.subject_key not in META_SUBJECT_KEYS and f.value_norm]


def _classify(facts: list[ExtractedFact], value_type: str, n_values: int) -> tuple[str, str]:
    cats = {f.category for f in facts}
    if value_type == "date":
        return ("deadline_conflict", "critical" if n_values >= 3 else "high") if "deadline" in cats \
            else ("deadline_conflict", "medium")
    if value_type == "money":
        return "budget_conflict", "high"
    if value_type == "number":
        if cats & {"requirement", "constraint"}:
            return "requirement_conflict", "high"
        return "numerical_conflict", "medium"
    if value_type == "presence":
        return "requirement_conflict", "high"
    if "technical_spec" in cats:
        return "specification_conflict", "medium"
    return "inconsistent_statement", "low"


def _doc_date_dt(doc: Document) -> tuple[datetime, str]:
    if doc.document_date:
        return datetime.combine(doc.document_date, datetime.min.time()), "document"
    return doc.created_at, "system"


def _source_from_fact(f: ExtractedFact) -> ContradictionSource:
    return ContradictionSource(
        fact_id=f.id, document_id=f.document_id, document_name=f.document.filename,
        document_date=f.document.document_date, statement=f.text, value_text=f.value_text or "",
        value_norm=f.value_norm or "", location=f.location, role="conflicting",
    )


def _explain(label: str, facts: list[ExtractedFact]) -> str:
    parts = [f"“{f.value_text}” in {f.document.filename}" + (f" ({f.location})" if f.location else "")
             for f in facts]
    text = f"{len(facts)} statements about “{label}” do not agree: " + "; ".join(parts) + "."
    hinted = [f.document.filename for f in facts if _UPDATE_HINT.search(f.text)]
    if hinted:
        text += (f" {', '.join(sorted(set(hinted)))} describes its value as an update, which may mean the other "
                 "sources are outdated. A newer document is not automatically correct, though.")
    text += " Review the evidence and choose which source is authoritative."
    return text


def _statement_events(db: Session, c: Contradiction, label: str, facts: list[ExtractedFact]) -> None:
    """Record what each source said, dated by the document's own date when it states one."""
    for f in sorted(facts, key=lambda x: _doc_date_dt(x.document)[0]):
        dt, src = _doc_date_dt(f.document)
        add_event(db, c.project_id, "statement", f"{f.document.filename} states {label.lower()}: {f.value_text}",
                  description=f.text, subject_key=c.subject_key, new_value=f.value_text,
                  source=f.document.filename, document_id=f.document_id, contradiction_id=c.id,
                  fact_id=f.id, event_date=dt, date_source=src)


def detect(db: Session, project_id: int, user_id: int | None = None) -> dict:
    groups: dict[tuple[str, str], list[ExtractedFact]] = defaultdict(list)
    for f in comparable_facts(db, project_id):
        groups[(f.subject_key, f.value_type)].append(f)

    existing = {}
    for c in db.scalars(select(Contradiction).where(Contradiction.project_id == project_id)
                        .order_by(Contradiction.id)):
        existing[(c.subject_key, c.value_type)] = c

    created = updated = reopened = closed = 0
    conflict_keys = set()
    for key, facts in groups.items():
        values = {f.value_norm for f in facts}
        if len(values) < 2:
            continue
        conflict_keys.add(key)
        # one piece of evidence per (document, value)
        uniq: dict[tuple[int, str], ExtractedFact] = {}
        for f in facts:
            uniq.setdefault((f.document_id, f.value_norm), f)
        ev_facts = list(uniq.values())
        label = humanize(Counter(f.subject.strip().lower() for f in ev_facts).most_common(1)[0][0])
        category, severity = _classify(ev_facts, key[1], len(values))
        n_docs = len({f.document_id for f in ev_facts})
        title = f"{label}: {len(values)} different values across {n_docs} document{'s' if n_docs != 1 else ''}"
        confidence = round(min(f.confidence for f in ev_facts) * 0.97, 2)
        c = existing.get(key)

        if c is None:
            c = Contradiction(
                project_id=project_id, code=next_code(db, Contradiction, project_id, "CON"), title=title,
                category=category, severity=severity, subject_key=key[0], value_type=key[1], status="open",
                confidence=confidence, explanation=_explain(label, ev_facts),
                sources=[_source_from_fact(f) for f in ev_facts],
            )
            db.add(c)
            db.flush()
            created += 1
            _statement_events(db, c, label, ev_facts)
            add_event(db, project_id, "disagreement", f"Unresolved disagreement detected: {label.lower()}",
                      description=c.explanation, subject_key=key[0],
                      new_value=" vs ".join(sorted({f.value_text or '' for f in ev_facts})),
                      source="OxisTrack detection", contradiction_id=c.id)
            log_activity(db, project_id, user_id, "contradiction.detected", f"{c.code}: {title}", "contradiction", c.id)
            continue

        known_values = {s.value_norm for s in c.sources}
        known_facts = {s.fact_id for s in c.sources}
        new_facts = [f for f in ev_facts if f.id not in known_facts]
        if c.status in ("resolved", "superseded"):
            fresh = [f for f in new_facts if f.value_norm not in known_values]
            if not fresh:
                continue
            c.status, c.resolved_at, c.resolved_by, c.authoritative_fact_id = "open", None, None, None
            c.resolution_note, c.auto_resolved, c.ai_reviewed = None, False, False
            for s in c.sources:
                s.role = "conflicting"
            reopened += 1
            add_event(db, project_id, "disagreement", f"Disagreement reopened: {label.lower()}",
                      description="A new conflicting value appeared after this issue was closed.",
                      subject_key=key[0], new_value=", ".join(f.value_text or "" for f in fresh),
                      source=fresh[0].document.filename, document_id=fresh[0].document_id, contradiction_id=c.id)
        current_ids = {f.id for f in ev_facts}
        stale = [s for s in c.sources if s.fact_id not in current_ids]
        if new_facts or stale:
            for s in stale:
                c.sources.remove(s)
            for f in new_facts:
                c.sources.append(_source_from_fact(f))
            _statement_events(db, c, label, new_facts)
            c.title, c.category, c.severity, c.confidence = title, category, severity, confidence
            c.explanation = _explain(label, ev_facts)
            updated += 1
            ev = db.scalar(select(TimelineEvent).where(
                TimelineEvent.contradiction_id == c.id, TimelineEvent.kind == "disagreement")
                .order_by(TimelineEvent.id.desc()))
            if ev is not None and c.status in ("open", "under_review"):  # keep the open disagreement current
                ev.description = c.explanation
                ev.new_value = " vs ".join(sorted({f.value_text or "" for f in ev_facts}))

    for key, c in existing.items():
        if key not in conflict_keys and c.status in ("open", "under_review"):
            c.status, c.resolved_at = "resolved", utcnow()
            c.resolution_note = ("Closed automatically: the remaining sources no longer disagree "
                                 "(a document was removed or replaced).")
            closed += 1
            add_event(db, project_id, "info", f"Disagreement no longer present: {c.title.split(':')[0].lower()}",
                      description=c.resolution_note, subject_key=c.subject_key, contradiction_id=c.id,
                      source="OxisTrack detection")
    db.commit()
    return {"created": created, "updated": updated, "reopened": reopened, "closed": closed}


AUTOPILOT_NAME = "OxisTrack Autopilot"


def resolve(db: Session, c: Contradiction, user: User | None, status: str, authoritative_fact_id: int | None,
            superseded_fact_ids: list[int] | None, note: str | None) -> Contradiction:
    """Resolve or re-open a contradiction. `user=None` means the decision was made by Autopilot."""
    label = c.title.split(":")[0]
    actor = user.name if user else AUTOPILOT_NAME
    actor_id = user.id if user else None
    c.auto_resolved = user is None and status == "resolved"
    if user is not None:
        c.ai_reviewed = True  # a person has taken over: Autopilot will not decide this one again
    note = (note or "").strip() or None
    if status in ("open", "under_review"):
        reopening = c.status in ("resolved", "superseded")
        c.status = status
        if reopening:
            c.resolved_at = c.resolved_by = c.authoritative_fact_id = None
            for s in c.sources:
                s.role = "conflicting"
            add_event(db, c.project_id, "disagreement", f"Disagreement reopened: {label.lower()}",
                      description=note or "Reopened for review.", subject_key=c.subject_key,
                      contradiction_id=c.id, source=actor)
        if note:
            c.resolution_note = note
        log_activity(db, c.project_id, actor_id, "contradiction.status", f"{c.code} marked {status.replace('_', ' ')}",
                     "contradiction", c.id)
        db.commit()
        return c

    by_fact = {s.fact_id: s for s in c.sources if s.fact_id}
    if status == "resolved":
        if authoritative_fact_id is None and not note:
            raise ValueError("Choose an authoritative source or explain how the issue was resolved.")
        if authoritative_fact_id is not None and authoritative_fact_id not in by_fact:
            raise ValueError("The authoritative source must be one of the conflicting statements.")
    elif status == "superseded" and not note:
        raise ValueError("Explain why this issue is superseded.")

    c.status, c.resolution_note, c.resolved_by, c.resolved_at = status, note, actor_id, utcnow()
    c.authoritative_fact_id = authoritative_fact_id if status == "resolved" else None
    superseded = set(superseded_fact_ids or [])
    auth = by_fact.get(authoritative_fact_id) if authoritative_fact_id else None
    for s in c.sources:
        if auth is not None and s is auth:
            s.role = "authoritative"
        elif s.fact_id in superseded or (auth is not None and s.value_norm != auth.value_norm and not superseded_fact_ids):
            s.role = "superseded"
        elif auth is not None and s.value_norm == auth.value_norm:
            s.role = "authoritative"
        else:
            s.role = "conflicting"

    if status == "resolved":
        others = sorted({s.value_text for s in c.sources if auth is None or s.value_norm != auth.value_norm})
        if auth is not None:
            db.add(Decision(
                project_id=c.project_id, contradiction_id=c.id, fact_id=auth.fact_id,
                title=f"{label} confirmed as {auth.value_text}", subject_key=c.subject_key,
                description=note or f"{auth.document_name} chosen as the authoritative source.",
                decided_value=auth.value_text, decided_by=actor_id,
            ))
            add_event(db, c.project_id, "confirmed_change", f"{label} confirmed as {auth.value_text}",
                      description=f"{actor} marked {auth.document_name} as the authoritative source.",
                      subject_key=c.subject_key, previous_value=" / ".join(others) or None,
                      new_value=auth.value_text, resolution=note or "Authoritative source selected.",
                      source=auth.document_name, document_id=auth.document_id, contradiction_id=c.id,
                      fact_id=auth.fact_id)
            _sync_requirements(db, c, auth)
        else:
            add_event(db, c.project_id, "confirmed_change", f"{label}: disagreement resolved",
                      description=f"Resolved by {actor} without selecting a single source.",
                      subject_key=c.subject_key, resolution=note, source=actor, contradiction_id=c.id)
        for s in c.sources:
            if s.role == "superseded":
                add_event(db, c.project_id, "superseded", f"{s.document_name} superseded for {label.lower()}",
                          description=f"Its value “{s.value_text}” was explicitly marked as superseded.",
                          subject_key=c.subject_key, previous_value=s.value_text,
                          new_value=auth.value_text if auth else None, source=s.document_name,
                          document_id=s.document_id, contradiction_id=c.id, fact_id=s.fact_id)
    else:
        add_event(db, c.project_id, "superseded", f"{label}: issue marked superseded",
                  description=note or "", subject_key=c.subject_key, resolution=note, source=actor,
                  contradiction_id=c.id)
    log_activity(db, c.project_id, actor_id, "contradiction.resolved", f"{c.code} {status} by {actor}",
                 "contradiction", c.id)
    db.commit()
    return c


def _sync_requirements(db: Session, c: Contradiction, auth: ContradictionSource) -> None:
    """A requirement that was waiting on this contradiction takes the confirmed value (user-approved)."""
    reqs = db.scalars(select(Requirement).where(
        Requirement.project_id == c.project_id,
        or_(Requirement.blocked_by_contradiction_id == c.id,
            and_(Requirement.subject_key == c.subject_key, Requirement.source_type == "document",
                 Requirement.user_edited.is_(False))))).all()
    for r in reqs:
        if c.value_type != "number" and r.blocked_by_contradiction_id != c.id:
            continue
        r.blocked_by_contradiction_id = None
        r.status = "not_checked"
        if c.value_type == "number":
            r.expected_value = auth.value_norm
            r.verification_method = "numeric"
        r.description = auth.statement if auth.statement.endswith(".") else auth.statement + "."
        r.source_fact_id, r.source_document_id, r.source_text = auth.fact_id, auth.document_id, auth.statement
