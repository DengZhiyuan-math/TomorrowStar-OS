"""The takeover record Module: limit, retained history, generations and one report rule."""

from __future__ import annotations

from career_evidence_graph import application_codex_assist as adapter
from career_evidence_graph import application_takeover_record as record
from career_evidence_graph import application_worker as worker

BLOCKER = {
    "code": "unsupported_structure",
    "field_id": None,
    "page_id": "page",
    "run_id": "run",
    "observed_at": 1.0,
}
PROVEN = {
    "stop_status": "stopped",
    "tools_revoked": True,
    "local_tools_drained": True,
    "process_stopped": True,
}


def row(generation, *, page="old", failed=None, status="stopped", stop=PROVEN):
    dispatch = {"blocker": dict(BLOCKER, page_id=page)}
    if failed:
        dispatch["failed_code"] = failed
    return {"generation": generation, "status": status, "stop": dict(stop), "dispatch": dispatch}


def test_settled_rows_never_fill_the_limit_and_keep_only_a_short_tail():
    job = {}
    for generation in range(1, 201):
        record.archive(job, row(generation))
    assert record.capacity_left(job)
    assert len(job["assistance_history"]) == record.SETTLED_HISTORY_RETAINED
    assert record.next_generation(job) == 201
    assert record.takeover_slot({}, job, BLOCKER)


def test_failed_and_unsettled_rows_are_counted_and_always_retained():
    job = {}
    record.archive(job, row(1, page="page", failed="native_assistance_unavailable"))
    for generation in range(2, 100):
        record.archive(job, row(generation))
    assert job["assistance_history"][0]["dispatch"]["failed_code"]
    assert not record.takeover_slot({}, job, BLOCKER)
    full = {}
    for generation in range(1, record.ASSISTANCE_HISTORY_LIMIT + 1):
        record.archive(full, row(generation, failed="cua_unavailable"))
    assert not record.capacity_left(full)
    assert not record.takeover_slot({}, full, dict(BLOCKER, page_id="new"))
    pending = row(1, status="stop_unknown", stop={**PROVEN, "local_tools_drained": False})
    assert record.counted_rows({"assistance": pending}) == 1


def test_old_history_of_64_settled_rows_still_loads():
    assert record.valid_history([row(index) for index in range(1, 65)])
    assert not record.valid_history(
        [row(index, failed="x") for index in range(1, record.ASSISTANCE_HISTORY_LIMIT + 2)]
    )


def test_generation_survives_a_dropped_history():
    job = {"assistance_generation": 7}
    assert record.next_generation(job) == 8
    record.begin(job, {"generation": 8})
    record.begin(job, {"generation": record.next_generation(job)})
    assert job["assistance"]["generation"] == 9
    assert job["assistance_generation"] == 9


def test_adapter_and_worker_share_one_report_rule():
    assert adapter._REPORT_SCHEMA is record.REPORT_SCHEMA
    assert worker.valid_assistance_report is record.valid_assistance_report
    assert worker.revoke_assistance is record.revoke_assistance
    assert worker.record_takeover_failure is record.record_takeover_failure


def test_one_stop_definition_reads_saved_stops_progress_and_driver_receipts():
    assert record.stop_evidence_proven(PROVEN)
    assert not record.stop_evidence_proven(dict(PROVEN, stop_status="unknown"))
    assert not record.stop_evidence_proven(dict(PROVEN, local_tools_drained=False))
    returned = {"revoked": True, "local_tools_drained": True, "active_calls": 0}
    assert record.native_return_proven(dict(returned, return_ready=True))
    assert not record.native_return_proven(dict(returned, return_ready=False))
    assert worker._native_stop_proven is record.native_return_proven
    assert worker.assistance_stop_pending({"assistance": row(1, status="stop_unknown")})


def test_reopen_keeps_the_observed_stop_and_retirement_proves_it():
    unknown = dict(PROVEN, stop_status="unknown", local_tools_drained=False, request_id="s")
    job = {"assistance": row(3, status="stop_unknown", stop=unknown)}
    retired_stop = record.retire_for_reopen(job)
    (kept,) = job["assistance_history"]
    assert retired_stop == unknown and kept["stop"] == unknown
    assert kept["status"] == "stop_unknown" and kept["retired"]["reason"] == "page_reopened"
    assert record.stop_proven(kept) and record.capacity_left(job)
    assert record.next_generation(job) == 4


def test_unstarted_takeover_stop_is_settled_by_the_record():
    stop = {
        "request_id": "stop",
        "reason": "assistance_unavailable",
        "requested_at": 1.0,
        "tools_revoked": True,
        "local_tools_drained": False,
        "process_stopped": False,
        "native_turn_id": None,
        "native_turn_status": "unknown",
        "stop_status": "stopping",
        "observed_at": None,
    }
    job = {"assistance": {"status": "stopping", "stop": stop}}
    assert record.settle_unstarted_stop(job)
    assert job["assistance"]["status"] == "stopped"
    assert record.valid_assistance_stop(job["assistance"]["stop"], "stopped")
    assert not record.settle_unstarted_stop(job)
