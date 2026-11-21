"""Helpers that turn ORM rows into API schemas with a few joined display fields."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Contradiction, Document, ExtractedFact, Requirement, RequirementValidation, Task,
)
from ..schemas import (
    ContradictionOut, DocumentOut, FactOut, RequirementOut, TaskOut, ValidationOut,
)


def document_out(db: Session, d: Document, counts: dict[int, int] | None = None) -> DocumentOut:
    o = DocumentOut.model_validate(d)
    o.fact_count = counts.get(d.id, 0) if counts is not None else (db.scalar(
        select(func.count()).select_from(ExtractedFact).where(
            ExtractedFact.document_id == d.id, ExtractedFact.is_current.is_(True))) or 0)
    return o


def fact_counts(db: Session, project_id: int) -> dict[int, int]:
    return dict(db.execute(select(ExtractedFact.document_id, func.count()).where(
        ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True))
        .group_by(ExtractedFact.document_id)).all())


def fact_out(f: ExtractedFact) -> FactOut:
    o = FactOut.model_validate(f)
    o.document_name = f.document.filename
    return o


def contradiction_out(db: Session, c: Contradiction) -> ContradictionOut:
    o = ContradictionOut.model_validate(c)
    o.resolved_by_name = c.resolver.name if c.resolver else ("OxisTrack Autopilot" if c.auto_resolved else None)
    return o


def requirement_out(db: Session, r: Requirement, with_validation: bool = True) -> RequirementOut:
    o = RequirementOut.model_validate(r)
    if r.source_document_id:
        o.source_document_name = db.scalar(select(Document.filename).where(Document.id == r.source_document_id))
    if with_validation:
        v = db.scalar(select(RequirementValidation).where(
            RequirementValidation.requirement_id == r.id, RequirementValidation.is_latest.is_(True))
            .order_by(RequirementValidation.id.desc()))
        o.latest_validation = ValidationOut.model_validate(v) if v else None
    return o


def task_out(db: Session, t: Task) -> TaskOut:
    o = TaskOut.model_validate(t)
    if t.related_document_id:
        o.related_document_name = db.scalar(select(Document.filename).where(Document.id == t.related_document_id))
    if t.related_requirement_id:
        o.related_requirement_code = db.scalar(select(Requirement.code).where(Requirement.id == t.related_requirement_id))
    if t.related_contradiction_id:
        o.related_contradiction_code = db.scalar(
            select(Contradiction.code).where(Contradiction.id == t.related_contradiction_id))
    return o
