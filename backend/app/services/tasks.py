"""Action Center: turn detected problems into suggested tasks. Suggestions need user approval."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Contradiction, Document, ExtractedFact, Requirement, RequirementValidation, Task, ValidationEvidence, utcnow,
)
from .textutil import humanize

STATUSES = ("suggested", "active", "completed", "dismissed")
PRIORITIES = ("low", "medium", "high")
DEADLINE_WINDOW_DAYS = 45


def generate_suggestions(db: Session, project_id: int) -> int:
    wanted: dict[str, Task] = {}

    for c in db.scalars(select(Contradiction).where(
            Contradiction.project_id == project_id, Contradiction.status.in_(("open", "under_review")))):
        label = c.title.split(":")[0]
        docs = sorted({s.document_name for s in c.sources})
        undecided = (c.resolution_note or "").startswith("OxisTrack Autopilot did not decide")
        wanted[f"contradiction:{c.id}"] = Task(
            title=f"Resolve conflicting {label.lower()}",
            description=("Autopilot could not pick a source for this one. " if undecided else "") +
            f"Review the {len(c.sources)} conflicting statements and choose the authoritative source.",
            reason=f"{c.code}: {', '.join(docs)} disagree about {label.lower()}.",
            origin="contradiction", priority={"critical": "high", "high": "high", "medium": "medium"}.get(c.severity, "low"),
            related_contradiction_id=c.id, related_document_id=c.sources[0].document_id if c.sources else None)

    rows = db.execute(select(Requirement, RequirementValidation).join(
        RequirementValidation, RequirementValidation.requirement_id == Requirement.id).where(
        Requirement.project_id == project_id, RequirementValidation.is_latest.is_(True))).all()
    for req, val in rows:
        if req.blocked_by_contradiction_id or val.status != req.status:
            continue
        doc_id = db.scalar(select(ValidationEvidence.document_id).where(
            ValidationEvidence.validation_id == val.id, ValidationEvidence.document_id.is_not(None)).limit(1))
        if doc_id is None:
            doc_id = db.scalar(select(Document.id).where(
                Document.project_id == project_id, Document.kind == "deliverable").limit(1))
        if val.status == "failed":
            wanted[f"failed:{req.id}"] = Task(
                title=f"Fix failed requirement {req.code}: {req.title}",
                description=f"{req.description} Update the deliverable so this requirement is met, then re-run verification.",
                reason=f"Verification failed: {val.explanation}", origin="failed_check", priority=req.priority,
                related_requirement_id=req.id, related_document_id=doc_id)
        elif val.status == "needs_review":
            wanted[f"review:{req.id}"] = Task(
                title=f"Review {req.code}: {req.title}",
                description="Inspect the evidence and record a manual pass or fail.",
                reason=f"Could not be verified automatically: {val.explanation}", origin="needs_review",
                priority="medium" if req.priority == "high" else "low",
                related_requirement_id=req.id, related_document_id=doc_id)

    today = date.today()
    contested = set(db.scalars(select(Contradiction.subject_key).where(
        Contradiction.project_id == project_id, Contradiction.status.in_(("open", "under_review")))))
    resolved = {c.subject_key: c for c in db.scalars(select(Contradiction).where(
        Contradiction.project_id == project_id, Contradiction.status == "resolved"))}
    seen_subjects: set[str] = set()
    for f in db.scalars(select(ExtractedFact).where(
            ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True),
            ExtractedFact.category == "deadline", ExtractedFact.value_type == "date")):
        if f.subject_key in contested or f.subject_key in seen_subjects:
            continue
        c = resolved.get(f.subject_key)
        if c and c.authoritative_fact_id and c.authoritative_fact_id != f.id:
            continue
        try:
            d = date.fromisoformat(f.value_norm or "")
        except ValueError:
            continue
        days = (d - today).days
        if 0 <= days <= DEADLINE_WINDOW_DAYS:
            seen_subjects.add(f.subject_key)
            wanted[f"deadline:{f.subject_key}"] = Task(
                title=f"{humanize(f.subject.lower())} in {days} day{'s' if days != 1 else ''} ({f.value_text})",
                description="Confirm the remaining work fits before this date.",
                reason=f"{f.document.filename} states: “{f.text}”", origin="deadline",
                priority="high" if days <= 14 else "medium", related_document_id=f.document_id, due_date=d)

    existing = {t.dedupe_key: t for t in db.scalars(select(Task).where(
        Task.project_id == project_id, Task.dedupe_key.is_not(None)))}
    created = 0
    for key, t in wanted.items():
        if key in existing:
            cur = existing[key]
            if key.startswith("deadline:") and cur.status in ("suggested", "active") and cur.title != t.title:
                # the confirmed deadline moved: keep one task and bring it up to date
                cur.title, cur.reason, cur.due_date, cur.priority = t.title, t.reason, t.due_date, t.priority
                cur.related_document_id = t.related_document_id
            continue
        t.project_id, t.dedupe_key, t.status = project_id, key, "suggested"
        db.add(t)
        created += 1
    # Withdraw suggestions (never approved tasks) whose cause no longer exists.
    for key, t in existing.items():
        if key in wanted or key.startswith(("impact:", "outdated:")):
            continue
        if t.status == "suggested":
            db.delete(t)
        elif t.status == "active" and t.auto_approved:  # Autopilot opened it; the cause is gone, so close it
            t.status, t.completed_at = "completed", utcnow()
            t.reason = f"{t.reason}\nClosed automatically: the underlying issue no longer exists."
    db.commit()
    return created
