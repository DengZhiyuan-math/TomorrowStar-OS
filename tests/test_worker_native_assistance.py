"""Draft RED cases; not part of active tests while JSON source is frozen."""

from copy import deepcopy

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph import cua_driver
from career_evidence_graph.application_worker import WorkerService, digest

POLICY = {
    "protocol": "cua-trusted-handoff/v1",
    "driver_sha256": "a" * 64,
    "tools": [
        "get_browser_state",
        "browser_click",
        "browser_type",
        "browser_deliver_material",
        "browser_set_value",
    ],
    "type_mode": "insert_text",
}


def native_service(service, monkeypatch):
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", POLICY["driver_sha256"])
    return WorkerService(
        service.store.applications,
        service.store.root,
        live=True,
        cua=True,
        single_flow_root=service.store.single_flow_root,
        single_career_root=service.store.single_career_root,
        single_validator=service.store.single_validator,
        native_assistance_policy=deepcopy(POLICY),
    )


def test_native_policy_applies_only_to_new_trusted_initial_reference(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native = native_service(service, monkeypatch)
    native.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": native.assistance_context(identifier)["binding"],
            "request_id": "new-native-assistance",
        },
    )
    reference = native.assistance_context(identifier)["assistance_ref"]
    assert reference["protocol"] == "codex-assistance/native/v1"
    assert reference["page_writes_enabled"] is True
    assert reference["native_policy_digest"] == digest(POLICY)


def test_trusted_new_config_cannot_upgrade_an_existing_readonly_reference(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    request = {
        "application_id": identifier,
        "binding": service.assistance_context(identifier)["binding"],
        "request_id": "old-request",
    }
    service.request("request-assistance", request)
    old_ref = service.assistance_context(identifier)["assistance_ref"]
    native = native_service(service, monkeypatch)
    native.request("request-assistance", request)
    assert native.assistance_context(identifier)["assistance_ref"] == old_ref
    assert old_ref["page_writes_enabled"] is False


@pytest.mark.parametrize("change", ["no_pin", "wrong_pin", "tools", "extra", "mode", "protocol"])
def test_native_policy_requires_fixed_reviewed_capabilities(
    retained_assistance_page, monkeypatch, change
):
    service, _ = retained_assistance_page
    policy = deepcopy(POLICY)
    monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", POLICY["driver_sha256"])
    if change == "no_pin":
        monkeypatch.setattr(cua_driver, "_NATIVE_HANDOFF_DRIVER_SHA256", None)
    elif change == "wrong_pin":
        policy["driver_sha256"] = "b" * 64
    elif change == "tools":
        policy["tools"].append("browser_prepare")
    elif change == "extra":
        policy["enable_writes"] = True
    elif change == "mode":
        policy["type_mode"] = "replace"
    elif change == "protocol":
        policy["protocol"] = "another-protocol"
    with pytest.raises(ValueError):
        WorkerService(
            service.store.applications,
            service.store.root,
            live=True,
            cua=True,
            native_assistance_policy=policy,
        )


def test_http_arguments_cannot_enable_native_assistance(retained_assistance_page):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "untrusted-flags",
            "native_assistance_policy": POLICY,
            "page_writes_enabled": True,
            "protocol": "codex-assistance/native/v1",
        },
    )
    ref = service.assistance_context(identifier)["assistance_ref"]
    assert ref["page_writes_enabled"] is False
    assert "protocol" not in ref and "native_policy_digest" not in ref


def claim_native(service, identifier, monkeypatch):
    native = native_service(service, monkeypatch)
    native.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": native.assistance_context(identifier)["binding"],
            "request_id": "native-request",
        },
    )
    ref = native.assistance_context(identifier)["assistance_ref"]
    native.request(
        "claim-assistance",
        {
            "application_id": identifier,
            "assistance_ref": ref,
            "request_id": "native-claim",
        },
    )
    return native, ref


def test_native_handoff_delivers_only_saved_answers_for_current_dom_fields(
    retained_assistance_page, monkeypatch
):
    from test_application_information import answer
    from test_worker_assistance_delivery import page_context

    from career_evidence_graph._vendor import job_apply_store as helper

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    helper.atomic_write_json(
        native.store.answers.root / "answers.json",
        {
            "schemaVersion": 1,
            "answers": dict(
                [
                    answer("Email", "  saved@example.invalid  "),
                    answer("French level", "A1"),
                    answer("Unrelated private question", "private unrelated"),
                ]
            ),
            "metadata": {},
        },
    )
    context = page_context(native, ref)
    context["data"]["fields"] = [
        {
            "id": "email",
            "name": "email",
            "type": "email",
            "label": "Email",
            "value": "",
            "visible": True,
        },
        {"id": "french", "type": "text", "label": "French level", "value": "", "visible": True},
    ]
    before = native.store.path.read_bytes()
    result = native.assistance_delivery(identifier, ref, page_context=context)
    assert result["answers"]["library_status"] == "available"
    facts = {r["fact"]: r for r in result["answers"]["facts"]}
    assert set(facts) == {"email", "language_french_cefr"}
    assert facts["email"]["value"] == "  saved@example.invalid  "
    assert facts["email"]["references"][0]["fact"] == "email"
    assert "unrelated" not in str(result).lower()
    assert native.store.path.read_bytes() == before
    assert native.assistance_context(identifier)["assistance_ref"] == ref


def test_native_scope_is_explicit_bound_metadata_not_a_grant(retained_assistance_page, monkeypatch):
    import os

    from test_worker_assistance_delivery import page_context

    from career_evidence_graph.worker_process_identity import process_identity

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    context = page_context(native, ref)
    process = process_identity(os.getpid())
    context["native_scope"] = {
        "target_id": "native-target",
        "tab_id": "native-tab",
        "cdp_target_id": "original-cdp-target",
        "binding_generation": 0,
        "tab_generation": 0,
        "process_fingerprint": {
            "pid": process["pid"],
            "start_time": 42,
            "executable": process["executable"],
        },
        "process_identity": process,
        "application_ref_digest": digest(ref),
    }
    result = native.assistance_delivery(identifier, ref, page_context=context)
    assert result["page_context"]["native_scope"] == context["native_scope"]
    assert result["page_context"]["page_writes_enabled"] is False
    assert result["assistance_ref"]["page_writes_enabled"] is True


def test_backend_readback_can_preserve_native_reference_without_granting_execution(
    retained_assistance_page, monkeypatch
):
    import time

    from career_evidence_graph.application_worker import (
        handoff_binding,
        valid_backend_page_verification,
    )

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    state = native.store.load()
    now = time.time()
    receipt = {
        "page_verified": True,
        "verified_at": now,
        "run_id": ref["binding"]["run_id"],
        "binding": handoff_binding(state, state["jobs"][0]),
        "assistance_ref": ref,
        "page_verification": {
            "protocol": "backend-page-verification/v1",
            "at": now,
            "assistance_ref": ref,
            "document": {"frame_id": "frame", "loader_id": "loader", "url": ref["binding"]["step"]},
            "data": {"url": ref["binding"]["step"], "fields": []},
            "worker_source": state["runtime"]["source"]["sha256"],
        },
    }
    before = native.store.path.read_bytes()
    assert valid_backend_page_verification(receipt)
    assert native.store.path.read_bytes() == before
    bad = deepcopy(receipt)
    bad["page_verification"]["assistance_ref"]["native_policy_digest"] = "invalid"
    assert not valid_backend_page_verification(bad)


def save_native_answers(native, records):
    from career_evidence_graph._vendor import job_apply_store as helper

    helper.atomic_write_json(
        native.store.answers.root / "answers.json",
        {
            "schemaVersion": 1,
            "answers": dict(records),
            "metadata": {},
        },
    )


@pytest.mark.parametrize(
    "change", ["withdrawn", "inferred", "conflict", "nonstring", "empty", "oversized"]
)
def test_native_answer_delivery_does_not_promote_uncertain_or_unsupported_values(
    retained_assistance_page, monkeypatch, change
):
    from test_application_information import answer
    from test_worker_assistance_delivery import page_context

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    records = [answer("French level", "A1")]
    expected = "missing"
    if change == "withdrawn":
        records.append(
            answer(
                "French proficiency CEFR",
                None,
                scope={"application_id": identifier},
                state="missing",
            )
        )
    elif change == "inferred":
        records.append(
            answer(
                "French proficiency CEFR",
                "B2",
                scope={"application_id": identifier},
                state="inferred",
            )
        )
        expected = "inferred"
    elif change == "conflict":
        records = [
            answer("French level", "A1", scope={"country": "CHE"}),
            answer("French proficiency CEFR", "B1", scope={"company": "Synthetic"}),
        ]
        expected = "conflict"
    elif change in {"nonstring", "empty", "oversized"}:
        records = [
            answer(
                "French level",
                {"level": "B1"}
                if change == "nonstring"
                else " "
                if change == "empty"
                else "x" * 20001,
            )
        ]
        expected = "unsupported_value"
    save_native_answers(native, records)
    context = page_context(native, ref)
    context["data"]["fields"] = [
        {"id": "french", "type": "text", "label": "French level", "value": ""}
    ]
    fact = native.assistance_delivery(identifier, ref, page_context=context)["answers"]["facts"][0]
    assert fact["status"] == expected
    assert "value" not in fact and "references" not in fact


@pytest.mark.parametrize("application_scope", [False, True])
def test_native_other_country_qualification_retains_application_exception(
    retained_assistance_page, monkeypatch, application_scope
):
    from test_application_information import answer
    from test_worker_assistance_delivery import page_context

    service, identifier = retained_assistance_page
    state = service.store.load()
    state["jobs"][0]["country"] = "OTHER"
    service.store.save(state)
    native, ref = claim_native(service, identifier, monkeypatch)
    label = "Will you now or in the future require visa sponsorship?"
    save_native_answers(
        native,
        [answer(label, "No", scope={"application_id": identifier} if application_scope else {})],
    )
    context = page_context(native, ref)
    context["data"]["fields"] = [{"id": "sponsor", "type": "text", "label": label, "value": ""}]
    fact = native.assistance_delivery(identifier, ref, page_context=context)["answers"]["facts"][0]
    assert fact["status"] == ("confirmed" if application_scope else "scope_required")
    assert ("value" in fact) == application_scope


@pytest.mark.parametrize("source", ["missing", "corrupt", "profile_only"])
def test_native_saved_answer_reads_do_not_initialize_or_fallback(
    retained_assistance_page, monkeypatch, tmp_path, source
):
    from test_worker_assistance_delivery import page_context

    from career_evidence_graph._vendor import job_apply_store as helper

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    if source == "missing":
        native.store.answers.root = tmp_path / "never-create-this-library"
    elif source == "corrupt":
        (native.store.answers.root / "answers.json").write_text("broken-json")
    else:
        save_native_answers(native, [])
        helper.atomic_write_json(
            native.store.answers.root / "profile.json",
            {
                "schemaVersion": 1,
                "profile": {"email": "profile-only@example.invalid"},
                "metadata": {},
            },
        )
    monkeypatch.setattr(
        helper.Store,
        "initialize",
        lambda *a, **k: pytest.fail("JSON answer read initialized a store"),
    )
    monkeypatch.setattr(
        helper.Store,
        "get_profile",
        lambda *a, **k: pytest.fail("JSON answer read used profile fallback"),
    )
    monkeypatch.setattr(
        helper.Store,
        "get_answer",
        lambda *a, **k: pytest.fail("JSON answer read used initializing answer accessor"),
    )
    context = page_context(native, ref)
    context["data"]["fields"] = [{"id": "email", "type": "email", "label": "Email", "value": ""}]
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts = native.assistance_delivery(identifier, ref, page_context=context)["answers"]["facts"]
    assert facts[0]["status"] == ("missing" if source == "profile_only" else "source_unavailable")
    assert "value" not in facts[0]
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    if source == "missing":
        assert not native.store.answers.root.exists()


@pytest.mark.parametrize(
    "change", ["digest", "pid", "negative_generation", "process_shape", "extra", "wrong_protocol"]
)
def test_native_scope_rejects_malformed_or_foreign_metadata(
    retained_assistance_page, monkeypatch, change
):
    import os

    from test_worker_assistance_delivery import page_context

    from career_evidence_graph.career_portal_data import PortalDataError
    from career_evidence_graph.worker_process_identity import process_identity

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    context = page_context(native, ref)
    process = process_identity(os.getpid())
    scope = {
        "target_id": "target",
        "tab_id": "tab",
        "cdp_target_id": "cdp-target",
        "binding_generation": 0,
        "tab_generation": 1,
        "process_fingerprint": {
            "pid": process["pid"],
            "start_time": 123,
            "executable": process["executable"],
        },
        "process_identity": process,
        "application_ref_digest": digest(ref),
    }
    if change == "digest":
        scope["application_ref_digest"] = "0" * 64
    elif change == "pid":
        scope["process_fingerprint"]["pid"] += 1
    elif change == "negative_generation":
        scope["tab_generation"] = -1
    elif change == "process_shape":
        scope["process_identity"] = {"pid": process["pid"]}
    elif change == "extra":
        scope["resume_credential"] = "must-not-emit"
    elif change == "wrong_protocol":
        ref = {**ref, "protocol": "codex-assistance/v1"}
    context["native_scope"] = scope
    with pytest.raises(PortalDataError):
        native.assistance_delivery(identifier, ref, page_context=context)


def journal_scope(native, ref):
    import os

    from test_worker_assistance_delivery import page_context

    from career_evidence_graph.worker_process_identity import process_identity

    context = page_context(native, ref)
    process = process_identity(os.getpid())
    return {
        "native_scope": {
            "target_id": "native-target",
            "tab_id": "native-tab",
            "cdp_target_id": "cdp-target",
            "binding_generation": 0,
            "tab_generation": 0,
            "process_fingerprint": {
                "pid": process["pid"],
                "start_time": 42,
                "executable": process["executable"],
            },
            "process_identity": process,
            "application_ref_digest": digest(ref),
        },
        "document": context["document"],
    }


def test_native_prepared_intent_is_durable_before_grant_and_repeated_once(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = journal_scope(native, ref)
    before = native.store.load()
    row = native.store.record_native_handoff(
        ref,
        request_id="native-execution",
        phase="prepared",
        scope=scope,
        expected_worker_source=before["runtime"]["source"]["sha256"],
    )
    assert row["phase"] == "prepared"
    assert row["semantic_unknown"] is False
    assert native.store.load()["jobs"][0]["native_handoff_runs"] == [row]
    original = native.store.path.read_bytes()
    assert (
        native.store.record_native_handoff(
            ref,
            request_id="native-execution",
            phase="prepared",
            scope=scope,
            expected_worker_source=before["runtime"]["source"]["sha256"],
        )
        == row
    )
    assert native.store.path.read_bytes() == original
    after = native.store.load()
    assert after["control"] == before["control"]
    assert after["jobs"][0]["assistance"] == before["jobs"][0]["assistance"]


def test_native_prepared_save_failure_does_not_leave_a_grant_record(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = journal_scope(native, ref)
    state = native.store.load()
    before = native.store.path.read_bytes()
    monkeypatch.setattr(
        native.store,
        "save",
        lambda _state: (_ for _ in ()).throw(OSError("synthetic disk failure")),
    )
    with pytest.raises(OSError):
        native.store.record_native_handoff(
            ref,
            request_id="native-execution",
            phase="prepared",
            scope=scope,
            expected_worker_source=state["runtime"]["source"]["sha256"],
        )
    assert native.store.path.read_bytes() == before


def prepare_journal(native, ref):
    scope = journal_scope(native, ref)
    native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="prepared",
        scope=scope,
        expected_worker_source=native.store.load()["runtime"]["source"]["sha256"],
    )
    return scope


def native_status(*, drained=True, calls=None):
    return {
        "handoff_id": "native-handoff",
        "generation": 1,
        "phase": "released" if drained else "revoked",
        "revoked": True,
        "active_calls": 0 if drained else 1,
        "local_tools_drained": drained,
        "return_ready": drained,
        "calls": calls or [],
    }


def test_native_grant_receipt_is_saved_once_without_changing_writer(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    before = native.store.load()
    receipt = {"handoff_id": "native-handoff", "generation": 1, "local_tools_drained": True}
    row = native.store.record_native_handoff(
        ref, request_id="journal-run", phase="granted", scope=scope, receipt=receipt
    )
    assert row["phase"] == "granted" and row["handoff_id"] == "native-handoff"
    original = native.store.path.read_bytes()
    assert (
        native.store.record_native_handoff(
            ref, request_id="journal-run", phase="granted", scope=scope, receipt=receipt
        )
        == row
    )
    assert native.store.path.read_bytes() == original
    assert native.store.load()["jobs"][0]["assistance"] == before["jobs"][0]["assistance"]


@pytest.mark.parametrize("change", ["request", "scope"])
def test_native_journal_cannot_change_the_unfinished_request_scope(
    retained_assistance_page, monkeypatch, change
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    request = "journal-run"
    if change == "request":
        request = "other-native-run"
    else:
        scope["native_scope"]["tab_id"] = "other-tab"
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id=request,
            phase="prepared",
            scope=scope,
            expected_worker_source=native.store.load()["runtime"]["source"]["sha256"],
        )
    assert native.store.path.read_bytes() == before


def test_pause_during_grant_saves_unknown_and_forces_revocation(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    state = native.store.load()
    state["control"] = "paused"
    native.store.save(state)
    original_assistance = deepcopy(state["jobs"][0]["assistance"])
    with pytest.raises(PortalDataError, match="必须撤销"):
        native.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="granted",
            scope=scope,
            receipt={"handoff_id": "native-handoff", "generation": 1, "local_tools_drained": True},
        )
    after = native.store.load()
    row = after["jobs"][0]["native_handoff_runs"][0]
    assert row["phase"] == "unknown" and row["semantic_unknown"] is True
    assert after["control"] == "paused" and after["jobs"][0]["assistance"] == original_assistance


def test_unknown_native_mutation_stays_unknown_after_physical_stop(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    call = {
        "call_id": "type-lost",
        "tool": "browser_type",
        "arguments_digest": "b" * 64,
        "status": "unknown",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "native_ref": "nativep1:0",
        "field_hint": {"role": "textbox", "name": "French level"},
    }
    call["scope"] = {
        "target_id": scope["native_scope"]["target_id"],
        "tab_id": scope["native_scope"]["tab_id"],
        "expected_document": scope["document"],
    }
    call["text_sha256"] = "c" * 64
    status = native_status(calls=[call])
    row = native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopping", scope=scope, receipt=status
    )
    assert row["semantic_unknown"] is True
    row = native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopped", scope=scope, receipt=status
    )
    assert row["phase"] == "stopped" and row["semantic_unknown"] is True
    assert native.store.load()["jobs"][0]["observations"][-1]["call_id"] == "type-lost"
    assert "arguments" not in native.store.load()["jobs"][0]["observations"][-1]
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="next-run",
            phase="prepared",
            scope=scope,
            expected_worker_source=native.store.load()["runtime"]["source"]["sha256"],
        )


def test_late_native_stop_records_original_execution_without_overwriting_new_ref(
    retained_assistance_page, monkeypatch
):
    from uuid import uuid4

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    state = native.store.load()
    state["control"] = "paused"
    state["jobs"][0]["status"] = "cancelled"
    state["jobs"][0]["assistance"]["id"] = uuid4().hex
    native.store.save(state)
    new_assistance = deepcopy(state["jobs"][0]["assistance"])
    row = native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopped", scope=scope, receipt=native_status()
    )
    assert row["assistance_ref"] == ref and row["phase"] == "stopped"
    after = native.store.load()
    assert after["jobs"][0]["assistance"] == new_assistance
    assert after["control"] == "paused" and after["jobs"][0]["status"] == "cancelled"


def test_native_handler_not_returned_cannot_be_reported_drained(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="stopped",
            scope=scope,
            receipt=native_status(drained=False),
        )
    assert native.store.path.read_bytes() == before


@pytest.mark.parametrize(
    "key", ["host_return_credential", "resume_credential", "rendezvous_path", "model_text"]
)
def test_native_journal_never_persists_private_transport_or_model_content(
    retained_assistance_page, monkeypatch, key
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    receipt = native_status()
    receipt[key] = "private transport value"
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref, request_id="journal-run", phase="unknown", scope=scope, receipt=receipt
        )
    assert native.store.path.read_bytes() == before


@pytest.mark.parametrize("source", [None, "0" * 64])
def test_native_prepared_intent_requires_original_loaded_source_identity(
    retained_assistance_page, monkeypatch, source
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="prepared",
            scope=journal_scope(native, ref),
            expected_worker_source=source,
        )
    assert native.store.path.read_bytes() == before


def test_late_stopping_receipt_does_not_regress_a_stopped_native_execution(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopped", scope=scope, receipt=native_status()
    )
    row = native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopping", scope=scope, receipt=native_status()
    )
    assert row["phase"] == "stopped" and row["semantic_unknown"] is False


def test_native_same_call_metadata_cannot_change_arguments_in_history(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    call = {
        "call_id": "click-one",
        "tool": "browser_click",
        "arguments_digest": "b" * 64,
        "status": "observed",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "native_ref": "nativep1:0",
        "field_hint": {"role": "textbox", "name": "French level"},
    }
    call["scope"] = {
        "target_id": scope["native_scope"]["target_id"],
        "tab_id": scope["native_scope"]["tab_id"],
        "expected_document": scope["document"],
    }
    receipt = native_status(calls=[call])
    native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopping", scope=scope, receipt=receipt
    )
    receipt["calls"][0]["arguments_digest"] = "c" * 64
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref, request_id="journal-run", phase="stopped", scope=scope, receipt=receipt
        )
    assert native.store.path.read_bytes() == before


def test_incomplete_native_history_cannot_be_treated_as_a_clean_stop(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    state = native.store.load()
    state["jobs"][0]["native_handoff_runs"][0].update(phase="stopped")
    del state["jobs"][0]["native_handoff_runs"][0]["semantic_unknown"]
    native.store.save(state)
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="next-run",
            phase="prepared",
            scope=scope,
            expected_worker_source=state["runtime"]["source"]["sha256"],
        )
    assert native.store.path.read_bytes() == before


def test_native_mutation_admission_is_journaled_before_the_host_allows_dispatch(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="granted",
        scope=scope,
        receipt={"handoff_id": "native-handoff", "generation": 1, "local_tools_drained": True},
    )
    call = {
        "call_id": "type-awaiting",
        "tool": "browser_type",
        "arguments_digest": "b" * 64,
        "status": "awaiting_host",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "native_ref": "nativep1:0",
        "field_hint": {"role": "textbox", "name": "French level"},
        "text_sha256": "c" * 64,
        "scope": {
            "target_id": scope["native_scope"]["target_id"],
            "tab_id": scope["native_scope"]["tab_id"],
            "expected_document": scope["document"],
        },
    }
    row = native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="granted",
        scope=scope,
        receipt=native_status(drained=False, calls=[call]),
    )
    assert row["events"][-1]["receipt"]["calls"][0]["status"] == "awaiting_host"
    assert row["phase"] == "granted" and row["semantic_unknown"] is False
    assert "text" not in row["events"][-1]["receipt"]["calls"][0]


def test_saved_unknown_mutation_prevents_later_host_admission_in_same_native_run(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="granted",
        scope=scope,
        receipt={"handoff_id": "native-handoff", "generation": 1, "local_tools_drained": True},
    )
    call_scope = {
        "target_id": scope["native_scope"]["target_id"],
        "tab_id": scope["native_scope"]["tab_id"],
        "expected_document": scope["document"],
    }
    call = {
        "call_id": "first-click",
        "tool": "browser_click",
        "arguments_digest": "a" * 64,
        "status": "unknown",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "native_ref": "nativep1:0",
        "field_hint": {"role": "textbox", "name": "French level"},
        "scope": call_scope,
    }
    native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="granted",
        scope=scope,
        receipt=native_status(calls=[call]),
    )
    next_call = {**call, "call_id": "second-click", "sequence": 2, "status": "awaiting_host"}
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="granted",
            scope=scope,
            receipt=native_status(drained=False, calls=[call, next_call]),
        )
    assert native.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["corrected", "withdrawn", "conflict", "unrelated"])
def test_native_type_preflight_revalidates_only_initial_confirmed_answer_refs(
    retained_assistance_page, monkeypatch, change
):
    from test_application_information import answer
    from test_worker_assistance_delivery import page_context

    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    initial = answer("French level", "A1")
    save_native_answers(native, [initial])
    context = page_context(native, ref)
    context["data"]["fields"] = [
        {"id": "french", "type": "text", "label": "French level", "value": ""}
    ]
    delivery = native.assistance_delivery(identifier, ref, page_context=context)
    records = [initial]
    if change == "corrected":
        records = [answer("French level", "B2")]
    elif change == "withdrawn":
        records.append(
            answer(
                "French proficiency CEFR",
                None,
                scope={"application_id": identifier},
                state="missing",
            )
        )
    elif change == "conflict":
        records = [
            answer("French level", "A1", scope={"country": "CHE"}),
            answer("French proficiency CEFR", "B1", scope={"company": "Synthetic"}),
        ]
    else:
        records.append(answer("Unrelated private question", "new-unrelated-fact"))
    save_native_answers(native, records)
    before = native.store.path.read_bytes()
    original_context = deepcopy(context)
    if change == "unrelated":
        assert native.store.validate_native_answers(ref, delivery["answers"]) is True
    else:
        with pytest.raises(PortalDataError):
            native.store.validate_native_answers(ref, delivery["answers"])
    assert native.store.path.read_bytes() == before and context == original_context


def test_native_type_preflight_does_not_initialize_missing_information(
    retained_assistance_page, monkeypatch, tmp_path
):
    from test_application_information import answer
    from test_worker_assistance_delivery import page_context

    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    save_native_answers(native, [answer("Email", "saved@example.invalid")])
    context = page_context(native, ref)
    context["data"]["fields"] = [{"id": "email", "type": "email", "label": "Email", "value": ""}]
    delivery = native.assistance_delivery(identifier, ref, page_context=context)
    native.store.answers.root = tmp_path / "unavailable-native-facts"
    monkeypatch.setattr(
        helper.Store,
        "initialize",
        lambda *a, **kw: pytest.fail("Native preflight initialized information"),
    )
    monkeypatch.setattr(
        helper.Store,
        "get_answer",
        lambda *a, **kw: pytest.fail("Native preflight used initializing lookup"),
    )
    with pytest.raises(PortalDataError):
        native.store.validate_native_answers(ref, delivery["answers"])
    assert not native.store.answers.root.exists()


@pytest.mark.parametrize(
    "change", ["missing_ref", "blank_ref", "long_ref", "hint_extra", "hint_type", "hint_long"]
)
def test_mutation_receipts_require_bounded_native_ref_and_actual_field_hint(
    retained_assistance_page, monkeypatch, change
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    call = {
        "call_id": "native-click",
        "tool": "browser_click",
        "arguments_digest": "a" * 64,
        "status": "awaiting_host",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "scope": {
            "target_id": scope["native_scope"]["target_id"],
            "tab_id": scope["native_scope"]["tab_id"],
            "expected_document": scope["document"],
        },
        "native_ref": "nativep1:0",
        "field_hint": {"role": "textbox", "name": "Email"},
    }
    if change == "missing_ref":
        del call["native_ref"]
    elif change == "blank_ref":
        call["native_ref"] = ""
    elif change == "long_ref":
        call["native_ref"] = "r" * 257
    elif change == "hint_extra":
        call["field_hint"]["selector"] = "#from-model"
    elif change == "hint_type":
        call["field_hint"]["name"] = ["not-native-text"]
    else:
        call["field_hint"]["name"] = "n" * 1001
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="stopping",
            scope=scope,
            receipt=native_status(calls=[call]),
        )
    assert native.store.path.read_bytes() == before


def test_native_unlabelled_control_does_not_invent_a_fact_or_fail_json_context(
    retained_assistance_page, monkeypatch
):
    from test_worker_assistance_delivery import page_context

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    context = page_context(native, ref)
    context["data"]["fields"] = [{"id": "", "name": "", "type": "text", "label": "", "value": ""}]
    answers = native.assistance_delivery(identifier, ref, page_context=context)["answers"]
    assert answers["library_status"] == "not_requested" and answers["facts"] == []


def test_json_delivery_exposes_native_unknown_without_claiming_native_business_completion(
    retained_assistance_page, monkeypatch
):
    from test_worker_assistance_delivery import page_context

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    call = {
        "call_id": "native-type-lost",
        "tool": "browser_type",
        "arguments_digest": "a" * 64,
        "status": "unknown",
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "scope": {
            "target_id": scope["native_scope"]["target_id"],
            "tab_id": scope["native_scope"]["tab_id"],
            "expected_document": scope["document"],
        },
        "native_ref": "nativep1:0",
        "field_hint": {"role": "textbox", "name": "Email"},
        "text_sha256": "b" * 64,
    }
    native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="stopping",
        scope=scope,
        receipt=native_status(calls=[call]),
    )
    delivery = native.assistance_delivery(identifier, ref, page_context=page_context(native, ref))
    assert len(delivery["pending_actions"]) == 1
    pending = delivery["pending_actions"][0]
    assert pending["call_id"] == "native-type-lost" and pending["status"] == "unknown"
    assert pending["source_ref"]["record"] == "native_handoff_runs"
    assert pending["scope"]["native_scope"] == scope["native_scope"]
    assert delivery["progress"]["completed"] == []
    assert delivery["next_step"]["kind"] == "reconcile_pending_actions"


def test_json_delivery_retains_unsettled_native_outer_intent(retained_assistance_page, monkeypatch):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    delivery = native.assistance_delivery(identifier, ref)
    assert delivery["pending_actions"][0]["kind"] == "native_handoff"
    assert delivery["pending_actions"][0]["status"] == "unknown"
    assert delivery["pending_actions"][0]["scope"]["document"] == scope["document"]


@pytest.mark.parametrize("status", ["observed", "not_sent"])
def test_native_nonpending_receipts_do_not_become_business_completion(
    retained_assistance_page, monkeypatch, status
):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    call = {
        "call_id": "native-click",
        "tool": "browser_click",
        "arguments_digest": "a" * 64,
        "status": status,
        "generation": 1,
        "sequence": 1,
        "mutation": True,
        "semantic_verified": False,
        "scope": {
            "target_id": scope["native_scope"]["target_id"],
            "tab_id": scope["native_scope"]["tab_id"],
            "expected_document": scope["document"],
        },
        "native_ref": "nativep1:0",
        "field_hint": {"role": "button", "name": "Choose option"},
    }
    native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="stopped",
        scope=scope,
        receipt=native_status(calls=[call]),
    )
    delivery = native.assistance_delivery(identifier, ref)
    assert delivery["pending_actions"] == [] and delivery["progress"]["completed"] == []


def test_historical_native_unknown_remains_scoped_after_a_new_assistance_reference(
    retained_assistance_page, monkeypatch
):
    from uuid import uuid4

    from test_worker_assistance_delivery import page_context

    from career_evidence_graph.application_worker import assistance_reference

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    native.store.record_native_handoff(ref, request_id="journal-run", phase="unknown", scope=scope)
    state = native.store.load()
    state["jobs"][0]["assistance"]["id"] = uuid4().hex
    native.store.save(state)
    newer = assistance_reference(state["jobs"][0]["assistance"])
    pending = native.assistance_delivery(
        identifier, newer, page_context=page_context(native, newer)
    )["pending_actions"][0]
    assert pending["current_scope"] is False
    assert pending["scope"]["assistance_ref_digest"] == digest(ref)
    assert pending["status"] == "unknown" and pending["scope"]["document"] == scope["document"]


@pytest.mark.parametrize(
    "proof",
    [
        None,
        {"local_tools_drained": True},
        {"revoked": True, "local_tools_drained": True, "active_calls": 0, "return_ready": False},
    ],
)
def test_stored_stopped_history_requires_real_final_drain_and_return_proof(
    retained_assistance_page, monkeypatch, proof
):
    import time

    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    state = native.store.load()
    row = state["jobs"][0]["native_handoff_runs"][0]
    row["phase"] = "stopped"
    row["events"].append({"phase": "stopped", "receipt": proof, "at": time.time()})
    native.store.save(state)
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="new-after-malformed-stop",
            phase="prepared",
            scope=scope,
            expected_worker_source=state["runtime"]["source"]["sha256"],
        )
    assert native.store.path.read_bytes() == before


def test_stored_native_unknown_latch_cannot_be_cleared_by_a_final_stop_snapshot(
    retained_assistance_page, monkeypatch
):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    native.store.record_native_handoff(ref, request_id="journal-run", phase="unknown", scope=scope)
    native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopped", scope=scope, receipt=native_status()
    )
    state = native.store.load()
    state["jobs"][0]["native_handoff_runs"][0]["semantic_unknown"] = False
    native.store.save(state)
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        native.store.record_native_handoff(
            ref,
            request_id="new-after-unknown",
            phase="prepared",
            scope=scope,
            expected_worker_source=state["runtime"]["source"]["sha256"],
        )
    assert native.store.path.read_bytes() == before


def test_late_incomplete_stop_receipt_cannot_replace_the_final_native_stop_proof(
    retained_assistance_page, monkeypatch
):
    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    original = native.store.record_native_handoff(
        ref, request_id="journal-run", phase="stopped", scope=scope, receipt=native_status()
    )
    before = native.store.path.read_bytes()
    late = native.store.record_native_handoff(
        ref,
        request_id="journal-run",
        phase="stopping",
        scope=scope,
        receipt=native_status(drained=False),
    )
    assert late == original and native.store.path.read_bytes() == before


def test_a_long_takeovers_repeated_calls_do_not_fill_the_run_limit(
    retained_assistance_page, monkeypatch
):
    """2026-11-03: 39 receipts of up to 35 calls reached 512 KB on the last option click;
    the save was refused and the takeover ended as native_receipt_persistence_failed."""
    import json

    from career_evidence_graph.application_worker import compact_native_runs
    from career_evidence_graph.career_portal_data import PortalDataError

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    scope = prepare_journal(native, ref)
    call_scope = {
        "target_id": scope["native_scope"]["target_id"],
        "tab_id": scope["native_scope"]["tab_id"],
        "expected_document": scope["document"],
    }
    grant = {"handoff_id": "native-handoff", "generation": 1, "local_tools_drained": True}
    native.store.record_native_handoff(
        ref, request_id="journal-run", phase="granted", scope=scope, receipt=grant
    )
    calls = []
    for sequence in range(1, 61):
        calls.append(
            {
                "call_id": f"read-{sequence:03d}",
                "tool": "get_browser_state",
                "arguments_digest": f"{sequence:064x}",
                "status": "observed",
                "generation": 1,
                "sequence": sequence,
                "mutation": False,
                "semantic_verified": False,
                "scope": call_scope,
            }
        )
        row = native.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="granted",
            scope=scope,
            receipt={
                **grant,
                "phase": "active",
                "revoked": False,
                "active_calls": 0,
                "return_ready": False,
                "calls": list(calls),
            },
        )
    repeated = len(json.dumps(row).encode())
    distinct = len(json.dumps(compact_native_runs([row])[0]).encode())
    assert repeated > 512_000 > distinct
    assert len(row["events"]) == 62

    # The limit still bounds the run's distinct content.
    from career_evidence_graph import application_worker

    monkeypatch.setattr(application_worker, "NATIVE_RUN_DISTINCT_LIMIT", distinct)
    calls.append(dict(calls[-1], call_id="read-061", sequence=61, arguments_digest="f" * 64))
    before = native.store.path.read_bytes()
    with pytest.raises(PortalDataError) as refused:
        native.store.record_native_handoff(
            ref,
            request_id="journal-run",
            phase="granted",
            scope=scope,
            receipt={
                **grant,
                "phase": "active",
                "revoked": False,
                "active_calls": 0,
                "return_ready": False,
                "calls": list(calls),
            },
        )
    assert refused.value.code == "native_handoff_receipt_invalid"
    assert native.store.path.read_bytes() == before
