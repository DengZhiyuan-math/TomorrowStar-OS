"""Default full materials reuse technical evidence and retain explicit source edits."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_resume import task_resume as task_resume
from test_automatic_complete_materials import SyntheticCompiler
from test_full_latex_generation import full_latex as full_latex
from test_resume_export import PDF_SAMPLE

from career_evidence_graph import application_match
from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.career_portal import create_server


@pytest.fixture
def complete_portal(full_latex, tmp_path, monkeypatch, request):
    store, original, _, analysis, calls, project, _, _ = full_latex
    preparation_only = getattr(request, "param", {}).get("preparation_only", False)
    grouped_review = getattr(request, "param", {}).get("grouped_review", False)
    if grouped_review:
        from test_standalone_prism_review import FakePrism

        assert preparation_only and getattr(request, "param", {}).get("stop_before_export")
        store.group_prism_client = FakePrism()
    information_root = None
    if getattr(request, "param", {}).get("information_library"):
        from career_evidence_graph._vendor import job_apply_store as helper

        information_root = tmp_path / "information-library"
        helper.Store(
            information_root, legacy_profile=tmp_path / "no-legacy-information"
        ).initialize()
    if preparation_only:
        # The application-mode fixture previously needed source bindings only.
        # Preparation also consumes a complete saved requirement judgment.
        analysis["requirements"][0].update(
            text="Operate reliable service systems.",
            importance="required",
            judgment="supported",
            hard_condition=False,
            explanation="Recorded recovery-protocol design for service reliability.",
        )
    job = store.applications.update_application(
        original["id"],
        {
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789012",
            "location": "Zurich, Switzerland",
            "job_description": (
                "Build Python services and operate reliable distributed service systems."
            ),
        },
        original["revision"],
    )
    if getattr(request, "param", {}).get("german_requirement"):
        job = store.applications.update_application(
            job["id"],
            {"job_description": job["job_description"] + " German B2 required."},
            job["revision"],
        )
        analysis["requirements"][0].update(
            text="German B2 required.",
            importance="required",
            judgment="unknown",
            hard_condition=True,
        )
    root = tmp_path / "shared-flow"
    store.root = root / "resumes"
    store.root.mkdir(parents=True)
    store.prism_client = SyntheticCompiler()
    compile_source = store.prism_client.compile
    store.prism_client.compile = lambda binding: (
        compile_source(binding) | {"pdf": PDF_SAMPLE.read_bytes()}
    )
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
        return result

    monkeypatch.setattr(application_match, "analyze_job", fake_analysis)
    with create_server(
        store.applications.root,
        store.catalog.root,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        preparation_only=preparation_only,
        information_library_root=information_root,
        flow_resume_factory=lambda *args: store,
    ) as server:
        flow = server.application_flow_service
        if getattr(request, "param", {}).get("german_requirement"):
            server.worker_service.store.answers.put_answer(
                {
                    "question": "German level",
                    "value": "B2",
                    "state": "confirmed",
                    "scope": {"country": "CHE"},
                }
            )
        if getattr(request, "param", {}).get("confirmed_email"):
            from career_evidence_graph._vendor import job_apply_store as helper

            scope = {"application_id": job["id"]}
            server.worker_service.store.answers.put_answer(
                {
                    "question": "Email",
                    "value": "job@example.invalid",
                    "scope": scope,
                    "state": "confirmed",
                }
            )
            output = full_latex[6]
            output["groups"][0]["source_ids"].append("answer:" + helper.answer_key("Email", scope))
            output["groups"][0]["latex"] = "Synthetic Person\njob@example.invalid\n"
        if getattr(request, "param", {}).get("identity_comment"):
            main = project / "main.tex"
            main.write_text(
                main.read_text().replace(
                    "Synthetic Person\n", "% internal identity group\nSynthetic Person\n"
                )
            )
            output = full_latex[6]
            output["groups"][0]["end_line"] = 2
            for group in output["groups"][1:]:
                group["start_line"] += 1
                group["end_line"] += 1
        task = flow.create(job["id"], job["revision"])
        if not getattr(request, "param", {}).get("new_task"):
            # Replay a persisted pre-JSON task; fresh tasks use content-writing/v1.
            with flow.applications.write_lock():
                state = flow._load()
                flow._task(state, task["id"]).pop("material_contract", None)
                flow._save(state)
            task = flow.snapshot(task["id"])["active_task"]
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda t: t["status"] == "analysis_ready")
        prepare = flow.bind_latex_base if grouped_review else flow.prepare_automatic_materials
        task = prepare(task["id"], task["revision"], str(project), "main.tex")
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(flow, task["id"], lambda t: t["status"] in {"draft_ready", "failed"})
        if getattr(request, "param", {}).get("new_task"):
            yield server, store, task, calls
            return
        assert task["status"] == "draft_ready", task["stages"]
        if getattr(request, "param", {}).get("stop_before_export"):
            yield server, store, task, calls
            return
        flow.start(task["id"], task["revision"], "export")
        task = wait_for(flow, task["id"], lambda t: t["status"] == "materials_ready")
        yield server, store, task, calls


def semantic_reuse(store, source, monkeypatch):
    calls, prompts = [], []
    outputs = iter(
        [
            {
                "profiles": [
                    {
                        "id": source["id"],
                        "content": "Python service systems",
                        "core_work_confirmed": True,
                        "locators": ["Build Python services"],
                    }
                ],
                "task_ids": [source["id"]],
            },
            {
                "approved": True,
                "source_task_id": source["id"],
                "reason": "Current facts and complete material cover this target unchanged.",
            },
        ]
    )

    def runner(*args, **kwargs):
        calls.append(kwargs)
        prompts.append(args[1])
        return SimpleNamespace(structured_result=next(outputs))

    store.model_runner = runner

    def forbid_generation(*args, **kwargs):
        raise AssertionError("Reusable full PDF must not regenerate")

    monkeypatch.setattr(store, "generate_for_task", forbid_generation)
    return calls, prompts


def target_task(server, store):
    job = store.applications.create_application(
        {
            "company": "Second synthetic employer",
            "role_title": "Service Engineer",
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789013",
            "location": "Zurich, Switzerland",
            "job_description": (
                "Build Python services and operate reliable distributed service systems."
            ),
        }
    )
    flow = server.application_flow_service
    task = flow.create(job["id"], job["revision"])
    # Target is another retained task under the historical PDF-reuse contract.
    with flow.applications.write_lock():
        state = flow._load()
        flow._task(state, task["id"]).pop("material_contract", None)
        flow._save(state)
    task = flow.snapshot(task["id"])["active_task"]
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda t: t["status"] == "analysis_ready")
    return flow.prepare_automatic_materials(task["id"], task["revision"])


@pytest.mark.parametrize(
    ("retained_worker_unavailable", "legacy_page_status"),
    [(False, None), (True, None), (True, "filling"), (True, "flow_restarted")],
    ids=["unbound", "unavailable-worker", "legacy-filling", "legacy-restarted"],
)
def test_default_system_valid_full_pdf_reuses_without_fabricating_acceptance(
    complete_portal, monkeypatch, retained_worker_unavailable, legacy_page_status
):
    server, store, source, generation = complete_portal
    flow = server.application_flow_service
    if retained_worker_unavailable:
        source = flow.bind_worker(
            source["id"],
            source["revision"],
            {
                "batch_id": "retained-worker-batch",
                "job_id": source["application_id"],
                "status": "ready_for_review",
            },
        )
        if legacy_page_status:
            from career_evidence_graph.application_worker import digest

            saved = json.loads(flow.path.read_text())
            retained = next(row for row in saved["tasks"] if row["id"] == source["id"])
            retained["status"] = (
                "needs_recheck" if legacy_page_status == "flow_restarted" else legacy_page_status
            )
            retained["worker_ref"].update(status="filling", reason="retained old page")
            if legacy_page_status == "flow_restarted":
                retained["reason"] = "flow_restarted"
            retained["revision"] = digest(
                {key: value for key, value in retained.items() if key != "revision"}
            )
            flow.path.write_text(json.dumps(saved))
            before_legacy = json.loads(flow.path.read_text())["tasks"][0]
        assert flow.snapshot(source["id"])["active_task"]["status"] == "needs_recheck"
    semantic, prompts = semantic_reuse(store, source, monkeypatch)
    task = target_task(server, store)
    flow.start(task["id"], task["revision"], "resume")
    task = wait_for(flow, task["id"], lambda t: t["status"] in {"materials_ready", "failed"})
    assert task["status"] == "materials_ready", task
    assert task["pdf_reuse"]["source_evidence_kind"] == "system_validated_export"
    assert task["artifacts"][-1]["result"]["kind"] == "checked_pdf_reuse"
    assert not task.get("material_acceptance") and not task.get("material_reviews")
    assert len(generation) == len(store.prism_client.calls) == 1
    assert len(semantic) == 2
    assert "human_reviewed" in prompts[-1] and "false" in prompts[-1]
    prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    assert prepared["status"] == "queued"
    worker = server.worker_service
    current = worker.store.load()
    worker.store.check_single(current["jobs"][0], current)
    assert worker.process is None
    if legacy_page_status:
        assert json.loads(flow.path.read_text())["tasks"][0] == before_legacy


@pytest.mark.parametrize(
    "complete_portal", [{}, {"confirmed_email": True}, {"identity_comment": True}], indirect=True
)
def test_default_complete_source_edit_saves_independent_version_and_uses_it_as_next_base(
    complete_portal,
):
    server, store, original, generation = complete_portal
    flow = server.application_flow_service
    old_draft = store.draft(original["draft_id"])
    old_pdf = store.pdf(original["resume_id"])
    task = flow.request(
        "begin-automatic-edit",
        {
            "task_id": original["id"],
            "task_revision": original["revision"],
        },
    )
    editable = store.draft(task["draft_id"])
    assert "% TomorrowStar group" in editable["latex_source"]
    changed = editable["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.", "Built 6 Python services; analyzed strategy."
    )
    task = flow.request(
        "save-automatic-source",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "expected_source_revision": task["prism"]["source_revision"],
            "latex_source": changed,
        },
    )
    edited = store.draft(task["draft_id"])
    assert edited["latex_source"] == changed
    assert edited["manual_source"]["actor"] == "user"
    assert edited["manual_source"]["human_reviewed"] is False
    assert task["manual_latex_base"]["source_revision"] == task["prism"]["source_revision"]
    assert not task["materials_confirmed"] and task["resume_id"] is None
    assert store.pdf(original["resume_id"]) == old_pdf
    assert store.draft(original["draft_id"])["latex_source"] == old_draft["latex_source"]
    assert len(generation) == len(store.prism_client.calls) == 1
    flow.start(task["id"], task["revision"], "export")
    task = wait_for(
        flow,
        task["id"],
        lambda t: t["status"] in {"materials_ready", "needs_recheck", "export_failed"},
    )
    assert task["status"] == "materials_ready", task
    prepared = flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    worker = server.worker_service
    current = worker.store.load()
    worker.store.check_single(current["jobs"][0], current)
    assert prepared["status"] == "queued" and worker.process is None


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
@pytest.mark.parametrize(
    "header",
    [
        "Synthetic Person\nother@example.invalid\n",
        "Synthetic-Person\njob@example.invalid\n",
        "Synthetic Person\njob@example.invalid\nBuilt 7 Python services.\n",
        "Synthetic Person\njob@example.invalid\nImplemented Python services.\n",
    ],
)
def test_retained_contact_header_does_not_authorize_later_fact_or_capability_edits(
    complete_portal, header
):
    from test_installed_write_admission import bytes_under

    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, original, _ = complete_portal
    flow = server.application_flow_service
    task = flow.begin_automatic_edit(original["id"], original["revision"])
    draft = store.draft(task["draft_id"])
    changed = draft["latex_source"].replace("Synthetic Person\njob@example.invalid\n", header)
    before = bytes_under(store.root.parent)
    with pytest.raises(PortalDataError) as error:
        flow.save_automatic_source(
            task["id"], task["revision"], task["prism"]["source_revision"], changed
        )
    assert error.value.code == "resume_group_verification_required"
    assert bytes_under(store.root.parent) == before
    assert flow.snapshot(task["id"])["active_task"]["draft_id"] == task["draft_id"]


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_default_materials_use_existing_worker_contact_and_unrelated_answer_keeps_pdf(
    complete_portal,
):
    server, store, original, generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    saved = store.read_export(original["resume_id"])
    assert "job@example.invalid" in saved["latex_source"]
    assert any(
        source.get("source_name") == "information-library" for source in generation[-1]["sources"]
    )
    worker.store.answers.put_answer(
        {
            "question": "Preferred interview time",
            "value": "Afternoons",
            "state": "confirmed",
            "scope": {"application_id": original["application_id"]},
        }
    )
    prepared = flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    assert prepared["status"] == "queued"
    current = worker.store.load()
    worker.store.check_single(current["jobs"][0], current)
    assert prepared["resume_sha256"] == original["resume_sha256"]
    assert len(generation) == len(store.prism_client.calls) == 1


def test_historical_unbound_contact_correction_cannot_silently_send_old_pdf(tmp_path):
    from test_installed_write_admission import bytes_under, prepared_inputs

    from career_evidence_graph.career_portal_data import PortalDataError

    applications, root, career, task = prepared_inputs(tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "historical-worker",
        worker_live=True,
    ) as server:
        server.worker_service.store.answers.put_answer(
            {
                "question": "Email",
                "value": "corrected@example.invalid",
                "state": "confirmed",
                "scope": {"application_id": task["application_id"]},
            }
        )
        before = bytes_under(tmp_path)
        with pytest.raises(PortalDataError):
            server.application_flow_service.prepare_worker(
                task["id"], task["revision"], "CHE", True
            )
        assert bytes_under(tmp_path) == before


@pytest.mark.parametrize("complete_portal", [{"confirmed_email": True}], indirect=True)
def test_contact_header_correction_waits_before_resending_existing_materials(complete_portal):
    from test_installed_write_admission import bytes_under

    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, task, generation = complete_portal
    server.worker_service.store.answers.put_answer(
        {
            "question": "Email",
            "value": "new@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": task["application_id"]},
        }
    )
    before = bytes_under(store.root.parent)
    with pytest.raises(PortalDataError) as changed:
        server.application_flow_service.prepare_worker(task["id"], task["revision"], "CHE", True)
    assert changed.value.code in {"flow_inputs_stale", "single_binding_invalid"}
    assert bytes_under(store.root.parent) == before
    assert len(generation) == len(store.prism_client.calls) == 1


def test_paused_bound_worker_edit_only_creates_independent_candidate(complete_portal):
    from copy import deepcopy

    server, store, original, _ = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    prepared = flow.prepare_worker(original["id"], original["revision"], "CHE", True)
    before_worker = deepcopy(worker.store.load())
    before_draft = store.draft(original["draft_id"])
    before_pdf = store.pdf(original["resume_id"])
    edited = flow.begin_automatic_edit(prepared["id"], prepared["revision"])
    assert edited["material_update"]["status"] == "staged"
    assert edited["material_update"]["editable_draft"]["id"] != original["draft_id"]
    for key in ("draft_id", "draft_sha256", "resume_id", "resume_sha256", "inputs", "worker_ref"):
        assert edited[key] == prepared[key]
    assert worker.store.load() == before_worker
    assert store.draft(original["draft_id"]) == before_draft
    assert store.pdf(original["resume_id"]) == before_pdf


def test_explicit_next_generation_retains_manual_source_as_its_base(complete_portal):
    server, store, original, _ = complete_portal
    flow = server.application_flow_service
    task = flow.begin_automatic_edit(original["id"], original["revision"])
    draft = store.draft(task["draft_id"])
    changed = draft["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.", "Built 6 Python services; analyzed strategy."
    )
    task = flow.save_automatic_source(
        task["id"], task["revision"], task["prism"]["source_revision"], changed
    )
    edited = store.draft(task["draft_id"])
    expected_base = task["manual_latex_base"]
    requests = []

    def regenerate(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        requests.append(payload)
        lines = payload["body_lines"]
        groups = []
        for group in edited["review_groups"]:
            begin = next(
                row["line_number"]
                for row in lines
                if row["text"] == f"% TomorrowStar group {group['id']} begin\n"
            )
            end = next(
                row["line_number"]
                for row in lines
                if row["text"] == f"% TomorrowStar group {group['id']} end\n"
            )
            groups.append(
                {
                    "title": group["title"],
                    "start_line": begin,
                    "end_line": end,
                    "source_ids": [source["source_id"] for source in group["sources"]],
                    "latex": group["rewritten"],
                    "disposition": "include",
                    "reason": "Retain manual wording",
                }
            )
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []},
            model_dump=lambda **kwargs: {"synthetic": True},
        )

    store.model_runner = regenerate
    flow.start(task["id"], task["revision"], "resume", retry=True)
    task = wait_for(flow, task["id"], lambda t: t["status"] in {"draft_ready", "failed", "stale"})
    assert task["status"] == "draft_ready", task["stages"]
    assert "Built 6 Python services; analyzed strategy." in requests[0]["base"]
    assert task["base_checkpoint"]["source_revision"] == expected_base["source_revision"]
    flow.start(task["id"], task["revision"], "export")
    task = wait_for(
        flow,
        task["id"],
        lambda t: t["status"] in {"materials_ready", "needs_recheck", "export_failed"},
    )
    assert task["status"] == "materials_ready", task
    flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    current = server.worker_service.store.load()
    server.worker_service.store.check_single(current["jobs"][0], current)
    assert len(requests) == 1


@pytest.mark.parametrize("legacy_page_copy", [False, True])
def test_pending_bound_materials_cannot_supply_an_automatic_base(complete_portal, legacy_page_copy):
    from career_evidence_graph.application_information import put_information_answer
    from career_evidence_graph.career_portal_data import PortalDataError

    server, store, original, _generation = complete_portal
    flow, worker = server.application_flow_service, server.worker_service
    source = flow.bind_worker(
        original["id"],
        original["revision"],
        {
            "batch_id": "retained-worker-batch",
            "job_id": original["application_id"],
            "status": "ready_for_review",
        },
    )
    old_pdf = store.pdf(original["resume_id"])
    put_information_answer(
        worker.store.answers,
        {
            "question": "Email",
            "value": "updated@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
    )
    application = store.applications.get_application(original["application_id"])
    pending = flow.update_inputs(source["id"], source["revision"], application["revision"])
    assert pending["material_update"]["status"] == "staged"
    if legacy_page_copy:
        from career_evidence_graph.application_worker import digest

        saved = json.loads(flow.path.read_text())
        retained = saved["tasks"][0]
        retained["reason"] = "flow_restarted"
        retained["worker_ref"]["status"] = "filling"
        retained["revision"] = digest(
            {key: value for key, value in retained.items() if key != "revision"}
        )
        flow.path.write_text(json.dumps(saved))
    with pytest.raises(PortalDataError) as stopped:
        target_task(server, store)
    assert stopped.value.code == "flow_latex_base_required"
    assert store.pdf(original["resume_id"]) == old_pdf
