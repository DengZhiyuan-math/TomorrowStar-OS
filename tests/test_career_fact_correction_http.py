"""Explicit career corrections update documentary facts and preserve original bytes."""

import json

import pytest
from test_career_portal_http import portal as portal


def test_explicit_career_fact_correction_saves_history_without_research_approval(portal):
    sources = portal.career / "sources"
    sources.mkdir()
    path = sources / "project.md"
    original = b"# Synthetic project\n\nImplemented the parser.\n"
    path.write_bytes(original)
    identifier = portal.state()["evidence"][0]["id"]
    status, _, raw = portal.request("GET", "/api/evidence/" + identifier)
    assert status == 200
    detail = json.loads(raw)
    corrected = "# Synthetic project\n\nImplemented the parser and its validation.\n"
    status, _, raw = portal.request(
        "PATCH",
        "/api/evidence/" + identifier,
        body=json.dumps(
            {
                "revision": detail["revision"],
                "content": corrected,
                "source": "Explicit correction by the project owner",
            }
        ).encode(),
        headers=portal.write_headers(),
    )
    assert status == 200, raw
    saved = json.loads(raw)
    assert saved["content"] == corrected and path.read_text() == corrected
    assert saved["revision"] != detail["revision"]
    assert len(saved["history"]) == 1
    change = saved["history"][0]
    assert change["before_revision"] == detail["revision"]
    assert change["after_revision"] == saved["revision"]
    assert change["source"] == "Explicit correction by the project owner"
    assert change["actor"] == "user" and change["status"] == "applied"
    assert (portal.career / change["backup"]).read_bytes() == original
    assert not (portal.career / ".planning").exists()


@pytest.mark.parametrize("failure", ["csrf", "stale", "research_record", "extra_fields"])
def test_career_correction_rejects_invalid_write_without_changing_documents(portal, failure):
    folder = portal.career / ("reports" if failure == "research_record" else "sources")
    folder.mkdir()
    path = folder / "project.md"
    original = b"# Original project\n\nOriginal documentary facts.\n"
    path.write_bytes(original)
    identifier = portal.state()["evidence"][0]["id"]
    _, _, raw = portal.request("GET", "/api/evidence/" + identifier)
    detail = json.loads(raw)
    payload = {"revision": detail["revision"], "content": "# Corrected project\n"}
    headers = portal.write_headers()
    expected = 409
    if failure == "csrf":
        headers.pop("X-CSRF-Token")
        expected = 403
    elif failure == "stale":
        payload["revision"] = "stale-revision"
    elif failure == "extra_fields":
        payload["actor"] = "research-reviewer"
        expected = 400
    status, _, _ = portal.request(
        "PATCH",
        "/api/evidence/" + identifier,
        body=json.dumps(payload).encode(),
        headers=headers,
    )
    assert status == expected
    assert path.read_bytes() == original
    assert not (portal.career / ".tomorrowstar-career-history").exists()


def test_failed_career_document_replace_preserves_original_and_pending_history(portal, monkeypatch):
    from career_evidence_graph import career_portal_data

    sources = portal.career / "sources"
    sources.mkdir()
    path = sources / "project.md"
    original = b"# Original project\n"
    path.write_bytes(original)
    identifier = portal.state()["evidence"][0]["id"]
    _, _, raw = portal.request("GET", "/api/evidence/" + identifier)
    detail = json.loads(raw)
    write = career_portal_data._write_file

    def fail_current_document(destination, content, *, replace):
        if destination == path and replace:
            raise OSError("Synthetic atomic replacement failed")
        return write(destination, content, replace=replace)

    monkeypatch.setattr(career_portal_data, "_write_file", fail_current_document)
    status, _, raw = portal.request(
        "PATCH",
        "/api/evidence/" + identifier,
        body=json.dumps(
            {"revision": detail["revision"], "content": "# Updated project\n"}
        ).encode(),
        headers=portal.write_headers(),
    )
    assert status == 500 and json.loads(raw)["error"] == "career_save_failed"
    assert path.read_bytes() == original
    _, _, raw = portal.request("GET", "/api/evidence/" + identifier)
    current = json.loads(raw)
    assert current["revision"] == detail["revision"]
    assert len(current["history"]) == 1
    assert current["history"][0]["status"] == "needs_recheck"
    assert (portal.career / current["history"][0]["backup"]).read_bytes() == original
