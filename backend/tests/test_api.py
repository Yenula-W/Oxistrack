"""End-to-end API tests: the full OxisTrack workflow against a real database session."""


def _register(client, email, name="Bea"):
    r = client.post("/auth/register", json={"email": email, "name": name, "password": "correct-horse"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload(client, pid, files, kind="source"):
    return client.post(f"/projects/{pid}/documents", data={"kind": kind},
                       files=[("files", (name, content, "application/octet-stream")) for name, content in files])


def test_auth_flow(client):
    assert client.get("/projects").status_code == 401
    assert client.post("/auth/register", json={"email": "x@example.com", "name": "X", "password": "short"}).status_code == 422
    client.post("/auth/register", json={"email": "x@example.com", "name": "X", "password": "long-enough-pw"})
    assert client.post("/auth/register", json={"email": "X@example.com", "name": "X", "password": "long-enough-pw"}).status_code == 409
    assert client.post("/auth/login", json={"email": "x@example.com", "password": "wrong-password"}).status_code == 401
    tok = client.post("/auth/login", json={"email": "x@example.com", "password": "long-enough-pw"}).json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["email"] == "x@example.com"
    assert client.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_project_access_control(auth):
    pid = auth.post("/projects", json={"name": "Private"}).json()["id"]
    doc = _upload(auth, pid, [("a.txt", b"Project deadline: May 1, 2027")]).json()["documents"][0]
    other = _register(auth, "eve@example.com", "Eve")
    assert auth.get(f"/projects/{pid}", headers=other).status_code == 404
    assert auth.get(f"/documents/{doc['id']}", headers=other).status_code == 404
    assert auth.delete(f"/documents/{doc['id']}", headers=other).status_code == 404
    assert auth.get(f"/projects/{pid}/facts", headers=other).status_code == 404
    # viewers can read but not write
    assert auth.post(f"/projects/{pid}/members", json={"email": "eve@example.com", "role": "viewer"}).status_code == 201
    assert auth.get(f"/projects/{pid}/facts", headers=other).status_code == 200
    assert auth.post(f"/projects/{pid}/requirements", json={"title": "X"}, headers=other).status_code == 403


def test_upload_validation(auth):
    pid = auth.post("/projects", json={"name": "P"}).json()["id"]
    assert _upload(auth, pid, [("malware.exe", b"MZ")]).status_code == 400
    assert _upload(auth, pid, [("fake.pdf", b"this is not a pdf")]).status_code == 400
    r = _upload(auth, pid, [("ok.txt", b"The app must support search."), ("bad.zip", b"PK")])
    assert r.status_code == 201 and len(r.json()["documents"]) == 1 and len(r.json()["errors"]) == 1
    r = _upload(auth, pid, [("../../evil.md", b"Budget: $10")])
    assert r.json()["documents"][0]["filename"] == "evil.md"
    assert _upload(auth, pid, [("empty.txt", b"")]).status_code == 400


def test_full_demo_workflow(auth):
    pid = auth.post("/demo/load?autopilot=false").json()["id"]
    docs = auth.get(f"/projects/{pid}/documents").json()
    assert len(docs) == 3 and all(d["status"] == "analyzed" and d["fact_count"] > 0 and d["is_sample"] for d in docs)
    assert {d["file_type"] for d in docs} == {"docx", "md", "pdf"}

    # contradictions are computed from the documents
    cons = {c["subject_key"]: c for c in auth.get(f"/projects/{pid}/contradictions").json()}
    deadline = cons["deadline"]
    assert deadline["category"] == "deadline_conflict" and deadline["status"] == "open"
    assert len({s["value_text"] for s in deadline["sources"]}) == 3
    assert all(s["location"] and s["statement"] for s in deadline["sources"])
    roles = cons["user role"]
    assert sorted({s["value_text"] for s in roles["sources"]}) == ["five user roles", "three user roles"]

    # every fact cites a real segment of its document
    detail = auth.get(f"/documents/{docs[0]['id']}").json()
    for f in detail["facts"]:
        assert detail["segments"][f["segment_index"]]["text"] == f["text"]

    # requirement compilation holds the contested requirement for review
    # requirements are extracted by the pipeline itself; the contested one is held for review, not guessed
    by_key = {r["subject_key"]: r for r in auth.get(f"/projects/{pid}/requirements").json()}
    assert len(by_key) == 6 and all(r["source_document_id"] for r in by_key.values())
    assert by_key["user role"]["blocked_by_contradiction_id"] == roles["id"]
    assert by_key["user role"]["expected_value"] is None
    assert auth.post(f"/projects/{pid}/requirements/compile", json={"source": "documents"}).json()["created"] == []

    assert auth.post(f"/projects/{pid}/verify").status_code == 400  # no deliverable yet
    auth.post(f"/projects/{pid}/demo/sample-deliverable")  # uploading a deliverable runs the verification engine
    reqs = {r["subject_key"]: r for r in auth.get(f"/projects/{pid}/requirements").json()}
    assert all(r["status"] != "not_checked" for r in reqs.values())
    summary = auth.post(f"/projects/{pid}/verify").json()
    assert summary["total"] == 6
    reqs = {r["subject_key"]: r for r in auth.get(f"/projects/{pid}/requirements").json()}
    assert reqs["dashboard"]["status"] == "passed" and reqs["dashboard"]["latest_validation"]["evidence"]
    assert reqs["notification"]["status"] == "failed"
    assert reqs["notification"]["latest_validation"]["evidence"][0]["polarity"] == "contradicts"
    assert reqs["qa test plan"]["status"] == "failed" and reqs["qa test plan"]["latest_validation"]["evidence"] == []
    assert reqs["user role"]["status"] == "needs_review"

    # resolving requires a decision by the user; nothing is assumed
    assert auth.patch(f"/contradictions/{roles['id']}/resolve", json={"status": "resolved"}).status_code == 400
    five = next(s for s in roles["sources"] if s["value_text"] == "five user roles")
    r = auth.patch(f"/contradictions/{roles['id']}/resolve", json={
        "status": "resolved", "authoritative_fact_id": five["fact_id"], "note": "Client confirmed five roles."}).json()
    assert r["status"] == "resolved" and r["resolved_by_name"] == "Ada" and r["resolved_at"]
    assert sorted(s["role"] for s in r["sources"]) == ["authoritative", "superseded", "superseded"]
    auth.post(f"/projects/{pid}/verify")
    req = next(r for r in auth.get(f"/projects/{pid}/requirements").json() if r["subject_key"] == "user role")
    assert req["status"] == "failed" and req["expected_value"] == "5"
    assert "Expected 5 but the deliverable states 3" in req["latest_validation"]["explanation"]

    # knowledge graph is built from stored records
    g = auth.get(f"/projects/{pid}/graph").json()
    types = {n["node_type"] for n in g["nodes"]}
    assert {"document", "deliverable", "fact", "topic", "requirement", "contradiction", "decision"} <= types
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source_id"] in ids and e["target_id"] in ids for e in g["edges"])

    # ripple impact: analysis changes nothing until applied
    rep = auth.post(f"/projects/{pid}/impact-analysis", json={
        "target_type": "requirement", "target_id": req["id"], "new_value": "7"}).json()
    levels = {(i["item_type"], i["level"]) for i in rep["items"]}
    assert ("document", "direct") in levels and ("requirement", "indirect") in levels and ("deliverable", "direct") in levels
    assert all(i["reason"] and i["recommended_action"] for i in rep["items"])
    assert next(r for r in auth.get(f"/projects/{pid}/requirements").json() if r["id"] == req["id"])["expected_value"] == "5"
    assert auth.post(f"/impact-reports/{rep['id']}/apply").json()["status"] == "applied"
    assert auth.post(f"/impact-reports/{rep['id']}/apply").status_code == 400
    changed = next(r for r in auth.get(f"/projects/{pid}/requirements").json() if r["id"] == req["id"])
    assert changed["expected_value"] == "7" and changed["status"] == "not_checked" and "7" in changed["description"]

    # tasks: suggestions need approval
    tasks = auth.get(f"/projects/{pid}/tasks").json()
    assert tasks and all(t["status"] == "suggested" for t in tasks)
    assert {"contradiction", "failed_check", "impact"} <= {t["origin"] for t in tasks}
    t = auth.patch(f"/tasks/{tasks[0]['id']}", json={"status": "active"}).json()
    assert t["status"] == "active"
    assert auth.patch(f"/tasks/{t['id']}", json={"status": "completed"}).json()["completed_at"]

    # timeline distinguishes statement / disagreement / confirmed change / superseded
    kinds = {e["kind"] for e in auth.get(f"/projects/{pid}/timeline").json()}
    assert {"statement", "disagreement", "confirmed_change", "superseded"} <= kinds

    ov = auth.get(f"/projects/{pid}/overview").json()
    assert ov["metrics"]["documents_analyzed"] == 3 and ov["metrics"]["open_contradictions"] == 2
    assert ov["health"]["score"] is not None

    ans = auth.post(f"/projects/{pid}/ask", json={"question": "What is the current project deadline?"}).json()
    assert "disagree" in ans["answer"] and len(ans["citations"]) == 3 and ans["uncertainty"]
    assert auth.post(f"/projects/{pid}/ask", json={"question": "zebra spaceship"}).json()["citations"] == []
    assert auth.get(f"/projects/{pid}/search", params={"q": "dashboard"}).json()["facts"]

    # reset restores a clean demo project
    new = auth.post("/demo/reset?autopilot=false").json()
    assert new["is_demo"] and len(auth.get("/projects").json()) == 1
    assert all(r["status"] == "not_checked" for r in auth.get(f"/projects/{new['id']}/requirements").json())
    assert auth.get(f"/projects/{new['id']}/tasks").json() and auth.get(f"/projects/{new['id']}/documents?kind=deliverable").json() == []


def test_text_compile_manual_review_and_crud(auth):
    pid = auth.post("/projects", json={"name": "Site"}).json()["id"]
    text = "Create a website with a login system, a dashboard, and a search feature. The design should be clean."
    created = auth.post(f"/projects/{pid}/requirements/compile", json={"source": "text", "text": text}).json()["created"]
    assert [r["code"] for r in created] == ["REQ-001", "REQ-002", "REQ-003", "REQ-004"]
    _upload(auth, pid, [("build.md", b"- Users can sign in with email.\n- The dashboard is live.\n")], kind="deliverable")
    auth.post(f"/projects/{pid}/verify")
    reqs = auth.get(f"/projects/{pid}/requirements").json()
    assert [r["status"] for r in reqs] == ["passed", "passed", "failed", "needs_review"]  # synonym match for login
    manual = reqs[3]
    assert manual["verification_method"] == "manual"
    assert auth.post(f"/requirements/{manual['id']}/review", json={"status": "passed", "note": "Reviewed with design lead."}).json()["status"] == "passed"
    auth.post(f"/projects/{pid}/verify")  # re-running keeps the human decision
    assert auth.get(f"/projects/{pid}/requirements").json()[3]["status"] == "passed"
    r = auth.patch(f"/requirements/{reqs[2]['id']}", json={"title": "Global search"}).json()
    assert r["title"] == "Global search" and r["status"] == "not_checked"
    assert auth.delete(f"/requirements/{reqs[0]['id']}").status_code == 204
    assert auth.post(f"/projects/{pid}/requirements", json={"title": "N", "verification_method": "numeric"}).status_code == 400


def test_new_document_version_detects_change_and_reopens(auth):
    pid = auth.post("/projects", json={"name": "V"}).json()["id"]
    _upload(auth, pid, [("spec.md", b"Max upload size: 10 MB\nThe app must support export."),
                        ("plan.md", b"Max upload size: 10 MB")])
    assert auth.get(f"/projects/{pid}/contradictions").json() == []
    r = _upload(auth, pid, [("spec.md", b"Max upload size: 25 MB\nThe app must support export.")])
    assert r.json()["documents"][0]["current_version"] == 2
    cons = auth.get(f"/projects/{pid}/contradictions").json()
    assert len(cons) == 1 and cons[0]["category"] == "numerical_conflict"
    reports = auth.get(f"/projects/{pid}/impact-reports").json()
    assert reports and reports[0]["previous_value"] == "10 MB" and "version 2" in reports[0]["source_of_change"]
    # identical re-upload is a no-op
    r = _upload(auth, pid, [("spec.md", b"Max upload size: 25 MB\nThe app must support export.")])
    assert r.json()["unchanged"] == ["spec.md"]
    # deleting the conflicting document closes the issue, with an audit note
    plan = next(d for d in auth.get(f"/projects/{pid}/documents").json() if d["filename"] == "plan.md")
    assert auth.delete(f"/documents/{plan['id']}").status_code == 204
    c = auth.get(f"/projects/{pid}/contradictions").json()[0]
    assert c["status"] == "resolved" and "automatically" in c["resolution_note"]


def test_failed_extraction_is_reported(auth):
    pid = auth.post("/projects", json={"name": "F"}).json()["id"]
    doc = _upload(auth, pid, [("broken.pdf", b"%PDF-1.7 truncated garbage")]).json()["documents"][0]
    d = auth.get(f"/documents/{doc['id']}").json()
    assert d["status"] == "failed" and d["error"]


def test_autopilot_runs_the_whole_pipeline(auth):
    """Upload → process → conflict + verification engines → graph → action center, with no clicks."""
    pid = auth.post("/demo/load").json()["id"]  # Autopilot is on by default
    cons = {c["subject_key"]: c for c in auth.get(f"/projects/{pid}/contradictions").json()}
    assert len(cons) == 3 and all(c["status"] == "resolved" and c["auto_resolved"] for c in cons.values())
    assert all(c["resolved_by_name"] == "OxisTrack Autopilot" and "because" in c["resolution_note"] for c in cons.values())
    chosen = {k: next(s["value_text"] for s in c["sources"] if s["role"] == "authoritative") for k, c in cons.items()}
    assert chosen == {"deadline": f"December 18, {chosen['deadline'][-4:]}", "budget": "$52,500", "user role": "five user roles"}

    reqs = {r["subject_key"]: r for r in auth.get(f"/projects/{pid}/requirements").json()}
    assert len(reqs) == 6 and reqs["user role"]["expected_value"] == "5" and not reqs["user role"]["blocked_by_contradiction_id"]

    reports = auth.get(f"/projects/{pid}/impact-reports").json()
    # the deadline was decided twice: once after the second document, again when the third changed it
    assert len(reports) == 4 and all(r["status"] == "applied" and "Autopilot" in r["source_of_change"] for r in reports)
    tasks = auth.get(f"/projects/{pid}/tasks").json()
    assert tasks and all(t["status"] == "active" and t["auto_approved"] for t in tasks)
    outdated = [t for t in tasks if t["origin"] == "impact"]
    assert len(outdated) == 2  # one per outdated document, not one per statement

    # a deliverable is verified as soon as it arrives, against the values Autopilot confirmed
    auth.post(f"/projects/{pid}/demo/sample-deliverable")
    reqs = {r["subject_key"]: r for r in auth.get(f"/projects/{pid}/requirements").json()}
    assert reqs["user role"]["status"] == "failed" and "Expected 5" in reqs["user role"]["latest_validation"]["explanation"]
    assert reqs["dashboard"]["status"] == "passed" and reqs["notification"]["status"] == "failed"
    assert any(t["origin"] == "failed_check" and t["status"] == "active" for t in auth.get(f"/projects/{pid}/tasks").json())

    # a person can overrule Autopilot, and it will not re-decide that issue
    c = cons["budget"]
    assert auth.patch(f"/contradictions/{c['id']}/resolve", json={"status": "open"}).json()["status"] == "open"
    auth.post(f"/projects/{pid}/contradictions/detect")
    again = next(x for x in auth.get(f"/projects/{pid}/contradictions").json() if x["id"] == c["id"])
    assert again["status"] == "open" and not again["auto_resolved"]

    # turning Autopilot off leaves decisions to people
    assert auth.patch(f"/projects/{pid}", json={"autopilot": False}).json()["autopilot"] is False


def test_autopilot_leaves_evenly_matched_sources_to_a_person(auth):
    pid = auth.post("/projects", json={"name": "Tie"}).json()["id"]
    _upload(auth, pid, [("a.md", b"Team size: 4"), ("b.md", b"Team size: 6")])
    c = auth.get(f"/projects/{pid}/contradictions").json()[0]
    assert c["status"] == "open" and "did not decide" in c["resolution_note"]
    assert any("could not pick" in t["description"] for t in auth.get(f"/projects/{pid}/tasks").json())


def _fake_ai(model, source_index=None, verdict="unclear", quote=None):
    """An LLMProvider whose HTTP layer is mocked: picks `source_index` and returns `verdict` for checks."""
    import json

    import httpx

    from app.services.ai import LLMProvider

    def handler(request):
        system = json.loads(request.content)["messages"][0]["content"]
        if "authoritative" in system:
            body = {"index": source_index, "reasoning": f"{model} read both statements."}
        elif "satisfies a requirement" in system:
            body = {"verdict": verdict, "segment": 0, "quote": quote, "reasoning": f"{model} checked the passage."}
        else:
            body = {"facts": [], "requirements": []}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})

    return LLMProvider("https://llm.invalid/v1", "k", model, transport=httpx.MockTransport(handler))


def _with_ais(analyst, reviewer):
    from app.services import ai

    ai.set_provider(analyst)
    ai.set_reviewer(reviewer)


def test_two_ais_break_a_tie_and_disagreement_goes_to_a_person(auth):
    from app.services import ai

    try:
        _with_ais(_fake_ai("model-a", 1), _fake_ai("model-b", 1))
        pid = auth.post("/projects", json={"name": "Tie"}).json()["id"]
        _upload(auth, pid, [("a.md", b"Team size: 4"), ("b.md", b"Team size: 6")])
        c = auth.get(f"/projects/{pid}/contradictions").json()[0]
        assert c["status"] == "resolved" and c["auto_resolved"]
        assert "evenly matched" in c["resolution_note"] and "model-a" in c["resolution_note"] and "model-b" in c["resolution_note"]
        assert next(s["value_text"] for s in c["sources"] if s["role"] == "authoritative") == "6"

        _with_ais(_fake_ai("model-a", 0), _fake_ai("model-b", 1))
        pid = auth.post("/projects", json={"name": "Split"}).json()["id"]
        _upload(auth, pid, [("a.md", b"Team size: 4"), ("b.md", b"Team size: 6")])
        c = auth.get(f"/projects/{pid}/contradictions").json()[0]
        assert c["status"] == "open" and "No two of the three checks agreed" in c["resolution_note"]
    finally:
        ai.set_provider(None)
        ai.set_reviewer(None)


def test_two_ais_settle_an_unclear_check_only_with_verified_quotes(auth):
    from app.services import ai

    deliverable = b"Search is implemented for stores. Search is not available offline."
    try:
        quote = "Search is implemented for stores."
        _with_ais(_fake_ai("model-a", verdict="satisfied", quote=quote), _fake_ai("model-b", verdict="satisfied", quote=quote))
        pid = auth.post("/projects", json={"name": "Agree"}).json()["id"]
        auth.post(f"/projects/{pid}/requirements", json={"title": "Search"})
        _upload(auth, pid, [("build.md", deliverable)], kind="deliverable")
        r = auth.get(f"/projects/{pid}/requirements").json()[0]
        assert r["status"] == "passed" and "Both AI models agreed" in r["latest_validation"]["explanation"]

        # an invented quote is rejected, so the check stays with a person
        _with_ais(_fake_ai("model-a", verdict="satisfied", quote=quote), _fake_ai("model-b", verdict="satisfied", quote="Search works everywhere."))
        pid = auth.post("/projects", json={"name": "Invented"}).json()["id"]
        auth.post(f"/projects/{pid}/requirements", json={"title": "Search"})
        _upload(auth, pid, [("build.md", deliverable)], kind="deliverable")
        r = auth.get(f"/projects/{pid}/requirements").json()[0]
        assert r["status"] == "needs_review" and "stays with a person" in r["latest_validation"]["explanation"]
    finally:
        ai.set_provider(None)
        ai.set_reviewer(None)
