from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORM):
    id: int
    email: str
    name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


# ---- projects
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    autopilot: bool = True


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    autopilot: bool | None = None


class ProjectOut(ORM):
    id: int
    name: str
    description: str
    is_demo: bool
    autopilot: bool
    owner_id: int
    created_at: datetime
    updated_at: datetime
    role: str | None = None


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["editor", "viewer"] = "editor"


class MemberOut(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    role: str


# ---- documents & facts
class DocumentOut(ORM):
    id: int
    project_id: int
    filename: str
    file_type: str
    kind: str
    status: str
    error: str | None
    size_bytes: int
    current_version: int
    document_date: date | None
    is_sample: bool
    created_at: datetime
    updated_at: datetime
    fact_count: int = 0


class FactOut(ORM):
    id: int
    project_id: int
    document_id: int
    document_name: str = ""
    document_version: int
    category: str
    text: str
    subject: str
    subject_key: str
    value_text: str | None
    value_type: str
    location: str | None
    segment_index: int | None
    confidence: float
    extractor: str
    created_at: datetime


class VersionOut(ORM):
    version: int
    size_bytes: int
    sha256: str
    created_at: datetime


class DocumentDetail(DocumentOut):
    segments: list[dict] = []
    facts: list[FactOut] = []
    versions: list[VersionOut] = []


class UploadOut(BaseModel):
    documents: list[DocumentOut]
    unchanged: list[str] = []
    errors: list[str] = []


# ---- contradictions
class SourceOut(ORM):
    id: int
    fact_id: int | None
    document_id: int | None
    document_name: str
    document_date: date | None
    statement: str
    value_text: str
    location: str | None
    role: str


class ContradictionOut(ORM):
    id: int
    code: str
    title: str
    category: str
    severity: str
    subject_key: str
    status: str
    confidence: float
    explanation: str
    resolution_note: str | None
    authoritative_fact_id: int | None
    resolved_by_name: str | None = None
    auto_resolved: bool = False
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    sources: list[SourceOut] = []


class ResolveIn(BaseModel):
    status: Literal["open", "under_review", "resolved", "superseded"]
    authoritative_fact_id: int | None = None
    superseded_fact_ids: list[int] | None = None
    note: str | None = Field(default=None, max_length=2000)


# ---- requirements & verification
class CompileIn(BaseModel):
    source: Literal["text", "documents"] = "text"
    text: str | None = Field(default=None, max_length=20000)


class RequirementIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="functional", max_length=40)
    priority: Literal["low", "medium", "high"] = "medium"
    verification_method: Literal["keyword", "numeric", "file_exists", "semantic", "manual"] = "keyword"
    expected_value: str | None = Field(default=None, max_length=300)
    keywords: list[str] | None = None


class RequirementPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=40)
    priority: Literal["low", "medium", "high"] | None = None
    verification_method: Literal["keyword", "numeric", "file_exists", "semantic", "manual"] | None = None
    expected_value: str | None = Field(default=None, max_length=300)
    keywords: list[str] | None = None


class EvidenceOut(ORM):
    id: int
    document_id: int | None
    document_name: str
    location: str | None
    snippet: str
    polarity: str


class ValidationOut(ORM):
    id: int
    requirement_id: int
    run_id: str
    is_latest: bool
    status: str
    method: str
    checked: str
    explanation: str
    reviewed_by: int | None
    created_at: datetime
    evidence: list[EvidenceOut] = []


class RequirementOut(ORM):
    id: int
    code: str
    title: str
    description: str
    category: str
    priority: str
    source_type: str
    source_text: str | None
    source_fact_id: int | None
    source_document_id: int | None
    source_document_name: str | None = None
    subject_key: str
    expected_value: str | None
    verification_method: str
    keywords: list[str] | None
    status: str
    blocked_by_contradiction_id: int | None
    created_at: datetime
    updated_at: datetime
    latest_validation: ValidationOut | None = None


class CompileOut(BaseModel):
    created: list[RequirementOut]
    skipped_duplicates: int


class VerifyIn(BaseModel):
    requirement_ids: list[int] | None = None


class ReviewIn(BaseModel):
    status: Literal["passed", "failed"]
    note: str = Field(min_length=3, max_length=2000)


# ---- graph / impact
class GraphNodeOut(ORM):
    id: int
    node_type: str
    ref_key: str
    label: str
    detail: str
    status: str | None


class GraphEdgeOut(ORM):
    id: int
    source_id: int
    target_id: int
    relation: str


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class ImpactIn(BaseModel):
    target_type: Literal["fact", "requirement"]
    target_id: int
    new_value: str = Field(min_length=1, max_length=300)
    source_of_change: str | None = Field(default=None, max_length=255)


class ImpactItemOut(ORM):
    id: int
    item_type: str
    item_ref: str
    label: str
    level: str
    distance: int
    path: str
    reason: str
    recommended_action: str
    confidence: float


class ImpactReportOut(ORM):
    id: int
    project_id: int
    target_type: str
    target_id: int | None
    target_label: str
    previous_value: str | None
    new_value: str
    source_of_change: str
    summary: str
    confidence: float
    status: str
    created_at: datetime
    applied_at: datetime | None
    items: list[ImpactItemOut] = []


# ---- tasks / timeline / activity
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: date | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["suggested", "active", "completed", "dismissed"] | None = None
    due_date: date | None = None


class TaskOut(ORM):
    id: int
    title: str
    description: str
    reason: str
    origin: str
    priority: str
    status: str
    related_document_id: int | None
    related_document_name: str | None = None
    related_requirement_id: int | None
    related_requirement_code: str | None = None
    related_contradiction_id: int | None
    related_contradiction_code: str | None = None
    related_impact_report_id: int | None
    due_date: date | None
    auto_approved: bool = False
    created_at: datetime
    completed_at: datetime | None


class TimelineOut(ORM):
    id: int
    kind: str
    title: str
    description: str
    subject_key: str
    previous_value: str | None
    new_value: str | None
    resolution: str | None
    source: str
    document_id: int | None
    contradiction_id: int | None
    event_date: datetime
    date_source: str
    created_at: datetime


class ActivityOut(ORM):
    id: int
    action: str
    message: str
    entity_type: str | None
    entity_id: int | None
    created_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
