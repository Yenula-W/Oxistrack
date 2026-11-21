"""Project-aware keyword search and a small evidence-citing assistant."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Contradiction, Decision, Document, ExtractedFact, Requirement, Task
from .ai import get_provider
from .contradictions import META_SUBJECT_KEYS
from .rules import SYNONYMS
from .textutil import STOPWORDS, stems, tokens

_QUESTION_WORDS = {"what", "which", "who", "when", "where", "why", "how", "many", "much", "is", "the", "does",
                   "do", "are", "current", "confirm", "confirms", "document", "documents", "tell", "me", "about"}


def _terms(query: str) -> list[str]:
    toks = [t for t in tokens(query) if t not in STOPWORDS and t not in _QUESTION_WORDS and len(t) > 1]
    return list(dict.fromkeys(toks or tokens(query)))[:8]


def _like_any(cols, terms):
    return or_(*[c.ilike(f"%{t}%") for c in cols for t in terms])


def _score(text: str, terms: list[str]) -> int:
    low = text.lower()
    return sum(2 if f" {t}" in f" {low}" else 1 for t in terms if t in low)


def search(db: Session, project_id: int, query: str, limit: int = 8) -> dict:
    terms = _terms(query)
    out = {"query": query, "documents": [], "facts": [], "requirements": [], "contradictions": [],
           "decisions": [], "tasks": []}
    if not terms:
        return out
    like_terms = list(dict.fromkeys(terms + [s[:-1] if s.endswith("y") else s for s in stems(" ".join(terms))]))

    def top(rows, text_of):
        scored = sorted(((_score(text_of(r), like_terms), r) for r in rows), key=lambda x: -x[0])
        return [r for s, r in scored if s > 0][:limit]

    docs = db.scalars(select(Document).where(Document.project_id == project_id,
                                             _like_any([Document.filename], like_terms)).limit(50)).all()
    out["documents"] = [{"id": d.id, "title": d.filename, "subtitle": f"{d.kind} · {d.file_type.upper()}"}
                        for d in top(docs, lambda d: d.filename)]
    facts = db.scalars(select(ExtractedFact).where(
        ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True),
        _like_any([ExtractedFact.text, ExtractedFact.subject], like_terms)).limit(200)).all()
    out["facts"] = [{"id": f.id, "title": f.text, "document_id": f.document_id,
                     "subtitle": f"{f.category.replace('_', ' ')} · {f.document.filename}" + (f" · {f.location}" if f.location else "")}
                    for f in top(facts, lambda f: f"{f.text} {f.subject}")]
    reqs = db.scalars(select(Requirement).where(
        Requirement.project_id == project_id,
        _like_any([Requirement.title, Requirement.description, Requirement.code], like_terms)).limit(100)).all()
    out["requirements"] = [{"id": r.id, "title": f"{r.code} {r.title}", "subtitle": r.status.replace("_", " ")}
                           for r in top(reqs, lambda r: f"{r.code} {r.title} {r.description}")]
    cons = db.scalars(select(Contradiction).where(
        Contradiction.project_id == project_id,
        _like_any([Contradiction.title, Contradiction.explanation, Contradiction.code], like_terms)).limit(100)).all()
    out["contradictions"] = [{"id": c.id, "title": f"{c.code} {c.title}", "subtitle": c.status.replace("_", " ")}
                             for c in top(cons, lambda c: f"{c.code} {c.title} {c.explanation}")]
    decs = db.scalars(select(Decision).where(
        Decision.project_id == project_id, _like_any([Decision.title, Decision.description], like_terms)).limit(100)).all()
    out["decisions"] = [{"id": d.id, "title": d.title, "subtitle": d.description[:120]}
                        for d in top(decs, lambda d: f"{d.title} {d.description}")]
    tks = db.scalars(select(Task).where(
        Task.project_id == project_id, Task.status != "dismissed",
        _like_any([Task.title, Task.description], like_terms)).limit(100)).all()
    out["tasks"] = [{"id": t.id, "title": t.title, "subtitle": t.status} for t in top(tks, lambda t: f"{t.title} {t.description}")]
    return out


def ask(db: Session, project_id: int, question: str) -> dict:
    """Answer from extracted facts only. Each answer lists the statements it is based on."""
    terms = _terms(question)
    q_stems = set(stems(" ".join(terms), drop_stop=False))
    for st in list(q_stems):
        for alt in SYNONYMS.get(st, []):
            q_stems |= set(stems(alt, drop_stop=False))
    facts = db.scalars(select(ExtractedFact).join(Document, Document.id == ExtractedFact.document_id).where(
        ExtractedFact.project_id == project_id, ExtractedFact.is_current.is_(True), Document.kind == "source")).all()
    scored = []
    for f in facts:
        overlap = len(q_stems & set(stems(f"{f.subject} {f.text}", drop_stop=False)))
        subj_hit = len(q_stems & set(f.subject_key.split())) if f.subject_key not in META_SUBJECT_KEYS else 0
        if overlap:
            scored.append((overlap + 2 * subj_hit + (0.5 if f.value_norm else 0), f))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    top = [f for _, f in scored[:10]]

    def cite(f: ExtractedFact) -> dict:
        return {"fact_id": f.id, "document_id": f.document_id, "document_name": f.document.filename,
                "location": f.location, "text": f.text}

    if not top:
        return {"mode": "none", "answer": "Nothing in this project's documents addresses that question.",
                "citations": [], "uncertainty": "No matching extracted facts were found.", "interpretation": None}

    subject = top[0].subject_key
    same = [f for f in top if subject and f.subject_key == subject and f.value_norm]
    con = db.scalar(select(Contradiction).where(
        Contradiction.project_id == project_id, Contradiction.subject_key == subject)
        .order_by(Contradiction.id.desc())) if subject else None

    provider = get_provider()
    if provider.uses_llm:
        payload = [{"id": f.id, "document": f.document.filename, "location": f.location, "statement": f.text,
                    "document_date": str(f.document.document_date or "")} for f in top]
        if con:
            payload.append({"id": 0, "note": f"Contradiction {con.code} status={con.status}; "
                            f"authoritative_fact_id={con.authoritative_fact_id}; note={con.resolution_note}"})
        res = provider.answer(question, payload)
        if res:
            ids = {f.id: f for f in top}
            cites = [cite(ids[i]) for i in res.cited_fact_ids if i in ids]
            if cites:
                return {"mode": "llm", "answer": res.answer, "citations": cites, "uncertainty": res.uncertainty,
                        "interpretation": "Generated by the AI assistant from the cited statements."}

    label = (top[0].subject or "this topic").lower()
    uncertainty, interpretation = "", None
    if con and con.status == "resolved" and con.authoritative_fact_id:
        auth = next((s for s in con.sources if s.role == "authoritative"), None)
        answer = (f"Confirmed {label}: {auth.value_text}, according to {auth.document_name}"
                  f"{f' ({auth.location})' if auth.location else ''}. This was confirmed when {con.code} was resolved"
                  f"{f' by {con.resolver.name}' if con.resolver else ''}.") if auth else con.title
        old = [s for s in con.sources if s.role == "superseded"]
        if old:
            answer += " Superseded: " + ", ".join(f"{s.value_text} ({s.document_name})" for s in old) + "."
        cites = [cite(f) for f in same] or [cite(top[0])]
    elif con and con.status in ("open", "under_review"):
        answer = (f"The sources disagree about the {label}: " +
                  "; ".join(f"{s.value_text} in {s.document_name}" for s in con.sources) +
                  f". No authoritative source has been chosen yet ({con.code} is {con.status.replace('_', ' ')}).")
        uncertainty = "Unresolved contradiction: OxisTrack does not assume the newest document is correct."
        cites = [cite(f) for f in same] or [cite(top[0])]
    elif same and len({f.value_norm for f in same}) == 1:
        f = same[0]
        answer = (f"The {label} is {f.value_text}, as stated in {f.document.filename}"
                  f"{f' ({f.location})' if f.location else ''}.")
        if len(same) > 1:
            answer += f" {len(same)} statements agree on this value."
        cites = [cite(x) for x in same]
    else:
        best = top[:3]
        answer = "The most relevant statements found: " + " ".join(f"“{f.text}” ({f.document.filename})" for f in best)
        uncertainty = "These are the closest matching statements; they may not fully answer the question."
        interpretation = "No single extracted value answers this directly, so related statements are shown."
        cites = [cite(f) for f in best]
    return {"mode": "rules", "answer": answer, "citations": cites, "uncertainty": uncertainty,
            "interpretation": interpretation}
