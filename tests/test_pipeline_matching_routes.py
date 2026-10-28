"""APP-06 routes consume complete materials before one precision Continue."""

import time
from copy import deepcopy

import pytest
from test_application_intake import message, page
from test_application_pipeline import Worker, advance
from test_application_pipeline import environment as environment
from test_application_resume import task_resume as task_resume
from test_automatic_complete_materials import SyntheticCompiler
from test_full_latex_generation import full_latex as full_latex
from test_pipeline_current_job import current_pipeline as current_pipeline
from test_pipeline_recommendation_queue import drive

from career_evidence_graph.application_flow import ApplicationFlowService, job_input_revision
from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_pipeline import ApplicationPipeline
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_worker import digest


@pytest.fixture
def routed_pipeline(full_latex, tmp_path, request):
    store, original, sources, analysis, calls, project, _, inputs = full_latex
    decision = getattr(request, "param", {"application_strategy": "manual"})
    job = store.applications.update_application(
        original["id"],
        {
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789012",
            "location": "Zurich, Switzerland",
            **decision,
        },
        original["revision"],
    )
    analysis.update(application_revision=job["revision"], jd_revision=job_input_revision(job))
    analysis["requirements"][0].update(
        text="Operate Python services",
        importance="required",
        judgment="supported",
        hard_condition=False,
    )
    worker = Worker()
    compiler = SyntheticCompiler()
    store.prism_client = compiler
    store.pdf_inspector = lambda raw: 1
    prepared, fetches = [], []

    def generate(task):
        current = store.applications.get_application(task["application_id"])
        return store.generate_for_task(
            current["id"],
            current["revision"],
            source_snapshot=sources,
            analysis=analysis,
            draft_only=True,
            task_inputs=task["inputs"],
            latex_base=task["latex_base"],
        )

    def export(task):
        return store.export_for_draft(
            task["draft_id"],
            task["draft_sha256"],
            task_inputs=task["inputs"],
            export_id=task["stages"]["export"]["attempt_id"],
            prism=task["prism"],
            automatic_materials=task["automatic_materials"],
        )

    def prepare(task, country):
        assert country == "CHE"
        prepared.append(deepcopy(task))
        worker.state.update(
            batch_id="synthetic-batch",
            jobs=[
                {
                    "application_id": job["id"],
                    "status": "queued",
                    "page_open": False,
                    "intent": None,
                    "handed_off": False,
                }
            ],
        )
        return {"batch_id": "synthetic-batch", "job_id": job["id"], "status": "queued"}

    def control(task, operation, payload):
        assert operation in {"resume", "heartbeat", "pause"}
        worker.state.update(controller=payload["controller"])
        if operation == "resume":
            worker.state["control"] = "running"
            worker.state["jobs"][0]["status"] = "filling"
        elif operation == "pause":
            worker.state["control"] = "paused"
        return {
            "batch_id": worker.state["batch_id"],
            "job_id": job["id"],
            "status": worker.state["jobs"][0]["status"],
        }

    flow = ApplicationFlowService(
        store.applications,
        tmp_path / "route-flow",
        input_provider=lambda identifier: {
            "application_revision": store.applications.get_application(identifier)["revision"],
            "inputs": inputs,
        },
        callbacks={
            "analysis": lambda _: analysis,
            "resume": generate,
            "export": export,
            "automatic_latex_base": lambda _: source_snapshot(project, "main.tex"),
            "prism_source": source_snapshot,
            "prism_export_configuration": lambda: digest(compiler.configuration()),
            "verify_draft": lambda task: store.draft(task["draft_id"]),
            "verify_materials": lambda task: store.read_export(task["resume_id"]),
            "prepare_worker": prepare,
            "control_worker": control,
            "automatic_edit_prepare": lambda task: store.prepare_group_review(
                task["draft_id"], task["draft_sha256"], task_inputs=task["inputs"]
            ),
            "automatic_source_save": lambda task, text: store.save_automatic_source(
                task["draft_id"],
                task["draft_sha256"],
                task_inputs=task["inputs"],
                latex_source=text,
            ),
        },
    )

    def fetch(url):
        fetches.append(url)
        return page(url) | {
            "final_url": job["url"],
            "redirects": [{"url": url, "status": 302, "location": job["url"]}],
            "body_text": job["job_description"],
            "job_fields": {
                "title": job["role_title"],
                "company": job["company"],
                "location": job["location"],
            },
        }

    intake = ApplicationIntakeService(
        store.applications,
        tmp_path / "route-intake",
        reader=lambda *_a, **_k: {
            "status": "readable",
            "emails": [message(links=["https://www.linkedin.com/jobs/view/12345"])],
            "provenance": {},
        },
        fetcher=fetch,
    )
    pipeline = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        yield pipeline, flow, intake, worker, store, calls, compiler, prepared, fetches
    finally:
        pipeline.close()
        flow.close()
        intake.close()


def reach(pipeline, statuses):
    for _ in range(250):
        pipeline._tick()
        state = pipeline.snapshot()
        if state["status"] in statuses:
            return state
        time.sleep(0.005)
    pytest.fail(str(pipeline.snapshot()))


@pytest.mark.parametrize(
    "routed_pipeline,reason",
    [
        ({"application_strategy": "manual"}, "已保存的人工分流决定"),
        ({"target_company": "target"}, "已标记为目标公司"),
        ({"compensation_priority": "exceptional"}, "已核对为超高薪资机会"),
        ({"personal_priority": "high"}, "个人优先意愿高"),
        (
            {"jd_match": "strong", "evidence_match": "direct"},
            "已核对 JD 高匹配，并有直接相关经历证据",
        ),
        (
            {"application_strategy": "manual", "jd_match": "weak", "personal_priority": "low"},
            "已保存的人工分流决定",
        ),
    ],
    indirect=["routed_pipeline"],
)
def test_precision_route_exports_complete_draft_then_prepares_original_page_discovery(
    routed_pipeline, reason
):
    pipeline, flow, _intake, worker, store, calls, compiler, prepared, fetches = routed_pipeline
    pipeline.start(request_id="precision-route")
    state = reach(pipeline, {"needs_input", "filling", "needs_recheck", "waiting_for_mail"})
    assert state["status"] == "filling", (state, _intake.snapshot())
    assert state.get("wait_reason") != "precision_adjustment" and state["control"] == "running"
    task = flow.snapshot(state["active_task_id"])["active_task"]
    assert task["materials_confirmed"] is True
    assert "Project 6" in store.read_export(task["resume_id"])["latex_source"]
    assert task["material_binding"]["actor"] == "system"
    assert task["material_binding"]["human_reviewed"] is False
    assert not task.get("material_reviews") and not task.get("group_reviews")
    assert state["items"][0]["application_route"] == "manual"
    assert state["items"][0]["route_reasons"] == [reason]
    assert len(calls) == len(compiler.calls) == len(fetches) == 1
    assert len(prepared) == len(worker.snapshot()["jobs"]) == 1
    assert prepared[0]["send_approval"]["authorization"]["precision_preparation"] is True
    assert worker.snapshot()["jobs"][0]["page_open"] is False


def test_precision_discovery_reopens_paused_without_preparing_the_worker_again(routed_pipeline):
    pipeline, flow, intake, worker, _store, calls, compiler, prepared, fetches = routed_pipeline
    pipeline.start(request_id="precision-reopen")
    waiting = reach(pipeline, {"needs_input", "filling", "waiting_for_mail"})
    assert waiting["status"] == "filling"
    pipeline.pause()
    original_task = flow.snapshot(waiting["active_task_id"])["active_task"]
    pipeline.close()
    reopened = ApplicationPipeline(flow, intake, worker, interval=100)
    try:
        for _ in range(3):
            reopened._tick()
        assert reopened.snapshot()["control"] == "paused"
        assert reopened.snapshot().get("wait_reason") != "precision_adjustment"
        assert flow.snapshot(original_task["id"])["active_task"] == original_task
        assert len(prepared) == len(calls) == len(compiler.calls) == len(fetches) == 1
        assert prepared[0]["resume_id"] == original_task["resume_id"]
        assert not worker.snapshot()["jobs"][0]["page_open"]
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "routed_pipeline",
    [
        {},
        {
            "application_strategy": "batch",
            "personal_priority": "low",
            "jd_match": "weak",
            "evidence_match": "missing",
        },
    ],
    indirect=True,
    ids=["unset-subjective-decisions", "explicit-batch-override"],
)
def test_ordinary_route_reaches_filling_without_subjective_approval(routed_pipeline):
    pipeline, flow, _intake, _worker, _store, calls, compiler, prepared, _fetches = routed_pipeline
    pipeline.start(request_id="ordinary-route")
    state = reach(pipeline, {"filling", "needs_input", "needs_recheck", "waiting_for_mail"})
    assert state["status"] == "filling", state
    assert state["items"][0]["application_route"] in {"review", "batch"}
    assert len(calls) == len(compiler.calls) == len(prepared) == 1
    assert not flow.snapshot(state["active_task_id"])["active_task"].get("material_reviews")


@pytest.mark.parametrize(
    "decision",
    [
        {"personal_priority": "low"},
        {"jd_match": "weak"},
        {"evidence_match": "missing"},
        {"application_strategy": "hold"},
    ],
)
def test_low_route_after_a_skipped_job_advances_in_queue_order(current_pipeline, decision):
    pipeline, flow, _intake, _worker = current_pipeline
    pipeline.start(request_id="skip-then-low")
    first = drive(pipeline, "filling")
    pipeline.skip_current(request_id="leave-first")
    second = drive(pipeline, "matching")
    current_id = second["items"][1]["application_id"]
    app = flow.applications.get_application(current_id)
    flow.applications.update_application(current_id, decision, app["revision"])
    third = drive(pipeline, "filling")
    assert third["active_task_id"] not in {first["active_task_id"], current_id}
    assert [row["status"] for row in third["items"]] == ["skipped", "excluded", "matched"]
    assert third["items"][1]["application_route"] == "hold"
    assert third["items"][1]["reason"]
    assert current_id not in flow.tasks


def test_precision_route_keeps_important_language_conflict_on_current_job(environment):
    from career_evidence_graph.application_worker import WorkerStore

    pipeline, flow, _intake, worker, jobs = environment
    worker.store = WorkerStore(flow.applications, flow.root.parent / "language-worker")
    flow.applications.update_application(
        jobs[0]["id"],
        {"application_strategy": "manual", "job_description": "German B2 required."},
        jobs[0]["revision"],
    )
    for question, value in [("German level", "B2"), ("German proficiency CEFR", "C1")]:
        worker.store.answers.put_answer(
            {"question": question, "value": value, "scope": {}, "state": "confirmed"}
        )
    pipeline.start(request_id="manual-language-conflict")
    waiting = advance(pipeline, "needs_input")
    assert waiting["items"][0]["reason_code"] == "language_information_required"
    assert waiting["items"][1]["status"] == "pending"
    assert flow.tasks == {} and worker.snapshot()["jobs"] == []
    assert waiting["can_resume_matching"] is True


def test_important_analysis_conflict_stops_current_before_next_analysis(environment):
    pipeline, flow, _intake, worker, jobs = environment
    start = flow.start

    def conflicting_analysis(identifier, revision, stage):
        result = start(identifier, revision, stage)
        if stage == "analysis":
            requirement = flow.tasks[identifier]["artifacts"][-1]["result"]["requirements"][0]
            requirement.update(hard_condition=True, judgment="gap")
        return result

    flow.start = conflicting_analysis
    pipeline.start(request_id="qualification-conflict")
    waiting = advance(pipeline, "needs_input")
    assert waiting["active_task_id"] == jobs[0]["id"]
    assert waiting["items"][1]["status"] == "pending"
    assert jobs[1]["id"] not in flow.tasks and worker.snapshot()["jobs"] == []
    assert [call for call in flow.calls if call[0] == "analysis"] == [("analysis", jobs[0]["id"])]


def test_precision_source_edit_is_blocked_until_the_original_page_is_paused(routed_pipeline):
    from career_evidence_graph.career_portal_data import PortalDataError

    pipeline, flow, _intake, _worker, store, calls, compiler, prepared, _fetches = routed_pipeline
    pipeline.start(request_id="precision-edit")
    discovering = reach(pipeline, {"needs_input", "filling"})
    assert discovering["status"] == "filling"
    original = flow.snapshot(discovering["active_task_id"])["active_task"]
    original_source = store.draft(original["draft_id"])["latex_source"]
    original_pdf = store.pdf(original["resume_id"])
    with pytest.raises(PortalDataError) as error:
        flow.begin_automatic_edit(original["id"], original["revision"])
    assert error.value.code == "bound_material_pause_required"
    assert len(prepared) == len(calls) == len(compiler.calls) == 1
    assert store.pdf(original["resume_id"]) == original_pdf
    assert store.draft(original["draft_id"])["latex_source"] == original_source
    assert prepared[0]["material_binding"]["human_reviewed"] is False


@pytest.mark.parametrize(
    "guard",
    [
        {"deadline": "2000-01-01"},
        {"status": "applied"},
        {"url": "http://example.com/jobs/insecure"},
    ],
)
def test_precision_route_never_overrides_independent_admission_guard(environment, guard):
    pipeline, flow, _intake, worker, jobs = environment
    flow.applications.update_application(
        jobs[0]["id"], {"application_strategy": "manual", **guard}, jobs[0]["revision"]
    )
    pipeline.start(request_id="guarded-precision")
    advance(pipeline, "matching")
    pipeline._tick()
    state = pipeline.snapshot()
    assert state["items"][0]["status"] == "excluded"
    assert state["items"][0]["reason"]
    assert flow.calls == [] and worker.snapshot()["jobs"] == []


def test_precision_route_never_overrides_confirmed_language_gap(environment):
    from career_evidence_graph.application_worker import WorkerStore

    pipeline, flow, _intake, worker, jobs = environment
    worker.store = WorkerStore(flow.applications, flow.root.parent / "language-worker")
    worker.store.answers.put_answer(
        {"question": "German level", "value": "A1", "scope": {}, "state": "confirmed"}
    )
    flow.applications.update_application(
        jobs[0]["id"],
        {"application_strategy": "manual", "job_description": "German B2 required."},
        jobs[0]["revision"],
    )
    pipeline.start(request_id="precision-language-gap")
    advance(pipeline, "matching")
    pipeline._tick()
    assert pipeline.snapshot()["items"][0]["status"] == "excluded"
    assert flow.calls == [] and worker.snapshot()["jobs"] == []
