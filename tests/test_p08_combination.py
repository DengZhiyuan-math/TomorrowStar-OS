"""Synthetic normal-entry P01–P07 combinations; no live model, Prism or ATS.

Only provider/process boundaries are doubled. Analysis, persisted Flow stages,
fixed writing, manual versions, PDF capture and bound Worker preparation use
production entrypoints. A retained-page double covers Continue, not browser DOM.
"""

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_application_flow import wait_for
from test_application_information import answer, tree_bytes, write_library
from test_application_resume import task_resume as task_resume
from test_normal_retrieval_pipeline import RecordedPipeline, requirement
from test_resume_export import PDF_SAMPLE

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_worker import digest, start_run
from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import PortalDataError

pytestmark = pytest.mark.usefixtures("planner_path")


class SavedPrism:
    """Return an already completed build; never invoke a compiler."""

    def open(self, binding):
        return "http://127.0.0.1:8799/"

    def compile(self, binding):
        pytest.fail("P08 manual return must reuse Prism's completed build")

    def read_compiled(self, binding):
        from career_evidence_graph.application_prism import dependency_snapshot

        current = dependency_snapshot(
            Path(binding["project_root"]), binding["main"], binding["files"]
        )
        raw = PDF_SAMPLE.read_bytes()
        return {
            "binding": current,
            "pdf": raw,
            "build": {
                "schema_version": "prism-build-result/v1",
                "status": "complete",
                "id": uuid4().hex,
                "main": current["main"],
                "files": current["files"],
                "exit": 0,
                "pdf_updated": True,
                "diagnostics": [],
                "cancelled": False,
                "timed_out": False,
                "pdf_sha256": hashlib.sha256(raw).hexdigest(),
            },
        }


@pytest.fixture
def combination(task_resume, tmp_path, monkeypatch):
    store, original, *_ = task_resume
    job = store.applications.update_application(
        original["id"],
        {
            "company": "Equivalent synthetic employer",
            "role_title": "Quantitative Research Engineer",
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789012",
            "location": "Lakeside, Switzerland",
            "job_description": "Build Python research services and communicate in English.",
        },
        original["revision"],
    )
    experiences = ExperienceStore(store.catalog.root)
    record = experiences.save(
        "opaque-work-317",
        title="Unfamiliar historical label",
        body="Built Python research services. User implemented the research service.",
    )
    catalog = store.catalog.root / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "candidate_id": "opaque-work-317",
                        "title": "Unfamiliar historical label",
                        "record_class": "current-confirmed-identity",
                        "accepted_reading_summary": "Research service implementation",
                        "confirmed_identity_facts": {},
                        "source_links": [],
                    }
                ]
            }
        )
    )
    manifest = tmp_path / "library.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "root": str(store.catalog.root),
                "catalog": {
                    "path": "catalog.json",
                    "sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
                },
            }
        )
    )
    information = tmp_path / "information"
    write_library(
        information,
        answers=dict(
            [
                answer("English fluency", "professional", scope={"country": "CHE"}),
                answer("English fluency", "no", scope={"country": "USA"}),
            ]
        ),
    )
    runner = RecordedPipeline([requirement("Build Python research services")])
    project = tmp_path / "base"
    project.mkdir()
    (project / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nSynthetic Person\n"
        "\\section*{Research engineering}\nBuilt Python research services.\n\\end{document}\n"
    )
    (project / "notes.txt").write_text("Keep ancillary material")
    root = tmp_path / "flow"
    store.root = root / "resumes"
    store.root.mkdir(parents=True)
    store.prism_client = SavedPrism()
    store.pdf_inspector = lambda raw: 1
    proofreading = []

    def proofread(config, prompt, **kwargs):
        proofreading.append(prompt)
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    store.model_runner = proofread
    subprocess.run(["git", "init", "--quiet", "--template=", str(store.catalog.root)], check=True)
    with create_server(
        store.applications.root,
        store.catalog.root,
        port=0,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        career_library_manifest=manifest,
        information_library_root=information,
        flow_match_runner=runner,
        flow_resume_factory=lambda *_: store,
        write_admission_policy="development",
    ) as server:
        monkeypatch.setattr(server.worker_service, "spawn", lambda: None)
        yield SimpleNamespace(
            server=server,
            flow=server.application_flow_service,
            store=store,
            job=job,
            runner=runner,
            experiences=experiences,
            record=record,
            information=information,
            project=project,
            proofreading=proofreading,
        )


def start_writing(case):
    flow, job = case.flow, case.job
    task = flow.create(job["id"], job["revision"])
    # This fixture replays a persisted P08 task from before JSON-only creation.
    with flow.applications.write_lock():
        saved = flow._load()
        historical = flow._task(saved, task["id"])
        historical.pop("material_contract", None)
        flow._save(saved)
    task = flow.snapshot(task["id"])["active_task"]
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda row: row["status"] in {"analysis_ready", "failed"})
    assert task["status"] == "analysis_ready", task["stages"]
    task = flow.prepare_automatic_materials(
        task["id"], task["revision"], str(case.project), "main.tex"
    )
    flow.start(task["id"], task["revision"], "resume")
    task = wait_for(flow, task["id"], lambda row: row["status"] in {"needs_input", "failed"})
    assert task["status"] == "needs_input", task
    state = task["experience_handoff"]
    assert state["generation_contract"] == "fixed-writing/v1"
    payload = generation.generation_context(case.store, state["id"])
    source = next(
        row for row in payload["sources"] if row.get("title") == "Unfamiliar historical label"
    )
    identity = next(row for row in payload["sources"] if row.get("source_kind") == "identity")
    groups = [
        {
            "title": "Identity",
            "start_line": 1,
            "end_line": 1,
            "source_ids": [identity["source_id"]],
            "latex": "Synthetic Person\n",
            "disposition": "include",
            "reason": "Keep confirmed identity",
        },
        {
            "title": "Research engineering",
            "start_line": 2,
            "end_line": 3,
            "source_ids": [source["source_id"]],
            "latex": "\\section*{Research engineering}\nBuilt Python research services.\n",
            "disposition": "include",
            "reason": "Recorded research service work",
        },
    ]
    state = generation.configure_generation(
        case.store,
        state["id"],
        groups=groups,
        experiences=[
            {
                "experience_id": "research-service",
                "source_ids": [source["source_id"]],
                "group_indexes": [1],
                "business_relevance": "Research service delivery",
                "evidence_role": "direct_domain",
                "focus": "Recorded implementation only",
            }
        ],
        organization_plan={
            "summary_focus": "Research service delivery",
            "ordering_rationale": "Lead with evidenced implementation",
        },
    )
    return task, state


def finish_writing(case, task, state):
    context = generation.writer_context(case.store, state["id"], "research-service")
    generation.submit_fragment(
        case.store,
        state["id"],
        "research-service",
        input_revision=context["input_revision"],
        groups=context["groups"],
        used_refs=[context["source_ids"][0]],
        issues=[],
        writer_id="synthetic-writer",
    )
    candidate = generation.assemble_generation(case.store, state["id"])
    generation.review_generation(
        case.store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="synthetic-final-reviewer",
        passed=True,
        issues=[],
    )
    generation.adopt_generation(case.store, state["id"])
    case.flow.request(
        "resume-experience-generation",
        {"task_id": task["id"], "task_revision": task["revision"], "generation_id": state["id"]},
    )
    task = wait_for(case.flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
    assert task["status"] == "draft_ready", task
    return task


def action(case, task, operation):
    return case.flow.request(operation, {"task_id": task["id"], "task_revision": task["revision"]})


def prepare_human_material(case):
    task, state = start_writing(case)
    task_id, analysis_id = task["id"], task["analysis_id"]
    assert case.runner.phases == ["plan", "evaluate"]
    assert len(case.runner.brief_calls) == 1
    assert case.runner.contexts[0]["records"][0]["candidate_id"] == "opaque-work-317"
    facts = case.runner.contexts[0]["confirmed_information_context"]["facts"]
    english = next(row for row in facts if row["fact"] == "language_english_fluent")
    assert english["value"] == "professional"
    assert english["records"][0]["scope"] == {"country": "CHE"}
    assert '"USA"' not in json.dumps(facts)
    task = finish_writing(case, task, state)
    parent = case.store.draft(task["draft_id"])
    task = action(case, task, "begin-prism-edit")
    source = Path(task["prism_edit"]["project_root"]) / task["prism_edit"]["main"]
    manual = source.read_text().replace(
        "\\begin{document}", "\\setlength{\\parindent}{7pt}\n\\begin{document}"
    )
    source.write_text(manual)
    task = action(case, task, "finish-prism-edit")
    assert task["draft_id"] != parent["id"]
    assert case.store.draft(task["draft_id"])["latex_source"] == manual
    assert len(case.proofreading) == 1
    task = action(case, task, "capture-prism-result")
    assert task["status"] == "materials_ready", task
    assert task["analysis_id"] == analysis_id and task["id"] == task_id
    pdf = case.store.pdf(task["resume_id"])
    assert hashlib.sha256(pdf).hexdigest() == task["resume_sha256"]
    assert case.store.draft(parent["id"])["latex_source"] == parent["latex_source"]
    return task, pdf, source, manual, parent


@pytest.mark.parametrize("protocol", ["legacy", "form-state/v1"])
def test_quant_normal_entry_to_manual_version_bound_worker_and_unknown_continue(
    combination, monkeypatch, protocol
):
    case = combination
    library_before = tree_bytes(case.information)
    experience_before = deepcopy(case.experiences.get("opaque-work-317"))
    base_before = tree_bytes(case.project)
    task, pdf, source, manual, parent = prepare_human_material(case)
    task_id, analysis_id = task["id"], task["analysis_id"]
    worker = case.server.worker_service
    bound = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    job = worker.store.load()["jobs"][0]
    assert bound["worker_ref"]["job_id"] == job["application_id"]
    assert job["single_binding"]["task_id"] == task_id
    assert job["single_binding"]["analysis_id"] == analysis_id
    assert Path(job["file_path"]).read_bytes() == pdf
    run_id = start_run(worker.store)

    class Page:
        context = None
        url = case.job["url"]

        def is_closed(self):
            return False

    page = Page()
    browser = ApplicationRunner(worker.store, None)
    browser.pages[job["application_id"]] = page
    browser.page_ids[page] = "retained-page"
    pending = {"action": "upload", "attempt_id": "old-unresolved-action", "run_id": run_id}
    snapshot = worker.store.load()
    snapshot["jobs"][0].update(
        status="needs_recheck",
        intent=deepcopy(pending),
        page_open=True,
        observations=[{"event": "original-unknown-result"}],
        page_observation={"run_id": run_id, "page_id": "retained-page", "event": "observed"},
    )
    worker.store.save(snapshot)
    fields = [
        {
            "id": "name",
            "type": "text",
            "question": "Full name",
            "value": "Human Name",
            "valid": True,
        },
        {
            "id": "resume",
            "type": "file",
            "question": "Resume",
            "filename": "human.pdf",
            "file_sha256": "d" * 64,
        },
    ]
    if protocol == "form-state/v1":
        pending = {
            "form_protocol": protocol,
            "form_binding": {
                "run_id": run_id,
                "page_id": "retained-page",
                "step": case.job["url"],
                "document_token": "doc",
            },
            "action": "fill",
            "field_id": "name",
            "field_type": "text",
            "expected_value": "Saved Name",
            "before_value": "Original Name",
            "dispatch_state": "sent",
            "run_id": run_id,
            "page_id": "retained-page",
            "attempt_id": "original-uncertain-fill",
            "field_shape": digest(
                {
                    key: fields[0].get(key)
                    for key in ("id", "type", "question", "options", "required")
                }
            ),
        }
        snapshot["jobs"][0]["intent"] = deepcopy(pending)
        worker.store.save(snapshot)
    reads = []
    monkeypatch.setattr(
        browser,
        "observe",
        lambda *_: reads.append(page) or {"fields": deepcopy(fields), "document_token": "doc"},
    )
    payload = {
        "application_id": job["application_id"],
        "controller": "synthetic-controller",
        "request_id": "one-continue",
    }
    worker.request("continue-current", payload)
    snapshot = worker.store.load()
    browser.commands(snapshot)
    browser.persist(snapshot)
    result = worker.store.load()
    assert result["control"] == "paused"
    assert result["jobs"][0]["intent"] == pending
    assert result["jobs"][0]["continuation"]["status"] == "needs_recheck"
    assert {"event": "original-unknown-result"} in result["jobs"][0]["observations"]
    assert result["jobs"][0]["form_state"]["baseline"]["name"]["value"] == "Human Name"
    assert result["jobs"][0]["form_state"]["attachment_baseline"][0]["filename"] == "human.pdf"
    assert len(reads) == 1
    worker.request("continue-current", payload)
    assert worker.store.load()["commands"] == []
    assert len(reads) == 1
    assert fields[0]["value"] == "Human Name" and fields[1]["filename"] == "human.pdf"
    assert tree_bytes(case.information) == library_before
    assert case.experiences.get("opaque-work-317") == experience_before
    assert tree_bytes(case.project) == base_before
    assert source.read_text() == manual
    assert Path(job["file_path"]).read_bytes() == pdf
    assert len(case.runner.brief_calls) == len(case.proofreading) == 1


def test_missing_writer_stops_normal_flow_and_resumes_same_fixed_analysis(combination):
    case = combination
    task, state = start_writing(case)
    original = deepcopy(task)
    with pytest.raises(PortalDataError):
        generation.assemble_generation(case.store, state["id"])
    assert case.flow.snapshot(task["id"])["active_task"] == original
    task = finish_writing(case, task, state)
    assert task["id"] == original["id"]
    assert task["analysis_id"] == original["analysis_id"]
    assert task["artifacts"][: len(original["artifacts"])] == original["artifacts"]
    assert len(case.runner.brief_calls) == 1
    assert case.runner.phases == ["plan", "evaluate"]
    assert case.server.worker_service.store.load()["jobs"] == []


@pytest.mark.worker_browser
def test_normal_material_reaches_real_isolated_ats_with_single_binding_intact(
    combination, monkeypatch
):
    from playwright.sync_api import sync_playwright
    from test_p07_runner_browser import INSTRUMENT, assert_no_final_actions, reach

    from career_evidence_graph._vendor import job_apply_store as helper

    case = combination
    # The retained single task uses its declared information library.
    helper.Store(case.information).put_answer(
        {"question": "Email", "value": "saved@example.invalid", "scope": {}, "state": "confirmed"}
    )
    task, pdf, source, manual, _ = prepare_human_material(case)
    worker = case.server.worker_service
    library_before = tree_bytes(worker.store.answers.root)
    case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    bound_before = deepcopy(worker.store.load()["jobs"][0]["single_binding"])
    worker.request("resume", {"controller": "synthetic-controller"})
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    html = (
        f"<title>{case.job['company']} - {case.job['role_title']}</title>"
        "<h1>Quantitative Research Engineer</h1>"
        + INSTRUMENT
        + """<form id="application-form" data-parser-state="complete">
        <label>Full name *<input name="name" value="Human Name" required></label>
        <label>Email *<input name="email" type="email" required></label>
        <label>Resume/CV *<input name="resume" type="file" required></label>
        <button type="submit">Submit application</button></form>"""
    )
    posts = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(offline=True)
            start_run(worker.store)
            runner = ApplicationRunner(worker.store, context)

            def intercept(route):
                class Route:
                    request = route.request

                    def fetch(self, **options):
                        assert options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                        return SimpleNamespace(status=200, dispose=lambda: None)

                    def fulfill(self, *, response):
                        assert response.status == 200
                        if self.request.method != "GET":
                            posts.append(self.request.method)
                        route.fulfill(status=200, body=html, content_type="text/html")

                    def abort(self, reason):
                        route.abort(reason)

                runner._live_guard(Route())

            context.route("**/*", intercept)
            ready = reach(worker, runner, lambda row: row["status"] == "ready_for_review")
            page = runner.pages[case.job["id"]]
            assert ready["single_binding"] == bound_before
            # The saved checker and dispatch file guard run without monkeypatching;
            # changed upload bytes cannot pass the material-required send boundary.
            worker.store.check_single(ready, worker.store.load())
            pdf_path = Path(ready["file_path"])
            try:
                pdf_path.write_bytes(pdf + b"\n% changed bytes")
                with pytest.raises(PortalDataError, match="简历版本"):
                    runner.check_inputs(ready, material_required=True)
            finally:
                pdf_path.write_bytes(pdf)
            assert page.locator("[name=name]").input_value() == "Human Name"
            assert page.locator("[name=email]").input_value() == "saved@example.invalid"
            uploaded = page.locator("[type=file]").evaluate(
                "async e=>Array.from(new Uint8Array(await e.files[0].arrayBuffer()))"
            )
            assert bytes(uploaded) == pdf
            assert tree_bytes(worker.store.answers.root) == library_before
            assert source.read_text() == manual
            assert_no_final_actions(page, posts)
        finally:
            browser.close()


def test_normal_manual_return_failure_retains_source_and_does_not_retry_provider(combination):
    case = combination
    task, state = start_writing(case)
    task = finish_writing(case, task, state)
    task = action(case, task, "begin-prism-edit")
    source = Path(task["prism_edit"]["project_root"]) / task["prism_edit"]["main"]
    manual = source.read_text() + "\n% human comment retained after provider failure\n"
    source.write_text(manual)
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(True)
        raise TimeoutError("Synthetic proofreader unavailable")

    case.store.model_runner = unavailable
    result = action(case, task, "finish-prism-edit")
    assert result["id"] == task["id"] and result["analysis_id"] == task["analysis_id"]
    assert result["material_source_state"] == "proofreading_unavailable"
    assert case.store.draft(result["draft_id"])["latex_source"] == manual
    assert source.read_text() == manual
    assert action(case, result, "finish-prism-edit") == result
    assert calls == [True]
    assert case.server.worker_service.store.load()["jobs"] == []


@pytest.mark.parametrize(
    "damage",
    [
        "analysis_result",
        "analysis_inputs",
        "draft_id",
        "material_binding",
        "missing_material_binding",
        "pdf_bytes",
    ],
)
def test_normal_manual_material_transmission_rejects_broken_saved_lineage(combination, damage):
    case = combination
    task, pdf, source, manual, _ = prepare_human_material(case)
    with case.flow.applications.write_lock():
        saved, current = case.flow._checked(task["id"], task["revision"])
        analysis = next(row for row in current["artifacts"] if row["stage"] == "analysis")
        if damage == "analysis_result":
            analysis["result"]["job_brief"]["business_object"] = "Changed saved result"
        elif damage == "analysis_inputs":
            analysis["inputs"]["sources_revision"] = "0" * 64
        elif damage == "draft_id":
            current["draft_id"] = "f" * 32
        elif damage == "material_binding":
            current["material_binding"]["draft_sha256"] = "0" * 64
        elif damage == "missing_material_binding":
            current.pop("material_binding")
        else:
            (case.store.root / current["resume_id"] / "resume.pdf").write_bytes(pdf + b"changed")
        case.flow._save(saved)
        changed = deepcopy(current)
    with pytest.raises(PortalDataError):
        case.flow.prepare_worker(changed["id"], changed["revision"], "CHE", True)
    assert case.server.worker_service.store.load()["jobs"] == []
    assert source.read_text() == manual
    assert len(case.runner.brief_calls) == len(case.proofreading) == 1


@pytest.mark.parametrize("change", ["source", "jd", "configuration", "url"])
@pytest.mark.parametrize("material_required", [False, True])
def test_bound_manual_material_is_local_but_cannot_move_to_another_url(
    combination, monkeypatch, change, material_required
):
    case = combination
    task, pdf, source, manual, _ = prepare_human_material(case)
    case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = case.server.worker_service
    state = worker.store.load()
    job = deepcopy(state["jobs"][0])
    original_binding = deepcopy(job["single_binding"])
    if change == "source":
        previous = case.experiences.get("opaque-work-317")
        case.experiences.save(
            "opaque-work-317",
            title=previous["title"],
            body=previous["body"] + "\nA later source correction for future versions.",
            expected_revision=previous["revision"],
        )
    elif change in {"jd", "url"}:
        application = case.store.applications.get_application(case.job["id"])
        case.store.applications.update_application(
            application["id"],
            {"job_description": "A changed job description for later matching."}
            if change == "jd"
            else {"url": application["url"][:-1] + "3"},
            application["revision"],
        )
    else:
        from career_evidence_graph import application_match, application_resume

        def forbidden(*args, **kwargs):
            pytest.fail("A delivered manual PDF cannot depend on live model configuration")

        monkeypatch.setattr(application_match, "match_configuration_revision", forbidden)
        monkeypatch.setattr(application_resume, "resume_configuration_revision", forbidden)
        monkeypatch.setattr(application_resume.ApplicationResumeStore, "configuration", forbidden)
    if change == "url":
        with pytest.raises(PortalDataError):
            worker.store.check_single(job, state, material_required=material_required)
    else:
        worker.store.check_single(job, state, material_required=material_required)
    assert worker.store.load()["jobs"][0]["single_binding"] == original_binding
    assert Path(job["file_path"]).read_bytes() == pdf
    assert source.read_text() == manual
    assert len(case.runner.brief_calls) == len(case.proofreading) == 1


@pytest.mark.parametrize("change", ["profile_identity", "applicable_email"])
@pytest.mark.parametrize("material_required", [False, True])
def test_manual_material_contact_correction_blocks_send_but_keeps_readable_versions(
    combination, change, material_required
):
    case = combination
    task, pdf, source, manual, _ = prepare_human_material(case)
    case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = case.server.worker_service
    state = worker.store.load()
    job = deepcopy(state["jobs"][0])
    original_binding = deepcopy(job["single_binding"])
    if change == "profile_identity":
        path = case.store.catalog.root / "sources/profile.json"
        profile = json.loads(path.read_text())
        profile["name"] = "Corrected Synthetic Person"
        path.write_text(json.dumps(profile))
    else:
        path = case.information / "answers.json"
        library = json.loads(path.read_text())
        key, record = answer(
            "Email", "corrected@example.invalid", scope={"application_id": case.job["id"]}
        )
        library["answers"][key] = record
        path.write_text(json.dumps(library))
    with pytest.raises(PortalDataError) as error:
        worker.store.check_single(job, state, material_required=material_required)
    assert error.value.code == "single_binding_invalid"
    assert worker.store.load()["jobs"][0]["single_binding"] == original_binding
    assert case.store.pdf(task["resume_id"]) == pdf
    assert Path(job["file_path"]).read_bytes() == pdf
    assert case.store.draft(task["draft_id"])["latex_source"] == manual
    assert source.read_text() == manual
    assert len(case.runner.brief_calls) == len(case.proofreading) == 1


@pytest.mark.parametrize("damage", ["invalid_json", "changed_profile"])
@pytest.mark.parametrize("material_required", [False, True])
def test_manual_material_corrupt_binding_snapshot_cannot_fall_back_to_selected_snapshot(
    combination, damage, material_required
):
    case = combination
    task, pdf, source, manual, _ = prepare_human_material(case)
    case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = case.server.worker_service
    state = worker.store.load()
    job = deepcopy(state["jobs"][0])
    directory = case.flow.root / "analyses" / task["analysis_id"]
    selected = directory / "source-snapshot.json"
    selected_before = selected.read_bytes()
    binding = directory / "binding-source-snapshot.json"
    snapshot = json.loads(binding.read_text())
    assert snapshot["revision"] == task["inputs"]["sources_revision"]
    assert json.loads(selected_before)["revision"] != snapshot["revision"]
    if damage == "invalid_json":
        binding.write_text("{broken saved original binding")
    else:
        snapshot["profile"]["name"] = "Unbound changed profile"
        binding.write_text(json.dumps(snapshot))
    with pytest.raises(PortalDataError) as error:
        worker.store.check_single(job, state, material_required=material_required)
    assert error.value.code == "single_binding_invalid"
    assert selected.read_bytes() == selected_before
    assert case.store.pdf(task["resume_id"]) == pdf
    assert Path(job["file_path"]).read_bytes() == pdf
    assert source.read_text() == manual
    assert len(case.runner.brief_calls) == len(case.proofreading) == 1
