"""Deterministic text helpers: dates, numbers, money, subject normalisation, sentence splitting."""
from __future__ import annotations

import re
from datetime import date

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
_MONTH_RE = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
             r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
DATE_PATTERNS = [
    re.compile(rf"\b(?P<mon>{_MONTH_RE})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?\b", re.I),
    re.compile(rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mon>{_MONTH_RE})\.?(?:,?\s+(?P<year>\d{{4}}))?\b",
               re.I),
    re.compile(r"\b(?P<year>\d{4})-(?P<mnum>\d{1,2})-(?P<day>\d{1,2})\b"),
    re.compile(r"\b(?P<mnum>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b"),
]

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_NUMWORD_RE = "|".join(k for k in NUMBER_WORDS if k != "one")  # "one" is too often a pronoun
NUM_RE = rf"(?:\d[\d,]*(?:\.\d+)?|{_NUMWORD_RE})"

MONEY_RE = re.compile(
    r"(?:(?P<cur>[$€£])\s?(?P<amt>\d[\d,]*(?:\.\d+)?)\s?(?P<suf>k|m|million|thousand)?\b)"
    r"|(?:\b(?P<amt2>\d[\d,]*(?:\.\d+)?)\s?(?P<suf2>k|m|million|thousand)?\s?(?P<cur2>usd|dollars|eur|euros|gbp|pounds)\b)",
    re.I,
)

SUBJECT_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "our", "its", "this", "that", "is", "are",
    "be", "project", "application", "app", "system", "product", "platform", "website", "site", "updated",
    "new", "final", "revised", "current", "original", "total", "overall", "number", "count", "required",
    "full", "basic", "complete", "proposed", "planned", "target", "feature", "features", "functionality",
    "capability", "support", "all", "each", "every", "their", "own", "with", "must", "should",
}
STOPWORDS = SUBJECT_STOPWORDS | {
    "it", "as", "at", "by", "from", "will", "shall", "have", "has", "include", "includes", "including",
    "we", "you", "they", "there", "which", "also", "can", "may", "not", "no", "any", "but", "if", "so",
    "than", "then", "into", "was", "were", "been", "being", "do", "does", "need", "needs", "require",
    "requires", "provide", "provides", "allow", "allows", "use", "uses", "user", "users",
}


def stem(word: str) -> str:
    """Tiny suffix-stripping stemmer; good enough to match plural / verb forms."""
    w = word.lower()
    for suf, rep in (("ies", "y"), ("sses", "ss"), ("ing", ""),
                     ("ed", ""), ("es", "e"), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and not (suf == "s" and w.endswith("ss")):
            return w[: len(w) - len(suf)] + rep
    return w


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-+#.]*[a-z0-9+#]|[a-z0-9]", text.lower())


def stems(text: str, drop_stop: bool = True) -> list[str]:
    return [stem(t) for t in tokens(text) if not (drop_stop and t in STOPWORDS)]


def subject_key(subject: str) -> str:
    """Normalise a subject so that 'Updated project deadline' and 'Project deadline' compare equal."""
    toks = [t for t in tokens(subject) if t not in SUBJECT_STOPWORDS]
    if not toks:
        toks = tokens(subject)
    return " ".join(stem(t) for t in toks)[:200]


def parse_number(raw: str) -> float | None:
    r = raw.strip().lower()
    if r in NUMBER_WORDS:
        return float(NUMBER_WORDS[r])
    try:
        return float(r.replace(",", ""))
    except ValueError:
        return None


def fmt_number(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def find_dates(text: str, ref: date | None = None) -> list[tuple[str, date, tuple[int, int]]]:
    """Return (matched text, date, span) for every date-like expression. Year-less dates are resolved
    against `ref` (the document date or today): the nearest occurrence not more than ~4 months before it."""
    ref = ref or date.today()
    out: list[tuple[str, date, tuple[int, int]]] = []
    taken: list[tuple[int, int]] = []
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            gd = m.groupdict()
            try:
                month = MONTHS[gd["mon"].lower().rstrip(".")] if gd.get("mon") else int(gd["mnum"])
                day = int(gd["day"])
                if gd.get("year"):
                    d = date(int(gd["year"]), month, day)
                else:
                    d = date(ref.year, month, day)
                    if (ref - d).days > 120:
                        d = date(ref.year + 1, month, day)
            except (ValueError, KeyError):
                continue
            taken.append(m.span())
            out.append((m.group(0), d, m.span()))
    out.sort(key=lambda x: x[2][0])
    return out


def find_money(text: str) -> list[tuple[str, float, tuple[int, int]]]:
    out = []
    for m in MONEY_RE.finditer(text):
        amt = m.group("amt") or m.group("amt2")
        suf = (m.group("suf") or m.group("suf2") or "").lower()
        val = float(amt.replace(",", ""))
        if suf in ("k", "thousand"):
            val *= 1_000
        elif suf in ("m", "million"):
            val *= 1_000_000
        out.append((m.group(0).strip(), val, m.span()))
    return out


_ABBR = re.compile(r"\b(?:e\.g|i\.e|etc|vs|mr|mrs|ms|dr|no|approx)\.$", re.I)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text.strip())
    out: list[str] = []
    for p in parts:
        if out and _ABBR.search(out[-1]):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return [p.strip() for p in out if p.strip()]


def clean_line(line: str) -> str:
    """Strip markdown / bullet decoration from a line."""
    s = line.strip()
    s = re.sub(r"^(?:#{1,6}\s+|[-*•·▪◦‣–]\s+|\d{1,2}[.)]\s+|\[[ xX]\]\s+)+", "", s)
    s = re.sub(r"(\*\*|__|`)", "", s)
    return s.strip()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def humanize(key: str) -> str:
    return key[:1].upper() + key[1:] if key else key
