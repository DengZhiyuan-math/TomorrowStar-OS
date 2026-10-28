"""Bounded baseline on isolated synthetic pages and a fixed model substitute."""

import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_cua_worker import COMBOBOX
from test_generic_worker import FIELDS, URL

from career_evidence_graph.application_resume import ApplicationResumeStore, export_pdf
from career_evidence_graph.application_worker import WorkerService, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog
from career_evidence_graph.cua_driver import managed_cua_browser
from career_evidence_graph.worker_measurement import MeasurementLog

CASES = [
    f"{engine}-{temperature}-{repeat}"
    for engine in ("native", "cua")
    for repeat in range(1, 4)
    for temperature in ("cold", "warm")
] + ["shared-answer", "unknown-send", "paused-answer", "restart"]
pytestmark = [
    pytest.mark.worker_browser,
    pytest.mark.skipif(
        os.environ.get("TS_MEASUREMENT_BASELINE") != "1",
        reason="Explicit synthetic baseline opt-in",
    ),
]


@pytest.fixture(scope="module")
def baseline_runtime(tmp_path_factory):
    from playwright.sync_api import sync_playwright

    root = tmp_path_factory.mktemp("measurement-runtime")
    with sync_playwright() as playwright:
        stack = ExitStack()
        state = {
            "playwright": playwright,
            "stack": stack,
            "context": None,
            "cua": None,
            "root": root,
            "logs": [],
        }
        try:
            yield state
        finally:
            state["stack"].close()
            for log, destination in state["logs"]:
                if log.path.exists():
                    shutil.copyfile(log.path, destination / "measurements.jsonl")
                summary_path = destination / "summary.json"
                if summary_path.exists():
                    result = json.loads(summary_path.read_text())
                    result.update(log.summary())
                    summary_path.write_text(json.dumps(result, indent=2) + "\n")


def open_runtime(pool, log, *, cold, cua):
    if cold or pool["context"] is None:
        pool["stack"].close()
        pool["stack"] = ExitStack()
        with log.stage("runtime_start"):
            if cua:
                context, driver = pool["stack"].enter_context(
                    managed_cua_browser(
                        pool["playwright"], log.root, click_route="dom_event", origins=[URL]
                    )
                )
            else:
                browser = pool["playwright"].chromium.launch(headless=True, channel="chromium")
                pool["stack"].callback(browser.close)
                context, driver = browser.new_context(offline=True, service_workers="block"), None
            context.set_offline(True)
            context.set_default_timeout(4000)
            pool.update(context=context, cua=driver)
    return pool["context"], pool["cua"]


def advance(runner, predicate, service, limit=30):
    for _ in range(limit):
        runner.tick()
        state = service.snapshot()
        if predicate(state):
            return state
    raise AssertionError("Synthetic fixture did not reach its expected outcome")


@pytest.mark.parametrize("case", CASES)
def test_synthetic_measurement_baseline(tmp_path, monkeypatch, baseline_runtime, case):
    destination = Path(os.environ["TS_MEASUREMENT_REPORT_DIR"]) / case
    destination.mkdir(parents=True, exist_ok=False)
    apps, career, worker = (tmp_path / part for part in ("apps", "career", "worker"))
    apps.mkdir()
    profile = career / "reports/public-site/site-content.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        json.dumps(
            {
                "schema_version": "public-site-source/v1",
                "profile": {
                    "name": "Synthetic Person",
                    "education": [
                        {
                            "institution": "Synthetic University",
                            "degree": "Mathematics",
                            "period": "2020–2024",
                            "detail": "",
                        }
                    ],
                },
            }
        )
    )
    service = WorkerService(ApplicationStore(apps), worker, live=True, generic=True)
    monkeypatch.setattr(service, "spawn", lambda: None)
    log = service.store.measurements
    baseline_runtime["logs"].append((log, destination))

    def export(html, pdf):
        with ThreadPoolExecutor(max_workers=1) as threads:
            threads.submit(export_pdf, html, pdf).result()

    resumes = ApplicationResumeStore(
        service.store.applications,
        CareerCatalog(career),
        worker / "resumes",
        exporter=export,
        tailorer=lambda draft, *args: draft | {"generation": "codex"},
    )
    resumes.measurements = log
    resumes.model_mode = "synthetic"
    count = 2 if case == "shared-answer" else 1
    warm = "warm" in case
    cua_mode = case.startswith("cua-") or case == "unknown-send"
    items = []
    setup = tmp_path / "setup"
    setup.mkdir()
    for index in range(count):
        app = service.store.applications.create_application(
            {
                "company": "Synthetic",
                "role_title": "Engineer",
                "status": "drafting",
                "url": URL.replace("42", str(42 + index)),
                "application_strategy": "batch",
            }
        )
        if warm:
            resumes.measurements = MeasurementLog(setup)
            resumes.generate(app["id"], app["revision"])
            resumes.measurements = log
        draft = resumes.generate(app["id"], app["revision"])
        items.append(
            {
                "application_id": app["id"],
                "revision": app["revision"],
                "country": "CHE",
                "filename": draft["filename"],
                "file_base64": draft["file_base64"],
                "measurement_id": draft["measurement_id"],
            }
        )
    service.request("prepare", {"jobs": items, "workflow": "batch"})
    for question, value in [
        ("Full name", "Synthetic Person"),
        ("Email", "synthetic@example.invalid"),
    ]:
        service.store.answers.put_answer(
            {
                "question": question,
                "value": value,
                "scope": {},
                "state": "confirmed",
                "source": "synthetic",
            }
        )
    missing = case in {"shared-answer", "paused-answer"}
    if not missing:
        service.store.answers.put_answer(
            {
                "question": "Application country",
                "value": "Switzerland",
                "scope": {},
                "state": "confirmed",
                "source": "synthetic",
            }
        )
    context, cua = open_runtime(baseline_runtime, log, cold=not warm, cua=cua_mode)
    start_run(service.store)
    service.request("resume", {"controller": "synthetic-controller"})
    runner = ApplicationRunner(service.store, context, cua=cua)
    control = (
        COMBOBOX
        if cua_mode
        else """<label for='country'>Application country *</label>
    <select id='country' name='country' required><option value=''>Choose</option>
    <option>Switzerland</option></select>"""
    )
    if missing:
        control = """<label for='sponsor'>
        Will you now or in the future require visa sponsorship? *</label>
        <select id='sponsor' name='sponsor' required><option value=''>Choose</option>
        <option>Yes</option><option>No</option></select>"""
    if case == "unknown-send":
        control = control.replace(
            "combo.value='Switzerland';",
            "fetch('/submit',{method:'POST',body:'synthetic'}).catch(()=>{});"
            "combo.value='Switzerland';",
        )
    html = (
        "<title>Engineer — Synthetic Careers</title><h1>Engineer</h1><form>"
        + FIELDS
        + control
        + "</form>"
    )
    sent, blocked = [], []

    def intercept(route):
        class Route:
            request = route.request

            def fetch(self, **options):
                assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                if self.request.method != "GET":
                    sent.append(self.request.method)
                return SimpleNamespace(status=200, dispose=lambda: None)

            def fulfill(self, *, response):
                route.fulfill(status=response.status, body=html, content_type="text/html")

            def abort(self, reason):
                if self.request.method != "GET":
                    blocked.append(self.request.method)
                route.abort(reason)

        runner._live_guard(Route())

    original_process = ApplicationRunner.process

    def traced_process(self, job, batch_id):
        try:
            return original_process(self, job, batch_id)
        except Exception as error:
            with (destination / "synthetic-error.log").open("a") as diagnostic:
                diagnostic.write(str(error) + "\n")
            raise

    monkeypatch.setattr(ApplicationRunner, "process", traced_process)
    context.route("**/*", intercept)
    failure = None
    checkpoints = []
    try:
        if missing:
            waiting = advance(
                runner, lambda s: all(j["status"] == "needs_input" for j in s["jobs"]), service
            )
            assert len(waiting["input_items"]) == 1
            time.sleep(0.04)  # An observed scripted wait, not human effort.
            if case == "paused-answer":
                service.request("pause", {"controller": "synthetic-controller"})
            job = waiting["jobs"][0]
            service.request(
                "answer",
                {
                    "application_id": job["application_id"],
                    "question_id": job["questions"][0]["id"],
                    "value": "No",
                },
            )
            if case == "paused-answer":
                before = service.store.load()["jobs"][0]["observations"]
                runner.tick()
                assert service.store.load()["control"] == "paused"
                assert service.store.load()["jobs"][0]["observations"] == before
                time.sleep(0.04)
                service.request("resume", {"controller": "synthetic-controller"})
        if case == "restart":
            runner.tick()
            job = service.store.load()["jobs"][0]
            assert runner.authorize(
                job,
                service.store.load()["batch_id"],
                {"action": "fill", "field_id": "synthetic-pending"},
            )
            runner.event("worker_stopped")
            runner.tick()
            checkpoints.append(
                {
                    "state": "stopped",
                    "intent_pending": bool(service.store.load()["jobs"][0]["intent"]),
                }
            )
            for page in list(runner.pages.values()):
                page.close()
            start_run(service.store)
            job = service.store.load()["jobs"][0]
            service.request(
                "resolve-action",
                {
                    "application_id": job["application_id"],
                    "intent_ref": job["intent"]["attempt_id"],
                    "conclusion": "not_applied",
                    "source": "Synthetic injection stopped before mutation",
                },
            )
            service.request(
                "recheck", {"application_id": job["application_id"], "acknowledge": True}
            )
            runner = ApplicationRunner(service.store, context)
            context.route("**/*", intercept)
            service.request("resume", {"controller": "synthetic-controller"})
        if case == "unknown-send":
            state = advance(runner, lambda s: s["jobs"][0]["status"] == "needs_recheck", service)
            job = state["jobs"][0]
            assert job["reason"] == "unverified_send_path"
            assert job["intent"] is not None
            checkpoints.append(
                {"state": "blocked", "reason": job["reason"], "intent_pending": True}
            )
            service.request("cancel-job", {"application_id": job["application_id"]})
            runner.tick()
            assert service.store.load()["jobs"][0]["intent"] == job["intent"]
        elif case == "restart":
            state = advance(runner, lambda s: s["jobs"][0]["status"] == "needs_recheck", service)
            assert state["jobs"][0]["reason"] == "recovered_result_not_visible"
            assert (
                runner.pages[items[0]["application_id"]].locator("input[name=person]").input_value()
                == ""
            )
            checkpoints.append(
                {
                    "state": "blocked",
                    "reason": "recovered_result_not_visible",
                    "old_verified_result_visible": False,
                }
            )
        else:
            state = advance(
                runner,
                lambda s: all(
                    j["status"] == "ready_for_review" and not j["pending_sync"] for j in s["jobs"]
                ),
                service,
            )
            assert all(j["intent"] is None and j["page_open"] for j in state["jobs"])
            if cua_mode:
                assert any(
                    o.get("executor") == "cua_driver" for o in state["jobs"][0]["observations"]
                )
        assert sent == []
        assert len(blocked) == (1 if case == "unknown-send" else 0)
    except BaseException as exc:
        failure = type(exc).__name__
        raise
    finally:
        for item in items:
            log.event("observation_end", episode_id=item["measurement_id"])
        summary = log.summary()
        summary.update(
            browser_version=context.browser.version,
            loaded_sources=service.store.load()["runtime"]["source"],
            case=case,
            scenario_result="failed" if failure else "passed",
            failure=failure,
            execution_mode="native_cua_mcp" if cua_mode else "headless_playwright",
            operator_mode="scripted_synthetic",
            runtime_condition="resident" if warm else "new",
            checkpoints=checkpoints,
            real_ats_requests=0,
            external_requests_released=0,
            final_requests_released=len(sent),
            blocked_sends=len(blocked),
            real_model_calls=0,
            model_substitute="fixed draft selection; real model latency and fees unmeasured",
        )
        (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        shutil.copyfile(log.path, destination / "measurements.jsonl")
        if (setup / "measurements.jsonl").exists():
            shutil.copyfile(setup / "measurements.jsonl", destination / "setup-measurements.jsonl")
        if (worker / "cua-runtime.json").exists():
            record = json.loads((worker / "cua-runtime.json").read_text())
            (destination / "runtime.json").write_text(
                json.dumps(
                    {
                        k: record.get(k)
                        for k in (
                            "version",
                            "binary_sha256",
                            "pid",
                            "window_id",
                            "startup_target_count",
                            "window_policy",
                        )
                    },
                    indent=2,
                )
            )
        context.unroute("**/*")
        anchor = context.pages[0] if cua_mode else None
        for page in list(context.pages):
            if page is not anchor:
                page.close()
    assert summary["episodes"]
    assert sum(row["model_calls"] for row in summary["episodes"]) == 0
    assert summary["incomplete"] is False
    if cua_mode:
        assert sum(row["cua_calls"] for row in summary["episodes"]) > 0
    if missing:
        assert summary["intervention_requests"] == 1
        assert len([op for op in summary["user_operations"] if op["operation"] == "answer"]) == 1
