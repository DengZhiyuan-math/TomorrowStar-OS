"""New jobs use compact LaTeX copies; the retired HTML endpoint is absent."""

import json
from pathlib import Path

from test_career_portal_http import portal as portal
from test_resume_template import EDUCATION, PREFIX, SUFFIX

from career_evidence_graph.career_portal import create_server


def test_default_template_callback_uses_private_copy(portal, tmp_path):
    project = tmp_path / "template-base"
    project.mkdir()
    main = project / "main.tex"
    original = PREFIX + EDUCATION + SUFFIX
    main.write_text(original)
    config = tmp_path / "review.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    server = create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        resume_review_root=tmp_path / "review",
        resume_review_config=config,
        write_admission_policy="development",
    )
    try:
        provider = server.application_flow_service.callbacks["automatic_latex_base"]
        first = provider({"id": "1" * 32})
        second = provider({"id": "2" * 32})
        assert first["project_root"] != second["project_root"] != str(project)
        derived = (Path(first["project_root"]) / first["main"]).read_text()
        assert "Scholarship: Synthetic Award" in derived
        assert derived.endswith(SUFFIX)
        assert main.read_text() == original
        assert provider({"id": "1" * 32}) == first
    finally:
        server.application_flow_service.close()
        server.server_close()


def test_retired_html_generation_route_is_not_exposed(portal):
    status, _, _ = portal.request(
        "POST", "/api/resumes/generate", body=b"{}", headers=portal.write_headers()
    )
    assert status == 404
