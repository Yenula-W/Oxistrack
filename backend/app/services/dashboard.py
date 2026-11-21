"""Overview metrics. Every number is computed from stored project records."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    ActivityLog, Contradiction, Document, ExtractedFact, Requirement, Task, TimelineEvent, utcnow,
)


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def overview(db: Session, project_id: int) -> dict:
    docs = db.scalars(select(Document).where(Document.project_id == project_id)).all()
    source_docs = [d for d in docs if d.kind == "source"]
    analyzed = [d for d in source_docs if d.status == "analyzed"]
    facts_total = _count(db, ExtractedFact, ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True))
    cons = db.scalars(select(Contradiction).where(Contradiction.project_id == project_id)
                      .order_by(Contradiction.created_at.desc())).all()
    open_cons = [c for c in cons if c.status in ("open", "under_review")]
    req_status = Counter(db.scalars(select(Requirement.status).where(Requirement.project_id == project_id)))
    req_total = sum(req_status.values())
    task_status = Counter(db.scalars(select(Task.status).where(Task.project_id == project_id)))

    factors, score = [], None
    if analyzed or req_total:
        score = 100.0
        weights = {"critical": 15, "high": 10, "medium": 6, "low": 3}
        pen = min(45, sum(weights.get(c.severity, 5) for c in open_cons))
        if pen:
            factors.append({"label": f"{len(open_cons)} unresolved contradiction{'s' if len(open_cons) != 1 else ''}",
                            "impact": -pen})
        if req_total:
            failed_pen = round(35 * req_status["failed"] / req_total)
            review_pen = round(12 * req_status["needs_review"] / req_total)
            if failed_pen:
                factors.append({"label": f"{req_status['failed']} of {req_total} requirements failed", "impact": -failed_pen})
            if review_pen:
                factors.append({"label": f"{req_status['needs_review']} requirements need review", "impact": -review_pen})
            if req_status["not_checked"] == req_total:
                factors.append({"label": "Requirements have not been verified yet", "impact": 0})
            pen += failed_pen + review_pen
        else:
            factors.append({"label": "No requirements compiled yet", "impact": 0})
        score = max(0, round(score - pen))
    health = {"score": score, "factors": factors,
              "label": None if score is None else "Healthy" if score >= 85 else "Needs attention" if score >= 60 else "At risk"}

    since = (utcnow() - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
    per_day: dict[str, dict] = {}
    for i in range(14):
        day = (since + timedelta(days=i)).date().isoformat()
        per_day[day] = {"date": day, "documents": 0, "facts": 0}
    for d in docs:
        k = d.created_at.date().isoformat()
        if k in per_day:
            per_day[k]["documents"] += 1
    for created in db.scalars(select(ExtractedFact.created_at).where(
            ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True),
            ExtractedFact.created_at >= since)):
        k = created.date().isoformat()
        if k in per_day:
            per_day[k]["facts"] += 1

    fact_cats = Counter(db.scalars(select(ExtractedFact.category).where(
        ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True))))
    changes = db.scalars(select(TimelineEvent).where(
        TimelineEvent.project_id == project_id, TimelineEvent.kind != "info")
        .order_by(TimelineEvent.event_date.desc(), TimelineEvent.id.desc()).limit(6)).all()
    activity = db.scalars(select(ActivityLog).where(ActivityLog.project_id == project_id)
                          .order_by(ActivityLog.id.desc()).limit(8)).all()
    suggested = db.scalars(select(Task).where(Task.project_id == project_id, Task.status.in_(("suggested", "active")))
                           .order_by(Task.status.desc(), Task.id.desc()).limit(5)).all()
    return {
        "metrics": {
            "documents_analyzed": len(analyzed), "documents_total": len(source_docs),
            "deliverables": len(docs) - len(source_docs), "facts": facts_total,
            "open_contradictions": len(open_cons), "contradictions_total": len(cons),
            "requirements_total": req_total, "requirements_passed": req_status["passed"],
            "requirements_failed": req_status["failed"], "requirements_needs_review": req_status["needs_review"],
            "requirements_not_checked": req_status["not_checked"],
            "open_tasks": task_status["active"], "suggested_tasks": task_status["suggested"],
            "completed_tasks": task_status["completed"],
        },
        "health": health,
        "document_activity": list(per_day.values()),
        "fact_categories": [{"category": k, "count": v} for k, v in fact_cats.most_common()],
        "recent_contradictions": cons[:5],
        "recent_changes": changes,
        "suggested_tasks": suggested,
        "recent_activity": activity,
    }
