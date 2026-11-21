"""Local rule-based intelligence engine.

Deterministic extraction of facts and requirements. It is used when no LLM is configured and as the
fallback / cross-check when one is. Every fact it emits is tied to the exact segment it came from.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .parsing import Segment
from .textutil import (
    NUM_RE, find_dates, find_money, fmt_number, normalize_ws, parse_number, split_sentences, stems,
    subject_key, tokens,
)

FACT_CATEGORIES = [
    "deadline", "date", "requirement", "decision", "goal", "entity", "budget", "quantity",
    "technical_spec", "constraint", "dependency", "statement",
]


@dataclass
class FactDraft:
    segment_index: int
    category: str
    text: str
    subject: str = ""
    value_text: str | None = None
    value_norm: str | None = None
    value_type: str = "none"
    confidence: float = 0.6
    extractor: str = "rules"


@dataclass
class RequirementDraft:
    title: str
    description: str
    category: str = "functional"
    priority: str = "medium"
    verification_method: str = "keyword"
    keywords: list[str] = field(default_factory=list)
    subject_key: str = ""
    expected_value: str | None = None
    source_text: str = ""


# Subjects that describe the document itself; never compared across documents.
META_KEYS = {"date", "document date", "meeting date", "dated", "created", "last updated", "prepared on",
             "version", "author", "prepared by", "attendee", "attendees", "status", "document", "title",
             "subject", "from", "to", "cc", "location", "time", "facilitator", "note taker", "revision"}
DOC_DATE_KEYS = {"date", "document date", "meeting date", "dated", "created", "prepared on", "last updated"}
NOTE_KEYS = {"note", "important", "action", "action item", "todo", "decision", "agreed", "outcome", "update",
             "summary", "requirement", "requirements", "goal", "objective", "constraint", "risk",
             "dependency", "scope", "deliverable", "open question", "follow-up", "follow up"}
ENTITY_KEYS = re.compile(r"\b(owner|manager|lead|client|sponsor|author|prepared by|attendees?|team|contact|"
                         r"stakeholders?|vendor|customer|organi[sz]er|facilitator|approver|reviewer)\b")
TECH_KEYS = re.compile(r"\b(platforms?|stack|framework|database|language|backend|frontend|hosting|api|os|"
                       r"browsers?|tech|technology|architecture|infrastructure|runtime|protocol)\b")
DEADLINE_KEY = re.compile(r"\b(deadline|due|launch|release|delivery|go-live|submission|milestone|ship|handoff|"
                          r"handover|completion)\b")
BUDGET_KEY = re.compile(r"\b(budget|cost|price|funding|spend|fee|estimate)\b")
KV_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 \-/&()']{1,60}?)\s*[:=]\s+(.+)$")

DEADLINE_RE = re.compile(
    r"\b(deadline|due date|due|deliver(?:ed|y)? (?:by|date)|launch(?:es)?(?: date)?|release date|go-live|"
    r"submission date|(?:completed|delivered|submitted|finished|ready) by|ship(?:s|ping)? (?:by|on))\b", re.I)
DEADLINE_SUBJ = re.compile(
    r"((?:[a-z\-]+ ){0,2}(?:deadline|due date|launch date|release date|go-live date|submission date|delivery date))")
BUDGET_SUBJ = re.compile(r"((?:[a-z\-]+ ){0,2}(?:budget|cost|price|funding))")
MODAL_RE = re.compile(
    r"\b(must not|shall not|should not|may not|cannot|can't|must|shall|should|has to|have to|needs? to|"
    r"(?:is|are) required to|requires?|required|will need to|(?:is|are) expected to)\b", re.I)
QTY_RE = re.compile(rf"\b({NUM_RE})\s+((?:[a-z][a-z\-]*\s+){{0,2}}?[a-z][a-z\-]*s)\b", re.I)
QTY_KV_RE = re.compile(rf"^({NUM_RE})\s*(%|[a-z]+(?:\s[a-z]+)?)?\.?$", re.I)
UNIT_NOUNS = {"days", "weeks", "months", "years", "hours", "minutes", "seconds", "times", "ms", "percent",
              "points", "items", "things", "versus", "others", "is", "was", "has", "does", "this", "its"}
CONSTRAINT_RE = re.compile(r"\b(must not|shall not|should not|cannot|can't|at most|no more than|limited to|"
                           r"maximum|minimum|at least|no fewer than|within \d|restricted|only)\b", re.I)
DECISION_RE = re.compile(r"\b(decided|agreed|approved|confirmed|chose|chosen|selected|will use|signed off|"
                         r"resolved to|decision)\b", re.I)
GOAL_RE = re.compile(r"\b(goals?|objectives?|aims? to|purpose|mission|vision)\b", re.I)
DEPENDENCY_RE = re.compile(r"\b(depends? on|dependent on|blocked by|prerequisite|relies on|contingent on|"
                           r"cannot start until)\b", re.I)
TECH_RE = re.compile(
    r"\b(react(?: native)?|next\.?js|vue|angular|flutter|swift|kotlin|ios|android|python|fastapi|django|node\.?js|"
    r"typescript|javascript|java|postgres(?:ql)?|mysql|mongodb|sqlite|redis|firebase|aws|azure|gcp|docker|"
    r"kubernetes|rest(?:ful)? api|graphql|oauth|jwt|https|tls|websockets?|sdk|ci/cd)\b", re.I)
STATEMENT_RE = re.compile(
    r"\b(needs? (?:revision|review|rework|an update|updating|approval|clarification|redesign)|"
    r"to be (?:revised|confirmed|decided|determined)|tbd|pending|under review|open question|at risk|blocker|"
    r"postponed|deferred|out of scope|changed|moved to|no longer)\b", re.I)
_LEAD_VERBS = re.compile(
    r"^(?:also|be able to|include|includes|support|supports|have|has|provide|provides|offer|contain|implement|"
    r"feature|allow|enable|use|be|deliver|prepare|produce|write|create|run|display|show|send|handle|store|expose|integrate with|comply with|run on|"
    r"work on|a|an|the|its|their|full|basic)\s+", re.I)
_OBJ_STOP = re.compile(r"\s+(?:for|so|that|which|to|when|with|by|in|and|or|using|on|across|within|per|before|"
                       r"after|from|at|as|via|through)\s+|[,;.(:]")


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    out = text
    for s, e in spans:
        out = out[:s] + " " * (e - s) + out[e:]
    return out


def find_quantities(text: str) -> list[tuple[float, str, str]]:
    """(number, noun phrase, matched text) for expressions like 'three user roles'. Dates are ignored."""
    work = _blank(text, [sp for _, _, sp in find_dates(text)] + [sp for _, _, sp in find_money(text)])
    out = []
    for m in QTY_RE.finditer(work):
        n = parse_number(m.group(1))
        phrase = m.group(2).strip().lower()
        if n is None or phrase.split()[-1] in UNIT_NOUNS or phrase.split()[0] in UNIT_NOUNS:
            continue
        out.append((n, phrase, m.group(0)))
    return out


def _object_phrase(after_modal: str) -> str:
    s = after_modal.strip()
    for _ in range(4):
        new = _LEAD_VERBS.sub("", s, count=1)
        if new == s:
            break
        s = new
    s = _OBJ_STOP.split(s + " ", maxsplit=1)[0]
    return " ".join(s.split()[:4]).strip(" .")


def _sentence_fact(idx: int, s: str, ref: date | None, hint: str | None = None) -> FactDraft | None:
    low = s.lower()
    dates = find_dates(s, ref)
    money = find_money(s)
    modal = MODAL_RE.search(s)

    if dates and (DEADLINE_RE.search(s) or hint == "deadline"):
        txt, d, _ = dates[-1] if re.search(r"\bfrom\b.+\bto\b", low) else dates[0]
        m = DEADLINE_SUBJ.search(low)
        return FactDraft(idx, "deadline", s, (m.group(1) if m else "deadline").strip(), txt, d.isoformat(),
                         "date", 0.85)
    if money and BUDGET_KEY.search(low):
        txt, val, _ = money[0]
        m = BUDGET_SUBJ.search(low)
        return FactDraft(idx, "budget", s, (m.group(1) if m else "budget").strip(), txt, fmt_number(val),
                         "money", 0.85)
    if DEPENDENCY_RE.search(s):
        return FactDraft(idx, "dependency", s, confidence=0.75)

    qty = find_quantities(s)
    if qty and (modal or re.search(r"\b(support|include|have|has|with|contain|offer|provide)s?\b", low)):
        n, phrase, matched = qty[0]
        cat = "requirement" if modal else "quantity"
        return FactDraft(idx, cat, s, phrase, matched, fmt_number(n), "number", 0.85 if modal else 0.75)
    if modal:
        negative = bool(re.match(r"(must not|shall not|should not|may not|cannot|can't)", modal.group(1), re.I))
        obj = _object_phrase(s[modal.end():])
        cat = "constraint" if CONSTRAINT_RE.search(s) else "requirement"
        if not obj or len(tokens(obj)) == 0:
            return FactDraft(idx, cat, s, confidence=0.6)
        return FactDraft(idx, cat, s, obj, "prohibited" if negative else "required",
                         "prohibited" if negative else "required", "presence", 0.8)
    if DECISION_RE.search(s) or hint == "decision":
        return FactDraft(idx, "decision", s, confidence=0.75)
    if GOAL_RE.search(s) or hint == "goal":
        return FactDraft(idx, "goal", s, confidence=0.7)
    if TECH_RE.search(s):
        return FactDraft(idx, "technical_spec", s, confidence=0.65)
    if dates:
        txt, d, _ = dates[0]
        return FactDraft(idx, "date", s, "", txt, d.isoformat(), "date", 0.7)
    if money:
        txt, val, _ = money[0]
        return FactDraft(idx, "budget", s, "", txt, fmt_number(val), "money", 0.65)
    m = STATEMENT_RE.search(s)
    if m or hint:
        subj = " ".join(s[: m.start()].split()[-4:]).strip(" ,.") if m else ""
        return FactDraft(idx, hint if hint in FACT_CATEGORIES else "statement", s, subj, confidence=0.6)
    return None


def _kv_fact(idx: int, text: str, key: str, val: str, ref: date | None) -> FactDraft | None:
    klow = normalize_ws(key.lower())
    val = val.strip()
    if klow in NOTE_KEYS:
        hint = {"decision": "decision", "agreed": "decision", "outcome": "decision", "goal": "goal",
                "objective": "goal", "constraint": "constraint", "dependency": "dependency",
                "requirement": "requirement", "requirements": "requirement"}.get(klow, "statement")
        f = _sentence_fact(idx, val, ref, hint=hint)
        if f:
            f.text = text
        return f

    dates = find_dates(val, ref)
    if dates and len(val) <= 60:
        txt, d, _ = dates[-1] if re.search(r"\bfrom\b.+\bto\b", val.lower()) else dates[0]
        cat = "deadline" if DEADLINE_KEY.search(klow) else "date"
        subject = "document date" if klow in DOC_DATE_KEYS else key
        return FactDraft(idx, cat, text, subject, txt, d.isoformat(), "date", 0.95)
    money = find_money(val)
    if money and len(val) <= 60:
        txt, amount, _ = money[0]
        return FactDraft(idx, "budget", text, key, txt, fmt_number(amount), "money", 0.95)
    m = QTY_KV_RE.match(val)
    if m and parse_number(m.group(1)) is not None:
        n = parse_number(m.group(1))
        if BUDGET_KEY.search(klow):
            return FactDraft(idx, "budget", text, key, val.rstrip("."), fmt_number(n), "money", 0.9)
        return FactDraft(idx, "quantity", text, key, val.rstrip("."), fmt_number(n), "number", 0.9)

    if len(key.split()) <= 5 and len(val.split()) <= 14:
        if ENTITY_KEYS.search(klow):
            cat = "entity"
        elif TECH_KEYS.search(klow):
            cat = "technical_spec"
        elif GOAL_RE.search(klow):
            cat = "goal"
        else:
            cat = "statement"
        norm = " ".join(sorted(set(stems(val, drop_stop=False))))
        return FactDraft(idx, cat, text, key, val.rstrip("."), norm, "text", 0.8)
    return _sentence_fact(idx, text, ref)


def extract_facts(segments: list[Segment], ref: date | None = None) -> list[FactDraft]:
    facts: list[FactDraft] = []
    for idx, seg in enumerate(segments):
        text = seg.text.strip()
        if len(text) < 6 or len(text) > 1200:
            continue
        kv = KV_RE.match(text)
        if kv and (MODAL_RE.search(kv.group(1)) or re.search(r"\d", kv.group(1)) or len(kv.group(1).split()) > 5
                   or find_quantities(kv.group(1))):
            kv = None
        fact = _kv_fact(idx, text, kv.group(1), kv.group(2), ref) if kv else _sentence_fact(idx, text, ref)
        if fact:
            facts.append(fact)
    return facts


def detect_document_date(segments: list[Segment], ref: date | None = None) -> date | None:
    """Look for an explicit 'Date: …' style header near the top of the document."""
    for seg in segments[:20]:
        kv = KV_RE.match(seg.text.strip())
        if kv and normalize_ws(kv.group(1).lower()) in DOC_DATE_KEYS:
            dates = find_dates(kv.group(2), ref)
            if dates:
                return dates[0][1]
    return None


# ---------------------------------------------------------------- requirements

SYNONYMS: dict[str, list[str]] = {
    "login": ["login", "log in", "log-in", "sign in", "sign-in", "signin", "authentication"],
    "authentication": ["authentication", "login", "log in", "sign in", "sign-in"],
    "registration": ["registration", "register", "sign up", "sign-up", "signup"],
    "notification": ["notification", "notify", "push alert"],
    "responsive": ["responsive", "mobile layout", "mobile-friendly", "breakpoint", "media query", "adaptive layout"],
    "search": ["search"],
    "dashboard": ["dashboard"],
    "export": ["export"],
    "report": ["report", "reporting"],
    "payment": ["payment", "checkout", "billing"],
    "profile": ["profile", "account settings"],
    "chat": ["chat", "messaging"],
    "analytic": ["analytics", "metrics"],
    "offline": ["offline"],
    "accessibility": ["accessibility", "a11y", "wcag", "screen reader"],
    "dark": ["dark mode", "dark theme"],
    "documentation": ["documentation", "readme", "user guide"],
}
_CATEGORY_RULES = [
    ("security", r"login|log in|sign in|auth|password|permission|role|encrypt|secur|privacy|2fa|access control"),
    ("interface", r"dashboard|layout|responsive|mobile|screen|design|theme|page|ui\b|ux\b|navigation|accessib"),
    ("communication", r"notif|email|sms|message|alert|chat"),
    ("data", r"database|storage|export|import|backup|sync|data\b|record|schema"),
    ("performance", r"fast|second|latency|load time|uptime|scal|performance|concurrent"),
    ("integration", r"\bapi\b|integrat|webhook|third-party|sso|oauth"),
    ("documentation", r"document|readme|manual|guide|report"),
    ("quality", r"test|qa\b|coverage|bug"),
]
_SUBJECTIVE = re.compile(r"\b(intuitive|user-friendly|user friendly|easy|clean|modern|attractive|professional|"
                         r"polished|engaging|high[- ]quality|beautiful|simple|pleasant|appropriate|reasonable|"
                         r"robust|maintainable|readable|well[- ]designed)\b", re.I)
_FILE_RE = re.compile(r"\b(readme|license|changelog|[\w\-]+\.(?:md|txt|pdf|docx|csv|xlsx|json|ya?ml))\b", re.I)
_LIST_INTRO = re.compile(r"\b(with|includes?|including|supports?|supporting|have|has|having|provides?|"
                         r"contains?|features?|featuring|offers?|consisting of|such as|needs?|requires?)\b[: ]", re.I)
_BUILD_VERBS = {"create", "build", "develop", "make", "design", "implement", "deliver", "write", "produce",
                "a", "an", "the", "new", "we", "need", "want", "please", "to", "i", "should", "must", "our"}
_SUPPORT_HINT = re.compile(r"layout|responsive|language|platform|browser|device|mode|format|locale|offline", re.I)


def categorize(text: str) -> str:
    low = text.lower()
    for cat, pat in _CATEGORY_RULES:
        if re.search(pat, low):
            return cat
    return "functional"


def priority_of(text: str) -> str:
    low = text.lower()
    if re.search(r"\b(must|shall|required|requires|critical|essential|mandatory|has to|needs? to)\b", low):
        return "high"
    if re.search(r"\b(could|may|nice to have|optional|if time|stretch|ideally)\b", low):
        return "low"
    return "medium"


def keywords_for(phrase: str) -> list[str]:
    """Search terms used by deterministic checks: the phrase itself plus known synonyms."""
    base = " ".join(t for t in tokens(phrase) if t not in {"a", "an", "the", "of", "for", "system", "feature",
                                                             "functionality", "support", "page", "module"})
    out = [base] if base else []
    for st in stems(phrase):
        for alt in SYNONYMS.get(st, []):
            if alt not in out:
                out.append(alt)
    return out[:10]


def method_for(text: str, expected_value: str | None = None) -> str:
    if _SUBJECTIVE.search(text):
        return "manual"
    if expected_value is not None or find_quantities(text):
        return "numeric"
    if _FILE_RE.search(text) and re.search(r"\bfile|readme|license|changelog|\.\w{2,4}\b", text.lower()):
        return "file_exists"
    return "keyword"


def _title(phrase: str) -> str:
    p = phrase.strip(" .")
    return p[:1].upper() + p[1:]


def _draft(subject_noun: str, item: str, source: str, prio: str | None = None) -> RequirementDraft:
    item = re.sub(r"^(?:and|or|also|a|an|the)\s+", "", item.strip(" .;"), flags=re.I)
    item = re.sub(r"^(?:and|or|also|a|an|the)\s+", "", item, flags=re.I)
    qty = find_quantities(item)
    verb = "support" if _SUPPORT_HINT.search(item) else "include"
    article = "" if (qty or item.endswith("s") or verb == "support") else ("an " if item[:1].lower() in "aeiou" else "a ")
    if verb == "support" and not item.endswith("s") and "layout" in item:
        item_desc = item + "s"
    else:
        item_desc = item
    desc = f"The {subject_noun} must {verb} {article}{item_desc}."
    expected, key, kw_phrase = None, subject_key(item), item
    if qty:
        n, phrase, _ = qty[0]
        expected, key, kw_phrase = fmt_number(n), subject_key(phrase), phrase
    return RequirementDraft(
        title=_title(item), description=desc, category=categorize(item), priority=prio or priority_of(source),
        verification_method=method_for(item, expected), keywords=keywords_for(kw_phrase), subject_key=key,
        expected_value=expected, source_text=source,
    )


def _split_items(tail: str) -> list[str]:
    tail = tail.strip(" .:")
    parts = re.split(r"\s*(?:,\s*(?:and\s+|or\s+)?|;\s*|\s+and\s+(?=(?:a|an|the)\s))\s*", tail)
    if len(parts) == 1 and " and " in tail:
        parts = tail.split(" and ")
    return [p.strip() for p in parts if len(p.strip()) > 1]


def compile_requirements(text: str) -> list[RequirementDraft]:
    """Turn natural-language instructions into atomic, checkable requirement drafts."""
    drafts: list[RequirementDraft] = []
    seen: set[str] = set()
    last_noun = "deliverable"
    lines = [ln for raw in text.splitlines() for ln in split_sentences(re.sub(r"^[\s\-*•\d.)]+", "", raw))]
    for sent in lines:
        sent = normalize_ws(sent)
        if len(sent) < 4:
            continue
        m = _LIST_INTRO.search(sent)
        lead = sent[: m.start()] if m else ""
        lead_tokens = [t for t in tokens(MODAL_RE.sub(" ", lead)) if t not in _BUILD_VERBS]
        if lead_tokens:
            last_noun = " ".join(lead_tokens[-2:]) if len(lead_tokens[-1]) < 4 else lead_tokens[-1]
        new: list[RequirementDraft] = []
        if m and lead.strip() and len(_split_items(sent[m.end():])) >= 1 and len(sent[m.end():].split()) <= 40:
            prio = "high" if not MODAL_RE.search(sent) or priority_of(sent) == "high" else priority_of(sent)
            new = [_draft(last_noun, it, sent, prio) for it in _split_items(sent[m.end():])]
        else:
            modal = MODAL_RE.search(sent)
            obj = _object_phrase(sent[modal.end():]) if modal else ""
            qty = find_quantities(sent)
            expected = fmt_number(qty[0][0]) if qty else None
            phrase = qty[0][1] if qty else (obj or " ".join(stems(sent)[:4]))
            new = [RequirementDraft(
                title=_title(phrase or sent[:60]), description=sent if sent.endswith(".") else sent + ".",
                category=categorize(sent), priority=priority_of(sent),
                verification_method=method_for(sent, expected), keywords=keywords_for(phrase),
                subject_key=subject_key(phrase), expected_value=expected, source_text=sent,
            )]
        for d in new:
            if d.subject_key and d.subject_key not in seen:
                seen.add(d.subject_key)
                drafts.append(d)
    return drafts
