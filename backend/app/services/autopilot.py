"""Autopilot: OxisTrack makes the routine decisions itself and records why.

It chooses the authoritative source for a contradiction, traces the ripple of that decision, and
approves suggested tasks. Every decision is written to the evidence timeline with its reasoning and
can be overruled by a person (re-open the contradiction, or turn Autopilot off in Settings).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Contradiction, ContradictionSource, Document, ExtractedFact, Project, Task, utcnow
from . import contradictions, impact
from .ai import get_provider, get_reviewer
from .common import log_activity
from .contradictions import _UPDATE_HINT, AUTOPILOT_NAME

UNDECIDED_PREFIX = f"{AUTOPILOT_NAME} did not decide"


def _fmt(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def decide(c: Contradiction) -> tuple[ContradictionSource | None, str, float]:
    """Pick the most credible source from the evidence. Returns (source, reasoning, confidence);
    source is None when the evidence is evenly matched and a person has to choose."""
    by_value: dict[str, list[ContradictionSource]] = defaultdict(list)
    for s in c.sources:
        if s.fact_id:
            by_value[s.value_norm].append(s)
    if len(by_value) < 2:
        return None, "There is only one value left to choose from.", 0.0

    dated = {v: max(s.document_date for s in ss if s.document_date)
             for v, ss in by_value.items() if any(s.document_date for s in ss)}
    newest = max(dated.values()) if dated else None
    newest_values = [v for v, d in dated.items() if d == newest]
    doc_counts = {v: len({s.document_id for s in ss}) for v, ss in by_value.items()}
    top_count = max(doc_counts.values())
    majority = [v for v, n in doc_counts.items() if n == top_count]

    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    for v, ss in by_value.items():
        score, why = 0, []
        if any(_UPDATE_HINT.search(s.statement) for s in ss):
            score += 3
            why.append("its source explicitly describes the value as an update")
        if newest and len(newest_values) == 1 and newest_values[0] == v:
            score += 2
            why.append(f"it comes from the most recently dated document ({_fmt(newest)})")
        if len(majority) == 1 and majority[0] == v and top_count > 1:
            score += 1
            why.append(f"{top_count} documents agree on it")
        scores[v], reasons[v] = score, why
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if ranked[0][1] == 0 or ranked[0][1] == ranked[1][1]:
        return None, ("The sources are evenly matched: no document is clearly newer, marked as an update, "
                      "or backed by more sources. A person needs to choose."), 0.0
    best = ranked[0][0]
    chosen = max(by_value[best], key=lambda s: (s.document_date or date.min, s.id))
    confidence = min(0.92, 0.6 + 0.08 * (ranked[0][1] - ranked[1][1]))
    reasoning = f"Chose “{chosen.value_text}” from {chosen.document_name} because " + " and ".join(reasons[best]) + "."
    others = [v for v in by_value if v != best and scores[v] > 0]
    if others:
        reasoning += " The other value had weaker support (" + "; ".join(
            f"“{by_value[v][0].value_text}”: {', '.join(reasons[v])}" for v in others) + ")."
    return chosen, reasoning, confidence


def _ask(model, c: Contradiction, sources: list[ContradictionSource]) -> tuple[ContradictionSource | None, str]:
    """One AI model's opinion. Only accepted when it names one of the real sources."""
    if model is None or not model.uses_llm:
        return None, ""
    res = model.choose_source(c.title, [
        {"index": i, "value": s.value_text, "statement": s.statement, "document": s.document_name,
         "document_date": str(s.document_date or "")} for i, s in enumerate(sources)])
    if res is None or res.index is None or not (0 <= res.index < len(sources)):
        return None, ""
    return sources[res.index], res.reasoning.strip()


def _settle(c: Contradiction) -> tuple[ContradictionSource | None, str, float]:
    """Combine the evidence rules with up to two AI models. Returns (source, note, confidence);
    source is None when they do not agree and a person has to choose."""
    sources = [s for s in c.sources if s.fact_id]
    rule_pick, rule_reason, confidence = decide(c)
    analyst, reviewer = get_provider(), get_reviewer()
    if not analyst.uses_llm:  # rules only
        return (rule_pick, rule_reason, confidence) if rule_pick else (None, rule_reason, 0.0)

    a_pick, a_why = _ask(analyst, c, sources)
    a_name = f"AI analyst ({analyst.model})"
    if reviewer is None:
        if rule_pick is not None and (a_pick is None or a_pick.value_norm == rule_pick.value_norm):
            note = rule_reason + (f" {a_name} agreed: {a_why}" if a_pick else "")
            return rule_pick, note, min(0.95, confidence + (0.05 if a_pick else 0))
        if rule_pick is None:
            return None, f"{rule_reason} No second AI is configured to break the tie.", 0.0
        return None, (f"The evidence rules pointed to “{rule_pick.value_text}” but {a_name} preferred "
                      f"“{a_pick.value_text}”. A person needs to choose."), 0.0

    r_pick, r_why = _ask(reviewer, c, sources)
    r_name = f"AI reviewer ({reviewer.model})"
    votes = [p for p in (rule_pick, a_pick, r_pick) if p is not None]
    for cand in votes:
        backers = sum(1 for p in votes if p.value_norm == cand.value_norm)
        if backers >= 2:
            chosen = max((p for p in votes if p.value_norm == cand.value_norm),
                         key=lambda s: (s.document_date or date.min, s.id))
            parts = [f"Chose “{chosen.value_text}” from {chosen.document_name}."]
            if rule_pick is None:
                parts.append("The evidence rules found the sources evenly matched, so two AI models reviewed them independently.")
            elif rule_pick.value_norm == chosen.value_norm:
                parts = [rule_reason]
            else:
                parts.append(f"The evidence rules pointed to “{rule_pick.value_text}”, but both AI models disagreed.")
            for name, pick, why in ((a_name, a_pick, a_why), (r_name, r_pick, r_why)):
                if pick is None:
                    parts.append(f"{name} did not pick a source.")
                elif pick.value_norm == chosen.value_norm:
                    parts.append(f"{name} agreed: {why}")
                else:
                    parts.append(f"{name} preferred “{pick.value_text}”: {why}")
            return chosen, " ".join(parts), 0.8 if backers == 2 else 0.95
    views = "; ".join(f"{n} chose “{p.value_text}”" for n, p in
                      (("the evidence rules", rule_pick), (a_name, a_pick), (r_name, r_pick)) if p is not None)
    return None, f"No two of the three checks agreed ({views or 'neither AI model picked a source'}). A person needs to choose.", 0.0


def resolve_open(db: Session, project: Project) -> list[Contradiction]:
    """Decide every open contradiction Autopilot has not looked at yet."""
    if not project.autopilot:
        return []
    resolved: list[Contradiction] = []
    pending = db.scalars(select(Contradiction).where(
        Contradiction.project_id == project.id, Contradiction.status == "open",
        Contradiction.ai_reviewed.is_(False)).order_by(Contradiction.id)).all()
    for c in pending:
        chosen, reasoning, confidence = _settle(c)
        c.ai_reviewed = True
        if chosen is None:
            c.resolution_note = f"{UNDECIDED_PREFIX} this one. {reasoning}"
            db.commit()
            continue
        note = f"{reasoning} Confidence {round(confidence * 100)}%. Reopen this to overrule it."
        contradictions.resolve(db, c, None, "resolved", chosen.fact_id, None, note[:1900])
        c.ai_reviewed = True
        log_activity(db, project.id, None, "autopilot.resolved",
                     f"{AUTOPILOT_NAME} resolved {c.code}: {chosen.value_text}", "contradiction", c.id)
        db.commit()
        resolved.append(c)
    return resolved


def ripple(db: Session, project: Project, resolved: list[Contradiction]) -> None:
    """After a decision, trace what it touches and queue one follow-up per document that is now outdated."""
    for c in resolved:
        fact = db.get(ExtractedFact, c.authoritative_fact_id) if c.authoritative_fact_id else None
        if fact is None:
            continue
        old = sorted({s.value_text for s in c.sources if s.role == "superseded"})
        try:
            report = impact.analyze(db, project.id, "fact", fact.id, fact.value_text or "", None,
                                    previous_value=" / ".join(old) or None,
                                    source_of_change=f"{AUTOPILOT_NAME}, resolving {c.code}")
        except impact.ImpactError:
            continue
        label = c.title.split(":")[0]
        for item in report.items:
            if item.item_type != "document" or item.level != "direct" or not item.item_ref.isdigit():
                continue
            doc = db.get(Document, int(item.item_ref))
            if doc is None:
                continue
            key = f"outdated:{doc.id}"
            line = f"{label}: {item.reason} Confirmed value: {fact.value_text}."
            task = db.scalar(select(Task).where(Task.project_id == project.id, Task.dedupe_key == key))
            if task is None:
                db.add(Task(project_id=project.id, title=f"Update {doc.filename}: it states outdated values",
                            description="Edit the document to match the confirmed values, then upload the new version.",
                            reason=line, origin="impact", priority="medium", status="suggested",
                            related_document_id=doc.id, related_impact_report_id=report.id, dedupe_key=key))
                db.flush()
            elif task.status in ("suggested", "active") and line not in task.reason:
                task.reason = f"{task.reason}\n{line}"
        report.status, report.applied_at = "applied", utcnow()
        db.commit()


def approve_tasks(db: Session, project: Project | None) -> int:
    """Approve every waiting suggestion so it becomes an active task."""
    if project is None or not project.autopilot:
        return 0
    n = 0
    for t in db.scalars(select(Task).where(Task.project_id == project.id, Task.status == "suggested")).all():
        t.status, t.auto_approved = "active", True
        n += 1
    db.commit()
    return n
