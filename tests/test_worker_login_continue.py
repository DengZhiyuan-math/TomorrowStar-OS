"""Continue a human login on the retained original page, without replaying work."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_worker import job
from test_application_worker import service as service
from test_single_application_worker import single_worker as single_worker

from career_evidence_graph.application_execution import (
    automated_owner,
    release_execution,
    require_execution,
)
from career_evidence_graph.application_worker import start_run
from career_evidence_graph.career_portal_data import PortalDataError


def login_wait(service, preparation=None):
    service.request("prepare", preparation or {"jobs": [job(service)]})
    run_id = start_run(service.store)
    state = service.store.load()
    current = state["jobs"][0]
    current.update(
        status="needs_recheck",
        reason="user_authentication",
        page_open=True,
        page_observation={
            "run_id": run_id,
            "page_id": "retained-login-page",
            "event": "observed",
            "at": state["runtime"]["observed_at"],
        },
        observations=[{"action": "fill", "field": "name", "verified": True}],
        answer_refs=[{"key": "synthetic-name", "revision": "retained", "field_id": "name"}],
    )
    service.store.save(state)
    return deepcopy(state)


def test_one_continue_rechecks_retained_login_page_and_keeps_completed_work(service, monkeypatch):
    before = login_wait(service)
    original = before["jobs"][0]
    pdf = Path(original["file_path"]).read_bytes()
    spawns = []
    monkeypatch.setattr(service, "spawn", lambda: spawns.append(True))

    result = service.request("resume", {"controller": "synthetic-controller"})

    assert result["control"] == "running"
    current = service.store.load()["jobs"][0]
    assert current["status"] == "queued" and current["reason"] == ""
    assert result["commands"] == [
        {"action": "recheck", "id": original["application_id"], "authentication": True}
    ]
    assert current["intent"] is None and current["page_open"] is True
    assert current["page_observation"] == original["page_observation"]
    assert current["answer_refs"] == original["answer_refs"]
    assert current["observations"][0] == original["observations"][0]
    assert current["observations"][-1]["action"] == "inputs_rechecked"
    assert Path(current["file_path"]).read_bytes() == pdf
    assert current["file_sha256"] == original["file_sha256"]
    assert spawns == [True]
    require_execution(
        service.store.applications,
        original["application_id"],
        automated_owner(service.store.root, before["batch_id"], original["application_id"]),
        "automated",
    )
    service.request("resume", {"controller": "synthetic-controller"})
    assert service.store.load()["commands"] == result["commands"]


@pytest.mark.parametrize(
    "change",
    [
        {"reason": "action_result_unknown"},
        {"intent": {"action": "upload", "attempt_id": "unknown-original-attempt"}},
        {"page_open": False},
        {"handed_off": True},
        {"manual_submission": True},
        {"status": "cancelled"},
    ],
)
def test_continue_does_not_reclaim_other_waits_or_unknown_work(service, change):
    before = login_wait(service)
    before["jobs"][0].update(change)
    service.store.save(before)

    service.request("resume", {"controller": "synthetic-controller"})

    after = service.store.load()
    assert after["jobs"][0] == before["jobs"][0]
    assert after["commands"] == []


@pytest.mark.parametrize("change,reason", [("target", "job_changed"), ("file", "file_changed")])
def test_continue_checks_current_target_and_pdf_before_queuing_login_recheck(
    service, change, reason
):
    before = login_wait(service)
    original = before["jobs"][0]
    if change == "target":
        service.store.applications.update_application(
            original["application_id"],
            {
                "url": "https://jobs.lever.co/other/00000000-0000-0000-0000-000000000099",
                "notes": "Retain this human edit",
            },
            original["revision"],
        )
    else:
        Path(original["file_path"]).write_bytes(b"%PDF-1.4 human replacement")

    service.request("resume", {"controller": "synthetic-controller"})

    after = service.store.load()
    current = after["jobs"][0]
    assert current["status"] == "needs_recheck" and current["reason"] == reason
    assert after["commands"] == []
    assert current["page_observation"] == original["page_observation"]
    assert current["answer_refs"] == original["answer_refs"]
    assert current["observations"] == original["observations"]
    if change == "target":
        assert (
            service.store.applications.get_application(original["application_id"])["notes"]
            == "Retain this human edit"
        )
    else:
        assert Path(current["file_path"]).read_bytes() == b"%PDF-1.4 human replacement"


def test_login_continue_cannot_recreate_released_execution_ownership(service):
    before = login_wait(service)
    current = before["jobs"][0]
    owner = automated_owner(service.store.root, before["batch_id"], current["application_id"])
    release_execution(service.store.applications, current["application_id"], owner, "automated")

    service.request("resume", {"controller": "synthetic-controller"})

    after = service.store.load()
    assert after["jobs"][0]["reason"] == "execution_missing"
    assert after["commands"] == []
    with pytest.raises(PortalDataError) as stopped:
        require_execution(service.store.applications, current["application_id"], owner, "automated")
    assert stopped.value.code == "execution_missing"


def test_login_continue_keeps_installed_write_preflight_before_any_mutation(service):
    login_wait(service)
    before = service.store.path.read_bytes()

    @contextmanager
    def unavailable(operation, payload):
        raise PortalDataError("installed_write_preflight_required", "Synthetic missing capability")
        yield

    service.write_preflight = unavailable
    with pytest.raises(PortalDataError) as stopped:
        service.request("resume", {"controller": "synthetic-controller"})
    assert stopped.value.code == "installed_write_preflight_required"
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("binding_changed", [False, True])
def test_single_login_continue_keeps_binding_validation_without_a_freshness_approval(
    single_worker, binding_changed
):
    service, item, checks, launches = single_worker
    before = login_wait(service, {"workflow": "single", "send_confirmed": True, "jobs": [item]})
    before["runtime"]["observed_at"] -= 60
    before["jobs"][0]["page_observation"]["at"] -= 60
    service.store.save(before)
    if binding_changed:

        def stale(*args, **kwargs):
            raise PortalDataError("single_binding_invalid", "Synthetic changed inputs")

        service.store.single_validator = stale

    result = service.request("resume", {"controller": "synthetic-controller"})

    if binding_changed:
        assert result["control"] == "paused"
        assert result["jobs"][0]["reason"] == "single_binding_invalid"
        assert result["commands"] == [] and launches == []
    else:
        assert result["control"] == "running"
        assert result["jobs"][0]["status"] == "queued"
        assert result["commands"][0]["authentication"] is True
        assert launches == [True] and len(checks) >= 2


def test_retained_navigation_attempt_can_be_loaded_without_automatic_replay(service):
    before = login_wait(service)
    intent = {
        "action": "advance",
        "navigation": {
            "control_id": "retained-next-control",
            "from_step": "contact-panel",
            "to_step": "questions-panel",
        },
        "attempt_id": "pending-navigation-attempt",
        "run_id": before["runtime"]["id"],
        "page_id": "retained-login-page",
    }
    before["jobs"][0]["intent"] = intent
    service.store.save(before)

    assert service.store.load()["jobs"][0]["intent"] == intent
    service.request("resume", {"controller": "synthetic-controller"})
    after = service.store.load()
    assert after["jobs"][0] == before["jobs"][0]
    assert after["commands"] == []


@pytest.mark.parametrize(
    "navigation",
    [
        None,
        [],
        {},
        {"control_id": "next", "from_step": "contact"},
        {"control_id": "next", "from_step": "contact", "to_step": "questions", "extra": True},
        {"control_id": "", "from_step": "contact", "to_step": "questions"},
        {"control_id": "next", "from_step": "  ", "to_step": "questions"},
        {"control_id": "next", "from_step": "contact", "to_step": 2},
        {"control_id": "next", "from_step": "contact", "to_step": "contact"},
    ],
)
def test_malformed_navigation_checkpoint_is_rejected(service, navigation):
    before = login_wait(service)
    before["jobs"][0]["intent"] = {"action": "advance", "navigation": navigation}
    service.store.save(before)
    with pytest.raises(ValueError, match="Invalid worker checkpoint"):
        service.store.load()


def test_navigation_descriptor_does_not_enable_unknown_intent_actions(service):
    before = login_wait(service)
    before["jobs"][0]["intent"] = {
        "action": "submit",
        "navigation": {"control_id": "next", "from_step": "contact", "to_step": "questions"},
    }
    service.store.save(before)
    with pytest.raises(ValueError, match="Invalid worker checkpoint"):
        service.store.load()
