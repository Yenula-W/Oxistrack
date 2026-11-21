"""Requirement compiler: natural-language text or extracted document facts → structured requirements."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Contradiction, Document, ExtractedFact, Requirement
from . import rules
from .ai import get_provider
from .common import log_activity, next_code
from .rules import RequirementDraft
from .textutil import humanize

METHODS = ("keyword", "numeric", "file_exists", "semantic", "manual")
STATUSES = ("not_checked", "passed", "failed", "needs_review")


def _existing_keys(db: Session, project_id: int) -> set[str]:
    return set(db.scalars(select(Requirement.subject_key).where(Requirement.project_id == project_id)))


def _create(db: Session, project_id: int, d: RequirementDraft, source_type: str, **extra) -> Requirement:
    r = Requirement(
        project_id=project_id, code=next_code(db, Requirement, project_id, "REQ"), title=d.title[:255],
        description=d.description, category=d.category, priority=d.priority, source_type=source_type,
        source_text=d.source_text, subject_key=d.subject_key, expected_value=d.expected_value,
        verification_method=d.verification_method, keywords=d.keywords, status="not_checked", **extra,
    )
    db.add(r)
    db.flush()
    return r


def compile_from_text(db: Session, project_id: int, text: str, user_id: int | None) -> dict:
    drafts = get_provider().compile_requirements(text)
    seen = _existing_keys(db, project_id)
    created, skipped = [], 0
    for d in drafts:
        if d.subject_key in seen:
            skipped += 1
            continue
        seen.add(d.subject_key)
        created.append(_create(db, project_id, d, "text"))
    log_activity(db, project_id, user_id, "requirements.compiled",
                 f"{len(created)} requirements compiled from instructions")
    db.commit()
    return {"created": created, "skipped_duplicates": skipped}


def compile_from_documents(db: Session, project_id: int, user_id: int | None, auto: bool = False) -> dict:
    """One requirement per requirement topic found in the source documents. Where sources disagree and
    the contradiction is unresolved, the requirement is created but held for review rather than guessed."""
    facts = db.scalars(
        select(ExtractedFact).join(Document, Document.id == ExtractedFact.document_id).where(
            ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True),
            Document.kind == "source", ExtractedFact.category.in_(("requirement", "constraint")),
            ExtractedFact.subject_key != "",
        ).order_by(ExtractedFact.id)
    ).all()
    groups: dict[str, list[ExtractedFact]] = defaultdict(list)
    for f in facts:
        groups[f.subject_key].append(f)
    seen = _existing_keys(db, project_id)
    created, skipped = [], 0
    for key, group in groups.items():
        if key in seen:
            skipped += 1
            _hold_if_contested(db, project_id, key, group)
            continue
        first = group[0]
        numeric = [f for f in group if f.value_type == "number"]
        values = sorted({f.value_norm for f in numeric})
        expected, blocked, source = (values[0] if len(values) == 1 else None), None, first
        description = first.text if first.text.endswith(".") else first.text + "."
        if len(values) > 1:
            c = db.scalar(select(Contradiction).where(
                Contradiction.project_id == project_id, Contradiction.subject_key == key,
                Contradiction.value_type == "number").order_by(Contradiction.id.desc()))
            auth = next((f for f in numeric if c and c.authoritative_fact_id == f.id), None)
            if c and c.status == "resolved" and auth:
                expected, source = auth.value_norm, auth
                description = auth.text if auth.text.endswith(".") else auth.text + "."
            else:
                blocked = c.id if c else None
                description = (f"Sources disagree on {first.subject.lower()} ({' vs '.join(values)}). "
                               "Resolve the contradiction to finalise this requirement.")
        prohibited = any(f.value_norm == "prohibited" for f in group)
        method = "manual" if prohibited else rules.method_for(source.text, expected)
        if numeric and expected is None:
            method = "numeric"
        draft = RequirementDraft(
            title=humanize(first.subject.strip()), description=description,
            category=rules.categorize(source.text), priority=rules.priority_of(source.text),
            verification_method=method, keywords=rules.keywords_for(first.subject), subject_key=key,
            expected_value=expected, source_text=source.text,
        )
        created.append(_create(db, project_id, draft, "document", source_fact_id=source.id,
                               source_document_id=source.document_id, blocked_by_contradiction_id=blocked))
        seen.add(key)
    if created or not auto:
        log_activity(db, project_id, user_id, "requirements.compiled",
                     f"{len(created)} requirement{'s' if len(created) != 1 else ''} compiled from documents")
    db.commit()
    return {"created": created, "skipped_duplicates": skipped}


def _hold_if_contested(db: Session, project_id: int, key: str, group: list[ExtractedFact]) -> None:
    """A requirement compiled earlier becomes contested when a later document states a different value.
    It is put on hold (never silently re-valued) until the contradiction is resolved."""
    values = sorted({f.value_norm for f in group if f.value_type == "number"})
    if len(values) < 2:
        return
    req = db.scalar(select(Requirement).where(
        Requirement.project_id == project_id, Requirement.subject_key == key,
        Requirement.source_type == "document", Requirement.user_edited.is_(False)))
    c = db.scalar(select(Contradiction).where(
        Contradiction.project_id == project_id, Contradiction.subject_key == key,
        Contradiction.value_type == "number").order_by(Contradiction.id.desc()))
    if req is None or c is None or c.status not in ("open", "under_review") or req.blocked_by_contradiction_id == c.id:
        return
    req.blocked_by_contradiction_id, req.expected_value, req.status = c.id, None, "not_checked"
    req.verification_method = "numeric"
    req.description = (f"Sources disagree on {group[0].subject.lower()} ({' vs '.join(values)}). "
                       "Resolve the contradiction to finalise this requirement.")
