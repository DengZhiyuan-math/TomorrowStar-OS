"""Candidate acceptance composes real preparation slices over synthetic boundaries."""

import json
import sys
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from test_application_information import answer, tree_bytes, write_library
from test_application_intake import message, page, ready
from test_application_match import model_output, model_runner
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_material_batch_http import control, wait_batch
from test_preparation_entry import post, snapshot
from test_standalone_prism_review import FakePrism

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.application_match import analyze_job
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError
from career_evidence_graph.codex_cli import CodexCLIError


@pytest.fixture(autouse=True)
def synthetic_context(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", sys.executable)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def prepare_career(portal):
    contributions = portal.career / "contributions"
    contributions.mkdir()
    contribution = contributions / "python.md"
    contribution.write_text(
        "# Synthetic Python service\n\n## Scope\nImplemented a Python service.\n\n"
        "## Responsibility attribution\n| Work | Owner |\n| --- | --- |\n"
        "| Implementation | User |\n\n## Boundaries\nNo GPU training claim.\n"
    )
    sources = portal.career / "sources"
    sources.mkdir()
    (sources / "profile.json").write_text('{"name":"Synthetic Person"}')
    return contribution


@contextmanager
def candidate_portal(portal, tmp_path, work, *, library=None):
    """Keep real orchestration, intake, analysis, draft, export receipts and stores."""

    def analyzer(application, sources, directory):
        work["analyses"].append(application["company"])
        output = model_output(sources)
        if application["company"] == "Qualification Synthetic":
            output["requirements"].append(
                {
                    "text": "German B2 required",
                    "importance": "required",
                    "judgment": "unknown",
                    "hard_condition": True,
                    "explanation": "The JD requires German B2; consult the confirmed library.",
                    "source_ids": [],
                    "citations": [],
                    "claim_scope": "unknown",
                }
            )

        def runner(*args, **kwargs):
            if application["company"] == "Model Failure Synthetic":
                raise CodexCLIError("Synthetic known model failure")
            return model_runner(output, work["model_calls"])(*args, **kwargs)

        return analyze_job(application, sources, directory, runner=runner)

    project = tmp_path / "candidate-latex-base"
    project.mkdir(exist_ok=True)
    main = project / "main.tex"
    if not main.exists():
        main.write_text(
            "\\documentclass[a4paper]{article}\n\\begin{document}\n"
            "Synthetic Person\n\\section*{Python service}\n"
            "Implemented a Python service.\n\\end{document}\n"
        )

    def latex_runner(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        application = payload["job"]
        work["drafts"].append(application["company"])
        if callback := work.get("generation"):
            callback(payload, application, config.workspace)
        identity = next(row for row in payload["sources"] if row.get("source_kind") == "identity")
        source = next(row for row in payload["sources"] if row.get("attribution") == "User")
        groups = [
            {
                "title": "Identity",
                "start_line": 1,
                "end_line": 1,
                "source_ids": [identity["source_id"]],
                "latex": "Synthetic Person\n",
                "disposition": "include",
                "reason": "Existing documented identity",
            },
            {
                "title": "Python service",
                "start_line": 2,
                "end_line": 3,
                "source_ids": [source["source_id"]],
                "latex": "\\section*{Python service}\nImplemented a Python service.\n",
                "disposition": "include",
                "reason": "Literal synthetic user contribution",
            },
        ]
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **_kwargs: {"synthetic": True},
        )

    class LatexFixtureStore(ApplicationResumeStore):
        def export_for_draft(self, *args, **kwargs):
            work["exports"].append(kwargs["export_id"])
            if callback := work.get("export_check"):
                callback()
            return super().export_for_draft(*args, **kwargs)

    class Compiler(FakePrism):
        def configuration(self):
            return {"synthetic": "latex-compile-boundary"}

    def resume_factory(applications, catalog, root):
        return LatexFixtureStore(
            applications, catalog, root, model_runner=latex_runner, prism_client=Compiler()
        )

    def intake_factory(applications, root):
        return ApplicationIntakeService(
            applications,
            root,
            reader=work.get("reader", lambda *_a, **_k: pytest.fail("Unexpected Gmail read")),
            fetcher=work.get("fetcher", lambda *_a, **_k: pytest.fail("Unexpected source fetch")),
        )

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "candidate-preparation",
        preparation_only=True,
        flow_analyzer=analyzer,
        flow_resume_factory=resume_factory,
        flow_intake_factory=intake_factory,
        information_library_root=library,
    ) as active:
        assert active.server.worker_service is None
        flow = active.server.application_flow_service
        new_task = flow._new_task

        def bound_task(*args, **kwargs):
            task = new_task(*args, **kwargs)
            # This candidate fixture replays pre-JSON tasks and recorded TeX outputs.
            task.pop("material_contract", None)
            task["latex_base"] = source_snapshot(project, "main.tex")
            return task

        # Template selection is fixture input, before the batch adopts any task.
        flow._new_task = bound_task
        yield active


def new_work(**boundaries):
    return {"analyses": [], "model_calls": [], "drafts": [], "exports": [], **boundaries}


def intake_post(active, action, payload):
    status, _, raw = active.request(
        "POST",
        "/api/recommendations/" + action,
        body=json.dumps(payload).encode(),
        headers=active.write_headers(),
    )
    return status, json.loads(raw)


def create_batch(active, rows, *, kind="application", request="a"):
    status, batch = post(
        active,
        "batch-create",
        {
            "request_id": request * 32,
            "items": [{"kind": kind, "id": row["id"], "revision": row["revision"]} for row in rows],
        },
    )
    assert status == 200, batch
    assert batch["control"] == "paused"
    assert control(active, batch, "resume")[0] == 200
    return batch


def review_draft(active, task):
    flow = active.server.application_flow_service
    task = flow.begin_group_review(task["id"], task["revision"])
    task = flow.capture_group_review(task["id"], task["revision"], task["prism"]["source_revision"])
    draft = flow._group_draft(task)
    for group in draft["review_groups"]:
        task = flow.review_group(
            task["id"],
            task["revision"],
            task["draft_id"],
            task["draft_sha256"],
            group["id"],
            group["review_fingerprint"],
        )
    assert task["factual_review"] == "groups_reviewed"
    return task


def confirm_pdf(active, task):
    status, result = post(
        active,
        "confirm-materials",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "resume_id": task["resume_id"],
            "resume_sha256": task["resume_sha256"],
        },
    )
    assert status == 200, result
    return result


def test_two_gmail_pages_mixed_dispositions_manual_source_retry_and_review_stop(portal, tmp_path):
    prepare_career(portal)
    career_before = tree_bytes(portal.career)
    library = tmp_path / "information-library"
    key, fact = answer("German level", "A2")
    write_library(library, answers={key: fact}, profile={"phone": "+000 synthetic"})
    library_before = tree_bytes(library)
    urls = [f"https://www.linkedin.com/jobs/view/{i}" for i in range(10001, 10005)]
    companies = dict(
        zip(
            urls,
            (
                "Missing Source Synthetic",
                "Qualification Synthetic",
                "Model Failure Synthetic",
                "Unselected Synthetic",
            ),
            strict=True,
        )
    )
    reads, captures = [], []

    def reader(directory, **scope):
        reads.append(scope)
        return {
            "status": "readable",
            "emails": [message("mail-one", urls[:2])]
            if not scope.get("page_token")
            else [message("mail-one", urls[:2]), message("mail-two", [urls[0], *urls[2:]])],
            "provenance": {"next_page_token": "page-two" if len(reads) == 1 else None},
        }

    def fetcher(url):
        captures.append(url)
        if url == urls[0] and captures.count(url) == 1 or url == urls[3]:
            return page(url, "login_required", "unknown") | {
                "capture_id": f"missing-{len(captures)}",
                "job_fields": {},
                "body_text": "Sign in to view the complete job description.",
            }
        return page(url) | {
            "capture_id": f"capture-{len(captures)}",
            "job_fields": {"title": "Engineer", "company": companies[url]},
            "body_text": "Build Python services."
            + (" German B2 required." if url == urls[1] else ""),
        }

    work = new_work(reader=reader, fetcher=fetcher)
    with candidate_portal(portal, tmp_path, work, library=library) as active:
        assert intake_post(active, "refresh", {"max_results": 2, "max_candidates": 4})[0] == 200
        first = ready(active.server.application_intake_service)
        assert first["status"] == "partial"
        assert intake_post(active, "continue", {"revision": first["revision"]})[0] == 200
        intake = ready(active.server.application_intake_service)
        assert intake["status"] == "complete" and intake["progress"]["pages"] == 2
        assert len(reads) == 2 and reads[1]["page_token"] == "page-two"
        assert reads[0]["query"] == reads[1]["query"] and captures == urls
        rows = {row["url"]: row for row in intake["recommendations"]}
        assert len(rows) == 4 and len(rows[urls[0]]["source_messages"]) == 2
        create_batch(active, [rows[url] for url in urls[:3]], kind="recommendation")
        state = wait_batch(
            active, lambda s: s["preparation_batch"]["reason"] == "no_processable_items"
        )
        batch = state["preparation_batch"]
        assert [row["status"] for row in batch["items"]] == ["deferred", "needs_input", "deferred"]
        assert [row["reason"] for row in batch["items"]] == [
            "recommendation_jd_incomplete",
            "flow_qualification_required",
            "match_model_unavailable",
        ]
        qualification = next(
            row
            for row in state["explanations"]
            if row["application_id"] == batch["items"][1]["application_id"]
        )
        assert qualification["qualification"]["status"] == "conflict"
        assert (
            qualification["qualification"]["conditions"][0]["library"]["references"][0]["key"]
            == key
        )
        assert work["drafts"] == work["exports"] == []
        assert rows[urls[3]]["jd_completeness"] != "full"
        missing = next(
            row
            for row in active.server.application_intake_service.snapshot()["recommendations"]
            if row["url"] == urls[0]
        )
        assert (
            intake_post(
                active,
                "acquire",
                {"id": missing["id"], "revision": missing["revision"], "retry": True},
            )[0]
            == 200
        )
        acquired = ready(active.server.application_intake_service)
        assert (
            next(row for row in acquired["recommendations"] if row["id"] == missing["id"])[
                "jd_completeness"
            ]
            == "full"
        )
        assert len(reads) == 2 and captures == [*urls, urls[0]]
        status, retried = post(
            active,
            "batch-retry",
            {
                "batch_id": batch["id"],
                "batch_revision": batch["revision"],
                "item_id": batch["items"][0]["item_id"],
            },
        )
        assert status == 200 and retried["control"] == "paused" and not work["drafts"]
        assert control(active, retried, "resume")[0] == 200
        state = wait_batch(
            active, lambda s: (s.get("active_task") or {}).get("status") == "draft_ready"
        )
        task = state["active_task"]
        review_draft(active, task)
        state = wait_batch(active, lambda s: s["active_task"]["status"] == "materials_ready")
        task = state["active_task"]
        assert state["draft_integrity"]["status"] == state["pdf_integrity"]["status"] == "valid"
        assert active.request("GET", f"/api/flow/drafts/{task['draft_id']}")[0] == 200
        assert active.request("GET", f"/api/flow/resumes/{task['resume_id']}/pdf")[0] == 200
        confirm_pdf(active, task)
        final = snapshot(active)
        assert final["preparation_batch"]["control"] == "paused"
        assert [row["status"] for row in final["preparation_batch"]["items"]] == [
            "waiting_application_record",
            "needs_input",
            "deferred",
        ]
        assert control(active, final["preparation_batch"], "resume")[0] == 409
        assert work["drafts"] == [companies[urls[0]]] and len(work["exports"]) == 1
        assert work["analyses"] == [companies[urls[1]], companies[urls[2]], companies[urls[0]]]
        persisted = active.server.application_intake_service.snapshot()
        assert len(persisted["recommendations"]) == 4
        assert (
            next(row for row in persisted["recommendations"] if row["url"] == urls[3])[
                "existing_application"
            ]
            is None
        )
        chain = json.loads(
            (
                active.server.application_intake_service.root
                / "runs"
                / intake["run_id"]
                / "source-chain.json"
            ).read_text()
        )
        assert len(chain["sources"]) == 5
        assert all(
            job["status"] == "drafting"
            for job in ApplicationStore(portal.applications).list_applications()
        )
        assert active.server.worker_service is None and all(
            task["worker_ref"] is None for task in final["tasks"]
        )
    assert tree_bytes(library) == library_before
    assert tree_bytes(portal.career) == career_before


def test_source_drift_during_generation_retains_old_draft_then_cancel_and_reopen_without_work(
    portal, tmp_path
):
    contribution = prepare_career(portal)
    applications = ApplicationStore(portal.applications)
    jobs = [
        applications.create_application(
            {"company": name, "role_title": "Engineer", "job_description": "Build Python services."}
        )
        for name in ("Drift Synthetic", "Pending Synthetic")
    ]
    entered, release = threading.Event(), threading.Event()
    work = new_work()

    def blocked(draft, application, directory):
        if len(work["drafts"]) == 2:
            entered.set()
            assert release.wait(5)
        return draft | {"generation": "codex"}

    work["generation"] = blocked
    with candidate_portal(portal, tmp_path, work) as active:
        create_batch(active, jobs, request="b")
        state = wait_batch(
            active, lambda s: (s.get("active_task") or {}).get("status") == "draft_ready"
        )
        task = state["active_task"]
        retained_id = task["draft_id"]
        retained_root = active.server.application_resume_store.root / retained_id
        retained_bytes = tree_bytes(retained_root)
        assert active.request("GET", f"/api/flow/drafts/{retained_id}")[0] == 200
        try:
            status, _ = post(
                active,
                "start",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "stage": "resume",
                    "retry": True,
                },
            )
            assert status == 200 and entered.wait(3)
            assert control(active, snapshot(active)["preparation_batch"], "pause")[0] == 200
            contribution.write_text(
                contribution.read_text().replace(
                    "Implemented a Python service.",
                    "Implemented a Python service with corrected responsibility scope.",
                )
            )
            changed_career = tree_bytes(portal.career)
            release.set()
            state = wait_batch(
                active,
                lambda s: (
                    s["active_task"]["stages"]["resume"].get("error_code") == "resume_inputs_stale"
                ),
            )
            task = state["active_task"]
            # The drifted generation fails; the completed analysis stays current (APP-04).
            assert task["status"] == "failed" and state["active_explanation"]["fresh"] is True
            assert task["stages"]["resume"]["error_code"] == "resume_inputs_stale"
            assert task["draft_id"] is None and task["resume_id"] is None
            assert len([row for row in task["artifacts"] if row["stage"] == "resume"]) == 1
            assert tree_bytes(retained_root) == retained_bytes
            assert active.request("GET", f"/api/flow/drafts/{retained_id}")[0] == 200
            status, failure = post(
                active,
                "begin-group-review",
                {"task_id": task["id"], "task_revision": task["revision"]},
            )
            # Nothing to review: the failed attempt left no draft.
            assert status == 409 and failure["error"] == "flow_group_review_blocked"
            batch = state["preparation_batch"]
            assert batch["items"][0]["status"] == "deferred"
            assert batch["items"][0]["reason"] == "resume_inputs_stale"
            assert batch["control"] == "paused" and batch["items"][1]["status"] == "pending"
            assert control(active, batch, "cancel")[0] == 200
            cancelled = snapshot(active)
            assert cancelled["preparation_batch"]["control"] == "cancelled"
            assert cancelled["preparation_batch"]["items"][1]["status"] == "cancelled"
            before_work = {
                key: list(work[key]) for key in ("analyses", "model_calls", "drafts", "exports")
            }
            assert before_work["drafts"] == ["Drift Synthetic", "Drift Synthetic"]
            assert before_work["exports"] == []
        finally:
            release.set()
    with candidate_portal(portal, tmp_path, work) as reopened:
        restored = snapshot(reopened)
        assert restored["runtime"]["session_id"] != cancelled["runtime"]["session_id"]
        assert restored["preparation_batch"]["control"] == "cancelled"
        assert restored["preparation_batch"]["items"][1]["status"] == "cancelled"
        assert len(restored["tasks"]) == 1
        assert reopened.request("GET", f"/api/flow/drafts/{retained_id}")[0] == 200
        assert tree_bytes(retained_root) == retained_bytes
        assert {key: work[key] for key in before_work} == before_work
        assert tree_bytes(portal.career) == changed_career
        assert all(job["status"] == "drafting" for job in applications.list_applications())
        assert reopened.server.worker_service is None


def test_known_pdf_failure_continues_unknown_publish_stops_and_receipt_only_recheck_preserves_queue(
    portal, tmp_path
):
    prepare_career(portal)
    career_before = tree_bytes(portal.career)
    applications = ApplicationStore(portal.applications)
    jobs = [
        applications.create_application(
            {"company": name, "role_title": "Engineer", "job_description": "Build Python services."}
        )
        for name in ("Known PDF Synthetic", "Unknown PDF Synthetic", "Pending PDF Synthetic")
    ]
    work = new_work()

    def export_check():
        if len(work["exports"]) == 1:
            raise PortalDataError("resume_export_failed", "Synthetic known renderer failure", 503)

    work["export_check"] = export_check
    with candidate_portal(portal, tmp_path, work) as active:
        store = active.server.application_resume_store
        export, reconcile = store.export_for_draft, store.reconcile_export
        reconciliations = []

        def unknown_publish(*args, **kwargs):
            export(*args, **kwargs)
            raise PortalDataError(
                "resume_export_needs_recheck", "Synthetic lost committed publication receipt", 409
            )

        def read_receipt(*args, **kwargs):
            reconciliations.append(args[0])
            return reconcile(*args, **kwargs)

        store.export_for_draft, store.reconcile_export = unknown_publish, read_receipt
        create_batch(active, jobs, request="c")
        state = wait_batch(
            active, lambda s: (s.get("active_task") or {}).get("status") == "draft_ready"
        )
        first = state["active_task"]
        review_draft(active, first)
        state = wait_batch(
            active,
            lambda s: (
                (s.get("active_task") or {}).get("application_id") == jobs[1]["id"]
                and s["active_task"]["status"] == "draft_ready"
            ),
        )
        first = next(task for task in state["tasks"] if task["id"] == first["id"])
        assert first["status"] == "export_failed" and first["factual_review"] == "groups_reviewed"
        assert state["preparation_batch"]["items"][0]["status"] == "deferred"
        assert state["preparation_batch"]["items"][0]["reason"] == "resume_export_failed"
        first_draft = store.root / first["draft_id"]
        first_before = tree_bytes(first_draft)
        second = state["active_task"]
        review_draft(active, second)
        state = wait_batch(active, lambda s: s["active_task"]["status"] == "needs_recheck")
        second = state["active_task"]
        batch = state["preparation_batch"]
        assert batch["control"] == "needs_recheck" and batch["items"][2]["status"] == "pending"
        assert work["analyses"] == ["Known PDF Synthetic", "Unknown PDF Synthetic"]
        assert work["drafts"] == work["analyses"] and len(work["exports"]) == 2
        receipt_id = second["stages"]["export"]["attempt_id"]
        export_root = store.root / receipt_id
        export_before = tree_bytes(export_root)
        assert json.loads((export_root / "export.json").read_text())["status"] == "complete"
        assert control(active, batch, "cancel")[0] == 409
        assert (
            post(
                active,
                "batch-retry",
                {
                    "batch_id": batch["id"],
                    "batch_revision": batch["revision"],
                    "item_id": batch["items"][0]["item_id"],
                },
            )[0]
            == 409
        )
        counts = {key: len(work[key]) for key in ("analyses", "model_calls", "drafts", "exports")}
        status, verified = post(
            active, "recheck-export", {"task_id": second["id"], "task_revision": second["revision"]}
        )
        assert status == 200 and verified["status"] == "materials_ready"
        assert verified["export_recheck"]["status"] == "complete" and reconciliations == [
            receipt_id
        ]
        assert {key: len(work[key]) for key in counts} == counts
        assert tree_bytes(export_root) == export_before and tree_bytes(first_draft) == first_before
        assert active.request("GET", f"/api/flow/resumes/{receipt_id}/pdf")[0] == 200
        assert snapshot(active)["pdf_integrity"]["status"] == "valid"
        confirm_pdf(active, verified)
        final = snapshot(active)
        assert final["preparation_batch"]["control"] == "paused"
        assert [row["status"] for row in final["preparation_batch"]["items"]] == [
            "deferred",
            "waiting_application_record",
            "pending",
        ]
        assert control(active, final["preparation_batch"], "resume")[0] == 409
        assert len(final["tasks"]) == 2 and all(
            task["worker_ref"] is None for task in final["tasks"]
        )
        assert {key: len(work[key]) for key in counts} == counts
        assert all(job["status"] == "drafting" for job in applications.list_applications())
        assert tree_bytes(portal.career) == career_before
