"""Preserve unbound historical completions and stop automatic recovery writes."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_worker import job
from test_application_worker import service as _service
from test_hosted_ats import live_service, prepare
from test_worker_recovery_regressions import UPLOAD_HTML, intercept_uploads, report

from career_evidence_graph import hosted_ats
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError

service = _service


@pytest.mark.parametrize(
    "case",
    [
        "fill_missing",
        "fill_null",
        "select_only",
        "earlier_complete",
        "wrong_run",
        "wrong_page",
        "wrong_hash",
        "interrupted",
        "bound_fill",
        "paired_select",
        "paired_empty_run",
        "paired_null_run",
        "missing_run",
        "historic_fill",
        "historic_select",
    ],
)
def test_unbound_completion_guard_preserves_evidence(service, case):
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    current = state["jobs"][0]
    selected = {
        "action": "select_file",
        "verified": True,
        "run_id": "old-run",
        "page_id": "old-page",
        "local_sha256": current["file_sha256"],
    }
    complete = {
        "action": "action_result",
        "result": "verified",
        "run_id": "old-run",
        "intent": {
            "action": "upload",
            "attempt_id": "explicit-old-attempt",
            "run_id": "old-run",
            "page_id": "old-page",
            "sha256": current["file_sha256"],
        },
    }
    observations = [selected]
    if case.startswith("fill") or case in {"bound_fill", "historic_fill"}:
        observations = [{"action": "fill", "verified": True, "field_id": "name"}]
        if case == "fill_null":
            observations[0]["intent"] = None
        elif case == "bound_fill":
            observations[0]["intent"] = {"action": "fill", "attempt_id": "explicit-fill"}
    elif case == "earlier_complete":
        observations = [complete, selected]
    elif case == "interrupted":
        observations = [selected, {"action": "select_file", "verified": False}, complete]
    elif case not in {"select_only", "historic_select"}:
        observations.append(complete)
        if case == "wrong_run":
            complete["intent"]["run_id"] = complete["run_id"] = "different-run"
        elif case == "wrong_page":
            complete["intent"]["page_id"] = "different-page"
        elif case == "wrong_hash":
            complete["intent"]["sha256"] = "different-file"
        elif case == "paired_empty_run":
            selected["run_id"] = complete["run_id"] = complete["intent"]["run_id"] = ""
        elif case == "paired_null_run":
            selected["run_id"] = complete["run_id"] = complete["intent"]["run_id"] = None
        elif case == "missing_run":
            del complete["intent"]["run_id"]
    current["observations"] = observations
    if case.startswith("historic"):
        state["batch_history"] = [{"batch_id": "old-batch", "jobs": [deepcopy(current)]}]
        current["observations"] = []
    service.store.save(state)
    before = service.store.path.read_bytes()
    runner = ApplicationRunner(service.store, None, service.fixture_origin)
    runner.pages[current["application_id"]] = object()
    runner.observe = lambda *_: {
        "fields": [{"id": "resume", "type": "file"}],
        "upload": {"state": "empty"},
    }
    runner.authorize = lambda *_: False
    if case == "bound_fill":
        runner.process(deepcopy(current), state["batch_id"])
    else:
        expected = (
            "recovered_result_not_visible"
            if case in {"paired_select", "paired_empty_run", "paired_null_run"}
            else "recovery_completion_unbound"
        )
        with pytest.raises(PortalDataError) as error:
            runner.process(deepcopy(current), state["batch_id"])
        assert error.value.code == expected
        if case not in {"paired_select", "paired_empty_run", "paired_null_run"}:
            assert service.store.path.read_bytes() == before


@pytest.mark.worker_browser
@pytest.mark.parametrize("action", ["upload", "fill"])
def test_old_r6_completion_stops_writes_and_preserves_human_history(tmp_path, monkeypatch, action):
    from playwright.sync_api import sync_playwright

    saved = (
        Path(__file__).parent.parent
        / ".scratch/application-worker-stability/fixes/2026-10-11-r6-r7/before-facts"
    )
    evidence = saved / (
        "attempt-progress-recheck_before_response.json"
        if action == "upload"
        else "attempt-completion-fill.json"
    )
    prior = json.loads(evidence.read_text())["jobs"][0]
    worker = live_service(tmp_path, monkeypatch)
    identifier = prepare(worker)["application_id"]
    html = UPLOAD_HTML
    fills = []
    if action == "fill":
        worker.store.answers.put_answer(
            {
                "question": "Full name",
                "value": "Synthetic Person",
                "scope": {},
                "state": "confirmed",
            }
        )
        html = html.replace(
            "<div class='file-upload'",
            "<label for='name'>Full name *</label><input id='name' required>"
            "<div class='file-upload'",
        )
        original_fill = hosted_ats.fill

        def counted_fill(page, field, value):
            fills.append(field["id"])
            return original_fill(page, field, value)

        monkeypatch.setattr(hosted_ats, "fill", counted_fill)
    state = worker.store.load()
    current = state["jobs"][0]
    assert current["file_sha256"] == prior["file_sha256"]
    # Bind fresh synthetic inputs. Preserve the exact old evidence arrays.
    current["observations"] = deepcopy(prior["observations"])
    current["action_resolutions"] = deepcopy(prior["action_resolutions"])
    worker.store.save(state)
    if action == "fill":
        assert any(
            o.get("action") == "fill" and o.get("verified") and o.get("intent") is None
            for o in current["observations"]
        )
    else:
        assert any(
            o.get("action") == "select_file" and o.get("verified") for o in current["observations"]
        )
        assert not any(
            o.get("action") == "action_result" and o.get("intent", {}).get("action") == "upload"
            for o in current["observations"]
        )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            start_run(worker.store)
            runner = ApplicationRunner(worker.store, context)
            sent, denied = [], []
            intercept_uploads(context, runner, sent, denied, html=html)
            paused = worker.store.load()
            assert paused["control"] == "paused" and sent == [] and fills == []
            worker.request("recheck", {"application_id": identifier, "acknowledge": True})
            worker.request("resume", {"controller": "synthetic-controller"})
            for _ in range(4):
                runner.tick()
            after = deepcopy(worker.store.load()["jobs"][0])
            report(
                "prior-r6-" + action,
                {
                    "old_evidence_source": str(evidence.relative_to(Path.cwd())),
                    "old_evidence": prior,
                    "restored_observations_unchanged": after["observations"][
                        : len(prior["observations"])
                    ]
                    == prior["observations"],
                    "new_fill_count": len(fills),
                    "new_upload_count": len(sent),
                    "old_record_verified_action_count": 1,
                    "job": after,
                    "real_ats_calls": 0,
                    "automatic_final_requests": 0,
                },
            )
            assert len(sent) == 0 and len(fills) == 0
            assert after["status"] == "needs_recheck"
            assert after["reason"] == "recovery_completion_unbound"
            assert after["observations"][: len(prior["observations"])] == prior["observations"]
            worker.request("review", {"application_id": identifier, "acknowledge": True})
            runner.tick()
            handed_off = worker.store.load()["jobs"][0]
            assert handed_off["handed_off"] and handed_off["handoff"]["status"] == "complete"
            assert sent == [] and fills == []
            worker.request("cancel-job", {"application_id": identifier})
            worker.request("release", {"application_id": identifier})
            runner.tick()
            cancelled = deepcopy(worker.store.load()["jobs"][0])
            assert cancelled["status"] == "cancelled" and not cancelled["page_open"]
            prepare(
                worker,
                url=current["job_url"].rsplit("/", 1)[0] + "/00000000-0000-0000-0000-000000000002",
            )
            replacement = worker.store.load()
            assert replacement["control"] == "paused"
            assert replacement["batch_history"][-1]["jobs"][0] == cancelled
            assert sent == [] and fills == []
            report(
                "old-r6-handoff-history-" + action,
                {
                    "cancelled": cancelled,
                    "history": replacement["batch_history"][-1],
                    "new_control": replacement["control"],
                    "new_automatic_writes": 0,
                },
            )
        finally:
            browser.close()
