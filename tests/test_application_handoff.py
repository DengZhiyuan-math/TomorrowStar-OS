"""The Codex executor reports evidence; only explicit human decisions update notes."""

import base64
import hashlib
import subprocess

import pytest

from career_evidence_graph.application_handoff import CodexHandoffService
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

URL = "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc"
PDF = b"%PDF-1.4 Synthetic approved resume"
SHA = hashlib.sha256(PDF).hexdigest()


@pytest.fixture
def handoff(tmp_path):
    apps = tmp_path / "applications"
    apps.mkdir()
    store = ApplicationStore(apps)
    app = store.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "url": URL,
            "application_strategy": "manual",
        }
    )
    service = CodexHandoffService(store, tmp_path / "codex")
    return service, store, app


def prepare(service, app):
    return service.request(
        "prepare",
        {
            "application_id": app["id"],
            "revision": app["revision"],
            "country": "CHE",
            "filename": "approved.pdf",
            "file_base64": base64.b64encode(PDF).decode(),
            "acknowledge": True,
        },
    )["active_task"]


def act(service, task, operation, **payload):
    return service.request(
        operation, {"task_id": task["id"], "task_revision": task["revision"], **payload}
    )


def ready(service, task, token):
    return act(
        service,
        task,
        "readback",
        claim_token=token,
        result="ready",
        page_url=URL,
        source="Synthetic live field readback; screenshot 01",
        fields=[{"question": "Full name", "value": "Synthetic Person"}],
        attachment={"filename": "approved.pdf", "sha256": SHA},
        missing=[],
    )["active_task"]


def test_single_job_lifecycle_survives_restart_without_automating_submission(handoff, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *a, **k: pytest.fail("Handoff must not start browser or model processes"),
    )
    service, store, app = handoff
    task = prepare(service, app)
    assert task["status"] == "prepared" and task["file_sha256"] == SHA
    assert "claim" in task["prompt"] and "Submit" in task["prompt"]
    assert store.get_application(app["id"])["status"] == "drafting"
    reply = act(service, task, "claim", owner="synthetic-codex-chat")
    token, task = reply["claim_token"], reply["active_task"]
    service = CodexHandoffService(store, service.root)
    assert token not in str(service.snapshot())
    task = ready(service, task, token)
    assert task["status"] == "ready_for_review"
    assert store.get_application(app["id"])["status"] == "drafting"
    task = act(
        service, task, "review", acknowledge=True, source="User checked fields and approved file"
    )["active_task"]
    assert task["status"] == "reviewed"
    reply = act(
        service,
        task,
        "submitted",
        acknowledge=True,
        source="User clicked Submit and observed completion",
    )
    task = next(t for t in reply["tasks"] if t["id"] == task["id"])
    assert task["status"] == "submitted" and reply["active_task"] is None
    assert store.get_application(app["id"])["status"] == "applied"
    reply = act(
        service, task, "receipt", acknowledge=True, locator="Synthetic confirmation page receipt-42"
    )
    task = next(t for t in reply["tasks"] if t["id"] == task["id"])
    assert task["status"] == "confirmed"
    assert store.get_application(app["id"])["status"] == "confirmation_received"
    assert task["readbacks"][0]["fields"][0]["value"] == "Synthetic Person"
    assert not list(service.root.rglob("DevToolsActivePort"))


def test_submission_evidence_is_retained_when_note_sync_conflicts(handoff):
    service, store, app = handoff
    task = prepare(service, app)
    claimed = act(service, task, "claim", owner="codex-a")
    task = ready(service, claimed["active_task"], claimed["claim_token"])
    task = act(service, task, "review", acknowledge=True, source="User review")["active_task"]
    external = store.update_application(
        app["id"], {"notes": "External editor keeps this"}, app["revision"]
    )
    task = act(service, task, "submitted", acknowledge=True, source="User already submitted")[
        "active_task"
    ]
    assert task["status"] == "submitted" and task["sync_error"] == "revision-conflict"
    assert task["submission"]["source"] == "User already submitted"
    assert store.get_application(app["id"])["status"] == "drafting"
    reply = act(
        service,
        task,
        "retry-sync",
        revision=external["revision"],
        acknowledge=True,
        source="User checked external edit; same job and actual submission",
    )
    assert reply["active_task"] is None
    note = store.get_application(app["id"])
    assert note["status"] == "applied" and note["notes"] == "External editor keeps this"
    assert len(reply["tasks"][0]["readbacks"]) == 1


def test_unknown_result_survives_changed_inputs_and_requires_explicit_resolution(handoff):
    service, store, app = handoff
    task = prepare(service, app)
    claimed = act(service, task, "claim", owner="codex-a")
    task, token = claimed["active_task"], claimed["claim_token"]
    changed = store.update_application(app["id"], {"notes": "External edit"}, app["revision"])
    task = act(
        service,
        task,
        "readback",
        claim_token=token,
        result="unknown",
        page_url=URL,
        source="Upload response was lost; preserve original tab",
        fields=[],
        missing=["Attachment result unknown"],
    )["active_task"]
    assert task["status"] == "needs_recheck"
    assert task["readbacks"][-1]["source"].startswith("Upload response was lost")
    with pytest.raises(Exception) as error:
        act(service, task, "claim", owner="codex-b")
    assert error.value.code == "handoff_claimed"
    task = act(
        service,
        task,
        "resolve",
        acknowledge=True,
        revision=changed["revision"],
        source="User inspected original page; upload was not applied",
        conclusion="not_applied",
    )["active_task"]
    assert task["status"] == "claimed"
    assert len(task["readbacks"]) == 1
    task = ready(service, task, token)
    assert task["status"] == "ready_for_review"
    result = act(
        service,
        task,
        "release",
        acknowledge=True,
        source="User stopped executor, resolved pending action and closed tab",
    )
    assert result["active_task"] is None
    assert result["tasks"][0]["status"] == "cancelled"
    assert store.get_application(app["id"])["status"] == "drafting"


def test_confirmed_answers_require_human_adoption_and_scope(handoff):
    service, store, app = handoff
    service.request(
        "answer",
        {"question": "Full name", "value": "Synthetic Person", "scope": {}, "acknowledge": True},
    )
    service.request(
        "answer",
        {
            "question": "Country-specific authorization",
            "value": "Yes",
            "scope": {"country": "USA"},
            "acknowledge": True,
        },
    )
    task = prepare(service, app)
    assert [(a["question"], a["value"]) for a in task["answers"]] == [
        ("Full name", "Synthetic Person")
    ]
    claim = act(service, task, "claim", owner="codex-a")
    token = claim["claim_token"]
    task = service.request(
        "answer",
        {"question": "Full name", "value": "Synthetic Corrected", "scope": {}, "acknowledge": True},
    )["active_task"]
    assert task["status"] == "needs_recheck"
    with pytest.raises(PortalDataError):
        ready(service, task, token)
    task = act(
        service,
        task,
        "resolve",
        acknowledge=True,
        conclusion="current_matches",
        source="User checked original field against corrected fact",
    )["active_task"]
    assert task["answers"][0]["value"] == "Synthetic Corrected"
    assert task["status"] == "claimed"


def test_task_scoped_answer_checks_complete_current_binding_before_adoption(handoff):
    service, store, app = handoff
    task = prepare(service, app)
    payload = {
        "task_id": task["id"],
        "task_revision": task["revision"],
        "question": "Full name",
        "value": "Synthetic Person",
        "scope": {"application_id": app["id"]},
        "acknowledge": True,
    }
    for invalid in (
        {k: v for k, v in payload.items() if k != "task_revision"},
        {k: v for k, v in payload.items() if k != "task_id"},
        {**payload, "task_revision": "stale"},
    ):
        with pytest.raises(PortalDataError):
            service.request("answer", invalid)
        assert service.snapshot()["library"] == []
    result = service.request("answer", payload)
    assert result["active_task"]["answers"][0]["value"] == "Synthetic Person"
    assert len(result["library"]) == 1


def test_cli_claim_and_readback_use_the_same_durable_task(handoff, tmp_path):
    import json
    import sys
    from pathlib import Path

    service, store, app = handoff
    task = prepare(service, app)
    script = Path(__file__).parents[1] / "scripts/run_codex_handoff.py"
    request = tmp_path / "claim.json"
    request.write_text(
        json.dumps(
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "owner": "synthetic-codex-cli",
            }
        )
    )
    command = [
        sys.executable,
        str(script),
        "--applications",
        str(store.root),
        "--root",
        str(service.root),
    ]
    result = subprocess.run(
        [*command, "claim", "--request", str(request)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    reply = json.loads(result.stdout)
    assert reply["active_task"]["claim"]["owner"] == "synthetic-codex-cli"
    state = subprocess.run([*command, "snapshot"], capture_output=True, text=True)
    assert state.returncode == 0
    assert reply["claim_token"] not in state.stdout
    assert json.loads(state.stdout)["active_task"]["status"] == "claimed"


def test_historical_receipt_cannot_downgrade_an_advanced_note(handoff):
    service, store, app = handoff
    task = prepare(service, app)
    claimed = act(service, task, "claim", owner="codex-a")
    task = ready(service, claimed["active_task"], claimed["claim_token"])
    task = act(service, task, "review", acknowledge=True, source="User reviewed")["active_task"]
    current = store.update_application(app["id"], {"status": "rejected"}, app["revision"])
    task = act(service, task, "submitted", acknowledge=True, source="User had already submitted")[
        "active_task"
    ]
    reply = act(
        service,
        task,
        "retry-sync",
        revision=current["revision"],
        acknowledge=True,
        source="Keep the later rejection, retain the old submission evidence",
    )
    task = reply["tasks"][0]
    assert store.get_application(app["id"])["status"] == "rejected"
    reply = act(service, task, "receipt", acknowledge=True, locator="Historical confirmation email")
    task = reply["tasks"][0]
    assert task["status"] == "confirmed" and task["sync_error"] == "status_advanced"
    assert store.get_application(app["id"])["status"] == "rejected"
    reply = act(
        service,
        task,
        "retry-sync",
        acknowledge=True,
        revision=current["revision"],
        source="Keep later note intact; historical receipt stays in task",
        preserve_note=True,
    )
    assert reply["tasks"][0]["pending_sync"] is None
    assert store.get_application(app["id"])["status"] == "rejected"


@pytest.mark.parametrize(
    "operation,fail_at", [("prepare", 1), ("prepare", 2), ("release", 1), ("release", 2)]
)
def test_storage_failure_has_a_recoverable_intent(handoff, monkeypatch, operation, fail_at):
    service, store, app = handoff
    task = prepare(service, app) if operation == "release" else None
    save = service._save
    calls = 0

    def fail_once(state):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError("Synthetic durable write failure")
        save(state)

    monkeypatch.setattr(service, "_save", fail_once)
    with pytest.raises(OSError):
        if operation == "prepare":
            prepare(service, app)
        else:
            act(service, task, "release", acknowledge=True, source="User closed the unused task")
    service = CodexHandoffService(store, service.root)
    if operation == "prepare":
        task = prepare(service, app)
        reply = act(service, task, "claim", owner="codex-a")
        assert reply["active_task"]["status"] == "claimed"
    else:
        task = service.snapshot()["tasks"][0]
        reply = act(
            service, task, "release", acknowledge=True, source="User confirms release completion"
        )
        assert reply["active_task"] is None and not reply["tasks"][0].get("release_pending")
    assert store.get_application(app["id"])["status"] == "drafting"


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("wrong_token", "handoff_owner"),
        ("second_owner", "handoff_claimed"),
        ("stale_task", "conflict"),
        ("unreviewed_submission", "human_review_required"),
        ("missing_ack", "human_confirmation_required"),
        ("wrong_pdf", "readback_incomplete"),
        ("different_job", "handoff_target"),
    ],
)
def test_claim_and_evidence_guards_preserve_note_and_task(handoff, fault, expected):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, store, app = handoff
    original = prepare(service, app)
    reply = act(service, original, "claim", owner="codex-a")
    task, token = reply["active_task"], reply["claim_token"]
    before = service.snapshot()
    payload = dict(
        claim_token=token,
        result="ready",
        page_url=URL,
        source="Synthetic readback",
        fields=[{"question": "Name", "value": "Synthetic Person"}],
        missing=[],
        attachment={"filename": "approved.pdf", "sha256": SHA},
    )
    with pytest.raises(PortalDataError) as error:
        if fault == "second_owner":
            act(service, task, "claim", owner="codex-b")
        elif fault == "stale_task":
            act(service, original, "claim", owner="codex-b")
        elif fault == "unreviewed_submission":
            act(service, task, "submitted", acknowledge=True, source="Unreviewed")
        elif fault == "missing_ack":
            act(service, task, "release", source="No explicit human confirmation")
        else:
            if fault == "wrong_token":
                payload["claim_token"] = "not-the-owner"
            elif fault == "wrong_pdf":
                payload["attachment"]["sha256"] = "0" * 64
            else:
                payload["page_url"] = URL.replace("123456789abc", "123456789abd")
            act(service, task, "readback", **payload)
    assert error.value.code == expected
    assert service.snapshot() == before
    assert store.get_application(app["id"])["status"] == "drafting"


def test_late_unknown_result_is_retained_after_answer_change_pauses_executor(handoff):
    service, _, app = handoff
    task = prepare(service, app)
    claimed = act(service, task, "claim", owner="codex-a")
    token = claimed["claim_token"]
    task = service.request(
        "answer",
        {
            "question": "Full name",
            "value": "Synthetic Correction",
            "scope": {},
            "acknowledge": True,
        },
    )["active_task"]
    task = act(
        service,
        task,
        "readback",
        claim_token=token,
        result="unknown",
        page_url=URL,
        source="Late response after pause: attachment outcome still unknown",
        fields=[],
        missing=["Read original page before retry"],
    )["active_task"]
    assert task["status"] == "needs_recheck"
    assert task["readbacks"][-1]["result"] == "unknown"
