"""Normal materials preparation binds an explicitly imported, mapped human baseline."""

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_imported_content_mapping import import_mapped
from test_imported_content_mapping import mapped_import as mapped_import

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def test_material_preparation_binds_mapped_import_without_inventing_generation(
    mapped_import, tmp_path
):
    store, job, _project, mapping = mapped_import
    imported = import_mapped(mapped_import)
    template = tmp_path / "fixed-template"
    template.mkdir()
    (template / "main.tex").write_text(mapping["template"])
    flow = ApplicationFlowService(
        store.applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: {"id": "known-analysis", "requirements": []},
            "prism_source": source_snapshot,
            "retained_draft": store.retained_career_draft,
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda t: t["status"] == "analysis_ready")
        prepared = flow.prepare_automatic_materials(
            task["id"],
            task["revision"],
            template,
            "main.tex",
            retained_draft_id=imported["id"],
            retained_draft_sha256=imported["draft_sha256"],
        )
        assert prepared["retained_baseline"] == {
            "id": imported["id"],
            "draft_sha256": imported["draft_sha256"],
        }
        assert store.retained_career_draft(prepared)["resume_content"] == mapping["content"]
        assert prepared["artifacts"] == task["artifacts"]
        assert store.draft(imported["id"])["origin"] == "existing_latex"
        repeated = flow.prepare_automatic_materials(
            prepared["id"],
            prepared["revision"],
            template,
            "main.tex",
            retained_draft_id=imported["id"],
            retained_draft_sha256=imported["draft_sha256"],
        )
        assert repeated == prepared
    finally:
        flow.close()


def test_wrong_mapping_template_cannot_bind_or_replace_prior_baseline(mapped_import, tmp_path):
    store, job, _project, mapping = mapped_import
    imported = import_mapped(mapped_import)
    template = tmp_path / "changed-template"
    template.mkdir()
    (template / "main.tex").write_text(mapping["template"] + "% Changed fixed template\n")
    flow = ApplicationFlowService(
        store.applications,
        tmp_path / "flow",
        callbacks={
            "analysis": lambda task: {"id": "known-analysis", "requirements": []},
            "prism_source": source_snapshot,
            "retained_draft": store.retained_career_draft,
        },
    )
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda t: t["status"] == "analysis_ready")
        before = (flow.root / "flow.json").read_bytes()
        with pytest.raises(PortalDataError):
            flow.prepare_automatic_materials(
                task["id"],
                task["revision"],
                template,
                "main.tex",
                retained_draft_id=imported["id"],
                retained_draft_sha256=imported["draft_sha256"],
            )
        assert (flow.root / "flow.json").read_bytes() == before
    finally:
        flow.close()
