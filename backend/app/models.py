"""Relational schema for OxisTrack (MySQL via SQLAlchemy 2.0)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

LongText = Text().with_variant(LONGTEXT(), "mysql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Autopilot: OxisTrack resolves contradictions, applies document-driven changes and approves tasks itself.
    autopilot: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    members: Mapped[list[ProjectMember]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class ProjectMember(Base, TimestampMixin):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | editor | viewer
    user: Mapped[User] = relationship()


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_project_kind", "project_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(20), default="source")  # source | deliverable
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|analyzed|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    versions: Mapped[list[DocumentVersion]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="DocumentVersion.version"
    )
    facts: Mapped[list[ExtractedFact]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, back_populates="document"
    )


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_doc_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str | None] = mapped_column(LongText, nullable=True)
    # Ordered list of {"location": str, "text": str}: raw parsed content used for citations.
    segments: Mapped[list | None] = mapped_column(JSON, nullable=True)


class ExtractedFact(Base, TimestampMixin):
    __tablename__ = "extracted_facts"
    __table_args__ = (Index("ix_facts_project_subject", "project_id", "subject_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    document_version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    text: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String(200), default="")
    subject_key: Mapped[str] = mapped_column(String(200), default="")
    value_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    value_norm: Mapped[str | None] = mapped_column(String(300), nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), default="none")  # date|number|money|presence|text|none
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    segment_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    extractor: Mapped[str] = mapped_column(String(30), default="rules")

    document: Mapped[Document] = relationship(back_populates="facts")


class Contradiction(Base, TimestampMixin):
    __tablename__ = "contradictions"
    __table_args__ = (Index("ix_contra_project_status", "project_id", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))  # low|medium|high|critical
    subject_key: Mapped[str] = mapped_column(String(200))
    value_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|under_review|resolved|superseded
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    explanation: Mapped[str] = mapped_column(Text, default="")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    authoritative_fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("extracted_facts.id", ondelete="SET NULL"), nullable=True
    )
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    ai_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    sources: Mapped[list[ContradictionSource]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, back_populates="contradiction"
    )
    resolver: Mapped[User | None] = relationship(foreign_keys=[resolved_by])


class ContradictionSource(Base):
    __tablename__ = "contradiction_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    contradiction_id: Mapped[int] = mapped_column(ForeignKey("contradictions.id", ondelete="CASCADE"), index=True)
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_facts.id", ondelete="SET NULL"), nullable=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    # Snapshot of the evidence so the record stays auditable if the document is later removed.
    document_name: Mapped[str] = mapped_column(String(255), default="")
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement: Mapped[str] = mapped_column(Text, default="")
    value_text: Mapped[str] = mapped_column(String(300), default="")
    value_norm: Mapped[str] = mapped_column(String(300), default="")
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="conflicting")  # conflicting|authoritative|superseded

    contradiction: Mapped[Contradiction] = relationship(back_populates="sources")


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    contradiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("contradictions.id", ondelete="SET NULL"), nullable=True
    )
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_facts.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    subject_key: Mapped[str] = mapped_column(String(200), default="")
    decided_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Requirement(Base, TimestampMixin):
    __tablename__ = "requirements"
    __table_args__ = (Index("ix_req_project_status", "project_id", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="functional")
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high
    source_type: Mapped[str] = mapped_column(String(20), default="manual")  # document|text|manual
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("extracted_facts.id", ondelete="SET NULL"), nullable=True
    )
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    subject_key: Mapped[str] = mapped_column(String(200), default="")
    expected_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    verification_method: Mapped[str] = mapped_column(String(20), default="keyword")
    # keyword | numeric | file_exists | semantic | manual
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="not_checked")  # not_checked|passed|failed|needs_review
    blocked_by_contradiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("contradictions.id", ondelete="SET NULL"), nullable=True
    )
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class RequirementValidation(Base, TimestampMixin):
    __tablename__ = "requirement_validations"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(20))
    checked: Mapped[str] = mapped_column(Text, default="")  # what was checked
    explanation: Mapped[str] = mapped_column(Text, default="")  # why it passed/failed/needs review
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    evidence: Mapped[list[ValidationEvidence]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class ValidationEvidence(Base):
    __tablename__ = "validation_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_validations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    document_name: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    snippet: Mapped[str] = mapped_column(Text, default="")
    polarity: Mapped[str] = mapped_column(String(20), default="supports")  # supports|contradicts|neutral


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("project_id", "node_type", "ref_key", name="uq_graph_node"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    node_type: Mapped[str] = mapped_column(String(20))
    # document|deliverable|fact|topic|requirement|contradiction|decision|task
    ref_key: Mapped[str] = mapped_column(String(200))  # entity id, or subject key for topics
    label: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id", ondelete="CASCADE"), index=True)
    relation: Mapped[str] = mapped_column(String(30))


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_project_status", "project_id", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(30), default="manual")
    # contradiction|failed_check|needs_review|impact|deadline|manual
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested|active|completed|dismissed
    related_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    related_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="SET NULL"), nullable=True
    )
    related_contradiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("contradictions.id", ondelete="SET NULL"), nullable=True
    )
    related_impact_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("impact_reports.id", ondelete="SET NULL"), nullable=True
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ImpactReport(Base, TimestampMixin):
    __tablename__ = "impact_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(20))  # requirement | fact
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_label: Mapped[str] = mapped_column(String(255))
    subject_key: Mapped[str] = mapped_column(String(200), default="")
    previous_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    new_value: Mapped[str] = mapped_column(String(300))
    source_of_change: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|applied|discarded
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list[ImpactItem]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class ImpactItem(Base):
    __tablename__ = "impact_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("impact_reports.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(String(20))
    item_ref: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(10))  # direct | indirect
    distance: Mapped[int] = mapped_column(Integer, default=1)
    path: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class TimelineEvent(Base, TimestampMixin):
    __tablename__ = "timeline_events"
    __table_args__ = (Index("ix_timeline_project_date", "project_id", "event_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    # statement | disagreement | confirmed_change | superseded | info
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    subject_key: Mapped[str] = mapped_column(String(200), default="")
    previous_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    contradiction_id: Mapped[int | None] = mapped_column(
        ForeignKey("contradictions.id", ondelete="SET NULL"), nullable=True
    )
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_facts.id", ondelete="SET NULL"), nullable=True)
    event_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    date_source: Mapped[str] = mapped_column(String(20), default="system")  # document | system


class ActivityLog(Base, TimestampMixin):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(String(500), default="")
