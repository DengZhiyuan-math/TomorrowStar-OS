"""Backend progression is independent of browser-controller button clicks."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_flow import (
    ApplicationFlowService,
    _preparation_progress,
    legacy_analysis_failure,
)
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError
from career_evidence_graph.job_screening import application_country


class Intake:
    def __init__(self, root, jobs):
        self.root = root
        self.jobs = jobs
        self.state = {"status": "idle", "run_id": None}
        self.calls = []

    def snapshot(self):
        return deepcopy(self.state)

    def source_delivery(self, run_id):
        path = self.root / "runs" / run_id / "source-chain.json"
        if any(part.is_symlink() for part in (path, path.parent, path.parent.parent)):
            raise PortalDataError("intake_source_invalid", "Synthetic redirected delivery", 409)
        chain = helper.read_json_object(path, "synthetic intake delivery")
        return {
            "schema_version": "intake-source-delivery/v1",
            "run_id": run_id,
            "application_ids": list(
                dict.fromkeys(
                    row["application_id"]
                    for row in chain["sources"]
                    if row.get("save_status") == "saved"
                )
            ),
        }

    def refresh(self, **kwargs):
        self.calls.append(kwargs)
        run_id = "a" * 32
        helper.atomic_write_json(
            self.root / "runs" / run_id / "source-chain.json",
            {
                "schemaVersion": 1,
                "sources": [
                    {"application_id": job["id"], "save_status": "saved"} for job in self.jobs
                ],
            },
        )
        self.state = {"status": "complete", "run_id": run_id}
        return self.snapshot()


class Flow:
    def __init__(self, root, apps, worker):
        self.root, self.applications, self.worker = root, apps, worker
        self.callbacks = {}
        self.tasks = {}
        self.calls = []

    prepare = ApplicationFlowService.prepare
    continue_preparation = ApplicationFlowService.continue_preparation

    def progress(self, task_id):
        return _preparation_progress(self.tasks[task_id], self.analysis_outcome(task_id))

    def snapshot(self, task_id=None):
        return {
            "tasks": deepcopy(list(self.tasks.values())),
            "active_task": deepcopy(self.tasks.get(task_id)),
        }

    def task_snapshot(self, task_id):
        return deepcopy(self.tasks.get(task_id))

    def analysis_outcome(self, task_id):
        task = self.tasks[task_id]
        status = {"draft": "pending", "analyzing": "running", "analysis_ready": "ready"}.get(
            task["status"], "unknown"
        )
        stage = task.get("stages", {}).get("analysis", {})
        legacy_skippable = legacy_analysis_failure(task)
        if legacy_skippable:
            status = "rejected"
        return {
            "schema_version": "analysis-outcome/v1",
            "task_id": task_id,
            "task_revision": task["revision"],
            "status": status,
            "error_code": stage.get("error_code"),
            "attempt_id": stage.get("attempt_id"),
            "recovery": "continue"
            if status == "ready"
            else "needs_recheck"
            if status == "unknown"
            else "needs_input"
            if status == "rejected"
            else "wait",
            "legacy_skippable": legacy_skippable,
        }

    def create(self, identifier, revision, **_options):
        task = {
            "id": identifier,
            "application_id": identifier,
            "revision": "v1",
            "job_binding": "job-v1",
            "inputs": {"jd_revision": "v1"},
            "status": "draft",
            "worker_ref": None,
            "artifacts": [],
            "resume_id": None,
            "resume_sha256": None,
        }
        self.tasks[identifier] = task
        self.calls.append(("create", identifier))
        return deepcopy(task)

    def start(self, identifier, revision, stage):
        task = self.tasks[identifier]
        self.calls.append((stage, identifier))
        if stage == "analysis":
            partial = "Partial" in self.applications.get_application(identifier)["company"]
            result = {
                "id": "analysis",
                "requirements": [
                    {
                        "text": "Python",
                        "importance": "required",
                        "judgment": "partial" if partial else "supported",
                        "hard_condition": False,
                    }
                ],
            }
            task.update(status="analysis_ready", analysis_id="analysis")
            task["artifacts"].append({"stage": "analysis", "adopted": True, "result": result})
        else:
            task.update(status="resume_ready", resume_id="pdf", resume_sha256="b" * 64)
        task["revision"] += "v"
        return deepcopy(task)

    def prepare_automatic_materials(self, identifier, revision):
        self.tasks[identifier]["automatic_materials"] = True
        return deepcopy(self.tasks[identifier])

    def prepare_worker(self, identifier, revision, country, send_confirmed, **kwargs):
        task = self.tasks[identifier]
        assert self.callbacks["verify_automation_authorization"](
            kwargs["automation_authorization"], task
        )
        self.calls.append(("prepare", identifier))
        self.worker.state.update(
            batch_id="batch",
            jobs=[
                {
                    "application_id": identifier,
                    "status": "queued",
                    "page_open": False,
                    "intent": None,
                    "handed_off": False,
                }
            ],
        )
        task.update(
            status="queued",
            worker_ref={"batch_id": "batch", "job_id": identifier, "status": "queued"},
        )
        return deepcopy(task)

    def worker_action(self, identifier, revision, operation, payload):
        self.calls.append(("worker_" + operation, identifier))
        self.worker.state.update(
            control="running" if operation != "pause" else "paused",
            controller=payload["controller"],
        )
        if operation == "resume":
            self.worker.state["jobs"][0]["status"] = "filling"
        return deepcopy(self.tasks[identifier])


class Worker:
    generic = True

    def __init__(self):
        self.state = {
            "control": "paused",
            "batch_id": None,
            "controller": None,
            "jobs": [],
            "runtime": {"id": "runtime"},
        }
        self.store = SimpleNamespace(language_levels=lambda application=None: {})

    def snapshot(self):
        return deepcopy(self.state)


@pytest.fixture
def environment(tmp_path):
    (tmp_path / "applications").mkdir()
    apps = ApplicationStore(tmp_path / "applications")
    jobs = [
        apps.create_application(
            {
                "company": company,
                "role_title": "ML Engineer",
                "url": f"https://example.com/jobs/{index}",
                "location": "Zurich, Switzerland",
                "job_description": "Python machine learning systems",
            }
        )
        for index, company in enumerate(("Partial Match", "Strong Match"))
    ]
    worker = Worker()
    flow = Flow(tmp_path / "flow", apps, worker)
    intake = Intake(tmp_path / "intake", jobs)
    pipeline = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        yield pipeline, flow, intake, worker, jobs
    finally:
        pipeline.close()


def advance(pipeline, target, limit=30):
    for _ in range(limit):
        pipeline._tick()
        if pipeline.snapshot()["status"] == target:
            return pipeline.snapshot()
    pytest.fail(str(pipeline.snapshot()))


@pytest.mark.parametrize("scope_kind", ["application_id", "country", "company"])
def test_matching_uses_current_job_language_exception(environment, scope_kind):
    from career_evidence_graph.application_worker import WorkerStore

    pipeline, flow, _intake, worker, jobs = environment
    worker.store = WorkerStore(flow.applications, flow.root.parent / "language-worker")
    for app in jobs:
        flow.applications.update_application(
            app["id"],
            {
                "job_description": "German B2 required.",
                "location": "Zurich, Switzerland" if app["id"] == jobs[0]["id"] else "Boston, USA",
            },
            app["revision"],
        )
    context = {"application_id": jobs[0]["id"], "country": "CHE", "company": jobs[0]["company"]}
    for scope, value in [({}, "A1"), ({scope_kind: context[scope_kind]}, "B2")]:
        worker.store.answers.put_answer(
            {
                "question": "German proficiency CEFR",
                "value": value,
                "scope": scope,
                "state": "confirmed",
            }
        )
    pipeline.start(request_id="language-scope")
    snapshot = advance(pipeline, "generating_resume")
    assert [call for call in flow.calls if call[0] == "analysis"] == [("analysis", jobs[0]["id"])]
    assert snapshot["active_task_id"] == jobs[0]["id"]
    assert (
        next(row for row in snapshot["items"] if row["application_id"] == jobs[1]["id"])["status"]
        == "pending"
    )
    assert jobs[1]["id"] not in flow.tasks
    assert snapshot["items"][1]["score"] is None


def language_wait(environment):
    """A language wait saved before 2026-11-08, when a language gap still stopped a job.

    New jobs no longer stop on language; a saved wait still resumes with one Continue.
    """
    from career_evidence_graph.application_worker import WorkerStore

    pipeline, flow, intake, worker, jobs = environment
    worker.store = WorkerStore(flow.applications, flow.root.parent / "language-worker")
    pipeline.start(request_id="language-conflict")
    advance(pipeline, "matching")
    with pipeline._control() as state:
        item = next(row for row in state["items"] if row["application_id"] == jobs[0]["id"])
        item.update(
            status="needs_input",
            posting_checked=True,
            reason=["适用语言信息有冲突或缺少明确等级，请核对"],
            reason_code="language_information_required",
        )
        state["resume_status"] = "matching"
        pipeline._stop(state, "needs_input", "当前岗位的适用语言信息需确认，其他岗位保持等待。")
    return pipeline, flow, intake, worker, jobs, pipeline.snapshot()


@pytest.mark.parametrize(
    "excluded_fields",
    [
        {"application_strategy": "hold"},
        {"personal_priority": "low"},
        {"jd_match": "weak"},
        {"evidence_match": "missing"},
        {"deadline": "2000-01-01"},
        {"status": "applied"},
        {"url": "http://example.com/jobs/excluded"},
    ],
    ids=[
        "hold",
        "low_priority",
        "weak_match",
        "missing_evidence",
        "expired",
        "recorded",
        "invalid_url",
    ],
)
def test_independently_excluded_job_does_not_request_language_resolution(
    environment, excluded_fields
):
    from career_evidence_graph.application_worker import WorkerStore

    pipeline, flow, intake, worker, jobs = environment
    worker.store = WorkerStore(flow.applications, flow.root.parent / "language-worker")
    flow.applications.update_application(
        jobs[0]["id"],
        {"job_description": "German B2 required."} | excluded_fields,
        jobs[0]["revision"],
    )
    for question, value in [("German level", "B2"), ("German proficiency CEFR", "C1")]:
        worker.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    pipeline.start(request_id="skip-independent-exclusion")
    advance(pipeline, "matching")
    pipeline._tick()
    current = pipeline.snapshot()
    assert current["items"][0]["status"] == "excluded"
    assert current["status"] == "matching" and current["control"] == "running"
    assert flow.calls == [] and worker.snapshot()["jobs"] == []
    result = advance(pipeline, "generating_resume")
    assert result["active_task_id"] == jobs[1]["id"]
    assert [call for call in flow.calls if call[0] == "analysis"] == [("analysis", jobs[1]["id"])]
    assert jobs[0]["id"] not in flow.tasks and len(intake.calls) == 1


def test_one_grant_drives_email_matching_resume_and_filling_without_ui(environment):
    pipeline, flow, intake, worker, jobs = environment
    pipeline.start(request_id="first-cycle")
    snapshot = advance(pipeline, "filling")
    assert intake.calls == [{"max_results": 3, "max_candidates": 10}]
    assert [call for call in flow.calls if call[0] == "analysis"] == [("analysis", jobs[0]["id"])]
    assert [call for call in flow.calls if call[0] == "resume"] == [("resume", jobs[0]["id"])]
    assert snapshot["active_task_id"] == jobs[0]["id"]
    assert snapshot["items"][0]["score"]["lower"] == 50
    assert snapshot["items"][1]["status"] == "pending"
    assert snapshot["items"][1]["score"] is None
    assert jobs[1]["id"] not in flow.tasks
    worker.state["jobs"][0]["status"] = "ready_for_review"
    completed = advance(pipeline, "ready_for_review")
    assert completed["control"] == "paused"
    notification = completed["notification"]
    assert notification["title"] and len(notification["title"]) <= 200
    assert len(notification["message"]) <= 1000
    pipeline._tick()
    assert pipeline.snapshot()["notification"] == notification
    assert all(call[0] not in {"submit", "recheck", "cancel", "release"} for call in flow.calls)


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Switzerland", "CHE"),
        ("London, United Kingdom", "GBR"),
        ("Zurich", None),
        ("Switzerland / France", None),
        ("Remote", None),
        ("Amsterdam, Netherlands", "OTHER"),
    ],
)
def test_country_requires_unambiguous_documentary_country(location, expected):
    assert application_country(location) == expected


def test_existing_unknown_worker_page_is_never_replaced(environment):
    pipeline, flow, intake, worker, _ = environment
    worker.state.update(
        batch_id="old-batch",
        jobs=[
            {
                "application_id": "old",
                "status": "needs_recheck",
                "page_open": True,
                "intent": {"action": "open"},
            }
        ],
    )
    original = worker.snapshot()
    pipeline.start(request_id="old-page")
    stopped = advance(pipeline, "blocked")
    assert stopped["control"] == "paused"
    assert worker.snapshot() == original
    assert not any(call[0] in {"prepare", "worker_resume", "worker_pause"} for call in flow.calls)


def test_restart_never_replays_mail_or_model_stage(environment):
    pipeline, flow, intake, worker, _ = environment
    pipeline.start(request_id="restart")
    pipeline._tick()
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        assert reopened.snapshot()["status"] == "interrupted"
        before = deepcopy(flow.calls), len(intake.calls)
        reopened._tick()
        reopened.start(request_id="restart")
        reopened._tick()
        assert (flow.calls, len(intake.calls)) == before
        assert reopened.snapshot()["control"] == "paused"
    finally:
        reopened.close()


def test_authorization_is_exact_and_revoked_on_pause(environment):
    pipeline, flow, _, _, _ = environment
    pipeline.start(request_id="exact-grant")
    advance(pipeline, "starting_worker")
    state = pipeline.snapshot()
    receipt = state["transmission_authorization"]
    task = flow.snapshot(state["active_task_id"])["active_task"]
    # Preparation has completed, so the receipt cannot authorize a second prepare.
    assert not pipeline.verify_authorization(receipt, task)
    for key in ("resume_id", "resume_sha256", "application_id", "intake_run_id", "country"):
        altered = receipt | {key: "changed"}
        assert not pipeline.verify_authorization(altered, task)
    pipeline.pause()
    assert not pipeline.verify_authorization(receipt, task)


def test_native_preflight_rejection_waits_only_when_task_unchanged(environment):
    pipeline, flow, _, _, _ = environment
    original = flow.prepare_worker
    attempts = []

    def waiting(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise PortalDataError("installed_write_preflight_required", "Waiting", 409)
        return original(*args, **kwargs)

    flow.prepare_worker = waiting
    pipeline.start(request_id="native-wait")
    waiting_state = advance(pipeline, "awaiting_native_check")
    assert waiting_state["control"] == "running"
    assert waiting_state["notification"] is None
    advance(pipeline, "filling")
    assert len(attempts) == 2


def test_no_retry_after_prepare_changes_task_and_fails(environment):
    pipeline, flow, _, _, _ = environment
    calls = []

    def uncertain(identifier, *_args, **_kwargs):
        calls.append(identifier)
        flow.tasks[identifier]["worker_preparation"] = {"status": "pending"}
        raise PortalDataError("installed_write_preflight_required", "Unknown", 409)

    flow.prepare_worker = uncertain
    pipeline.start(request_id="unknown-prepare")
    advance(pipeline, "needs_recheck")
    pipeline._tick()
    assert len(calls) == 1


def test_backend_heartbeat_uses_own_controller_without_frontend(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="heartbeat")
    advance(pipeline, "filling")
    pipeline._tick()
    assert any(call[0] == "worker_heartbeat" for call in flow.calls)
    worker.state["controller"] = "other-window"
    previous = deepcopy(flow.calls)
    stopped = advance(pipeline, "needs_recheck")
    assert stopped["control"] == "paused"
    assert flow.calls == previous


def test_historical_intake_rows_never_enter_cycle(environment):
    pipeline, flow, intake, _, jobs = environment
    # This recommendation was not in the source-chain of the current mail run.
    historical = flow.applications.create_application(
        {
            "company": "Historical",
            "role_title": "ML Engineer",
            "url": "https://example.com/historical",
            "location": "Switzerland",
            "job_description": "Python",
        }
    )
    intake.state["recommendations"] = [{"application_id": historical["id"]}]
    pipeline.start(request_id="scope")
    state = advance(pipeline, "filling")
    assert {item["application_id"] for item in state["items"]} == {job["id"] for job in jobs}
    assert not any(call[1] == historical["id"] for call in flow.calls)


def test_no_fields_are_sent_when_country_not_in_source(environment):
    pipeline, flow, _, _, jobs = environment
    for job in jobs:
        flow.applications.update_application(job["id"], {"location": "Remote"}, job["revision"])
    pipeline.start(request_id="missing-country")
    state = advance(pipeline, "needs_input")
    assert "国家" in state["notification"]["message"]
    assert not any(call[0] in {"prepare", "worker_resume"} for call in flow.calls)


def test_legacy_cycle_deadline_does_not_stop_a_healthy_owned_worker(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="expiry")
    advance(pipeline, "filling")
    state = pipeline._load()
    state["expires_at"] = 0
    pipeline._save(state)
    pipeline._tick()
    current = pipeline.snapshot()
    assert current["status"] == "filling" and current["control"] == "running"
    assert worker.state["control"] == "running"
    pipeline.pause()
    assert pipeline.snapshot()["control"] == "paused"
    assert worker.state["control"] == "paused"
    calls = deepcopy(flow.calls)
    pipeline._tick()
    assert flow.calls == calls


@pytest.mark.parametrize("authorized", [False, True])
def test_real_flow_internal_authorization_cannot_be_supplied_without_verifier(tmp_path, authorized):
    import time

    from career_evidence_graph.application_flow import ApplicationFlowService

    (tmp_path / "applications").mkdir()
    apps = ApplicationStore(tmp_path / "applications")
    job = apps.create_application(
        {
            "company": "Example",
            "role_title": "ML Engineer",
            "url": "https://example.com/job",
            "location": "Switzerland",
            "job_description": "Python",
        }
    )
    prepared = []
    receipt = {"country": "CHE", "authorization_id": "once-workflow-grant"}
    callbacks = {
        "analysis": lambda _: {"id": "analysis", "requirements": []},
        "resume": lambda _: {"id": "pdf", "pdf_sha256": "b" * 64},
        "verify_materials": lambda _: None,
        "prepare_worker": lambda task, country: (
            prepared.append(task) or {"batch_id": "batch", "job_id": job["id"], "status": "queued"}
        ),
    }
    if authorized:
        callbacks["verify_automation_authorization"] = lambda candidate, task: candidate == receipt
    flow = ApplicationFlowService(apps, tmp_path / "flow", callbacks=callbacks)
    try:
        task = flow.create(job["id"], job["revision"])
        for stage, expected in (("analysis", "analysis_ready"), ("resume", "resume_ready")):
            flow.start(task["id"], task["revision"], stage)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                task = flow.snapshot(task["id"])["active_task"]
                if task["status"] == expected:
                    break
                time.sleep(0.01)
            assert task["status"] == expected
        if not authorized:
            with pytest.raises(PortalDataError) as error:
                flow.prepare_worker(
                    task["id"], task["revision"], "CHE", True, automation_authorization=receipt
                )
            assert error.value.code == "flow_automation_authorization_invalid"
            assert not prepared
        else:
            flow.prepare_worker(
                task["id"], task["revision"], "CHE", True, automation_authorization=receipt
            )
            approval = prepared[0]["send_approval"]
            assert approval["actor"] == "system" and approval["verified_by"] == "workflow_policy"
            assert approval["authorization"] == receipt
            assert prepared[0]["material_binding"]["human_reviewed"] is False
    finally:
        flow.close()


@pytest.mark.parametrize(
    "location",
    [
        "Switzerland / Iceland",
        "Switzerland or South Africa",
        "Iceland, Switzerland",
        "Switzerland, Iceland",
    ],
)
def test_country_does_not_drop_an_unhandled_second_country(location):
    assert application_country(location) is None


def test_failed_heartbeat_pauses_actual_owned_worker_before_notification(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="heartbeat-failed")
    advance(pipeline, "filling")
    original = flow.worker_action

    def failing(identifier, revision, operation, payload):
        if operation == "heartbeat":
            raise PortalDataError("installed_write_preflight_required", "Expired proof", 409)
        return original(identifier, revision, operation, payload)

    flow.worker_action = failing
    advance(pipeline, "needs_recheck")
    assert worker.state["control"] == "paused"


def test_derived_send_approval_requires_intact_bound_workflow_grant(environment):
    from career_evidence_graph.application_single_binding import valid_send_approval

    pipeline, flow, _, _, _ = environment
    pipeline.start(request_id="policy-proof")
    advance(pipeline, "starting_worker")
    state = pipeline.snapshot()
    task = flow.snapshot(state["active_task_id"])["active_task"]
    receipt = state["transmission_authorization"]
    task["send_approval"] = {
        "confirmed": True,
        "verified_by": "workflow_policy",
        "actor": "system",
        "human_reviewed": False,
        "authorization": receipt,
        "country": receipt["country"],
        "job_url": receipt["job_url"],
        **{key: task[key] for key in ("resume_id", "resume_sha256", "analysis_id", "inputs")},
    }
    assert valid_send_approval(task, flow.root, require_active=True)
    assert not valid_send_approval(task, None)
    for key, value in (
        ("verified_by", "user"),
        ("human_reviewed", True),
        ("country", "USA"),
        ("job_url", "https://other.example/job"),
    ):
        changed = deepcopy(task)
        changed["send_approval"][key] = value
        assert not valid_send_approval(changed, flow.root)
    changed = deepcopy(task)
    changed["resume_sha256"] = "c" * 64
    assert not valid_send_approval(changed, flow.root)
    pipeline.pause()
    assert valid_send_approval(task, flow.root)  # Read-only provenance survives pause.
    assert not valid_send_approval(task, flow.root, require_active=True)


def test_needs_input_keeps_owned_worker_lease_and_continues_after_autosave(environment):
    pipeline, flow, _, worker, _ = environment
    pipeline.start(request_id="new-fact")
    advance(pipeline, "filling")
    worker.state["jobs"][0]["status"] = "needs_input"
    waiting = advance(pipeline, "needs_input")
    assert waiting["control"] == "running" and worker.state["control"] == "running"
    notification = waiting["notification"]
    pipeline._tick()
    assert pipeline.snapshot()["notification"] == notification
    assert any(call[0] == "worker_heartbeat" for call in flow.calls)
    worker.state["jobs"][0]["status"] = "filling"
    resumed = advance(pipeline, "filling")
    assert resumed["control"] == "running" and resumed["notification"] is None
    assert sum(call[0] == "worker_resume" for call in flow.calls) == 1


def test_second_mail_cycle_after_empty_read_preserves_history_and_old_request(environment):
    pipeline, _, intake, _, _ = environment
    intake.jobs = []
    pipeline.start(request_id="empty-one")
    first = advance(pipeline, "no_matches")
    pipeline.start(request_id="empty-two")
    second = advance(pipeline, "no_matches")
    assert second["id"] != first["id"]
    assert len(intake.calls) == 2
    assert second["history"][0]["id"] == first["id"]
    retained = helper.read_json_object(
        pipeline.path.parent / second["history"][0]["path"], "prior cycle"
    )
    assert retained["authorization"] == first["authorization"]
    pipeline.start(request_id="empty-one")
    pipeline._tick()
    assert len(intake.calls) == 2 and pipeline.snapshot()["id"] == second["id"]


def test_explicit_start_after_paused_filling_does_not_replay_existing_page(environment):
    pipeline, flow, _, _, _ = environment
    pipeline.start(request_id="original")
    advance(pipeline, "filling")
    pipeline.pause()
    before = deepcopy(flow.calls)
    result = pipeline.start(request_id="continue")
    assert result["status"] == "needs_recheck" and result["control"] == "paused"
    pipeline._tick()
    assert flow.calls == before


@pytest.mark.parametrize(
    "location",
    [
        "Remote - join us",
        "Remote - can work anywhere",
        "Remote - ask Can about us",
        "Remote - fra team",
        "Remote - che team",
        "Remote - deu team",
        "Remote - gbr team",
    ],
)
def test_country_codes_do_not_match_ordinary_words_case_insensitively(location):
    assert application_country(location) is None


@pytest.mark.parametrize(
    "location, expected",
    [
        ("Toronto, CAN", "CAN"),
        ("Remote, US", "USA"),
        ("Zurich, CHE", "CHE"),
        ("London, GBR", "GBR"),
        ("Paris, FRA", "FRA"),
        ("Berlin, DEU", "DEU"),
        ("toronto, canada", "CAN"),
        ("zurich, switzerland", "CHE"),
        ("remote, united states", "USA"),
        ("london, united kingdom", "GBR"),
    ],
)
def test_explicit_uppercase_codes_and_case_insensitive_country_names(location, expected):
    assert application_country(location) == expected


@pytest.mark.parametrize(
    "location",
    [
        "Remote (excluding US)",
        "Remote outside Canada",
        "Remote, not Switzerland",
        "Remote - CONTACT US",
    ],
)
def test_excluded_countries_and_uppercase_call_to_action_do_not_set_scope(location):
    assert application_country(location) is None


@pytest.mark.parametrize(
    "location, expected",
    [
        ("US", "USA"),
        ("CAN", "CAN"),
        ("Toronto, CAN", "CAN"),
        ("Remote (US)", "USA"),
        ("Remote US", "USA"),
    ],
)
def test_country_code_is_an_explicit_location_component(location, expected):
    assert application_country(location) == expected


@pytest.mark.parametrize(
    "location",
    [
        "Remote - non-US",
        "Non-US",
        "Remote, non-Canada",
        "Remote, other than Switzerland",
    ],
)
def test_negative_country_prefix_and_other_than_never_establish_scope(location):
    assert application_country(location) is None


@pytest.mark.parametrize(
    "location",
    [
        "Travel to Canada",
        "Contact our team in Switzerland",
        "Switzerland, travel to Canada",
    ],
)
def test_country_names_in_prose_do_not_establish_a_positive_location(location):
    assert application_country(location) is None


@pytest.mark.parametrize(
    "location", ["Zurich, Switzerland", "Remote in Switzerland", "Switzerland Remote"]
)
def test_positive_country_location_components_remain_supported(location):
    assert application_country(location) == "CHE"


def fail_analysis(flow, identifiers, *, code="match_attribution_invalid", mutate=None):
    original = flow.start

    def failing(identifier, revision, stage):
        if stage != "analysis" or identifier not in identifiers:
            return original(identifier, revision, stage)
        task = flow.tasks[identifier]
        flow.calls.append(("analysis", identifier))
        task.update(
            status="failed",
            analysis_id=None,
            resume_id=None,
            resume_sha256=None,
            materials_confirmed=False,
            artifacts=[],
            stages={
                "analysis": {"status": "failed", "error_code": code, "attempt_id": "c" * 32},
                "resume": {"status": "pending"},
            },
        )
        if mutate:
            mutate(task)
        return deepcopy(task)

    flow.start = failing


def stop_at_legacy_analysis_failure(pipeline, flow, target):
    for _ in range(20):
        pipeline._tick()
        if flow.tasks.get(target, {}).get("status") == "failed":
            state = pipeline._load()
            pipeline._stop(state, "needs_recheck", "岗位已有其他阶段或未知结果，保留原任务。")
            return pipeline.snapshot()
    pytest.fail("Known failed analysis was not reached")


@pytest.mark.parametrize(
    "code",
    [
        "match_model_invalid",
        "match_requirement_conflict",
        "match_source_invalid",
        "match_attribution_invalid",
    ],
)
def test_known_internal_analysis_failure_continues_other_jobs_without_retry(environment, code):
    pipeline, flow, _, _, jobs = environment
    fail_analysis(flow, {jobs[0]["id"]}, code=code)
    pipeline.start(request_id="skip-known-failure")
    state = advance(pipeline, "filling")
    failed = next(row for row in state["items"] if row["application_id"] == jobs[0]["id"])
    assert failed["status"] == "analysis_failed"
    assert failed["reason"] == code
    assert failed["analysis_attempt_id"] == "c" * 32
    assert state["active_task_id"] == jobs[1]["id"]
    assert sum(call == ("analysis", jobs[0]["id"]) for call in flow.calls) == 1
    assert flow.tasks[jobs[0]["id"]]["status"] == "failed"
    assert flow.tasks[jobs[0]["id"]]["artifacts"] == []


def test_all_known_analysis_failures_stop_without_generating_or_starting_worker(environment):
    pipeline, flow, _, _, jobs = environment
    fail_analysis(flow, {job["id"] for job in jobs})
    pipeline.start(request_id="all-failed")
    state = advance(pipeline, "needs_input")
    assert all(row["status"] == "analysis_failed" for row in state["items"])
    assert not any(call[0] in {"resume", "prepare", "worker_resume"} for call in flow.calls)


@pytest.mark.parametrize(
    "code,mutate",
    [
        ("flow_interrupted", None),
        ("match_timeout", None),
        ("match_unknown", None),
        ("match_config_invalid", None),
        ("match_attribution_invalid", lambda task: task.update(analysis_id="unexpected")),
        ("match_attribution_invalid", lambda task: task.update(worker_ref={"batch_id": "old"})),
        ("match_attribution_invalid", lambda task: task.update(artifacts=[{"stage": "analysis"}])),
        (
            "match_attribution_invalid",
            lambda task: task["stages"].update(resume={"status": "queued"}),
        ),
    ],
)
def test_unknown_or_later_stage_failure_keeps_whole_pipeline_stopped(environment, code, mutate):
    pipeline, flow, _, _, jobs = environment
    fail_analysis(flow, {jobs[0]["id"]}, code=code, mutate=mutate)
    pipeline.start(request_id="unknown-failure")
    state = advance(pipeline, "needs_recheck")
    assert state["control"] == "paused"
    assert ("analysis", jobs[1]["id"]) not in flow.calls


@pytest.mark.parametrize(
    "code",
    [
        "match_model_invalid",
        "match_requirement_conflict",
        "match_source_invalid",
        "match_attribution_invalid",
    ],
)
def test_explicit_start_recovers_only_matching_without_reread_or_failed_stage_retry(
    environment, code
):
    pipeline, flow, intake, _, jobs = environment
    fail_analysis(flow, {jobs[0]["id"]}, code=code)
    pipeline.start(request_id="initial")
    before = stop_at_legacy_analysis_failure(pipeline, flow, jobs[0]["id"])
    failed_task = deepcopy(flow.tasks[jobs[0]["id"]])
    intake.state.update(run_id="d" * 32, status="running")
    resumed = pipeline.start(request_id="explicit-recover")
    assert resumed["status"] == "matching" and resumed["control"] == "running"
    for key in ("id", "authorization", "intake_run_id", "started_at"):
        assert resumed[key] == before[key]
    advance(pipeline, "filling")
    assert len(intake.calls) == 1
    assert sum(call == ("analysis", jobs[0]["id"]) for call in flow.calls) == 1
    assert flow.tasks[jobs[0]["id"]] == failed_task


def test_analysis_recovery_leaves_unrelated_unknown_worker_untouched(environment):
    pipeline, flow, _, worker, jobs = environment
    fail_analysis(flow, {jobs[0]["id"]})
    worker.state.update(
        batch_id="historical",
        jobs=[
            {
                "application_id": "old-job",
                "status": "needs_recheck",
                "page_open": True,
                "intent": {"action": "open"},
                "handed_off": True,
            }
        ],
    )
    original_worker = worker.snapshot()
    pipeline.start(request_id="initial")
    stop_at_legacy_analysis_failure(pipeline, flow, jobs[0]["id"])
    assert pipeline.start(request_id="recover")["status"] == "matching"
    advance(pipeline, "blocked")
    assert worker.snapshot() == original_worker
    assert ("analysis", jobs[1]["id"]) in flow.calls
    assert not any(call[0].startswith("worker_") or call[0] == "prepare" for call in flow.calls)


def test_pipeline_snapshot_projects_job_labels_without_changing_persisted_checksum(environment):
    pipeline, _, _, _, jobs = environment
    pipeline.start(request_id="labels")
    advance(pipeline, "matching")
    before = pipeline.path.read_bytes()
    projected = pipeline.snapshot()
    assert projected["items"][0]["company"] == jobs[0]["company"]
    assert projected["items"][0]["role_title"] == jobs[0]["role_title"]
    assert pipeline.path.read_bytes() == before
    assert "company" not in pipeline._load()["items"][0]


@pytest.mark.parametrize(
    "change",
    ["different_stage", "analysis_result", "worker_reference", "own_batch", "changed_source_chain"],
)
def test_known_matching_recovery_rejects_other_stages_unknown_outputs_and_changed_scope(
    environment, change
):
    pipeline, flow, intake, _, jobs = environment
    fail_analysis(flow, {jobs[0]["id"]})
    pipeline.start(request_id="initial")
    stop_at_legacy_analysis_failure(pipeline, flow, jobs[0]["id"])
    state = pipeline._load()
    if change == "different_stage":
        state["status"] = "ready_for_review"
    elif change == "analysis_result":
        flow.tasks[jobs[0]["id"]]["analysis_id"] = "unknown-result"
    elif change == "worker_reference":
        flow.tasks[jobs[0]["id"]]["worker_ref"] = {"batch_id": "unknown"}
    elif change == "own_batch":
        state["worker_batch_id"] = "unknown"
    else:
        chain = intake.root / "runs" / state["intake_run_id"] / "source-chain.json"
        helper.atomic_write_json(chain, {"sources": []})
    pipeline._save(state)
    assert pipeline.snapshot()["can_resume_matching"] is False
    before = pipeline.path.read_bytes()
    calls = deepcopy(flow.calls)
    with pytest.raises(PortalDataError, match="原自动流程"):
        pipeline.start(request_id="recover")
    assert pipeline.path.read_bytes() == before
    assert flow.calls == calls and len(intake.calls) == 1


def test_can_resume_matching_is_read_only_and_accepts_another_completed_analysis(environment):
    pipeline, flow, _, _, jobs = environment
    fail_analysis(flow, {jobs[1]["id"]})
    pipeline.start(request_id="initial")
    advance(pipeline, "matching")
    # Historical matching analyzed a batch before entering materials. Construct
    # that retained checkpoint without advancing the new sequential scheduler.
    state = pipeline._load()
    for item, application in zip(state["items"], jobs, strict=True):
        task = flow.create(application["id"], application["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        item.update(task_id=task["id"], status="matching")
    state["items"][0].update(
        status="matched",
        score={"coverage": 100.0, "eligibility": "not_specified", "lower": 50.0, "upper": 50.0},
    )
    pipeline._stop(state, "needs_recheck", "岗位已有其他阶段或未知结果，保留原任务。")
    before = pipeline.path.read_bytes()
    tasks = deepcopy(flow.tasks)
    assert pipeline.snapshot()["can_resume_matching"] is True
    assert pipeline.path.read_bytes() == before and flow.tasks == tasks
    assert "can_resume_matching" not in pipeline._load()
    resumed = pipeline.start(request_id="recover")
    assert resumed["status"] == "matching" and resumed["can_resume_matching"] is False


def test_unknown_qualification_continues_preparation_without_becoming_confirmed(environment):
    from career_evidence_graph.application_flow import task_eligibility

    pipeline, flow, _, _, _ = environment
    original = flow.start

    def start(identifier, revision, stage):
        result = original(identifier, revision, stage)
        if stage == "analysis":
            requirement = flow.tasks[identifier]["artifacts"][-1]["result"]["requirements"][0]
            requirement.update(hard_condition=True, judgment="unknown")
        return result

    flow.start = start
    pipeline.start(request_id="unknown-qualification")
    state = advance(pipeline, "filling")
    task = flow.tasks[state["active_task_id"]]
    assert task_eligibility(task)["status"] == "needs_input"
    assert any(call[0] == "prepare" for call in flow.calls)


def test_a_qualification_conflict_names_the_hard_conditions_not_met(environment):
    pipeline, flow, _, _, _ = environment
    original = flow.start

    def start(identifier, revision, stage):
        result = original(identifier, revision, stage)
        if stage == "analysis":
            requirement = flow.tasks[identifier]["artifacts"][-1]["result"]["requirements"][0]
            requirement.update(
                text="Speak German at a native level.", hard_condition=True, judgment="gap"
            )
        return result

    flow.start = start
    pipeline.start(request_id="qualification-conflict")
    state = advance(pipeline, "needs_input")
    item = next(row for row in state["items"] if row.get("reason") == "flow_eligibility_required")
    assert state["wait_reason"] == "qualification_conflict"
    assert item["mismatch"] == ["Speak German at a native level."]
    # A job stopped before the field existed learns it on the next running tick.
    saved = pipeline._load()
    for row in saved["items"]:
        row.pop("mismatch", None)
    pipeline._advance(saved)
    assert pipeline._load()["items"][0]["mismatch"] == ["Speak German at a native level."]


@pytest.mark.parametrize(
    "upper,review,tier",
    [
        (14.9, False, "skip"),
        (15, False, "auto"),
        (54.9, False, "auto"),
        (55, False, "approve"),
        (74.9, False, "approve"),
        (75, False, "manual"),
        (10, True, "approve"),
        (40, True, "approve"),
        (90, True, "manual"),
    ],
)
def test_score_tiers_lean_toward_the_user_near_each_line(upper, review, tier):
    from career_evidence_graph.application_match_scoring import score_tier

    # Decided 2026-10-31: lines at 20/60/80 with a 5-point margin toward more involvement.
    score = {"lower": upper - 5, "upper": upper, "coverage": 95, "eligibility": "not_specified"}
    assert score_tier(score, needs_review=review) == tier


@pytest.mark.parametrize(
    ("record", "country"),
    [
        ({"location": "Zurich, Switzerland", "job_description": ""}, "CHE"),
        # 2026-11-08, Mistral: only the page's structured field named the country.
        (
            {
                "location": "Zurich",
                "job_description": "Job location\naddress: addressCountry: Switzerland",
            },
            "CHE",
        ),
        ({"location": "Zurich", "job_description": "We are based in Zurich."}, None),
        (
            {
                "location": "Zurich",
                "job_description": "addressCountry: Switzerland\naddressCountry: France",
            },
            None,
        ),
    ],
)
def test_a_job_country_falls_back_to_the_pages_structured_country(record, country):
    from career_evidence_graph.job_screening import job_country

    assert job_country(record) == country
