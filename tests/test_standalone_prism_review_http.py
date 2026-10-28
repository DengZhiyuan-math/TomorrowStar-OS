"""Independent résumé review uses local snapshots, without an application task."""

import json

import pytest
from test_career_portal_http import portal as portal


def test_standalone_review_is_disabled_without_explicit_configuration(portal):
    status, _, raw = portal.request("GET", "/api/resume-review/state")
    assert status == 200, raw
    assert json.loads(raw) == {"enabled": False}


def test_readback_serves_one_immutable_latex_pdf_version_without_job_task(
    portal, tmp_path, monkeypatch
):
    from threading import Thread

    from test_application_prism import compiling_editor
    from test_career_portal_http import Portal

    from career_evidence_graph.career_portal import create_server

    project = tmp_path / "dedicated-cv"
    project.mkdir()
    text = r"\documentclass{article}\begin{document}Synthetic CV\end{document}"
    (project / "main.tex").write_text(text)
    config = tmp_path / "resume-review.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    with compiling_editor(project, monkeypatch) as calls:
        server = create_server(
            portal.applications,
            portal.career,
            flow_root=tmp_path / "preparation",
            preparation_only=True,
            resume_review_root=tmp_path / "review-snapshots",
            resume_review_config=config,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        active = Portal(server, portal.applications, portal.career)
        try:
            status, _, raw = active.request("GET", "/api/resume-review/state")
            assert status == 200, raw
            initial = json.loads(raw)
            assert initial["enabled"] is True and initial["latest"] is None
            assert not [call for call in calls if call[0] == "POST"]
            status, _, raw = active.request(
                "POST",
                "/api/resume-review/capture",
                body=json.dumps({"source_revision": initial["live_source_revision"]}).encode(),
                headers=active.write_headers(),
            )
            assert status == 200, raw
            state = json.loads(raw)
            version = state["latest"]
            assert version["review_status"] == "pending_human_review"
            assert len(version["source_revision"]) == len(version["pdf_sha256"]) == 64
            assert (
                active.request("GET", f"/api/resume-review/versions/{version['id']}/source")[2]
                == text.encode()
            )
            status, headers, pdf = active.request(
                "GET", f"/api/resume-review/versions/{version['id']}/pdf"
            )
            assert status == 200 and pdf.startswith(b"%PDF-")
            assert headers["Content-Type"] == "application/pdf"
            (project / "main.tex").write_text(text.replace("Synthetic CV", "Edited CV"))
            status, _, raw = active.request("GET", "/api/resume-review/state")
            changed = json.loads(raw)
            assert changed["source_changed"] is True
            assert changed["latest"]["id"] == version["id"]
            assert (
                active.request("GET", f"/api/resume-review/versions/{version['id']}/source")[2]
                == text.encode()
            )
            status, _, raw = active.request("GET", "/api/flow/state")
            flow = json.loads(raw)
            assert flow["tasks"] == [] and flow["capabilities"]["worker"] is False
            assert len([call for call in calls if call[0] == "POST"]) == 1
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


@pytest.fixture
def review_portal(portal, tmp_path, monkeypatch):
    from threading import Thread

    from test_application_prism import compiling_editor
    from test_career_portal_http import Portal

    from career_evidence_graph.career_portal import create_server

    project = tmp_path / "review-project"
    project.mkdir()
    (project / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Synthetic first version\end{document}"
    )
    config = tmp_path / "resume-review.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    with compiling_editor(project, monkeypatch) as calls:
        server = create_server(
            portal.applications,
            portal.career,
            flow_root=tmp_path / "preparation",
            preparation_only=True,
            resume_review_root=tmp_path / "review-snapshots",
            resume_review_config=config,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield Portal(server, portal.applications, portal.career), project, calls
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


def test_capture_requires_same_origin_csrf_and_explicit_source_version(review_portal):
    active, _, calls = review_portal
    assert active.request("POST", "/api/resume-review/capture", body=b"{}")[0] == 403
    status, _, _ = active.request(
        "POST", "/api/resume-review/capture", body=b"{}", headers=active.write_headers()
    )
    assert status == 400
    assert not [call for call in calls if call[0] == "POST"]
