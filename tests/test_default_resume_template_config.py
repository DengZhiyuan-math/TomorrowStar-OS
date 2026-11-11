"""Explicit template selection works independently of the standalone review UI."""

import ast
import json
from pathlib import Path

import pytest
from test_career_portal_http import portal as portal
from test_json_resume_template_content import TEMPLATE

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import PortalDataError


def test_default_automatic_flow_uses_selected_template_without_review_ui(portal, tmp_path):
    project = tmp_path / "selected-template"
    project.mkdir()
    main = project / "main.tex"
    main.write_text(TEMPLATE)
    config = tmp_path / "resume-review.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    server = create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "automatic-flow",
        resume_template_config=config,
        write_admission_policy="development",
    )
    try:
        provider = server.application_flow_service.callbacks["automatic_latex_base"]
        selected = provider({"id": "1" * 32, "material_contract": "content-writing/v1"})
        assert selected == source_snapshot(project, "main.tex")
        assert server.resume_review_store is None
        assert main.read_text() == TEMPLATE
        assert json.loads(config.read_text()) == {
            "project_root": str(project),
            "main": "main.tex",
        }
        assert set(project.iterdir()) == {main}
    finally:
        server.application_flow_service.close()
        server.server_close()


@pytest.mark.parametrize("preparation_only", [False, True])
@pytest.mark.parametrize("synthetic", [False, True])
def test_native_template_config_is_independent_of_mode_and_disabled_for_synthetic(
    preparation_only, synthetic
):
    source = Path(__file__).parents[1] / "macos/server.py"
    call = next(
        node
        for node in ast.walk(ast.parse(source.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_server"
    )
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    assert "resume_template_config" in keywords
    support = Path("/private/tmp/synthetic-support")
    result = eval(
        compile(ast.Expression(keywords["resume_template_config"]), str(source), "eval"),
        {
            "support": support,
            "preparation_only": preparation_only,
            "synthetic_root": support / "synthetic" if synthetic else None,
        },
    )
    assert result == (None if synthetic else support / "resume-review.json")


@pytest.mark.parametrize("damage", ["invalid-json", "extra-field", "missing-slots", "symlink"])
def test_explicit_bad_template_is_visible_instead_of_silent_fallback(portal, tmp_path, damage):
    project = tmp_path / "selected-template"
    project.mkdir()
    main = project / "main.tex"
    main.write_text(TEMPLATE if damage != "missing-slots" else "Not a template")
    config = tmp_path / "resume-review.json"
    fields = {"project_root": str(project), "main": "main.tex"}
    if damage == "extra-field":
        fields["ignored"] = "not allowed"
    config.write_text("{" if damage == "invalid-json" else json.dumps(fields))
    if damage == "symlink":
        real = tmp_path / "real-config.json"
        config.rename(real)
        config.symlink_to(real)
    before = main.read_bytes()
    server = create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "automatic-flow",
        resume_template_config=config,
        write_admission_policy="development",
    )
    try:
        provider = server.application_flow_service.callbacks["automatic_latex_base"]
        with pytest.raises(PortalDataError) as caught:
            provider({"id": "1" * 32, "material_contract": "content-writing/v1"})
        assert caught.value.code == "resume_template_invalid"
        assert main.read_bytes() == before
    finally:
        server.application_flow_service.close()
        server.server_close()


def test_missing_template_config_preserves_unconfigured_fallback(portal, tmp_path):
    config = tmp_path / "not-configured.json"
    server = create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "automatic-flow",
        resume_template_config=config,
        write_admission_policy="development",
    )
    try:
        provider = server.application_flow_service.callbacks["automatic_latex_base"]
        assert provider({"id": "1" * 32, "material_contract": "content-writing/v1"}) is None
        assert not config.exists()
    finally:
        server.application_flow_service.close()
        server.server_close()
