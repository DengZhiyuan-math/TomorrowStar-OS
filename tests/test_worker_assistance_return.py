"""T08 return records: a verified outcome releases the writer back to the script."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_assistance import claim_native, prepare_journal

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_worker import (
    adopt_assistance_outcome,
    adopt_assistance_report,
    adopt_assistance_stop,
    assistance_stop_pending,
    revoke_assistance,
    script_writes_allowed,
    start_run,
    valid_assistance_outcome,
    valid_assistance_report,
)
from career_evidence_graph.career_portal_data import PortalDataError


def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def make_report(*, turn="turn-one", received_at=1.0, **claimed_changes):
    claimed = {
        "status": "blocked_segment_resolved",
        "summary": "Country selected",
        "unresolved_action_ids": [],
        "fields": [{"field_id": "country", "state": "filled"}],
        "next_step": {"kind": "return_to_script", "field_id": "phone"},
    } | claimed_changes
    return {
        "protocol": "assistance-report/v1",
        "request_id": "report-one",
        "native_turn_id": turn,
        "received_at": received_at,
        "claimed": claimed,
        "claimed_sha256": sha(claimed),
    }


def make_outcome(state, kind="script_checkpoint", **changes):
    job = state["jobs"][0]
    stop = job["assistance"]["stop"]
    base = stop["observed_at"]
    value = {
        "protocol": "assistance-outcome/v1",
        "kind": kind,
        "report_sha256": sha(job["assistance"]["report"]),
        "stop_request_id": stop["request_id"],
        "session_reclaimed_at": base + 1,
        "page_verification": {
            "at": base + 2,
            "document": {
                "frame_id": "frame",
                "loader_id": "loader",
                "url": job["assistance"]["binding"]["step"],
            },
            "fields": [
                {
                    "id": "country",
                    "required": True,
                    "valid": True,
                    "value_empty": False,
                    "file_count": 0,
                }
            ],
            "worker_source": state["runtime"]["source"]["sha256"],
        },
        "verified": {"materials": [], "optional_failures": []},
        "attributed_fields": [{"field_id": "country", "call_id": "call-one"}],
        "return_count": 1 if kind == "script_checkpoint" else 0,
        "adopted_at": base + 3,
    }
    if kind == "script_checkpoint":
        value["checkpoint_field_id"] = "phone"
    return value | changes


def stop_native(native, ref, *, reason="native_turn_completed", turn_status="completed"):
    state = native.store.load()
    job = state["jobs"][0]
    assert revoke_assistance(job, reason=reason, request_id="stop-one")
    assert adopt_assistance_stop(
        job,
        ref,
        {
            "tools_revoked": True,
            "local_tools_drained": True,
            "process_stopped": True,
            "native_turn_id": "turn-one",
            "native_turn_status": turn_status,
            "stop_status": "stopped",
        },
        request_id="stop-one",
    )
    native.store.save(state)


def reported_native(service, identifier, monkeypatch, *, report=None, **stop):
    native, ref = claim_native(service, identifier, monkeypatch)
    stop_native(native, ref, **stop)
    state = native.store.load()
    assert adopt_assistance_report(
        state["jobs"][0], ref, report or make_report(), request_id="stop-one"
    )
    native.store.save(state)
    return native, ref


def not_adopted_rows(job):
    return [
        row for row in job["observations"] if row.get("action") == "assistance_report_not_adopted"
    ]


def test_released_requires_stop_report_and_outcome(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native, ref = reported_native(service, identifier, monkeypatch)
    state = native.store.load()
    job = state["jobs"][0]
    assert not script_writes_allowed(state)
    assert adopt_assistance_outcome(state, job, ref, make_outcome(state))
    assert job["assistance"]["status"] == "released"
    assert job["assistance"]["active_writer"] == "script"
    assert script_writes_allowed(state)
    native.store.save(state)
    released = native.store.load()
    assert released["jobs"][0]["assistance"] == job["assistance"]

    def tamper(change):
        broken = deepcopy(released)
        change(broken["jobs"][0]["assistance"])
        helper.atomic_write_json(native.store.path, broken)
        with pytest.raises(ValueError, match="assistance"):
            native.assistance_context(identifier)

    tamper(lambda a: a.pop("report"))
    tamper(lambda a: a.pop("outcome"))
    tamper(lambda a: a.pop("stop"))
    tamper(lambda a: a.update(active_writer="codex"))
    tamper(lambda a: a.update(claim_request_id=None))
    tamper(lambda a: a["stop"].update(stop_status="stopping"))
    tamper(lambda a: a["outcome"].update(report_sha256="0" * 64))
    tamper(lambda a: a["outcome"].update(adopted_at=a["stop"]["observed_at"] - 1))
    tamper(lambda a: a["outcome"].update(return_count=2))
    tamper(lambda a: a.update(superseded={"reason": "user_paused", "at": 1.0}))
    # A bare writer flip without the stop/report/outcome chain stays invalid.
    tamper(lambda a: [a.pop(k) for k in ("report", "outcome", "stop")])

    report = make_report()
    assert valid_assistance_report(report)
    for broken in (
        report | {"extra": 1},
        report | {"protocol": "assistance-report/v2"},
        report | {"claimed_sha256": "0" * 64},
        make_report(status="done"),
        make_report(summary="x" * 70_000),
        make_report(unresolved_action_ids=[1]),
        report | {"native_turn_id": ""},
    ):
        assert not valid_assistance_report(broken)
    stop = released["jobs"][0]["assistance"]["stop"]
    saved = released["jobs"][0]["assistance"]["report"]
    outcome = released["jobs"][0]["assistance"]["outcome"]
    assert valid_assistance_outcome(outcome, report=saved, stop=stop)
    for broken in (
        outcome | {"kind": "submitted"},
        outcome | {"session_reclaimed_at": stop["observed_at"] - 1},
        outcome | {"stop_request_id": "other-stop"},
        outcome | {"return_count": 0},
        {k: v for k, v in outcome.items() if k != "checkpoint_field_id"},
        outcome | {"unexpected": True},
    ):
        assert not valid_assistance_outcome(broken, report=saved, stop=stop)


@pytest.mark.parametrize("change", ["pause", "cancel", "skip", "material", "generation"])
def test_outcome_rejected_after_pause_cancel_skip_material_or_generation_change(
    retained_assistance_page, monkeypatch, change
):
    service, identifier = retained_assistance_page
    native, ref = reported_native(service, identifier, monkeypatch)
    outcome = make_outcome(native.store.load())
    if change == "pause":
        native.request("pause", {"controller": "synthetic-controller"})
    elif change == "cancel":
        native.request("cancel", {"controller": "synthetic-controller"})
    elif change == "skip":
        native.request("skip-current", {"application_id": identifier, "request_id": "skip-one"})
    else:
        state = native.store.load()
        if change == "material":
            state["jobs"][0]["file_sha256"] = "f" * 64
        else:
            state["jobs"][0]["assistance"]["generation"] += 1
        native.store.save(state)
    state = native.store.load()
    job = state["jobs"][0]
    if change in {"pause", "cancel", "skip"}:
        assert job["assistance"]["superseded"]["reason"] in {
            "user_paused",
            "cancelled",
            "skip-current",
        }
    report = deepcopy(job["assistance"]["report"])

    assert adopt_assistance_outcome(state, job, ref, outcome)
    assert not adopt_assistance_outcome(state, job, ref, outcome)

    assert "outcome" not in job["assistance"]
    assert job["assistance"]["status"] == "stopped"
    assert job["assistance"]["active_writer"] == "codex"
    assert job["assistance"]["report"] == report
    rows = not_adopted_rows(job)
    assert len(rows) == 1
    assert set(rows[0]) == {"action", "reason", "report_sha256", "at"}
    assert rows[0]["report_sha256"] == sha(report)
    native.store.save(state)
    assert native.store.load()["jobs"][0]["assistance"]["report"] == report


def test_terminal_stop_ignores_a_later_uncertain_adapter_snapshot(
    retained_assistance_page, monkeypatch
):
    """After reclaim the Adapter cannot re-read the handoff; a stopped record is final."""
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    stop_native(native, ref)
    state = native.store.load()
    job = state["jobs"][0]
    before = deepcopy(job["assistance"])
    later = {
        "tools_revoked": True,
        "local_tools_drained": False,
        "process_stopped": True,
        "native_turn_id": "turn-one",
        "native_turn_status": "completed",
        "stop_status": "stopped",
    }
    assert not adopt_assistance_stop(job, ref, later, request_id="stop-one")
    assert job["assistance"] == before
    with pytest.raises(PortalDataError):
        adopt_assistance_stop(job, ref, later, request_id="another-stop")


def test_superseded_is_recorded_once_and_only_for_controls(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native, ref = reported_native(service, identifier, monkeypatch)
    state = native.store.load()
    job = state["jobs"][0]
    assert not revoke_assistance(job, reason="assistance_scope_lost")
    assert "superseded" not in job["assistance"]
    assert revoke_assistance(job, reason="worker_restarted")
    first = deepcopy(job["assistance"]["superseded"])
    assert first["reason"] == "worker_restarted"
    assert not revoke_assistance(job, reason="user_paused")
    assert job["assistance"]["superseded"] == first


@pytest.mark.parametrize("case", ["other_turn", "scope_lost_reason", "interrupted", "native_run"])
def test_outcome_requires_turn_bound_report_and_completed_stop_reason(
    retained_assistance_page, monkeypatch, case
):
    service, identifier = retained_assistance_page
    if case == "native_run":
        native, ref = claim_native(service, identifier, monkeypatch)
        prepare_journal(native, ref)
        stop_native(native, ref)
        state = native.store.load()
        adopt_assistance_report(state["jobs"][0], ref, make_report(), request_id="stop-one")
        native.store.save(state)
    else:
        native, ref = reported_native(
            service,
            identifier,
            monkeypatch,
            report=make_report(turn="other-turn") if case == "other_turn" else None,
            **{
                "scope_lost_reason": {"reason": "assistance_scope_lost"},
                "interrupted": {"turn_status": "interrupted"},
            }.get(case, {}),
        )
    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_outcome(state, job, ref, make_outcome(state))
    assert "outcome" not in job["assistance"]
    assert job["assistance"]["status"] == "stopped"
    assert len(not_adopted_rows(job)) == 1


def test_outcome_adoption_is_idempotent_and_conflicting_reports_rejected(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = reported_native(service, identifier, monkeypatch)
    state = native.store.load()
    job = state["jobs"][0]
    assert not adopt_assistance_report(job, ref, make_report(), request_id="stop-one")
    with pytest.raises(PortalDataError) as conflict:
        adopt_assistance_report(job, ref, make_report(summary="other"), request_id="stop-one")
    assert conflict.value.code == "assistance_outcome_conflict"
    with pytest.raises(PortalDataError):
        adopt_assistance_report(job, ref, make_report() | {"extra": 1}, request_id="stop-one")
    with pytest.raises(PortalDataError):
        adopt_assistance_report(job, ref, make_report(), request_id="other-stop")

    outcome = make_outcome(state)
    assert adopt_assistance_outcome(state, job, ref, outcome)
    released = deepcopy(job)
    assert not adopt_assistance_outcome(state, job, ref, deepcopy(outcome))
    assert job == released
    with pytest.raises(PortalDataError) as conflict:
        adopt_assistance_outcome(state, job, ref, outcome | {"report_sha256": "0" * 64})
    assert conflict.value.code == "assistance_outcome_conflict"
    with pytest.raises(PortalDataError) as conflict:
        adopt_assistance_report(job, ref, make_report(summary="late"), request_id="stop-one")
    assert conflict.value.code == "assistance_outcome_conflict"
    assert job == released
    assert not_adopted_rows(job) == []


def test_released_is_not_stop_pending_for_start_run_or_recovery(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = reported_native(service, identifier, monkeypatch)
    state = native.store.load()
    job = state["jobs"][0]
    assert assistance_stop_pending(job) is False
    adopt_assistance_outcome(state, job, ref, make_outcome(state))
    assert assistance_stop_pending(job) is False
    native.store.save(state)

    start_run(native.store)

    assistance = native.store.load()["jobs"][0]["assistance"]
    assert assistance["status"] == "released"
    assert assistance["stop"]["stop_status"] == "stopped"


def test_second_script_checkpoint_is_rejected(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native, ref = reported_native(service, identifier, monkeypatch)
    state = native.store.load()
    state["jobs"][0]["assistance_return_count"] = 1
    native.store.save(state)

    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_outcome(state, job, ref, make_outcome(state))
    assert "outcome" not in job["assistance"]
    assert not_adopted_rows(job)[0]["reason"] == "assistance_return_limit"

    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_outcome(
        state, job, ref, make_outcome(state, "filling_complete", return_count=1)
    )
    assert job["assistance"]["status"] == "released"
    assert job["assistance_return_count"] == 1


def test_first_script_checkpoint_counts_one_return(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native, ref = reported_native(service, identifier, monkeypatch)
    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_outcome(state, job, ref, make_outcome(state))
    assert job["assistance_return_count"] == 1
    native.store.save(state)
    assert native.store.load()["jobs"][0]["assistance_return_count"] == 1


def completed_native(service, identifier, monkeypatch, **job_changes):
    native, ref = reported_native(
        service, identifier, monkeypatch, report=make_report(status="ready_for_review")
    )
    state = native.store.load()
    job = state["jobs"][0]
    assert adopt_assistance_outcome(state, job, ref, make_outcome(state, "filling_complete"))
    job.update(job_changes)
    native.store.save(state)
    return native, ref


def test_assistance_completion_only_for_released_filling_complete(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.application_worker import assistance_completion

    service, identifier = retained_assistance_page
    assert assistance_completion(service.store.load()["jobs"][0]) is None
    native, ref = reported_native(service, identifier, monkeypatch)
    state = native.store.load()
    job = state["jobs"][0]
    assert assistance_completion(job) is None
    checkpoint = deepcopy(state)
    adopt_assistance_outcome(checkpoint, checkpoint["jobs"][0], ref, make_outcome(checkpoint))
    assert checkpoint["jobs"][0]["assistance"]["status"] == "released"
    assert assistance_completion(checkpoint["jobs"][0]) is None

    outcome = make_outcome(state, "filling_complete")
    adopt_assistance_outcome(state, job, ref, outcome)
    completion = assistance_completion(job)
    assert completion == outcome
    completion["kind"] = "changed"
    assert job["assistance"]["outcome"]["kind"] == "filling_complete"
    broken = deepcopy(job)
    broken["assistance"]["outcome"]["report_sha256"] = "0" * 64
    assert assistance_completion(broken) is None


def review(native, identifier):
    return native.request(
        "review", {"application_id": identifier, "actor": "system", "human_reviewed": False}
    )


def test_review_accepts_verified_codex_completion_without_script_stability(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, _ref = completed_native(service, identifier, monkeypatch, status="ready_for_review")
    form = native.store.load()["jobs"][0]["form_state"]
    assert form.get("parser", {}).get("status") != "stable"

    job = review(native, identifier)["jobs"][0]

    assert job["handed_off"] is True
    assert job["handoff"]["source"] == "automatic_submit_wait"
    assert job["status"] == "ready_for_review"
    assert not job.get("manual_submission")
    saved = native.store.load()["jobs"][0]
    assert saved["form_state"] == form
    assert not saved.get("manual_submission")
    assert native.store.applications.get_application(identifier)["status"] == "drafting"

    # Ordinary script jobs still require script-parser stability.
    plain = service.store.load()
    plain["jobs"][0].pop("assistance")
    plain["jobs"][0].update(status="ready_for_review", handed_off=False)
    service.store.save(plain)
    with pytest.raises(PortalDataError) as blocked:
        review(service, identifier)
    assert blocked.value.code == "form_review_pending"


@pytest.mark.parametrize("case", ["unknown", "cover_letter", "required_empty", "material"])
def test_review_still_blocks_unknown_or_missing_material_for_codex_completion(
    retained_assistance_page, monkeypatch, case
):
    service, identifier = retained_assistance_page
    native, _ref = completed_native(service, identifier, monkeypatch, status="ready_for_review")
    state = native.store.load()
    job = state["jobs"][0]
    if case == "unknown":
        job["intent"] = {"action": "upload", "attempt_id": "unknown-upload"}
    elif case == "cover_letter":
        job["cover_letter_delivery"] = {"requirement": "required", "status": "running"}
    elif case == "required_empty":
        # A valid outcome may still record an empty required field; review refuses it.
        job["assistance"]["outcome"]["page_verification"]["fields"][0]["value_empty"] = True
    else:
        Path(job["file_path"]).write_bytes(b"%PDF-1.4 changed")
    native.store.save(state)
    before = native.store.load()

    with pytest.raises(PortalDataError) as blocked:
        review(native, identifier)

    assert blocked.value.code in {
        "form_review_pending",
        "cover_letter_review_pending",
        "single_material_sources_invalid",
        "file_changed",
    }
    after = native.store.load()
    assert after["jobs"][0] == before["jobs"][0]
    assert not after["jobs"][0].get("handed_off")


def lose_outcome_save(native, ref, monkeypatch):
    state = native.store.load()
    outcome = make_outcome(state, "filling_complete")
    job = state["jobs"][0]
    assert adopt_assistance_outcome(state, job, ref, outcome)
    original = helper.atomic_write_json
    failures = []

    def fail_once(path, value):
        if path == native.store.path and not failures:
            failures.append(path)
            raise OSError("synthetic lost save")
        return original(path, value)

    monkeypatch.setattr(helper, "atomic_write_json", fail_once)
    with pytest.raises(OSError):
        native.store.save(state)
    monkeypatch.setattr(helper, "atomic_write_json", original)
    assert native.store.stop_reason() == "checkpoint_unavailable"
    saved = native.store.load()["jobs"][0]["assistance"]
    assert saved["status"] == "stopped" and "outcome" not in saved
    # Continue lifts this storage stop itself once the checkpoint is writable again.
    return outcome


def test_lost_outcome_save_readopts_same_report_after_continue_only(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = reported_native(
        service, identifier, monkeypatch, report=make_report(status="ready_for_review")
    )
    outcome = lose_outcome_save(native, ref, monkeypatch)
    commands = deepcopy(native.store.load()["commands"])

    native.request("resume", {"controller": "synthetic-controller"})

    assert native.store.stop_reason() == ""
    state = native.store.load()
    assert state["control"] == "running"
    job = state["jobs"][0]
    assert job["status"] not in {"needs_recheck", "cancelled"}
    assert state["resume_serial"] == job["assistance"]["binding"]["resume_serial"] + 1
    retry = outcome | {"adopted_at": outcome["adopted_at"] + 1}
    assert adopt_assistance_outcome(state, job, ref, retry)
    assert job["assistance"]["status"] == "released"
    assert job["assistance"]["outcome"]["report_sha256"] == outcome["report_sha256"]
    assert not_adopted_rows(job) == []
    assert state["commands"] == commands
    native.store.save(state)
    assert native.store.load()["jobs"][0]["assistance"]["status"] == "released"

    # A different report is still a conflict, never a second adoption.
    with pytest.raises(PortalDataError) as conflict:
        adopt_assistance_outcome(state, job, ref, retry | {"report_sha256": "0" * 64})
    assert conflict.value.code == "assistance_outcome_conflict"


@pytest.mark.parametrize("change", ["pause", "material", "controller", "same_serial_scope"])
def test_readoption_refused_after_pause_or_material_change(
    retained_assistance_page, monkeypatch, change
):
    service, identifier = retained_assistance_page
    native, ref = reported_native(
        service, identifier, monkeypatch, report=make_report(status="ready_for_review")
    )
    outcome = lose_outcome_save(native, ref, monkeypatch)
    if change == "pause":
        native.request("pause", {"controller": "synthetic-controller"})
    if change == "controller":
        native.request("resume", {"controller": "other-controller"})
    elif change != "same_serial_scope":
        native.request("resume", {"controller": "synthetic-controller"})
    state = native.store.load()
    job = state["jobs"][0]
    if change == "material":
        job["file_sha256"] = "f" * 64
    elif change == "same_serial_scope":
        # Only a Continue-advanced serial is excused; an earlier serial is not.
        state["resume_serial"] = job["assistance"]["binding"]["resume_serial"] - 1

    assert adopt_assistance_outcome(state, job, ref, outcome)

    assert "outcome" not in job["assistance"]
    assert job["assistance"]["status"] == "stopped"
    assert job["assistance"]["active_writer"] == "codex"
    assert len(not_adopted_rows(job)) == 1


def test_sync_failure_retries_pending_sync_only(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native, _ref = completed_native(service, identifier, monkeypatch, status="ready_for_review")
    applications = native.store.applications
    original = applications.update_application
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(args)
        raise OSError("synthetic app unavailable")

    state = native.store.load()
    job = state["jobs"][0]
    monkeypatch.setattr(applications, "update_application", unavailable)
    native.store.sync(job, "申请页面已填写完成，请到原申请网站确认并最终提交。")
    assert job["pending_sync"] and job["sync_error"] == "write_failed"
    native.store.save(state)
    before = native.store.load()

    monkeypatch.setattr(applications, "update_application", original)
    after = native.request("retry-sync", {"application_id": identifier})

    job = native.store.load()["jobs"][0]
    assert job["pending_sync"] == "" and job["sync_error"] == ""
    assert applications.get_application(identifier)["next_action"].startswith("申请页面已填写完成")
    for key in ("assistance", "form_state", "intent", "observations", "status", "handed_off"):
        assert job.get(key) == before["jobs"][0].get(key)
    assert native.store.load()["commands"] == before["commands"]
    assert after["jobs"][0]["status"] == "ready_for_review"
    assert len(calls) == 1
