"""Synthetic grouped review requires exact source, draft and group versions."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_full_latex_flow import bind, candidate
from test_full_latex_flow import latex_flow as latex_flow
from test_full_latex_generation import full_latex as full_latex
from test_job_explanations import requirement

from career_evidence_graph.career_portal_data import PortalDataError


def generated(latex_flow):
    service, task, project = latex_flow
    task = bind(service, task, project)
    service.callbacks["resume"] = candidate
    service.start(task["id"], task["revision"], "resume")
    task = wait_for(service, task["id"], lambda row: row["status"] == "draft_ready")
    service.callbacks["prism_source"] = lambda root, main: deepcopy(
        task["latex_base"]
        if str(root) == task["latex_base"]["project_root"]
        else task["source_checkpoint"]
    )
    return service, task


def prepared(task):
    result = candidate(task)
    result.update(id="prepared", group_session={"id": "session"}, group_context_revision="context")
    result["review_groups"] = [
        {"id": "one", "review_fingerprint": "1" * 64},
        {"id": "two", "review_fingerprint": "2" * 64},
    ]
    result["verified_unchanged_group_ids"] = []
    return result


def act(service, task, action, **payload):
    return service.request(
        action, dict(task_id=task["id"], task_revision=task["revision"], **payload)
    )


def test_group_confirmation_requires_same_source_preview(latex_flow):
    service, task = generated(latex_flow)
    service.callbacks["group_prepare"] = prepared
    task = act(service, task, "begin-group-review")
    with pytest.raises(PortalDataError):
        act(
            service,
            task,
            "review-group",
            draft_id="prepared",
            draft_sha256="a" * 64,
            group_id="one",
            review_fingerprint="1" * 64,
        )
    result = prepared(task)
    result.update(id="captured", draft_sha256="c" * 64)
    result["group_preview"] = {"id": "preview", "source_revision": task["prism"]["source_revision"]}
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": result,
        "preview": result["group_preview"],
        "status": "ready",
        "mapping_error": None,
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    task = act(
        service,
        task,
        "review-group",
        draft_id=task["draft_id"],
        draft_sha256=task["draft_sha256"],
        group_id="one",
        review_fingerprint="1" * 64,
    )
    assert task["factual_review"] == "pending"
    task = act(
        service,
        task,
        "review-group",
        draft_id=task["draft_id"],
        draft_sha256=task["draft_sha256"],
        group_id="two",
        review_fingerprint="2" * 64,
    )
    assert task["factual_review"] == "groups_reviewed"
    assert task["materials_confirmed"] is False and task["resume_id"] is None
    with pytest.raises(PortalDataError):
        act(service, task, "export-pdf", draft_id="prepared", draft_sha256="a" * 64)


def test_unknown_capture_blocks_changes_and_recheck_does_not_rerun(latex_flow):
    service, task = generated(latex_flow)
    service.callbacks["group_prepare"] = prepared
    task = act(service, task, "begin-group-review")

    def unknown(*args, **kwargs):
        raise PortalDataError("prism_review_needs_recheck", "Unknown", 409)

    service.callbacks["group_capture"] = unknown
    with pytest.raises(PortalDataError):
        act(
            service,
            task,
            "capture-group-review",
            expected_source_revision=task["prism"]["source_revision"],
        )
    task = service.snapshot(task["id"])["active_task"]
    assert task["group_read"]["status"] == "needs_recheck"
    for action, payload in [
        ("cancel", {}),
        ("begin-group-review", {}),
        ("capture-group-review", {"expected_source_revision": task["prism"]["source_revision"]}),
    ]:
        with pytest.raises(PortalDataError):
            act(service, task, action, **payload)
    reconciled = []
    service.callbacks["group_capture"] = lambda *args, **kwargs: (
        reconciled.append(kwargs["reconcile"])
        or {
            "draft": None,
            "preview": None,
            "status": "mapping_required",
            "mapping_error": "mapping",
        }
    )
    task = act(service, task, "recheck-group-review")
    assert reconciled == [True] and task["group_mapping"]["status"] == "mapping_required"


def test_mapping_failure_invalidates_all_receipts(latex_flow):
    service, task = generated(latex_flow)
    service.callbacks["group_prepare"] = prepared
    task = act(service, task, "begin-group-review")
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": None,
        "preview": {"id": "technical"},
        "status": "mapping_required",
        "mapping_error": "Unmapped source",
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    assert task["group_reviews"] == [] and task["factual_review"] == "pending"
    with pytest.raises(PortalDataError):
        act(
            service,
            task,
            "review-group",
            draft_id="prepared",
            draft_sha256="a" * 64,
            group_id="one",
            review_fingerprint="1" * 64,
        )


def reviewed(latex_flow):
    service, task = generated(latex_flow)
    service.callbacks["group_prepare"] = prepared
    task = act(service, task, "begin-group-review")
    result = prepared(task)
    result.update(id="captured", draft_sha256="c" * 64)
    result["group_preview"] = {"id": "preview", "source_revision": task["prism"]["source_revision"]}
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": result,
        "status": "ready",
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    for group in result["review_groups"]:
        task = act(
            service,
            task,
            "review-group",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id=group["id"],
            review_fingerprint=group["review_fingerprint"],
        )
    return service, task, result


def test_only_verified_unchanged_groups_inherit_and_new_pdf_stays_pending(latex_flow):
    service, task, previous = reviewed(latex_flow)
    old_receipts = deepcopy(task["group_reviews"])
    changed = deepcopy(previous)
    changed.update(id="changed", draft_sha256="e" * 64, verified_unchanged_group_ids=["one"])
    changed["review_groups"][1]["review_fingerprint"] = "3" * 64
    changed.pop("group_preview")
    service.callbacks["group_edit"] = lambda *args: changed
    task = act(service, task, "edit-review-group", payload={"group_id": "two"})
    assert [r["group_id"] for r in task["group_reviews"]] == ["one"]
    assert task["group_reviews"][0]["inherited_from"] == {
        "receipt_id": old_receipts[0]["id"],
        "draft_id": old_receipts[0]["draft_id"],
        "draft_sha256": old_receipts[0]["draft_sha256"],
    }
    assert task["group_reviews"][0]["id"] != old_receipts[0]["id"]
    assert old_receipts[0] in task["group_review_history"]
    assert task["factual_review"] == "pending" and task["materials_confirmed"] is False
    assert len(task["group_review_history"]) == 3


@pytest.mark.parametrize("mutation", ["fingerprint", "context", "flag"])
def test_carry_fails_closed_if_equality_or_verification_missing(latex_flow, mutation):
    service, task, previous = reviewed(latex_flow)
    changed = deepcopy(previous)
    changed.update(id="changed", draft_sha256="e" * 64, verified_unchanged_group_ids=["one", "two"])
    if mutation == "fingerprint":
        for group in changed["review_groups"]:
            group["review_fingerprint"] = "f" * 64
    elif mutation == "context":
        changed["group_context_revision"] = "changed"
    else:
        changed["verified_unchanged_group_ids"] = []
    service.callbacks["group_edit"] = lambda *args: changed
    task = act(service, task, "edit-review-group", payload={"group_id": "two"})
    assert not task["group_reviews"] and task["factual_review"] == "pending"


def test_capture_running_is_observable_and_no_application_lock_is_held(latex_flow):
    import threading

    service, task = generated(latex_flow)
    service.callbacks["group_prepare"] = prepared
    task = act(service, task, "begin-group-review")
    entered, release = threading.Event(), threading.Event()

    def capture(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return {"draft": None, "status": "mapping_required"}

    service.callbacks["group_capture"] = capture
    errors = []

    def run():
        try:
            act(
                service,
                task,
                "capture-group-review",
                expected_source_revision=task["prism"]["source_revision"],
            )
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(2)
        current = service.snapshot(task["id"])["active_task"]
        assert current["group_read"]["status"] == "running"
        for operation in ["cancel", "begin-group-review"]:
            with pytest.raises(PortalDataError):
                act(service, current, operation)
        with pytest.raises(PortalDataError):
            service.create(task["application_id"], task["application_revision"], force_new=True)
    finally:
        release.set()
        thread.join(3)
    assert not errors and not thread.is_alive()


def test_restart_retains_unknown_group_attempt_without_callback(latex_flow):
    service, task = generated(latex_flow)
    with service.applications.write_lock():
        state, current = service._checked(task["id"], task["revision"])
        current["group_read"] = {
            "status": "running",
            "attempt_id": "original",
            "expected_source_revision": "x",
        }
        service._save(state)
        service._recover()
    current = service.snapshot(task["id"])["active_task"]
    assert current["group_read"]["status"] == "needs_recheck"
    assert current["group_read"]["attempt_id"] == "original"
    assert current["status"] == "needs_recheck"


def test_known_preflight_source_change_does_not_create_unknown_compile(latex_flow):
    service, task = generated(latex_flow)
    service.callbacks["group_prepare"] = prepared
    task = act(service, task, "begin-group-review")

    def fail(*args, **kwargs):
        raise PortalDataError("prism_source_changed", "Changed before capture", 409)

    service.callbacks["group_capture"] = fail
    with pytest.raises(PortalDataError):
        act(
            service,
            task,
            "capture-group-review",
            expected_source_revision=task["prism"]["source_revision"],
        )
    current = service.snapshot(task["id"])["active_task"]
    assert current["group_read"]["status"] == "failed"
    assert current["status"] == "draft_ready"


@pytest.mark.parametrize("operation", ["group_prepare", "group_edit"])
def test_restart_local_group_copy_preserves_old_draft_without_unknown_compile(
    latex_flow, operation
):
    service, task = generated(latex_flow)
    with service.applications.write_lock():
        state, current = service._checked(task["id"], task["revision"])
        current["group_read"] = {
            "status": "running",
            "attempt_id": "original",
            "operation": operation,
        }
        service._save(state)
        service._recover()
    current = service.snapshot(task["id"])["active_task"]
    assert current["draft_id"] == task["draft_id"]
    assert current["group_read"]["status"] == "failed" and current["status"] == "draft_ready"


def test_changed_live_source_and_wrong_group_fingerprint_cannot_confirm(latex_flow):
    service, task, draft = reviewed(latex_flow)
    with pytest.raises(PortalDataError) as error:
        act(
            service,
            task,
            "review-group",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id="one",
            review_fingerprint="f" * 64,
        )
    assert error.value.code == "flow_group_changed"
    base = deepcopy(task["latex_base"])
    changed = deepcopy(task["source_checkpoint"]) | {"source_revision": "changed"}
    service.callbacks["prism_source"] = lambda root, main: (
        base if str(root) == base["project_root"] else changed
    )
    with pytest.raises(PortalDataError) as error:
        act(
            service,
            task,
            "review-group",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id="one",
            review_fingerprint="1" * 64,
        )
    assert error.value.code == "prism_source_changed"
    assert len(service.snapshot(task["id"])["active_task"]["group_review_history"]) == 2


@pytest.mark.parametrize("git_parent", [False, True])
def test_actual_store_flow_source_edit_reuses_only_unchanged_group_receipts(
    full_latex, tmp_path, git_parent
):
    from pathlib import Path

    from test_full_latex_generation import generate
    from test_standalone_prism_review import FakePrism

    from career_evidence_graph.application_flow import ApplicationFlowService
    from career_evidence_graph.application_prism import source_snapshot

    store, job, _, analysis, calls, base, _, inputs = full_latex
    if git_parent:
        (store.root / ".git").mkdir()
    generated_draft = generate(full_latex)
    service = ApplicationFlowService(
        store.applications,
        tmp_path / "actual-group-flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: analysis | {"requirements": [requirement()]},
            "resume": lambda task: generated_draft,
            "prism_source": source_snapshot,
            "group_prepare": lambda task: store.prepare_group_review(
                task["draft_id"], task["draft_sha256"], task_inputs=task["inputs"]
            ),
            "group_capture": lambda task, **kwargs: store.capture_group_review(
                task["draft_id"], task["draft_sha256"], task_inputs=task["inputs"], **kwargs
            ),
            "export": lambda task: pytest.fail("Export remains blocked"),
        },
    )
    store.group_prism_client = FakePrism()
    try:
        task = service.create(job["id"], job["revision"], inputs=inputs)
        # This fixture restores the retained pre-JSON grouped-review contract.
        with service.applications.write_lock():
            saved = service._load()
            service._task(saved, task["id"]).pop("material_contract", None)
            service._save(saved)
        task = service.snapshot(task["id"])["active_task"]
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = bind(service, task, base)
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "draft_ready")
        task = act(service, task, "begin-group-review")
        assert task["factual_review"] == "pending"
        source = store.group_review_state(task["draft_id"])["live_source_revision"]
        task = act(service, task, "capture-group-review", expected_source_revision=source)
        original = store.draft(task["draft_id"])
        for group in original["review_groups"]:
            task = act(
                service,
                task,
                "review-group",
                draft_id=task["draft_id"],
                draft_sha256=task["draft_sha256"],
                group_id=group["id"],
                review_fingerprint=group["review_fingerprint"],
            )
        assert task["factual_review"] == "groups_reviewed"
        main = Path(task["prism"]["project_root"]) / "main.tex"
        main.write_text(
            main.read_text().replace(
                "Analyzed strategy; built 1 Python services.",
                "Built 1 Python services; analyzed strategy.",
            )
        )
        source = store.group_review_state(task["draft_id"])["live_source_revision"]
        task = act(service, task, "capture-group-review", expected_source_revision=source)
        assert task["factual_review"] == "pending"
        revised = store.draft(task["draft_id"])
        changed = next(group for group in revised["review_groups"] if group["title"] == "Project 1")
        assert len(task["group_reviews"]) == 6
        assert changed["id"] not in {row["group_id"] for row in task["group_reviews"]}
        assert all(row.get("inherited_from") for row in task["group_reviews"])
        task = act(
            service,
            task,
            "review-group",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id=changed["id"],
            review_fingerprint=changed["review_fingerprint"],
        )
        assert task["factual_review"] == "groups_reviewed" and task["materials_confirmed"] is False
        assert store.group_prism_client.calls == ["compile", "compile"] and len(calls) == 1
    finally:
        service.close()


def test_mapping_repair_can_restore_only_verified_old_version_receipts(latex_flow):
    service, task, previous = reviewed(latex_flow)
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": None,
        "status": "mapping_required",
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    assert not task["group_reviews"] and task["factual_review"] == "pending"
    repaired = deepcopy(previous)
    repaired.update(id="repaired", draft_sha256="e" * 64, verified_unchanged_group_ids=["one"])
    repaired["review_groups"][1]["review_fingerprint"] = "3" * 64
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": repaired,
        "status": "ready",
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    assert [row["group_id"] for row in task["group_reviews"]] == ["one"]
    assert task["factual_review"] == "pending"


def test_identical_read_does_not_duplicate_artifacts_or_review_lineage(latex_flow):
    service, task, previous = reviewed(latex_flow)
    original_artifacts = deepcopy(task["artifacts"])
    receipts = deepcopy(task["group_reviews"])
    history = deepcopy(task["group_review_history"])
    previous["verified_unchanged_group_ids"] = ["one", "two"]
    service.callbacks["group_capture"] = lambda *args, **kwargs: {
        "draft": previous,
        "status": "ready",
    }
    task = act(
        service,
        task,
        "capture-group-review",
        expected_source_revision=task["prism"]["source_revision"],
    )
    assert task["artifacts"] == original_artifacts
    assert task["group_reviews"] == receipts and task["group_review_history"] == history
    assert task["factual_review"] == "groups_reviewed"


def test_late_capture_after_other_task_write_is_retained_for_reconciliation(latex_flow):
    service, task = generated(latex_flow)
    service.callbacks["group_prepare"] = prepared
    task = act(service, task, "begin-group-review")

    def capture(request, **kwargs):
        with service.applications.write_lock():
            state, current = service._checked(request["id"], request["revision"])
            current["hard_condition_resolutions"] = [{"reason": "Changed during capture"}]
            service._save(state)
        result = prepared(request)
        result.update(id="late", draft_sha256="e" * 64)
        return {"draft": result, "status": "ready"}

    service.callbacks["group_capture"] = capture
    with pytest.raises(PortalDataError) as error:
        act(
            service,
            task,
            "capture-group-review",
            expected_source_revision=task["prism"]["source_revision"],
        )
    assert error.value.code == "flow_inputs_stale"
    current = service.snapshot(task["id"])["active_task"]
    assert current["draft_id"] == task["draft_id"]
    assert current["group_read"]["status"] == "needs_recheck"
