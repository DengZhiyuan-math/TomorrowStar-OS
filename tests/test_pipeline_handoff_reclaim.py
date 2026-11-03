"""Queue mode reclaims a page handed to the user with one explicit Continue.

2026-11-03: a job stopped at ready_for_review with handed_off true; quitting the App
lost its page. Continue went to the reopen path and answered page_lost, while the
Flow recheck was refused as pipeline_entry_required: queue mode had no way back.
"""

import time

import pytest
from test_application_resume import task_resume as task_resume
from test_bound_material_update import bound_pipeline as bound_pipeline
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.career_portal import pipeline_control
from career_evidence_graph.career_portal_data import PortalDataError

SOURCE = "Checked the employer page: nothing was submitted; the page was closed."


def handed_off(server, **changes):
    """The job the user took over, whose page was lost with the App."""
    worker = server.worker_service
    state = worker.store.load()
    job = state["jobs"][0]
    job.update(
        {
            "status": "ready_for_review",
            "reason": "",
            "handed_off": True,
            "page_open": False,
            "intent": None,
            "handoff": {
                "status": "pending",
                "at": time.time(),
                "run_id": (state.get("runtime") or {}).get("id"),
                "source": "user_requested_handoff",
                "actor": "user",
                "human_reviewed": False,
            },
        }
        | changes
    )
    worker.store.save(state)
    server.application_pipeline_service.pause()


def routed(server, monkeypatch):
    """Record Worker operations; the lost page answers page_lost, reopen is recorded."""
    flow = server.application_flow_service
    original, actions = flow.worker_action, []

    def worker_action(task_id, task_revision, operation, payload):
        actions.append((operation, dict(payload)))
        if operation == "continue-current":
            raise PortalDataError("page_lost", "原页不能核验。", 409)
        if operation == "reopen-current":
            return None
        return original(task_id, task_revision, operation, payload)

    monkeypatch.setattr(flow, "worker_action", worker_action)
    return actions


def test_continue_with_reclaim_rechecks_then_reopens_the_lost_page(bound_pipeline, monkeypatch):
    server, _, _ = bound_pipeline
    handed_off(server)
    actions = routed(server, monkeypatch)
    pipeline = server.application_pipeline_service

    pipeline_control(
        pipeline,
        "continue",
        {"request_id": "reclaim-continue", "reclaim": True, "handoff_source": SOURCE},
    )

    assert [operation for operation, _ in actions] == [
        "recheck",
        "continue-current",
        "reopen-current",
    ]
    assert actions[0][1] == {"reclaim": True, "handoff_source": SOURCE, "acknowledge": True}
    job = server.worker_service.store.load()["jobs"][0]
    assert job["handed_off"] is False and job["intent"] is None
    assert job["status"] == "queued"
    recheck = [row for row in job["observations"] if row.get("action") == "inputs_rechecked"]
    assert recheck[-1]["source"] == "user_confirmed_recheck"
    assert recheck[-1]["handoff_source"] == SOURCE
    receipt = pipeline.snapshot()["current_requests"][-1]
    assert (receipt["request_id"], receipt["status"]) == ("reclaim-continue", "complete")


def test_continue_without_reclaim_still_answers_page_lost(bound_pipeline, monkeypatch):
    server, _, _ = bound_pipeline
    handed_off(server)
    flow = server.application_flow_service
    actions = []

    def worker_action(task_id, task_revision, operation, payload):
        actions.append(operation)
        raise PortalDataError("page_lost", "原页不能核验。", 409)

    monkeypatch.setattr(flow, "worker_action", worker_action)
    with pytest.raises(PortalDataError) as error:
        server.application_pipeline_service.continue_current(request_id="plain-continue")
    assert error.value.code == "page_lost"
    assert actions == ["continue-current", "reopen-current"]
    assert server.worker_service.store.load()["jobs"][0]["handed_off"] is True


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"manual_submission": {"source": "user_confirmation", "at": 1.0}}, "already_submitted"),
        ({"intent": {"action": "fill", "attempt_id": "a" * 32}}, "action_unresolved"),
    ],
)
def test_reclaim_keeps_the_workers_recheck_guards(bound_pipeline, monkeypatch, changes, code):
    server, _, _ = bound_pipeline
    handed_off(server, **changes)
    actions = routed(server, monkeypatch)
    with pytest.raises(PortalDataError) as error:
        server.application_pipeline_service.continue_current(
            request_id="guarded-reclaim", reclaim=True, handoff_source=SOURCE
        )
    assert error.value.code == code
    assert [operation for operation, _ in actions] == ["recheck"]
    assert server.worker_service.store.load()["jobs"][0]["handed_off"] is True


def test_reclaim_waits_for_an_unresolved_manual_submission(bound_pipeline, monkeypatch):
    server, _, _ = bound_pipeline
    handed_off(server)
    actions = routed(server, monkeypatch)
    monkeypatch.setattr(
        "career_evidence_graph.application_worker.manual_submission_unresolved",
        lambda job: True,
    )
    with pytest.raises(PortalDataError) as error:
        server.application_pipeline_service.continue_current(
            request_id="unresolved-reclaim", reclaim=True, handoff_source=SOURCE
        )
    assert error.value.code == "submission_result_unknown"
    assert actions == []


@pytest.mark.parametrize(
    "payload",
    [
        {"request_id": "bad-1", "reclaim": True},
        {"request_id": "bad-2", "reclaim": True, "handoff_source": ""},
        {"request_id": "bad-3", "reclaim": True, "handoff_source": "x" * 1001},
        {"request_id": "bad-4", "reclaim": False, "handoff_source": SOURCE},
        {"request_id": "bad-5", "reclaim": True, "handoff_source": SOURCE, "acknowledge": True},
    ],
)
def test_malformed_reclaim_has_no_effect(bound_pipeline, monkeypatch, payload):
    server, _, _ = bound_pipeline
    handed_off(server)
    actions = routed(server, monkeypatch)
    before = server.worker_service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        pipeline_control(server.application_pipeline_service, "continue", payload)
    assert error.value.code == "pipeline_request_invalid"
    assert error.value.status == 409
    assert actions == []
    assert server.worker_service.store.path.read_bytes() == before


@pytest.mark.parametrize("page_current", [False, True])
def test_reclaim_clears_only_a_stale_page_open_flag(bound_pipeline, monkeypatch, page_current):
    """2026-11-03: the handed-off page closed with the App but kept page_open."""
    server, _, _ = bound_pipeline
    from career_evidence_graph.application_worker import start_run

    worker = server.worker_service
    # The run that owned the handed-off page.
    start_run(worker.store)
    state = worker.store.load()
    runtime = state["runtime"]
    if not page_current:
        # The App quit: the run's heartbeat is old, so its page is no longer current.
        runtime["observed_at"] -= 60
    state["jobs"][0]["page_observation"] = {
        "run_id": runtime["id"],
        "page_id": "handed-off-page",
        "event": "observed",
        "at": runtime["observed_at"],
    }
    worker.store.save(state)
    handed_off(server, page_open=True)
    assert worker._page_current(worker.store.load(), worker.store.load()["jobs"][0]) is (
        page_current
    )
    actions = routed(server, monkeypatch)

    server.application_pipeline_service.continue_current(
        request_id="reclaim-stale-page", reclaim=True, handoff_source=SOURCE
    )

    job = worker.store.load()["jobs"][0]
    recheck = [row for row in job["observations"] if row.get("action") == "inputs_rechecked"]
    assert recheck[-1]["page_open_cleared"] is (not page_current)
    assert job["page_open"] is page_current
    assert job["handed_off"] is False and job["status"] == "queued"
    # The same request goes on to Continue and, with the page lost, to reopen.
    assert [operation for operation, _ in actions] == [
        "recheck",
        "continue-current",
        "reopen-current",
    ]
