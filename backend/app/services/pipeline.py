"""Upload storage and the document analysis pipeline:

uploaded documents → document processing (parse, extract facts and requirements, keep evidence)
→ conflict engine + verification engine → knowledge graph → suggested actions."""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import Document, DocumentVersion, ExtractedFact, Project
from . import contradictions, tasks
from .ai import get_provider
from .common import add_event, log_activity
from .parsing import ParseError, Segment, file_type_of, parse_document, sniff_ok
from .rules import detect_document_date
from .textutil import subject_key

log = logging.getLogger("oxistrack.pipeline")


class UploadError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def safe_filename(name: str) -> str:
    name = Path(name.replace("\\", "/")).name  # drop any client-supplied directory parts
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name).strip(" .")
    return name[:200] or "document"


def _storage_path(project_id: int, file_type: str) -> Path:
    root = Path(get_settings().upload_dir).resolve()
    folder = root / str(int(project_id))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4().hex}.{file_type}"  # server-generated name: no path traversal possible


def store_upload(db: Session, project: Project, user_id: int | None, filename: str, data: bytes,
                 kind: str = "source", is_sample: bool = False) -> tuple[Document, bool]:
    """Persist an uploaded file. Returns (document, changed); a re-upload of the same filename becomes a
    new version, and an identical re-upload is a no-op."""
    settings = get_settings()
    name = safe_filename(filename)
    ftype = file_type_of(name)
    if ftype is None:
        raise UploadError(f"“{name}”: unsupported file type. Allowed: PDF, DOCX, TXT, CSV, XLSX, Markdown.", 415)
    if not data:
        raise UploadError(f"“{name}” is empty.")
    if len(data) > settings.max_upload_bytes:
        raise UploadError(f"“{name}” is larger than the {settings.max_upload_mb} MB limit.", 413)
    if not sniff_ok(ftype, data[:2048]):
        raise UploadError(f"“{name}” does not look like a valid {ftype.upper()} file.")
    if kind not in ("source", "deliverable"):
        raise UploadError("Invalid document kind.")

    sha = hashlib.sha256(data).hexdigest()
    doc = db.scalar(select(Document).where(
        Document.project_id == project.id, Document.filename == name, Document.kind == kind))
    if doc and doc.versions and doc.versions[-1].sha256 == sha and doc.status != "failed":
        return doc, False

    path = _storage_path(project.id, ftype)
    path.write_bytes(data)
    if doc is None:
        doc = Document(project_id=project.id, filename=name, file_type=ftype, kind=kind, status="queued",
                       size_bytes=len(data), current_version=1, is_sample=is_sample, uploaded_by=user_id)
        db.add(doc)
        db.flush()
        action = "uploaded"
    else:
        doc.current_version += 1
        doc.status, doc.error, doc.size_bytes = "queued", None, len(data)
        action = f"updated to version {doc.current_version}"
    db.add(DocumentVersion(document_id=doc.id, version=doc.current_version, storage_path=str(path),
                           sha256=sha, size_bytes=len(data)))
    log_activity(db, project.id, user_id, "document.uploaded", f"{name} {action}", "document", doc.id)
    db.commit()
    db.refresh(doc)
    return doc, True


def _read_version_bytes(version: DocumentVersion) -> bytes:
    root = Path(get_settings().upload_dir).resolve()
    path = Path(version.storage_path).resolve()
    if root not in path.parents:
        raise ParseError("Stored file path is outside the upload directory.")
    return path.read_bytes()


def analyze_document(db: Session, document_id: int, user_id: int | None = None) -> Document | None:
    doc = db.get(Document, document_id)
    if doc is None:
        return None
    doc.status, doc.error = "processing", None
    db.commit()
    version = doc.versions[-1]
    try:
        segments = parse_document(doc.file_type, _read_version_bytes(version))
    except ParseError as exc:
        doc.status, doc.error = "failed", str(exc)
        db.commit()
        return doc
    except Exception:  # noqa: BLE001 - never leak parser internals to the client
        log.exception("extraction failed for document %s", document_id)
        doc.status, doc.error = "failed", "Extraction failed: the file could not be read."
        db.commit()
        return doc

    version.segments = [s.as_dict() for s in segments]
    version.extracted_text = "\n".join(s.text for s in segments)
    doc.document_date = detect_document_date(segments, date.today()) or doc.document_date

    previous = db.scalars(select(ExtractedFact).where(
        ExtractedFact.document_id == doc.id, ExtractedFact.is_current.is_(True))).all()
    new_facts: list[ExtractedFact] = []
    if doc.kind == "source":  # deliverables are checked against requirements, not mined for facts
        try:
            drafts = get_provider().extract_facts(segments, doc.document_date or date.today())
        except Exception:  # noqa: BLE001
            log.exception("fact extraction failed for document %s", document_id)
            doc.status, doc.error = "failed", "AI analysis failed while extracting facts."
            db.commit()
            return doc
        for p in previous:
            p.is_current = False
        for d in drafts:
            seg: Segment = segments[d.segment_index]
            new_facts.append(ExtractedFact(
                project_id=doc.project_id, document_id=doc.id, document_version=doc.current_version,
                category=d.category, text=d.text, subject=d.subject[:200], subject_key=subject_key(d.subject),
                value_text=(d.value_text or None) and d.value_text[:300], value_norm=(d.value_norm or None)
                and d.value_norm[:300], value_type=d.value_type, location=seg.location,
                segment_index=d.segment_index, confidence=round(d.confidence, 2), extractor=d.extractor,
            ))
        db.add_all(new_facts)
    doc.status = "analyzed"
    if doc.kind == "source":
        add_event(db, doc.project_id, "info", f"{doc.filename} analyzed" + (
            f" (version {doc.current_version})" if doc.current_version > 1 else ""),
            description=f"{len(new_facts)} facts extracted.", source=doc.filename, document_id=doc.id)
    else:
        add_event(db, doc.project_id, "info", f"Deliverable {doc.filename} received",
                  description="Ready to be verified against the project requirements.",
                  source=doc.filename, document_id=doc.id)
    log_activity(db, doc.project_id, user_id, "document.analyzed",
                 f"{doc.filename}: {len(new_facts)} facts extracted", "document", doc.id)
    db.commit()

    _run_engines(db, doc, previous, new_facts, user_id)
    return doc


def _run_engines(db: Session, doc: Document, previous: list[ExtractedFact], new_facts: list[ExtractedFact],
                 user_id: int | None) -> None:
    """Everything downstream of document processing, in pipeline order:
    conflict engine + verification engine → knowledge graph → suggested actions."""
    from . import autopilot, graph, requirements, verification  # local imports avoid circular dependencies

    project = db.get(Project, doc.project_id)
    decided = []
    if doc.kind == "source":
        if previous:
            _record_version_changes(db, doc, previous, new_facts, user_id)
        contradictions.detect(db, doc.project_id, user_id)                      # conflict engine
        decided = autopilot.resolve_open(db, project)                           # Autopilot picks the source
        requirements.compile_from_documents(db, doc.project_id, user_id, auto=True)
    try:
        verification.run(db, doc.project_id, user_id)                           # verification engine
    except verification.VerificationError:
        pass  # nothing to verify yet: no deliverable or no requirements
    graph.sync(db, doc.project_id)                                              # knowledge graph
    autopilot.ripple(db, project, decided)                                      # impact reports
    tasks.generate_suggestions(db, doc.project_id)                              # action center
    autopilot.approve_tasks(db, project)


def _record_version_changes(db: Session, doc: Document, old: list[ExtractedFact], new: list[ExtractedFact],
                            user_id: int | None) -> None:
    """A new version of a document changed a stated value: record it and draft an impact report."""
    from . import impact  # local import: impact depends on graph, which depends on models only

    old_by_key = {(f.subject_key, f.value_type): f for f in old if f.subject_key and f.value_norm}
    for f in new:
        prev = old_by_key.get((f.subject_key, f.value_type))
        if not prev or not f.value_norm or prev.value_norm == f.value_norm:
            continue
        add_event(db, doc.project_id, "statement",
                  f"{doc.filename} v{doc.current_version} changes {f.subject.lower()} to {f.value_text}",
                  description=f.text, subject_key=f.subject_key, previous_value=prev.value_text,
                  new_value=f.value_text, source=f"{doc.filename} (version {doc.current_version})",
                  document_id=doc.id, fact_id=f.id)
        db.commit()
        impact.analyze(db, doc.project_id, "fact", f.id, f.value_text or "", user_id,
                       previous_value=prev.value_text,
                       source_of_change=f"{doc.filename} version {doc.current_version}")


def run_analysis_background(document_ids: list[int], user_id: int | None = None) -> None:
    """Entry point for FastAPI BackgroundTasks: uses its own DB session."""
    db = SessionLocal()
    try:
        for doc_id in document_ids:
            try:
                analyze_document(db, doc_id, user_id)
            except Exception:  # noqa: BLE001
                log.exception("analysis crashed for document %s", doc_id)
                db.rollback()
                doc = db.get(Document, doc_id)
                if doc:
                    doc.status, doc.error = "failed", "Analysis failed unexpectedly."
                    db.commit()
    finally:
        db.close()


def delete_document(db: Session, doc: Document, user_id: int | None) -> None:
    project_id, name, kind = doc.project_id, doc.filename, doc.kind
    root = Path(get_settings().upload_dir).resolve()
    for v in doc.versions:
        p = Path(v.storage_path).resolve()
        if root in p.parents and p.exists():
            p.unlink()
    db.delete(doc)
    log_activity(db, project_id, user_id, "document.deleted", f"{name} deleted", "document", None)
    add_event(db, project_id, "info", f"{name} removed from the project", source=name)
    db.commit()
    if kind == "source":
        contradictions.detect(db, project_id, user_id)
