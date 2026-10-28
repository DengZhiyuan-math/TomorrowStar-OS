"""Known material reconnection preserves originals and never replays external work."""

from copy import deepcopy

import pytest
from test_application_experience_latex import (
    configure,
    prepare,
    select_supporting_sources,
    submit,
)
from test_application_experience_latex import (
    retained_source_selection as retained_source_selection,
)
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_experience_latex import FEEDBACK_KEY, read_completed
from career_evidence_graph.application_flow import (
    ApplicationFlowService,
    analysis_input_binding,
    retained_configuration_inputs,
)
from career_evidence_graph.application_prism import PrismClient
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def completed(retained_source_selection, tmp_path, monkeypatch, request):
    data, retained, state, _, accepted = retained_source_selection
    store, job, _, analysis, calls, _, _, inputs = data
    if getattr(request, "param", None) == "feedback":
        _, raw = generation._load(store, state["id"])
        new_request = deepcopy(raw["request"])
        new_request["task_inputs"][FEEDBACK_KEY] = "a" * 64
        state = generation.prepare_generation(store, job["id"], job["revision"], **new_request)
        state = generation.configure_generation(
            store,
            state["id"],
            groups=raw["groups"],
            experiences=[
                {key: value for key, value in row.items() if key != "input_revision"}
                for row in raw["experiences"]
            ],
        )
        retained_source_selection = (
            data,
            retained,
            state,
            generation.writer_context(store, state["id"], "selected-project"),
            accepted,
        )
    select_supporting_sources(retained_source_selection, [accepted[0]])
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="independent-reviewer",
        passed=True,
        issues=[],
    )
    draft = generation.adopt_generation(store, state["id"])
    yield from _completed_case(data, retained, state, draft, tmp_path, monkeypatch)


@pytest.fixture
def initial_completed(full_latex, tmp_path, monkeypatch, request):
    data = list(full_latex)
    if getattr(request, "param", None) == "feedback":
        data[7] = {**data[7], FEEDBACK_KEY: "a" * 64}
    state = configure(data, prepare(data))
    for index in range(6):
        submit(full_latex, state, index)
    store = full_latex[0]
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="independent-reviewer",
        passed=True,
        issues=[],
    )
    draft = generation.adopt_generation(store, state["id"])
    yield from _completed_case(full_latex, None, state, draft, tmp_path, monkeypatch)


def _completed_case(data, retained, state, draft, tmp_path, monkeypatch):
    store, job, _, analysis, calls, _, _, inputs = data
    exported = {
        **draft,
        "kind": "pdf",
        "id": "e" * 32,
        "draft_id": draft["id"],
        "pdf_sha256": "f" * 64,
        "automatic_materials": True,
        "export_configuration_revision": digest(PrismClient().configuration()),
    }
    reads = []
    monkeypatch.setattr(
        store, "read_export", lambda identifier: reads.append(identifier) or deepcopy(exported)
    )
    flow = ApplicationFlowService(
        store.applications,
        tmp_path / "reconnected-flow",
        preparation_only=True,
        input_provider=lambda _: {"application_revision": job["revision"], "inputs": inputs},
        callbacks={
            "existing_experience_materials": lambda task, gid, eid: read_completed(
                store, task, gid, eid
            ),
        },
    )
    task = flow.create(job["id"], job["revision"])
    with store.applications.write_lock():
        saved = flow._load()
        task = flow._task(saved, task["id"])
        task.update(status="analysis_ready", analysis_id=analysis["id"])
        task["stages"]["analysis"] = {"status": "complete", "artifact_id": analysis["id"]}
        task["artifacts"] = [
            *([{"stage": "resume", "adopted": True, "result": retained}] if retained else []),
            {"stage": "analysis", "adopted": True, "result": deepcopy(analysis)},
        ]
        flow._save(saved)
        task = deepcopy(task)
    calls.clear()
    yield flow, task, state["id"], exported, store, calls, reads
    flow.close()


def test_attach_completed_materials_is_atomic_preserves_history_and_is_idempotent(completed):
    flow, original, gid, exported, _, calls, reads = completed
    result = flow.request(
        "attach-experience-materials",
        {
            "task_id": original["id"],
            "task_revision": original["revision"],
            "generation_id": gid,
            "export_id": exported["id"],
        },
    )
    assert result["id"] == original["id"]
    assert result["status"] == "materials_ready"
    assert result["resume_id"] == exported["id"]
    assert result["artifacts"][:2] == original["artifacts"]
    assert result["material_reconnections"][0]["previous"]["stages"] == original["stages"]
    assert result["material_binding"]["human_reviewed"] is False
    assert result["draft_review"] is None
    before = flow.path.read_bytes()
    assert (
        flow.attach_experience_materials(original["id"], original["revision"], gid, exported["id"])
        == result
    )
    assert flow.path.read_bytes() == before
    flow._fresh(result)
    assert calls == []
    assert reads == [exported["id"], exported["id"]]


@pytest.mark.parametrize("completed", ["feedback"], indirect=True)
def test_attach_retains_only_proven_material_feedback_and_remains_fresh(completed):
    flow, original, gid, exported, _, calls, _ = completed
    result = flow.attach_experience_materials(
        original["id"], original["revision"], gid, exported["id"]
    )
    assert FEEDBACK_KEY not in original["inputs"]
    assert result["inputs"][FEEDBACK_KEY] == "a" * 64
    assert result["input_epoch"] == original["input_epoch"] + 1
    flow._fresh(result)
    assert (
        flow.attach_experience_materials(original["id"], original["revision"], gid, exported["id"])
        == result
    )
    assert calls == []


@pytest.mark.parametrize(
    "change",
    [
        "application",
        "analysis",
        "inputs",
        "lineage",
        "pdf_hash_binding",
        "config",
        "manual",
        "final_manual",
    ],
)
def test_invalid_existing_materials_leave_flow_unchanged(completed, change):
    flow, original, gid, exported, store, calls, _ = completed
    if change == "pdf_hash_binding":
        exported["draft_sha256"] = "0" * 64
    elif change == "config":
        exported["export_configuration_revision"] = "0" * 64
    elif change in {"manual", "final_manual"}:
        prior = original["artifacts"][0]["result"] if change == "manual" else exported
        checkpoint = prior["source_checkpoint"]
        from pathlib import Path

        path = Path(checkpoint["project_root"]) / checkpoint["main"]
        path.write_text(path.read_text() + "% new human edit\n")
    else:
        with store.applications.write_lock():
            saved = flow._load()
            task = flow._task(saved, original["id"])
            if change == "application":
                task["application_id"] = "wrong-application"
            elif change == "analysis":
                task["analysis_id"] = "different-analysis"
            elif change == "inputs":
                task["inputs"]["unexpected"] = "changed"
            else:
                task["artifacts"][0]["result"]["draft_sha256"] = "0" * 64
            flow._save(saved)
            original = deepcopy(task)
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.attach_experience_materials(original["id"], original["revision"], gid, exported["id"])
    assert flow.path.read_bytes() == before
    assert calls == []


@pytest.mark.parametrize(
    "unknown",
    ["running", "queued", "needs_recheck", "worker", "group", "update", "binding", "codex"],
)
def test_attach_refuses_unresolved_operations(completed, unknown):
    flow, original, gid, exported, store, calls, reads = completed
    with store.applications.write_lock():
        saved = flow._load()
        task = flow._task(saved, original["id"])
        if unknown == "worker":
            task["worker_preparation"] = {"status": "pending"}
        elif unknown == "group":
            task["group_read"] = {"status": "needs_recheck"}
        elif unknown == "update":
            task["material_update"] = {"status": "preparing"}
        elif unknown == "codex":
            task["codex_handoff_ref"] = {"task_id": "existing-executor"}
        elif unknown == "binding":
            task["material_binding_error"] = "unknown_operation"
        else:
            task["stages"]["resume"]["status"] = unknown
        flow._save(saved)
        original = deepcopy(task)
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.attach_experience_materials(original["id"], original["revision"], gid, exported["id"])
    assert flow.path.read_bytes() == before
    assert reads == calls == []


def test_presentation_feedback_requires_a_matching_completed_reconnection_receipt():
    from career_evidence_graph.application_worker import digest

    task = {"inputs": {"facts": "same", FEEDBACK_KEY: "a" * 64}, "stages": {}}
    assert FEEDBACK_KEY not in retained_configuration_inputs(task, {"facts": "same"})
    task.update(
        resume_id="export-id",
        material_reconnections=[
            {
                "generation_id": "generation-id",
                "export_id": "export-id",
                "input_revision": digest(task["inputs"]),
                FEEDBACK_KEY: "a" * 64,
            }
        ],
    )
    assert retained_configuration_inputs(task, {"facts": "same"}) == task["inputs"]
    assert analysis_input_binding(task["inputs"]) == {"facts": "same"}
    task["material_reconnections"][0][FEEDBACK_KEY] = "b" * 64
    assert FEEDBACK_KEY not in retained_configuration_inputs(task, {"facts": "same"})


@pytest.mark.parametrize("initial_completed", [None, "feedback"], indirect=True)
def test_initial_material_attachment_survives_retry_and_reopen(initial_completed):
    flow, original, gid, exported, _, calls, reads = initial_completed
    result = flow.attach_experience_materials(
        original["id"], original["revision"], gid, exported["id"]
    )
    receipt = result["material_reconnections"][0]
    assert receipt["lineage"] == "initial_generation"
    assert receipt["previous"].get("draft_id") is None
    assert result["artifacts"][:1] == original["artifacts"]
    before = flow.path.read_bytes()
    flow.close()
    reopened = ApplicationFlowService(
        flow.applications,
        flow.root,
        preparation_only=True,
        input_provider=flow.input_provider,
        callbacks=flow.callbacks,
    )
    try:
        assert (
            reopened.attach_experience_materials(
                original["id"], original["revision"], gid, exported["id"]
            )
            == result
        )
        assert flow.path.read_bytes() == before
    finally:
        reopened.close()
    assert calls == []
    assert reads == [exported["id"], exported["id"]]


@pytest.mark.parametrize("change", ["draft", "artifact", "manual", "base", "inputs", "source"])
def test_initial_attachment_preserves_conflicting_current_work(initial_completed, change):
    flow, original, gid, exported, store, calls, _ = initial_completed
    with store.applications.write_lock():
        state = flow._load()
        task = flow._task(state, original["id"])
        if change == "draft":
            task["draft_id"] = "another-draft"
        elif change == "artifact":
            task["artifacts"].append(
                {
                    "stage": "resume",
                    "adopted": True,
                    "result": {"kind": "draft", "origin": "existing_latex", "id": "human"},
                }
            )
        elif change == "manual":
            task["manual_source"] = {"source_revision": "human-edit"}
        elif change == "base":
            task["latex_base"] = {"project_root": "another-base"}
        elif change == "inputs":
            task["inputs"]["changed"] = True
        else:
            from pathlib import Path

            checkpoint = exported["source_checkpoint"]
            path = Path(checkpoint["project_root"]) / checkpoint["main"]
            path.write_text(path.read_text() + "% new human edit\n")
        flow._save(state)
        original = deepcopy(task)
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.attach_experience_materials(original["id"], original["revision"], gid, exported["id"])
    assert flow.path.read_bytes() == before
    assert calls == []


def test_initial_attachment_retry_preserves_new_manual_source(initial_completed):
    from pathlib import Path

    flow, original, gid, exported, _, calls, _ = initial_completed
    result = flow.attach_experience_materials(
        original["id"], original["revision"], gid, exported["id"]
    )
    checkpoint = exported["source_checkpoint"]
    path = Path(checkpoint["project_root"]) / checkpoint["main"]
    path.write_text(path.read_text() + "% human edit after attachment\n")
    before = flow.path.read_bytes()
    with pytest.raises(PortalDataError):
        flow.attach_experience_materials(result["id"], result["revision"], gid, exported["id"])
    assert flow.path.read_bytes() == before
    assert path.read_text().endswith("% human edit after attachment\n")
    assert calls == []


def test_completed_content_retains_account_context_across_local_credential_refresh():
    task = {
        "inputs": {"account_context_revision": "original-login-metadata", "jd_revision": "same"},
        "stages": {"analysis": {"status": "complete"}, "resume": {"status": "complete"}},
    }
    current = {"account_context_revision": "refreshed-login-metadata", "jd_revision": "same"}
    assert retained_configuration_inputs(task, current) == task["inputs"]
    # An actual factual change must still invalidate the completed content.
    changed = {**current, "jd_revision": "changed"}
    assert retained_configuration_inputs(task, changed) == changed
    pending = {**task, "stages": {"analysis": {"status": "pending"}}}
    assert retained_configuration_inputs(pending, current) == current
