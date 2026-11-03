"""Worker material intents keep native identity and durable ownership together."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_native_bound_material_protocol import material_call, text_resolution
from test_single_application_worker import single_worker as single_worker
from test_worker_assistance_delivery import page_context
from test_worker_bound_material_delivery import bound_material_page as bound_material_page
from test_worker_bound_material_delivery import field
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page
from test_worker_native_material_journal import material_call as _material_journal
from test_worker_native_material_journal import sealed_receipt

from career_evidence_graph._vendor.job_apply_store import StoreError
from career_evidence_graph.application_worker import _native_handoff_receipt
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError

material_journal = _material_journal


def receipt(call):
    return {
        "handoff_id": "material-handoff",
        "generation": 1,
        "phase": "active",
        "revoked": False,
        "active_calls": 1,
        "local_tools_drained": False,
        "return_ready": False,
        "calls": [call],
    }


def test_worker_journals_exact_native_material_call_without_private_payload():
    original = receipt(material_call())
    recorded = _native_handoff_receipt(original)
    assert recorded == original
    recorded["calls"][0]["target_descriptor"]["id"] = "other-control"
    assert recorded != original


@pytest.mark.parametrize("status", ["awaiting_host", "observed", "unknown"])
def test_worker_rejects_private_material_bytes_in_native_receipt(status):
    call = material_call() | {"status": status, "material_resolution": text_resolution()}
    with pytest.raises(PortalDataError, match="回执|元数据"):
        _native_handoff_receipt(receipt(call))


def test_worker_rejects_material_metadata_on_an_ordinary_native_type_call():
    call = deepcopy(material_call())
    call.update(tool="browser_type", text_sha256="c" * 64)
    with pytest.raises(PortalDataError):
        _native_handoff_receipt(receipt(call))


def bound_call(service, reference, context):
    catalog = service.store.assistance_delivery(reference, page_context=context)["materials"]
    material = next(row for row in catalog if row["kind"] == "cover_letter")
    call = material_call()
    call.update(
        material_ref=material["material_ref"],
        target_descriptor=deepcopy(context["data"]["fields"][0]["material_target"]),
    )
    call["scope"]["expected_document"] = deepcopy(context["document"])
    return call


def test_runner_resolves_material_against_saved_and_current_exact_field(bound_material_page):
    service, _, issue = bound_material_page
    question = field(draft_path="questions.letter")
    reference, context = issue([question])
    call = bound_call(service, reference, context)
    runner = ApplicationRunner(service.store, None)
    before = service.store.path.read_bytes()

    resolved = runner._resolve_native_material_call(reference, call, context)

    assert resolved["question"] == question
    assert resolved["text"] == service.store.load()["jobs"][0]["materials"][0]["text"]
    assert resolved["material_ref"] == call["material_ref"]
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["label", "marker", "duplicate", "human", "document"])
def test_runner_refuses_changed_or_ambiguous_native_material_target(bound_material_page, change):
    service, _, issue = bound_material_page
    reference, context = issue([field(draft_path="questions.letter")])
    call = bound_call(service, reference, context)
    if change == "label":
        # Both native and owner see the new label; old prepared semantics still refuse it.
        call["target_descriptor"]["label"] = "Salary expectations"
        context["data"]["fields"][0]["material_target"]["label"] = "Salary expectations"
    elif change == "marker":
        call["target_descriptor"]["worker_field"] = "another-field"
    elif change == "duplicate":
        context["data"]["fields"].append(deepcopy(context["data"]["fields"][0]))
    elif change == "human":
        context["data"]["fields"][0]["value"] = "Human draft"
    else:
        call["scope"]["expected_document"]["loader_id"] = "other-loader"
    before = service.store.path.read_bytes()

    with pytest.raises(PortalDataError):
        ApplicationRunner(service.store, None)._resolve_native_material_call(
            reference, call, context
        )

    assert service.store.path.read_bytes() == before


def test_runner_saves_original_material_intent_before_returning_private_payload(material_journal):
    service, reference, scope, current_receipt, _ = material_journal
    call = current_receipt["calls"][0]
    context = page_context(service, reference)
    question = service.store.load()["jobs"][0]["form_state"]["snapshot"]["fields"][0]
    context["data"]["fields"] = [
        {
            "id": call["target_descriptor"]["id"],
            "type": question["type"],
            "value": "",
            "material_target": deepcopy(call["target_descriptor"]),
        }
    ]

    payload = ApplicationRunner(service.store, None)._prepare_native_material_call(
        reference,
        call,
        context,
        request_id="journal-run",
        scope=scope,
        receipt=current_receipt,
    )

    state = service.store.load()
    intent = state["jobs"][0]["intent"]
    assert intent["expected_value"] == payload["text"]
    assert intent["native_material"]["call_id"] == call["call_id"]
    assert intent["native_material"]["resolution"] == {
        key: value for key, value in payload.items() if key != "text"
    }
    assert service.store.native_material_intent(state, state["jobs"][0], reference) == intent


def prepared_runner(material_journal):
    service, reference, scope, current_receipt, _ = material_journal
    runner = ApplicationRunner(service.store, None)
    call = current_receipt["calls"][0]
    context = page_context(service, reference)
    context["data"]["fields"] = [
        {
            "value": "",
            "material_target": deepcopy(call["target_descriptor"]),
        }
    ]
    payload = runner._prepare_native_material_call(
        reference,
        call,
        context,
        request_id="journal-run",
        scope=scope,
        receipt=current_receipt,
    )
    intent = service.store.load()["jobs"][0]["intent"]
    return runner, payload, (service, reference, scope, current_receipt, intent)


def test_failed_material_checkpoint_returns_no_private_payload(material_journal, monkeypatch):
    service, *_ = material_journal
    before = service.store.path.read_bytes()

    def disk_full(state):
        raise OSError("synthetic full disk")

    monkeypatch.setattr(service.store, "save", disk_full)
    with pytest.raises(OSError):
        prepared_runner(material_journal)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("failure", [ValueError, TypeError])
def test_failed_material_serialization_uses_storage_failure_boundary(
    material_journal, monkeypatch, failure
):
    from career_evidence_graph._vendor import job_apply_store as helper

    service, *_ = material_journal
    before = service.store.path.read_bytes()
    original = helper.atomic_write_json

    def fail_checkpoint(path, value):
        if path == service.store.path:
            raise failure("synthetic serialization failure")
        return original(path, value)

    monkeypatch.setattr(helper, "atomic_write_json", fail_checkpoint)
    with pytest.raises(StoreError, match="checkpoint"):
        prepared_runner(material_journal)
    assert service.store.path.read_bytes() == before
    assert service.store.storage_error == "checkpoint_unavailable"


@pytest.mark.parametrize(
    "result",
    [
        "observed",
        "unknown",
        "in_flight",
        "changed",
        "invalid",
        "save_failed",
        "scope_error",
        "timeout",
    ],
)
def test_material_reconciliation_requires_original_observed_and_actual_value(
    material_journal, monkeypatch, result
):
    runner, payload, journal = prepared_runner(material_journal)
    service, reference, scope, _, intent = journal
    status = result if result in {"unknown", "in_flight"} else "observed"
    native = sealed_receipt(journal, status)
    service.store.record_native_handoff(
        reference,
        request_id="journal-run",
        phase="unknown" if status == "unknown" else "granted",
        scope=scope,
        receipt=native,
    )
    target = deepcopy(native["calls"][0]["target_descriptor"])
    target["value_empty"] = False
    actual = {
        "field": {"material_target": target, "valid": result != "invalid", "aria_invalid": ""},
        "sha256": payload["sha256"],
        "size_bytes": payload["size_bytes"],
        "filename": None,
        "value": payload["text"] if result != "changed" else "Human changed text",
    }
    reads = []
    monkeypatch.setattr(runner, "_assistance_page_checker", lambda ref: (None, lambda: None))
    monkeypatch.setattr(
        runner, "_read_native_material_field", lambda *args, **kwargs: reads.append(args) or actual
    )
    if result in {"scope_error", "timeout"}:
        from playwright.sync_api import TimeoutError

        def failed_read(*args, **kwargs):
            reads.append(args)
            if result == "scope_error":
                raise PortalDataError("material_readback_unknown", "原字段范围已变化。", 409)
            raise TimeoutError("synthetic original field readback timeout")

        monkeypatch.setattr(runner, "_read_native_material_field", failed_read)

    if result == "save_failed":
        from career_evidence_graph._vendor import job_apply_store as helper

        original = helper.atomic_write_json

        def fail_checkpoint(path, value):
            if path == service.store.path:
                raise ValueError("synthetic late serialization failure")
            return original(path, value)

        monkeypatch.setattr(helper, "atomic_write_json", fail_checkpoint)
        with pytest.raises(StoreError, match="checkpoint"):
            runner._reconcile_native_material(reference, native, request_id="journal-run")
        assert service.store.load()["jobs"][0]["intent"] == intent
        assert runner.storage_stopped
        return

    if result in {"scope_error", "timeout"}:
        from career_evidence_graph.application_codex_assist import CodexAdapter

        reconciled = []

        def after_yield(value):
            service.store.record_native_handoff(
                reference, request_id="journal-run", phase="granted", scope=scope, receipt=value
            )
            reconciled.append(
                runner._reconcile_native_material(reference, value, request_id="journal-run")
            )

        run = SimpleNamespace(
            status="running",
            error_code="",
            tools_revoked=False,
            native={
                "persistence_failed": False,
                "failed_receipt": None,
                "published": "",
                "after_yield": after_yield,
                "yield_started": False,
            },
        )
        # Exercise the real publication callback; no native execution is claimed.
        CodexAdapter._native_publish(object.__new__(CodexAdapter), run, native)
        assert run.native["persistence_failed"] is False
        assert run.native["failed_receipt"] is None
        assert run.status == "running"
        assert reconciled == [False]
        verified = reconciled[0]
    else:
        verified = runner._reconcile_native_material(reference, native, request_id="journal-run")

    current = service.store.load()["jobs"][0]
    assert verified is (result == "observed")
    assert (current["intent"] is None) is (result == "observed")
    assert bool(reads) is (status == "observed")
    assert current["assistance"]["active_writer"] == "codex"
    if verified:
        assert (
            current["form_state"]["written_fields"][intent["field_id"]]["value"] == payload["text"]
        )
    else:
        assert current["intent"] == intent
        assert not any(row.get("action") == "action_result" for row in current["observations"])
        if result in {"scope_error", "timeout"}:
            assert current["native_handoff_runs"][0]["events"][-1]["receipt"] == native


@pytest.mark.parametrize(
    "status", ["awaiting_host", "in_flight", "observed", "unknown", "unsealed"]
)
def test_native_network_permission_requires_actual_original_seal(
    material_journal, monkeypatch, status
):
    runner, _, journal = prepared_runner(material_journal)
    service, reference, scope, original, intent = journal
    native = original if status == "unsealed" else sealed_receipt(journal, status)
    service.store.record_native_handoff(
        reference,
        request_id="journal-run",
        phase="unknown" if status == "unknown" else "granted",
        scope=scope,
        receipt=native,
    )
    page = object()
    state = service.store.load()
    job = state["jobs"][0]
    runner.pages[job["application_id"]] = page
    monkeypatch.setattr(runner, "_assistance_page_checker", lambda ref: (page, lambda: None))

    allowed = runner._native_material_network_permitted(state, job, page)

    assert allowed is (status in {"awaiting_host", "in_flight", "observed"})
    assert service.store.load()["jobs"][0]["intent"] == intent
    assert runner.permitted(state, page) is False


@pytest.mark.parametrize("material_journal", ["text", "file"], indirect=True)
def test_verified_material_cleared_on_same_page_cannot_create_second_attempt(
    material_journal, monkeypatch
):
    runner, payload, journal = prepared_runner(material_journal)
    service, reference, scope, original_receipt, intent = journal
    observed = sealed_receipt(journal, "observed")
    service.store.record_native_handoff(
        reference, request_id="journal-run", phase="granted", scope=scope, receipt=observed
    )
    file = payload["kind"] == "file"
    target = deepcopy(observed["calls"][0]["target_descriptor"])
    target.update(value_empty=False, file_count=1 if file else 0)
    actual = {
        "field": {"material_target": target, "valid": True, "aria_invalid": ""},
        "sha256": payload["sha256"],
        "size_bytes": payload["size_bytes"],
        "filename": payload.get("filename"),
        "value": payload.get("text"),
    }
    monkeypatch.setattr(runner, "_assistance_page_checker", lambda ref: (None, lambda: None))
    monkeypatch.setattr(runner, "_read_native_material_field", lambda *a, **kw: actual)
    assert runner._reconcile_native_material(reference, observed, request_id="journal-run")
    job = service.store.load()["jobs"][0]
    assert job["intent"] is None
    assert intent in runner.verified_intents(job)

    # The same original field is now empty again. A fresh native ref/call does
    # not authorize replaying its earlier verified delivery after that removal.
    call = deepcopy(original_receipt["calls"][0])
    call.update(
        call_id="second-material-call",
        native_ref="nativep2:0",
        sequence=2,
        arguments_digest="d" * 64,
    )
    context = page_context(service, reference)
    context["data"]["fields"] = [{"value": "", "material_target": call["target_descriptor"]}]
    current_receipt = {**observed, "calls": [observed["calls"][0], call]}
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError) as failure:
        runner._prepare_native_material_call(
            reference,
            call,
            context,
            request_id="journal-run",
            scope=scope,
            receipt=current_receipt,
        )
    assert failure.value.code == "recovered_result_not_visible"
    assert service.store.path.read_bytes() == before
    assert service.store.load()["jobs"][0]["intent"] is None


@pytest.mark.parametrize("material_journal", ["text", "file"], indirect=True)
def test_recorded_ordinary_material_completion_also_prevents_native_replay(material_journal):
    service, reference, scope, receipt_value, template = material_journal
    intent = deepcopy(template)
    intent.pop("native_material")
    state = service.store.load()
    state["jobs"][0]["observations"].append(
        {
            "action": "action_result",
            "intent": intent,
            "result": "verified",
            "run_id": intent["run_id"],
            "at": intent["prepared_at"],
        }
    )
    service.store.save(state)
    runner = ApplicationRunner(service.store, None)
    assert intent in runner.verified_intents(service.store.load()["jobs"][0])
    call = receipt_value["calls"][0]
    context = page_context(service, reference)
    context["data"]["fields"] = [{"value": "", "material_target": call["target_descriptor"]}]
    before = service.store.path.read_bytes()

    with pytest.raises(PortalDataError) as failure:
        runner._prepare_native_material_call(
            reference, call, context, request_id="journal-run", scope=scope, receipt=receipt_value
        )

    assert failure.value.code == "recovered_result_not_visible"
    assert service.store.path.read_bytes() == before


def unparsed_resume_call(service, reference, context, label):
    """A page the script parsed to zero questions, with one hidden resume file input."""
    target = {
        "frame": "main",
        "worker_field": "",
        "draft_path": "",
        "id": "",
        "name": "",
        "tag": "input",
        "type": "file",
        "label": label,
        "required": False,
        "disabled": False,
        "readonly": False,
        "accept": ".pdf,.doc,.docx",
        "multiple": False,
        "max_length": None,
        "file_count": 0,
        "value_empty": True,
    }
    context["data"]["fields"] = [
        {"id": "", "type": "file", "label": label, "value": "", "material_target": target},
        {"id": "first", "type": "text", "label": "First name", "value": ""},
    ]
    catalog = service.store.assistance_delivery(reference, page_context=context)["materials"]
    call = material_call()
    call.update(
        material_ref=next(row for row in catalog if row["kind"] == "resume")["material_ref"],
        target_descriptor=deepcopy(target),
        field_hint={"role": "button", "name": label or "file"},
    )
    call["scope"]["expected_document"] = deepcopy(context["document"])
    return call


@pytest.mark.parametrize(
    ("label", "accepted"),
    [
        ("Upload your CV", True),
        ("Lebenslauf *", True),
        # Preparation owns field meaning: no resume into a cover-letter or unnamed input.
        ("Cover letter", False),
        ("CV and cover letter", False),
        ("Certificates", False),
        ("", False),
    ],
)
def test_runner_resolves_the_resume_on_a_page_without_script_questions(
    bound_material_page, label, accepted
):
    service, _, issue = bound_material_page
    reference, context = issue([], prepare=False)
    call = unparsed_resume_call(service, reference, context, label)
    runner = ApplicationRunner(service.store, None)
    before = service.store.path.read_bytes()

    if not accepted:
        with pytest.raises(PortalDataError) as error:
            runner._resolve_native_material_call(reference, call, context)
        assert error.value.code in {"material_field_changed", "material_destination_unverified"}
        assert service.store.path.read_bytes() == before
        return
    resolved = runner._resolve_native_material_call(reference, call, context)
    job = service.store.load()["jobs"][0]
    assert resolved["question"] is None
    assert resolved["material_id"] == "resume"
    assert resolved["sha256"] == job["file_sha256"]
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["second_file", "attached", "document", "cover_letter_ref"])
def test_runner_refuses_an_unproven_resume_destination_without_questions(
    bound_material_page, change
):
    service, _, issue = bound_material_page
    reference, context = issue([], prepare=False)
    call = unparsed_resume_call(service, reference, context, "Upload your CV")
    if change == "second_file":
        context["data"]["fields"].append(
            dict(deepcopy(context["data"]["fields"][0]), label="Other document")
        )
        context["data"]["fields"][-1]["material_target"]["label"] = "Other document"
    elif change == "attached":
        call["target_descriptor"].update(value_empty=False, file_count=1)
        context["data"]["fields"][0]["material_target"].update(value_empty=False, file_count=1)
    elif change == "document":
        call["scope"]["expected_document"]["loader_id"] = "other-loader"
    else:
        catalog = service.store.assistance_delivery(reference, page_context=context)["materials"]
        call["material_ref"] = next(
            (row["material_ref"] for row in catalog if row["kind"] != "resume"), "d" * 64
        )
    with pytest.raises(PortalDataError):
        ApplicationRunner(service.store, None)._resolve_native_material_call(
            reference, call, context
        )


def test_unparsed_resume_delivery_journals_the_ledger_row_as_its_only_attempt(
    bound_material_page,
):
    from test_worker_native_assistance import prepare_journal

    from career_evidence_graph.application_worker_browser import native_resume_delivered

    service, _, issue = bound_material_page
    reference, context = issue([], prepare=False)
    call = unparsed_resume_call(service, reference, context, "Upload your CV")
    scope = prepare_journal(service, reference)
    call["scope"] = {
        "target_id": scope["native_scope"]["target_id"],
        "tab_id": scope["native_scope"]["tab_id"],
        "expected_document": scope["document"],
    }
    context["document"] = deepcopy(scope["document"])
    grant = {"handoff_id": "material-handoff", "generation": 1, "local_tools_drained": True}
    service.store.record_native_handoff(
        reference, request_id="journal-run", phase="granted", scope=scope, receipt=grant
    )
    service.store.record_native_handoff(
        reference,
        request_id="journal-run",
        phase="granted",
        scope=scope,
        receipt=dict(receipt(call), active_calls=0, local_tools_drained=True),
    )
    payload = ApplicationRunner(service.store, None)._prepare_native_material_call(
        reference,
        call,
        context,
        request_id="journal-run",
        scope=scope,
        receipt=receipt(call),
    )
    job = service.store.load()["jobs"][0]
    assert job.get("intent") is None
    assert payload["sha256"] == job["file_sha256"]
    manifest = {k: v for k, v in payload.items() if k != "bytes_base64"}
    observed = dict(
        call,
        status="observed",
        material_resolution=manifest,
        material_readback={
            "kind": "file_list",
            "sha256": manifest["sha256"],
            "size_bytes": manifest["size_bytes"],
            "filename": manifest["filename"],
            "file_count": 1,
        },
    )
    service.store.record_native_handoff(
        reference,
        request_id="journal-run",
        phase="granted",
        scope=scope,
        receipt=dict(receipt(observed), active_calls=0, local_tools_drained=True),
    )
    job = service.store.load()["jobs"][0]
    assert native_resume_delivered(job, scope["document"])
