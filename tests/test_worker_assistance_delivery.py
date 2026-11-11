"""The Worker projects a bounded JSON handoff from existing original-page records."""

import json
import time
from copy import deepcopy

import pytest
from test_single_application_worker import single_worker as single_worker
from test_worker_codex_assistance import retained_assistance_page as retained_assistance_page

from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def claimed_page(retained_assistance_page):
    service, identifier = retained_assistance_page
    service.request(
        "request-assistance",
        {
            "application_id": identifier,
            "binding": service.assistance_context(identifier)["binding"],
            "request_id": "json-handoff",
        },
    )
    reference = service.assistance_context(identifier)["assistance_ref"]
    service.request(
        "claim-assistance",
        {"application_id": identifier, "assistance_ref": reference, "request_id": "json-claim"},
    )
    return service, identifier, reference


def page_context(service, ref):
    return {
        "status": "captured",
        "at": time.time(),
        "observed_at": time.time(),
        "binding": deepcopy(ref["binding"]),
        "document": {
            "frame_id": "original-frame",
            "loader_id": "original-loader",
            "url": ref["binding"]["step"],
        },
        "data": {
            "url": ref["binding"]["step"],
            "title": "Synthetic application",
            "fields": [
                {
                    "id": "country",
                    "name": "country",
                    "type": "combobox",
                    "label": "Country",
                    "value": "",
                    "required": True,
                    "valid": False,
                }
            ],
            "attachments": [],
            "validation_errors": [],
        },
        "worker_source": service.store.load()["runtime"]["source"]["sha256"],
        "page_writes_enabled": False,
    }


def test_handoff_is_json_with_bound_progress_and_no_image_or_side_effects(claimed_page):
    service, identifier, ref = claimed_page
    context = page_context(service, ref)
    before = {p: p.read_bytes() for p in service.store.root.rglob("*") if p.is_file()}
    delivery = service.assistance_delivery(identifier, ref, page_context=context)
    assert json.loads(json.dumps(delivery, allow_nan=False)) == delivery
    assert delivery["schema_version"] == 1
    assert delivery["assistance_ref"] == ref
    assert delivery["progress"]["completed"] == []
    assert delivery["progress"]["remaining"][0]["field_hint"]["id"] == "country"
    assert delivery["page_context"] == context
    assert delivery["pending_actions"] == []
    assert delivery["next_step"]["kind"] == "inspect_control_and_continue"
    assert "screenshot" not in json.dumps(delivery)
    assert {p: p.read_bytes() for p in service.store.root.rglob("*") if p.is_file()} == before
    assert service.store.assistance_delivery(ref, page_context=context) == delivery


def test_verified_receipts_are_completed_but_unknown_actions_are_not_retried(claimed_page):
    service, identifier, ref = claimed_page
    state = service.store.load()
    job = state["jobs"][0]
    job["reason"] = "unsupported_control"
    verified = {
        "action": "fill",
        "attempt_id": "email-filled",
        "field_id": "email",
        "run_id": ref["binding"]["run_id"],
        "page_id": ref["binding"]["page_id"],
    }
    unknown = {
        "action": "upload",
        "attempt_id": "upload-without-reply",
        "run_id": ref["binding"]["run_id"],
        "page_id": ref["binding"]["page_id"],
    }
    job["observations"] += [
        {"action": "fill", "verified": True, "intent": verified, "at": 1},
        {
            "action": "transport",
            "stage": "requestfailed",
            "intent": unknown,
            "reason": "connection_lost",
            "at": 2,
        },
    ]
    job["intent"] = unknown
    service.store.save(state)
    before = service.store.path.read_bytes()
    result = service.assistance_delivery(identifier, ref, page_context=page_context(service, ref))
    assert [r["action_id"] for r in result["progress"]["completed"]] == ["email-filled"]
    assert result["progress"]["completed"][0]["source_ref"] == {
        "record": "effective_action_results",
        "action_id": "email-filled",
    }
    assert result["pending_actions"][0]["action_id"] == "upload-without-reply"
    assert result["pending_actions"][0]["status"] == "unknown"
    assert result["next_step"]["kind"] == "reconcile_pending_actions"
    assert result["blocker"]["code"] == "unsupported_control"
    assert service.store.path.read_bytes() == before


def test_verified_result_is_removed_when_a_later_write_failure_is_unresolved(claimed_page):
    service, identifier, ref = claimed_page
    state = service.store.load()
    intent = {"action": "fill", "field_id": "email", "attempt_id": "same-attempt"}
    state["jobs"][0]["observations"] += [
        {"action": "fill", "verified": True, "intent": intent, "at": 1},
        {"action": "transport", "stage": "requestfailed", "intent": intent, "at": 2},
    ]
    service.store.save(state)
    result = service.assistance_delivery(identifier, ref)
    assert result["progress"]["completed"] == []
    assert result["pending_actions"][0]["action_id"] == "same-attempt"


def test_no_page_context_does_not_create_an_observation_or_infer_progress(claimed_page):
    service, identifier, ref = claimed_page
    state = service.store.load()
    state["jobs"][0]["form_state"]["snapshot"] = {
        "fields": [{"id": "country", "label": "Country", "required": True, "value": ""}]
    }
    service.store.save(state)
    result = service.assistance_delivery(identifier, ref)
    assert result["page_context"] == {"status": "unavailable", "binding": ref["binding"]}
    assert result["progress"]["completed"] == []
    assert result["progress"]["remaining"][0]["source"] == "saved_form_snapshot"


@pytest.mark.parametrize(
    "change",
    [
        "pause",
        "cancel",
        "document",
        "answer",
        "material",
        "wrong_job",
        "wrong_ref",
        "expired",
        "backend",
    ],
)
def test_changed_scope_rejects_the_old_json_handoff_without_writing(claimed_page, change):
    service, identifier, ref = claimed_page
    state = service.store.load()
    if change == "pause":
        state["control"] = "paused"
    elif change == "cancel":
        state["jobs"][0]["status"] = "cancelled"
    elif change == "document":
        state["jobs"][0]["form_state"]["binding"]["document_token"] = "new-document"
    elif change == "answer":
        state["jobs"][0]["answer_refs"] = [{"field_id": "email", "revision": "new"}]
    elif change == "material":
        state["jobs"][0]["file_sha256"] = "0" * 64
    elif change == "wrong_job":
        identifier = "another-application"
    elif change == "wrong_ref":
        ref = {**ref, "generation": ref["generation"] + 1}
    elif change == "expired":
        state["runtime"]["observed_at"] = time.time() - 20
    elif change == "backend":
        state["backend_authority"].update(status="revoked", revoked_at=time.time())
    service.store.save(state)
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.assistance_delivery(identifier, ref)
    assert service.store.path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "binding",
        "url",
        "loader",
        "source",
        "expired",
        "future",
        "screenshot",
        "nan",
        "password",
        "oversized",
        "raw_html",
        "field_screenshot",
    ],
)
def test_page_context_cannot_smuggle_a_foreign_or_non_json_payload(claimed_page, change):
    service, identifier, ref = claimed_page
    context = page_context(service, ref)
    if change == "binding":
        context["binding"]["page_id"] = "other-page"
    elif change == "url":
        context["data"]["url"] = "https://foreign.invalid"
    elif change == "loader":
        context["document"]["loader_id"] = ""
    elif change == "source":
        context["worker_source"] = "0" * 64
    elif change == "expired":
        context["observed_at"] = time.time() - 20
    elif change == "future":
        context["at"] = time.time() + 20
    elif change == "screenshot":
        context["screenshot"] = {"base64": "image"}
    elif change == "nan":
        context["data"]["fields"][0]["value"] = float("nan")
    elif change == "password":
        context["data"]["fields"][0].update(type="password", value="secret")
    elif change == "oversized":
        context["data"]["fields"][0]["value"] = "x" * 512_000
    elif change == "raw_html":
        context["data"]["html"] = "<form>not a locator</form>"
    elif change == "field_screenshot":
        context["data"]["fields"][0]["screenshot"] = "pixels"
    before = service.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        service.assistance_delivery(identifier, ref, page_context=context)
    assert service.store.path.read_bytes() == before


def test_unready_materials_are_not_presented_as_deliverable(claimed_page):
    service, identifier, ref = claimed_page
    state = service.store.load()
    state["jobs"][0]["materials"] = [
        {"id": "unknown-letter", "kind": "cover_letter", "status": "needs_recheck"},
        {"id": "ready-note", "kind": "motivation_text", "status": "ready", "field_id": "note"},
    ]
    # This is a new trusted test snapshot; bind the request to these exact existing materials.
    from career_evidence_graph.application_worker import assistance_binding, assistance_reference

    state["jobs"][0]["assistance"]["binding"] = assistance_binding(state, state["jobs"][0])
    service.store.save(state)
    ref = assistance_reference(state["jobs"][0]["assistance"])
    result = service.assistance_delivery(identifier, ref)
    assert [r.get("material_id") for r in result["materials"]] == [None, "ready-note"]
    assert "unknown-letter" not in json.dumps(result)
    assert "text" not in result["materials"][1]


def test_confirmed_not_applied_action_is_not_called_unknown_or_completed(claimed_page):
    service, identifier, ref = claimed_page
    state = service.store.load()
    intent = {"action": "upload", "attempt_id": "checked-not-applied"}
    state["jobs"][0]["intent"] = intent
    state["jobs"][0]["action_resolutions"] = [
        {
            "intent_ref": "checked-not-applied",
            "intent": intent,
            "conclusion": "not_applied",
            "at": 1,
        },
    ]
    service.store.save(state)
    result = service.assistance_delivery(identifier, ref)
    assert result["progress"]["completed"] == []
    assert result["pending_actions"] == []


@pytest.mark.parametrize(
    "change", ["field_type", "field_flag", "field_validity", "locator", "bad_binding"]
)
def test_json_shapes_are_validated_at_the_interface(claimed_page, change):
    service, identifier, ref = claimed_page
    context = page_context(service, ref)
    if change == "field_type":
        context["data"]["fields"][0]["value"] = {"text": "arbitrary"}
    elif change == "field_flag":
        context["data"]["fields"][0]["required"] = "yes"
    elif change == "field_validity":
        context["data"]["fields"][0]["valid"] = "yes"
    elif change == "locator":
        context["data"]["fields"][0]["locator_hint"] = {"selector": "#untrusted"}
    elif change == "bad_binding":
        ref = {**ref, "binding": ["not a binding"]}
    with pytest.raises(PortalDataError):
        service.assistance_delivery(identifier, ref, page_context=context)


@pytest.mark.parametrize("source", ["aria", "validation_errors"])
def test_custom_control_validation_is_present_in_remaining_and_blocker(claimed_page, source):
    service, identifier, ref = claimed_page
    context = page_context(service, ref)
    field = context["data"]["fields"][0]
    field.update(value="CHE", valid=True)
    if source == "aria":
        field["aria_invalid"] = "true"
    else:
        context["data"]["validation_errors"] = [
            {
                "field_hint": {
                    "id": "country",
                    "name": "country",
                    "role": "combobox",
                    "label": "Country",
                },
                "valid": True,
                "aria_invalid": "true",
            }
        ]
    result = service.assistance_delivery(identifier, ref, page_context=context)
    assert [row["field_hint"]["id"] for row in result["progress"]["remaining"]] == ["country"]
    assert result["blocker"]["field_hint"]["id"] == "country"


@pytest.mark.parametrize("scope", ["historical", "unscoped", "current", "changed_value"])
def test_recorded_completion_is_qualified_by_current_scope_and_readback(claimed_page, scope):
    service, identifier, ref = claimed_page
    state = service.store.load()
    intent = {
        "action": "fill",
        "attempt_id": "country-done",
        "field_id": "country",
        "expected_value": "CHE",
    }
    if scope != "unscoped":
        intent.update({key: ref["binding"][key] for key in ("run_id", "page_id", "document_token")})
    if scope == "historical":
        intent.update(run_id="old-run", page_id="old-page", document_token="old-document")
    state["jobs"][0]["observations"].append(
        {"action": "fill", "verified": True, "intent": intent, "at": 1}
    )
    service.store.save(state)
    context = page_context(service, ref)
    context["data"]["fields"][0].update(
        value="CHE" if scope != "changed_value" else "FRA", valid=True
    )
    row = service.assistance_delivery(identifier, ref, page_context=context)["progress"][
        "completed"
    ][0]
    assert row["action_id"] == "country-done"
    if scope == "current":
        assert row["status"] == "verified" and row["current_scope"] is True
    elif scope == "historical":
        assert row["status"] == "historical_verified" and row["current_scope"] is False
    else:
        assert row["status"] == "verified_scope_unknown"


@pytest.mark.parametrize("change", ["attachment_payload", "validation_not_list", "file_payload"])
def test_nested_context_collections_have_declared_json_shapes(claimed_page, change):
    service, identifier, ref = claimed_page
    context = page_context(service, ref)
    if change == "attachment_payload":
        context["data"]["attachments"] = [{"screenshot": "pixels", "html": "<form>"}]
    elif change == "validation_not_list":
        context["data"]["validation_errors"] = {"script": "arbitrary"}
    else:
        context["data"]["fields"][0]["files"] = [{"name": "resume.pdf", "path": "/untrusted/file"}]
    with pytest.raises(PortalDataError):
        service.assistance_delivery(identifier, ref, page_context=context)


def test_same_document_completion_from_an_earlier_form_step_is_historical(claimed_page):
    service, identifier, ref = claimed_page
    state = service.store.load()
    current_form = state["jobs"][0]["form_state"]["binding"]
    intent = {
        "action": "fill",
        "attempt_id": "previous-step-country",
        "field_id": "country",
        "expected_value": "CHE",
        **{key: ref["binding"][key] for key in ("run_id", "page_id", "document_token")},
        "form_binding": {**current_form, "step": "previous-form-step"},
    }
    state["jobs"][0]["observations"].append(
        {"action": "fill", "verified": True, "intent": intent, "at": 1}
    )
    service.store.save(state)
    context = page_context(service, ref)
    context["data"]["fields"][0].update(value="CHE", valid=True)
    completed = service.assistance_delivery(identifier, ref, page_context=context)["progress"][
        "completed"
    ][0]
    assert completed["status"] == "historical_verified"
    assert completed["current_scope"] is False
    assert completed["scope"]["form_binding"]["step"] == "previous-form-step"


def test_native_answers_map_section_prefixed_labels_and_choice_groups(
    retained_assistance_page, monkeypatch
):
    """onlyfy joins the section heading into a control's label and a radio's label is
    its option text (2026-11-03: saved salutation, country and consent were missing)."""
    from test_application_information import answer
    from test_worker_native_assistance import claim_native

    from career_evidence_graph._vendor import job_apply_store as helper

    service, identifier = retained_assistance_page
    native, ref = claim_native(service, identifier, monkeypatch)
    consent = "I consent to my data being passed on to other companies of the Group"
    helper.atomic_write_json(
        native.store.answers.root / "answers.json",
        {
            "schemaVersion": 1,
            "answers": dict(
                [
                    answer("Salutation", "Ms"),
                    answer("Country of residence", "Switzerland"),
                    answer("Email", "saved@example.invalid"),
                    answer(consent, "Yes"),
                ]
            ),
            "metadata": {},
        },
    )

    def control(identifier, label, kind="combobox", **extra):
        return {"id": identifier, "type": kind, "label": label, "value": "", **extra}

    context = page_context(native, ref)
    context["data"]["fields"] = [
        control("salutation", "Personal details Salutation"),
        control("country", "Personal details Country of residence"),
        # Only a known personal heading is dropped; another contact keeps its identity.
        control("emergency", "Emergency contact Email", "email"),
        control("consent-yes", "Yes", "radio", name="questions[cf_1]", question=consent),
        control("consent-no", "No", "radio", name="questions[cf_1]", question=consent),
        # A choice without its group question stays an unknown question.
        control("lone", "Yes", "radio", name="questions[cf_2]"),
    ]
    facts = {
        row["fact"]: row
        for row in native.assistance_delivery(identifier, ref, page_context=context)["answers"][
            "facts"
        ]
    }
    assert facts["salutation"]["field_ids"] == ["salutation"]
    assert facts["salutation"]["status"] == "confirmed"
    assert facts["country_of_residence"]["field_ids"] == ["country"]
    assert facts["country_of_residence"]["status"] == "confirmed"
    assert facts["data_processing_consent"]["field_ids"] == ["consent-yes", "consent-no"]
    assert facts["data_processing_consent"]["status"] == "confirmed"
    assert facts["question:emergency contact email"]["status"] == "missing"
    assert facts["question:yes"]["field_ids"] == ["lone"]
    assert facts["question:yes"]["status"] == "missing"
    assert "email" not in facts
