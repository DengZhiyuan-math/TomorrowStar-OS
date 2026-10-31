"""Contact corrections keep analysis and materials; an explicit sync adopts them (APP-04)."""

from copy import deepcopy

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_information import applicable_answers, put_information_answer
from career_evidence_graph.application_worker import fact_for
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
@pytest.mark.parametrize(
    "question,value",
    [
        ("Email", "updated@example.invalid"),
        ("Full name", "Corrected Synthetic Name"),
        ("Phone", "+41 44 555 0100"),
    ],
)
def test_contact_correction_keeps_completed_analysis_and_old_material_history(
    complete_portal, question, value
):
    server, store, original, generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    original_artifacts = deepcopy(original["artifacts"])
    original_pdf = store.pdf(original["resume_id"])
    put_information_answer(
        worker.store.answers,
        {
            "question": question,
            "value": value,
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        },
    )
    job = store.applications.get_application(original["application_id"])
    task = flow.request(
        "update-inputs",
        {
            "task_id": original["id"],
            "task_revision": original["revision"],
            "application_revision": job["revision"],
        },
    )
    assert task["analysis_id"] == original["analysis_id"]
    assert task["stages"]["analysis"] == original["stages"]["analysis"]
    assert task["status"] == "analysis_ready"
    assert task["artifacts"] == original_artifacts
    assert task["resume_id"] is None and task["draft_id"] is None
    assert store.pdf(original["resume_id"]) == original_pdf
    assert len(generation) == len(store.prism_client.calls) == 1


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_correction_updates_current_header_then_binds_worker_without_reanalysis(
    complete_portal, full_latex
):
    server, store, original, generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    old_source = store.draft(original["draft_id"])["latex_source"]
    old_pdf = store.pdf(original["resume_id"])
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        },
    )
    job = store.applications.get_application(original["application_id"])
    task = flow.update_inputs(original["id"], original["revision"], job["revision"])
    full_latex[6]["groups"][0]["latex"] = "Synthetic Person\nupdated@example.invalid\n"
    task = flow.prepare_automatic_materials(task["id"], task["revision"])
    flow.start(task["id"], task["revision"], "resume")
    task = wait_for(flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
    assert task["status"] == "draft_ready", task
    flow.start(task["id"], task["revision"], "export")
    task = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert task["status"] == "materials_ready", task
    prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    assert prepared["analysis_id"] == original["analysis_id"]
    worker_state = worker.store.load()
    worker.store.check_single(worker_state["jobs"][0], worker_state)
    assert "updated@example.invalid" in store.read_export(task["resume_id"])["latex_source"]
    assert "job@example.invalid" not in store.read_export(task["resume_id"])["latex_source"]
    assert store.draft(original["draft_id"])["latex_source"] == old_source
    assert store.pdf(original["resume_id"]) == old_pdf
    assert (
        len([artifact for artifact in prepared["artifacts"] if artifact["stage"] == "analysis"])
        == 1
    )
    assert len(generation) == 1
    assert len(store.prism_client.calls) == 2


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
@pytest.mark.parametrize(
    "question,value",
    [
        ("German level", "B2"),
        ("French level", "C1"),
        ("Are you currently authorized to work in this country", "Yes"),
        ("Will you now or in the future require visa sponsorship", "No"),
    ],
)
def test_important_qualification_changes_recheck_only_the_applicable_job(
    complete_portal, question, value
):
    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    job = store.applications.get_application(original["application_id"])
    other = store.applications.create_application(
        {
            "company": "Other Synthetic Employer",
            "role_title": job["role_title"],
            "location": "Boston, USA",
            "url": "https://jobs.lever.co/other/12345678-1234-1234-1234-123456789013",
            "job_description": job["job_description"],
        }
    )
    untouched = flow.create(other["id"], other["revision"])
    flow.start(untouched["id"], untouched["revision"], "analysis")
    untouched = wait_for(flow, untouched["id"], lambda row: row["status"] == "analysis_ready")
    put_information_answer(
        worker.store.answers,
        {
            "question": question,
            "value": value,
            "state": "confirmed",
            "scope": {"application_id": job["id"]},
        },
    )
    current = flow.update_inputs(original["id"], original["revision"], job["revision"])
    assert current["analysis_id"] == original["analysis_id"]
    assert current["resume_id"] == original["resume_id"]
    assert current["inputs"] == original["inputs"]
    prepared = flow.prepare_worker(current["id"], current["revision"], "CHE", True)
    state = worker.store.load()
    worker.store.check_single(state["jobs"][0], state)
    assert prepared["resume_id"] == original["resume_id"]
    actual_question = {"id": "qualification", "question": question}
    assert worker.store.resolve(actual_question, state["jobs"][0])[0] == value
    other_context = {
        **state["jobs"][0],
        "application_id": other["id"],
        "country": "USA",
        "company": other["company"],
    }
    # A bound task cannot be relabelled as another job to select its information
    # store. Verify that gate, then check scope against the genuine selected store.
    with pytest.raises(PortalDataError) as error:
        worker.store.resolve(actual_question, other_context)
    assert error.value.code == "single_information_invalid"
    assert (
        applicable_answers(
            worker.store.library(state["jobs"][0]), fact_for(question), other_context
        )
        == []
    )
    assert current["artifacts"] == original["artifacts"]
    assert (
        flow.update_inputs(untouched["id"], untouched["revision"], other["revision"])["analysis_id"]
        == untouched["analysis_id"]
    )


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_change_explanation_keeps_analysis_and_materials_current(complete_portal):
    server, _store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        },
    )
    from career_evidence_graph.application_explanations import job_explanation

    job = flow.applications.get_application(original["application_id"])
    explanation = job_explanation(
        job, original, current_inputs=flow.input_provider(job["id"])["inputs"]
    )
    # APP-04: a contact correction never stales the analysis or the final materials.
    assert explanation["fresh"] is True
    assert explanation["materials_fresh"] is True
    assert explanation["progress"]["status"] == original["status"]
    assert explanation["input_binding"]["analysis_id"] == original["analysis_id"]


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_update_cannot_clear_unknown_export_attempt(complete_portal):
    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service

    def unknown_export(_task):
        raise OSError("Synthetic compiler response lost")

    flow.callbacks["export"] = unknown_export
    flow.start(original["id"], original["revision"], "export", retry=True)
    unknown = wait_for(flow, original["id"], lambda row: row["status"] == "needs_recheck")
    before = flow.path.read_bytes()
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        },
    )
    job = store.applications.get_application(original["application_id"])
    with pytest.raises(PortalDataError) as error:
        flow.update_inputs(unknown["id"], unknown["revision"], job["revision"])
    assert error.value.code == "flow_update_inflight"
    assert flow.path.read_bytes() == before
    assert (
        flow.snapshot(original["id"])["active_task"]["stages"]["export"]
        == unknown["stages"]["export"]
    )


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_refresh_reuses_manual_complete_source_and_preserves_old_versions(complete_portal):
    import json
    from types import SimpleNamespace

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    old_source = store.draft(original["draft_id"])["latex_source"]
    old_pdf = store.pdf(original["resume_id"])
    task = flow.begin_automatic_edit(original["id"], original["revision"])
    changed = store.draft(task["draft_id"])["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.", "Built 6 Python services; analyzed strategy."
    )
    task = flow.save_automatic_source(
        task["id"], task["revision"], task["prism"]["source_revision"], changed
    )
    manual = store.draft(task["draft_id"])
    manual_base = deepcopy(task["manual_latex_base"])
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        },
    )
    job = store.applications.get_application(original["application_id"])
    task = flow.update_inputs(task["id"], task["revision"], job["revision"])
    assert task["analysis_id"] == original["analysis_id"]
    assert task["manual_latex_base"] == manual_base
    assert task["manual_source"] == manual["manual_source"]
    requests = []

    def retain_manual_source(_config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        groups = []
        for group in manual["review_groups"]:
            begin = next(
                row["line_number"]
                for row in payload["body_lines"]
                if row["text"] == f"% TomorrowStar group {group['id']} begin\n"
            )
            end = next(
                row["line_number"]
                for row in payload["body_lines"]
                if row["text"] == f"% TomorrowStar group {group['id']} end\n"
            )
            groups.append(
                {
                    "title": group["title"],
                    "start_line": begin,
                    "end_line": end,
                    "source_ids": [source["source_id"] for source in group["sources"]],
                    "latex": group["rewritten"].replace(
                        "job@example.invalid", "updated@example.invalid"
                    ),
                    "disposition": "include",
                    "reason": "Preserve manual wording and refresh confirmed contact.",
                }
            )
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **_options: {"synthetic": True},
        )

    store.model_runner = retain_manual_source
    # The synthetic generator is a different configured boundary. Bind it before
    # the next material call; the documentary analysis still stays unchanged.
    task = flow.update_inputs(task["id"], task["revision"], job["revision"])
    assert task["analysis_id"] == original["analysis_id"]
    flow.start(task["id"], task["revision"], "resume")
    task = wait_for(
        flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed", "stale"}
    )
    assert task["status"] == "draft_ready", task["stages"]
    assert not requests
    assert (
        "Built 6 Python services; analyzed strategy."
        in store.draft(task["draft_id"])["latex_source"]
    )
    assert task["base_checkpoint"]["source_revision"] == manual_base["source_revision"]
    flow.start(task["id"], task["revision"], "export")
    task = wait_for(
        flow,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "failed", "needs_recheck"},
    )
    assert task["status"] == "materials_ready", task["stages"]
    flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    current = worker.store.load()
    worker.store.check_single(current["jobs"][0], current)
    result = store.read_export(task["resume_id"])
    assert "updated@example.invalid" in result["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in result["latex_source"]
    assert store.draft(manual["id"])["latex_source"] == changed
    assert store.draft(original["draft_id"])["latex_source"] == old_source
    assert store.pdf(original["resume_id"]) == old_pdf


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_change_keeps_current_confirmed_qualification_fact(complete_portal, tmp_path):
    from career_evidence_graph.application_flow import ApplicationFlowService, task_eligibility

    server, store, original, _generation = complete_portal
    flow = ApplicationFlowService(
        store.applications,
        tmp_path / "qualification-flow",
        input_provider=server.application_flow_service.input_provider,
        callbacks={
            "analysis": lambda _task: {
                "id": "synthetic-qualification",
                "requirements": [
                    {
                        "text": "German B2 required",
                        "importance": "required",
                        "judgment": "unknown",
                        "hard_condition": True,
                    }
                ],
            }
        },
    )
    job = store.applications.get_application(original["application_id"])
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        task = flow.clarify_condition(
            task["id"], task["revision"], 0, True, "Confirmed synthetic current fact"
        )
        original_resolution = deepcopy(task["hard_condition_resolutions"])
        assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
        put_information_answer(
            server.worker_service.store.answers,
            {
                "question": "Email",
                "value": "updated@example.invalid",
                "state": "confirmed",
                "scope": {"application_id": job["id"]},
            },
        )
        task = flow.update_inputs(task["id"], task["revision"], job["revision"])
        assert task["analysis_id"] == "synthetic-qualification"
        assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
        assert task["hard_condition_resolutions"] == original_resolution
    finally:
        flow.close()


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
@pytest.mark.parametrize("changed", ["unselected-career-document", "jd", "benchmark"])
def test_analysis_refresh_distinguishes_facts_from_research_benchmark(complete_portal, changed):
    import json

    from career_evidence_graph.application_match import match_configuration_revision
    from career_evidence_graph.application_worker import digest

    server, store, original, _generation = complete_portal
    flow = server.application_flow_service
    job = store.applications.get_application(original["application_id"])
    original_pdf = store.pdf(original["resume_id"])
    if changed == "unselected-career-document":
        document = store.catalog.root / "contributions/project-6.md"
        document.write_text(document.read_text() + "\nAdditional current career evidence.\n")
    elif changed == "jd":
        job = store.applications.update_application(
            job["id"],
            {
                "job_description": job["job_description"]
                + " Additional requirement: distributed reliability."
            },
            job["revision"],
        )
    else:
        directory = store.catalog.root / ".tomorrowstar-match-history"
        directory.mkdir()
        baseline = {
            "schemaVersion": 1,
            "source_snapshot_revision": original["inputs"]["sources_revision"],
            "configuration_revision": match_configuration_revision(),
            "policy_version": "documentary-match/v1",
            "evaluated_at": "2026-10-21T12:00:00+00:00",
            "historical_materials_available": False,
            "cases": [],
        }
        (directory / "current.json").write_text(
            json.dumps(baseline | {"revision": digest(baseline)})
        )
    task = flow.update_inputs(original["id"], original["revision"], job["revision"])
    if changed == "benchmark":
        assert task["analysis_id"] == original["analysis_id"]
        assert task["stages"]["analysis"] == original["stages"]["analysis"]
        assert task["inputs"] == original["inputs"]
        assert task["resume_id"] == original["resume_id"]
        assert store.pdf(task["resume_id"]) == original_pdf
        assert len(_generation) == 1
    else:
        assert task["analysis_id"] is None and task["stages"]["analysis"] == {"status": "pending"}
    assert task["artifacts"] == original["artifacts"]


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
@pytest.mark.parametrize("stage", ["resume", "export"])
def test_contact_update_preserves_inflight_material_attempt_until_its_result(
    complete_portal, stage
):
    import threading

    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    entered, release = threading.Event(), threading.Event()
    prior_callback = flow.callbacks[stage]

    def held_attempt(task):
        entered.set()
        assert release.wait(5)
        return prior_callback(task)

    flow.callbacks[stage] = held_attempt
    try:
        flow.start(original["id"], original["revision"], stage, retry=True)
        assert entered.wait(3)
        running = flow.snapshot(original["id"])["active_task"]
        before = flow.path.read_bytes()
        put_information_answer(
            worker.store.answers,
            {
                "question": "Email",
                "value": "updated@example.invalid",
                "state": "confirmed",
                "scope": {"application_id": original["application_id"]},
            },
        )
        job = store.applications.get_application(original["application_id"])
        with pytest.raises(PortalDataError) as error:
            flow.update_inputs(running["id"], running["revision"], job["revision"])
        assert error.value.code == "flow_update_inflight"
        assert flow.path.read_bytes() == before
    finally:
        release.set()
    result = wait_for(
        flow,
        original["id"],
        lambda row: row["stages"][stage]["status"] not in {"queued", "running"},
    )
    assert result["stages"][stage]["attempt_id"] == running["stages"][stage]["attempt_id"]
    assert result["stages"][stage]["status"] in {"failed", "needs_recheck"}


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
@pytest.mark.parametrize("change,expected", [("contact", "analysis_ready"), ("model", "stale")])
def test_running_analysis_ignores_contact_changes_but_rejects_incompatible_model_change(
    complete_portal, tmp_path, change, expected
):
    import threading

    from career_evidence_graph.application_flow import ApplicationFlowService

    server, store, original, _generation = complete_portal
    entered, release = threading.Event(), threading.Event()
    calls, configuration = [], {}

    def provider(identifier):
        current = server.application_flow_service.input_provider(identifier)
        current["inputs"].update(configuration)
        return current

    def analyze(task):
        calls.append(task["id"])
        entered.set()
        assert release.wait(5)
        return {"id": "synthetic-current-analysis", "requirements": []}

    flow = ApplicationFlowService(
        store.applications,
        tmp_path / "running-analysis-flow",
        input_provider=provider,
        callbacks={"analysis": analyze},
    )
    job = store.applications.get_application(original["application_id"])
    try:
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        assert entered.wait(3)
        if change == "contact":
            put_information_answer(
                server.worker_service.store.answers,
                {
                    "question": "Email",
                    "value": "updated@example.invalid",
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                },
            )
        else:
            configuration["analysis_configuration_revision"] = "incompatible-new-model"
        release.set()
        result = wait_for(
            flow, task["id"], lambda row: row["status"] in {"analysis_ready", "failed", "stale"}
        )
        assert result["status"] == expected, result["stages"]
        assert len(calls) == 1 and len(result["artifacts"]) == 1
        assert result["artifacts"][0]["adopted"] is (change == "contact")
    finally:
        release.set()
        flow.close()


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_change_does_not_detach_existing_worker_or_replace_its_pdf(complete_portal):
    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    prepared = flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    old_worker = deepcopy(worker.store.load())
    old_pdf = store.pdf(original["resume_id"])
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        },
    )
    job = store.applications.get_application(original["application_id"])
    task = flow.update_inputs(prepared["id"], prepared["revision"], job["revision"])
    assert task["analysis_id"] == original["analysis_id"] and task["status"] == "needs_recheck"
    assert task["worker_ref"] == prepared["worker_ref"]
    assert worker.store.load() == old_worker
    assert store.pdf(original["resume_id"]) == old_pdf
    with pytest.raises(PortalDataError):
        worker.store.check_single(old_worker["jobs"][0], old_worker)
    with pytest.raises(PortalDataError) as error:
        flow.start(task["id"], task["revision"], "resume")
    assert error.value.code == "flow_materials_in_use"


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_answering_first_work_authorization_fact_keeps_original_unchanged_pdf_usable(
    complete_portal,
):
    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    prepared = flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    before = worker.store.load()
    job = before["jobs"][0]
    worker.store.check_single(job, before)
    pdf = store.pdf(original["resume_id"])

    # This is a factual answer to an ordinary required ATS qualification field.
    # The JD/analysis has no corresponding unresolved hard condition, and this
    # supporting answer does not change the completed CV or its career sources.
    put_information_answer(
        worker.store.answers,
        {
            "question": "Are you currently authorized to work in this country",
            "value": "Yes",
            "state": "confirmed",
            "scope": {"country": "CHE"},
        },
        source="application-answer",
    )
    assert store.pdf(original["resume_id"]) == pdf
    assert flow.snapshot(prepared["id"])["active_task"]["worker_ref"] == prepared["worker_ref"]
    worker.store.check_single(job, before)


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_real_answer_then_one_continue_keeps_original_pdf_and_page(complete_portal, monkeypatch):
    from copy import deepcopy

    from career_evidence_graph.application_worker import start_run
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    prepared = flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    run_id = start_run(worker.store)
    state = worker.store.load()
    current = state["jobs"][0]
    question = {
        "id": "permission",
        "type": "select",
        "question": "Are you currently authorized to work in this country",
        "options": ["Yes", "No"],
        "required": True,
        "multiple": False,
        "value": "",
        "valid": False,
    }
    # A synthetic observation checkpoint for the retained original ATS page.
    # Every operation after this precondition uses the real service/Runner path.
    current.update(
        status="needs_input",
        page_open=True,
        questions=[question],
        page_observation={
            "run_id": run_id,
            "page_id": "retained-permission-page",
            "event": "observed",
            "at": state["runtime"]["observed_at"],
        },
    )
    worker.store.save(state)
    before = deepcopy(current)
    runner = ApplicationRunner(worker.store, None)

    class Page:
        context = None

        def is_closed(self):
            return False

    page = Page()
    runner.pages[current["application_id"]] = page
    runner.page_ids[page] = "retained-permission-page"
    observed = []
    monkeypatch.setattr(
        runner,
        "observe",
        lambda original_page, _job: observed.append(original_page) or {"fields": []},
    )
    worker.request(
        "answer",
        {
            "application_id": current["application_id"],
            "question_id": question["id"],
            "value": "Yes",
        },
    )
    answered = worker.store.load()
    assert answered["jobs"][0]["questions"] == []
    worker.request(
        "continue-current",
        {
            "application_id": current["application_id"],
            "controller": "synthetic-controller",
            "request_id": "continue-after-permission-answer",
        },
    )
    continued = worker.store.load()
    runner.commands(continued)
    runner.persist(continued)
    after = worker.store.load()
    final = after["jobs"][0]
    assert final["file_path"] == before["file_path"]
    assert final["file_sha256"] == before["file_sha256"]
    assert final["single_binding"] == before["single_binding"]
    assert flow.snapshot(prepared["id"])["active_task"]["analysis_id"] == original["analysis_id"]
    assert final["continuation"]["status"] == "verified", final["continuation"]
    assert observed == [page]
    assert after["control"] == "running"


@pytest.mark.parametrize(
    "complete_portal", [{"confirmed_email": True, "german_requirement": True}], indirect=True
)
def test_current_worker_rechecks_applicable_language_conflict_without_replacing_pdf(
    complete_portal,
):
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    prepared = flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    state = worker.store.load()
    job = state["jobs"][0]
    worker.store.check_single(job, state)
    before_pdf = store.pdf(original["resume_id"])
    put_information_answer(
        worker.store.answers,
        {
            "question": "German level",
            "value": "A2",
            "state": "confirmed",
            "scope": {"country": "CHE"},
        },
    )
    with pytest.raises(PortalDataError) as error:
        worker.store.check_single(job, state)
    assert error.value.code == "single_eligibility_required"
    with pytest.raises(PortalDataError):
        ApplicationRunner(worker.store, None).check_inputs(job)
    assert store.pdf(original["resume_id"]) == before_pdf
    assert flow.snapshot(prepared["id"])["active_task"]["analysis_id"] == original["analysis_id"]
    assert worker.store.load() == state


@pytest.mark.parametrize(
    "complete_portal", [{"confirmed_email": True, "german_requirement": True}], indirect=True
)
def test_language_fact_withdrawal_rechecks_original_worker_without_discarding_history(
    complete_portal,
):
    from career_evidence_graph.application_explanations import qualification_for
    from career_evidence_graph.application_information import read_information_library
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    clarified = flow.clarify_condition(
        original["id"], original["revision"], 0, True, "Existing current German B2 fact"
    )
    receipt = deepcopy(clarified["hard_condition_resolutions"])
    prepared = flow.prepare_worker(clarified["id"], clarified["revision"], "CHE", True)
    state = worker.store.load()
    current_job = state["jobs"][0]
    job = store.applications.get_application(current_job["application_id"])
    worker.store.check_single(current_job, state)
    put_information_answer(
        worker.store.answers,
        {
            "question": "Are you currently authorized to work in this country",
            "value": "Yes",
            "state": "confirmed",
            "scope": {"country": "CHE"},
        },
    )
    supported = qualification_for(
        prepared, job | {"country": "CHE"}, read_information_library(worker.store.answers.root)
    )
    assert supported["status"] == "supported"
    assert supported["conditions"][0]["resolution"]["source"] == receipt[0]["source"]
    worker.store.check_single(current_job, state)
    put_information_answer(
        worker.store.answers,
        {
            "question": "German level",
            "value": None,
            "state": "missing",
            "scope": {"country": "CHE"},
        },
        source="answer-withdrawal",
    )
    current = qualification_for(
        prepared, job | {"country": "CHE"}, read_information_library(worker.store.answers.root)
    )
    assert current["status"] == "needs_input"
    assert current["conditions"][0]["resolution"] is None
    # Unknown qualification retains the ordinary preparation boundary. The current
    # readback must not claim the withdrawn fact is still confirmed.
    worker.store.check_single(current_job, state)
    ApplicationRunner(worker.store, None).check_inputs(current_job)
    assert flow.snapshot(prepared["id"])["active_task"]["hard_condition_resolutions"] == receipt
    assert worker.store.load() == state


def test_historical_qualification_receipt_preserves_unchanged_analysis_basis():
    from career_evidence_graph.application_flow import task_eligibility
    from career_evidence_graph.application_worker import digest

    inputs = {
        "sources_revision": "sources",
        "qualification_information_revision": "old-qualification-receipt",
        "information_library_root": "/synthetic-answers",
        "information_library_revision": "current-contact",
    }
    analysis = {
        "id": "historical-analysis",
        "requirements": [
            {
                "text": "German B2 required",
                "importance": "required",
                "judgment": "unknown",
                "hard_condition": True,
            }
        ],
    }
    task = {
        "inputs": inputs,
        "analysis_id": analysis["id"],
        "artifacts": [{"stage": "analysis", "adopted": True, "result": analysis}],
        "hard_condition_resolutions": [
            {
                "analysis_id": analysis["id"],
                "requirement_index": 0,
                "confirmed": True,
                "verified_by": "user",
                "eligible": True,
                "source": "Original confirmed fact",
                "analysis_input_revision": digest(
                    {
                        "sources_revision": "sources",
                        "qualification_information_revision": "old-qualification-receipt",
                    }
                ),
            }
        ],
    }
    assert task_eligibility(task, bind_inputs=True)["status"] == "supported"
    task["inputs"]["sources_revision"] = "changed-real-career-source"
    assert task_eligibility(task, bind_inputs=True)["status"] == "needs_input"


def test_historical_manual_language_statement_rechecks_explicit_withdrawal():
    from test_job_explanations import job_and_task, requirement

    from career_evidence_graph.application_explanations import qualification_for
    from career_evidence_graph.application_worker import digest

    application, task = job_and_task(
        [requirement("German B2 required", judgment="unknown", hard=True)]
    )
    task["inputs"].update(
        {
            "information_library_root": "/synthetic-answers",
            "information_library_revision": "contact",
            "qualification_information_revision": "old-qualification-receipt",
        }
    )
    old_analysis_binding = {
        key: value
        for key, value in task["inputs"].items()
        if key
        not in {
            "information_library_root",
            "information_library_revision",
            "preparation_policy_revision",
        }
    }
    task["hard_condition_resolutions"] = [
        {
            "analysis_id": task["analysis_id"],
            "requirement_index": 0,
            "confirmed": True,
            "verified_by": "user",
            "eligible": True,
            "source": "I meet the German B2 minimum.",
            "analysis_input_revision": digest(old_analysis_binding),
            "at": 1,
        }
    ]
    before = deepcopy(task)
    record = {
        "key": "german",
        "question": "German level",
        "state": "confirmed",
        "value": "B2",
        "scope": {"application_id": application["id"]},
    }
    assert (
        qualification_for(task, application, {"status": "available", "records": [record]})["status"]
        == "supported"
    )
    withdrawn = {**record, "state": "missing", "value": None}
    result = qualification_for(task, application, {"status": "available", "records": [withdrawn]})
    assert result["status"] == "needs_input"
    assert result["conditions"][0]["resolution"] is None
    assert task == before
