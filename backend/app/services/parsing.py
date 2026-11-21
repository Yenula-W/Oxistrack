"""Document parsing: turn an uploaded file into ordered, citable text segments."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .textutil import clean_line, normalize_ws, split_sentences

ALLOWED_TYPES = {"pdf", "docx", "txt", "csv", "xlsx", "md"}
MAX_SEGMENTS = 4000
MAX_ROWS = 2000


class ParseError(Exception):
    pass


@dataclass
class Segment:
    location: str | None
    text: str

    def as_dict(self) -> dict:
        return {"location": self.location, "text": self.text}


def file_type_of(filename: str) -> str | None:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext == "markdown":
        ext = "md"
    return ext if ext in ALLOWED_TYPES else None


def sniff_ok(file_type: str, head: bytes) -> bool:
    """Cheap content check so a renamed binary is not accepted as a document."""
    if file_type == "pdf":
        return head.startswith(b"%PDF")
    if file_type in ("docx", "xlsx"):
        return head.startswith(b"PK")
    return b"\x00" not in head  # text formats must not contain NUL bytes


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ParseError("Could not decode the file as text.")


def _segments_from_lines(lines: list[tuple[str | None, str]]) -> list[Segment]:
    out: list[Segment] = []
    for loc, raw in lines:
        line = clean_line(raw)
        if not line or set(line) <= set("-=_*|: "):
            continue
        for sent in split_sentences(line):
            out.append(Segment(loc, normalize_ws(sent)))
    return out


def _parse_text(data: bytes) -> list[Segment]:
    text = _decode(data)
    return _segments_from_lines([(f"Line {i}", ln) for i, ln in enumerate(text.splitlines(), 1)])


def _unwrap(lines: list[str]) -> list[str]:
    """Join hard-wrapped PDF lines back into sentences."""
    out: list[str] = []
    for ln in (l.strip() for l in lines):
        if not ln:
            continue
        prev = out[-1] if out else ""
        wrapped = len(prev) >= 60 and not prev.endswith((".", ":", ";", "!", "?")) and clean_line(ln) == ln
        if prev and wrapped:
            out[-1] = prev + " " + ln
        else:
            out.append(ln)
    return out


def _parse_pdf(data: bytes) -> list[Segment]:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise ParseError("The PDF could not be opened (it may be corrupt or encrypted).") from exc
    lines: list[tuple[str | None, str]] = []
    with doc:
        if doc.needs_pass:
            raise ParseError("The PDF is password protected.")
        for pno, page in enumerate(doc, 1):
            for block in page.get_text("blocks"):
                if len(block) >= 7 and block[6] != 0:  # skip image blocks
                    continue
                for ln in _unwrap(str(block[4]).splitlines()):
                    lines.append((f"Page {pno}", ln))
    if not lines:
        raise ParseError("No selectable text found in the PDF (scanned PDFs need OCR, which is not enabled).")
    return _segments_from_lines(lines)


def _row_segments(prefix: str, rows: list[list[str]]) -> list[Segment]:
    """Tabular data → 'label: value' statements so each cell is citable by row."""
    rows = [[normalize_ws(str(c)) if c is not None else "" for c in r] for r in rows[:MAX_ROWS]]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    width = max(len(r) for r in rows)
    out: list[Segment] = []
    if width <= 2:
        for i, r in enumerate(rows, 1):
            cells = [c for c in r if c]
            if len(cells) == 2:
                out.append(Segment(f"{prefix}row {i}", f"{cells[0]}: {cells[1]}"))
            elif cells:
                out.append(Segment(f"{prefix}row {i}", cells[0]))
        return out
    for i, r in enumerate(body, 2):
        label = r[0] if r else ""
        for j in range(1, len(r)):
            if not r[j]:
                continue
            head = header[j] if j < len(header) and header[j] else f"Column {j + 1}"
            out.append(Segment(f"{prefix}row {i}", f"{label} {head}: {r[j]}" if label else f"{head}: {r[j]}"))
    return out


def _parse_csv(data: bytes) -> list[Segment]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return _row_segments("", list(csv.reader(io.StringIO(text), dialect)))


def _parse_xlsx(data: bytes) -> list[Segment]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ParseError("The spreadsheet could not be opened.") from exc
    out: list[Segment] = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if c is None else (c.date().isoformat() if hasattr(c, "date") else str(c)) for c in row])
            if len(rows) >= MAX_ROWS:
                break
        out.extend(_row_segments(f"Sheet '{ws.title}', ", rows))
    return out


def _parse_docx(data: bytes) -> list[Segment]:
    import docx

    try:
        d = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ParseError("The Word document could not be opened.") from exc
    lines = [(f"Paragraph {i}", p.text) for i, p in enumerate(d.paragraphs, 1)]
    out = _segments_from_lines(lines)
    for t, table in enumerate(d.tables, 1):
        rows = [[c.text for c in row.cells] for row in table.rows]
        out.extend(_row_segments(f"Table {t}, ", rows))
    return out


def parse_document(file_type: str, data: bytes) -> list[Segment]:
    parser = {"pdf": _parse_pdf, "docx": _parse_docx, "xlsx": _parse_xlsx, "csv": _parse_csv,
              "txt": _parse_text, "md": _parse_text}.get(file_type)
    if parser is None:
        raise ParseError(f"Unsupported file type: {file_type}")
    segments = parser(data)[:MAX_SEGMENTS]
    if not segments:
        raise ParseError("The document contains no readable text.")
    return segments
