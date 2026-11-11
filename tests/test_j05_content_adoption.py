"""Content versions use the existing immutable draft and export boundaries."""

import hashlib
import json
from uuid import uuid4

import pytest
from test_application_resume import cached_resume as cached_resume
from test_json_resume_render import resume_content, revised

from career_evidence_graph.application_prism import archive_sources, source_snapshot
from career_evidence_graph.application_resume_render import render_resume
from career_evidence_graph.career_portal_data import PortalDataError


def prepared(cached_resume):
    store, job, _ = cached_resume
    identifier = uuid4().hex
    directory = store.root / identifier
    project = directory / "project"
    project.mkdir(parents=True)
    original = "\\documentclass{article}\n\\begin{document}\nOriginal template\n\\end{document}\n"
    (project / "main.tex").write_text(original)
    (project / "note.txt").write_text("Preserved ancillary file")
    base = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    archive = archive_sources(base)
    (directory / "base-sources.json").write_bytes(archive)
    content = resume_content()
    content["application_id"] = job["id"]
    content = revised(content)
    rendered = render_resume(content)
    plan = {
        "resume_content": content,
        "latex_source": rendered.tex,
        "template_revision": rendered.template_revision,
        "renderer_revision": rendered.renderer_revision,
        "item_ranges": {key: list(value) for key, value in rendered.ranges.items()},
        "review_groups": [],
        "omitted_groups": [],
        "verification_queue": [],
        "limitations": [],
        "block_mapping": [],
    }
    (directory / "candidate-main.tex").write_text(rendered.tex)
    experience = content["experiences"][0]
    facts = {
        "schema_version": "experience-facts/v1",
        "revision": "facts-synthetic-v1",
        "experience_id": experience["id"],
        "candidate_id": experience["candidate_id"],
        **{
            key: experience[key]
            for key in ("title", "role", "organization", "start", "end", "location")
        },
        "sources": [{"id": "synthetic-source", "locator": "synthetic:fixture"}],
        "facts": [
            {
                "id": "fact-demo-1",
                "text": "Recorded workflow implementation.",
                "source_refs": ["synthetic-source"],
                "responsibility": "team",
                "status": "completed",
                "scope": "workflow",
            }
        ],
    }
    writing_plan = {
        "schema_version": "resume-plan/v1",
        "application_id": job["id"],
        "profile": content["profile"],
        "education": content["education"],
        "summary": [],
        "skills": [],
        "assignments": [
            {
                "schema_version": "experience-assignment/v1",
                "assignment_revision": "assignment-v1",
                "experience_id": experience["id"],
                "candidate_id": experience["candidate_id"],
                "experience": facts,
                "inferences": [],
                "allowed_fact_refs": ["fact-demo-1"],
                "allowed_inference_refs": [],
                "writing_requirements": ["Keep recorded responsibility"],
            }
        ],
    }
    state = {
        "id": identifier,
        "generation_contract": "content-writing/v1",
        "application_id": job["id"],
        "application_revision": job["revision"],
        "request": {"latex_base": base, "task_inputs": {"sources_revision": "synthetic"}},
        "configuration": {"kind": "synthetic-fixed"},
        "base_sha256": hashlib.sha256(archive).hexdigest(),
        "payload": {
            "analysis": {"analysis_id": "synthetic-analysis"},
            "job": {"company": job["company"], "role_title": job["role_title"]},
            "sources": [],
            "analysis_selected_source_ids": [],
        },
        "writing_plan": writing_plan,
        "review": {
            "passed": True,
            "content_revision": content["revision"],
            "candidate_sha256": hashlib.sha256(rendered.tex.encode()).hexdigest(),
        },
    }
    return store, state, plan, original


def test_adopted_content_is_readable_after_reopen_with_deterministic_build(cached_resume):
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    draft = persist_content_generation(store, state, plan)
    assert draft["generation_contract"] == "content-writing/v1"
    assert draft["resume_content"] == plan["resume_content"]
    assert draft["content_revision"] == plan["resume_content"]["revision"]
    assert "\\subsection*{Software Engineer}" in draft["latex_source"]
    assert store.draft(draft["id"])["resume_content"] == plan["resume_content"]
    assert (store.root / draft["id"] / "project/note.txt").read_text() == "Preserved ancillary file"
    manifest = json.loads((store.root / draft["id"] / "render-manifest.json").read_text())
    assert manifest["content_revision"] == draft["content_revision"]
    assert manifest["tex_sha256"] == hashlib.sha256(draft["latex_source"].encode()).hexdigest()
    assert cached_resume[2] == []


def test_adoption_is_immutable_and_preserves_edited_project(cached_resume):
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    path = store.root / state["id"] / "project/main.tex"
    path.write_text("Human edit awaiting reconciliation")
    with pytest.raises(PortalDataError, match="人工修改"):
        persist_content_generation(store, state, plan)
    assert path.read_text() == "Human edit awaiting reconciliation"
    assert not (path.parent.parent / "draft.json").exists()


def test_adoption_recovers_saved_render_without_overwriting_a_new_edit(cached_resume, monkeypatch):
    from career_evidence_graph import application_resume_versions as versions

    store, state, plan, _ = prepared(cached_resume)
    original_write = versions.helper.atomic_write_json

    def interrupted(path, value):
        if path.name == "content.json":
            raise KeyboardInterrupt("simulate process exit after rendered project write")
        return original_write(path, value)

    with monkeypatch.context() as scope:
        scope.setattr(versions.helper, "atomic_write_json", interrupted)
        with pytest.raises(KeyboardInterrupt):
            versions.persist_content_generation(store, state, plan)
    draft = versions.persist_content_generation(store, state, plan)
    saved = {
        path.name: path.read_bytes()
        for path in (store.root / state["id"]).iterdir()
        if path.is_file()
    }
    assert (
        versions.persist_content_generation(store, state, plan)["draft_sha256"]
        == draft["draft_sha256"]
    )
    assert saved == {
        path.name: path.read_bytes()
        for path in (store.root / state["id"]).iterdir()
        if path.is_file()
    }


@pytest.mark.parametrize("filename", ["content.json", "render-manifest.json", "latex-sources.json"])
def test_archived_content_build_tamper_rejected_on_reopen(cached_resume, filename):
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    draft = persist_content_generation(store, state, plan)
    (store.root / draft["id"] / filename).write_text("{}")
    with pytest.raises(PortalDataError) as error:
        store.draft(draft["id"])
    assert error.value.code == "resume_draft_invalid"


def test_automatic_pdf_export_carries_same_content_revision(cached_resume):
    from pathlib import Path
    from types import SimpleNamespace

    from career_evidence_graph.application_prism import dependency_snapshot
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    draft = persist_content_generation(store, state, plan)
    pdf = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()

    def read_compiled(binding):
        current = dependency_snapshot(
            Path(binding["project_root"]), binding["main"], binding["files"]
        )
        return {
            "binding": current,
            "pdf": pdf,
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
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            },
        }

    store.prism_client = SimpleNamespace(read_compiled=read_compiled)
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=draft["task_inputs"],
        export_id=uuid4().hex,
        prism=draft["source_checkpoint"],
        automatic_materials=True,
    )
    assert result["resume_content"] == draft["resume_content"]
    assert result["content_revision"] == draft["content_revision"]
    assert store.read_export(result["id"])["content_revision"] == draft["content_revision"]


def test_prism_human_source_keeps_parent_content_without_claiming_stale_json(cached_resume):
    from pathlib import Path
    from types import SimpleNamespace

    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    parent = persist_content_generation(store, state, plan)
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *args, **kwargs: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(session["project_root"]) / session["main"]
    edited = main.read_text().replace(
        "Implemented a validation", "HUMAN EDIT: Implemented a validation"
    )
    main.write_text(edited)
    child = store.finish_prism_edit(session["id"])
    assert child["latex_source"] == edited
    assert child["material_version_contract"] == "local-material/v1"
    assert "resume_content" not in child
    assert "content_revision" not in child
    assert "render_manifest" not in child
    assert store.draft(parent["id"])["resume_content"] == parent["resume_content"]
    assert store.draft(parent["id"])["latex_source"] == parent["latex_source"]
    task = {
        "application_id": child["application_id"],
        "job_binding": child["analysis_binding"].get("jd_revision"),
        "inputs": child["task_inputs"],
        "artifacts": [{"stage": "resume", "adopted": True, "result": {**child, "kind": "draft"}}],
    }
    assert store.retained_career_draft(task)["id"] == child["id"]


def test_adoption_rejects_renderable_content_with_foreign_fact_reference(cached_resume):
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    content = plan["resume_content"]
    content["experiences"][0]["items"][0]["fact_refs"] = ["foreign-fact"]
    content = revised(content)
    rendered = render_resume(content)
    plan.update(resume_content=content, latex_source=rendered.tex)
    state["review"].update(
        content_revision=content["revision"],
        candidate_sha256=hashlib.sha256(rendered.tex.encode()).hexdigest(),
    )
    (store.root / state["id"] / "candidate-main.tex").write_text(rendered.tex)
    with pytest.raises((PortalDataError, ValueError)):
        persist_content_generation(store, state, plan)


@pytest.mark.parametrize("change", [False, True])
def test_protected_human_content_is_retained_or_blocks_adoption(cached_resume, change):
    from copy import deepcopy

    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    retained = deepcopy(plan["resume_content"])
    item = retained["experiences"][0]["items"][0]
    item.update(origin="human", protected=True, edit_source="synthetic:user-edit")
    item["text"] = "Exact human description and order."
    retained = revised(retained)
    state["payload"]["retained_content"] = deepcopy(retained)
    candidate = deepcopy(retained)
    if change:
        candidate["experiences"][0]["items"][0]["text"] = (
            "An AI replacement of the human description."
        )
    candidate = revised(candidate)
    rendered = render_resume(candidate)
    plan.update(
        resume_content=candidate,
        latex_source=rendered.tex,
        item_ranges={key: list(value) for key, value in rendered.ranges.items()},
    )
    state["review"].update(
        content_revision=candidate["revision"],
        candidate_sha256=hashlib.sha256(rendered.tex.encode()).hexdigest(),
    )
    (store.root / state["id"] / "candidate-main.tex").write_text(rendered.tex)
    if change:
        with pytest.raises((PortalDataError, ValueError)):
            persist_content_generation(store, state, plan)
    else:
        draft = persist_content_generation(store, state, plan)
        assert (
            draft["resume_content"]["experiences"][0]["items"][0]
            == retained["experiences"][0]["items"][0]
        )


def test_unchanged_content_draft_remains_the_writing_baseline(cached_resume):
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared(cached_resume)
    draft = persist_content_generation(store, state, plan)
    task = {
        "application_id": draft["application_id"],
        "job_binding": draft["analysis_binding"].get("jd_revision"),
        "inputs": draft["task_inputs"],
        "artifacts": [{"stage": "resume", "adopted": True, "result": {**draft, "kind": "draft"}}],
    }
    assert store.retained_career_draft(task)["id"] == draft["id"]


def prepared_template(cached_resume):
    from career_evidence_graph.application_worker import digest

    store, state, plan, _ = prepared(cached_resume)
    directory = store.root / state["id"]
    template = (
        "\\documentclass{article}\n\\begin{document}\n"
        "Fixed Applicant \\href{https://fixed.example.test}{Website}\n"
        "\\section*{Education}\nFixed University, Fixed Degree\n"
        "\\section*{Summary}\n%% TOMORROWSTAR_SUMMARY %%\n"
        "\\section*{Skills}\n%% TOMORROWSTAR_SKILLS %%\n"
        "\\section*{Experience}\n%% TOMORROWSTAR_EXPERIENCES %%\n"
        "\\end{document}\n"
    )
    (directory / "project/main.tex").write_text(template)
    base = source_snapshot(
        directory / "project", "main.tex", source_policy="generated-latex-project/v1"
    )
    archive = archive_sources(base)
    (directory / "base-sources.json").write_bytes(archive)
    state["request"]["latex_base"] = base
    state["base_sha256"] = hashlib.sha256(archive).hexdigest()
    for value, schema in (
        (state["writing_plan"], "resume-template-plan/v1"),
        (plan["resume_content"], "resume-template-content/v1"),
    ):
        value.pop("profile")
        value.pop("education")
        value.update(schema_version=schema, template_revision=digest(template))
    from career_evidence_graph.application_resume_content import content_revision

    content = plan["resume_content"]
    content["revision"] = content_revision(content)
    rendered = render_resume(content, template=template)
    plan.update(
        resume_content=content,
        latex_source=rendered.tex,
        template_revision=rendered.template_revision,
        renderer_revision=rendered.renderer_revision,
        item_ranges={key: list(value) for key, value in rendered.ranges.items()},
    )
    state["review"].update(
        content_revision=content["revision"],
        candidate_sha256=hashlib.sha256(rendered.tex.encode()).hexdigest(),
    )
    (directory / "candidate-main.tex").write_text(rendered.tex)
    return store, state, plan, template


def test_adopted_variable_content_rebuilds_against_the_frozen_fixed_template(cached_resume):
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, template = prepared_template(cached_resume)
    draft = persist_content_generation(store, state, plan)
    content = json.loads((store.root / draft["id"] / "content.json").read_text())
    assert not {"profile", "education"} & content.keys()
    assert "Fixed Applicant" not in json.dumps(content)
    assert "Fixed University" not in json.dumps(content)
    assert "Fixed Applicant" in draft["latex_source"]
    assert "Fixed University, Fixed Degree" in draft["latex_source"]
    assert store.draft(draft["id"])["latex_source"] == render_resume(content, template=template).tex
    assert cached_resume[2] == []


def test_adoption_rejects_a_changed_frozen_template_binding(cached_resume):
    from career_evidence_graph.application_resume_versions import persist_content_generation

    store, state, plan, _ = prepared_template(cached_resume)
    state["writing_plan"]["template_revision"] = "another-template"
    with pytest.raises((ValueError, PortalDataError)):
        persist_content_generation(store, state, plan)
    assert not (store.root / state["id"] / "draft.json").exists()


def test_content_items_name_the_sources_their_facts_came_from():
    from career_evidence_graph.application_resume import _content_source_ids

    def source(identifier, fact):
        return {"source_id": identifier, "record_context": {"candidate_id": "c1", "fact_id": fact}}

    draft = {
        "resume_content": {
            "experiences": [{"items": [{"fact_refs": ["c1::f1"]}, {"fact_refs": ["c1::f3"]}]}]
        },
        "generation_sources": [source("S1", "f1"), source("S2", "f2"), source("S3", "f3")],
    }
    # Installed MC-11: template-content résumés reported no used sources, so the
    # match overview showed 0% résumé coverage for every generated résumé.
    assert _content_source_ids(draft) == ["S1", "S3"]
