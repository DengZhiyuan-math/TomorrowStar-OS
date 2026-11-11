"""Every execution entry consumes verified single qualification, preserving legacy screening."""

import pytest
from test_single_application_worker import single_worker as single_worker

from career_evidence_graph import application_worker
from career_evidence_graph.career_portal_data import PortalDataError


def prepare(service, item):
    return service.request(
        "prepare", {"workflow": "single", "send_confirmed": True, "jobs": [item]}
    )


def action(service, item, operation):
    if operation == "prepare":
        return prepare(service, item)
    if operation == "resume":
        return service.request("resume", {"controller": "synthetic-controller"})
    state = service.store.load()
    state["jobs"][0]["status"] = "ready_for_review" if operation == "review" else "needs_recheck"
    service.store.save(state)
    return service.request(
        operation, {"application_id": item["application_id"], "acknowledge": True}
    )


@pytest.mark.parametrize("operation", ["prepare", "resume", "review", "recheck"])
def test_verified_single_entries_do_not_rescreen_legacy_jd(single_worker, monkeypatch, operation):
    service, item, checks, _ = single_worker
    if operation != "prepare":
        prepare(service, item)
    checks.clear()
    recorded_validator = service.store.single_validator

    def fixed_validator(*args, **kwargs):
        recorded_validator(*args, **kwargs)
        return True  # Recorded adapter result: binding and fixed delivery were validated.

    monkeypatch.setattr(service.store, "single_validator", fixed_validator)

    def forbidden(*args, **kwargs):
        pytest.fail("An execution entry cannot reinterpret a verified P04 qualification")

    monkeypatch.setattr(application_worker, "screen_applications", forbidden)
    result = action(service, item, operation)
    assert checks, "The workflow label cannot bypass the single validator"
    assert result["jobs"][0]["workflow"] == "single"
    if operation == "resume":
        assert result["control"] == "running"
    if operation == "review":
        assert result["jobs"][0]["handed_off"] is True


@pytest.mark.parametrize("operation", ["prepare", "resume", "review", "recheck"])
@pytest.mark.parametrize("code", ["single_binding_invalid", "single_eligibility_required"])
def test_single_validator_rejections_stop_each_entry_before_legacy_fallback(
    single_worker, monkeypatch, operation, code
):
    service, item, _, launches = single_worker
    if operation != "prepare":
        prepare(service, item)

    def rejected(*args, **kwargs):
        raise PortalDataError(code, "Recorded rejection at the existing single validator", 409)

    monkeypatch.setattr(service.store, "single_validator", rejected)
    monkeypatch.setattr(
        application_worker, "screen_applications", lambda *a, **kw: pytest.fail("fallback")
    )
    if operation == "resume":
        result = action(service, item, operation)
        assert result["control"] == "paused"
        assert result["jobs"][0]["reason"] == code
    else:
        with pytest.raises(PortalDataError) as failure:
            action(service, item, operation)
        assert failure.value.code == code
    state = service.store.load()
    assert not state["jobs"] or state["jobs"][0]["handed_off"] is False
    assert launches == []
    if operation == "prepare":
        assert not state["jobs"]
        assert not (service.store.root / "attachments").exists()


@pytest.mark.parametrize("operation", ["prepare", "resume", "review", "recheck"])
def test_legacy_execution_entries_keep_existing_language_screen(
    single_worker, monkeypatch, operation
):
    service, item, _, _ = single_worker
    if operation != "prepare":
        prepare(service, item)
        state = service.store.load()
        state["jobs"][0]["workflow"] = "batch"
        state.pop("current_job_id", None)
        service.store.save(state)
    calls = []

    def legacy(*args, **kwargs):
        calls.append(1)
        raise PortalDataError("legacy_screen_rejection", "Recorded legacy screening", 409)

    monkeypatch.setattr(application_worker, "screen_applications", legacy)
    if operation == "prepare":
        with pytest.raises(PortalDataError) as failure:
            service.request("prepare", {"jobs": [item]})
        assert failure.value.code == "legacy_screen_rejection"
    elif operation == "resume":
        result = action(service, item, operation)
        assert result["jobs"][0]["reason"] == "legacy_screen_rejection"
    else:
        with pytest.raises(PortalDataError) as failure:
            action(service, item, operation)
        assert failure.value.code == "legacy_screen_rejection"
    assert calls == [1]


def test_workflow_label_alone_cannot_authorize_single_prepare(single_worker, monkeypatch):
    service, item, _, _ = single_worker
    service.store.single_validator = None
    monkeypatch.setattr(
        application_worker, "screen_applications", lambda *a, **kw: pytest.fail("fallback")
    )
    with pytest.raises(PortalDataError) as failure:
        prepare(service, item)
    assert failure.value.code == "single_binding_invalid"
    assert service.store.load()["jobs"] == []


@pytest.mark.parametrize("marker", [None, False, "unverified"])
def test_unverified_fixed_marker_keeps_legacy_language_adapter(single_worker, monkeypatch, marker):
    service, item, _, _ = single_worker
    monkeypatch.setattr(service.store, "single_validator", lambda *a, **kw: marker)
    monkeypatch.setattr(
        service.store,
        "check_language_requirement",
        lambda *a, **kw: (_ for _ in ()).throw(
            PortalDataError("language_information_required", "Recorded legacy conflict", 409)
        ),
    )
    with pytest.raises(PortalDataError) as failure:
        prepare(service, item)
    assert failure.value.code == "language_information_required"
    assert service.store.load()["jobs"] == []


@pytest.mark.parametrize("marker", [None, False])
def test_legacy_public_recheck_consumes_marker_before_queuing(single_worker, monkeypatch, marker):
    service, item, _, launches = single_worker
    prepare(service, item)
    state = service.store.load()
    state["jobs"][0]["status"] = "needs_recheck"
    service.store.save(state)
    before = service.store.path.read_bytes()
    monkeypatch.setattr(service.store, "single_validator", lambda *a, **kw: marker)
    calls = []

    def conflict(*args, **kwargs):
        calls.append(kwargs["country"])
        raise PortalDataError("language_information_required", "Recorded legacy fact conflict", 409)

    monkeypatch.setattr(service.store, "check_language_requirement", conflict)
    with pytest.raises(PortalDataError) as failure:
        service.request("recheck", {"application_id": item["application_id"], "acknowledge": True})
    assert failure.value.code == "language_information_required"
    assert calls == [item["country"]]
    assert service.store.path.read_bytes() == before
    assert launches == []
