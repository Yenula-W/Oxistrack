"""Unit tests for the deterministic engine: parsing, extraction, requirement compilation, LLM guard rails."""
import io
import json
from datetime import date

import httpx

from app.services import rules
from app.services.ai import LLMProvider
from app.services.parsing import Segment, file_type_of, parse_document, sniff_ok
from app.services.pipeline import safe_filename
from app.services.textutil import find_dates, subject_key


def seg(*lines):
    return [Segment(f"Line {i}", t) for i, t in enumerate(lines, 1)]


def test_subject_normalisation_groups_variants():
    assert subject_key("Updated project deadline") == subject_key("Project deadline") == "deadline"
    assert subject_key("user roles") == subject_key("Number of user roles") == "user role"


def test_dates_without_year_resolve_against_reference():
    assert find_dates("December 20", date(2026, 11, 1))[0][1] == date(2026, 12, 20)
    assert find_dates("January 5", date(2026, 11, 1))[0][1] == date(2027, 1, 5)
    assert find_dates("2026-03-04")[0][1] == date(2026, 3, 4)


def test_extracts_typed_facts_with_sources():
    facts = rules.extract_facts(seg(
        "Project deadline: December 20, 2026", "The application requires three user roles.",
        "Application must include a dashboard.", "Budget: $48,000", "Dashboard design needs revision.",
        "Overview"), date(2026, 11, 1))
    by_cat = {f.category: f for f in facts}
    assert by_cat["deadline"].value_norm == "2026-12-20" and by_cat["deadline"].segment_index == 0
    req = [f for f in facts if f.category == "requirement"]
    assert (req[0].subject, req[0].value_norm, req[0].value_type) == ("user roles", "3", "number")
    assert (req[1].subject, req[1].value_type) == ("dashboard", "presence")
    assert by_cat["budget"].value_norm == "48000"
    assert by_cat["statement"].subject == "Dashboard design"
    assert all(f.text != "Overview" for f in facts)  # headings are not facts


def test_compiles_the_spec_example():
    drafts = rules.compile_requirements(
        "Create a website with a login system, a dashboard, a search feature, and a responsive mobile layout.")
    assert [d.description for d in drafts] == [
        "The website must include a login system.", "The website must include a dashboard.",
        "The website must include a search feature.", "The website must support responsive mobile layouts."]
    assert "sign in" in drafts[0].keywords
    subjective = rules.compile_requirements("The interface should be intuitive.")[0]
    assert subjective.verification_method == "manual"
    numeric = rules.compile_requirements("The app must support five user roles.")[0]
    assert (numeric.verification_method, numeric.expected_value) == ("numeric", "5")


def test_parsers_for_every_supported_format():
    import docx
    import openpyxl
    import pymupdf

    assert [s.text for s in parse_document("md", b"# Title\n\n- Deadline: May 1\n- Must support search.")] == [
        "Title", "Deadline: May 1", "Must support search."]
    assert parse_document("csv", b"Item,Value\nBudget,5000\n")[1].text == "Budget: 5000"

    d = docx.Document()
    d.add_paragraph("Project deadline: June 3, 2027")
    buf = io.BytesIO()
    d.save(buf)
    out = parse_document("docx", buf.getvalue())
    assert out[0].text == "Project deadline: June 3, 2027" and out[0].location == "Paragraph 1"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Phase", "Cost", "Owner"])
    ws.append(["Design", 5000, "Mia"])
    buf = io.BytesIO()
    wb.save(buf)
    texts = [s.text for s in parse_document("xlsx", buf.getvalue())]
    assert "Design Cost: 5000" in texts

    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "The application must include notifications.")
    out = parse_document("pdf", pdf.tobytes())
    assert out[0].location == "Page 1" and "notifications" in out[0].text


def test_upload_guards():
    assert file_type_of("notes.exe") is None and file_type_of("a.PDF") == "pdf"
    assert not sniff_ok("pdf", b"MZ\x90\x00 not a pdf")
    assert not sniff_ok("txt", b"abc\x00def")
    assert safe_filename("../../etc/passwd.txt") == "passwd.txt"
    assert "/" not in safe_filename("..\\..\\windows\\evil.md")


def _llm(payload: dict) -> LLMProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    return LLMProvider("https://llm.invalid/v1", "test-key", "test-model", transport=httpx.MockTransport(handler))


def test_llm_facts_with_invented_quotes_are_discarded():
    segments = seg("The app will be built by a team in Lisbon.")
    provider = _llm({"facts": [
        {"segment": 0, "category": "entity", "subject": "team location", "value": "Lisbon", "value_type": "text",
         "quote": "team in Lisbon", "confidence": 0.9},
        {"segment": 0, "category": "deadline", "subject": "deadline", "value": "March 1", "value_type": "date",
         "quote": "The deadline is March 1", "confidence": 0.99},
        {"segment": 7, "category": "goal", "subject": "x", "quote": "anything", "confidence": 0.9},
    ]})
    facts = provider.extract_facts(segments)
    assert [f.subject for f in facts] == ["team location"] and facts[0].extractor == "llm"


def test_llm_failure_falls_back_to_rules():
    def handler(request):
        return httpx.Response(500)

    provider = LLMProvider("https://llm.invalid/v1", "k", "m", transport=httpx.MockTransport(handler))
    facts = provider.extract_facts(seg("Project deadline: December 20, 2026"))
    assert facts and facts[0].extractor == "rules"
    assert provider.compile_requirements("The app must include a dashboard.")[0].title == "Dashboard"
    assert provider.judge("x", [(0, "y")]) is None
