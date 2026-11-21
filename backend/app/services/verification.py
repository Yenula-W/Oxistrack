"""Requirement verification against uploaded deliverables.

Checks are evidence-first: a requirement only passes when concrete, citable evidence is found by a
deterministic check (or an LLM verdict whose quote is verified verbatim against the deliverable).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Document, Project, Requirement, RequirementValidation, ValidationEvidence
from . import tasks
from .ai import get_provider, get_reviewer
from .common import add_event, log_activity
from .rules import KV_RE, find_quantities
from .textutil import NUM_RE, fmt_number, normalize_ws, parse_number, stems

NEG_RE = re.compile(
    r"\b(not|no|never|without|missing|lacks?|lacking|excluded?|omitted|deferred|postponed|out of scope|todo|"
    r"tbd|unimplemented|removed|dropped|incomplete|n/a|won't|isn't|aren't|wasn't|doesn't|hasn't)\b", re.I)
MAX_EVIDENCE = 4


class VerificationError(Exception):
    pass


@dataclass
class Seg:
    doc: Document
    index: int
    location: str | None
    text: str
    low: str = ""
    stemset: set = field(default_factory=set)

    def __post_init__(self):
        self.low = self.text.lower().replace("-", " ")
        self.stemset = set(stems(self.text, drop_stop=False))


@dataclass
class Result:
    status: str
    checked: str
    explanation: str
    evidence: list[tuple[Seg | None, str, str]] = field(default_factory=list)  # (seg, snippet, polarity)


def _matches(seg: Seg, keywords: list[str]) -> bool:
    for i, kw in enumerate(keywords):
        k = kw.lower().replace("-", " ").strip()
        if not k:
            continue
        ks = stems(k)
        if " " not in k:
            if ks and ks[0] in seg.stemset:
                return True
        elif k in seg.low or (i == 0 and ks and all(s in seg.stemset for s in ks)):
            return True
    return False


def _keywords(req: Requirement) -> list[str]:
    return [k for k in (req.keywords or []) if isinstance(k, str) and k.strip()] or [req.title]


def _check_keyword(req: Requirement, segs: list[Seg]) -> Result:
    kws = _keywords(req)
    hits = [s for s in segs if _matches(s, kws)]
    pos = [s for s in hits if not NEG_RE.search(s.text)]
    neg = [s for s in hits if NEG_RE.search(s.text)]
    checked = "Searched the deliverable for: " + ", ".join(f"“{k}”" for k in kws[:6]) + "."
    ev = [(s, s.text, "supports") for s in pos[:MAX_EVIDENCE]] + [(s, s.text, "contradicts") for s in neg[:MAX_EVIDENCE]]
    if pos and not neg:
        return Result("passed", checked, f"Found {len(pos)} statement(s) in the deliverable that reference this "
                      "requirement, with no statement saying it is absent.", ev)
    if neg and not pos:
        return Result("failed", checked, "The deliverable mentions this requirement only to say it is missing, "
                      "deferred or not implemented.", ev)
    if pos and neg:
        return Result("needs_review", checked, "The deliverable contains both supporting statements and "
                      "statements suggesting this is missing or incomplete. A person should review the evidence.", ev)
    return Result("failed", checked, "No statement in the deliverable references this requirement.", [])


def _numbers_in(seg: Seg, subj: set[str]) -> list[float]:
    found = [n for n, phrase, _ in find_quantities(seg.text) if subj & set(stems(phrase, drop_stop=False))]
    kv = KV_RE.match(seg.text)
    if kv and subj <= set(stems(kv.group(1), drop_stop=False)):
        m = re.match(rf"\s*({NUM_RE})\b", kv.group(2), re.I)
        if m and (n := parse_number(m.group(1))) is not None:
            found.append(n)
    return found


def _check_numeric(req: Requirement, segs: list[Seg]) -> Result:
    kws = _keywords(req)
    subj = set(stems(kws[0])) or set(stems(req.title))
    expected = parse_number(req.expected_value or "")
    if expected is None:
        return Result("needs_review", "No expected value is set for this numeric requirement.",
                      "Set the expected value (or resolve the conflicting sources) before this can be checked.")
    checked = f"Looked for a count of “{kws[0]}” in the deliverable and compared it with the expected value {fmt_number(expected)}."
    match, differ, mention = [], [], []
    for s in segs:
        if not (subj <= s.stemset or _matches(s, kws[:1])):
            continue
        nums = _numbers_in(s, subj)
        if not nums:
            mention.append(s)
        elif expected in nums:
            match.append(s)
        else:
            differ.append((s, nums[0]))
    ev = [(s, s.text, "supports") for s in match[:MAX_EVIDENCE]] + \
         [(s, s.text, "contradicts") for s, _ in differ[:MAX_EVIDENCE]]
    if match and not differ:
        return Result("passed", checked, f"The deliverable states the expected value ({fmt_number(expected)}).", ev)
    if differ and not match:
        got = ", ".join(sorted({fmt_number(n) for _, n in differ}))
        return Result("failed", checked, f"Expected {fmt_number(expected)} but the deliverable states {got}.", ev)
    if match and differ:
        return Result("needs_review", checked, "The deliverable states the expected value in one place and a "
                      "different value in another.", ev)
    if mention:
        return Result("needs_review", checked, "The deliverable mentions this topic but never states a number, so "
                      "the count cannot be confirmed automatically.",
                      [(s, s.text, "neutral") for s in mention[:MAX_EVIDENCE]])
    return Result("failed", checked, "The deliverable does not mention this topic at all.", [])


def _check_file(req: Requirement, docs: list[Document]) -> Result:
    kws = _keywords(req)
    names = [d.filename for d in docs]
    wanted = [k.lower() for k in kws[:3]]
    hit = [n for n in names if any(w.replace(" ", "") in n.lower().replace(" ", "").replace("_", "") for w in wanted)]
    checked = f"Checked uploaded deliverable file names for: {', '.join(wanted)}."
    listing = "Uploaded deliverable files: " + ", ".join(names)
    if hit:
        return Result("passed", checked, f"Found matching file: {', '.join(hit)}.", [(None, listing, "supports")])
    return Result("failed", checked, "No uploaded deliverable file matches the expected name.",
                  [(None, listing, "contradicts")])


def _check_semantic(req: Requirement, segs: list[Seg]) -> Result:
    provider = get_provider()
    kw_stems = set(stems(" ".join(_keywords(req)) + " " + req.description))
    ranked = sorted(segs, key=lambda s: -len(kw_stems & s.stemset))[:14]
    related = [s for s in ranked if kw_stems & s.stemset]
    checked = "Compared the meaning of the requirement with the most relevant passages of the deliverable."
    if not provider.uses_llm:
        return Result("needs_review", checked, "Semantic checks need an LLM provider, which is not configured. "
                      "Related passages are listed for manual review; nothing was assumed.",
                      [(s, s.text, "neutral") for s in related[:MAX_EVIDENCE]])
    verdict = provider.judge(req.description, [(i, s.text) for i, s in enumerate(ranked)])
    if verdict is None:
        return Result("needs_review", checked, "The AI provider was unavailable, so this check could not be completed.",
                      [(s, s.text, "neutral") for s in related[:MAX_EVIDENCE]])
    seg = ranked[verdict.segment] if verdict.segment is not None and 0 <= verdict.segment < len(ranked) else None
    quote_ok = bool(seg and verdict.quote and normalize_ws(verdict.quote).lower() in normalize_ws(seg.text).lower())
    if verdict.verdict == "satisfied" and quote_ok:
        return Result("passed", checked, f"AI review (quote verified in the deliverable): {verdict.reasoning}",
                      [(seg, seg.text, "supports")])
    if verdict.verdict == "not_satisfied" and quote_ok:
        return Result("failed", checked, f"AI review (quote verified in the deliverable): {verdict.reasoning}",
                      [(seg, seg.text, "contradicts")])
    return Result("needs_review", checked, "The AI review was inconclusive or its citation could not be verified "
                  f"in the deliverable, so it was not accepted. {verdict.reasoning}".strip(),
                  [(s, s.text, "neutral") for s in related[:MAX_EVIDENCE]])


def _ai_review(req: Requirement, segs: list[Seg], first: Result) -> Result:
    """Two independent AI models re-read an unclear check. Their verdict is accepted only when both agree
    and each one quotes a passage that really is in the deliverable; otherwise it stays with a person."""
    analyst, reviewer = get_provider(), get_reviewer()
    if not analyst.uses_llm or reviewer is None:
        return first
    kw_stems = set(stems(" ".join(_keywords(req)) + " " + req.description))
    ranked = sorted(segs, key=lambda s: -len(kw_stems & s.stemset))[:14]
    excerpts = [(i, s.text) for i, s in enumerate(ranked)]
    verdicts = []
    for model in (analyst, reviewer):
        v = model.judge(req.description, excerpts)
        seg = ranked[v.segment] if v and v.segment is not None and 0 <= v.segment < len(ranked) else None
        ok = bool(v and seg and v.quote and normalize_ws(v.quote).lower() in normalize_ws(seg.text).lower())
        verdicts.append((model.model, v.verdict if v and ok else "unclear", seg if ok else None, v.reasoning if v else ""))
    (m1, v1, s1, why1), (m2, v2, s2, why2) = verdicts
    if v1 == v2 and v1 in ("satisfied", "not_satisfied"):
        status, pol = ("passed", "supports") if v1 == "satisfied" else ("failed", "contradicts")
        evidence = [(s, s.text, pol) for s in {id(x): x for x in (s1, s2) if x}.values()]
        return Result(status, first.checked + " The result was unclear, so two AI models reviewed the deliverable independently.",
                      f"Both AI models agreed, each citing a passage found in the deliverable. {m1}: {why1} {m2}: {why2}",
                      evidence)
    return Result("needs_review", first.checked + " Two AI models also reviewed it.",
                  f"{first.explanation} The AI models did not both reach a clear, cited verdict "
                  f"({m1}: {v1.replace('_', ' ')}; {m2}: {v2.replace('_', ' ')}), so this stays with a person.", first.evidence)


def load_deliverables(db: Session, project_id: int) -> tuple[list[Document], list[Seg]]:
    docs = db.scalars(select(Document).where(
        Document.project_id == project_id, Document.kind == "deliverable", Document.status == "analyzed")).all()
    segs: list[Seg] = []
    for d in docs:
        for i, s in enumerate((d.versions[-1].segments or []) if d.versions else []):
            segs.append(Seg(d, i, s.get("location"), s.get("text", "")))
    return list(docs), segs


def run(db: Session, project_id: int, user_id: int | None, requirement_ids: list[int] | None = None) -> dict:
    docs, segs = load_deliverables(db, project_id)
    if not docs:
        raise VerificationError("Upload a deliverable before running verification.")
    q = select(Requirement).where(Requirement.project_id == project_id).order_by(Requirement.id)
    if requirement_ids:
        q = q.where(Requirement.id.in_(requirement_ids))
    reqs = db.scalars(q).all()
    if not reqs:
        raise VerificationError("There are no requirements to verify yet.")
    run_id = str(uuid.uuid4())
    project = db.get(Project, project_id)
    autopilot_on = bool(project and project.autopilot)
    counts = {"passed": 0, "failed": 0, "needs_review": 0}
    for req in reqs:
        latest = db.scalar(select(RequirementValidation).where(
            RequirementValidation.requirement_id == req.id, RequirementValidation.is_latest.is_(True)))
        if req.verification_method == "manual" and latest and latest.reviewed_by:
            counts[latest.status] = counts.get(latest.status, 0) + 1
            continue  # keep the human decision
        if req.blocked_by_contradiction_id:
            res = Result("needs_review", "Checked whether the requirement itself is settled.",
                         "The source documents disagree about this requirement. Resolve the linked "
                         "contradiction first; OxisTrack will not guess which value is correct.")
        elif req.verification_method == "numeric":
            res = _check_numeric(req, segs)
        elif req.verification_method == "file_exists":
            res = _check_file(req, docs)
        elif req.verification_method == "semantic":
            res = _check_semantic(req, segs)
        elif req.verification_method == "manual":
            related = [s for s in segs if _matches(s, _keywords(req))]
            res = Result("needs_review", "This requirement is subjective and cannot be verified automatically.",
                         "Manual review required. Possibly related passages are listed to help the reviewer.",
                         [(s, s.text, "neutral") for s in related[:MAX_EVIDENCE]])
        else:
            res = _check_keyword(req, segs)
        if res.status == "needs_review" and autopilot_on and not req.blocked_by_contradiction_id:
            res = _ai_review(req, segs, res)
        db.execute(update(RequirementValidation).where(RequirementValidation.requirement_id == req.id)
                   .values(is_latest=False))
        db.add(RequirementValidation(
            project_id=project_id, requirement_id=req.id, run_id=run_id, is_latest=True, status=res.status,
            method=req.verification_method, checked=res.checked, explanation=res.explanation,
            evidence=[ValidationEvidence(
                document_id=s.doc.id if s else None, document_name=s.doc.filename if s else "",
                location=s.location if s else None, snippet=snippet[:1000], polarity=pol)
                for s, snippet, pol in res.evidence],
        ))
        req.status = res.status
        counts[res.status] += 1
    add_event(db, project_id, "info", "Verification run completed",
              description=f"{counts['passed']} passed, {counts['failed']} failed, {counts['needs_review']} need review "
                          f"against {', '.join(d.filename for d in docs)}.", source="OxisTrack verification")
    log_activity(db, project_id, user_id, "verification.run",
                 f"Verification: {counts['passed']} passed, {counts['failed']} failed, {counts['needs_review']} need review")
    db.commit()
    tasks.generate_suggestions(db, project_id)
    return {"run_id": run_id, **counts, "total": len(reqs), "deliverables": [d.filename for d in docs]}


def manual_review(db: Session, req: Requirement, user_id: int, status: str, note: str) -> RequirementValidation:
    db.execute(update(RequirementValidation).where(RequirementValidation.requirement_id == req.id)
               .values(is_latest=False))
    v = RequirementValidation(
        project_id=req.project_id, requirement_id=req.id, run_id=str(uuid.uuid4()), is_latest=True, status=status,
        method="manual", checked="Reviewed by a person.", explanation=note, reviewed_by=user_id)
    db.add(v)
    req.status = status
    log_activity(db, req.project_id, user_id, "requirement.reviewed", f"{req.code} manually marked {status}",
                 "requirement", req.id)
    db.commit()
    return v
