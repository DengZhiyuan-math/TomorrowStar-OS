"""Explicit analysis retries retain immutable attempt lineage across reopening."""

from copy import deepcopy

import pytest
from test_application_flow import wait_for
from test_canonical_career_sources import canonical as canonical

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def test_explicit_analysis_retry_reopens_with_failed_attempt_and_original_binding(tmp_path):
    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    applications = ApplicationStore(applications_root)
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Python Engineer",
            "job_description": "Build reliable Python systems.",
        }
    )
    requests = []

    def analyze(task):
        requests.append(deepcopy(task))
        if len(requests) == 1:
            raise PortalDataError("match_model_invalid", "Synthetic P04 output failed")
        return {"id": "completed-analysis"}

    flow_root = tmp_path / "flow"
    flow = ApplicationFlowService(applications, flow_root, callbacks={"analysis": analyze})
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        failed = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
    finally:
        flow.close()
    failed_attempt = failed["stages"]["analysis"]["attempt_id"]
    reopened = ApplicationFlowService(applications, flow_root, callbacks={"analysis": analyze})
    try:
        observed = reopened.snapshot(task["id"])["active_task"]
        assert len(requests) == 1
        reopened.start(task["id"], observed["revision"], "analysis", retry=True)
        completed = wait_for(reopened, task["id"], lambda row: row["status"] == "analysis_ready")
        assert len(requests) == 2
        assert requests[1]["stages"]["analysis"]["resume_from_attempt_id"] == failed_attempt
        assert requests[1]["stages"]["analysis"]["attempt_id"] != failed_attempt
        assert completed["analysis_attempts"] == [
            {
                "stage": failed["stages"]["analysis"],
                "inputs": failed["inputs"],
                "job_binding": failed["job_binding"],
            }
        ]
        assert completed["analysis_id"] == "completed-analysis"
    finally:
        reopened.close()


def test_portal_explicit_retry_passes_prior_attempt_directory_to_supported_analyzer(tmp_path):
    import json
    import subprocess

    from career_evidence_graph.application_flow import job_input_revision
    from career_evidence_graph.application_match import match_configuration_revision
    from career_evidence_graph.career_portal import create_server

    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    applications = ApplicationStore(applications_root)
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Engineer",
            "job_description": "Build Python systems.",
        }
    )
    career_root = tmp_path / "career"
    career_root.mkdir()
    subprocess.run(["git", "init", "--quiet", str(career_root)], check=True)
    (career_root / "sources").mkdir()
    (career_root / "sources" / "profile.json").write_text(json.dumps({"name": "Synthetic Person"}))
    calls = []

    def analyzer(application, sources, directory, *, resume_from=None):
        calls.append((directory, resume_from))
        directory.mkdir(parents=True)
        (directory / "retained-evidence.json").write_text('{"status":"retained"}')
        if len(calls) == 1:
            raise PortalDataError("match_model_invalid", "Synthetic P04 failure")
        return {
            "id": directory.name,
            "application_id": application["id"],
            "application_revision": application["revision"],
            "jd_revision": job_input_revision(application),
            "input_source_snapshot_revision": sources["revision"],
            "source_snapshot_revision": sources["revision"],
            "configuration_revision": match_configuration_revision(),
        }

    with create_server(
        applications_root,
        career_root,
        flow_root=tmp_path / "flow",
        flow_analyzer=analyzer,
    ) as server:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        failed = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        prior_directory = calls[0][0]
        original_evidence = (prior_directory / "retained-evidence.json").read_bytes()
        flow.start(task["id"], failed["revision"], "analysis", retry=True)
        complete = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        assert calls[0][1] is None
        assert calls[1][1] == prior_directory
        assert prior_directory.name == failed["stages"]["analysis"]["attempt_id"]
        assert calls[1][0].name == complete["stages"]["analysis"]["attempt_id"]
        assert calls[1][0] != prior_directory
        assert (prior_directory / "retained-evidence.json").read_bytes() == original_evidence


def test_default_portal_cold_retry_preserves_successful_jd_and_material_reads(canonical, tmp_path):
    import json
    import subprocess

    from test_application_match import model_runner
    from test_matching_stage_recovery import terminal_model_failure
    from test_normal_retrieval_pipeline import RecordedPipeline, requirement
    from test_structured_career_store import facts

    from career_evidence_graph.career_experiences import ExperienceStore
    from career_evidence_graph.career_portal import create_server

    _, career_root, _, _, _, manifest, _ = canonical
    subprocess.run(["git", "init", "--quiet", str(career_root)], check=True)
    content = facts(candidate_id="unseen-identity")
    content["facts"][0]["text"] = "Studied cross-domain models with biology collaborators."
    content["facts"].append(
        deepcopy(content["facts"][0])
        | {"id": "fact-2", "text": "Unrelated recorded detail. " * 2800}
    )
    ExperienceStore(career_root).save("unseen-identity", title=content["title"], content=content)
    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    applications = ApplicationStore(applications_root)
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Research Engineer",
            "job_description": "Collaborate across scientific domains.",
        }
    )

    class FailFirstEvaluation(RecordedPipeline):
        evaluation_attempts = 0

        def __call__(self, config, prompt, **kwargs):
            schema = json.loads(config.output_schema.read_text())
            if set(schema.get("properties", {})) == {"selections"}:
                data = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
                self.read_calls.append(data)
                supplied = data.get("source_ranges", [data])[0]
                return model_runner(
                    {
                        "selections": [
                            {
                                "source_id": supplied["source"]["source_id"],
                                "requirement_indexes": [0],
                            }
                        ]
                    },
                    self.calls,
                )(config, prompt, **kwargs)
            if schema.get("title") in {"_ModelOutput", "_ControlledOutput"}:
                self.evaluation_attempts += 1
                if self.evaluation_attempts == 1:
                    raise terminal_model_failure("Synthetic known P04 failure")
            return super().__call__(config, prompt, **kwargs)

    runner = FailFirstEvaluation([requirement("Collaborate across scientific domains")])
    options = {
        "flow_root": tmp_path / "flow",
        "career_library_manifest": manifest,
        "flow_match_runner": runner,
        "write_admission_policy": "development",
    }
    with create_server(applications_root, career_root, **options) as server:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        failed = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
        assert failed["stages"]["analysis"]["error_code"] == "match_model_unavailable"
        assert len(runner.brief_calls) == 1
        assert runner.read_calls
        read_count = len(runner.read_calls)
        assert runner.phases == ["plan"]
        original_directory = flow.root / "analyses" / failed["stages"]["analysis"]["attempt_id"]
        original_files = {
            path.relative_to(original_directory): path.read_bytes()
            for path in original_directory.rglob("*")
            if path.is_file()
        }
    with create_server(applications_root, career_root, **options) as reopened_server:
        flow = reopened_server.application_flow_service
        observed = flow.snapshot(task["id"])["active_task"]
        assert observed["stages"]["analysis"] == failed["stages"]["analysis"]
        assert runner.evaluation_attempts == 1
        flow.start(task["id"], observed["revision"], "analysis", retry=True)
        completed = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        assert completed["analysis_id"] != failed.get("analysis_id")
        assert len(runner.brief_calls) == 1
        assert len(runner.read_calls) == read_count
        assert runner.phases == ["plan", "evaluate"]
        assert runner.evaluation_attempts == 2
        assert completed["analysis_attempts"][0]["stage"] == failed["stages"]["analysis"]
        assert {
            path.relative_to(original_directory): path.read_bytes()
            for path in original_directory.rglob("*")
            if path.is_file()
        } == original_files


@pytest.mark.parametrize(
    ("configuration_field", "configuration_value", "expected_status", "change_library"),
    [
        ("engine_sha256", "new-diagnostic-app-source-hash", "complete", True),
        ("requested_model", "different-requested-model", "pending", True),
        ("engine_sha256", "metadata-only-new-app-source-hash", "complete", False),
    ],
)
def test_completed_portal_analysis_checks_semantics_after_library_and_configuration_change(
    canonical,
    tmp_path,
    monkeypatch,
    configuration_field,
    configuration_value,
    expected_status,
    change_library,
):
    import subprocess

    from test_normal_retrieval_pipeline import RecordedPipeline, requirement
    from test_structured_career_store import facts

    from career_evidence_graph import application_match
    from career_evidence_graph.career_experiences import ExperienceStore
    from career_evidence_graph.career_portal import create_server

    _, career_root, _, _, _, manifest, _ = canonical
    subprocess.run(["git", "init", "--quiet", str(career_root)], check=True)
    store = ExperienceStore(career_root)
    for identifier in ("unseen-identity", "zz-unselected"):
        content = facts(candidate_id=identifier, experience_id="experience-" + identifier)
        store.save(identifier, title=content["title"], content=content)
    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    applications = ApplicationStore(applications_root)
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Research Engineer",
            "job_description": "Validate a team model.",
        }
    )
    runner = RecordedPipeline([requirement("Validate a team model")])
    with create_server(
        applications_root,
        career_root,
        flow_root=tmp_path / "flow",
        career_library_manifest=manifest,
        flow_match_runner=runner,
        write_admission_policy="development",
    ) as server:
        flow = server.application_flow_service
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        completed = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        original = completed["artifacts"][-1]["result"]
        assert original["retrieval"]["selected_candidate_ids"] == ["unseen-identity"]
        call_count = len(runner.calls)
        if change_library:
            unselected = store.get("zz-unselected")
            updated = deepcopy(unselected["content"])
            updated["facts"][0]["text"] = "Tutored another synthetic class."
            store.save(
                "zz-unselected",
                title=updated["title"],
                content=updated,
                expected_revision=unselected["revision"],
            )
        configuration = application_match.match_configuration()
        configuration[configuration_field] = configuration_value
        monkeypatch.setattr(
            application_match, "match_configuration", lambda environment=None: configuration
        )
        refreshed = flow.update_inputs(completed["id"], completed["revision"], job["revision"])
        assert refreshed["stages"]["analysis"]["status"] == expected_status
        if expected_status == "complete":
            assert refreshed["analysis_id"]
            adopted = refreshed["artifacts"][-1]["result"]
            if change_library:
                assert adopted["reused_from"]["model_called"] is False
            else:
                assert refreshed["analysis_id"] == completed["analysis_id"]
                assert refreshed["artifacts"] == completed["artifacts"]
            assert adopted["requirements"] == original["requirements"]
        else:
            assert refreshed["analysis_id"] is None
            assert refreshed["artifacts"] == completed["artifacts"]
        assert len(runner.calls) == call_count
        assert len(runner.brief_calls) == 1
        assert runner.phases == ["plan", "evaluate"]
