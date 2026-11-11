"""Batch 1-D: queue-state assertions only log privately; they never change a transition."""

import json

from career_evidence_graph.application_pipeline import (
    QUEUE_ASSERTION_LOG,
    ApplicationPipeline,
    queue_state,
)


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Applications:
    def write_lock(self):
        return _Lock()


class _Flow:
    applications = _Applications()


def _pipeline(tmp_path):
    pipeline = ApplicationPipeline.__new__(ApplicationPipeline)
    pipeline.flow = _Flow()
    pipeline.path = tmp_path / "pipeline.json"
    pipeline._saved_control = None
    pipeline._notify = lambda *args: None
    return pipeline


def _log(tmp_path):
    path = tmp_path / QUEUE_ASSERTION_LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_projection_reads_only_control_fields():
    state = {"control": "paused", "status": "x", "items": [1], "wait_reason": "w"}
    assert queue_state(state) == {
        "control": "paused",
        "status": "x",
        "resume_status": None,
        "wait_reason": "w",
        "active_task_id": None,
    }


def test_stop_without_resume_status_is_logged_and_still_stops(tmp_path):
    pipeline = _pipeline(tmp_path)
    state = {"control": "running", "status": "matching"}
    pipeline._stop(state, "needs_recheck", "synthetic")
    assert state["control"] == "paused" and state["status"] == "needs_recheck"
    assert [row["code"] for row in _log(tmp_path)] == ["stop_without_resume_status"]
    pipeline._stop(state | {"resume_status": "matching"}, "needs_recheck", "synthetic")
    assert len(_log(tmp_path)) == 1


def test_resume_keeping_wait_fields_is_logged_but_saved_unchanged(tmp_path):
    pipeline = _pipeline(tmp_path)
    pipeline._save({"control": "paused", "status": "s", "wait_reason": "w", "resume_status": "m"})
    resumed = {"control": "running", "status": "m", "wait_reason": "w"}
    pipeline._save(resumed)
    assert json.loads(pipeline.path.read_text())["wait_reason"] == "w"
    (row,) = _log(tmp_path)
    assert row["code"] == "resume_kept_wait_fields" and row["fields"] == ["wait_reason"]
    pipeline._save({"control": "paused", "status": "s"})
    pipeline._save({"control": "running", "status": "m"})
    assert len(_log(tmp_path)) == 1
