"""A new page attempt reuses saved material, never old browser success."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_application_handoff import PDF, SHA, act, prepare, ready
from test_application_handoff import handoff as handoff

from career_evidence_graph import application_handoff as handoff_module
from career_evidence_graph._vendor import job_apply_store as answer_store
from career_evidence_graph.application_execution import (
    release_execution,
    require_execution,
    reserve_execution,
)
from career_evidence_graph.application_handoff import CodexHandoffService
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest


def prepared_again(service, old, request_id="new-page-1"):
    return service.request(
        "restart",
        {"task_id": old["id"], "task_revision": old["revision"], "request_id": request_id},
    )


def ready_task(service, app):
    task = prepare(service, app)
    reply = act(service, task, "claim", owner="previous-codex-chat")
    return ready(service, reply["active_task"], reply["claim_token"])


def test_new_page_attempt_reuses_pdf_and_keeps_old_fill_as_a_hint(handoff):
    service, store, app = handoff
    old = ready_task(service, app)
    reports = old["readbacks"]
    reply = prepared_again(service, old)
    current = reply["active_task"]
    assert current["id"] != old["id"] and current["status"] == "prepared"
    assert current["application_id"] == app["id"]
    assert current["filename"] == "approved.pdf" and current["file_sha256"] == SHA
    assert Path(current["file_path"]).read_bytes() == PDF
    assert current["claim"] is None and current["readbacks"] == []
    assert current["submission"] is None and current["receipt"] is None
    assert current["reuse_context"]["predecessor_id"] == old["id"]
    assert current["reuse_context"]["fields"] == [
        {"question": "Full name", "value": "Synthetic Person"}
    ]
    historical = next(row for row in reply["tasks"] if row["id"] == old["id"])
    assert historical["active"] is False and historical["readbacks"] == reports
    assert Path(historical["file_path"]).read_bytes() == PDF
    assert store.get_application(app["id"])["status"] == "drafting"
    assert service.snapshot()["library"] == []
    assert "reuse_context" in current["prompt"] and "Submit" in current["prompt"]


def test_lost_restart_response_reuses_the_same_attempt_and_new_claim(handoff):
    service, store, app = handoff
    old = ready_task(service, app)
    current = prepared_again(service, old)["active_task"]
    claimed = act(service, current, "claim", owner="new-codex-chat")
    before = service.path.read_bytes()
    reopened = CodexHandoffService(store, service.root)
    reply = prepared_again(reopened, old)
    assert reply["active_task"]["id"] == current["id"]
    assert reply["active_task"]["status"] == "claimed"
    assert reply["active_task"]["claim"]["owner"] == "new-codex-chat"
    assert service.path.read_bytes() == before
    assert len(reply["tasks"]) == 2
    assert claimed["claim_token"] not in str(reply)


def test_restart_recovers_when_old_owner_release_response_is_lost(handoff, monkeypatch):
    service, store, app = handoff
    old = ready_task(service, app)
    release = handoff_module.release_execution
    calls = 0

    def lose_response(*args):
        nonlocal calls
        calls += 1
        release(*args)
        if calls == 1:
            raise OSError("Old owner released; local response was lost")

    monkeypatch.setattr(handoff_module, "release_execution", lose_response)
    with pytest.raises(OSError):
        prepared_again(service, old)
    reopened = CodexHandoffService(store, service.root)
    result = prepared_again(reopened, old)
    current = result["active_task"]
    assert current["status"] == "prepared" and current["id"] != old["id"]
    assert current["reuse_context"]["predecessor_revision"] == old["revision"]
    assert len(result["tasks"]) == 2
    assert prepared_again(reopened, old)["active_task"]["id"] == current["id"]


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4])
def test_restart_recovers_each_durable_publish_window(handoff, monkeypatch, fail_at):
    service, store, app = handoff
    old = ready_task(service, app)
    save = service._save
    count = 0

    def fail_once(state):
        nonlocal count
        count += 1
        if count == fail_at:
            raise OSError("Synthetic new-page state save failure")
        save(state)

    monkeypatch.setattr(service, "_save", fail_once)
    with pytest.raises(OSError):
        prepared_again(service, old)
    reopened = CodexHandoffService(store, service.root)
    reply = prepared_again(reopened, old)
    current = reply["active_task"]
    assert len(reply["tasks"]) == 2
    assert current["status"] == "prepared" and not current.get("reservation_pending")
    assert Path(current["file_path"]).read_bytes() == PDF
    assert prepared_again(reopened, old)["active_task"]["id"] == current["id"]


def test_existing_attempt_is_a_verified_read_only_tokenless_delivery(handoff):
    service, store, app = handoff
    old = ready_task(service, app)
    current = prepared_again(service, old)["active_task"]
    claimed = act(service, current, "claim", owner="new-codex-chat")
    before = service.path.read_bytes()
    reader = CodexHandoffService(store, service.root, existing_only=True)
    delivered = reader.existing_attempt(current["id"])
    assert delivered["id"] == current["id"] and delivered["status"] == "claimed"
    assert delivered["reuse_context"]["predecessor_id"] == old["id"]
    assert "prompt" in delivered and "_claim_token" not in delivered
    assert claimed["claim_token"] not in str(delivered)
    assert service.path.read_bytes() == before
    historical = reader.existing_attempt(old["id"])
    assert historical["status"] == "cancelled" and historical["readbacks"] == old["readbacks"]


def test_new_attempt_refuses_a_new_saved_hold_before_releasing_old_owner(handoff):
    service, store, app = handoff
    old = ready_task(service, app)
    store.update_application(app["id"], {"application_strategy": "hold"}, app["revision"])
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError, match="分流"):
        prepared_again(service, old)
    assert service.path.read_bytes() == before
    assert service.snapshot()["active_task"]["id"] == old["id"]


def test_reused_hints_omit_redactions_empty_values_and_ambiguous_questions(handoff):
    service, _, app = handoff
    task = prepare(service, app)
    claimed = act(service, task, "claim", owner="previous-codex-chat")
    old = act(
        service,
        claimed["active_task"],
        "readback",
        claim_token=claimed["claim_token"],
        result="ready",
        page_url=task["job_url"],
        source="Synthetic original fields",
        fields=[
            {"question": "Email", "value": "redacted"},
            {"question": "Phone", "value": "<redacted>"},
            {"question": "Website", "value": "[REDACTED]"},
            {"question": "Optional", "value": ""},
            {"question": "Preferred city", "value": "Zurich"},
            {"question": "preferred city*", "value": "Paris"},
            {"question": "Motivation", "value": "Keep my wording.\nAnd my second line."},
            {"question": "No marketing", "value": "unchecked"},
        ],
        attachment={"filename": "approved.pdf", "sha256": SHA},
        missing=[],
    )["active_task"]
    current = prepared_again(service, old)["active_task"]
    assert current["reuse_context"]["fields"] == [
        {"question": "Motivation", "value": "Keep my wording.\nAnd my second line."},
        {"question": "No marketing", "value": "unchecked"},
    ]
    assert service.snapshot()["library"] == []


@pytest.mark.parametrize("changed", ["owner", "target", "applied", "pdf"])
def test_changed_execution_or_material_cannot_release_the_old_attempt(handoff, changed):
    service, store, app = handoff
    old = ready_task(service, app)
    if changed == "owner":
        owner = f"codex:{service.root}:{old['id']}"
        release_execution(store, app["id"], owner, "codex")
        reserve_execution(store, app["id"], "another-executor", "automated")
    elif changed == "target":
        store.update_application(
            app["id"], {"url": app["url"].replace("123456789abc", "123456789abd")}, app["revision"]
        )
    elif changed == "applied":
        store.update_application(app["id"], {"status": "applied"}, app["revision"])
    else:
        Path(old["file_path"]).write_bytes(b"%PDF-1.4 External replacement")
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError):
        prepared_again(service, old)
    assert service.path.read_bytes() == before
    if changed == "owner":
        assert require_execution(store, app["id"], "another-executor", "automated")["active"]


@pytest.mark.parametrize(
    "state", ["claimed", "needs_input", "needs_recheck", "reviewed", "submitted"]
)
def test_a_nonready_or_unknown_attempt_cannot_be_replayed(handoff, state):
    service, _, app = handoff
    task = prepare(service, app)
    claimed = act(service, task, "claim", owner="previous-codex-chat")
    task = claimed["active_task"]
    if state in {"needs_input", "needs_recheck"}:
        task = act(
            service,
            task,
            "readback",
            claim_token=claimed["claim_token"],
            result="unknown" if state == "needs_recheck" else "needs_input",
            page_url=task["job_url"],
            source="Pending required answer or unknown remote result",
            fields=[],
            missing=["Must observe result before proceeding"],
        )["active_task"]
    elif state in {"reviewed", "submitted"}:
        task = ready(service, task, claimed["claim_token"])
        task = act(service, task, "review", acknowledge=True, source="User review")["active_task"]
        if state == "submitted":
            reply = act(service, task, "submitted", acknowledge=True, source="User submitted")
            task = next(row for row in reply["tasks"] if row["id"] == task["id"])
    assert task["status"] == state
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError):
        prepared_again(service, task)
    assert service.path.read_bytes() == before


def test_new_attempt_reads_current_record_and_confirmed_answers(handoff):
    service, store, app = handoff
    old = ready_task(service, app)
    current = store.update_application(
        app["id"], {"notes": "Keep this later manual edit"}, app["revision"]
    )
    service.answers.put_answer(
        {
            "question": "Full name",
            "value": "Current confirmed name",
            "scope": {},
            "state": "confirmed",
            "source": "Explicit saved correction",
        }
    )
    reply = prepared_again(service, old)
    new = reply["active_task"]
    assert new["application_revision"] == current["revision"]
    assert [row["value"] for row in new["answers"]] == ["Current confirmed name"]
    assert new["reuse_context"]["fields"] == [
        {"question": "Full name", "value": "Synthetic Person"}
    ]
    assert next(row for row in reply["tasks"] if row["id"] == old["id"])["answers"] == []
    assert store.get_application(app["id"])["notes"] == "Keep this later manual edit"


def test_recovery_does_not_release_an_owner_that_arrived_after_old_release(handoff, monkeypatch):
    service, store, app = handoff
    old = ready_task(service, app)
    release = handoff_module.release_execution
    called = False

    def other_owner_arrives(*args):
        nonlocal called
        release(*args)
        if not called:
            called = True
            reserve_execution(store, app["id"], "another-executor", "automated")
            raise OSError("Another executor arrived after old release")

    monkeypatch.setattr(handoff_module, "release_execution", other_owner_arrives)
    with pytest.raises(OSError):
        prepared_again(service, old)
    reopened = CodexHandoffService(store, service.root)
    with pytest.raises(PortalDataError) as error:
        prepared_again(reopened, old)
    assert error.value.code == "execution_conflict"
    assert require_execution(store, app["id"], "another-executor", "automated")["active"]
    historical = next(row for row in reopened.snapshot()["tasks"] if row["id"] == old["id"])
    assert historical["readbacks"] == old["readbacks"]


@pytest.mark.parametrize("corrupt", ["field", "executor", "source", "claim_token"])
def test_invalid_historical_ready_proof_cannot_authorize_a_new_attempt(handoff, corrupt):
    service, _, app = handoff
    old = ready_task(service, app)
    state = json.loads(service.path.read_text())
    saved = state["tasks"][0]
    if corrupt == "field":
        saved["readbacks"][-1]["fields"] = [None]
    elif corrupt == "executor":
        saved["readbacks"][-1]["executor"] = "not-the-claimed-executor"
    elif corrupt == "source":
        saved["readbacks"][-1]["source"] = ""
    else:
        saved.pop("_claim_token")
    saved["revision"] = record_digest(
        {key: value for key, value in saved.items() if key != "revision"}
    )
    service.path.write_text(json.dumps(state))
    old["revision"] = saved["revision"]
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError):
        prepared_again(service, old)
    assert service.path.read_bytes() == before


def test_new_attempt_and_fresh_cli_instance_use_declared_information_library(handoff, tmp_path):
    service, store, app = handoff
    service.request(
        "answer",
        {"question": "Email", "value": "old@example.invalid", "scope": {}, "acknowledge": True},
    )
    old = ready_task(service, app)
    old_library = (service.root / "answer-library/answers.json").read_bytes()
    primary = answer_store.Store(
        tmp_path / "primary-information", legacy_profile=tmp_path / "no-import"
    )
    primary.initialize()
    primary.put_answer(
        {
            "question": "Email",
            "value": "current@example.invalid",
            "scope": {},
            "state": "confirmed",
            "source": "Current confirmed contact",
        }
    )
    selected = CodexHandoffService(store, service.root, information_library_root=primary.root)
    current = prepared_again(selected, old)["active_task"]
    assert current["information_library_root"] == str(primary.root)
    assert [row["value"] for row in current["answers"]] == ["current@example.invalid"]
    reopened = CodexHandoffService(store, service.root)
    claimed = act(reopened, current, "claim", owner="current-codex-chat")
    assert [row["value"] for row in claimed["active_task"]["answers"]] == [
        "current@example.invalid"
    ]
    assert [row["value"] for row in reopened.snapshot()["library"]] == ["current@example.invalid"]
    assert (service.root / "answer-library/answers.json").read_bytes() == old_library


def test_task_scoped_answer_updates_declared_library_with_history_not_legacy_copy(
    handoff, tmp_path
):
    service, store, app = handoff
    old = ready_task(service, app)
    legacy_before = (service.root / "answer-library/answers.json").read_bytes()
    primary = answer_store.Store(
        tmp_path / "primary-information", legacy_profile=tmp_path / "no-import"
    )
    primary.initialize()
    primary.put_answer(
        {
            "question": "Email",
            "value": "current@example.invalid",
            "scope": {},
            "state": "confirmed",
            "source": "Current confirmed contact",
        }
    )
    selected = CodexHandoffService(store, service.root, information_library_root=primary.root)
    current = prepared_again(selected, old)["active_task"]
    reopened = CodexHandoffService(store, service.root)
    result = act(
        reopened,
        current,
        "answer",
        question="Email",
        value="corrected@example.invalid",
        scope={},
        acknowledge=True,
    )
    assert [row["value"] for row in result["active_task"]["answers"]] == [
        "corrected@example.invalid"
    ]
    assert [row["value"] for row in result["library"]] == ["corrected@example.invalid"]
    assert (service.root / "answer-library/answers.json").read_bytes() == legacy_before
    receipts = list((primary.root / ".tomorrowstar-answer-history").glob("*/requested.json"))
    assert len(receipts) == 1


def test_declared_information_root_survives_interrupted_restart_and_cold_cli(
    handoff, tmp_path, monkeypatch
):
    service, store, app = handoff
    old = ready_task(service, app)
    primary = answer_store.Store(
        tmp_path / "primary-information", legacy_profile=tmp_path / "no-import"
    )
    primary.initialize()
    primary.put_answer(
        {
            "question": "Email",
            "value": "current@example.invalid",
            "scope": {},
            "state": "confirmed",
            "source": "Current confirmed contact",
        }
    )
    selected = CodexHandoffService(store, service.root, information_library_root=primary.root)
    release = handoff_module.release_execution

    def release_then_fail(*args):
        release(*args)
        raise OSError("Released old owner before successor creation")

    monkeypatch.setattr(handoff_module, "release_execution", release_then_fail)
    with pytest.raises(OSError):
        prepared_again(selected, old)
    monkeypatch.setattr(handoff_module, "release_execution", release)
    reopened = CodexHandoffService(store, service.root)
    current = prepared_again(reopened, old)["active_task"]
    assert current["information_library_root"] == str(primary.root)
    assert current["answers"][0]["value"] == "current@example.invalid"


def test_unavailable_declared_information_never_falls_back_to_legacy(handoff, tmp_path):
    service, store, app = handoff
    old = ready_task(service, app)
    missing = tmp_path / "missing-information"
    selected = CodexHandoffService(store, service.root, information_library_root=missing)
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        prepared_again(selected, old)
    assert error.value.code == "information_library_unavailable"
    assert service.path.read_bytes() == before and not missing.exists()


def test_restart_payload_cannot_select_an_arbitrary_information_directory(handoff, tmp_path):
    service, _, app = handoff
    old = ready_task(service, app)
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.request(
            "restart",
            {
                "task_id": old["id"],
                "task_revision": old["revision"],
                "request_id": "new-page",
                "information_library_root": str(tmp_path / "untrusted"),
            },
        )
    assert error.value.code == "invalid_handoff"
    assert service.path.read_bytes() == before


def test_old_restart_request_cannot_redirect_to_a_later_active_attempt(handoff):
    service, _, app = handoff
    first = ready_task(service, app)
    second = prepared_again(service, first, "first-restart")["active_task"]
    claimed = act(service, second, "claim", owner="second-codex-chat")
    second = ready(service, claimed["active_task"], claimed["claim_token"])
    third = prepared_again(service, second, "second-restart")["active_task"]
    before = service.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        prepared_again(service, first, "first-restart")
    assert error.value.code == "handoff_restart_superseded"
    assert service.path.read_bytes() == before
    assert service.snapshot()["active_task"]["id"] == third["id"]


def test_restart_cli_accepts_the_same_private_request_idempotently(handoff, tmp_path):
    service, store, app = handoff
    old = ready_task(service, app)
    request = tmp_path / "restart.json"
    request.write_text(
        json.dumps(
            {
                "task_id": old["id"],
                "task_revision": old["revision"],
                "request_id": "private-cli-request",
            }
        )
    )
    command = [
        sys.executable,
        str(Path(__file__).parents[1] / "scripts/run_codex_handoff.py"),
        "--applications",
        str(store.root),
        "--root",
        str(service.root),
        "restart",
        "--request",
        str(request),
    ]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    current = json.loads(first.stdout)["active_task"]
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["active_task"]["id"] == current["id"]
    assert current["status"] == "prepared" and current["readbacks"] == []


def test_reading_existing_attempt_does_not_recreate_missing_execution_directory(handoff):
    service, store, app = handoff
    old = ready_task(service, app)
    current = prepared_again(service, old)["active_task"]
    shutil.rmtree(store.root / ".execution")
    before = {
        str(path.relative_to(store.root)): path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(PortalDataError) as error:
        service.existing_attempt(current["id"])
    assert error.value.code == "execution_missing"
    assert not (store.root / ".execution").exists()
    assert {
        str(path.relative_to(store.root)): path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file()
    } == before


def test_restart_retry_does_not_borrow_an_independently_prepared_same_pdf(handoff, monkeypatch):
    service, store, app = handoff
    old = ready_task(service, app)
    save = service._save
    count = 0

    def lose_second_save_response(state):
        nonlocal count
        count += 1
        save(state)
        if count == 2:
            raise OSError("Released old owner state persisted; stop before new prepare")

    monkeypatch.setattr(service, "_save", lose_second_save_response)
    with pytest.raises(OSError):
        prepared_again(service, old)
    reopened = CodexHandoffService(store, service.root)
    independent = prepare(reopened, app)
    assert not independent.get("reuse_context")
    before = reopened.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        prepared_again(reopened, old)
    assert error.value.code == "handoff_active"
    assert reopened.path.read_bytes() == before
    assert reopened.snapshot()["active_task"]["id"] == independent["id"]


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_existing_attempt_rejects_owner_symlinks_without_repair(handoff, tmp_path, kind):
    service, store, app = handoff
    old = ready_task(service, app)
    current = prepared_again(service, old)["active_task"]
    directory = store.root / ".execution"
    ownership = directory / (hashlib.sha256(app["id"].encode()).hexdigest() + ".json")
    if kind == "file":
        relocated = tmp_path / "old-owner.json"
        ownership.rename(relocated)
        ownership.symlink_to(relocated)
    else:
        relocated = tmp_path / "old-execution"
        directory.rename(relocated)
        directory.symlink_to(relocated, target_is_directory=True)
    state_before = service.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.existing_attempt(current["id"])
    assert error.value.code == "execution_invalid"
    assert service.path.read_bytes() == state_before
    assert ownership.is_symlink() if kind == "file" else directory.is_symlink()
