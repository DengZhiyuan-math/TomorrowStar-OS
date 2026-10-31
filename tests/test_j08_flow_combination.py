"""Current JSON materials traverse the existing Flow without legacy review gates."""

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_flow import wait_for
from test_application_information import answer, tree_bytes, write_library
from test_application_resume import task_resume as task_resume
from test_automatic_material_reuse_edit import complete_portal as complete_portal
from test_canonical_career_sources import canonical as canonical
from test_full_latex_generation import full_latex as full_latex
from test_normal_retrieval_pipeline import RecordedPipeline, requirement
from test_p08_combination import SavedPrism
from test_p08_combination import combination as combination
from test_structured_career_store import facts

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore

TEMPLATE = (
    "\\documentclass{article}\n\\usepackage{hyperref}\n\\begin{document}\n"
    "Fixed Template Person\\par\n"
    "\\href{mailto:fixed@example.test}{fixed@example.test}\\par\n"
    "\\section*{Education}\nFixed University; documented degree in progress.\\par\n"
    "\\section*{Summary}\n%% TOMORROWSTAR_SUMMARY %%\n"
    "\\section*{Skills}\n%% TOMORROWSTAR_SKILLS %%\n"
    "\\section*{Experience}\n%% TOMORROWSTAR_EXPERIENCES %%\n"
    "\\end{document}\n"
)


class AllExperiences(RecordedPipeline):
    def __call__(self, config, prompt, **kwargs):
        result = super().__call__(config, prompt, **kwargs)
        if json.loads(config.output_schema.read_text()).get("title") == "_PageResult":
            context = json.loads(prompt.split("CONTEXT_JSON\n", 1)[1])
            result.structured_result["selections"] = [
                {
                    "candidate_id": row["candidate_id"],
                    "requirement_indexes": [0],
                    "rationale": "Read both relevant structured experiences.",
                }
                for row in context["records"]
            ]
        return result


@pytest.fixture
def json_flow(canonical, tmp_path, monkeypatch, request):
    _, career, _, _, _, manifest, _ = canonical
    subprocess.run(["git", "init", "--quiet", "--template=", str(career)], check=True)
    (career / "sources").mkdir()
    (career / "sources/profile.json").write_text(
        json.dumps({"name": "Library Person", "links": [], "education": []})
    )
    experiences = ExperienceStore(career)
    for candidate, title in (
        ("unseen-identity", "Network research"),
        ("second-work", "Validation research"),
    ):
        content = facts(
            candidate_id=candidate, experience_id="experience-" + candidate, title=title
        )
        content["facts"][0]["text"] = "Studied cross-domain models with biology collaborators."
        experiences.save(candidate, title=content["title"], content=content)
    catalog_path = career / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["records"].append(
        {
            "candidate_id": "second-work",
            "title": "Validation research",
            "record_class": "current-confirmed-identity",
            "accepted_reading_summary": "Recorded validation research.",
            "confirmed_identity_facts": {},
            "source_links": [],
        }
    )
    catalog_path.write_text(json.dumps(catalog))
    descriptor = json.loads(manifest.read_text())
    descriptor["catalog"]["sha256"] = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(descriptor))
    information = tmp_path / "information"
    write_library(information, answers=dict([answer("Email", "library@example.test")]))
    project = tmp_path / "template"
    project.mkdir()
    (project / "main.tex").write_text(TEMPLATE)
    applications_root = tmp_path / "applications"
    applications_root.mkdir()
    applications = ApplicationStore(applications_root)
    job = applications.create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Research Engineer",
            "job_description": "Collaborate across scientific domains.",
            "url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789012",
        }
    )
    runner = AllExperiences([requirement("Collaborate across scientific domains")])
    with create_server(
        applications_root,
        career,
        flow_root=tmp_path / "flow",
        worker_root=tmp_path / "worker",
        worker_live=True,
        career_library_manifest=manifest,
        information_library_root=information,
        flow_match_runner=runner,
        automatic_resume_author=getattr(request, "param", {}).get("automatic_resume_author", False),
        write_admission_policy="development",
    ) as server:
        monkeypatch.setattr(server.worker_service, "spawn", lambda: None)
        store = server.application_resume_store
        store.prism_client = SavedPrism()
        store.pdf_inspector = lambda _: 1

        def recorded_material_model(config, prompt, **kwargs):
            if "material-consistency" in config.workspace.parts:
                output = {"consistent": True, "issues": []}
            elif "cover-letters" in config.workspace.parts:
                if config.output_schema.name == "review-schema.json":
                    output = {"supported": True, "reason": "Bound synthetic facts."}
                else:
                    context = json.loads(prompt[prompt.index("\n{") + 1 :])
                    # Grouped prompts list library facts under their experience.
                    source = (
                        context["sources"]
                        + [
                            fact
                            for experience in context.get("experiences", [])
                            for fact in experience.get("facts", [])
                        ]
                    )[0]
                    output = {
                        "language": "en",
                        "paragraphs": [
                            {
                                "id": "technical-experience",
                                "kind": "fact",
                                "text": source["text"],
                                "source_ids": [source["source_id"]],
                                "source_quotes": [source["text"]],
                            }
                        ],
                    }
            else:
                output = {"patches": [], "notices": []}
            return SimpleNamespace(
                structured_result=output, model_dump=lambda **kwargs: {"structured_result": output}
            )

        store.model_runner = recorded_material_model
        yield SimpleNamespace(
            server=server,
            flow=server.application_flow_service,
            store=store,
            applications=applications,
            job=job,
            runner=runner,
            project=project,
            career=career,
            information=information,
            manifest=manifest,
        )


def start_json_writing(case, job=None, *, bind_template=True):
    job = job or case.job
    flow = case.flow
    task = flow.create(job["id"], job["revision"])
    flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(flow, task["id"], lambda row: row["status"] in {"analysis_ready", "failed"})
    assert task["status"] == "analysis_ready", task
    task = flow.prepare_automatic_materials(
        task["id"],
        task["revision"],
        **({"project_root": str(case.project), "main": "main.tex"} if bind_template else {}),
    )
    flow.start(task["id"], task["revision"], "resume")
    task = wait_for(flow, task["id"], lambda row: row["status"] in {"needs_input", "failed"})
    task = wait_for(
        flow,
        task["id"],
        lambda row: row.get("cover_letter", {}).get("status") not in {"queued", "running"},
    )
    assert task["status"] == "needs_input", task
    assert task["experience_handoff"]["generation_contract"] == "content-writing/v1"
    context = generation.generation_context(case.store, task["experience_handoff"]["id"])
    assert len(context["content_plan"]["assignments"]) == 2
    return task


def finish_json_writing(case, task):
    handoff = task["experience_handoff"]
    context = generation.generation_context(case.store, handoff["id"])
    assert "profile" not in context["content_plan"] and "education" not in context["content_plan"]
    assert "Fixed Template Person" not in json.dumps(context["content_plan"])
    state = generation.configure_generation(case.store, handoff["id"])
    for experience in state["experiences"]:
        writer = generation.writer_context(case.store, handoff["id"], experience["experience_id"])
        assignment = writer["assignment"]
        generation.submit_fragment(
            case.store,
            handoff["id"],
            experience["experience_id"],
            input_revision=writer["input_revision"],
            writer_id="recorded-writer-" + experience["experience_id"],
            content_fragment={
                "schema_version": "experience-writing/v1",
                "assignment_revision": writer["input_revision"],
                "experience_id": experience["experience_id"],
                "candidate_id": assignment["candidate_id"],
                "status": "complete",
                "items": [
                    {
                        "id": "item-" + experience["experience_id"],
                        "text": "Planned cross-domain model research with biology collaborators.",
                        "fact_refs": assignment["allowed_fact_refs"][:1],
                    }
                ],
            },
        )
    generation.assemble_generation(case.store, handoff["id"])
    review = generation.review_context(case.store, handoff["id"])
    generation.review_generation(
        case.store,
        handoff["id"],
        candidate_sha256=review["candidate_sha256"],
        reviewer_id="recorded-independent-reviewer",
        passed=True,
        issues=[],
    )
    adopted = generation.adopt_generation(case.store, handoff["id"])
    task = case.flow.task_snapshot(task["id"])
    case.flow.request(
        "resume-experience-generation",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "generation_id": handoff["id"],
        },
    )
    task = wait_for(case.flow, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
    task = wait_for(
        case.flow,
        task["id"],
        lambda row: row.get("material_consistency", {}).get("status") not in {"queued", "running"},
    )
    assert task["status"] == "draft_ready", task
    return task, adopted


def test_json_material_state_is_projected_for_clients_without_a_second_decision(json_flow):
    task, _ = finish_json_writing(json_flow, start_json_writing(json_flow))
    before = json_flow.flow.path.read_bytes()
    projection = json_flow.flow.snapshot(task["id"])
    assert projection["local_materials"] is True
    assert "local_materials" not in projection["active_task"]
    assert projection["active_task"]["revision"] == task["revision"]
    assert json_flow.flow.path.read_bytes() == before


@pytest.mark.parametrize("version", ["generated", "mapped", "unmerged", "education-layout"])
def test_next_json_job_reuses_fixed_template_instead_of_previous_rendered_resume(
    json_flow, version
):
    case = json_flow
    if version == "education-layout":
        main = case.project / "main.tex"
        main.write_text(
            TEMPLATE.replace(
                "Fixed University; documented degree in progress.\\par\n",
                "\\entry{Fixed University}{2020--present}\n"
                "\\textit{Documented degree in progress}\\par\n\\nopagebreak[4]\n",
            )
        )
    before = tree_bytes(case.project)
    task, draft = finish_json_writing(case, start_json_writing(case))
    original = draft
    if version in {"mapped", "unmerged"}:
        editing = case.flow.begin_prism_edit(task["id"], task["revision"])
        session = editing["prism_edit"]
        main = Path(session["project_root"]) / session["main"]
        edited = main.read_text().replace("Planned cross-domain", "Human cross-domain", 1)
        if version == "unmerged":
            edited = edited.replace(
                "\\begin{document}", "\\setlength{\\parindent}{7pt}\n\\begin{document}"
            )
        main.write_text(edited)
        task = case.flow.finish_prism_edit(editing["id"], editing["revision"])
        draft = case.store.draft(task["draft_id"])
        assert draft["content_reconciliation"]["status"] == version
    assert "%% TOMORROWSTAR_EXPERIENCES %%" not in draft["latex_source"]
    second = case.applications.create_application(
        {
            "company": "Second Synthetic Employer",
            "role_title": "Research Engineer",
            "job_description": "Collaborate across scientific domains.",
        }
    )
    next_task = start_json_writing(case, second, bind_template=False)
    context = generation.generation_context(case.store, next_task["experience_handoff"]["id"])
    assert context["content_plan"]["template_revision"] == original["template_revision"]
    assert tree_bytes(case.project) == before
    assert case.store.draft(original["id"])["resume_content"] == original["resume_content"]


def test_new_json_job_skips_newer_legacy_rendered_source_when_selecting_template(json_flow):
    case = json_flow
    task, original = finish_json_writing(case, start_json_writing(case))
    legacy_project = case.project.parent / "legacy-rendered"
    legacy_project.mkdir()
    (legacy_project / "main.tex").write_text(original["latex_source"])
    legacy_source = source_snapshot(legacy_project, "main.tex")
    # Restore a historical, pre-contract task after the current content version.
    # Its rendered source remains usable for legacy recovery, but has no slots.
    with case.applications.write_lock():
        state = case.flow._load()
        legacy = deepcopy(task)
        legacy.pop("material_contract")
        legacy.update(
            id="a" * 32, prism=legacy_source, source_checkpoint=legacy_source, artifacts=[]
        )
        state["tasks"].append(legacy)
        case.flow._save(state)
    second = case.applications.create_application(
        {
            "company": "Next Synthetic Employer",
            "role_title": "Research Engineer",
            "job_description": "Collaborate across scientific domains.",
        }
    )
    next_task = start_json_writing(case, second, bind_template=False)
    context = generation.generation_context(case.store, next_task["experience_handoff"]["id"])
    assert context["content_plan"]["template_revision"] == original["template_revision"]
    assert (legacy_project / "main.tex").read_text() == original["latex_source"]


@pytest.mark.parametrize("entry", ["automatic", "preparation"])
def test_new_json_template_can_be_first_bound_inside_git_without_hashing_git_metadata(
    json_flow, entry
):
    case = json_flow
    subprocess.run(["git", "init", "--quiet", "--template=", str(case.project)], check=True)
    before = tree_bytes(case.project)
    with create_server(
        case.applications.root,
        case.career,
        flow_root=case.project.parent / ("first-bind-" + entry),
        career_library_manifest=case.manifest,
        information_library_root=case.information,
        flow_match_runner=case.runner,
        write_admission_policy="development",
        preparation_only=entry == "preparation",
    ) as server:
        flow = server.application_flow_service
        task = flow.create(case.job["id"], case.job["revision"])
        flow.start(task["id"], task["revision"], "analysis")
        task = wait_for(flow, task["id"], lambda row: row["status"] == "analysis_ready")
        bind = flow.bind_latex_base if entry == "preparation" else flow.prepare_automatic_materials
        task = bind(task["id"], task["revision"], case.project, "main.tex")
        assert task["latex_base"]["source_policy"] == "generated-latex-project/v1"
        assert set(task["latex_base"]["files"]) == {"main.tex"}
        assert tree_bytes(case.project) == before


def test_new_default_raw_delivery_waits_for_content_import_without_legacy_writing(combination):
    case = combination
    before = tree_bytes(case.store.catalog.root)
    task = case.flow.create(case.job["id"], case.job["revision"])
    case.flow.start(task["id"], task["revision"], "analysis")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "analysis_ready")
    task = case.flow.prepare_automatic_materials(
        task["id"], task["revision"], str(case.project), "main.tex"
    )
    case.flow.start(task["id"], task["revision"], "resume")
    task = wait_for(case.flow, task["id"], lambda row: row["status"] in {"failed", "needs_input"})
    assert task["status"] == "failed"
    assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
    assert task["material_contract"] == "content-writing/v1"
    assert "experience_handoff" not in task
    assert tree_bytes(case.store.catalog.root) == before


@pytest.mark.parametrize("complete_portal", [{"new_task": True}], indirect=True)
def test_new_json_task_cannot_fall_back_to_pre_json_analysis_writing(complete_portal):
    server, store, task, calls = complete_portal
    assert task["material_contract"] == "content-writing/v1"
    assert task["status"] == "failed"
    assert task["stages"]["resume"]["error_code"] == "resume_content_material_required"
    assert calls == []
    assert not list(store.root.glob("*/draft.json"))
