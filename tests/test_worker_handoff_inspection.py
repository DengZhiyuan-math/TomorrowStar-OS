"""Read-only retained-worker challenge; it never supplies execution authority."""

import fcntl
import os
import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest
from owned_cdp_fake import OwnedCDPFake
from test_worker_stability import retained_live_page as _retained_live_page

from career_evidence_graph import application_worker, application_worker_browser
from career_evidence_graph.application_worker import CONTROLLER_HANDOFF_INSPECTION
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.worker_process_identity import process_identity

retained_live_page = _retained_live_page


@pytest.fixture
def pending_handoff(retained_live_page, monkeypatch, request):
    service, identifier = retained_live_page
    identity = {
        "pid": os.getpid(),
        "uid": os.getuid(),
        "started_seconds": 100,
        "started_microseconds": 123,
        "executable": "/synthetic/python",
    }
    monkeypatch.setattr(application_worker, "process_identity", lambda _: deepcopy(identity))
    monkeypatch.setattr(
        application_worker_browser, "process_identity", lambda _: deepcopy(identity)
    )
    state = service.store.load()
    state["runtime"]["capabilities"].append(CONTROLLER_HANDOFF_INSPECTION)
    service.store.save(state)
    context = SimpleNamespace(
        browser=SimpleNamespace(is_connected=lambda: True, on=lambda *_: None), on=lambda *_: None
    )

    class Page:
        url = state["jobs"][0]["job_url"]

        def is_closed(self):
            return False

        def screenshot(self, **_):
            return b"synthetic screenshot"

    page = Page()
    page.context = context

    class Session:
        def send(self, method, _arguments=None):
            if method == "Page.getFrameTree":
                return {
                    "frameTree": {
                        "frame": {
                            "id": "synthetic-frame",
                            "loaderId": "synthetic-document",
                            "url": page.url,
                        }
                    }
                }
            if method == "Page.createIsolatedWorld":
                return {"executionContextId": 1}
            if method == "Runtime.evaluate":
                return {"result": {"value": {"url": page.url, "fields": []}}}
            raise AssertionError(method)

        def detach(self):
            pass

    context.new_cdp_session = lambda _: Session()
    request.addfinalizer(OwnedCDPFake(page).close)
    runner = ApplicationRunner(service.store, None)
    runner.context = context
    runner.pages[identifier] = page
    runner.page_ids[page] = "synthetic-retained-page"
    descriptor = os.open(service.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    service.store.worker_lock_descriptor = descriptor
    payload = {
        "application_id": identifier,
        "binding": service.snapshot()["jobs"][0]["page_inspection_target"],
    }
    before = service.store.load()
    service.request("inspect-handoff", payload)
    try:
        yield service, runner, payload, before, identity
    finally:
        os.close(descriptor)


def test_original_worker_challenge_preserves_page_attachment_intent_and_answers(pending_handoff):
    service, runner, payload, before, _ = pending_handoff
    state = service.store.load()
    runner.commands(state)
    service.store.save(state)
    result = service.request("verify-handoff", payload)
    receipt = result["runtime"]["controller_handoff"]
    assert receipt["status"] == "captured"
    assert receipt["verification"]["state"] == "validated_capture_receipt"
    assert receipt["verification"]["current_page_verified"] is False
    assert receipt["page_snapshot"]["data"]["url"] == before["jobs"][0]["job_url"]
    assert receipt["page_snapshot"]["document"]["loader_id"] == "synthetic-document"
    assert receipt["verification"]["execution_authority"] is False
    assert result["runtime_status"]["process"] == "unknown" and service.process is None
    after = service.store.load()
    assert after["control"] == "paused" and after["jobs"] == before["jobs"]
    after["runtime"].pop("controller_handoff")
    assert after == before


@pytest.mark.parametrize(
    "change", ["generation", "page", "source", "intent", "nonce", "expired", "worker_lock_lost"]
)
def test_changed_handoff_is_denied_without_consuming_original_work(pending_handoff, change):
    service, runner, payload, before, identity = pending_handoff
    state = service.store.load()
    if change == "generation":
        identity["started_microseconds"] += 1
    elif change == "page":
        runner.page_ids[next(iter(runner.page_ids))] = "synthetic-other-page"
    elif change == "source":
        state["runtime"]["source"]["sha256"] = "a" * 64
    elif change == "intent":
        state["jobs"][0]["intent"]["attempt_id"] = "synthetic-other-intent"
    elif change == "nonce":
        state["commands"][0]["request_id"] = "synthetic-other-request"
    elif change == "worker_lock_lost":
        fcntl.flock(service.store.worker_lock_descriptor, fcntl.LOCK_UN)
    else:
        state["runtime"]["controller_handoff"]["requested_at"] -= 11
    runner.commands(state)
    service.store.save(state)
    preserved = service.store.path.read_bytes()
    with pytest.raises(PortalDataError, match="保持暂停"):
        service.request("verify-handoff", payload)
    assert service.store.path.read_bytes() == preserved and service.process is None
    assert service.store.load()["control"] == "paused"
    assert before["jobs"][0]["intent"] is not None


@pytest.mark.parametrize("change", ["foreign_url", "failed_owner", "owner_process_exited"])
def test_handoff_capture_rejects_changed_url_or_owner_before_receipt(pending_handoff, change):
    service, runner, payload, before, _ = pending_handoff
    if change == "foreign_url":
        runner.pages[
            payload["application_id"]
        ].url = "https://other.example.invalid/foreign-application"
    else:
        runner.cua = SimpleNamespace(
            client=SimpleNamespace(
                failed=change == "failed_owner",
                process=SimpleNamespace(
                    poll=lambda: 1 if change == "owner_process_exited" else None
                ),
            )
        )
    state = service.store.load()
    runner.commands(state)
    service.store.save(state)
    receipt = state["runtime"]["controller_handoff"]
    assert receipt["status"] == "failed" and receipt["reason"]
    assert state["jobs"] == before["jobs"] and state["control"] == "paused"
    with pytest.raises(PortalDataError):
        service.request("verify-handoff", payload)
    assert service.process is None


@pytest.mark.parametrize("change", ["released_lock", "replaced_lock", "attachment", "generation"])
def test_handoff_verification_rechecks_lock_file_and_generation(pending_handoff, change):
    service, runner, payload, _, identity = pending_handoff
    state = service.store.load()
    runner.commands(state)
    service.store.save(state)
    if change == "released_lock":
        fcntl.flock(service.store.worker_lock_descriptor, fcntl.LOCK_UN)
    elif change == "replaced_lock":
        path = service.store.root / ".worker.lock"
        path.unlink()
        path.touch()
    elif change == "attachment":
        from pathlib import Path

        Path(state["jobs"][0]["file_path"]).write_bytes(b"synthetic changed attachment")
    else:
        identity["started_microseconds"] += 1
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.request("verify-handoff", payload)
    assert service.store.path.read_bytes() == before and service.process is None


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin kernel process generation")
def test_kernel_process_identity_has_a_stable_birth_generation():
    first = process_identity(os.getpid())
    assert first and first["pid"] == os.getpid() and first["uid"] == os.getuid()
    assert first["executable"] and first == process_identity(os.getpid())
    assert process_identity(-1) is None


@pytest.mark.parametrize("worker_first", [False, True])
def test_loaded_role_probe_does_not_load_native_libraries(tmp_path, worker_first):
    import json
    import subprocess
    from pathlib import Path

    source = Path(application_worker.__file__).parents[1]
    probe = """
import json, sys
def audit(event, args):
    if event == "ctypes.dlopen":
        raise RuntimeError("Loaded identity import attempted an external action")
sys.addaudithook(audit)
sys.path.insert(0, sys.argv[1])
from career_evidence_graph.loaded_code import measure_packaged_roles
print(json.dumps(measure_packaged_roles(worker_first=sys.argv[2] == "True")))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(source), str(worker_first)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    measured = json.loads(result.stdout)
    assert measured["worker"] and measured["controller"]
