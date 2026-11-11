"""Unknown reading calls are sent again; known failures retain completed source reads."""

import json

import pytest
from test_application_material_packet import batch_reader, many_small_sources
from test_matching_stage_recovery import terminal_model_failure

from career_evidence_graph import application_material_packet as material
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("reading_limits")

APPLICATION = {"company": "Example", "role_title": "Researcher", "job_description": "Risk."}
REQUIREMENTS = [{"text": "Validate risk", "importance": "required", "hard_condition": False}]


class InterruptedRead(BaseException):
    pass


def test_first_unknown_reading_call_is_checkpointed_and_sent_again(tmp_path):
    original = many_small_sources()
    calls = []

    def interrupted(*args, **kwargs):
        calls.append("dispatched")
        raise InterruptedRead

    with pytest.raises(InterruptedRead):
        material.prepare_material_packet(
            APPLICATION,
            original,
            tmp_path / "first",
            runner=interrupted,
            requirements=REQUIREMENTS,
        )
    saved = json.loads((tmp_path / "first/material-packet.json").read_text())
    assert saved["status"] == "reading"
    assert saved["pending_call"]["source_ids"]
    # A model call has no effect outside the App, so the unknown page is read again
    # (Model Call Record, decided 2026-11-09).
    retry_calls = []
    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "retry",
        runner=batch_reader(retry_calls),
        requirements=REQUIREMENTS,
        previous=saved,
    )
    assert packet["status"] == "complete"
    assert "pending_call" not in packet
    assert calls == ["dispatched"]
    assert retry_calls


def test_checkpoint_between_completed_batch_and_next_dispatch_is_resumable(tmp_path, monkeypatch):
    monkeypatch.setattr(material, "MAX_READING_PROMPT_BYTES", 18_000)
    original = many_small_sources()
    first = tmp_path / "first"
    write = material.helper.atomic_write_json

    def stop_between_calls(path, value):
        write(path, value)
        if (
            path == first / "material-packet.json"
            and value["status"] == "reading"
            and not value.get("pending_call")
            and any(row["status"] == "complete" for row in value["source_reads"].values())
        ):
            raise InterruptedRead

    with monkeypatch.context() as patch:
        patch.setattr(material.helper, "atomic_write_json", stop_between_calls)
        with pytest.raises(InterruptedRead):
            material.prepare_material_packet(
                APPLICATION,
                original,
                first,
                runner=batch_reader([]),
                requirements=REQUIREMENTS,
            )
    saved = json.loads((first / "material-packet.json").read_text())
    complete = {key for key, row in saved["source_reads"].items() if row["status"] == "complete"}
    assert complete
    calls = []
    _, resumed = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "resumed",
        runner=batch_reader(calls),
        requirements=REQUIREMENTS,
        previous=saved,
        resume_from=first,
    )
    assert resumed["status"] == "complete"
    reread = {
        row["source"]["source_id"]
        for context, _ in calls
        for row in context.get("source_ranges", [context])
    }
    assert not complete & reread


@pytest.mark.parametrize("old_shape", ["no_packet", "no_pending_marker"])
def test_older_unknown_dispatch_without_native_receipt_is_sent_again(tmp_path, old_shape):
    from career_evidence_graph.application_worker import digest

    original = many_small_sources()
    first = tmp_path / "first"

    def interrupted(*args, **kwargs):
        raise InterruptedRead

    with pytest.raises(InterruptedRead):
        material.prepare_material_packet(
            APPLICATION,
            original,
            first,
            runner=interrupted,
            requirements=REQUIREMENTS,
        )
    path = first / "material-packet.json"
    if old_shape == "no_packet":
        path.unlink()
    else:
        saved = json.loads(path.read_text())
        saved.pop("pending_call")
        saved.pop("revision")
        saved["revision"] = digest(saved)
        path.write_text(json.dumps(saved))
    calls = []
    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "retry",
        runner=batch_reader(calls),
        requirements=REQUIREMENTS,
        resume_from=first,
    )
    assert packet["status"] == "complete"
    assert calls


def test_known_failed_reading_retries_only_unfinished_sources_and_marks_dispatch(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(material, "MAX_READING_PROMPT_BYTES", 18_000)
    original = many_small_sources()
    calls, dispatches = [], []
    successful = batch_reader(calls)

    def fail_second(*args, **kwargs):
        if calls:
            raise terminal_model_failure("Synthetic confirmed terminal CLI failure")
        return successful(*args, **kwargs)

    first = tmp_path / "first"
    with pytest.raises(PortalDataError):
        material.prepare_material_packet(
            APPLICATION,
            original,
            first,
            runner=fail_second,
            requirements=REQUIREMENTS,
        )
    saved = json.loads((first / "material-packet.json").read_text())
    assert saved["status"] == "failed"
    complete = {key for key, row in saved["source_reads"].items() if row["status"] == "complete"}
    retry_calls = []
    _, packet = material.prepare_material_packet(
        APPLICATION,
        original,
        tmp_path / "retry",
        runner=batch_reader(retry_calls),
        requirements=REQUIREMENTS,
        resume_from=first,
        on_dispatch=lambda: dispatches.append("new-origin"),
    )
    assert packet["status"] == "complete"
    assert len(dispatches) == len(retry_calls)
    assert all(packet["source_reads"][key]["reused"] for key in complete)
    delivered = [
        row["source"]["source_id"]
        for context, _ in retry_calls
        for row in context.get("source_ranges", [context])
    ]
    assert not set(delivered) & complete
