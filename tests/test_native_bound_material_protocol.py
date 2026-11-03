"""Fixed native material delivery validates private payloads before one admission."""

import base64
import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy

import pytest
from test_adapter_codex_native import native_case, recorded, start_case
from test_native_cua_session import native_service, ready_record

from career_evidence_graph import cua_driver
from career_evidence_graph._vendor.job_apply_store import StoreError
from career_evidence_graph.career_portal_data import PortalDataError


def text_resolution():
    return {
        "protocol": "fixed-material/v1",
        "resolution_id": "a" * 32,
        "material_ref": "b" * 64,
        "kind": "text",
        "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        "size_bytes": 5,
        "text": "hello",
    }


def test_fixed_text_resolution_checks_exact_whole_body_and_returns_owned_copy():
    payload = text_resolution()
    validated = cua_driver.validate_fixed_material_resolution(payload, material_ref="b" * 64)
    assert validated == payload
    assert validated is not payload


def file_resolution():
    raw = b"%PDF-1.4\nSynthetic fixed material.\n%%EOF\n"
    return {
        "protocol": "fixed-material/v1",
        "resolution_id": "c" * 32,
        "material_ref": "d" * 64,
        "kind": "file",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "bytes_base64": base64.b64encode(raw).decode("ascii"),
        "filename": "cover-letter.pdf",
        "mime_type": "application/pdf",
    }


def test_fixed_pdf_resolution_accepts_one_exact_bounded_private_payload():
    payload = file_resolution()
    assert cua_driver.validate_fixed_material_resolution(payload) == payload


def test_pdf_unicode_basename_matches_native_control_character_rule():
    payload = file_resolution() | {"filename": "résumé\u200d\u00a0.PDF"}
    assert cua_driver.validate_fixed_material_resolution(payload) == payload
    call = material_call() | {"material_ref": payload["material_ref"]}
    call["material_resolution"] = {k: v for k, v in payload.items() if k != "bytes_base64"}
    assert cua_driver.validate_native_material_metadata(call) == call
    with pytest.raises(ValueError):
        cua_driver.validate_fixed_material_resolution(payload | {"filename": "résumé\u0085.pdf"})


def material_target():
    return {
        "tag": "textarea",
        "id": "letter",
        "name": "cover_letter",
        "type": "textarea",
        "label": "Cover letter",
        "frame": "main",
        "worker_field": "letter",
        "draft_path": "",
        "required": False,
        "disabled": False,
        "readonly": False,
        "value_empty": True,
        "accept": "",
        "multiple": False,
        "max_length": None,
        "file_count": 0,
    }


def test_material_target_preserves_zero_limit_and_unprepared_control_identity():
    target = material_target() | {"max_length": 0, "worker_field": ""}
    validated = cua_driver.validate_native_material_target(target)
    assert validated == target
    assert validated is not target


def material_call():
    return {
        "call_id": "material-call",
        "tool": "browser_deliver_material",
        "arguments_digest": "e" * 64,
        "status": "awaiting_host",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "scope": {
            "target_id": "original",
            "tab_id": "tab",
            "expected_document": {
                "frame_id": "frame",
                "loader_id": "loader",
                "url": "https://example.invalid",
            },
        },
        "native_ref": "field-1",
        "field_hint": {"role": "textbox", "name": "Cover letter"},
        "material_ref": "b" * 64,
        "target_descriptor": material_target(),
    }


def test_material_metadata_validates_native_target_before_host_resolution():
    call = material_call()
    assert cua_driver.validate_native_material_metadata(call) == call


@pytest.mark.parametrize("kind", ["text", "file"])
def test_adapter_sends_fixed_material_once_after_intent_save_without_public_payload(
    tmp_path, monkeypatch, kind
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [material_call() | {"scope": scope}]
    private, receipts = [], []
    payload = text_resolution() if kind == "text" else file_resolution()
    native.calls[0]["material_ref"] = payload["material_ref"]

    def resolve(call):
        assert receipts[-1]["calls"] == [call]
        events.append("material-intent-saved")
        return payload

    def admit(call_id, arguments_digest, decision, **kwargs):
        assert events[-1] == "material-intent-saved"
        private.append(deepcopy(kwargs.get("material_resolution")))
        assert decision == "allow"
        manifest = {
            key: value for key, value in payload.items() if key not in {"text", "bytes_base64"}
        }
        readback = {
            "kind": "value" if kind == "text" else "file_list",
            "sha256": payload["sha256"],
            "size_bytes": payload["size_bytes"],
        }
        if kind == "file":
            readback.update(filename=payload["filename"], file_count=1)
        native.calls[0].update(
            status="observed",
            material_resolution=manifest,
            material_readback=readback,
        )
        return native.handoff_status()

    native.admit_call = admit
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=resolve,
        after_yield=lambda receipt: receipts.append(deepcopy(receipt)),
    )
    try:
        assert run.status == "ready"
        assert private == [payload]
        for _ in range(2):
            run = adapter.progress(run.run_id)
        assert private == [payload]
        assert run.native_handoff["calls"][0]["status"] == "observed"
        exposed = json.dumps([receipts, run.native_handoff, recorded(config)])
        assert "hello" not in exposed and "bytes_base64" not in exposed
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"sha256": "0" * 64},
        {"size_bytes": 4},
        {"size_bytes": True},
        {"material_ref": "B" * 64},
        {"resolution_id": "a" * 64},
        {"path": "/private/body"},
        {"text": ""},
        {"text": "\ud800"},
        {"kind": "body"},
    ],
)
def test_private_text_refuses_changed_content_scope_or_extra_authority(changes):
    with pytest.raises(ValueError, match="^Invalid fixed material resolution$"):
        cua_driver.validate_fixed_material_resolution(text_resolution() | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"filename": "../cover.pdf"},
        {"filename": "dir\\cover.pdf"},
        {"filename": ".pdf"},
        {"filename": "cover\n.pdf"},
        {"filename": "cover.txt"},
        {"mime_type": "text/html"},
        {"filename": "x" * 252 + ".pdf"},
        {"bytes_base64": "JVBERi0xLjQK\n"},
        {"bytes_base64": "AB=="},
        {"bytes_base64": ""},
        {"size_bytes": 700001},
        {"sha256": "0" * 64},
        {"text": "private wrong body"},
    ],
)
def test_private_file_refuses_path_substitution_and_noncanonical_or_changed_bytes(changes):
    with pytest.raises(ValueError, match="^Invalid fixed material resolution$"):
        cua_driver.validate_fixed_material_resolution(file_resolution() | changes)


def test_payload_limits_count_exact_decoded_and_utf8_bytes():
    body = "é" * 10000
    text = text_resolution() | {
        "text": body,
        "size_bytes": 20000,
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
    }
    assert cua_driver.validate_fixed_material_resolution(text) == text
    with pytest.raises(ValueError):
        cua_driver.validate_fixed_material_resolution(
            text | {"text": body + "é", "size_bytes": 20002}
        )
    raw = b"%PDF-" + b"x" * 699995
    pdf = file_resolution() | {
        "size_bytes": 700000,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes_base64": base64.b64encode(raw).decode(),
    }
    assert cua_driver.validate_fixed_material_resolution(pdf) == pdf
    with pytest.raises(ValueError):
        cua_driver.validate_fixed_material_resolution(pdf, material_ref="e" * 64)


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "hidden body"},
        {"max_length": True},
        {"max_length": -1},
        {"file_count": True},
        {"file_count": 21},
        {"required": 1},
        {"frame": "child"},
        {"worker_field": "x" * 201},
        {"draft_path": "x" * 1001},
        {"label": "x" * 1001},
    ],
)
def test_material_target_rejects_unknown_or_unbounded_identity(changes):
    with pytest.raises(ValueError):
        cua_driver.validate_native_material_target(material_target() | changes)


@pytest.mark.parametrize(
    "change",
    [
        "raw_body",
        "private_manifest",
        "early_readback",
        "missing_seal",
        "changed_hash",
        "extra_readback",
        "mismatched_ref",
    ],
)
def test_material_metadata_cannot_publish_private_payload_or_unproven_readback(change):
    call = material_call()
    payload = text_resolution()
    manifest = {k: v for k, v in payload.items() if k != "text"}
    readback = {"kind": "value", "sha256": payload["sha256"], "size_bytes": 5}
    call.update(status="observed", material_resolution=manifest, material_readback=readback)
    if change == "raw_body":
        call["text"] = "private body"
    elif change == "private_manifest":
        call["material_resolution"]["text"] = "hello"
    elif change == "early_readback":
        call["status"] = "unknown"
    elif change == "missing_seal":
        call.pop("material_resolution")
    elif change == "changed_hash":
        call["material_readback"]["sha256"] = "f" * 64
    elif change == "extra_readback":
        call["material_readback"]["text"] = "hello"
    else:
        call["material_resolution"]["material_ref"] = "f" * 64
    with pytest.raises(ValueError):
        cua_driver.validate_native_material_metadata(call)


def test_native_control_transport_sends_only_validated_pdf_admission(tmp_path, monkeypatch):
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", "1" * 64)
    monkeypatch.setattr(cua_driver, "verify_native_handoff_recipient", lambda *a, **k: {"pid": 20})
    with native_service(tmp_path) as (path, options, process, requests, state):
        client = cua_driver.NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64)
        call, payload = material_call(), file_resolution()
        call["material_ref"] = payload["material_ref"]
        try:
            client.yield_to(
                ready_record(path),
                request_id="material-lease",
                scope=call["scope"],
                application_ref_digest="a" * 64,
                appserver_identity={},
                driver_executable="/native",
            )
            state["calls"] = [call]
            assert client.handoff_status()["calls"] == [call]
            client.admit_call(
                call["call_id"], call["arguments_digest"], "allow", material_resolution=payload
            )
            sent = [r for r in requests if r["method"] == "trusted_session_handoff_admit"]
            assert len(sent) == 1
            assert sent[0]["args"] == {
                "handoff_id": "handoff-test",
                "call_id": call["call_id"],
                "arguments_digest": call["arguments_digest"],
                "decision": "allow",
                "material_resolution": payload,
            }
            for decision, invalid in (("deny", payload), ("allow", payload | {"sha256": "0" * 64})):
                with pytest.raises(PortalDataError) as rejected:
                    client.admit_call(
                        call["call_id"],
                        call["arguments_digest"],
                        decision,
                        material_resolution=invalid,
                    )
                assert rejected.value.code == "cua_handoff_invalid"
            assert sum(r["method"] == "trusted_session_handoff_admit" for r in requests) == 1
        finally:
            client.close()


@pytest.mark.parametrize("decision", [True, False, None, "raise", "scope", "wrong_ref", "bad_hash"])
def test_material_callback_failure_denies_once_without_sending_any_body(
    tmp_path, monkeypatch, decision
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [material_call() | {"scope": scope}]
    admissions, receipts = [], []

    def resolve(call):
        if decision == "raise":
            raise ValueError("synthetic material validation failed")
        if decision == "scope":
            raise PortalDataError("assistance_binding_changed", "synthetic scope changed", 409)
        if decision == "wrong_ref":
            return text_resolution() | {"material_ref": "c" * 64}
        if decision == "bad_hash":
            return text_resolution() | {"sha256": "c" * 64}
        return decision

    original_admit = native.admit_call

    def admit(call_id, arguments_digest, verdict, **kwargs):
        admissions.append((verdict, deepcopy(kwargs)))
        return original_admit(call_id, arguments_digest, verdict, **kwargs)

    native.admit_call = admit
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=resolve,
        after_yield=lambda receipt: receipts.append(deepcopy(receipt)),
    )
    try:
        assert run.status == "unknown" and native.revoked
        assert not adapter._runs[run.run_id].native["persistence_failed"]
        for _ in range(2):
            adapter.progress(run.run_id)
        assert len(admissions) == 1 and admissions[0][0] == "deny"
        assert "material_resolution" not in admissions[0][1]
        assert not any(row.get("method") == "turn/start" for row in recorded(config))
        assert "hello" not in json.dumps([receipts, run.native_handoff, recorded(config)])
    finally:
        adapter.close()


@pytest.mark.parametrize("code", ["material_destination_unverified", "material_field_changed"])
def test_unproven_material_destination_refuses_only_that_call_and_keeps_the_takeover(
    tmp_path, monkeypatch, capsys, code
):
    # A CV the Worker could not prove on an unparsed page stopped a whole takeover
    # that had already filled nine controls (2026-11-03).
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [material_call() | {"scope": scope}]
    admissions = []

    def resolve(call):
        error = PortalDataError(code, "synthetic destination", 409)
        error.condition = "files!=1"
        raise error

    original_admit = native.admit_call

    def admit(call_id, arguments_digest, verdict, **kwargs):
        admissions.append((verdict, deepcopy(kwargs)))
        return original_admit(call_id, arguments_digest, verdict, **kwargs)

    native.admit_call = admit
    adapter, run = start_case(
        config, ref, scope, packet, driver, native, before_native_call=resolve
    )
    try:
        for _ in range(2):
            adapter.progress(run.run_id)
        assert run.status != "unknown" and not native.revoked
        assert len(admissions) == 1 and admissions[0][0] == "deny"
        assert "material_resolution" not in admissions[0][1]
        log = capsys.readouterr().out
        assert (
            "native_material_admission_denied: "
            + json.dumps({"code": code, "condition": "files!=1"})
        ) in log
        assert "native_call_admission_denied" not in log
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "drift",
    [
        None,
        {"native_ref": "ref-other"},
        {"field_hint": {"role": "button", "name": "Other"}},
        {"material_ref": "e" * 64},
    ],
)
def test_declined_material_row_with_driver_refusal_keeps_its_identity(tmp_path, monkeypatch, drift):
    # 2026-11-03: the host-declined CV came back with r8's refusal (and r10's detail);
    # that outcome is not a changed call, but any admitted key that moves still is.
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [material_call() | {"scope": scope}]

    def resolve(call):
        error = PortalDataError("material_destination_unverified", "synthetic", 409)
        error.condition = "resume_inputs!=1"
        raise error

    original_admit = native.admit_call

    def admit(call_id, arguments_digest, verdict, **kwargs):
        original_admit(call_id, arguments_digest, verdict, **kwargs)
        native.calls[0].update(
            refusal="handoff_host_did_not_authorize",
            refusal_detail={"in_viewport": True},
            **(drift or {}),
        )
        return native.handoff_status()

    native.admit_call = admit
    adapter, run = start_case(
        config, ref, scope, packet, driver, native, before_native_call=resolve
    )
    try:
        for _ in range(2):
            adapter.progress(run.run_id)
        if drift is None:
            assert run.status != "unknown" and not native.revoked
            assert run.error_code != "native_call_identity_changed"
        else:
            assert run.error_code == "native_call_identity_changed"
    finally:
        adapter.close()


def test_unpersisted_material_metadata_stops_before_resolver_and_admission(tmp_path, monkeypatch):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [material_call() | {"scope": scope}]
    resolved, admitted = [], []

    def persist(receipt):
        if receipt.get("calls"):
            raise OSError("synthetic receipt save failure")

    native.admit_call = lambda *args, **kwargs: admitted.append(kwargs)
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        after_yield=persist,
        before_native_call=lambda call: resolved.append(call) or text_resolution(),
    )
    try:
        assert run.status == "unknown" and native.revoked
        assert resolved == admitted == []
        assert not any(row.get("method") == "turn/start" for row in recorded(config))
    finally:
        adapter.close()


@pytest.mark.parametrize("acknowledgement", ["lost", "awaiting_host", "wrong_seal"])
def test_material_admission_tracks_only_its_public_seal_and_never_replays(
    tmp_path, monkeypatch, acknowledgement
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [material_call() | {"scope": scope}]
    admitted, resolved, receipts = [], [], []
    payload = text_resolution()
    manifest = {key: value for key, value in payload.items() if key != "text"}

    def admit(call_id, arguments_digest, decision, **kwargs):
        admitted.append(deepcopy(kwargs["material_resolution"]))
        native.calls[0]["material_resolution"] = deepcopy(manifest)
        if acknowledgement == "lost":
            raise TimeoutError("synthetic admission acknowledgement lost")
        if acknowledgement == "wrong_seal":
            native.calls[0]["material_resolution"]["resolution_id"] = "f" * 32
        return native.handoff_status()

    native.admit_call = admit
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=lambda call: resolved.append(call) or payload,
        after_yield=lambda receipt: receipts.append(deepcopy(receipt)),
    )
    try:
        assert run.status == ("ready" if acknowledgement == "awaiting_host" else "unknown")
        for _ in range(2):
            run = adapter.progress(run.run_id)
        assert admitted == [payload] and len(resolved) == 1
        assert native.revoked is (acknowledgement != "awaiting_host")
        if acknowledgement == "wrong_seal":
            assert not any(
                call.get("material_resolution", {}).get("resolution_id") == "f" * 32
                for receipt in receipts
                for call in receipt.get("calls", [])
            )
        assert "hello" not in json.dumps([receipts, run.native_handoff, recorded(config)])
    finally:
        adapter.close()


@pytest.mark.parametrize("where", ["call", "descriptor", "resolution"])
def test_adapter_rejects_private_metadata_before_filtering_or_host_resolution(
    tmp_path, monkeypatch, where
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    call = material_call() | {"scope": scope}
    if where == "call":
        call["text"] = "private body"
    elif where == "descriptor":
        call["target_descriptor"]["text"] = "private body"
    else:
        call["material_resolution"] = text_resolution()
    native.calls = [call]
    resolved, admitted, receipts = [], [], []
    native.admit_call = lambda *args, **kwargs: admitted.append(kwargs)
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=lambda call: resolved.append(call) or text_resolution(),
        after_yield=lambda receipt: receipts.append(deepcopy(receipt)),
    )
    try:
        assert run.status == "unknown" and native.revoked
        assert resolved == admitted == []
        exposed = json.dumps([receipts, run.native_handoff, recorded(config)])
        assert "hello" not in exposed and "private body" not in exposed
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"file_count": 0},
        {"file_count": True},
        {"filename": "other.pdf"},
        {"sha256": "e" * 64},
        {"size_bytes": True},
        {"bytes_base64": "cHJpdmF0ZQ=="},
    ],
)
def test_observed_file_metadata_requires_exact_one_file_readback(changes):
    payload = file_resolution()
    call = material_call() | {"material_ref": payload["material_ref"], "status": "observed"}
    call["material_resolution"] = {k: v for k, v in payload.items() if k != "bytes_base64"}
    call["material_readback"] = {
        "kind": "file_list",
        "sha256": payload["sha256"],
        "size_bytes": payload["size_bytes"],
        "filename": payload["filename"],
        "file_count": 1,
    } | changes
    with pytest.raises(ValueError):
        cua_driver.validate_native_material_metadata(call)


@pytest.mark.parametrize("trusted", [False, True])
def test_owned_scope_grants_only_the_native_sealed_material_capability(
    tmp_path, monkeypatch, trusted
):
    class ScopeCaptured(Exception):
        pass

    scopes = []

    @contextmanager
    def capture_client(driver, socket, scope, log, env, **kwargs):
        scopes.append(deepcopy(scope))
        raise ScopeCaptured
        yield

    monkeypatch.setattr(cua_driver, "managed_cua_client", capture_client)
    with (
        pytest.raises(ScopeCaptured),
        cua_driver.managed_owned_cua_browser(
            None,
            tmp_path,
            tmp_path / "synthetic-driver",
            {},
            {},
            ["https://example.invalid/form"],
            trusted_session=trusted,
        ),
    ):
        pytest.fail("This boundary test must not create any native or browser process")
    scope = scopes[0]
    assert scope["allow"]["tools"] == [
        "check_permissions",
        "browser_prepare",
        "get_browser_state",
        "browser_click",
        "browser_type",
        *(["browser_set_input_files"] if trusted else []),
        "end_session",
    ]
    assert "browser_deliver_material" not in scope["allow"]["tools"]
    assert scope["resources"] == {
        "browser": {
            "profiles": [{"kind": "isolated_new"}],
            "origins": ["about:blank", "https://example.invalid"],
            **({"fixed_material_uploads": True} if trusted else {}),
        }
    }


def test_native_host_catalog_requires_internal_upload_before_session_begin(tmp_path, monkeypatch):
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", "1" * 64)
    tools = [
        "browser_prepare",
        "get_browser_state",
        "browser_click",
        "browser_type",
        "end_session",
        "check_permissions",
    ]
    with native_service(tmp_path, catalog_change={"tools": [{"name": name} for name in tools]}) as (
        path,
        options,
        process,
        requests,
        state,
    ):
        with pytest.raises(PortalDataError) as error:
            cua_driver.NativeCuaSessionClient(path, process, options, driver_sha256="1" * 64)
        assert error.value.code == "cua_native_session_unavailable"
        assert not any(row["method"] == "trusted_session_begin" for row in requests)


@pytest.mark.parametrize("failure_type", [OSError, StoreError])
def test_material_intent_save_failure_stays_latched_with_the_actual_unsealed_call(
    tmp_path, monkeypatch, failure_type
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    call = material_call() | {"scope": scope}
    native.calls = [call]
    saves, resolutions, admissions = [], [], []

    def resolve(metadata):
        resolutions.append(deepcopy(metadata))
        if len(resolutions) == 1:
            raise failure_type("synthetic one-time material intent save failure")
        return text_resolution()

    native.admit_call = lambda *args, **kwargs: admissions.append((args, kwargs))
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=resolve,
        after_yield=lambda receipt: saves.append(deepcopy(receipt)),
    )
    try:
        assert run.status == "unknown" and run.error_code == "native_receipt_persistence_failed"
        assert native.revoked and run.tools_revoked
        assert admissions == [] and resolutions == [call]
        failed = deepcopy(adapter._runs[run.run_id].native["failed_receipt"])
        assert failed["calls"] == [call]
        assert failed["calls"][0]["status"] == "awaiting_host"
        assert "material_resolution" not in failed["calls"][0]
        saved = deepcopy(saves)
        for current in (
            adapter.progress(run.run_id),
            adapter.stop(run.run_id, request_id="after-intent-save-recovery"),
            adapter.progress(run.run_id),
        ):
            assert current.status == "unknown"
            assert current.error_code == "native_receipt_persistence_failed"
            assert not current.page_write_allowed and not current.model_turn_allowed
            assert current.native_handoff["calls"] == [call]
        assert saves == saved and resolutions == [call] and admissions == []
        assert adapter._runs[run.run_id].native["failed_receipt"] == failed
        assert "hello" not in json.dumps([saves, failed, recorded(config)])
        assert not any(row.get("method") == "turn/start" for row in recorded(config))
    finally:
        adapter.close()


@pytest.mark.parametrize("failure_type", [OSError, StoreError])
def test_late_material_reconciliation_save_failure_keeps_actual_observed_receipt_latched(
    tmp_path, monkeypatch, failure_type
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    native.calls = [material_call() | {"scope": scope}]
    payload = text_resolution()
    saves, admissions, failures = [], [], []
    fail_next_pump = False

    def pump():
        nonlocal fail_next_pump
        if fail_next_pump:
            fail_next_pump = False
            failures.append("save failed")
            raise failure_type("synthetic one-time reconciliation save failure")
        return True

    def admit(*args, **kwargs):
        admissions.append(deepcopy(kwargs["material_resolution"]))
        native.calls[0].update(
            status="observed",
            material_resolution={key: value for key, value in payload.items() if key != "text"},
            material_readback={"kind": "value", "sha256": payload["sha256"], "size_bytes": 5},
        )
        return native.handoff_status()

    native.admit_call = admit
    adapter, run = start_case(
        config,
        ref,
        scope,
        packet,
        driver,
        native,
        before_native_call=lambda call: payload,
        pump=pump,
        after_yield=lambda receipt: saves.append(deepcopy(receipt)),
    )
    try:
        assert run.status == "ready" and admissions == [payload]
        observed = deepcopy(run.native_handoff)
        assert observed["calls"][0]["status"] == "observed"
        fail_next_pump = True
        current = adapter.progress(run.run_id)
        assert current.status == "unknown"
        assert current.error_code == "native_receipt_persistence_failed"
        assert native.revoked and current.tools_revoked
        assert failures == ["save failed"]
        assert adapter._runs[run.run_id].native["failed_receipt"] == observed
        saved = deepcopy(saves)
        for current in (
            adapter.progress(run.run_id),
            adapter.stop(run.run_id, request_id="after-reconciliation-save-recovery"),
            adapter.progress(run.run_id),
        ):
            assert current.status == "unknown"
            assert current.error_code == "native_receipt_persistence_failed"
            assert current.native_handoff["calls"] == observed["calls"]
            assert not current.page_write_allowed and not current.model_turn_allowed
        assert saves == saved and failures == ["save failed"] and admissions == [payload]
        assert adapter._runs[run.run_id].native["failed_receipt"] == observed
        assert "hello" not in json.dumps(
            [saves, current.native_handoff, observed, recorded(config)]
        )
    finally:
        adapter.close()


@pytest.mark.parametrize("failure", ["validation", "scope"])
def test_owner_pump_validation_refusal_does_not_become_a_storage_failure(
    tmp_path, monkeypatch, failure
):
    config, ref, scope, packet, driver, native, events = native_case(tmp_path, monkeypatch)
    fail_next_pump = False

    def pump():
        nonlocal fail_next_pump
        if fail_next_pump:
            fail_next_pump = False
            if failure == "scope":
                raise PortalDataError("assistance_binding_changed", "synthetic scope changed", 409)
            raise ValueError("synthetic ownership validation failed")
        return True

    adapter, run = start_case(config, ref, scope, packet, driver, native, pump=pump)
    try:
        assert run.status == "ready"
        fail_next_pump = True
        current = adapter.progress(run.run_id)
        assert current.status == "unknown" and current.error_code == "event_pump_failed"
        assert native.revoked and current.tools_revoked
        assert not adapter._runs[run.run_id].native["persistence_failed"]
        assert adapter._runs[run.run_id].native["failed_receipt"] is None
    finally:
        adapter.close()
