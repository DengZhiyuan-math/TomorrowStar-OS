"""Retired HTML resume entrypoints cannot call models, renderers or write artifacts."""

import pytest

from career_evidence_graph.application_resume import ApplicationResumeStore, render_resume
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("method", ["generate", "_run", "_generate"])
def test_legacy_generation_entrypoints_are_gone_without_initializing_services(method, tmp_path):
    store = ApplicationResumeStore.__new__(ApplicationResumeStore)
    with pytest.raises(PortalDataError) as failure:
        getattr(store, method)("historical-id", "historical-revision")
    assert failure.value.code == "resume_html_retired"
    assert failure.value.status == 410
    assert list(tmp_path.iterdir()) == []


def test_html_renderer_is_retired_even_for_unvalidated_input():
    with pytest.raises(PortalDataError) as failure:
        render_resume({})
    assert failure.value.code == "resume_html_retired"
    assert failure.value.status == 410


def test_task_generation_requires_a_latex_template_before_accessing_services():
    store = ApplicationResumeStore.__new__(ApplicationResumeStore)
    with pytest.raises(PortalDataError) as failure:
        store.generate_for_task("id", "revision", source_snapshot={}, analysis={})
    assert failure.value.code == "resume_latex_required"
    assert failure.value.status == 410


def test_export_without_latex_cannot_access_a_draft_or_render():
    store = ApplicationResumeStore.__new__(ApplicationResumeStore)
    with pytest.raises(PortalDataError) as failure:
        store.export_for_draft("historical", "hash", task_inputs={}, export_id="1" * 32)
    assert failure.value.code == "resume_html_retired"
    assert failure.value.status == 410


def test_historical_html_checkpoint_cannot_be_relabelled_as_a_latex_export():
    store = ApplicationResumeStore.__new__(ApplicationResumeStore)
    store._current_export_draft = lambda *_: {"origin": "legacy_html"}
    with pytest.raises(PortalDataError) as failure:
        store.export_for_draft(
            "historical",
            "hash",
            task_inputs={},
            export_id="1" * 32,
            prism={"project_root": "/unreadable-historical-source"},
        )
    assert failure.value.code == "resume_html_retired"
    assert failure.value.status == 410
