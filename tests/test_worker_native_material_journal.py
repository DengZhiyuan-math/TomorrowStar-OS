"""Native material calls reserve the original ordinary intent before dispatch."""

import json
import time
from copy import deepcopy
from uuid import uuid4

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_bound_material_delivery import bound_material_page as bound_material_page
from test_worker_bound_material_delivery import field, file_export
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_assistance import prepare_journal

from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def material_call(bound_material_page, request):
    service, _, issue = bound_material_page
    kind = getattr(request, "param", "text")
    if kind == "file":
        service.store.cover_letter_exporter = file_export
    question = field(kind="file" if kind == "file" else "textarea", draft_path="questions.letter")
    ref, context = issue([question])
    entry = next(
        row
        for row in service.store.assistance_delivery(ref, page_context=context)["materials"]
        if row["kind"] == "cover_letter"
    )
    resolved = service.store.resolve_bound_material(
        ref, entry["material_ref"], question=question, page_context=context
    )
    scope = prepare_journal(service, ref)
    grant = {"handoff_id": "native-handoff", "generation": 1, "local_tools_drained": True}
    service.store.record_native_handoff(
        ref, request_id="journal-run", phase="granted", scope=scope, receipt=grant
    )
    call = {
        "call_id": "fixed-text-call",
        "tool": "browser_deliver_material",
        "arguments_digest": "a" * 64,
        "status": "awaiting_host",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "native_ref": "nativep1:0",
        "field_hint": {"role": "textbox", "name": "Cover letter"},
        "scope": {
            "target_id": scope["native_scope"]["target_id"],
            "tab_id": scope["native_scope"]["tab_id"],
            "expected_document": scope["document"],
        },
        "material_ref": entry["material_ref"],
        "target_descriptor": context["data"]["fields"][0]["material_target"],
    }
    manifest = {
        "protocol": "fixed-material/v1",
        "resolution_id": uuid4().hex,
        "material_ref": entry["material_ref"],
        "kind": kind,
        "sha256": resolved["sha256"],
        "size_bytes": len(resolved["text"].encode() if kind == "text" else resolved["bytes"]),
    }
    if kind == "file":
        manifest.update(filename=resolved["filename"], mime_type="application/pdf")
    job = service.store.load()["jobs"][0]
    intent = {
        "action": "fill" if kind == "text" else "upload",
        "field_id": question["id"],
        "draft_path": question["draft_path"],
        "material_id": resolved["material_id"],
        "sha256": resolved["sha256"],
        "form_protocol": "form-state/v1",
        "form_binding": deepcopy(job["form_state"]["binding"]),
        "attempt_id": uuid4().hex,
        "run_id": ref["binding"]["run_id"],
        "page_id": ref["binding"]["page_id"],
        "prepared_at": time.time(),
        "input_refs": {"revision": job["revision"], "file_sha256": job["file_sha256"]},
        "native_material": {
            "protocol": "fixed-material/v1",
            "request_id": "journal-run",
            "handoff_id": "native-handoff",
            "call_id": call["call_id"],
            "arguments_digest": call["arguments_digest"],
            "generation": 1,
            "sequence": 1,
            "assistance_ref_digest": digest(ref),
            "resolution": manifest,
        },
    }
    intent.update(
        {"expected_value": resolved["text"]}
        if kind == "text"
        else {"filename": resolved["filename"]}
    )
    receipt = {
        **grant,
        "phase": "active",
        "revoked": False,
        "active_calls": 0,
        "return_ready": False,
        "calls": [call],
    }
    return service, ref, scope, receipt, intent


def save_material(material_call):
    service, ref, scope, receipt, intent = material_call
    return service.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="granted",
        scope=scope,
        receipt=receipt,
        material_intent=intent,
    )


def test_material_intent_and_awaiting_call_are_one_durable_checkpoint(material_call):
    service, ref, _, receipt, intent = material_call
    before = service.store.load()["jobs"][0]
    assert before["intent"] is None
    assert not before["native_handoff_runs"][0]["events"][-1]["receipt"].get("calls")
    row = save_material(material_call)
    state = service.store.load()
    job = state["jobs"][0]
    assert job["intent"] == intent
    assert row["events"][-1]["receipt"] == receipt
    assert "material_resolution" not in row["events"][-1]["receipt"]["calls"][0]
    assert intent["expected_value"] not in json.dumps(row)
    assert "bytes_base64" not in json.dumps(row)
    assert (
        service.store.native_material_intent(
            state, job, ref, request_id="journal-run", call=receipt["calls"][0]
        )
        == intent
    )


def test_failed_atomic_checkpoint_does_not_publish_intent_or_admission(material_call, monkeypatch):
    service, _, _, _, _ = material_call
    before = service.store.path.read_bytes()

    def disk_full(state):
        raise OSError("synthetic checkpoint failure")

    monkeypatch.setattr(service.store, "save", disk_full)
    with pytest.raises(OSError):
        save_material(material_call)
    assert service.store.path.read_bytes() == before


def test_already_journaled_awaiting_call_still_saves_ordinary_intent(material_call):
    service, ref, scope, receipt, intent = material_call
    service.store.record_native_handoff(
        ref, request_id="journal-run", phase="granted", scope=scope, receipt=receipt
    )
    assert service.store.load()["jobs"][0]["intent"] is None
    save_material(material_call)
    assert service.store.load()["jobs"][0]["intent"] == intent


def sealed_receipt(material_call, status="in_flight"):
    _, _, _, receipt, intent = material_call
    result = deepcopy(receipt)
    call = result["calls"][0]
    call["status"] = status
    call["material_resolution"] = deepcopy(intent["native_material"]["resolution"])
    if status == "observed":
        file = intent["action"] == "upload"
        call["material_readback"] = {
            "kind": "file_list" if file else "value",
            "sha256": intent["sha256"],
            "size_bytes": intent["native_material"]["resolution"]["size_bytes"],
        }
        if file:
            call["material_readback"].update(filename=intent["filename"], file_count=1)
    return result


def test_exact_native_seal_readback_and_stop_preserve_original_pending_intent(material_call):
    service, ref, scope, _, intent = material_call
    save_material(material_call)
    for status in ("in_flight", "observed"):
        receipt = sealed_receipt(material_call, status)
        row = service.store.record_native_handoff(
            ref, request_id="journal-run", phase="granted", scope=scope, receipt=receipt
        )
        assert row["phase"] == "granted"
        state = service.store.load()
        assert (
            service.store.native_material_intent(
                state, state["jobs"][0], ref, call=receipt["calls"][0]
            )
            == intent
        )
    receipt.update(revoked=True, active_calls=0, local_tools_drained=True, return_ready=True)
    row = service.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopped", scope=scope, receipt=receipt
    )
    assert row["phase"] == "stopped" and not row["semantic_unknown"]
    assert service.store.load()["jobs"][0]["intent"] == intent


@pytest.mark.parametrize("change", ["seal", "material", "target"])
def test_pending_material_intent_never_accepts_another_native_action(material_call, change):
    service, ref, scope, _, _ = material_call
    save_material(material_call)
    receipt = sealed_receipt(material_call)
    call = receipt["calls"][0]
    if change == "seal":
        call["material_resolution"]["resolution_id"] = uuid4().hex
    elif change == "material":
        call["material_ref"] = "e" * 64
        call["material_resolution"]["material_ref"] = "e" * 64
    elif change == "target":
        call["target_descriptor"]["worker_field"] = "another-control"
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.store.record_native_handoff(
            ref, request_id="journal-run", phase="granted", scope=scope, receipt=receipt
        )
    assert service.store.path.read_bytes() == before


def test_next_awaiting_call_is_recorded_but_cannot_admit_over_pending_intent(material_call):
    service, ref, scope, receipt, intent = material_call
    save_material(material_call)
    observed = sealed_receipt(material_call, "observed")
    new_call = deepcopy(receipt["calls"][0])
    new_call.update(call_id="next-awaiting-call", sequence=2)
    observed["calls"].append(new_call)
    row = service.store.record_native_handoff(
        ref, request_id="journal-run", phase="granted", scope=scope, receipt=observed
    )
    assert row["phase"] == "granted" and not row["semantic_unknown"]
    state = service.store.load()
    assert state["jobs"][0]["intent"] == intent
    assert (
        service.store.native_material_intent(state, state["jobs"][0], ref, call=new_call) is False
    )
    second = deepcopy(intent)
    second["attempt_id"] = uuid4().hex
    second["native_material"].update(call_id="next-awaiting-call", sequence=2)
    second["native_material"]["resolution"]["resolution_id"] = uuid4().hex
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="granted",
            scope=scope,
            receipt=observed,
            material_intent=second,
        )
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("status", ["awaiting_host", "observed"])
def test_unknown_material_call_cannot_be_rewound_or_washed_clean(material_call, status):
    service, ref, scope, _, intent = material_call
    save_material(material_call)
    unknown = sealed_receipt(material_call, "unknown")
    service.store.record_native_handoff(
        ref, request_id="journal-run", phase="granted", scope=scope, receipt=unknown
    )
    before = service.store.path.read_bytes()
    later = sealed_receipt(material_call, status)
    with pytest.raises(PortalDataError):
        service.store.record_native_handoff(
            ref, request_id="journal-run", phase="stopping", scope=scope, receipt=later
        )
    assert service.store.path.read_bytes() == before
    unknown.update(revoked=True, active_calls=0, local_tools_drained=True, return_ready=True)
    row = service.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopped", scope=scope, receipt=unknown
    )
    assert row["semantic_unknown"] is True
    assert service.store.load()["jobs"][0]["intent"] == intent


@pytest.mark.parametrize("change", ["job", "binding", "call", "seal"])
def test_readonly_matcher_requires_original_job_binding_and_call(material_call, change):
    service, ref, _, receipt, _ = material_call
    save_material(material_call)
    state = service.store.load()
    job = state["jobs"][0]
    call = deepcopy(receipt["calls"][0])
    if change == "job":
        job = deepcopy(job)
        job["application_id"] = "f" * 32
    elif change == "binding":
        state["jobs"][0]["file_sha256"] = "c" * 64
    elif change == "call":
        call["call_id"] = "another-call"
    else:
        call["material_resolution"] = deepcopy(job["intent"]["native_material"]["resolution"])
        call["material_resolution"]["resolution_id"] = uuid4().hex
    before = service.store.path.read_bytes()
    assert service.store.native_material_intent(state, job, ref, call=call) is False
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("status", ["in_flight", "observed"])
def test_sealed_native_result_without_prepared_intent_is_rejected(material_call, status):
    service, ref, scope, _, _ = material_call
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as error:
        service.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="granted",
            scope=scope,
            receipt=sealed_receipt(material_call, status),
        )
    assert error.value.code == "native_material_intent_missing"
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "binding",
        "worker_source",
        "other_intent",
        "attempt",
        "body",
        "private_payload",
        "wrong_field",
        "wrong_call",
    ],
)
def test_admission_rejects_stale_or_unbound_ordinary_intents(material_call, change):
    service, _, _, _, intent = material_call
    if change == "binding":
        state = service.store.load()
        state["jobs"][0]["file_sha256"] = "c" * 64
        service.store.save(state)
    elif change in {"worker_source", "other_intent"}:
        state = service.store.load()
        if change == "worker_source":
            state["runtime"]["source"]["sha256"] = "e" * 64
        else:
            state["jobs"][0]["intent"] = {"action": "fill", "field_id": "unrelated-pending"}
        service.store.save(state)
    elif change == "attempt":
        intent["attempt_id"] = "not-a-fixed-attempt"
    elif change == "body":
        intent["expected_value"] = "Changed arbitrary model text."
    elif change == "private_payload":
        intent["native_material"]["resolution"]["text"] = intent["expected_value"]
    elif change == "wrong_field":
        intent["field_id"] = "another-field"
    else:
        intent["native_material"]["call_id"] = "another-call"
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        save_material(material_call)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("material_call", ["file"], indirect=True)
def test_upload_intent_journals_hash_and_manifest_without_private_bytes(material_call):
    service, ref, scope, _, intent = material_call
    row = save_material(material_call)
    assert service.store.load()["jobs"][0]["intent"] == intent
    assert "file_path" not in json.dumps(row)
    assert "bytes_base64" not in json.dumps(row)
    assert "expected_value" not in intent
    observed = sealed_receipt(material_call, "observed")
    service.store.record_native_handoff(
        ref, request_id="journal-run", phase="granted", scope=scope, receipt=observed
    )
    state = service.store.load()
    assert (
        service.store.native_material_intent(
            state, state["jobs"][0], ref, call=observed["calls"][0]
        )
        == intent
    )
