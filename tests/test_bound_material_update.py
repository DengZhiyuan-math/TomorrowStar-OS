"""Same-job material updates retain the old binding until original-page readback."""

from copy import deepcopy

import pytest
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph.application_information import put_information_answer


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_bound_contact_change_retains_original_current_material_until_commit(complete_portal):
    server, store, original, _calls = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    prepared = flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    previous = deepcopy(worker.store.load())
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        },
    )
    app = store.applications.get_application(original["application_id"])
    updated = flow.request(
        "update-inputs",
        {
            "task_id": prepared["id"],
            "task_revision": prepared["revision"],
            "application_revision": app["revision"],
        },
    )
    assert updated["resume_id"] == original["resume_id"]
    assert updated["draft_id"] == original["draft_id"]
    assert updated["inputs"] == original["inputs"]
    assert updated["material_update"]["inputs"] != original["inputs"]
    assert updated["worker_ref"] == prepared["worker_ref"]
    assert worker.store.load() == previous


@pytest.fixture
def bound_pipeline(full_latex, tmp_path, monkeypatch, request):
    """Real synthetic mail→Flow→strict Worker admission, without a browser process."""
    import hashlib
    import json
    import subprocess
    import time

    from test_application_intake import message, page
    from test_automatic_complete_materials import SyntheticCompiler
    from test_resume_export import PDF_SAMPLE

    from career_evidence_graph import application_match
    from career_evidence_graph._vendor import job_apply_store as helper
    from career_evidence_graph.application_flow import job_input_revision
    from career_evidence_graph.application_intake import ApplicationIntakeService
    from career_evidence_graph.application_pipeline import ApplicationPipeline
    from career_evidence_graph.application_prism import source_snapshot
    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.validation.hashing import record_digest as digest

    store, original, _, analysis, calls, project, output, _ = full_latex
    options = getattr(request, "param", {})
    url = options.get("url", "https://careers.example.test/jobs/synthetic-services")
    store.applications.update_application(
        original["id"],
        {
            "url": url,
            "location": "Zurich, Switzerland",
            **(
                {"job_description": options["job_description"]}
                if "job_description" in options
                else {}
            ),
            **(
                {"application_strategy": options["application_strategy"]}
                if "application_strategy" in options
                else {}
            ),
        },
        original["revision"],
    )
    analysis["requirements"][0].update(
        text="Operate service systems",
        importance="required",
        judgment="supported",
        hard_condition=False,
    )
    root = tmp_path / "bound-flow"
    store.root = root / "resumes"
    store.root.mkdir(parents=True)
    store.prism_client = SyntheticCompiler()
    compile_source = store.prism_client.compile

    def compile_version(binding):
        result = compile_source(binding)
        text = (Path(binding["project_root"]) / binding["main"]).read_bytes()
        return result | {
            "pdf": PDF_SAMPLE.read_bytes().replace(
                b"startxref\n", b"%" + hashlib.sha256(text).hexdigest().encode() + b"\nstartxref\n"
            )
        }

    from pathlib import Path

    store.prism_client.compile = compile_version
    store.pdf_inspector = lambda raw: 1
    subprocess.run(["git", "init", "--quiet", str(store.catalog.root)], check=True)

    def fake_analysis(application, sources, directory, *, information_library=None, **kwargs):
        from career_evidence_graph.application_information import information_context

        directory.mkdir(parents=True)
        result = analysis | {
            "id": directory.name,
            "application_id": application["id"],
            "application_revision": application["revision"],
            "jd_revision": job_input_revision(application),
            "source_snapshot_revision": sources["revision"],
            "information_context_revision": information_context(
                application, information_library or {"status": "unconfigured", "records": []}
            )["revision"],
        }
        (directory / "analysis.json").write_text(json.dumps(result))
        from test_application_match import persist_analysis_inputs

        persist_analysis_inputs(directory, application, sources)
        (directory / "synthetic-material-inputs.json").write_text(
            json.dumps(
                {
                    "schema_version": "synthetic-material-inputs/v1",
                    "analysis_id": result["id"],
                    "application": application,
                    "sources": sources,
                }
            )
        )
        return result

    monkeypatch.setattr(application_match, "analyze_job", fake_analysis)
    monkeypatch.setattr(ApplicationPipeline, "_run", lambda self, _: self._closed.wait())

    def intake_factory(apps, intake_root):
        return ApplicationIntakeService(
            apps,
            intake_root,
            reader=lambda *_a, **_k: {
                "status": "readable",
                "emails": [message(links=["https://www.linkedin.com/jobs/view/424242"])],
                "provenance": {},
            },
            fetcher=lambda target: (
                page(target)
                | {
                    "final_url": url,
                    "redirects": [{"url": target, "status": 302, "location": url}],
                    "body_text": options.get("job_description", "Operate service systems."),
                    "job_fields": {
                        "title": "Service Engineer",
                        "company": "Synthetic",
                        "location": "Zurich, Switzerland",
                    },
                }
            ),
        )

    with create_server(
        store.applications.root,
        store.catalog.root,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        worker_generic=True,
        flow_resume_factory=lambda *_a: store,
        flow_intake_factory=intake_factory,
    ) as server:
        worker, flow, pipeline = (
            server.worker_service,
            server.application_flow_service,
            server.application_pipeline_service,
        )

        def legacy_material_sources(applications, flow_root, job):
            # This fixture saves pre-JSON materials. Its explicit synthetic
            # delivery adapter consumes those saved inputs, not a native P04 brief.
            assert applications.root == store.applications.root
            binding = job["single_binding"]
            directory = flow_root / "analyses" / binding["analysis_id"]
            record = helper.read_json_object(
                directory / "synthetic-material-inputs.json", "synthetic material inputs"
            )
            report = helper.read_json_object(directory / "analysis.json", "synthetic analysis")
            assert record["schema_version"] == "synthetic-material-inputs/v1"
            assert record["analysis_id"] == report["id"] == binding["analysis_id"]
            assert record["application"]["id"] == report["application_id"] == job["application_id"]
            assert (
                job_input_revision(record["application"])
                == report["jd_revision"]
                == binding["job_binding"]
            )
            sources = record["sources"]
            assert sources["revision"] == report["source_snapshot_revision"]
            assert sources["revision"] == digest(
                {key: value for key, value in sources.items() if key != "revision"}
            )
            return record

        monkeypatch.setattr(
            worker.store, "single_material_source_provider", legacy_material_sources
        )
        monkeypatch.setattr(worker, "spawn", lambda: None)
        create = flow.create

        def historical_task(*args, **kwargs):
            # This fixture exercises saved pre-JSON material compatibility.
            # Current jobs keep their content contract and cannot use this path.
            task = create(*args, **kwargs)
            with flow.applications.write_lock():
                state = flow._load()
                saved = flow._task(state, task["id"])
                saved.pop("material_contract", None)
                flow._save(state)
                return deepcopy(saved)

        monkeypatch.setattr(flow, "create", historical_task)
        flow.callbacks["automatic_latex_base"] = lambda _task: source_snapshot(project, "main.tex")
        worker.store.answers.put_answer(
            {"question": "Email", "value": "job@example.invalid", "state": "confirmed", "scope": {}}
        )
        output["groups"][0]["source_ids"].append("answer:" + helper.answer_key("Email", {}))
        output["groups"][0]["latex"] = "Synthetic Person\njob@example.invalid\n"
        pipeline.start(request_id="bound-material-cycle")
        stop_at = options.get("stop_at", "filling")
        for _ in range(300):
            pipeline._tick()
            if pipeline.snapshot()["status"] == stop_at or (
                stop_at == "needs_input"
                and worker.store.load()["jobs"]
                and pipeline.snapshot()["status"] == "filling"
            ):
                break
            time.sleep(0.01)
        assert pipeline.snapshot()["status"] == stop_at or (
            stop_at == "needs_input"
            and worker.store.load()["jobs"]
            and pipeline.snapshot()["status"] == "filling"
        ), pipeline.snapshot()
        current = worker.store.load()
        if current["jobs"]:
            worker.store.check_single(current["jobs"][0], current)
        yield server, store, calls


def test_bound_pipeline_candidate_compiles_without_rewriting_manual_body(bound_pipeline):
    import time

    from career_evidence_graph.application_worker import start_run

    server, store, calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    start_run(worker.store)
    # Preparation runs before opening a Page; readback remains a separate exact gate.
    pipeline.pause()
    original = flow.snapshot()["active_task"]
    before = store.read_export(original["resume_id"])["latex_source"]
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="one-bound-continue")
    for _ in range(300):
        task = flow.snapshot(original["id"])["active_task"]
        if task.get("material_update", {}).get("status") != "preparing":
            break
        time.sleep(0.01)
    update = task["material_update"]
    assert update["status"] == "awaiting_page", (
        update.get("error_code"),
        update.get("error_message"),
    )
    candidate = update["candidate"]
    current_source = store.read_export(candidate["resume_id"])["latex_source"]
    assert "updated@example.invalid" in current_source
    assert "job@example.invalid" not in current_source
    assert before.split("\\section", 1)[1] in current_source
    assert task["resume_id"] == original["resume_id"]
    assert candidate["resume_id"] != task["resume_id"]
    assert len(calls) == 1
    assert len(store.prism_client.calls) == 2
    assert worker.store.load()["control"] == "paused"


def test_unknown_candidate_export_only_reconciles_the_consumed_original_attempt(
    bound_pipeline, monkeypatch
):
    import time

    from career_evidence_graph.application_worker import start_run
    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    start_run(worker.store)
    pipeline.pause()
    original = flow.snapshot()["active_task"]
    exported = []
    # The candidate uses the same actual callback as ordinary immutable exports.
    # This fault must occur after the completed export receipt is durable.
    original_candidate = flow.callbacks["bound_material_candidate"]

    def candidate_response_lost(task):
        result = original_candidate(task)
        exported.append(result["resume_id"])
        raise PortalDataError("resume_export_needs_recheck", "synthetic response lost", 409)

    monkeypatch.setitem(flow.callbacks, "bound_material_candidate", candidate_response_lost)
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    pipeline.continue_current(request_id="lost-export-response")
    for _ in range(250):
        current = flow.snapshot()["active_task"]
        if current.get("material_update", {}).get("status") != "preparing":
            break
        time.sleep(0.01)
    assert current["material_update"]["status"] == "needs_recheck"
    attempt = current["material_update"]["candidate"]["stages"]["export"]["attempt_id"]
    assert attempt == exported[0]
    assert current["resume_id"] == original["resume_id"]
    monkeypatch.setitem(flow.callbacks, "bound_material_candidate", original_candidate)
    pipeline.continue_current(request_id="read-original-export-attempt")
    for _ in range(250):
        current = flow.snapshot()["active_task"]
        if current.get("material_update", {}).get("status") != "preparing":
            break
        time.sleep(0.01)
    assert current["material_update"]["status"] == "awaiting_page", current["material_update"].get(
        "error_message"
    )
    assert current["material_update"]["candidate"]["resume_id"] == attempt
    assert len(store.prism_client.calls) == 2 and len(calls) == 1
    assert current["resume_id"] == original["resume_id"]
    assert worker.store.load()["control"] == "paused"


@pytest.mark.parametrize("legacy_journal", [False, True])
def test_bound_material_commit_keeps_identity_only_and_retains_original_receipts(
    bound_pipeline, legacy_journal
):
    import fcntl
    import json
    import os
    import time
    from pathlib import Path

    from career_evidence_graph.application_worker import digest, start_run

    server, store, _calls = bound_pipeline
    flow, worker, pipeline = (
        server.application_flow_service,
        server.worker_service,
        server.application_pipeline_service,
    )
    run_id = start_run(worker.store)
    descriptor = os.open(worker.store.root / ".worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    worker.store.worker_lock_descriptor = descriptor
    try:
        pipeline.pause()
        current = worker.store.load()
        job = current["jobs"][0]
        job.update(
            page_open=True,
            status="ready_for_review",
            reason="final_submit_manual",
            manual_fields={"notes": "Human text retained"},
            manual_attachments=[{"name": "resume.pdf", "sha256": job["file_sha256"]}],
            page_observation={"run_id": run_id, "page_id": "retained-page", "at": time.time()},
        )
        worker.store.save(current)
        before = deepcopy(job)
        old_pdf = Path(job["file_path"]).read_bytes()
        original = flow.snapshot()["active_task"]
        put_information_answer(
            worker.store.answers,
            {
                "question": "Email",
                "value": "updated@example.invalid",
                "state": "confirmed",
                "scope": {},
            },
        )
        pipeline.continue_current(request_id="commit-without-page-copies")
        for _ in range(300):
            task = flow.snapshot(original["id"])["active_task"]
            if task.get("material_update", {}).get("status") != "preparing":
                break
            time.sleep(0.01)
        assert task["material_update"]["status"] == "awaiting_page", task["material_update"]
        pipeline._tick()
        current = worker.store.load()
        job = current["jobs"][0]
        assert job["material_update"]["status"] == "inspect_pending"
        stat = os.fstat(descriptor)
        # Supply the Runner readback boundary; run the real local commit and its
        # exact input, owner, old/new PDF, journal and single-binding validation.
        job["material_update"].update(
            status="page_verified",
            page_receipt={
                "run_id": run_id,
                "page_id": "retained-page",
                "worker_lock": {"device": stat.st_dev, "inode": stat.st_ino},
            },
        )
        worker.store.save(current)
        pipeline._tick()
        persisted = json.loads(flow.path.read_text())["tasks"][0]
        assert persisted["material_update"]["status"] == "bound", pipeline.snapshot()
        assert persisted["worker_ref"] == {
            "batch_id": current["batch_id"],
            "job_id": before["application_id"],
        }
        assert persisted["status"] == "needs_recheck"
        if legacy_journal:
            journal_path = (
                flow.root / "material-updates" / (persisted["material_update"]["id"] + ".json")
            )
            journal = json.loads(journal_path.read_text())
            journal["new"]["worker_ref"].update(
                status="ready_for_review", reason="old copied page state", page_open=True
            )
            journal["revision"] = digest(
                {key: value for key, value in journal.items() if key != "revision"}
            )
            journal_path.write_text(json.dumps(journal))
            local = json.loads(flow.path.read_text())
            local["tasks"][0]["material_update"]["status"] = "committing"
            local["tasks"][0]["revision"] = digest(
                {key: value for key, value in local["tasks"][0].items() if key != "revision"}
            )
            flow.path.write_text(json.dumps(local))
            pipeline._tick()
            persisted = json.loads(flow.path.read_text())["tasks"][0]
            assert persisted["material_update"]["status"] == "bound"
            assert persisted["worker_ref"] == {
                "batch_id": current["batch_id"],
                "job_id": before["application_id"],
            }
            assert (
                json.loads(journal_path.read_text())["new"]["worker_ref"]["reason"]
                == "old copied page state"
            )
        after = worker.store.load()
        worker.store.check_single(after["jobs"][0], after)
        for key in ("manual_fields", "manual_attachments", "page_observation", "intent"):
            assert after["jobs"][0][key] == before[key]
        assert after["runtime"]["id"] == run_id
        assert Path(before["file_path"]).read_bytes() == old_pdf
        assert store.pdf(original["resume_id"]) == old_pdf
        assert persisted["resume_id"] != original["resume_id"]
        current = worker.store.load()
        current["jobs"][0]["material_update"]["status"] = "complete"
        worker.store.save(current)
        pipeline._tick()
        completed = json.loads(flow.path.read_text())["tasks"][0]
        assert completed["material_update"]["status"] == "complete"
        assert completed["status"] == "materials_ready"
        assert completed["worker_ref"] == persisted["worker_ref"]
    finally:
        os.close(descriptor)
        worker.store.worker_lock_descriptor = None
