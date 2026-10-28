"""Registration denial stops the production exporter before any browser activity."""

from unittest.mock import Mock

import pytest
from test_application_resume import task_resume as task_resume

from career_evidence_graph.application_resume import export_pdf
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("reason", ["denied", "unknown"])
def test_registration_failure_preserves_existing_pdf_without_playwright(
    tmp_path, monkeypatch, reason
):
    from playwright import sync_api

    from career_evidence_graph import chrome_registration

    source, destination = tmp_path / "synthetic.html", tmp_path / "synthetic.pdf"
    source.write_text("<p>Synthetic data only.</p>")
    original = b"%PDF-1.4\nPrevious synthetic original"
    destination.write_bytes(original)
    destination.chmod(0o640)
    query = Mock(
        side_effect=RuntimeError(f"macos_chrome_registration_{reason}: private synthetic detail")
    )
    monkeypatch.setattr(chrome_registration, "check_chrome_launch_environment", query)
    start = Mock(side_effect=AssertionError("No Playwright or Chrome may start"))
    monkeypatch.setattr(sync_api, "sync_playwright", start)
    with pytest.raises(PortalDataError) as failure:
        export_pdf(source, destination)
    assert failure.value.code == f"resume_chrome_registration_{reason}"
    assert "private synthetic detail" not in str(failure.value)
    assert destination.read_bytes() == original
    assert destination.stat().st_mode & 0o777 == 0o640
    query.assert_called_once_with()
    start.assert_not_called()


@pytest.mark.parametrize("builtin", [True, False])
def test_export_configuration_binds_only_builtin_registration_engine(
    task_resume, monkeypatch, builtin
):
    from career_evidence_graph import chrome_registration

    store, *_ = task_resume
    if builtin:
        store.exporter = export_pdf
    query = Mock(side_effect=AssertionError("Configuration must not query the current environment"))
    monkeypatch.setattr(chrome_registration, "check_chrome_launch_environment", query)
    monkeypatch.setattr(chrome_registration, "ENGINE_SHA256", "a" * 64, raising=False)
    original = store.export_configuration()
    before = store.export_configuration_revision()
    monkeypatch.setattr(chrome_registration, "ENGINE_SHA256", "b" * 64)
    changed = store.export_configuration()
    after = store.export_configuration_revision()
    if builtin:
        assert original["renderer"].get("registration_engine_sha256") == "a" * 64
        assert changed["renderer"].get("registration_engine_sha256") == "b" * 64
        assert before != after
    else:
        assert "registration_engine_sha256" not in original["renderer"]
        assert original == changed and before == after
    query.assert_not_called()
