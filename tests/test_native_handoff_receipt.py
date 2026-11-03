"""The native handoff receipt is checked once, at the driver's handoff port."""

from __future__ import annotations

from copy import deepcopy

import pytest

from career_evidence_graph import application_worker as worker
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import (
    NativeHandoffPort,
    native_handoff_port,
    validate_handoff_receipt,
)

SCOPE = {
    "target_id": "target",
    "tab_id": "tab",
    "expected_document": {"frame_id": "frame", "loader_id": "loader", "url": "https://x.test/"},
}
CLICK = {
    "call_id": "click-1",
    "tool": "browser_click",
    "arguments_digest": "a" * 64,
    "status": "awaiting_host",
    "generation": 1,
    "sequence": 1,
    "mutation": True,
    "semantic_verified": False,
    "scope": SCOPE,
    "native_ref": "ref-1",
    "field_hint": {"role": "combobox", "name": "Country"},
}
READ = {
    key: value
    for key, value in CLICK.items()
    if key not in {"native_ref", "field_hint"} | {"call_id", "tool", "mutation"}
} | {"call_id": "read-1", "tool": "get_browser_state", "mutation": False}
SET_VALUE = dict(
    CLICK,
    call_id="set-1",
    tool="browser_set_value",
    field_hint={"role": "checkbox", "name": "I agree"},
    text_sha256="b" * 64,
)
# r6: an option click names only its option; the owning combobox is the previous row.
OPTION = dict(CLICK, call_id="option-1", sequence=2, field_hint={"role": "option", "name": "Mr."})
# r6: a hidden file input is listed as an upload-only ref (AX role button, css_hidden).
HIDDEN_UPLOAD = dict(
    {k: v for k, v in CLICK.items() if k != "field_hint"},
    call_id="upload-1",
    tool="browser_deliver_material",
    sequence=3,
    native_ref="ref-file",
    field_hint={"role": "button", "name": "file"},
    material_ref="c" * 64,
    target_descriptor={
        "tag": "input",
        "type": "file",
        "id": "",
        "name": "",
        "worker_field": "",
        "label": "",
        "accept": ".pdf",
        "draft_path": "",
        "required": False,
        "disabled": False,
        "readonly": False,
        "value_empty": True,
        "multiple": False,
        "frame": "main",
        "max_length": None,
        "file_count": 0,
    },
)
STATUS = {
    "handoff_id": "handoff",
    "generation": 1,
    "phase": "active",
    "revoked": False,
    "active_calls": 0,
    "local_tools_drained": True,
    "return_ready": False,
    "calls": [CLICK, READ],
}


def changed(**changes):
    value = deepcopy(STATUS)
    value.update(changes)
    return value


@pytest.mark.parametrize(
    "receipt",
    [
        changed(generation=2**64),
        changed(extra=True),
        changed(host_return_credential="secret"),
        changed(active_calls=1),
        changed(return_ready=True, active_calls=1, local_tools_drained=False),
        changed(calls=[CLICK, CLICK]),
        changed(calls=[dict(CLICK, mutation=False)]),
        changed(calls=[dict(READ, mutation=True)]),
        changed(calls=[dict(READ, native_ref="ref")]),
        changed(calls=[dict(CLICK, text_sha256="b" * 64)]),
        changed(calls=[dict(CLICK, scope={"target_id": "target"})]),
        changed(calls=[{k: v for k, v in SET_VALUE.items() if k != "text_sha256"}]),
        changed(calls=[{k: v for k, v in SET_VALUE.items() if k != "field_hint"}]),
        changed(calls=[dict(SET_VALUE, mutation=False)]),
        changed(calls=[dict(SET_VALUE, text_sha256="B" * 64)]),
        changed(calls=[dict(SET_VALUE, material_ref="c" * 64)]),
        changed(phase="not an identifier"),
    ],
)
def test_one_rule_rejects_every_drifted_shape(receipt):
    with pytest.raises(ValueError):
        validate_handoff_receipt(receipt)
    with pytest.raises(PortalDataError) as error:
        worker._native_handoff_receipt(receipt)
    assert error.value.code == "native_handoff_receipt_invalid"


def test_grant_and_status_are_the_two_receipt_forms():
    grant = {"handoff_id": "handoff", "generation": 1, "local_tools_drained": True}
    assert validate_handoff_receipt(grant, grant=True) == grant
    assert validate_handoff_receipt(dict(grant, yielded=True), grant=True)["yielded"] is True
    assert validate_handoff_receipt(STATUS) == STATUS
    with_set_value = changed(calls=[CLICK, READ, SET_VALUE])
    assert validate_handoff_receipt(with_set_value) == with_set_value
    r6 = changed(calls=[CLICK, OPTION, HIDDEN_UPLOAD])
    assert validate_handoff_receipt(r6) == r6
    assert worker._native_handoff_receipt(r6) == r6
    assert worker._native_handoff_receipt(grant) == grant
    with pytest.raises(PortalDataError):
        worker._native_handoff_receipt(dict(grant, yielded=True))


class Client:
    native_session = True
    driver_sha256 = "d" * 64
    driver_executable = "/driver"
    socket_path = "/socket"
    timeout = 15
    handoff_transition_inflight = False
    control_inflight = False

    def __init__(self, status):
        self.status = status

    def handoff_status(self, **options):
        return self.status

    revoke_handoff = handoff_status

    def admit_call(self, *args, **options):
        return self.status

    def yield_to(self, ready, **options):
        return {"handoff_id": "handoff", "generation": 1, "local_tools_drained": True}


def test_the_port_is_the_seam_and_reports_one_unknown_code():
    port = NativeHandoffPort(Client(STATUS))
    assert port.handoff_status() == STATUS
    assert port.admit_call("click-1", "a" * 64, "allow") == STATUS
    for receipt in [changed(generation=-1), {"handoff_id": "handoff"}]:
        port = NativeHandoffPort(Client(receipt))
        for read in (port.handoff_status, port.revoke_handoff):
            with pytest.raises(PortalDataError) as error:
                read()
            assert error.value.code == "cua_handoff_unknown"
    # A yield receipt without the driver's own yielded answer is not a grant.
    with pytest.raises(PortalDataError):
        NativeHandoffPort(Client(STATUS)).yield_to({})


def test_the_port_answers_control_busy_and_never_exposes_the_session():
    client = Client(STATUS)
    port = native_handoff_port(client)
    assert not port.control_busy
    client.control_inflight = True
    assert port.control_busy
    assert port.action_timeout == 15
    assert not hasattr(port, "call") and not hasattr(port, "resume_after_handoff")
    assert native_handoff_port(object()) is None
    with pytest.raises(ValueError):
        NativeHandoffPort(object())
