"""Content JSON handoffs use the normal fixed-input Flow continuation."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_canonical_career_sources import canonical as canonical
from test_experience_handoff_flow import begin, handoff
from test_full_latex_flow import candidate
from test_full_latex_flow import latex_flow as latex_flow


def test_content_handoff_continues_original_delivery_despite_live_input_drift(latex_flow):
    service, _, project = latex_flow
    progress = {}
    calls = []

    def generate(task):
        calls.append(task["id"])
        if len(calls) == 1:
            progress.update(
                handoff(task),
                generation_contract="content-writing/v1",
                fixed_inputs_revision="fixed-content-inputs",
            )
            return deepcopy(progress)
        return candidate(task)

    service.callbacks["resume"] = generate
    service.callbacks["experience_generation"] = lambda _: deepcopy(progress)
    task = begin(latex_flow)
    progress["status"] = "adopted"
    service.input_provider = lambda _: {
        "application_revision": service.applications.get_application(task["application_id"])[
            "revision"
        ],
        "inputs": {**task["inputs"], "sources_revision": "changed-live-library"},
    }
    (project / "main.tex").write_text("Changed external template")
    service.request(
        "resume-experience-generation",
        {"task_id": task["id"], "task_revision": task["revision"], "generation_id": progress["id"]},
    )
    result = wait_for(
        service, task["id"], lambda row: row["status"] in {"draft_ready", "failed", "stale"}
    )
    assert result["status"] == "draft_ready", result
    assert result["analysis_id"] == task["analysis_id"]
    assert calls == [task["id"], task["id"]]


@pytest.mark.parametrize(
    "field", ["application_id", "analysis_binding", "fixed_inputs_revision", "generation_contract"]
)
def test_content_handoff_rejects_changed_delivery_identity(latex_flow, field):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, _, _ = latex_flow
    progress = {}

    def generate(task):
        progress.update(
            handoff(task),
            generation_contract="content-writing/v1",
            fixed_inputs_revision="fixed-content-inputs",
        )
        return deepcopy(progress)

    service.callbacks["resume"] = generate
    service.callbacks["experience_generation"] = lambda _: deepcopy(progress)
    task = begin(latex_flow)
    progress["status"] = "adopted"
    progress[field] = (
        {"analysis_id": "another-analysis"}
        if field == "analysis_binding"
        else "fixed-writing/v1"
        if field == "generation_contract"
        else "another-delivery"
    )
    with pytest.raises(PortalDataError, match="固定经历交付"):
        service.request(
            "resume-experience-generation",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "generation_id": progress["id"],
            },
        )


@pytest.mark.parametrize(
    "retained_handoff", [False, True, "manual", "manual-unmerged", "refresh", "refresh-jd"]
)
def test_default_portal_prepares_json_with_the_existing_fixed_template(
    canonical, tmp_path, retained_handoff
):
    import json
    import subprocess

    from test_application_information import answer, tree_bytes, write_library
    from test_normal_retrieval_pipeline import RecordedPipeline, requirement
    from test_structured_career_store import facts

    from career_evidence_graph import application_experience_latex as generation
    from career_evidence_graph.career_experiences import ExperienceStore
    from career_evidence_graph.career_portal import create_server
    from career_evidence_graph.career_portal_data import ApplicationStore

    _, career_root, _, _, _, manifest, _ = canonical
    subprocess.run(["git", "init", "--quiet", "--template=", str(career_root)], check=True)
    (career_root / "sources").mkdir()
    profile = {
        "name": "Synthetic Applicant",
        "links": [{"label": "Original email", "href": "mailto:old@example.test"}],
        "education": [
            {
                "institution": "Synthetic University",
                "degree": "Mathematics",
                "period": "2020–2024",
                "detail": "Documented degree detail",
            }
        ],
    }
    (career_root / "sources/profile.json").write_text(json.dumps(profile))
    content = facts(candidate_id="unseen-identity")
    content["facts"][0]["text"] = "Studied cross-domain models with biology collaborators."
    ExperienceStore(career_root).save("unseen-identity", title=content["title"], content=content)
    library_root = tmp_path / "information"
    write_library(library_root, answers=dict([answer("Email", "current@example.test")]))
    career_before = tree_bytes(career_root)
    information_before = tree_bytes(library_root)
    project = tmp_path / "resume-template"
    project.mkdir()
    template = (
        "\\documentclass[10pt,a4paper]{article}\n"
        "\\usepackage[hidelinks]{hyperref}\n\\begin{document}\n"
        "\\textbf{Fixed Template Person}\\par\n"
        "\\href{mailto:fixed@example.test}{fixed@example.test}\\par\n"
        "\\section*{Education}\n"
        "Fixed University, BSc Mathematics, 2019--2023.\\par\n"
        "\\section*{Summary}\n%% TOMORROWSTAR_SUMMARY %%\n"
        "\\section*{Skills}\n%% TOMORROWSTAR_SKILLS %%\n"
        "\\section*{Experience}\n%% TOMORROWSTAR_EXPERIENCES %%\n"
        "\\end{document}\n"
    )
    (project / "main.tex").write_text(template)
    application_root = tmp_path / "applications"
    application_root.mkdir()
    applications = ApplicationStore(application_root)
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Research Engineer",
            "job_description": "Collaborate across scientific domains.",
        }
    )
    runner = RecordedPipeline([requirement("Collaborate across scientific domains")])
    with create_server(
        application_root,
        career_root,
        flow_root=tmp_path / "flow",
        career_library_manifest=manifest,
        information_library_root=library_root,
        flow_match_runner=runner,
        automatic_resume_author=False,
        write_admission_policy="development",
        preparation_only=True,
    ) as server:
        flow = server.application_flow_service
        # This fixture drives the resume handoff; sibling materials have their own tests.
        flow.callbacks.pop("cover_letter", None)
        flow.callbacks.pop("material_consistency", None)
        task = flow.create(job["id"], job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        assert not task.get("latex_base")
        before_calls = len(runner.calls)
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(
            flow, task["id"], lambda row: row["status"] in {"needs_input", "failed", "stale"}
        )
        assert task["status"] == "failed", task["stages"]["resume"]
        assert task["stages"]["resume"]["error_code"] == "resume_template_required"
        task = flow.bind_latex_base(task["id"], task["revision"], project, "main.tex")
        flow.start(task["id"], task["revision"], "resume")
        task = wait_for(
            flow, task["id"], lambda row: row["status"] in {"needs_input", "failed", "stale"}
        )
        assert task["status"] == "needs_input", task["stages"]["resume"]
        handoff = task["experience_handoff"]
        assert handoff["generation_contract"] == "content-writing/v1"
        assert handoff["analysis_binding"]["analysis_id"] == task["analysis_id"]
        from career_evidence_graph.career_portal_data import PortalDataError

        with pytest.raises(PortalDataError) as awaiting:
            flow.start(task["id"], task["revision"], "resume", retry=True)
        assert awaiting.value.code == "flow_generation_not_adopted"
        assert flow.snapshot(task["id"])["active_task"] == task
        # Model-facing content contains variable fields; literal identity stays in TeX.
        store = server.application_resume_store
        context = generation.generation_context(store, handoff["id"])
        assert context["content_plan"]["schema_version"] == "resume-template-plan/v1"
        assert "profile" not in context["content_plan"]
        assert "education" not in context["content_plan"]
        configured = generation.configure_generation(store, handoff["id"])
        for experience in configured["experiences"]:
            writer = generation.writer_context(store, handoff["id"], experience["experience_id"])
            assignment = writer["assignment"]
            assert "Fixed Template Person" not in json.dumps(writer)
            assert "fixed@example.test" not in json.dumps(writer)
            generation.submit_fragment(
                store,
                handoff["id"],
                experience["experience_id"],
                input_revision=writer["input_revision"],
                writer_id="synthetic-writer-" + experience["experience_id"],
                content_fragment={
                    "schema_version": "experience-writing/v1",
                    "assignment_revision": writer["input_revision"],
                    "experience_id": experience["experience_id"],
                    "candidate_id": assignment["candidate_id"],
                    "status": "complete",
                    "items": [
                        {
                            "id": "item-" + experience["experience_id"],
                            "text": (
                                "Planned cross-domain model research with biology collaborators."
                            ),
                            "fact_refs": assignment["allowed_fact_refs"][:1],
                        }
                    ],
                },
            )
        assembled = generation.assemble_generation(store, handoff["id"])
        assert "\\subsection*{Network research}" in assembled["latex_source"]
        assert "\\textbf{Fixed Template Person}\\par\n" in assembled["latex_source"]
        assert (
            "\\href{mailto:fixed@example.test}{fixed@example.test}\\par\n"
            in assembled["latex_source"]
        )
        assert "Fixed University, BSc Mathematics, 2019--2023.\\par\n" in assembled["latex_source"]
        assert "current@example.test" not in assembled["latex_source"]
        assert "old@example.test" not in assembled["latex_source"]
        review = generation.review_context(store, handoff["id"])
        assert "latex_source" not in review
        generation.review_generation(
            store,
            handoff["id"],
            candidate_sha256=review["candidate_sha256"],
            reviewer_id="synthetic-reviewer",
            passed=True,
            issues=[],
        )
        adopted = generation.adopt_generation(store, handoff["id"])
        assert adopted["resume_content"] == assembled["resume_content"]
        flow.request(
            "resume-experience-generation",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "generation_id": handoff["id"],
            },
        )
        completed = wait_for(
            flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed", "stale"}
        )
        assert completed["status"] == "draft_ready", completed
        assert completed["draft_id"] == adopted["id"]
        assert completed["analysis_id"] == task["analysis_id"]
        adopted_files = {
            path.relative_to(store.root / adopted["id"]): path.read_bytes()
            for path in (store.root / adopted["id"]).rglob("*")
            if path.is_file()
        }
        if retained_handoff in {"manual", "manual-unmerged"}:
            from pathlib import Path
            from types import SimpleNamespace

            store.prism_client = SimpleNamespace(open=lambda _: "http://127.0.0.1:8799/")
            store.model_runner = lambda *args, **kwargs: SimpleNamespace(
                structured_result={"patches": [], "notices": []}
            )
            editing = flow.begin_prism_edit(completed["id"], completed["revision"])
            session = editing["prism_edit"]
            main = Path(session["project_root"]) / session["main"]
            human_text = main.read_text().replace(
                "Planned cross-domain", "Human edited cross-domain"
            )
            if retained_handoff == "manual-unmerged":
                human_text = human_text.replace(
                    "\\section*{Experience}", "\\section*{Selected Experience}"
                )
            main.write_text(human_text)
            completed = flow.finish_prism_edit(editing["id"], editing["revision"])
            human = store.draft(completed["draft_id"])
            assert human["latex_source"] == human_text
            if retained_handoff == "manual-unmerged":
                assert "resume_content" not in human
                assert human["content_reconciliation"]["status"] == "unmerged"
            else:
                assert human["content_reconciliation"]["status"] == "mapped"
                item = human["resume_content"]["experiences"][0]["items"][0]
                assert item["text"].startswith("Human edited cross-domain")
                assert item["origin"] == "human" and item["protected"]
        if retained_handoff is True:
            # Historical completed tasks can still carry their adopted handoff.
            with flow.applications.write_lock():
                state = flow._load()
                current = flow._task(state, task["id"])
                current["experience_handoff"] = generation.generation_state(store, handoff["id"])
                flow._save(state)
            completed = flow.snapshot(task["id"])["active_task"]
        if retained_handoff in {"refresh", "refresh-jd"}:
            if retained_handoff == "refresh":
                experiences = ExperienceStore(career_root)
                previous = experiences.get("unseen-identity")
                changed = deepcopy(previous["content"])
                changed["facts"][0]["text"] = (
                    "Planned validation with biology collaborators under a revised protocol."
                )
                experiences.save(
                    "unseen-identity",
                    title=previous["title"],
                    content=changed,
                    expected_revision=previous["revision"],
                )
                career_before = tree_bytes(career_root)
            else:
                job = applications.update_application(
                    job["id"],
                    {
                        "job_description": (
                            "Collaborate across scientific domains and report findings."
                        )
                    },
                    job["revision"],
                )
            updated = flow.update_inputs(completed["id"], completed["revision"], job["revision"])
            assert updated["stages"]["analysis"]["status"] == "pending"
            assert updated["latex_base"] == task["latex_base"]
            flow.start(updated["id"], updated["revision"], "analysis")
            completed = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
            assert completed["analysis_id"] != task["analysis_id"]
            before_calls = len(runner.calls)
            flow.start(completed["id"], completed["revision"], "resume")
        else:
            flow.start(completed["id"], completed["revision"], "resume", retry=True)
        replacement = wait_for(
            flow,
            task["id"],
            lambda row: row["status"] in {"needs_input", "draft_ready", "failed", "stale"},
        )
        if retained_handoff == "manual-unmerged":
            for _ in range(2):
                assert replacement["status"] == "failed", replacement
                attempt = replacement["stages"]["resume"]
                assert attempt["error_code"] == "resume_content_manual_merge_required"
                assert attempt["retained_draft"] == {
                    "id": human["id"],
                    "draft_sha256": human["draft_sha256"],
                }
                flow.start(replacement["id"], replacement["revision"], "resume", retry=True)
                replacement = wait_for(flow, task["id"], lambda row: row["status"] == "failed")
            assert (
                replacement["stages"]["resume"]["error_code"]
                == "resume_content_manual_merge_required"
            )
            assert store.draft(human["id"])["latex_source"] == human_text
            assert len(runner.calls) == before_calls
            assert tree_bytes(career_root) == career_before
            assert tree_bytes(library_root) == information_before
            return
        assert replacement["status"] == "needs_input", replacement
        assert replacement["latex_base"] == task["latex_base"]
        assert "latex_base" not in replacement["stages"]["resume"]
        new_handoff = replacement["experience_handoff"]
        assert new_handoff["id"] != adopted["id"]
        replacement_context = generation.generation_context(store, new_handoff["id"])
        assert replacement_context["retained_content"] == (
            human["resume_content"] if retained_handoff == "manual" else adopted["resume_content"]
        )
        if retained_handoff == "manual":
            # The editor owns the live project; the immutable parent archives stay fixed.
            adopted_files[main.relative_to(store.root / adopted["id"])] = human_text.encode()
            assert store.draft(adopted["id"])["resume_content"] == adopted["resume_content"]
        assert adopted_files == {
            path.relative_to(store.root / adopted["id"]): path.read_bytes()
            for path in (store.root / adopted["id"]).rglob("*")
            if path.is_file()
        }
        if retained_handoff is True:
            assert replacement["experience_handoff_history"][-1]["id"] == adopted["id"]
            assert replacement["experience_handoff_history"][-1]["status"] == "adopted"
        assert len(runner.calls) == before_calls
    assert tree_bytes(career_root) == career_before
    assert tree_bytes(library_root) == information_before


def test_unknown_resume_result_cannot_be_replayed_by_an_explicit_retry(latex_flow):
    from career_evidence_graph.career_portal_data import PortalDataError

    service, task, _ = latex_flow
    service.callbacks["resume"] = lambda _: pytest.fail("Unknown work cannot be dispatched again")
    with service.applications.write_lock():
        state = service._load()
        current = service._task(state, task["id"])
        current["stages"]["resume"] = {"status": "needs_recheck", "attempt_id": "unknown-attempt"}
        current["status"] = "needs_recheck"
        service._save(state)
    before = service.snapshot(task["id"])["active_task"]
    with pytest.raises(PortalDataError) as error:
        service.start(before["id"], before["revision"], "resume", retry=True)
    assert error.value.code in {"flow_resume_recheck_required", "flow_batch_recheck_required"}
    assert service.snapshot(task["id"])["active_task"] == before
