"""Internal resume reuse telemetry does not add review operations."""

import career_evidence_graph.worker_measurement as measurement
from career_evidence_graph.worker_measurement import MeasurementLog


def test_preparation_covers_whole_interval_and_dedupes_reopen(tmp_path, monkeypatch):
    ticks = iter([1_000_000, 81_000_000])
    monkeypatch.setattr(measurement.time, "monotonic_ns", lambda: next(ticks))
    log = MeasurementLog(tmp_path)
    episode = log.preparation_started("private-task", "private-input")
    reopened = MeasurementLog(tmp_path)
    assert reopened.preparation_started("private-task", "private-input") == episode
    reopened.preparation_ready(episode, task_id="private-task", pdf_sha256="a" * 64, inherited=True)
    reopened.preparation_ready(episode, task_id="private-task", pdf_sha256="a" * 64, inherited=True)
    summary = reopened.reuse_summary()
    assert len(summary["preparations"]) == 1
    row = summary["preparations"][0]
    assert row["total_ms"] == 80
    assert row["clock_complete"] is True
    assert row["inherited"] is True
    assert "private-task" not in log.path.read_text()
    assert "private-input" not in log.path.read_text()
    assert log.summary()["incomplete"] is False


def test_cross_process_preparation_has_unknown_total(tmp_path, monkeypatch):
    log = MeasurementLog(tmp_path)
    episode = log.preparation_started("task", "input")
    monkeypatch.setattr(measurement, "_CLOCK", "another-process")
    log.preparation_ready(episode, task_id="task", pdf_sha256="b" * 64, inherited=False)
    row = log.reuse_summary()["preparations"][0]
    assert row["total_ms"] is None
    assert row["clock_complete"] is False


def test_confirmations_dedupe_snapshots_and_count_prior_acceptance(tmp_path):
    log = MeasurementLog(tmp_path)
    log.confirmation_requested("task-a", "pdf-a")
    log.confirmation_accepted("task-a", "pdf-a")
    log = MeasurementLog(tmp_path)
    log.confirmation_requested("task-a", "pdf-a")
    log.confirmation_accepted("task-a", "pdf-a")
    log.confirmation_requested("task-b", "pdf-a")
    log.confirmation_requested("task-b", "pdf-a")
    log.confirmation_requested("task-b", "pdf-new")
    log.confirmation_requested("task-c", "historically-accepted", already_accepted=True)
    summary = log.reuse_summary()
    assert summary["confirmation_requests"] == 4
    assert summary["confirmation_acceptances"] == 1
    assert summary["repeat_confirmation_requests"] == 2
    assert log.summary()["intervention_requests"] == 0
    assert log.summary()["user_operations"] == []


def test_only_matching_task_can_finish_and_revision_changes_start_new(tmp_path):
    log = MeasurementLog(tmp_path)
    first = log.preparation_started("task", "revision-a")
    second = log.preparation_started("task", "revision-b")
    assert first != second
    log.preparation_ready(first, task_id="other", pdf_sha256="a" * 64, inherited=True)
    assert log.reuse_summary()["preparations"] == []
    log.preparation_ready(first, task_id="task", pdf_sha256="a" * 64, inherited=True)
    assert len(log.reuse_summary()["preparations"]) == 1


def test_malformed_telemetry_does_not_enter_summary(tmp_path):
    log = MeasurementLog(tmp_path)
    log.event("resume_preparation_start", request_group="missing-task")
    assert log.reuse_summary()["preparations"] == []
    assert log.reuse_summary()["incomplete"] is True


def test_inherited_pdf_eliminates_a_previously_accepted_content_confirmation(tmp_path):
    baseline_root, reuse_root = tmp_path / "baseline", tmp_path / "reuse"
    baseline_root.mkdir()
    reuse_root.mkdir()
    baseline, reused = MeasurementLog(baseline_root), MeasurementLog(reuse_root)
    for log in (baseline, reused):
        log.confirmation_accepted("historical-task", "same-reviewed-pdf")
    baseline.confirmation_requested("new-task", "same-reviewed-pdf")
    episode = reused.preparation_started("new-task", "same-reviewed-inputs")
    reused.preparation_ready(
        episode, task_id="new-task", pdf_sha256="same-reviewed-pdf", inherited=True
    )
    assert baseline.reuse_summary()["repeat_confirmation_requests"] == 1
    assert reused.reuse_summary()["repeat_confirmation_requests"] == 0
    assert baseline.reuse_summary()["confirmation_acceptances"] == 1
    assert reused.reuse_summary()["confirmation_acceptances"] == 1
