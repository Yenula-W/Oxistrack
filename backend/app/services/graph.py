"""Knowledge graph: nodes and edges are rebuilt from the project's stored records."""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Contradiction, Decision, Document, ExtractedFact, GraphEdge, GraphNode, Requirement,
    RequirementValidation, Task, ValidationEvidence,
)
from .contradictions import META_SUBJECT_KEYS
from .textutil import humanize, stems


def _short(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def sync(db: Session, project_id: int) -> tuple[list[GraphNode], list[GraphEdge]]:
    db.execute(delete(GraphEdge).where(GraphEdge.project_id == project_id))
    db.execute(delete(GraphNode).where(GraphNode.project_id == project_id))
    nodes: dict[tuple[str, str], GraphNode] = {}
    edges: set[tuple[tuple[str, str], tuple[str, str], str]] = set()

    def node(ntype: str, ref, label: str, detail: str = "", status: str | None = None) -> tuple[str, str]:
        key = (ntype, str(ref))
        if key not in nodes:
            nodes[key] = GraphNode(project_id=project_id, node_type=ntype, ref_key=str(ref)[:200],
                                   label=_short(label, 80), detail=detail, status=status)
        return key

    docs = db.scalars(select(Document).where(Document.project_id == project_id)).all()
    doc_keys = {}
    for d in docs:
        ntype = "deliverable" if d.kind == "deliverable" else "document"
        doc_keys[d.id] = node(ntype, d.id, d.filename, f"{d.file_type.upper()} · version {d.current_version}", d.status)

    facts = [f for f in db.scalars(select(ExtractedFact).where(
        ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True)).order_by(ExtractedFact.id))
        if f.subject_key not in META_SUBJECT_KEYS and f.category != "entity"]
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()

    subjects: dict[str, Counter] = defaultdict(Counter)
    for f in facts:
        if f.subject_key:
            subjects[f.subject_key][f.subject.strip().lower()] += 1
    for r in reqs:
        if r.subject_key and r.subject_key not in subjects:
            subjects[r.subject_key][r.title.lower()] += 1
    topic_keys = {k: node("topic", k, humanize(c.most_common(1)[0][0]), "Topic shared by related statements")
                  for k, c in subjects.items()}
    topic_tokens = {k: set(k.split()) for k in topic_keys}

    def link_references(src: tuple[str, str], text: str, own: str) -> None:
        st = set(stems(text, drop_stop=False))
        for k, toks in topic_tokens.items():
            if k != own and toks and toks <= st:
                edges.add((src, topic_keys[k], "references"))

    fact_keys = {}
    for f in facts:
        fk = node("fact", f.id, f.text, f"{f.category.replace('_', ' ')} · {f.location or 'location unknown'}",
                  f.category)
        fact_keys[f.id] = fk
        if f.document_id in doc_keys:
            edges.add((doc_keys[f.document_id], fk, "contains"))
        if f.subject_key in topic_keys:
            edges.add((fk, topic_keys[f.subject_key], "about"))
        link_references(fk, f.text, f.subject_key)

    req_keys = {}
    for r in reqs:
        rk = node("requirement", r.id, f"{r.code} {r.title}", r.description, r.status)
        req_keys[r.id] = rk
        if r.subject_key in topic_keys:
            edges.add((rk, topic_keys[r.subject_key], "concerns"))
        if r.source_fact_id in fact_keys:
            edges.add((rk, fact_keys[r.source_fact_id], "derived_from"))
        link_references(rk, f"{r.title} {r.description}", r.subject_key)

    con_keys = {}
    for c in db.scalars(select(Contradiction).where(Contradiction.project_id == project_id)):
        ck = node("contradiction", c.id, f"{c.code} {c.title.split(':')[0]}", c.title, c.status)
        con_keys[c.id] = ck
        if c.subject_key in topic_keys:
            edges.add((ck, topic_keys[c.subject_key], "disputes"))
        for s in c.sources:
            if s.fact_id in fact_keys:
                edges.add((ck, fact_keys[s.fact_id], "involves"))

    for d in db.scalars(select(Decision).where(Decision.project_id == project_id)):
        dk = node("decision", d.id, d.title, d.description, "decided")
        if d.contradiction_id in con_keys:
            edges.add((dk, con_keys[d.contradiction_id], "resolves"))
        if d.fact_id in fact_keys:
            edges.add((dk, fact_keys[d.fact_id], "confirms"))
        elif d.subject_key in topic_keys:
            edges.add((dk, topic_keys[d.subject_key], "confirms"))

    for t in db.scalars(select(Task).where(Task.project_id == project_id, Task.status.in_(("active", "completed")))):
        tk = node("task", t.id, t.title, t.description, t.status)
        if t.related_contradiction_id in con_keys:
            edges.add((tk, con_keys[t.related_contradiction_id], "addresses"))
        if t.related_requirement_id in req_keys:
            edges.add((tk, req_keys[t.related_requirement_id], "addresses"))
        if t.related_document_id in doc_keys and not (t.related_contradiction_id or t.related_requirement_id):
            edges.add((tk, doc_keys[t.related_document_id], "addresses"))

    deliverables = [d for d in docs if d.kind == "deliverable"]
    vals = db.scalars(select(RequirementValidation).where(
        RequirementValidation.project_id == project_id, RequirementValidation.is_latest.is_(True))).all()
    for v in vals:
        if v.requirement_id not in req_keys or v.reviewed_by:
            continue
        ev_docs = set(db.scalars(select(ValidationEvidence.document_id).where(
            ValidationEvidence.validation_id == v.id, ValidationEvidence.document_id.is_not(None))))
        rel = {"passed": "satisfies", "failed": "fails", "needs_review": "unclear_for"}.get(v.status, "checked")
        for d in deliverables:
            if d.status == "analyzed" and (d.id in ev_docs or not ev_docs):
                edges.add((doc_keys[d.id], req_keys[v.requirement_id], rel))

    db.add_all(nodes.values())
    db.flush()
    edge_rows = [GraphEdge(project_id=project_id, source_id=nodes[s].id, target_id=nodes[t].id, relation=rel)
                 for s, t, rel in sorted(edges)]
    db.add_all(edge_rows)
    db.commit()
    return list(nodes.values()), edge_rows
