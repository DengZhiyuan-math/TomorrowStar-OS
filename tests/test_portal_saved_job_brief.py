"""A failed legacy P04 does not reinterpret its unchanged JD after source updates."""

import pytest
from test_application_information import answer
from test_canonical_career_sources import canonical as canonical
from test_career_portal_http import portal as portal
from test_matching_stage_recovery import terminal_model_failure
from test_normal_retrieval_pipeline import RecordedPipeline, requirement

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def test_portal_reuses_completed_jd_from_legacy_failure_after_source_change(
    canonical, portal, tmp_path
):
    _, root, _, _, _, manifest, _ = canonical
    answers = helper.Store(tmp_path / "answers")
    answers.initialize()
    _, record = answer("English fluency", "professional")
    answers.put_answer(record)
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic Research",
            "role_title": "Research Intern",
            "job_description": "Communicate in English in a research team.",
        }
    )
    initial = RecordedPipeline([requirement("Professional English")], select=False)

    def fail_evaluation(config, prompt, **kwargs):
        if config.output_schema.name == "match-schema.json":
            raise terminal_model_failure("Known P04 provider failure")
        return initial(config, prompt, **kwargs)

    def server(runner):
        return create_server(
            portal.applications,
            portal.career,
            flow_root=tmp_path / "flow",
            career_library_manifest=manifest,
            information_library_root=answers.root,
            flow_match_runner=runner,
            write_admission_policy="development",
        )

    first = server(fail_evaluation)
    try:
        task = first.application_flow_service.create(job["id"], job["revision"])
        with pytest.raises(PortalDataError):
            # The retained native API generates an actual pre-M3 archive without
            # creating an immutable Analysis request envelope.
            flow = first.application_flow_service
            analyze_job(
                flow.applications.get_application(job["id"]),
                flow._analysis_sources(),
                flow.root / "analyses" / ("a" * 32),
                runner=fail_evaluation,
                source_loader=flow.analysis.source_loader,
                information_library=flow.information_provider(),
            )
    finally:
        first.server_close()
    assert len(initial.brief_calls) == 1
    assert not (tmp_path / "flow/analyses/requests").exists()
    # Reproduce the legacy retained attempt, whose P02 exists without the newer checkpoint.
    for progress in (tmp_path / "flow/analyses").glob("*/analysis-progress.json"):
        progress.unlink()
    before = {
        p.relative_to(tmp_path / "flow/analyses"): p.read_bytes()
        for p in (tmp_path / "flow/analyses").rglob("*")
        if p.is_file()
    }
    ExperienceStore(root).save(
        "new-user-record", title="Unrelated saved fact", body="A later documentary fact."
    )
    retry = RecordedPipeline(initial.requirements, select=False)
    second = server(retry)
    try:
        flow = second.application_flow_service
        current = flow.create(job["id"], job["revision"])
        assert current["inputs"]["sources_revision"] != task["inputs"]["sources_revision"]
        result = flow.callbacks["analysis"](current)
        assert result["job_brief"]["revision"]
        assert retry.brief_calls == []
        assert retry.read_calls == []
        assert retry.phases == ["plan", "evaluate"]
        assert all(
            (flow.root / "analyses" / path).read_bytes() == raw for path, raw in before.items()
        )
        receipts = list((flow.root / "analyses").glob("*/job-brief-reuse.json"))
        assert len(receipts) == 1
    finally:
        second.server_close()
