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
# r7: a combobox expand click names the value the driver showed (a placeholder here).
EXPAND = dict(CLICK, call_id="expand-1", sequence=4, expected_target={"value": "Please select"})
# r7: a pre-ledger refusal is a not_sent row with its code, never a mutation.
REFUSED = {
    key: value for key, value in CLICK.items() if key not in {"status", "mutation", "call_id"}
} | {
    "call_id": "refused-1",
    "sequence": 5,
    "status": "not_sent",
    "mutation": False,
    "refusal": "handoff_existing_content",
}
REFUSED_BARE = {
    key: value for key, value in REFUSED.items() if key not in {"native_ref", "field_hint"}
} | {"call_id": "refused-2", "sequence": 6, "refusal": "handoff_arguments_invalid"}
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
        changed(calls=[dict(OPTION, expected_target={"value": "Mr."})]),
        changed(calls=[dict(SET_VALUE, expected_target={"value": ""})]),
        changed(calls=[dict(EXPAND, expected_target={"value": "a\nb"})]),
        changed(calls=[dict(EXPAND, expected_target={"value": "x" * 20_001})]),
        changed(calls=[dict(EXPAND, expected_target={"value": "x", "id": "y"})]),
        changed(calls=[dict(REFUSED, status="observed")]),
        changed(calls=[dict(REFUSED, refusal="")]),
        changed(calls=[dict(REFUSED, refusal="has space")]),
        changed(calls=[dict(REFUSED, result={"ok": True})]),
        changed(calls=[dict(REFUSED, tool="browser_navigate")]),
    ],
)
def test_one_rule_rejects_every_drifted_shape(receipt):
    with pytest.raises(ValueError):
        validate_handoff_receipt(receipt)
    with pytest.raises(PortalDataError) as error:
        worker._native_handoff_receipt(receipt)
    assert error.value.code == "native_handoff_receipt_invalid"


DETAIL = {
    "hit": {
        "tag": "div",
        "role": "presentation",
        "id": "overlay",
        "classes": ["a", "b", "c"],
        "interactive_break": True,
    },
    "point": {"x": 120.5, "y": 900},
    "target_rect": {"x": 100, "y": 880, "w": 240, "h": 40},
    "viewport": {"w": 1280, "h": 720, "scroll_x": 0, "scroll_y": 12.5},
    "in_viewport": False,
    "scrolled": True,
}


def test_r10_refusal_detail_rides_only_a_refused_row():
    hit = dict(EXPAND, call_id="hit-1", status="not_sent", refusal="target_hit_mismatch")
    valid = changed(
        calls=[
            dict(hit, refusal_detail=DETAIL),
            # r10: nothing at the point (e.g. outside the viewport) reports hit null.
            dict(hit, call_id="hit-2", sequence=12, refusal_detail=dict(DETAIL, hit=None)),
            dict(REFUSED, refusal_detail={"in_viewport": True}),
            dict(
                HIDDEN_UPLOAD,
                status="not_sent",
                refusal="target_hit_mismatch",
                refusal_detail={"point": {"x": 1, "y": 2}},
            ),
        ]
    )
    assert validate_handoff_receipt(valid) == valid
    assert worker._native_handoff_receipt(valid) == valid
    for detail in (
        # Every string within its limit, the whole diagnosis over 1 KB.
        dict(
            DETAIL,
            hit=dict(DETAIL["hit"], tag="t" * 200, role="r" * 200, id="i" * 200)
            | {"classes": ["c" * 200] * 3},
        ),
        dict(DETAIL, hit=dict(DETAIL["hit"], id="x" * 201)),
        dict(DETAIL, unknown=True),
        dict(DETAIL, hit=dict(DETAIL["hit"], unknown="x")),
        dict(DETAIL, point={"x": "1", "y": 2}),
        dict(DETAIL, point={"x": float("nan"), "y": 2}),
        dict(DETAIL, in_viewport=1),
        dict(DETAIL, hit=dict(DETAIL["hit"], classes=["a", "b", "c", "d"])),
        dict(DETAIL, hit=dict(DETAIL["hit"], tag="a\nb")),
        dict(DETAIL, hit=[]),
        dict(DETAIL, hit="none"),
        [],
    ):
        with pytest.raises(ValueError):
            validate_handoff_receipt(changed(calls=[dict(hit, refusal_detail=detail)]))
    # Only a refused row carries the diagnosis.
    with pytest.raises(ValueError):
        validate_handoff_receipt(changed(calls=[dict(CLICK, refusal_detail=DETAIL)]))
    with pytest.raises(ValueError):
        validate_handoff_receipt(
            changed(calls=[dict(HIDDEN_UPLOAD, status="not_sent", refusal_detail=DETAIL)])
        )


RESOLUTION = {
    "protocol": "fixed-material/v1",
    "resolution_id": "f" * 32,
    "material_ref": "c" * 64,
    "kind": "file",
    "sha256": "e" * 64,
    "size_bytes": 10,
    "filename": "cv.pdf",
    "mime_type": "application/pdf",
}
FILE_LIST = {
    "kind": "file_list",
    "sha256": "e" * 64,
    "size_bytes": 10,
    "filename": "cv.pdf",
    "file_count": 1,
}
DELIVERED = dict(
    HIDDEN_UPLOAD,
    call_id="upload-observed",
    status="observed",
    material_resolution=RESOLUTION,
    material_readback=FILE_LIST,
)
READBACK = {
    "file_count": 0,
    "input_connected": True,
    "input_replaced": False,
    "filename_shown": False,
    "value_cleared": True,
}


def test_r11_readback_proves_a_file_by_its_list_or_its_shown_name():
    shown = dict(FILE_LIST, proof="filename_shown", file_count=0)
    for readback in (
        FILE_LIST,
        dict(FILE_LIST, proof="file_list"),
        shown,
        dict(shown, file_count=1),
    ):
        valid = changed(calls=[dict(DELIVERED, material_readback=readback)])
        assert validate_handoff_receipt(valid) == valid
    for readback in (
        # Without the shown-name proof a FileList must hold the one delivered file.
        dict(FILE_LIST, file_count=0),
        dict(FILE_LIST, proof="file_list", file_count=0),
        dict(shown, proof="dom_text"),
        dict(shown, file_count=2),
        dict(shown, filename="other.pdf"),
        dict(shown, sha256="0" * 64),
        dict(shown, size_bytes=-1),
        dict(shown, size_bytes="10"),
        dict(shown, extra=True),
    ):
        with pytest.raises(ValueError):
            validate_handoff_receipt(changed(calls=[dict(DELIVERED, material_readback=readback)]))


def test_r11_refusal_detail_carries_the_unproven_readback():
    unknown = dict(
        {k: v for k, v in DELIVERED.items() if k != "material_readback"},
        status="unknown",
        refusal="handoff_native_effect_unverified",
    )
    for detail in ({"readback": READBACK}, dict(DETAIL, readback=dict(READBACK, file_count=3))):
        valid = changed(calls=[dict(unknown, refusal_detail=detail)])
        assert validate_handoff_receipt(valid) == valid
        assert worker._native_handoff_receipt(valid) == valid
    for readback in (
        {k: v for k, v in READBACK.items() if k != "value_cleared"},
        dict(READBACK, extra=True),
        dict(READBACK, file_count=-1),
        dict(READBACK, file_count=True),
        dict(READBACK, file_count=1.0),
        dict(READBACK, input_replaced=0),
        None,
    ):
        with pytest.raises(ValueError):
            validate_handoff_receipt(
                changed(calls=[dict(unknown, refusal_detail={"readback": readback})])
            )


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
    r7 = changed(
        calls=[
            CLICK,
            EXPAND,
            REFUSED,
            REFUSED_BARE,
            dict(
                REFUSED_BARE, call_id="r3", tool="browser_deliver_material", material_ref="c" * 64
            ),
        ]
    )
    assert validate_handoff_receipt(r7) == r7
    assert worker._native_handoff_receipt(r7) == r7
    with pytest.raises(PortalDataError):
        worker._native_handoff_receipt(dict(grant, yielded=True))


def test_r8_admitted_rows_the_core_refused_keep_their_keys_and_name_why():
    # r8: after host admission the core's not_sent or unknown reason uses the same key.
    core_refused = dict(
        EXPAND, call_id="core-1", sequence=7, status="not_sent", refusal="target_hit_mismatch"
    )
    unverified = dict(
        SET_VALUE,
        call_id="core-2",
        sequence=8,
        status="unknown",
        refusal="handoff_native_effect_unverified",
    )
    host_denied = dict(
        CLICK,
        call_id="core-3",
        sequence=9,
        status="not_sent",
        refusal="handoff_host_did_not_authorize",
    )
    upload_refused = dict(
        HIDDEN_UPLOAD,
        call_id="core-4",
        sequence=10,
        status="not_sent",
        refusal="handoff_native_refused",
    )
    observed = dict(CLICK, call_id="seen-1", sequence=11, status="observed")
    r8 = changed(
        calls=[core_refused, unverified, host_denied, upload_refused, REFUSED_BARE, observed]
    )
    assert validate_handoff_receipt(r8) == r8
    assert worker._native_handoff_receipt(r8) == r8
    for drifted in (
        dict(core_refused, status="observed"),
        dict(core_refused, status="awaiting_host"),
        dict(unverified, refusal="has space"),
        dict(upload_refused, status="observed"),
        dict(upload_refused, refusal=""),
        dict(core_refused, result={"ok": True}),
    ):
        with pytest.raises(ValueError):
            validate_handoff_receipt(changed(calls=[drifted]))


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
