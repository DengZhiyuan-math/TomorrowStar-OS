"""The worker checkpoint bounds routine request rows and skips liveness-only rewrites."""

import json

from test_workable_uploads import setup_service

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_worker import (
    ROUTINE_OBSERVATION_WINDOW,
    compact_native_runs,
    compact_observations,
    diagnostic_url,
    pack_source_sets,
    start_run,
    unpack_source_sets,
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


SOURCES = [{"evidence_id": f"source-{i}", "text": "x" * 100} for i in range(20)]


def letter(identifier, sources=SOURCES):
    return {
        "id": identifier,
        "kind": "cover_letter",
        "source_binding": {"application": {"id": "a"}, "sources": json.loads(json.dumps(sources))},
    }


def test_repeated_material_sources_are_stored_once_and_restored_exactly(tmp_path, monkeypatch):
    # 2026-11-04: four letter attempts kept the same 1.4 MB source list.
    service = setup_service(tmp_path, monkeypatch)
    start_run(service.store)
    state = service.store.load()
    job = state["jobs"][0]
    other = [{"evidence_id": "other"}]
    job["materials"] = [letter("current")]
    job["material_history"] = [letter("old-1"), letter("old-2"), letter("old-3", other)]
    expected = json.loads(json.dumps(state))
    service.store.save(state)
    # The caller's state is unchanged by the stored form.
    assert state == expected
    stored = json.loads(service.store.path.read_text())["jobs"][0]
    assert len(stored["source_sets"]) == 2
    assert all(
        set(row["source_binding"]["sources"]) == {"source_set"}
        for row in stored["material_history"]
    )
    loaded = service.store.load()
    assert loaded["jobs"][0]["materials"] == expected["jobs"][0]["materials"]
    assert loaded["jobs"][0]["material_history"] == expected["jobs"][0]["material_history"]
    assert "source_sets" not in loaded["jobs"][0]
    # A record without source sets (older form) loads unchanged.
    assert unpack_source_sets(json.loads(json.dumps(expected))) == expected
    packed = pack_source_sets(expected)
    packed["jobs"][0]["source_sets"] = {}
    try:
        unpack_source_sets(json.loads(json.dumps(packed)))
    except ValueError:
        pass
    else:
        raise AssertionError("a dangling source-set reference must not load")


def test_an_unchanged_checkpoint_is_not_parsed_again_and_each_load_is_a_copy(tmp_path, monkeypatch):
    # 2026-11-04: a 1 s queue tick re-parsed a 13 MB checkpoint while paused (78% CPU).
    service = setup_service(tmp_path, monkeypatch)
    start_run(service.store)
    reads = []
    original = helper.read_json_object

    def counted(path, label):
        reads.append(label)
        return original(path, label)

    monkeypatch.setattr(helper, "read_json_object", counted)
    first = service.store.load()
    second = service.store.load()
    assert reads.count("worker state") == 1
    assert first == second and first is not second
    first["jobs"][0]["status"] = "cancelled"
    assert service.store.load()["jobs"][0]["status"] != "cancelled"
    second["worker_error"] = "synthetic_change"
    service.store.save(second)
    assert service.store.load()["worker_error"] == "synthetic_change"
    assert reads.count("worker state") == 2


def test_diagnostic_rows_keep_no_query_values_or_credentials():
    url = "https://user:secret@bucket.s3.example/uploads/a.pdf?X-Amz-Signature=abc&X-Amz-Expires=600#f"
    assert diagnostic_url(url) == (
        "https://bucket.s3.example/uploads/a.pdf",
        ["X-Amz-Expires", "X-Amz-Signature"],
    )
    assert diagnostic_url("https://host:8443/p") == ("https://host:8443/p", [])
    job = {"observations": [{**routine("old"), "url": url}]}
    compact_observations(job)
    row = job["observations"][0]
    assert "secret" not in json.dumps(row) and "abc" not in json.dumps(row)
    assert row["url"] == "https://bucket.s3.example/uploads/a.pdf"
    assert row["query_keys"] == ["X-Amz-Expires", "X-Amz-Signature"]
