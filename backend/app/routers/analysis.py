from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user, require_entity, require_project
from ..models import (
    Contradiction, ImpactReport, Project, Requirement, RequirementValidation, Task, TimelineEvent, User, utcnow,
)
from ..schemas import (
    CompileIn, CompileOut, ContradictionOut, GraphOut, ImpactIn, ImpactReportOut, RequirementIn,
    RequirementOut, RequirementPatch, ResolveIn, ReviewIn, TaskIn, TaskOut, TaskPatch, TimelineOut,
    ValidationOut, VerifyIn,
)
from ..services import autopilot, contradictions, graph, impact, requirements, rules, tasks, verification
from ..services.common import log_activity, next_code
from ..services.textutil import subject_key
from .serializers import contradiction_out, requirement_out, task_out

router = APIRouter(tags=["analysis"])


def _refresh_tasks(db: Session, project_id: int) -> int:
    created = tasks.generate_suggestions(db, project_id)
    autopilot.approve_tasks(db, db.get(Project, project_id))
    return created


# ---- contradictions
@router.get("/projects/{project_id}/contradictions", response_model=list[ContradictionOut])
def list_contradictions(project_id: int, status: str | None = None, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    q = select(Contradiction).where(Contradiction.project_id == project_id).order_by(Contradiction.id)
    if status:
        q = q.where(Contradiction.status == status)
    return [contradiction_out(db, c) for c in db.scalars(q)]


@router.post("/projects/{project_id}/contradictions/detect")
def detect_contradictions(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = require_project(db, project_id, user, write=True)
    result = contradictions.detect(db, project_id, user.id)
    decided = autopilot.resolve_open(db, project)
    graph.sync(db, project_id)
    autopilot.ripple(db, project, decided)
    _refresh_tasks(db, project_id)
    result["resolved_by_autopilot"] = len(decided)
    return result


@router.patch("/contradictions/{contradiction_id}/resolve", response_model=ContradictionOut)
def resolve_contradiction(contradiction_id: int, body: ResolveIn, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    c = require_entity(db, Contradiction, contradiction_id, user, write=True, name="Contradiction")
    try:
        contradictions.resolve(db, c, user, body.status, body.authoritative_fact_id, body.superseded_fact_ids, body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _refresh_tasks(db, c.project_id)
    return contradiction_out(db, c)


# ---- requirements
@router.post("/projects/{project_id}/requirements/compile", response_model=CompileOut)
def compile_requirements(project_id: int, body: CompileIn, user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    require_project(db, project_id, user, write=True)
    if body.source == "text":
        if not body.text or not body.text.strip():
            raise HTTPException(400, "Enter the instructions to compile.")
        res = requirements.compile_from_text(db, project_id, body.text, user.id)
    else:
        res = requirements.compile_from_documents(db, project_id, user.id)
    return CompileOut(created=[requirement_out(db, r) for r in res["created"]],
                      skipped_duplicates=res["skipped_duplicates"])


@router.get("/projects/{project_id}/requirements", response_model=list[RequirementOut])
def list_requirements(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    rows = db.scalars(select(Requirement).where(Requirement.project_id == project_id).order_by(Requirement.id))
    return [requirement_out(db, r) for r in rows]


@router.post("/projects/{project_id}/requirements", response_model=RequirementOut, status_code=201)
def create_requirement(project_id: int, body: RequirementIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    require_project(db, project_id, user, write=True)
    if body.verification_method == "numeric" and not body.expected_value:
        raise HTTPException(400, "Numeric requirements need an expected value.")
    r = Requirement(
        project_id=project_id, code=next_code(db, Requirement, project_id, "REQ"), title=body.title.strip(),
        description=body.description.strip(), category=body.category, priority=body.priority, source_type="manual",
        subject_key=subject_key(body.title), expected_value=body.expected_value,
        verification_method=body.verification_method,
        keywords=[k.strip() for k in body.keywords if k.strip()] if body.keywords else rules.keywords_for(body.title),
        user_edited=True)
    db.add(r)
    db.flush()
    log_activity(db, project_id, user.id, "requirement.created", f"{r.code} {r.title} added", "requirement", r.id)
    db.commit()
    return requirement_out(db, r)


@router.patch("/requirements/{requirement_id}", response_model=RequirementOut)
def patch_requirement(requirement_id: int, body: RequirementPatch, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    r = require_entity(db, Requirement, requirement_id, user, write=True, name="Requirement")
    data = body.model_dump(exclude_unset=True)
    if "keywords" in data and data["keywords"] is not None:
        data["keywords"] = [k.strip() for k in data["keywords"] if k.strip()][:10]
    for k, v in data.items():
        setattr(r, k, v)
    if (r.verification_method == "numeric") and not r.expected_value:
        raise HTTPException(400, "Numeric requirements need an expected value.")
    if data:
        r.user_edited = True
        if r.blocked_by_contradiction_id and "expected_value" in data and data["expected_value"]:
            r.blocked_by_contradiction_id = None
        r.status = "not_checked"  # a changed requirement must be re-verified
        db.query(RequirementValidation).filter(RequirementValidation.requirement_id == r.id).update({"is_latest": False})
    log_activity(db, r.project_id, user.id, "requirement.updated", f"{r.code} updated", "requirement", r.id)
    db.commit()
    _refresh_tasks(db, r.project_id)
    return requirement_out(db, r)


@router.delete("/requirements/{requirement_id}", status_code=204)
def delete_requirement(requirement_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = require_entity(db, Requirement, requirement_id, user, write=True, name="Requirement")
    pid = r.project_id
    log_activity(db, pid, user.id, "requirement.deleted", f"{r.code} {r.title} deleted")
    db.delete(r)
    db.commit()
    _refresh_tasks(db, pid)
    return Response(status_code=204)


@router.post("/requirements/{requirement_id}/review", response_model=RequirementOut)
def review_requirement(requirement_id: int, body: ReviewIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    r = require_entity(db, Requirement, requirement_id, user, write=True, name="Requirement")
    verification.manual_review(db, r, user.id, body.status, body.note.strip())
    _refresh_tasks(db, r.project_id)
    return requirement_out(db, r)


# ---- verification
@router.post("/projects/{project_id}/verify")
def verify(project_id: int, body: VerifyIn | None = None, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    require_project(db, project_id, user, write=True)
    try:
        result = verification.run(db, project_id, user.id, body.requirement_ids if body else None)
    except verification.VerificationError as exc:
        raise HTTPException(400, str(exc)) from exc
    autopilot.approve_tasks(db, db.get(Project, project_id))
    return result


@router.get("/projects/{project_id}/verification-results", response_model=list[ValidationOut])
def verification_results(project_id: int, latest_only: bool = True, user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    q = select(RequirementValidation).where(RequirementValidation.project_id == project_id).order_by(
        RequirementValidation.id.desc())
    if latest_only:
        q = q.where(RequirementValidation.is_latest.is_(True))
    return db.scalars(q.limit(500)).all()


# ---- graph & impact
@router.get("/projects/{project_id}/graph", response_model=GraphOut)
def get_graph(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    nodes, edges = graph.sync(db, project_id)
    return GraphOut(nodes=nodes, edges=edges)


@router.post("/projects/{project_id}/impact-analysis", response_model=ImpactReportOut, status_code=201)
def impact_analysis(project_id: int, body: ImpactIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    require_project(db, project_id, user, write=True)
    try:
        return impact.analyze(db, project_id, body.target_type, body.target_id, body.new_value, user.id,
                              source_of_change=body.source_of_change)
    except impact.ImpactError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/projects/{project_id}/impact-reports", response_model=list[ImpactReportOut])
def list_impact_reports(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    return db.scalars(select(ImpactReport).where(ImpactReport.project_id == project_id)
                      .order_by(ImpactReport.id.desc()).limit(30)).all()


@router.get("/impact-reports/{report_id}", response_model=ImpactReportOut)
def get_impact_report(report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return require_entity(db, ImpactReport, report_id, user, name="Impact report")


@router.post("/impact-reports/{report_id}/apply", response_model=ImpactReportOut)
def apply_impact_report(report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    report = require_entity(db, ImpactReport, report_id, user, write=True, name="Impact report")
    try:
        impact.apply(db, report, user)
    except impact.ImpactError as exc:
        raise HTTPException(400, str(exc)) from exc
    autopilot.approve_tasks(db, db.get(Project, report.project_id))
    return report


@router.post("/impact-reports/{report_id}/discard", response_model=ImpactReportOut)
def discard_impact_report(report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    report = require_entity(db, ImpactReport, report_id, user, write=True, name="Impact report")
    if report.status != "draft":
        raise HTTPException(400, "Only draft reports can be discarded.")
    report.status = "discarded"
    db.commit()
    return report


# ---- tasks
@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(project_id: int, status: str | None = None, priority: str | None = None,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    q = select(Task).where(Task.project_id == project_id).order_by(Task.id.desc())
    if status:
        q = q.where(Task.status == status)
    if priority:
        q = q.where(Task.priority == priority)
    return [task_out(db, t) for t in db.scalars(q)]


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(project_id: int, body: TaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user, write=True)
    t = Task(project_id=project_id, title=body.title.strip(), description=body.description.strip(),
             reason="Created manually.", origin="manual", priority=body.priority, status="active",
             due_date=body.due_date)
    db.add(t)
    db.flush()
    log_activity(db, project_id, user.id, "task.created", f"Task “{t.title}” created", "task", t.id)
    db.commit()
    return task_out(db, t)


@router.post("/projects/{project_id}/tasks/suggest")
def suggest_tasks(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user, write=True)
    return {"created": _refresh_tasks(db, project_id)}


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def patch_task(task_id: int, body: TaskPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = require_entity(db, Task, task_id, user, write=True, name="Task")
    data = body.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    for k, v in data.items():
        if v is not None or k == "due_date":
            setattr(t, k, v)
    if new_status and new_status != t.status:
        t.completed_at = utcnow() if new_status == "completed" else None
        verb = {"active": "approved" if t.status == "suggested" else "reopened", "completed": "completed",
                "dismissed": "dismissed", "suggested": "moved back to suggestions"}[new_status]
        t.status = new_status
        log_activity(db, t.project_id, user.id, f"task.{new_status}", f"Task “{t.title}” {verb}", "task", t.id)
    db.commit()
    return task_out(db, t)


# ---- timeline
@router.get("/projects/{project_id}/timeline", response_model=list[TimelineOut])
def timeline(project_id: int, kind: str | None = None, include_info: bool = True,
             limit: int = Query(200, ge=1, le=500), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    q = select(TimelineEvent).where(TimelineEvent.project_id == project_id)
    if kind:
        q = q.where(TimelineEvent.kind == kind)
    if not include_info:
        q = q.where(TimelineEvent.kind != "info")
    return db.scalars(q.order_by(TimelineEvent.event_date.desc(), TimelineEvent.id.desc()).limit(limit)).all()
