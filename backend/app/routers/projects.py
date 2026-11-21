from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import current_user, membership, require_project
from ..models import ActivityLog, Project, ProjectMember, User
from ..schemas import (
    ActivityOut, AskIn, ContradictionOut, DocumentOut, MemberIn, MemberOut, ProjectIn, ProjectOut,
    ProjectPatch, TaskOut, TimelineOut,
)
from ..services import dashboard, demo, search
from ..services.ai import get_provider, get_reviewer
from ..services.common import log_activity
from .serializers import contradiction_out, document_out, task_out

router = APIRouter(tags=["projects"])


def _out(p: Project, role: str | None) -> ProjectOut:
    o = ProjectOut.model_validate(p)
    o.role = role
    return o


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Project, ProjectMember.role).join(
        ProjectMember, ProjectMember.project_id == Project.id).where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())).all()
    return [_out(p, role) for p, role in rows]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(name=body.name.strip(), description=body.description.strip(), owner_id=user.id, autopilot=body.autopilot)
    p.members.append(ProjectMember(user_id=user.id, role="owner"))
    db.add(p)
    db.flush()
    log_activity(db, p.id, user.id, "project.created", f"Project “{p.name}” created", "project", p.id)
    db.commit()
    return _out(p, "owner")


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = require_project(db, project_id, user)
    return _out(p, membership(db, project_id, user).role)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def patch_project(project_id: int, body: ProjectPatch, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    p = require_project(db, project_id, user, write=True)
    if body.name is not None:
        p.name = body.name.strip()
    if body.description is not None:
        p.description = body.description.strip()
    if body.autopilot is not None and body.autopilot != p.autopilot:
        p.autopilot = body.autopilot
        log_activity(db, p.id, user.id, "project.autopilot", f"Autopilot turned {'on' if p.autopilot else 'off'}")
        db.commit()
        if p.autopilot:  # catch up on anything that was waiting for a decision
            from ..services import autopilot, graph, tasks

            decided = autopilot.resolve_open(db, p)
            graph.sync(db, p.id)
            autopilot.ripple(db, p, decided)
            tasks.generate_suggestions(db, p.id)
            autopilot.approve_tasks(db, p)
    db.commit()
    return _out(p, membership(db, project_id, user).role)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = require_project(db, project_id, user, write=True)
    if p.owner_id != user.id:
        raise HTTPException(403, "Only the project owner can delete a project.")
    demo.delete_project_files(db, p)
    db.delete(p)
    db.commit()
    return Response(status_code=204)


# ---- members
@router.get("/projects/{project_id}/members", response_model=list[MemberOut])
def list_members(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = require_project(db, project_id, user)
    return [MemberOut(id=m.id, user_id=m.user_id, name=m.user.name, email=m.user.email, role=m.role)
            for m in p.members]


@router.post("/projects/{project_id}/members", response_model=MemberOut, status_code=201)
def add_member(project_id: int, body: MemberIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = require_project(db, project_id, user, write=True)
    if p.owner_id != user.id:
        raise HTTPException(403, "Only the project owner can manage members.")
    target = db.scalar(select(User).where(User.email == body.email.lower()))
    if target is None:
        raise HTTPException(404, "No OxisTrack account uses that email. Ask them to register first.")
    if any(m.user_id == target.id for m in p.members):
        raise HTTPException(409, "That person is already a member of this project.")
    m = ProjectMember(project_id=p.id, user_id=target.id, role=body.role)
    db.add(m)
    log_activity(db, p.id, user.id, "member.added", f"{target.name} added as {body.role}")
    db.commit()
    return MemberOut(id=m.id, user_id=target.id, name=target.name, email=target.email, role=m.role)


@router.delete("/projects/{project_id}/members/{member_id}", status_code=204)
def remove_member(project_id: int, member_id: int, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    p = require_project(db, project_id, user, write=True)
    m = db.get(ProjectMember, member_id)
    if p.owner_id != user.id or m is None or m.project_id != p.id:
        raise HTTPException(403, "Only the project owner can manage members.")
    if m.user_id == p.owner_id:
        raise HTTPException(400, "The project owner cannot be removed.")
    db.delete(m)
    db.commit()
    return Response(status_code=204)


# ---- overview, activity, search
@router.get("/projects/{project_id}/overview")
def overview(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = require_project(db, project_id, user)
    data = dashboard.overview(db, project_id)
    data["recent_contradictions"] = [contradiction_out(db, c) for c in data["recent_contradictions"]]
    data["recent_changes"] = [TimelineOut.model_validate(e) for e in data["recent_changes"]]
    data["suggested_tasks"] = [task_out(db, t) for t in data["suggested_tasks"]]
    data["recent_activity"] = [ActivityOut.model_validate(a) for a in data["recent_activity"]]
    data["project"] = _out(p, membership(db, project_id, user).role)
    return data


@router.get("/projects/{project_id}/activity", response_model=list[ActivityOut])
def activity(project_id: int, limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    return db.scalars(select(ActivityLog).where(ActivityLog.project_id == project_id)
                      .order_by(ActivityLog.id.desc()).limit(limit)).all()


@router.get("/projects/{project_id}/search")
def search_project(project_id: int, q: str = Query(min_length=1, max_length=200),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    return search.search(db, project_id, q)


@router.post("/projects/{project_id}/ask")
def ask_project(project_id: int, body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_project(db, project_id, user)
    return search.ask(db, project_id, body.question)


# ---- demo + system
@router.post("/demo/load", response_model=ProjectOut)
def demo_load(autopilot: bool = True, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(demo.load(db, user, autopilot), "owner")


@router.post("/demo/reset", response_model=ProjectOut)
def demo_reset(autopilot: bool = True, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(demo.reset(db, user, autopilot), "owner")


@router.post("/projects/{project_id}/demo/sample-deliverable", response_model=DocumentOut)
def demo_deliverable(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = require_project(db, project_id, user, write=True)
    return document_out(db, demo.add_sample_deliverable(db, p, user))


@router.get("/demo/samples")
def demo_samples(user: User = Depends(current_user)):
    return [{"filename": name, "size_bytes": len(data), "kind": "deliverable" if name == demo.DELIVERABLE_NAME else "source"}
            for name, data in demo.sample_files().items()]


@router.get("/demo/samples/{filename}")
def demo_sample_file(filename: str, user: User = Depends(current_user)):
    files = demo.sample_files()
    if filename not in files:
        raise HTTPException(404, "Sample file not found.")
    return Response(files[filename], media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/system/status")
def system_status(user: User = Depends(current_user)):
    s = get_settings()
    provider = get_provider()
    reviewer = get_reviewer()
    return {
        "reviewer_model": reviewer.model if reviewer else None,
        "ai_provider": provider.name, "ai_label": provider.label, "uses_llm": provider.uses_llm,
        "llm_model": s.llm_model if provider.uses_llm else None,
        "database": s.database_url.split(":", 1)[0].split("+")[0],
        "max_upload_mb": s.max_upload_mb, "allowed_types": ["pdf", "docx", "txt", "csv", "xlsx", "md"],
    }
