"""Original attempt binding and conservative legacy recovery regressions."""

import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_application_worker import job
from test_application_worker import service as _service
from test_hosted_ats import live_service, prepare
from test_worker_recovery_regressions import UPLOAD_HTML, intercept_uploads, report
from worker_preview_support import advance_until

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError

service = _service


@pytest.mark.parametrize("pending", ["cleared", "replaced", "cancelled"])
def test_late_completion_keeps_original_attempt_and_current_state(service, pending):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    stale = deepcopy(state["jobs"][0])
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    old_intent = {"action": "upload", "sha256": stale["file_sha256"]}
    assert runner.authorize(stale, state["batch_id"], old_intent)
    identifier = stale["application_id"]
    service.request(
        "resolve-action",
        {
            "application_id": identifier,
            "intent_ref": old_intent["attempt_id"],
            "conclusion": "not_applied",
            "source": "Synthetic readback before completion",
        },
    )
    service.request("recheck", {"application_id": identifier, "acknowledge": True})
    next_intent = {"action": "fill", "field_id": "synthetic-next"}
    if pending == "replaced":
        assert runner.authorize(service.store.load()["jobs"][0], state["batch_id"], next_intent)
    elif pending == "cancelled":
        service.request("cancel-job", {"application_id": identifier})
    before = deepcopy(service.store.load()["jobs"][0])
    runner.update(
        stale,
        state["batch_id"],
        completed_intent=old_intent,
        intent=None,
        status="ready_for_review",
        reason="",
    )
    after = service.store.load()["jobs"][0]
    assert after["observations"][-1]["intent"] == old_intent
    assert after["observations"][-1]["result"] == "verified"
    assert ApplicationRunner.recovered_upload(after)
    assert "completed_intent" not in after
    if pending != "cleared":
        assert after["status"] == before["status"] and after["reason"] == before["reason"]
        assert after["intent"] == before["intent"]
    else:
        assert after["intent"] is None


def test_unowned_clear_cannot_complete_a_new_attempt(service):
    service.request("prepare", {"jobs": [job(service)]})
    service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    stale = deepcopy(state["jobs"][0])
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    active = {"action": "upload", "sha256": stale["file_sha256"]}
    assert runner.authorize(stale, state["batch_id"], active)
    before = deepcopy(service.store.load()["jobs"][0])
    runner.update(stale, state["batch_id"], intent=None, status="ready_for_review")
    after = service.store.load()["jobs"][0]
    assert after["intent"] == active and after["status"] == "filling"
    assert after["observations"] == before["observations"]


@pytest.mark.parametrize("action", ["fill", "upload"])
@pytest.mark.parametrize("conclusion", ["not_applied", "manual_stop"])
def test_legacy_conflict_stops_before_write_without_rewriting_evidence(service, action, conclusion):
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    intent = {"action": action, "attempt_id": "legacy-attempt", "sha256": current["file_sha256"]}
    current["action_resolutions"] = [
        {"intent_ref": "legacy-attempt", "intent": intent, "conclusion": conclusion, "at": 120}
    ]
    current["observations"] = [
        {"action": "action_result", "intent": intent, "result": "verified", "at": 60}
    ]
    service.store.save(state)
    before = service.store.path.read_bytes()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    runner.pages[current["application_id"]] = object()
    runner.observe = lambda *_: {
        "fields": [{"id": "resume", "type": "file"}],
        "upload": {"state": "empty"},
    }

    def reject_write(*_):
        raise AssertionError("Legacy conflict reached a new action authorization")

    runner.authorize = reject_write
    with pytest.raises(PortalDataError) as error:
        runner.process(deepcopy(current), state["batch_id"])
    assert error.value.code == "recovery_order_unknown"
    assert service.store.path.read_bytes() == before


@pytest.mark.worker_browser
@pytest.mark.parametrize("case", ["recheck_before_response", "legacy_clock_backwards"])
def test_delayed_upload_does_not_replay_after_restart(tmp_path, monkeypatch, case):
    from playwright.sync_api import sync_playwright

    worker = live_service(tmp_path, monkeypatch, lever_uploads=True)
    identifier = prepare(worker)["application_id"]
    counts, checkpoints = [], []
    original_intent = None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            for index in range(2):
                context = browser.new_context(offline=True)
                start_run(worker.store)
                runner = ApplicationRunner(worker.store, context)
                sent = []

                def intercept(route, _request, current_runner=runner, cycle=index, requests=sent):
                    def fetch(**options):
                        nonlocal original_intent
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        if route.request.method == "POST":
                            requests.append(route.request.url)
                            if cycle == 0:
                                original_intent = deepcopy(worker.store.load()["jobs"][0]["intent"])
                                recorded_at = time.time()
                                with monkeypatch.context() as clock:
                                    if case == "legacy_clock_backwards":
                                        clock.setattr(time, "time", lambda: recorded_at + 60)
                                    worker.request(
                                        "resolve-action",
                                        {
                                            "application_id": identifier,
                                            "intent_ref": original_intent["attempt_id"],
                                            "conclusion": "not_applied",
                                            "source": "Synthetic readback before response",
                                        },
                                    )
                                if case == "legacy_clock_backwards":
                                    legacy = worker.store.load()
                                    legacy["jobs"][0]["action_resolutions"][-1].pop(
                                        "observation_count"
                                    )
                                    worker.store.save(legacy)
                                else:
                                    worker.request(
                                        "recheck",
                                        {"application_id": identifier, "acknowledge": True},
                                    )
                        return SimpleNamespace(status=200, dispose=lambda: None)

                    def fulfill(*, response):
                        if route.request.method == "POST":
                            route.fulfill(status=response.status, json={})
                        else:
                            route.fulfill(
                                status=response.status, body=UPLOAD_HTML, content_type="text/html"
                            )

                    current_runner._live_guard(
                        SimpleNamespace(
                            request=route.request, fetch=fetch, fulfill=fulfill, abort=route.abort
                        )
                    )

                context.route("**/*", intercept)
                if index:
                    worker.request("recheck", {"application_id": identifier, "acknowledge": True})
                worker.request("resume", {"controller": "synthetic-controller"})
                if not index:
                    advance_until(
                        worker,
                        runner,
                        lambda row: any(
                            event.get("action") == "action_result"
                            and event.get("result") == "verified"
                            and event.get("intent", {}).get("action") == "upload"
                            for event in row["observations"]
                        ),
                    )
                else:
                    for _ in range(4):
                        runner.tick()
                current = deepcopy(worker.store.load()["jobs"][0])
                checkpoints.append(current)
                counts.append(len(sent))
                report("attempt-progress-" + case, {"uploads_by_run": counts, "jobs": checkpoints})
                if index and case == "legacy_clock_backwards":
                    assert current["reason"] == "page_changed" and not runner.pages
                    assert len(sent) == 0
                context.close()
            completion = next(
                o
                for o in checkpoints[0]["observations"]
                if o.get("action") == "action_result"
                and o.get("intent", {}).get("attempt_id") == original_intent["attempt_id"]
            )
            report(
                "attempt-completion-" + case,
                {
                    "uploads_by_run": counts,
                    "completion": completion,
                    "jobs": checkpoints,
                    "real_ats_calls": 0,
                    "automatic_final_requests": 0,
                },
            )
            assert counts == [1, 0]
            assert checkpoints[-1]["status"] == "needs_recheck"
            assert (
                checkpoints[-1]["observations"][: len(checkpoints[0]["observations"])]
                == checkpoints[0]["observations"]
            )
        finally:
            browser.close()


@pytest.mark.worker_browser
def test_delayed_fill_keeps_its_attempt_after_recheck(tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright

    worker = live_service(tmp_path, monkeypatch, lever_uploads=True)
    identifier = prepare(worker)["application_id"]
    worker.store.answers.put_answer(
        {"question": "Full name", "value": "Synthetic Person", "scope": {}, "state": "confirmed"}
    )
    html = UPLOAD_HTML.replace(
        "<div class='file-upload'",
        "<label for='name'>Full name *</label><input id='name' required><div class='file-upload'",
    )
    counts, checkpoints = [], []
    original_fill = hosted_ats.fill
    mutations = []

    def fill_and_recheck(page, field, value):
        active = worker.store.load()["jobs"][0]["intent"]
        worker.request(
            "resolve-action",
            {
                "application_id": identifier,
                "intent_ref": active["attempt_id"],
                "conclusion": "not_applied",
                "source": "Synthetic readback before field completion",
            },
        )
        worker.request("recheck", {"application_id": identifier, "acknowledge": True})
        original_fill(page, field, value)
        mutations.append(active["attempt_id"])

    monkeypatch.setattr(hosted_ats, "fill", fill_and_recheck)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            for index in range(2):
                previous_mutations = len(mutations)
                context = browser.new_context(offline=True)
                start_run(worker.store)
                runner = ApplicationRunner(worker.store, context)
                sent, denied = [], []
                intercept_uploads(context, runner, sent, denied, html=html)
                if index:
                    worker.request("recheck", {"application_id": identifier, "acknowledge": True})
                worker.request("resume", {"controller": "synthetic-controller"})
                if not index:
                    advance_until(
                        worker,
                        runner,
                        lambda row: any(
                            event.get("action") == "late_fill_result"
                            for event in row["observations"]
                        ),
                    )
                else:
                    for _ in range(4):
                        runner.tick()
                checkpoints.append(deepcopy(worker.store.load()["jobs"][0]))
                counts.append(len(mutations) - previous_mutations)
                context.close()
            proof = next(
                o for o in checkpoints[0]["observations"] if o.get("action") == "late_fill_result"
            )
            report(
                "attempt-completion-fill",
                {
                    "fill_counts": counts,
                    "completion": proof,
                    "jobs": checkpoints,
                    "real_ats_calls": 0,
                },
            )
            assert proof["intent"]["attempt_id"] == mutations[0]
            assert proof["adopted"] is False and proof["value"] == "Synthetic Person"
            assert counts == [1, 0]
            assert checkpoints[-1]["reason"] == "page_changed"
        finally:
            browser.close()
