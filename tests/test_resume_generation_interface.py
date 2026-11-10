"""Resume owns author execution and receipt-only recovery of saved handoffs."""

import json
import threading
from copy import deepcopy

import pytest
from test_application_flow import wait_for
from test_application_resume_author import author_output, response
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_flow_combination import start_json_writing

from career_evidence_graph.career_portal_data import PortalDataError


def test_reconcile_generation_without_receipts_never_dispatches(json_flow):
    case = json_flow
    task = start_json_writing(case)
    handoff = deepcopy(task["experience_handoff"])

    def forbidden(*args, **kwargs):
        pytest.fail("Receipt-only recovery must not dispatch a model")

    case.store.model_runner = forbidden
    with pytest.raises(PortalDataError) as stopped:
        case.store.reconcile_generation(handoff)
    assert stopped.value.code == "resume_author_needs_recheck"
    assert stopped.value.experience_handoff == handoff
    stopped.value.experience_handoff["id"] = "changed"
    assert task["experience_handoff"] == handoff


@pytest.mark.parametrize("json_flow", [{"automatic_resume_author": True}], indirect=True)
def test_default_flow_dispatches_authors_through_resume_owner(json_flow, monkeypatch):
    case = json_flow
    material_runner = case.store.model_runner
    calls = []

    def runner(config, prompt, **kwargs):
        if "automatic-authors" in config.workspace.parts:
            return response(author_output(json.loads(prompt.split("\n", 1)[1])))
        return material_runner(config, prompt, **kwargs)

    original = case.store.execute_generation

    def execute(handoff, *, admit_call=None):
        calls.append(handoff["id"])
        assert callable(admit_call) and admit_call() is True
        return original(handoff, admit_call=admit_call)

    case.store.model_runner = runner
    monkeypatch.setattr(case.store, "execute_generation", execute)
    task = case.flow.create(case.job["id"], case.job["revision"])
    case.flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "analysis_ready")
    task = case.flow.prepare_automatic_materials(
        task["id"], task["revision"], project_root=str(case.project), main="main.tex"
    )
    case.flow.start(task["id"], task["revision"], "resume")
    done = wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")
    assert len(calls) == 1
    assert case.store.draft(done["draft_id"])["generation_contract"] == "content-writing/v1"


def test_generation_without_answer_resends_through_execute_never_reconcile(json_flow):
    case = json_flow
    task = start_json_writing(case)
    handoff = task["experience_handoff"]
    calls, lost = [], []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request["role"])
        if request["role"].startswith("experience-") and not lost:
            lost.append(request["role"])
            raise TimeoutError("Synthetic lost author response")
        return response(author_output(request))

    case.store.model_runner = runner
    with pytest.raises(PortalDataError) as unknown:
        case.store.execute_generation(handoff)
    assert unknown.value.code == "resume_author_no_answer"
    before = list(calls)
    with pytest.raises(PortalDataError) as retained:
        case.store.reconcile_generation(handoff)
    assert retained.value.code == "resume_author_needs_recheck"
    assert retained.value.experience_handoff == handoff
    assert calls == before
    result = case.store.execute_generation(handoff)
    assert result["generation_contract"] == "content-writing/v1"
    assert calls[len(before)] == lost[0] and "plan" not in calls[len(before) :]


def test_cancelling_flow_stops_subsequent_author_calls_and_preserves_completed_plan(json_flow):
    case = json_flow
    task = start_json_writing(case)
    entered, release = threading.Event(), threading.Event()
    calls, errors = [], []

    def runner(config, prompt, **kwargs):
        request = json.loads(prompt.split("\n", 1)[1])
        calls.append(request["role"])
        entered.set()
        assert release.wait(5)
        return response(author_output(request))

    def execute():
        try:
            case.store.execute_generation(
                task["experience_handoff"],
                admit_call=lambda: case.flow.resume_call_allowed(task),
            )
        except PortalDataError as error:
            errors.append(error.code)

    case.store.model_runner = runner
    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5)
        current = case.flow.task_snapshot(task["id"])
        case.flow.cancel_preparation(task["id"], current["revision"])
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        assert calls == ["plan"]
        assert errors == ["resume_author_paused"]
        assert case.flow.task_snapshot(task["id"])["status"] == "cancelled"
        with pytest.raises(PortalDataError) as reconcile:
            case.store.reconcile_generation(task["experience_handoff"])
        assert reconcile.value.code == "resume_author_needs_recheck"
        assert calls == ["plan"]
    finally:
        release.set()
        thread.join(5)


@pytest.mark.parametrize("json_flow", [{"automatic_resume_author": True}], indirect=True)
def test_default_flow_reconciles_saved_adoption_without_another_author(json_flow, monkeypatch):
    from career_evidence_graph import application_experience_latex as generation

    case = json_flow
    material_runner = case.store.model_runner
    calls, reconciled, lost = [], [], []

    def runner(config, prompt, **kwargs):
        if "automatic-authors" in config.workspace.parts:
            request = json.loads(prompt.split("\n", 1)[1])
            calls.append(request["role"])
            return response(author_output(request))
        return material_runner(config, prompt, **kwargs)

    original_adopt = generation.adopt_generation
    original_reconcile = case.store.reconcile_generation

    def lose_once(store, identifier):
        result = original_adopt(store, identifier)
        if not lost:
            lost.append(identifier)
            raise OSError("Synthetic adoption reply lost after save")
        return result

    def reconcile(handoff):
        reconciled.append(handoff["id"])
        return original_reconcile(handoff)

    case.store.model_runner = runner
    monkeypatch.setattr(generation, "adopt_generation", lose_once)
    monkeypatch.setattr(case.store, "reconcile_generation", reconcile)
    task = case.flow.create(case.job["id"], case.job["revision"])
    case.flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "analysis_ready")
    task = case.flow.prepare_automatic_materials(
        task["id"], task["revision"], project_root=str(case.project), main="main.tex"
    )
    case.flow.start(task["id"], task["revision"], "resume")
    unknown = wait_for(
        case.flow, task["id"], lambda row: row["stages"]["resume"]["status"] == "needs_recheck"
    )
    before = list(calls)
    case.flow.recheck_resume_author(task["id"], unknown["revision"])
    done = wait_for(case.flow, task["id"], lambda row: row["status"] == "draft_ready")
    assert calls == before
    assert reconciled == lost == [done["draft_id"]]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("application_id", "f" * 32),
        ("analysis_binding", {"analysis_id": "f" * 32}),
        ("generation_contract", "fixed-writing/v1"),
        ("fixed_inputs_revision", "f" * 64),
        ("resume_configuration_revision", "f" * 64),
    ],
)
def test_handoff_fixed_reference_mismatch_stops_before_any_author(json_flow, field, value):
    case = json_flow
    task = start_json_writing(case)
    handoff = deepcopy(task["experience_handoff"])
    handoff[field] = value
    calls = []
    case.store.model_runner = lambda *args, **kwargs: calls.append("unexpected")
    with pytest.raises(PortalDataError) as rejected:
        case.store.execute_generation(handoff)
    assert rejected.value.code == "resume_generation_reference_mismatch"
    assert calls == []


def test_mutable_handoff_snapshot_cannot_fabricate_saved_author_results(json_flow):
    case = json_flow
    task = start_json_writing(case)
    handoff = deepcopy(task["experience_handoff"])
    handoff.update(status="adopted", adopted_draft={"id": handoff["id"]})
    calls = []
    case.store.model_runner = lambda *args, **kwargs: calls.append("unexpected")
    with pytest.raises(PortalDataError) as unresolved:
        case.store.reconcile_generation(handoff)
    assert unresolved.value.code == "resume_author_needs_recheck"
    assert calls == []
