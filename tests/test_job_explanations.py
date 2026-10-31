"""User-facing explanations preserve documentary scores and qualification uncertainty."""

from copy import deepcopy

import pytest
from test_application_flow import application as application

from career_evidence_graph.application_explanations import job_explanation
from career_evidence_graph.application_flow import job_input_revision


def job_and_task(requirements):
    application = {
        "id": "synthetic-job",
        "revision": "job-v1",
        "company": "Synthetic Employer",
        "role_title": "Python Engineer",
        "location": "",
        "job_description": "Complete synthetic JD.",
    }
    report = {
        "id": "analysis-v1",
        "requirements": requirements,
        "policy_version": "documentary-match/v1",
        "limitations": [],
    }
    task = {
        "id": "synthetic-task",
        "application_id": application["id"],
        "revision": "task-v1",
        "job_binding": job_input_revision(application),
        "inputs": {
            "sources_revision": "source-v1",
            "preparation_policy_revision": "preparation-policy/v1.0",
        },
        "status": "analysis_ready",
        "analysis_id": report["id"],
        "stages": {"analysis": {"status": "complete"}, "resume": {"status": "pending"}},
        "artifacts": [{"stage": "analysis", "adopted": True, "result": report}],
    }
    return application, task


def requirement(text="Python services", *, judgment="supported", hard=False):
    return {
        "text": text,
        "importance": "required",
        "judgment": judgment,
        "hard_condition": hard,
        "explanation": "Synthetic documentary reason.",
        "sources": [
            {"source_name": "synthetic.md", "locator": "Scope", "source_id": "source:scope"}
        ],
    }


def test_explanation_keeps_score_and_unknown_qualification_separate():
    application, task = job_and_task(
        [
            requirement(),
            requirement("Work permit", judgment="unknown", hard=True),
        ]
    )
    original = deepcopy(task)
    result = job_explanation(application, task, current_inputs=task["inputs"])
    assert result["score"]["lower"] == 50
    assert result["score"]["upper"] == 100
    assert result["score"]["coverage"] == 50
    assert result["qualification"]["status"] == "needs_input"
    assert result["progress"]["status"] == "analysis_ready"
    assert result["reasons"][1]["explanation"] == "Synthetic documentary reason."
    assert result["reasons"][0]["sources"][0]["locator"] == "Scope"
    assert result["policy_version"] == "preparation-policy/v1.0"
    assert result["preferences"]["unknown"] == ["company", "salary", "personal_priority"]
    assert "grade" not in result and task == original


def test_preparation_snapshot_orders_by_match_and_manual_move_preserves_explanations(
    application, tmp_path
):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService

    applications, first = application
    second = applications.create_application(
        {
            "company": "Other Synthetic",
            "role_title": "Engineer",
            "job_description": "Another full JD.",
        }
    )

    def analyze(task):
        return {
            "id": "analysis-" + task["id"],
            "requirements": [
                requirement(
                    judgment="partial" if task["application_id"] == first["id"] else "supported"
                )
            ],
        }

    service = ApplicationFlowService(
        applications, tmp_path / "flow", preparation_only=True, callbacks={"analysis": analyze}
    )
    try:
        for app in (first, second):
            task = service.create(app["id"], app["revision"])
            service.start(task["id"], task["revision"], "analysis")
            wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        state = service.snapshot()
        assert [r["application_id"] for r in state["explanations"]] == [second["id"], first["id"]]
        before = {r["application_id"]: r for r in state["explanations"]}
        service.request(
            "reorder",
            {
                "application_id": first["id"],
                "direction": "up",
                "order_revision": state["order_revision"],
            },
        )
        after = service.snapshot()
        assert [r["application_id"] for r in after["explanations"]] == [first["id"], second["id"]]
        assert after["order_mode"] == "manual"
        assert {r["application_id"]: r for r in after["explanations"]} == before
        assert all(r["progress"]["status"] == "analysis_ready" for r in after["explanations"])
    finally:
        service.close()
    reopened = ApplicationFlowService(applications, tmp_path / "flow", preparation_only=True)
    try:
        assert [r["application_id"] for r in reopened.snapshot()["explanations"]] == [
            first["id"],
            second["id"],
        ]
    finally:
        reopened.close()


def test_documentary_high_score_does_not_confirm_a_hard_applicant_fact():
    application, task = job_and_task([requirement("German B2 required", hard=True)])
    result = job_explanation(application, task, current_inputs=task["inputs"])
    assert result["score"]["lower"] == 100
    assert result["qualification"]["status"] == "needs_input"


def test_qualification_reuses_country_scope_from_unambiguous_job_location():
    application, task = job_and_task(
        [requirement("German B2 required", judgment="unknown", hard=True)]
    )
    application["location"] = "Zurich, Switzerland"
    task["job_binding"] = job_input_revision(application)
    library = {
        "status": "available",
        "records": [
            {
                "key": "global",
                "question": "German level",
                "value": "A1",
                "scope": {},
                "state": "confirmed",
            },
            {
                "key": "country",
                "question": "German level",
                "value": "B2",
                "scope": {"country": "CHE"},
                "state": "confirmed",
            },
        ],
    }
    result = job_explanation(application, task, current_inputs=task["inputs"], library=library)
    assert result["qualification"]["status"] == "supported"
    assert result["qualification"]["conditions"][0]["library"]["references"][0]["key"] == "country"


def test_confirmed_library_fact_resolves_qualification_without_changing_documentary_score():
    application, task = job_and_task(
        [requirement("German B2 required", judgment="unknown", hard=True)]
    )
    library = {
        "status": "available",
        "revision": "library-v1",
        "records": [
            {
                "key": "language",
                "question": "German level",
                "value": "C1",
                "scope": {},
                "state": "confirmed",
            }
        ],
        "preferences": {},
    }
    result = job_explanation(application, task, current_inputs=task["inputs"], library=library)
    assert result["score"]["lower"] == 0 and result["score"]["upper"] == 100
    assert result["qualification"]["status"] == "supported"
    assert result["qualification"]["conditions"][0]["library"]["references"][0]["key"] == "language"
    library["records"][0]["value"] = "A2"
    conflict = job_explanation(application, task, current_inputs=task["inputs"], library=library)
    assert conflict["qualification"]["status"] == "conflict"
    assert conflict["score"] == result["score"]
    assert conflict["reasons"] == result["reasons"]


def test_changed_inputs_keep_historical_reason_but_do_not_present_current_qualification():
    application, task = job_and_task([requirement()])
    before = job_explanation(application, task, current_inputs=task["inputs"])
    after = job_explanation(
        application, task, current_inputs=task["inputs"] | {"sources_revision": "source-v2"}
    )
    assert after["fresh"] is False
    assert after["progress"]["status"] == "stale"
    assert after["score"] == before["score"] and after["reasons"] == before["reasons"]
    assert after["qualification"]["status"] == "needs_input"
    assert after["qualification"]["historical_status"] == "not_specified"


def test_resume_configuration_change_does_not_stale_the_matching_explanation():
    application, task = job_and_task([requirement()])
    task["inputs"]["resume_configuration_revision"] = "renderer-v1"
    result = job_explanation(
        application,
        task,
        current_inputs=task["inputs"] | {"resume_configuration_revision": "renderer-v2"},
    )
    assert result["fresh"] is True and result["score"]["lower"] == 100


@pytest.mark.parametrize(
    "requirements",
    [
        [requirement("Work permit", judgment="unknown", hard=True)],
        [requirement("Work permit", judgment="gap", hard=True)],
        [requirement("Work permit", judgment="supported", hard=True)],
        [],
    ],
)
def test_preparation_rejects_resume_until_required_facts_are_confirmed(
    application, tmp_path, requirements
):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, job = application
    calls = []
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda _: {"id": "analysis-v1", "requirements": requirements},
            "resume": lambda _: calls.append("resume") or {"id": "r", "pdf_sha256": "a" * 64},
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        with pytest.raises(PortalDataError) as error:
            service.start(task["id"], task["revision"], "resume")
        assert error.value.code == "flow_qualification_required"
        assert service.snapshot(task["id"])["active_task"] == task
        assert calls == []
    finally:
        service.close()


@pytest.mark.parametrize("requirements", [[], None, ["malformed"], [{"text": "Permit"}]])
def test_unusable_requirements_cannot_establish_qualification(requirements):
    application, task = job_and_task(requirements)
    result = job_explanation(application, task, current_inputs=task["inputs"])
    assert result["qualification"]["status"] == "unassessed"
    assert result["score"] is None or result["score"]["lower"] is None


def test_library_refresh_keeps_analysis_but_requires_current_fact_confirmation(
    application, tmp_path
):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService

    applications, job = application
    inputs = {"information_library_revision": "library-v1", "preparation_policy_revision": "v1.0"}
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        input_provider=lambda _: {"application_revision": job["revision"], "inputs": inputs},
        callbacks={
            "analysis": lambda _: {
                "id": "a",
                "requirements": [requirement("Work permit", judgment="unknown", hard=True)],
            }
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = service.clarify_condition(
            task["id"], task["revision"], 0, True, "Confirmed synthetic fact."
        )
        original = service.snapshot(task["id"])["active_explanation"]
        assert original["qualification"]["status"] == "supported"
        inputs["information_library_revision"] = "library-v2"
        assert service.snapshot(task["id"])["active_explanation"]["fresh"] is False
        task = service.update_inputs(task["id"], task["revision"], job["revision"])
        assert task["analysis_id"] == "a"
        current = service.snapshot(task["id"])["active_explanation"]
        assert current["fresh"] is True and current["score"] == original["score"]
        assert current["qualification"]["status"] == "needs_input"
        assert task["hard_condition_resolutions"][0]["source"] == "Confirmed synthetic fact."
        task = service.clarify_condition(
            task["id"], task["revision"], 0, False, "Current fact correction."
        )
        assert (
            service.snapshot(task["id"])["active_explanation"]["qualification"]["status"]
            == "conflict"
        )
    finally:
        service.close()


def test_opening_older_task_uses_its_own_analysis(application, tmp_path):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService

    applications, job = application
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={"analysis": lambda task: {"id": task["id"], "requirements": [requirement()]}},
    )
    try:
        tasks = []
        for _ in range(2):
            task = service.create(job["id"], job["revision"])
            service.start(task["id"], task["revision"], "analysis")
            tasks.append(
                wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
            )
            if len(tasks) == 1:
                service.cancel(tasks[0]["id"], tasks[0]["revision"])
        assert tasks[0]["id"] != tasks[1]["id"]
        state = service.snapshot(tasks[0]["id"])
        assert state["active_explanation"]["task_id"] == tasks[0]["id"]
        assert (
            state["active_explanation"]["input_binding"]["analysis_id"] == tasks[0]["analysis_id"]
        )
        assert state["explanations"][0]["task_id"] == tasks[1]["id"]
    finally:
        service.close()


def test_fact_correction_during_resume_generation_cannot_adopt_old_materials(application, tmp_path):
    import threading

    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService

    applications, job = application
    entered, release = threading.Event(), threading.Event()

    def resume(_):
        entered.set()
        assert release.wait(2)
        return {"id": "old-fact-resume", "pdf_sha256": "a" * 64}

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda _: {
                "id": "a",
                "requirements": [requirement("Work permit", judgment="unknown", hard=True)],
            },
            "resume": resume,
        },
    )
    try:
        task = service.create(job["id"], job["revision"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = service.clarify_condition(task["id"], task["revision"], 0, True, "Confirmed.")
        task = service.start(task["id"], task["revision"], "resume")
        assert entered.wait(2)
        task = service.snapshot(task["id"])["active_task"]
        service.clarify_condition(
            task["id"], task["revision"], 0, False, "Correction: not eligible."
        )
        release.set()
        task = wait_for(
            service, task["id"], lambda row: any(a["stage"] == "resume" for a in row["artifacts"])
        )
        assert task["resume_id"] is None and task["materials_confirmed"] is False
        assert task["status"] == "analysis_ready"
        assert task["artifacts"][-1]["adopted"] is False
    finally:
        release.set()
        service.close()


def test_one_unverifiable_job_does_not_hide_other_explanations(application, tmp_path):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService
    from career_evidence_graph.career_portal_data import PortalDataError

    applications, first = application
    second = applications.create_application(
        {"company": "Second", "role_title": "Engineer", "job_description": "Full synthetic JD."}
    )
    unavailable = set()

    def current(application_id):
        if application_id in unavailable:
            raise PortalDataError("sources_unavailable", "Synthetic unavailable inputs.", 409)
        return {
            "application_revision": applications.get_application(application_id)["revision"],
            "inputs": {"sources_revision": "source-v1"},
        }

    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        preparation_only=True,
        input_provider=current,
        callbacks={"analysis": lambda task: {"id": task["id"], "requirements": [requirement()]}},
    )
    try:
        for job in (first, second):
            task = service.create(job["id"], job["revision"])
            service.start(task["id"], task["revision"], "analysis")
            wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        before = {r["application_id"]: r for r in service.snapshot()["explanations"]}
        unavailable.add(first["id"])
        after = {r["application_id"]: r for r in service.snapshot()["explanations"]}
        assert after[second["id"]] == before[second["id"]]
        assert after[first["id"]]["fresh"] is False
        assert after[first["id"]]["score"] == before[first["id"]]["score"]
    finally:
        service.close()


def test_model_configuration_change_keeps_completed_analysis_explanation_fresh():
    application, task = job_and_task([requirement()])
    task["inputs"]["analysis_configuration_revision"] = "original-model"
    current = task["inputs"] | {"analysis_configuration_revision": "different-model"}
    result = job_explanation(application, task, current_inputs=current)
    assert result["fresh"] is True
    assert result["progress"]["status"] == "analysis_ready"
    assert result["reasons"][0]["explanation"] == "Synthetic documentary reason."


def test_automatic_flow_shows_the_match_overview_without_gating_on_it(application, tmp_path):
    from test_application_flow import wait_for

    from career_evidence_graph.application_flow import ApplicationFlowService

    applications, job = application
    service = ApplicationFlowService(
        applications,
        tmp_path / "flow",
        callbacks={"analysis": lambda task: {"id": task["id"], "requirements": [requirement()]}},
    )
    try:
        task = service.create(job["id"], job["revision"])
        assert "match_explanation" not in service.snapshot(task["id"])
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        state = service.snapshot(task["id"])
        # Installed MC-11: the automatic flow showed only a score badge, without
        # the range and per-requirement reasons the preparation overview gives.
        assert state["match_explanation"]["input_binding"]["analysis_id"] == task["analysis_id"]
        assert state["match_explanation"]["reasons"]
        assert "active_explanation" not in state
    finally:
        service.close()
