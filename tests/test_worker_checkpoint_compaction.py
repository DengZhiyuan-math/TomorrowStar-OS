"""The worker checkpoint bounds routine request rows and skips liveness-only rewrites."""

import json

from test_workable_uploads import setup_service

from career_evidence_graph.application_worker import (
    ROUTINE_OBSERVATION_WINDOW,
    compact_native_runs,
    compact_observations,
    start_run,
)


def routine(index, stage="request_blocked", reason="unverified_send_path"):
    return {
        "action": "request_diagnostic",
        "request_id": f"routine-{index}",
        "stage": stage,
        "reason": reason,
        "caused_stop": False,
        "at": index,
    }


def test_routine_rows_keep_a_recent_window_with_counts_and_every_stop():
    stop = {**routine("stop"), "stage": "request_response_rejected", "caused_stop": True}
    named = routine("named")
    readback = {"action": "readback_diagnostic", "request_id": "routine-named"}
    rows = [stop, named, readback]
    rows += [routine(i) for i in range(500)]
    rows += [routine(i, "request_permitted", "request_allowed") for i in range(500, 600)]
    total = len(rows)
    job = {"observations": rows}

    compact_observations(job)

    kept = job["observations"]
    assert kept[:3] == [stop, named, readback]
    # The named row stays outside the count; the oldest unnamed rows are dropped first.
    assert [row["at"] for row in kept[3:]] == list(range(401, 600))
    routine_kept = [row for row in kept[1:] if row["action"] == "request_diagnostic"]
    assert len(routine_kept) == ROUTINE_OBSERVATION_WINDOW
    assert job["observation_counts"] == {
        "request_diagnostic/request_blocked/unverified_send_path": 401
    }
    dropped = sum(job["observation_counts"].values())
    assert dropped + len(kept) == total
    # A second save of the compacted record changes nothing.
    again = json.loads(json.dumps(job))
    compact_observations(again)
    assert again == job


def test_retired_native_runs_store_each_call_once_without_losing_a_receipt():
    first = {"call_id": "a", "tool": "browser_click", "status": "dispatched"}
    done = {**first, "status": "completed"}
    second = {"call_id": "b", "tool": "browser_type", "status": "completed"}
    receipts = [{"calls": [first]}, {"calls": [done]}, {"calls": [done, second], "revoked": True}]
    run = {
        "request_id": "run",
        "phase": "stopped",
        "events": [{"phase": "granted", "receipt": r, "at": i} for i, r in enumerate(receipts)],
    }

    (compacted,) = compact_native_runs([run])

    assert compacted["calls"] == [first, done, second]
    for event, receipt in zip(compacted["events"], receipts, strict=True):
        rebuilt = {k: v for k, v in event["receipt"].items() if k != "call_refs"}
        rebuilt["calls"] = [compacted["calls"][i] for i in event["receipt"]["call_refs"]]
        assert rebuilt == receipt
    assert compact_native_runs([compacted]) == [compacted]


def test_save_compacts_the_record_and_reports_a_liveness_only_change(tmp_path, monkeypatch):
    service = setup_service(tmp_path, monkeypatch)
    start_run(service.store)
    state = service.store.load()
    job = state["jobs"][0]
    job["observations"] += [routine(i) for i in range(ROUTINE_OBSERVATION_WINDOW + 50)]
    service.store.save(state)
    saved = service.store.load()
    assert saved["jobs"][0]["observation_counts"] == {
        "request_diagnostic/request_blocked/unverified_send_path": 50
    }

    saved["worker_heartbeat"] += 1
    saved["runtime"]["observed_at"] += 1
    assert service.store.liveness_only(saved)
    stale = json.loads(json.dumps(saved))
    stale["runtime"]["observed_at"] -= 10
    assert not service.store.liveness_only(stale)
    stale["runtime"].pop("observed_at")
    assert not service.store.liveness_only(stale)
    saved["worker_error"] = "synthetic_change"
    assert not service.store.liveness_only(saved)
    service.store.save(saved)
    assert service.store.load()["worker_error"] == "synthetic_change"
