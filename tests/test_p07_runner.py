"""Retained-page merging and unknown actions never overwrite or blindly replay."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from career_evidence_graph import application_form_runner as flow
from career_evidence_graph.application_form_state import sample
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def field(value="", **changes):
    return {
        "id": "email",
        "type": "email",
        "question": "Email",
        "value": value,
        "valid": True,
        "required": True,
        **changes,
    }


def job_for(fields):
    observed = {
        "fields": fields,
        "stage": "form",
        "document_token": "document",
        "parser": {"status": "complete"},
    }
    form = None
    for now in (0, 0.25, 0.5):
        form = sample(
            form,
            observed,
            binding={
                "run_id": "run",
                "page_id": "page",
                "step": "form",
                "document_token": "document",
            },
            now=now,
        )
    return {"form_state": form, "intent": None, "observations": []}, observed


def test_nonempty_fields_collect_one_batch_and_phone_format_is_equivalent():
    current = [field("human@example.invalid"), field("+41 (79) 123-45-67", id="phone", type="tel")]
    job, observed = job_for(current)
    fills, kept = flow.plan(
        job,
        observed,
        [
            (current[0], "saved@example.invalid", {"key": "mail"}),
            (current[1], "+41791234567", {"key": "phone"}),
        ],
    )
    assert fills == [] and len(kept) == 1
    assert job["form_state"]["differences"][0]["current_value"] == "human@example.invalid"


@pytest.mark.parametrize("action", ["keep", "use", "edit"])
def test_explicit_choice_applies_only_to_its_observed_field_source_and_proposal(action):
    current = field("human@example.invalid")
    job, observed = job_for([current])
    reference = {"key": "saved", "revision": "one"}
    proposed = "saved@example.invalid"
    flow.plan(job, observed, [(current, proposed, reference)])
    difference = job["form_state"]["differences"][0]
    value = (
        current["value"]
        if action == "keep"
        else proposed
        if action == "use"
        else "edited@example.invalid"
    )
    job["form_state"]["choices"] = {
        difference["id"]: {
            **difference,
            "action": action,
            "value": value,
            "binding": deepcopy(job["form_state"]["binding"]),
        }
    }
    fills, kept = flow.plan(job, observed, [(current, proposed, reference)])
    assert bool(fills) == (action != "keep")
    assert bool(kept) == (action == "keep")
    assert job["form_state"]["differences"] == []
    if fills:
        assert fills[0][1] == value
    changed = field("third@example.invalid")
    assert flow.plan(job, observed, [(changed, proposed, reference)]) == ([], [])
    assert job["form_state"]["differences"]
    flow.plan(job, observed, [(current, proposed, {**reference, "revision": "two"})])
    assert job["form_state"]["differences"]


def test_website_replacing_protected_value_with_saved_value_still_needs_choice():
    original = field("human@example.invalid")
    job, observed = job_for([original])
    rewritten = field("saved@example.invalid")
    fills, kept = flow.plan(job, observed, [(rewritten, rewritten["value"], {"key": "saved"})])
    assert fills == kept == []
    assert job["form_state"]["differences"][0]["baseline_value"] == original["value"]


def test_user_clearing_a_system_written_value_is_not_an_empty_field_to_refill():
    current = field("")
    job, observed = job_for([current])
    flow.note_write(job, current, "saved@example.invalid", {"key": "saved"})
    assert flow.plan(job, observed, [(current, "saved@example.invalid", {"key": "saved"})]) == (
        [],
        [],
    )
    assert job["form_state"]["differences"]


@pytest.mark.parametrize(
    "current,dispatch,expected",
    [
        ("saved@example.invalid", "sent", "current_matches"),
        ("", "prepared", "not_applied"),
        ("", "sent", "unknown"),
        ("third@example.invalid", "returned", "third_value"),
    ],
)
def test_unknown_fill_classifies_current_target_before_value_third_value_and_unknown(
    current, dispatch, expected
):
    observed_field = field(current)
    job, observed = job_for([observed_field])
    page = object()
    runner = SimpleNamespace(run_id="run", page_ids={page: "page"}, drafts={})
    intent = {
        "form_protocol": "form-state/v1",
        "action": "fill",
        "field_id": "email",
        "field_type": "email",
        "expected_value": "saved@example.invalid",
        "before_value": "",
        "run_id": "run",
        "page_id": "page",
        "attempt_id": "attempt",
        "dispatch_state": dispatch,
    }
    intent["form_binding"] = deepcopy(job["form_state"]["binding"])
    intent["field_shape"] = digest(
        {key: observed_field.get(key) for key in ("id", "type", "question", "options", "required")}
    )
    job["intent"] = deepcopy(intent)
    assert flow.inspect_pending(runner, page, job, observed) == expected
    assert (job["intent"] is None) == (
        expected in {"current_matches", "not_applied", "third_value"}
    )
    if expected == "third_value":
        assert job["form_state"]["pending_action_difference"]["current_value"] == current


@pytest.mark.parametrize("hash_matches", [False, True])
def test_unknown_upload_requires_actual_hash_not_equal_filename(hash_matches):
    actual = field(
        "",
        id="resume",
        type="file",
        filename="resume.pdf",
        file_sha256="a" * 64 if hash_matches else "b" * 64,
    )
    job, observed = job_for([actual])
    page = object()
    runner = SimpleNamespace(run_id="run", page_ids={page: "page"}, drafts={})
    job["intent"] = {
        "action": "upload",
        "form_protocol": "form-state/v1",
        "sha256": "a" * 64,
        "run_id": "run",
        "page_id": "page",
        "dispatch_state": "sent",
    }
    job["intent"]["form_binding"] = deepcopy(job["form_state"]["binding"])
    assert flow.inspect_pending(runner, page, job, observed) == (
        "current_matches" if hash_matches else "unknown"
    )


@pytest.mark.parametrize(
    "mutation", ["parser", "errors", "required", "difference", "intent", "intervention"]
)
def test_submit_readiness_rejects_each_unresolved_gate(mutation):
    job, observed = job_for([field("saved@example.invalid")])
    flow.check_ready(job, observed)
    if mutation == "parser":
        job["form_state"]["parser"]["status"] = "waiting"
    elif mutation == "errors":
        observed["validation_errors"] = [{"field_id": "email", "message": "Invalid"}]
    elif mutation == "required":
        observed["fields"][0]["valid"] = False
    elif mutation == "difference":
        job["form_state"]["differences"] = [{"important": True}]
    elif mutation == "intent":
        job["intent"] = {"action": "upload"}
    else:
        job["form_state"]["intervention_pending"] = True
    with pytest.raises(PortalDataError):
        flow.check_ready(job, observed)


def test_cover_upload_cannot_be_completed_by_equal_resume_bytes():
    resume = field("", id="resume", type="file", resume=True, file_sha256="a" * 64)
    cover = field("", id="cover", type="file", resume=False, file_sha256="")
    job, observed = job_for([resume, cover])
    page = object()
    runner = SimpleNamespace(run_id="run", page_ids={page: "page"}, drafts={})
    job["intent"] = {
        "action": "upload",
        "form_protocol": "form-state/v1",
        "sha256": "a" * 64,
        "field_id": "cover",
        "kind": "cover_letter",
        "material_id": "cover-material",
        "run_id": "run",
        "page_id": "page",
        "dispatch_state": "sent",
    }
    job["intent"]["form_binding"] = deepcopy(job["form_state"]["binding"])
    assert flow.inspect_pending(runner, page, job, observed) == "unknown"
    assert job["intent"]


@pytest.mark.parametrize("dispatch", ["prepared", "returned"])
def test_completed_fill_with_third_value_enters_concentrated_choices(dispatch):
    current = field("third@example.invalid")
    job, observed = job_for([current])
    page = object()
    runner = SimpleNamespace(run_id="run", page_ids={page: "page"}, drafts={})
    job["intent"] = {
        "action": "fill",
        "form_protocol": "form-state/v1",
        "field_id": "email",
        "field_type": "email",
        "before_value": "",
        "expected_value": "saved@example.invalid",
        "run_id": "run",
        "page_id": "page",
        "dispatch_state": dispatch,
    }
    job["intent"]["form_binding"] = deepcopy(job["form_state"]["binding"])
    job["intent"]["field_shape"] = digest(
        {key: current.get(key) for key in ("id", "type", "question", "options", "required")}
    )
    assert flow.inspect_pending(runner, page, job, observed) == "third_value"
    assert job["intent"] is None
    assert job["action_resolutions"][-1]["conclusion"] == "superseded"
    assert job["form_state"]["differences"][0]["current_value"] == current["value"]


def retained_runner(tmp_path, monkeypatch):
    from test_hosted_ats import live_service, prepare

    from career_evidence_graph.application_worker import start_run
    from career_evidence_graph.application_worker_browser import ApplicationRunner

    service = live_service(tmp_path, monkeypatch)
    current = prepare(service)
    start_run(service.store)
    runner = ApplicationRunner(service.store, None)
    page = type("RetainedPage", (), {"url": current["job_url"]})()
    runner.pages[current["application_id"]] = page
    runner.page_ids[page] = "retained-page"
    state = service.store.load()
    return runner, page, state["jobs"][0], state["batch_id"]


def test_same_url_new_document_clears_choices_and_preserves_old_baseline_history(
    tmp_path, monkeypatch
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    observed = {"fields": [field("human@example.invalid")], "document_token": "old-document"}
    first = flow.capture(runner, page, job, batch, observed)
    state = runner.store.load()
    state["jobs"][0]["form_state"]["choices"] = {"old-choice": {"value": "old"}}
    runner.store.save(state)
    fresh = flow.capture(runner, page, job, batch, {**observed, "document_token": "new-document"})
    assert fresh["binding"]["document_token"] == "new-document"
    assert not fresh.get("choices")
    assert runner.store.load()["jobs"][0]["form_history"][-1]["baseline"] == first["baseline"]


def test_old_document_unknown_fill_does_not_gain_replay_from_new_empty_document():
    job, observed = job_for([field("")])
    observed["document_token"] = "new-document"
    page = object()
    runner = SimpleNamespace(run_id="run", page_ids={page: "page"}, drafts={})
    job["intent"] = {
        "action": "fill",
        "form_protocol": "form-state/v1",
        "field_id": "email",
        "field_type": "email",
        "before_value": "",
        "expected_value": "saved@example.invalid",
        "form_binding": {"document_token": "old-document"},
        "run_id": "run",
        "page_id": "page",
        "dispatch_state": "prepared",
    }
    before = deepcopy(job["intent"])
    assert flow.inspect_pending(runner, page, job, observed) == "unknown"
    assert job["intent"] == before


def test_late_plan_cannot_replace_an_equal_snapshot_on_new_document(tmp_path, monkeypatch):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    observed = {"fields": [field("human@example.invalid")], "document_token": "old-document"}
    flow.capture(runner, page, job, batch, observed)
    flow.plan(
        job, observed, [(observed["fields"][0], "saved@example.invalid", {"source": "saved"})]
    )
    old = deepcopy(job)
    flow.capture(runner, page, job, batch, {**observed, "document_token": "new-document"})
    before = deepcopy(runner.store.load())
    with pytest.raises(PortalDataError):
        flow.save_plan(runner, old, batch)
    assert runner.store.load() == before


def test_late_capture_after_cancel_preserves_existing_checkpoint(tmp_path, monkeypatch):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    observed = {"fields": [field("human@example.invalid")], "document_token": "document"}
    flow.capture(runner, page, job, batch, observed)
    before = runner.store.load()
    before["jobs"][0]["status"] = "cancelled"
    runner.store.save(before)
    with pytest.raises(PortalDataError):
        flow.capture(
            runner, page, job, batch, {**observed, "fields": [field("late@example.invalid")]}
        )
    assert runner.store.load() == before


def test_pre_send_snapshot_rejects_late_attachment_and_parser_activity():
    original = {
        "fields": [field("", id="resume", type="file", filename="")],
        "document_token": "document",
    }
    late = deepcopy(original)
    late["fields"][0].update(filename="human.pdf", file_sha256="a" * 64)
    runner = SimpleNamespace(observe=lambda *_: late)
    with pytest.raises(PortalDataError):
        flow.check_snapshot(runner, object(), {}, original)

    runner.observe = lambda *_: {**original, "parser": {"status": "active"}}
    with pytest.raises(PortalDataError):
        flow.check_snapshot(runner, object(), {}, original)


def test_consumed_choice_cannot_overwrite_later_human_reversion():
    human = field("human@example.invalid")
    job, observed = job_for([human])
    ref = {"key": "saved"}
    flow.plan(job, observed, [(human, "saved@example.invalid", ref)])
    difference = job["form_state"]["differences"][0]
    job["form_state"]["choices"] = {
        difference["id"]: {
            **difference,
            "action": "use",
            "value": "saved@example.invalid",
            "binding": deepcopy(job["form_state"]["binding"]),
        }
    }
    written = field("saved@example.invalid")
    flow.note_write(job, written, written["value"], ref)
    assert job["form_state"]["choices"][difference["id"]]["applied"]
    assert flow.plan(job, observed, [(human, written["value"], ref)]) == ([], [])
    assert job["form_state"]["differences"]


@pytest.mark.parametrize("change", ["none", "attempt", "document", "cancelled", "run"])
def test_fill_readback_endorses_only_the_original_active_form(tmp_path, monkeypatch, change):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    observed = {"fields": [field("saved@example.invalid")], "document_token": "document"}
    flow.capture(runner, page, job, batch, observed)
    intent = {
        "action": "fill",
        "attempt_id": "old-attempt",
        "run_id": runner.run_id,
        "page_id": runner.page_ids[page],
        "form_binding": deepcopy(job["form_state"]["binding"]),
    }
    state = runner.store.load()
    current = state["jobs"][0]
    current.update(status="filling", intent=deepcopy(intent))
    current["form_state"]["written_fields"] = {"protected": {"value": "newer"}}
    if change == "attempt":
        current["intent"]["attempt_id"] = "new-attempt"
    elif change == "document":
        current["form_state"]["binding"]["document_token"] = "new-document"
    elif change == "cancelled":
        current["status"] = "cancelled"
    elif change == "run":
        state["runtime"]["id"] = "next-run"
    before = deepcopy(current)
    runner.store.save(state)
    monkeypatch.setattr(runner, "permitted", lambda *_: True)
    adopted = flow.record_fill(
        runner,
        job,
        batch,
        intent,
        observed["fields"][0],
        "saved@example.invalid",
        {"key": "saved"},
        {},
        observed,
    )
    after = runner.store.load()["jobs"][0]
    assert adopted == (change == "none")
    if change != "none":
        assert after["intent"] == before["intent"]
        assert after["form_state"] == before["form_state"]
        assert after["answer_refs"] == before["answer_refs"]
        assert after["observations"][-1]["action"] == "late_fill_result"


def test_parser_activity_retains_each_observed_adjacent_value_and_expires_only_changed_choice(
    tmp_path, monkeypatch
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    observed = {
        "fields": [field("human@example.invalid")],
        "document_token": "document",
        "parser": {"status": "active"},
    }
    flow.capture(runner, page, job, batch, observed)
    state = runner.store.load()
    state["jobs"][0]["form_state"]["choices"] = {
        "mail": {"field_id": "email"},
        "other": {"field_id": "other"},
    }
    runner.store.save(state)
    for value in ("website-a@example.invalid", "website-b@example.invalid"):
        flow.capture(runner, page, job, batch, {**observed, "fields": [field(value)]})
    form = runner.store.load()["jobs"][0]["form_state"]
    changes = [entry["fields"][0] for entry in form["value_history"]]
    assert [(entry["before"]["value"], entry["after"]["value"]) for entry in changes] == [
        ("human@example.invalid", "website-a@example.invalid"),
        ("website-a@example.invalid", "website-b@example.invalid"),
    ]
    assert form["choices"]["mail"]["expired"]
    assert not form["choices"]["other"].get("expired")
    assert form["baseline"]["email"]["value"] == "human@example.invalid"


def test_explicit_keep_retires_old_system_value_expectation_in_saved_plan(tmp_path, monkeypatch):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    human = field("human@example.invalid")
    observed = {"fields": [human], "document_token": "document"}
    flow.capture(runner, page, job, batch, observed)
    reference = {"key": "saved"}
    flow.plan(job, observed, [(human, "saved@example.invalid", reference)])
    difference = job["form_state"]["differences"][0]
    state = runner.store.load()
    form = state["jobs"][0]["form_state"]
    form["written_fields"] = {"email": {"value": "saved@example.invalid"}}
    form["choices"] = {
        difference["id"]: {
            **difference,
            "action": "keep",
            "value": human["value"],
            "binding": deepcopy(form["binding"]),
        }
    }
    runner.store.save(state)
    job = state["jobs"][0]
    fills, kept = flow.plan(job, observed, [(human, "saved@example.invalid", reference)])
    flow.save_plan(runner, job, batch)
    assert fills == [] and len(kept) == 1
    assert not runner.store.load()["jobs"][0]["form_state"]["written_fields"]


def test_first_observation_consumes_own_marker_even_when_site_has_already_rewritten_it(
    tmp_path, monkeypatch
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    observed = {"fields": [field("human@example.invalid")], "document_token": "document"}
    flow.capture(runner, page, job, batch, observed)
    state = runner.store.load()
    flow.note_write(
        state["jobs"][0], field("own@example.invalid"), "own@example.invalid", {"key": "saved"}
    )
    runner.store.save(state)
    for value in ("site@example.invalid", "own@example.invalid"):
        flow.capture(runner, page, job, batch, {**observed, "fields": [field(value)]})
    form = runner.store.load()["jobs"][0]["form_state"]
    assert not form["written_fields"]["email"]["readback_pending"]
    assert all(not entry["fields"][0]["confirmed_own_readback"] for entry in form["value_history"])


def test_exact_pending_target_readback_does_not_impersonate_new_user_intervention(
    tmp_path, monkeypatch
):
    runner, page, job, batch = retained_runner(tmp_path, monkeypatch)
    before_field = field("")
    observed = {"fields": [before_field], "document_token": "document"}
    flow.capture(runner, page, job, batch, observed)
    state = runner.store.load()
    form = state["jobs"][0]["form_state"]
    form["parser"]["status"] = "stable"
    state["jobs"][0]["intent"] = {
        "action": "fill",
        "form_protocol": "form-state/v1",
        "field_id": "email",
        "expected_value": "saved@example.invalid",
        "form_binding": deepcopy(form["binding"]),
        "field_shape": digest(
            {
                key: before_field.get(key)
                for key in ("id", "type", "question", "options", "required")
            }
        ),
    }
    runner.store.save(state)
    actual = {**observed, "fields": [field("saved@example.invalid")], "user_activity": {"email": 1}}
    result = flow.capture(runner, page, job, batch, actual)
    assert not result.get("intervention_pending")
    assert runner.store.load()["jobs"][0]["intent"]
    assert result["value_history"][-1]["fields"][0]["after"]["value"] == "saved@example.invalid"
