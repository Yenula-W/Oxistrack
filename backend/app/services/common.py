from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ActivityLog, TimelineEvent, utcnow


def log_activity(db: Session, project_id: int | None, user_id: int | None, action: str, message: str,
                 entity_type: str | None = None, entity_id: int | None = None) -> None:
    db.add(ActivityLog(project_id=project_id, user_id=user_id, action=action, message=message[:500],
                       entity_type=entity_type, entity_id=entity_id))


def add_event(db: Session, project_id: int, kind: str, title: str, *, description: str = "",
              subject_key: str = "", previous_value: str | None = None, new_value: str | None = None,
              resolution: str | None = None, source: str = "", document_id: int | None = None,
              contradiction_id: int | None = None, fact_id: int | None = None,
              event_date: datetime | None = None, date_source: str = "system") -> TimelineEvent:
    ev = TimelineEvent(
        project_id=project_id, kind=kind, title=title[:255], description=description,
        subject_key=subject_key, previous_value=previous_value, new_value=new_value, resolution=resolution,
        source=source[:255], document_id=document_id, contradiction_id=contradiction_id, fact_id=fact_id,
        event_date=event_date or utcnow(), date_source=date_source,
    )
    db.add(ev)
    return ev


def next_code(db: Session, model, project_id: int, prefix: str) -> str:
    n = db.scalar(select(func.count()).select_from(model).where(model.project_id == project_id)) or 0
    existing = set(db.scalars(select(model.code).where(model.project_id == project_id)))
    while True:
        n += 1
        code = f"{prefix}-{n:03d}"
        if code not in existing:
            return code
