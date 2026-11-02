"""Complete grouped review binds one current PDF without inventing human acceptance."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_full_latex_flow import latex_flow as latex_flow
from test_full_latex_generation import full_latex as full_latex
from test_group_review_flow import act, reviewed

from career_evidence_graph.application_input_binding import configuration_revision
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def configure(service):
    service.callbacks["verify_draft"] = lambda task: None
    service.callbacks["prism_export_configuration"] = lambda: "configuration"
    service.callbacks["group_state"] = lambda task: {
        "status": "ready",
        "pending_attempt_id": None,
        "live_source_revision": task["prism"]["source_revision"],
    }
    service.callbacks["verify_materials"] = lambda task: None

    def export(task):
        review = service._reviewed_groups(task)
        return {
            "id": task["stages"]["export"]["attempt_id"],
            "kind": "pdf",
            "draft_id": task["draft_id"],
            "draft_sha256": task["draft_sha256"],
            "pdf_sha256": "f" * 64,
            "export_configuration_revision": "configuration",
            "group_review": review,
        }

    service.callbacks["export"] = export


def test_reviewed_groups_bind_pdf_then_separate_material_confirmation(latex_flow):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(
        service,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "export_failed", "needs_recheck"},
    )
    assert task["status"] == "materials_ready"
    assert task["materials_confirmed"] is True
    assert task["material_binding"]["actor"] == "system"
    assert task["material_binding"]["human_reviewed"] is False
    assert not task.get("material_reviews")
    assert task["factual_review"] == "groups_reviewed"
    result = task["artifacts"][-1]["result"]
    assert result["group_review"]["receipts"] == task["group_reviews"]
    confirmed = service.confirm_materials(
        task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
    )
    assert confirmed["status"] == "materials_ready" and confirmed["materials_confirmed"]
    assert confirmed["worker_ref"] is None
    with pytest.raises(PortalDataError):
        service.prepare_worker(confirmed["id"], confirmed["revision"], "CH", True)


def test_automatic_material_verification_failure_retains_pdf_for_read_only_recheck(latex_flow):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    exports = []
    original = service.callbacks["export"]

    def export(request):
        exports.append(request["stages"]["export"]["attempt_id"])
        return original(request)

    def damaged(_):
        raise PortalDataError("flow_materials_changed", "Synthetic changed PDF", 409)

    service.callbacks.update(export=export, verify_materials=damaged)
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
    assert task["resume_id"] == exports[0]
    assert task["stages"]["export"]["status"] == "needs_recheck"
    assert not task["materials_confirmed"] and not task.get("material_binding")
    assert not task.get("material_reviews") and not task["worker_ref"]
    prior = deepcopy(task["artifacts"])
    service.callbacks["reconcile_export"] = lambda request: deepcopy(prior[-1]["result"])
    # The original receipt is still not authority to skip byte verification.
    pending = service.recheck_export(task["id"], task["revision"])
    assert pending["status"] == "needs_recheck" and not pending["materials_confirmed"]
    service.callbacks["verify_materials"] = lambda request: None
    rebound = service.recheck_export(pending["id"], pending["revision"])
    assert rebound["status"] == "materials_ready" and rebound["materials_confirmed"]
    assert rebound["material_binding"]["pdf_sha256"] == task["resume_sha256"]
    assert rebound["material_binding"]["human_reviewed"] is False
    assert not rebound.get("material_reviews") and exports == [task["resume_id"]]
    assert rebound["artifacts"][: len(prior)] == prior


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "preview",
        "source",
        "input",
        "actor",
        "fingerprint",
        "mapping",
        "pending",
        "draft",
    ],
)
def test_every_group_receipt_and_current_source_are_required(latex_flow, change):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    with service.applications.write_lock():
        state = service._load()
        saved = service._task(state, task["id"])
        if change == "missing":
            saved["group_reviews"].pop()
        elif change == "duplicate":
            saved["group_reviews"].append(deepcopy(saved["group_reviews"][0]))
        elif change in {"preview", "source", "input", "actor", "fingerprint", "draft"}:
            key = {
                "preview": "preview_id",
                "source": "source_revision",
                "input": "input_revision",
                "actor": "verified_by",
                "fingerprint": "review_fingerprint",
                "draft": "draft_id",
            }[change]
            saved["group_reviews"][0][key] = "changed"
        elif change == "mapping":
            saved["group_mapping"]["status"] = "mapping_required"
        elif change == "pending":
            saved["group_read"] = {"status": "needs_recheck"}
        service._save(state)
    task = service.snapshot(task["id"])["active_task"]
    with pytest.raises(PortalDataError):
        service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])


def test_sealed_review_receipts_must_match_current_export(latex_flow):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    original = service.callbacks["export"]

    def wrong(task):
        result = original(task)
        result["group_review"]["receipts"][0]["id"] = "wrong"
        result["group_review"]["revision"] = digest(
            {k: v for k, v in result["group_review"].items() if k != "revision"}
        )
        return result

    service.callbacks["export"] = wrong
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(
        service,
        task["id"],
        lambda row: row["status"] in {"materials_ready", "export_failed", "needs_recheck"},
    )
    assert task["status"] != "resume_ready" and not task["materials_confirmed"]


def test_reviewed_group_batch_waits_for_pdf_then_application_record(latex_flow, monkeypatch):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    batch = service.material_batch
    monkeypatch.setattr(batch, "_enqueue", lambda value: None)
    item = {
        "item_id": "one",
        "task_input_epoch": task.get("input_epoch", 0),
        "status": "waiting_draft_review",
    }
    state = {
        "preparation_batch": {
            "active_task_id": task["id"],
            "active_item_id": "one",
            "items": [item],
            "control": "running",
            "events": [],
            "epoch": 0,
        }
    }
    batch.after_task(state, task)
    assert item["status"] == "active"
    broken = deepcopy(task)
    broken["group_reviews"].pop()
    batch.after_task(state, broken)
    assert item["status"] == "waiting_draft_review"
    task["status"] = "resume_ready"
    batch.after_task(state, task)
    assert item["status"] == "waiting_pdf_review"
    task.update(status="materials_ready", materials_confirmed=True)
    batch.after_task(state, task)
    assert item["status"] == "waiting_application_record"
    assert state["preparation_batch"]["control"] == "paused"
    assert state["preparation_batch"]["reason"] == "waiting_application_record"


def test_group_confirmation_repeat_preserves_same_sealed_receipt_and_approval(latex_flow):
    service, task, draft = reviewed(latex_flow)
    configure(service)
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    task = service.confirm_materials(
        task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
    )
    receipt = deepcopy(task["group_reviews"])
    group = draft["review_groups"][0]
    task = act(
        service,
        task,
        "review-group",
        draft_id=task["draft_id"],
        draft_sha256=task["draft_sha256"],
        group_id=group["id"],
        review_fingerprint=group["review_fingerprint"],
    )
    assert task["group_reviews"] == receipt and task["materials_confirmed"]
    assert len(task["material_reviews"]) == 1


def test_unchanged_preview_read_preserves_existing_pdf_confirmation(latex_flow):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    confirmed = service.confirm_materials(
        task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
    )
    draft = deepcopy(service._group_draft(confirmed))
    service.callbacks["group_capture"] = lambda *args, **kwargs: {"draft": draft, "status": "ready"}
    reread = service.capture_group_review(
        confirmed["id"], confirmed["revision"], confirmed["prism"]["source_revision"]
    )
    assert reread["status"] == "materials_ready" and reread["materials_confirmed"]
    assert reread["resume_id"] == confirmed["resume_id"]
    assert reread["material_reviews"] == confirmed["material_reviews"]
    assert reread["group_review_history"] == confirmed["group_review_history"]
    assert reread["artifacts"] == confirmed["artifacts"]


def test_rechecking_unknown_same_preview_settles_review_without_reviving_material_approval(
    latex_flow,
):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    task = service.confirm_materials(
        task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
    )
    draft = deepcopy(service._group_draft(task))

    def unknown(*args, **kwargs):
        raise PortalDataError("prism_review_needs_recheck", "Synthetic unknown read", 409)

    service.callbacks["group_capture"] = unknown
    with pytest.raises(PortalDataError):
        service.capture_group_review(task["id"], task["revision"], task["prism"]["source_revision"])
    pending = service.snapshot(task["id"])["active_task"]
    assert pending["status"] == "needs_recheck" and not pending["materials_confirmed"]
    service.callbacks["group_capture"] = lambda *args, **kwargs: {"draft": draft, "status": "ready"}
    recovered = service.recheck_group_review(pending["id"], pending["revision"])
    assert recovered["status"] == "draft_ready"
    assert recovered["factual_review"] == "groups_reviewed"
    assert not recovered["materials_confirmed"] and recovered["resume_id"] is None
    assert recovered["material_reviews"] == pending["material_reviews"]


def test_unknown_formal_binding_reconciles_existing_receipt_without_reexport(latex_flow):
    service, task, _ = reviewed(latex_flow)
    configure(service)
    original = service.callbacks["export"]
    calls = []
    saved = {}

    def unknown(request):
        calls.append("bind")
        saved.update(original(request))
        raise PortalDataError("resume_export_needs_recheck", "Unknown", 409)

    service.callbacks["export"] = unknown
    service.callbacks["reconcile_export"] = lambda request: deepcopy(saved)
    service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(service, task["id"], lambda row: row["status"] == "needs_recheck")
    assert not task["materials_confirmed"]
    with pytest.raises(PortalDataError):
        service.export_pdf(
            task["id"], task["revision"], task["draft_id"], task["draft_sha256"], retry=True
        )
    task = service.recheck_export(task["id"], task["revision"])
    assert task["status"] == "materials_ready" and task["materials_confirmed"] and calls == ["bind"]


def test_actual_store_flow_new_pdf_never_inherits_old_material_approval(full_latex, tmp_path):
    from pathlib import Path

    from test_full_latex_flow import bind
    from test_full_latex_generation import generate
    from test_group_review_presentation_policy import education_data
    from test_job_explanations import requirement
    from test_standalone_prism_review import FakePrism

    from career_evidence_graph.application_flow import ApplicationFlowService
    from career_evidence_graph.application_prism import PrismClient, source_snapshot
    from career_evidence_graph.resume_presentation import PRESENTATION_POLICY_VERSION

    full_latex = education_data(full_latex)
    store, job, _, analysis, calls, base, _, inputs = full_latex
    initial = generate(full_latex)
    assert initial["presentation_policy"] == PRESENTATION_POLICY_VERSION
    store.group_prism_client = FakePrism()

    def verify_draft(task):
        saved = store.draft(task["draft_id"])
        assert saved["draft_sha256"] == task["draft_sha256"]
        assert saved["task_inputs"] == task["inputs"]
        assert saved["source_checkpoint"] == task["source_checkpoint"]

    service = ApplicationFlowService(
        store.applications,
        tmp_path / "actual-reviewed-flow",
        preparation_only=True,
        callbacks={
            "analysis": lambda task: analysis | {"requirements": [requirement()]},
            "resume": lambda task: initial,
            "prism_source": source_snapshot,
            "group_prepare": lambda task: store.prepare_group_review(
                task["draft_id"], task["draft_sha256"], task_inputs=task["inputs"]
            ),
            "group_capture": lambda task, **kwargs: store.capture_group_review(
                task["draft_id"], task["draft_sha256"], task_inputs=task["inputs"], **kwargs
            ),
            "group_state": lambda task: store.group_review_state(task["draft_id"]),
            "verify_draft": verify_draft,
            "prism_export_configuration": lambda: configuration_revision(
                PrismClient().configuration()
            ),
            "export": lambda task: store.export_for_draft(
                task["draft_id"],
                task["draft_sha256"],
                task_inputs=task["inputs"],
                export_id=task["stages"]["export"]["attempt_id"],
                prism=task["prism"],
                group_reviews=task["group_reviews"],
            ),
        },
    )

    def verify_materials(task):
        saved = store.read_export(task["resume_id"])
        assert saved["pdf_sha256"] == task["resume_sha256"]
        assert saved["draft_id"] == task["draft_id"]
        assert saved["group_review"] == service._reviewed_groups(task)

    service.callbacks["verify_materials"] = verify_materials
    try:
        task = service.create(job["id"], job["revision"], inputs=inputs)
        # Replay a saved full-TeX task with existing group-review receipts.
        with service.applications.write_lock():
            state = service._load()
            service._task(state, task["id"]).pop("material_contract", None)
            service._save(state)
        task = service.snapshot(task["id"])["active_task"]
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = bind(service, task, base)
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] == "draft_ready")
        task = act(service, task, "begin-group-review")
        task = act(
            service,
            task,
            "capture-group-review",
            expected_source_revision=store.group_review_state(task["draft_id"])[
                "live_source_revision"
            ],
        )
        draft = store.draft(task["draft_id"])
        fixed_ids = {
            group["id"]
            for group in draft["review_groups"]
            if group.get("content_policy") == "fixed_education"
        }
        assert len(fixed_ids) == 1
        for group in draft["review_groups"]:
            if group["id"] in fixed_ids:
                continue
            task = act(
                service,
                task,
                "review-group",
                draft_id=task["draft_id"],
                draft_sha256=task["draft_sha256"],
                group_id=group["id"],
                review_fingerprint=group["review_fingerprint"],
            )
        service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
        task = wait_for(
            service,
            task["id"],
            lambda row: row["status"] in {"materials_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task
        first = store.read_export(task["resume_id"])
        assert first["group_review"]["presentation_policy"] == PRESENTATION_POLICY_VERSION
        assert {row["group_id"] for row in first["group_review"]["fixed_education"]} == fixed_ids
        assert not fixed_ids.intersection(row["group_id"] for row in task["group_reviews"])
        assert first["group_review"] == service._reviewed_groups(task)
        assert task["materials_confirmed"]
        assert task["material_binding"]["human_reviewed"] is False
        assert not task.get("material_reviews")
        task = service.confirm_materials(
            task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
        )
        assert task["materials_confirmed"] and len(task["material_reviews"]) == 1
        main = Path(task["prism"]["project_root"]) / "main.tex"
        main.write_text(
            main.read_text().replace(
                "Analyzed strategy; built 1 Python services.",
                "Built 1 Python services; analyzed strategy.",
            )
        )
        task = act(
            service,
            task,
            "capture-group-review",
            expected_source_revision=store.group_review_state(task["draft_id"])[
                "live_source_revision"
            ],
        )
        assert len(task["group_reviews"]) == 6 and not task["materials_confirmed"]
        assert task["resume_id"] is None and task["factual_review"] == "pending"
        draft = store.draft(task["draft_id"])
        changed = next(g for g in draft["review_groups"] if g["title"] == "Project 1")
        task = act(
            service,
            task,
            "review-group",
            draft_id=task["draft_id"],
            draft_sha256=task["draft_sha256"],
            group_id=changed["id"],
            review_fingerprint=changed["review_fingerprint"],
        )
        service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
        task = wait_for(
            service,
            task["id"],
            lambda row: row["status"] in {"materials_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task
        second = store.read_export(task["resume_id"])
        assert second["id"] != first["id"] and second["draft_id"] != first["draft_id"]
        assert second["pdf_sha256"] == first["pdf_sha256"]
        assert task["materials_confirmed"] and len(task["material_reviews"]) == 1
        assert task["material_binding"]["resume_id"] == second["id"]
        assert store.read_export(first["id"]) == first
        task = service.confirm_materials(
            task["id"], task["revision"], task["resume_id"], task["resume_sha256"]
        )
        assert task["materials_confirmed"] and len(task["material_reviews"]) == 2
        assert store.group_prism_client.calls == ["compile", "compile"] and len(calls) == 1
        assert not task["worker_ref"]
    finally:
        service.close()
