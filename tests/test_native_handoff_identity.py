"""A ready JSON file is a locator, never the recipient's authority proof."""

from copy import deepcopy

import pytest

from career_evidence_graph import worker_process_identity as identity
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import verify_native_handoff_recipient


def process(pid, executable):
    return {
        "pid": pid,
        "uid": 501,
        "started_seconds": 1_700_000_000 + pid,
        "started_microseconds": 10,
        "executable": executable,
    }


def test_parent_identity_uses_stable_child_and_kernel_parent_without_changing_saved_shape(
    monkeypatch,
):
    child, parent = process(20, "/native/driver"), process(10, "/native/codex")
    monkeypatch.setattr(
        identity,
        "_process_information",
        lambda pid: (deepcopy(child), 10) if pid == 20 else (deepcopy(parent), 1),
    )
    assert identity.process_identity(20) == child
    assert identity.process_parent_identity(20) == parent
    assert set(identity.process_identity(20)) == set(child)


def test_recipient_proof_uses_kernel_generation_executable_and_direct_parent(monkeypatch):
    import career_evidence_graph.cua_driver as module

    child, parent = process(20, "/native/driver"), process(10, "/native/codex")
    monkeypatch.setattr(
        module, "process_identity", lambda pid: deepcopy(child) if pid == 20 else deepcopy(parent)
    )
    monkeypatch.setattr(module, "process_parent_identity", lambda pid: deepcopy(parent))
    ready = {
        "protocol": "cua-trusted-handoff/v1",
        "request_id": "request-one",
        "socket_path": "/private/driver.sock",
        "application_ref_digest": "a" * 64,
        "status": "pending",
        "connection_id": "connection-one",
        "peer_pid": 20,
        "proxy_pid": 20,
    }
    result = verify_native_handoff_recipient(
        ready,
        expected_request_id="request-one",
        expected_socket="/private/driver.sock",
        application_ref_digest="a" * 64,
        appserver_identity=parent,
        driver_executable="/native/driver",
    )
    assert result == child


@pytest.mark.parametrize(
    "change",
    [
        "not_child",
        "wrong_binary",
        "reused_parent",
        "reused_child",
        "mixed_proxy",
        "wrong_request",
        "wrong_socket",
    ],
)
def test_ready_file_never_substitutes_for_proven_recipient(monkeypatch, change):
    import career_evidence_graph.cua_driver as module

    child, parent = process(20, "/native/driver"), process(10, "/native/codex")
    actual_parent = deepcopy(parent)
    if change == "not_child":
        actual_parent = process(11, "/native/codex")
    elif change == "wrong_binary":
        child["executable"] = "/other/native/driver"
    elif change == "reused_parent":
        actual_parent["started_microseconds"] += 1
    reads = []

    def read(pid):
        if pid != 20:
            return deepcopy(parent)
        reads.append(True)
        value = deepcopy(child)
        if change == "reused_child" and len(reads) > 1:
            value["started_microseconds"] += 1
        return value

    monkeypatch.setattr(module, "process_identity", read)
    monkeypatch.setattr(module, "process_parent_identity", lambda pid: deepcopy(actual_parent))
    ready = {
        "protocol": "cua-trusted-handoff/v1",
        "request_id": "request-one",
        "socket_path": "/private/driver.sock",
        "application_ref_digest": "a" * 64,
        "status": "pending",
        "connection_id": "connection-one",
        "peer_pid": 20,
        "proxy_pid": 20,
    }
    if change == "mixed_proxy":
        ready["proxy_pid"] = 21
    elif change == "wrong_request":
        ready["request_id"] = "old-request"
    elif change == "wrong_socket":
        ready["socket_path"] = "/other/driver.sock"
    with pytest.raises(PortalDataError) as error:
        verify_native_handoff_recipient(
            ready,
            expected_request_id="request-one",
            expected_socket="/private/driver.sock",
            application_ref_digest="a" * 64,
            appserver_identity=parent,
            driver_executable="/native/driver",
        )
    assert error.value.code == "cua_recipient_unverified"
