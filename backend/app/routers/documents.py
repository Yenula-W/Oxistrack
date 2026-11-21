from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import current_user, require_entity, require_project
from ..models import Document, ExtractedFact, User
from ..schemas import DocumentDetail, DocumentOut, FactOut, UploadOut, VersionOut
from ..security import RateLimiter
from ..services import pipeline
from .serializers import document_out, fact_counts, fact_out

router = APIRouter(tags=["documents"])
upload_limit = RateLimiter(limit=30, window_seconds=60, bucket="upload")
MAX_FILES = 12


@router.post("/projects/{project_id}/documents", response_model=UploadOut, status_code=201,
             dependencies=[Depends(upload_limit)])
async def upload_documents(project_id: int, background: BackgroundTasks, files: list[UploadFile] = File(...),
                           kind: str = Form("source"), user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    project = require_project(db, project_id, user, write=True)
    if kind not in ("source", "deliverable"):
        raise HTTPException(400, "kind must be 'source' or 'deliverable'.")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload at most {MAX_FILES} files at a time.")
    limit = get_settings().max_upload_bytes
    created, unchanged, errors = [], [], []
    for f in files:
        data = await f.read(limit + 1)
        try:
            doc, changed = pipeline.store_upload(db, project, user.id, f.filename or "document", data, kind)
        except pipeline.UploadError as exc:
            errors.append(str(exc))
            continue
        (created if changed else unchanged).append(doc)
    if not created and not unchanged:
        raise HTTPException(400, " ".join(errors) or "No files were uploaded.")
    if created:
        background.add_task(pipeline.run_analysis_background, [d.id for d in created], user.id)
    return UploadOut(documents=[document_out(db, d) for d in created + unchanged],
                     unchanged=[d.filename for d in unchanged], errors=errors)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(project_id: int, kind: str | None = None, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    q = select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc(), Document.id.desc())
    if kind:
        q = q.where(Document.kind == kind)
    counts = fact_counts(db, project_id)
    return [document_out(db, d, counts) for d in db.scalars(q)]


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = require_entity(db, Document, document_id, user, name="Document")
    facts = db.scalars(select(ExtractedFact).where(
        ExtractedFact.document_id == d.id, ExtractedFact.is_current.is_(True))
        .order_by(ExtractedFact.segment_index, ExtractedFact.id)).all()
    base = document_out(db, d).model_dump()
    latest = d.versions[-1] if d.versions else None
    return DocumentDetail(**base, segments=(latest.segments or []) if latest else [],
                          facts=[fact_out(f) for f in facts],
                          versions=[VersionOut.model_validate(v) for v in d.versions])


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = require_entity(db, Document, document_id, user, write=True, name="Document")
    pipeline.delete_document(db, d, user.id)
    return Response(status_code=204)


@router.post("/documents/{document_id}/analyze", response_model=DocumentOut, status_code=202)
def analyze_document(document_id: int, background: BackgroundTasks, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    d = require_entity(db, Document, document_id, user, write=True, name="Document")
    if d.status == "processing":
        raise HTTPException(409, "This document is already being analyzed.")
    d.status, d.error = "queued", None
    db.commit()
    background.add_task(pipeline.run_analysis_background, [d.id], user.id)
    return document_out(db, d)


@router.get("/projects/{project_id}/facts", response_model=list[FactOut])
def list_facts(project_id: int, category: str | None = None, document_id: int | None = None,
               q: str | None = Query(default=None, max_length=200), user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    query = select(ExtractedFact).where(
        ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True)).order_by(
        ExtractedFact.document_id, ExtractedFact.segment_index, ExtractedFact.id)
    if category:
        query = query.where(ExtractedFact.category == category)
    if document_id:
        query = query.where(ExtractedFact.document_id == document_id)
    if q:
        query = query.where(ExtractedFact.text.ilike(f"%{q}%"))
    return [fact_out(f) for f in db.scalars(query.limit(1000))]


@router.get("/facts/{fact_id}", response_model=FactOut)
def get_fact(fact_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return fact_out(require_entity(db, ExtractedFact, fact_id, user, name="Fact"))
