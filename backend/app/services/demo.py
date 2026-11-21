"""Reproducible demo project. The sample files are generated here and then go through the exact same
upload → parse → extract → detect pipeline as user uploads. No results are precomputed."""
from __future__ import annotations

import io
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, Project, ProjectMember, User
from . import pipeline
from .common import log_activity

DEMO_NAME = "Mobile App Development Project"
DEMO_DESCRIPTION = ("Sample project data. Three sample documents with intentionally conflicting information, "
                    "processed by the real OxisTrack pipeline.")
DELIVERABLE_NAME = "Build Summary v0.9 (sample deliverable).md"


def _ctx() -> dict:
    today = date.today()
    year = today.year if (today.month, today.day) <= (12, 10) else today.year + 1
    fmt = lambda d: f"{d.strftime('%B')} {d.day}, {d.year}"  # noqa: E731
    return {"d1": fmt(today - timedelta(days=10)), "d2": fmt(today - timedelta(days=7)),
            "d3": fmt(today - timedelta(days=5)), "d4": fmt(today - timedelta(days=1)), "y": year}


PROPOSAL = [
    ("h", "Original Proposal for the Mobile App Development Project"),
    ("p", "Sample document for the OxisTrack demo."),
    ("p", "Date: {d1}"),
    ("p", "Prepared by: Priya Nair"),
    ("p", "Client: Northwind Outfitters"),
    ("h", "Summary"),
    ("p", "Goal: Give Northwind field staff a single mobile app for planning and logging store visits."),
    ("p", "Project deadline: December 20, {y}"),
    ("p", "Budget: $48,000"),
    ("p", "Platform: iOS and Android"),
    ("h", "Scope"),
    ("p", "The application requires three user roles."),
    ("p", "The application must include a dashboard."),
    ("p", "The application must support search."),
    ("p", "The application must include a permissions matrix for every user role."),
]
NOTES = """# Sprint Planning Meeting Notes

*Sample document for the OxisTrack demo.*

Date: {d2}
Attendees: Priya Nair, Marcus Lee, Sofia Alvarez

## Discussion

- Project deadline: December 22, {y}
- The application requires three user roles.
- Dashboard design needs revision.
- Decision: The team agreed to keep search in the first release.
- The team must prepare a QA test plan for each user role.
- Budget: $48,000
"""
UPDATED = [
    "Updated Requirements for the Mobile App Development Project",
    "Sample document for the OxisTrack demo.",
    "Date: {d3}",
    "Prepared by: Marcus Lee",
    "",
    "Updated project deadline: December 18, {y}",
    "Budget: $52,500",
    "",
    "The application requires five user roles.",
    "The application must include a dashboard.",
    "The application must support search.",
    "The application must include notifications.",
    "Notifications depend on the user roles model.",
]
DELIVERABLE = """# Build Summary for Release Candidate 0.9

*Sample deliverable for the OxisTrack demo. It intentionally misses some requirements.*

Date: {d4}

## What is in this build

- The dashboard is implemented and shows upcoming store visits.
- Search is implemented across stores, visits and contacts.
- The build ships with 3 user roles: admin, manager and field agent.
- A permissions matrix is documented for each user role.

## Known gaps

- Push notifications are not implemented yet and are deferred to the next release.
"""


def _docx(lines: list[tuple[str, str]], ctx: dict) -> bytes:
    import docx

    d = docx.Document()
    for kind, text in lines:
        if kind == "h":
            d.add_heading(text.format(**ctx), level=1)
        else:
            d.add_paragraph(text.format(**ctx))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _pdf(lines: list[str], ctx: dict) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for i, line in enumerate(lines):
        if line:
            page.insert_text((72, y), line.format(**ctx), fontsize=16 if i == 0 else 11)
        y += 30 if i == 0 else 20
    data = doc.tobytes()
    doc.close()
    return data


def sample_files() -> dict[str, bytes]:
    ctx = _ctx()
    return {
        "Original Proposal (sample).docx": _docx(PROPOSAL, ctx),
        "Meeting Notes (sample).md": NOTES.format(**ctx).encode(),
        "Updated Requirements (sample).pdf": _pdf(UPDATED, ctx),
        DELIVERABLE_NAME: DELIVERABLE.format(**ctx).encode(),
    }


def find_demo(db: Session, user: User) -> Project | None:
    return db.scalar(select(Project).where(Project.owner_id == user.id, Project.is_demo.is_(True)))


def load(db: Session, user: User, autopilot: bool = True) -> Project:
    existing = find_demo(db, user)
    if existing:
        return existing
    project = Project(name=DEMO_NAME, description=DEMO_DESCRIPTION, owner_id=user.id, is_demo=True, autopilot=autopilot)
    project.members.append(ProjectMember(user_id=user.id, role="owner"))
    db.add(project)
    db.commit()
    log_activity(db, project.id, user.id, "project.created", "Sample project loaded")
    for name, data in sample_files().items():
        if name == DELIVERABLE_NAME:
            continue
        doc, _ = pipeline.store_upload(db, project, user.id, name, data, "source", is_sample=True)
        pipeline.analyze_document(db, doc.id, user.id)
    return project


def add_sample_deliverable(db: Session, project: Project, user: User) -> Document:
    doc, _ = pipeline.store_upload(db, project, user.id, DELIVERABLE_NAME, sample_files()[DELIVERABLE_NAME],
                                   "deliverable", is_sample=True)
    pipeline.analyze_document(db, doc.id, user.id)
    return doc


def delete_project_files(db: Session, project: Project) -> None:
    for doc in db.scalars(select(Document).where(Document.project_id == project.id)).all():
        pipeline.delete_document(db, doc, None)


def reset(db: Session, user: User, autopilot: bool = True) -> Project:
    existing = find_demo(db, user)
    if existing:
        delete_project_files(db, existing)
        db.delete(existing)
        db.commit()
    return load(db, user, autopilot)
