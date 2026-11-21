from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Project, ProjectMember, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    user_id = decode_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "Not authenticated.", headers={"WWW-Authenticate": "Bearer"})
    return user


def membership(db: Session, project_id: int, user: User) -> ProjectMember | None:
    return db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == user.id))


def require_project(db: Session, project_id: int, user: User, write: bool = False) -> Project:
    """Project-level access control. Non-members get 404 so project ids cannot be probed."""
    project = db.get(Project, project_id)
    member = membership(db, project_id, user) if project else None
    if project is None or member is None:
        raise HTTPException(404, "Project not found.")
    if write and member.role == "viewer":
        raise HTTPException(403, "Viewers cannot change this project.")
    return project


def require_entity(db: Session, model, entity_id: int, user: User, write: bool = False, name: str = "Item"):
    obj = db.get(model, entity_id)
    if obj is None:
        raise HTTPException(404, f"{name} not found.")
    try:
        require_project(db, obj.project_id, user, write)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(404, f"{name} not found.") from exc
        raise
    return obj
