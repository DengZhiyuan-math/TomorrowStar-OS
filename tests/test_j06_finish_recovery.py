"""Interrupted human-source finishing resumes only verifiable local work."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_resume import cached_resume as cached_resume
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_p05_generation import fixed as fixed
from test_p06_versions import material as material

from career_evidence_graph import application_resume_versions as versions
from career_evidence_graph.career_portal_data import PortalDataError


def opened(material):
    store, parent, calls = material
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    return store, parent, calls, editing, Path(editing["project_root"]) / editing["main"]


def test_saved_proofreading_response_is_adopted_without_second_model(material, monkeypatch):
    store, parent, calls, editing, main = opened(material)
    original = versions.helper.atomic_write_json
    interrupted = []

    def write(path, value):
        original(path, value)
        if path.name == "proofread-response.json" and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt()

    monkeypatch.setattr(versions.helper, "atomic_write_json", write)
    with pytest.raises(KeyboardInterrupt):
        store.finish_prism_edit(editing["id"])
    monkeypatch.setattr(versions.helper, "atomic_write_json", original)
    result = store.finish_prism_edit(editing["id"])
    assert result["latex_source"] == parent["latex_source"]
    assert len(calls) == 1
    assert store.finish_prism_edit(editing["id"])["id"] == result["id"]


def test_unknown_proofreading_call_waits_on_every_resume(material):
    store, parent, calls, editing, main = opened(material)

    def interrupted(*args, **kwargs):
        calls.append(True)
        raise KeyboardInterrupt()

    store.model_runner = interrupted
    with pytest.raises(KeyboardInterrupt):
        store.finish_prism_edit(editing["id"])
    for _ in range(2):
        with pytest.raises(PortalDataError) as error:
            store.finish_prism_edit(editing["id"])
        assert error.value.code == "prism_edit_needs_recheck"
    assert len(calls) == 1
    assert main.read_text() == parent["latex_source"]


def test_lost_patch_response_adopts_applied_source_without_second_write(material):
    store, parent, calls, editing, main = opened(material)
    before = main.read_text().replace(
        r"\end{document}", "we recieve reliable output.\n" + r"\end{document}"
    )
    main.write_text(before)
    start = before.index("recieve")
    patch = dict(
        start=start,
        end=start + 7,
        before="recieve",
        after="receive",
        kind="spelling",
        reason="Spelling",
    )
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    writer = store.prism_client.apply_proofread
    writes = []

    def interrupted(*args):
        writes.append(True)
        writer(*args)
        raise KeyboardInterrupt()

    store.prism_client.apply_proofread = interrupted
    with pytest.raises(KeyboardInterrupt):
        store.finish_prism_edit(editing["id"])
    result = store.finish_prism_edit(editing["id"])
    assert result["latex_source"] == before.replace("recieve", "receive")
    assert len(writes) == 1
    assert store.draft(parent["id"])["latex_source"] == parent["latex_source"]


def test_saved_proofread_preserves_newer_human_source(material, monkeypatch):
    store, parent, calls, editing, main = opened(material)
    original = versions.helper.atomic_write_json

    def write(path, value):
        original(path, value)
        if path.name == "proofread-result.json":
            raise KeyboardInterrupt()

    monkeypatch.setattr(versions.helper, "atomic_write_json", write)
    with pytest.raises(KeyboardInterrupt):
        store.finish_prism_edit(editing["id"])
    monkeypatch.setattr(versions.helper, "atomic_write_json", original)
    late = main.read_text() + "\n% newer manual edit\n"
    main.write_text(late)
    result = store.finish_prism_edit(editing["id"])
    assert result["prism_edit"]["status"] == "source_changed"
    assert result["latex_source"] == parent["latex_source"]
    assert main.read_text() == late
    assert len(calls) == 1


def test_saved_draft_is_adopted_after_session_commit_interruption(material, monkeypatch):
    store, parent, calls, editing, main = opened(material)
    original = versions.helper.atomic_write_json
    stopped = []

    def write(path, value):
        if path.name == "edit-session.json" and value.get("draft_id") and not stopped:
            stopped.append(True)
            raise KeyboardInterrupt()
        original(path, value)

    monkeypatch.setattr(versions.helper, "atomic_write_json", write)
    with pytest.raises(KeyboardInterrupt):
        store.finish_prism_edit(editing["id"])
    monkeypatch.setattr(versions.helper, "atomic_write_json", original)
    before_ids = {path.parent.name for path in store.root.glob("*/draft.json")}
    late = main.read_text() + "\n% later human save\n"
    main.write_text(late)
    result = store.finish_prism_edit(editing["id"])
    assert result["id"] in before_ids
    assert main.read_text() == late
    assert before_ids == {path.parent.name for path in store.root.glob("*/draft.json")}
    assert len(calls) == 1


def test_unconfirmed_patch_write_is_not_repeated(material):
    store, parent, calls, editing, main = opened(material)
    before = main.read_text().replace(
        r"\end{document}", "we recieve reliable output.\n" + r"\end{document}"
    )
    main.write_text(before)
    start = before.index("recieve")
    patch = dict(
        start=start,
        end=start + 7,
        before="recieve",
        after="receive",
        kind="spelling",
        reason="Spelling",
    )
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    writes = []

    def interrupted(*args):
        writes.append(True)
        raise KeyboardInterrupt()

    store.prism_client.apply_proofread = interrupted
    with pytest.raises(KeyboardInterrupt):
        store.finish_prism_edit(editing["id"])
    for _ in range(2):
        with pytest.raises(PortalDataError) as error:
            store.finish_prism_edit(editing["id"])
        assert error.value.code == "prism_edit_needs_recheck"
    assert writes == [True]
    assert main.read_text() == before


def template_parent(cached_resume, *, role=None):
    import hashlib

    from test_j05_content_adoption import prepared

    from career_evidence_graph.application_prism import archive_sources, source_snapshot
    from career_evidence_graph.application_resume_content import content_revision, validate_content
    from career_evidence_graph.application_resume_render import render_resume

    store, state, plan, _ = prepared(cached_resume)
    project = Path(state["request"]["latex_base"]["project_root"])
    template = (
        "\\documentclass{article}\n\\begin{document}\n"
        "Fixed Applicant, fixed@example.test\n"
        "\\section*{Education}\nFixed University, Fixed Degree; recieve documentary credit\n"
        "\\section*{Summary}\n%% TOMORROWSTAR_SUMMARY %%\n"
        "\\section*{Skills}\n%% TOMORROWSTAR_SKILLS %%\n"
        "\\section*{Experience}\n%% TOMORROWSTAR_EXPERIENCES %%\n"
        "\\end{document}\n"
    )
    (project / "main.tex").write_text(template)
    base = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    archive = archive_sources(base)
    (store.root / state["id"] / "base-sources.json").write_bytes(archive)
    state["request"]["latex_base"] = base
    state["base_sha256"] = hashlib.sha256(archive).hexdigest()
    content = plan["resume_content"]
    content.pop("profile")
    content.pop("education")
    content.update(
        schema_version="resume-template-content/v1", template_revision=versions.digest(template)
    )
    if role is not None:
        content["experiences"][0]["role"] = role
    content["revision"] = content_revision(content)
    content = validate_content(content).model_dump(mode="json")
    writing_plan = state["writing_plan"]
    writing_plan.pop("profile")
    writing_plan.pop("education")
    if role is not None:
        writing_plan["assignments"][0]["experience"]["role"] = role
    writing_plan.update(
        schema_version="resume-template-plan/v1", template_revision=versions.digest(template)
    )
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
    (store.root / state["id"] / "candidate-main.tex").write_text(rendered.tex)
    parent = versions.persist_content_generation(store, state, plan)
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    return store, parent


def test_human_wording_returns_to_content_and_reopens_with_fixed_template(cached_resume):
    store, parent = template_parent(cached_resume)
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    changed = main.read_text().replace("Implemented a validation", "Designed a validation")
    main.write_text(changed)
    result = store.finish_prism_edit(editing["id"])
    assert result["material_version_contract"] == "local-material/v1"
    assert "final_review" not in result
    assert result["content_reconciliation"]["status"] == "mapped"
    item = result["resume_content"]["experiences"][0]["items"][0]
    assert item["origin"] == "human" and item["protected"] is True
    assert item["text"].startswith("Designed a validation")
    assert result["latex_source"] == changed
    assert "Fixed Applicant" in changed and "Fixed University" in changed
    assert store.draft(result["id"])["resume_content"] == result["resume_content"]
    assert store.draft(parent["id"])["resume_content"] == parent["resume_content"]


def test_fixed_template_edit_remains_raw_without_claiming_rebuildability(cached_resume):
    store, parent = template_parent(cached_resume)
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    changed = main.read_text().replace("Fixed University", "Corrected University")
    main.write_text(changed)
    result = store.finish_prism_edit(editing["id"])
    assert result["content_reconciliation"]["status"] == "unmerged"
    assert result["parent_content_ref"]["content_revision"] == parent["content_revision"]
    assert "resume_content" not in result and "content_revision" not in result
    assert result["latex_source"] == changed
    assert store.draft(result["id"])["latex_source"] == changed


def test_saved_patch_receipt_preserves_late_edit_and_corrected_archive(material, monkeypatch):
    store, parent, calls, editing, main = opened(material)
    before = main.read_text().replace(
        r"\end{document}", "we recieve reliable output.\n" + r"\end{document}"
    )
    main.write_text(before)
    start = before.index("recieve")
    patch = dict(
        start=start,
        end=start + 7,
        before="recieve",
        after="receive",
        kind="spelling",
        reason="Spelling",
    )
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    original = versions.helper.atomic_write_json

    def write(path, value):
        original(path, value)
        if path.name == "proofread-write-receipt.json":
            raise KeyboardInterrupt()

    monkeypatch.setattr(versions.helper, "atomic_write_json", write)
    with pytest.raises(KeyboardInterrupt):
        store.finish_prism_edit(editing["id"])
    monkeypatch.setattr(versions.helper, "atomic_write_json", original)
    corrected = before.replace("recieve", "receive")
    late = corrected + "\n% newer human edit\n"
    main.write_text(late)
    store.prism_client.apply_proofread = lambda *a: pytest.fail("No second write")
    store.model_runner = lambda *a, **k: pytest.fail("No second model")
    result = store.finish_prism_edit(editing["id"])
    assert result["prism_edit"]["status"] == "source_changed"
    assert result["latex_source"] == corrected
    assert main.read_text() == late
    assert result["proofreading"]["patches"] == [patch]


@pytest.mark.parametrize("fixed", [False, True])
def test_proofreading_only_changes_variable_items(cached_resume, fixed):
    store, parent = template_parent(cached_resume)
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    before = main.read_text()
    if fixed:
        # Fixed education is ordinary prose to the generic TeX proofreader.
        token, after = "recieve", "receive"
    else:
        before = before.replace("Implemented a validation", "Implemented a validaton")
        token, after = "validaton", "validation"
    main.write_text(before)
    start = before.index(token)
    patch = dict(
        start=start,
        end=start + len(token),
        before=token,
        after=after,
        kind="spelling",
        reason="Synthetic small spelling change",
    )
    writes = []

    def writer(binding, expected, replacement):
        assert main.read_text() == expected
        writes.append(True)
        main.write_text(replacement)

    store.prism_client.apply_proofread = writer
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    result = store.finish_prism_edit(editing["id"])
    if fixed:
        assert result["latex_source"] == before
        assert result["proofreading"]["status"] == "unavailable"
        assert not writes
    else:
        assert result["latex_source"] == before.replace(token, after)
        assert result["proofreading"]["patches"] == [patch]
        assert writes == [True]


@pytest.mark.parametrize("unmerged", [False, True])
def test_manual_pdf_export_binds_content_reconciliation_and_source(cached_resume, unmerged):
    import hashlib
    import json
    from uuid import uuid4

    from career_evidence_graph.application_prism import dependency_snapshot

    store, parent = template_parent(cached_resume)
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    before, after = (
        ("Fixed University", "Updated University")
        if unmerged
        else ("Implemented a validation", "Designed a validation")
    )
    main.write_text(main.read_text().replace(before, after))
    draft = store.finish_prism_edit(editing["id"])
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

    store.prism_client.read_compiled = read_compiled
    result = store.capture_compiled_pdf(
        draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"], export_id=uuid4().hex
    )
    assert result["content_reconciliation"] == draft["content_reconciliation"]
    assert ("content_revision" in result) is not unmerged
    assert store.read_export(result["id"])["draft_sha256"] == draft["draft_sha256"]
    intent = json.loads((store.root / result["id"] / "export-intent.json").read_text())
    assert intent["content_revision"] == draft.get("content_revision")
    assert intent["template_revision"] == draft.get("template_revision")
    assert intent["content_reconciliation_revision"] == versions.digest(
        draft["content_reconciliation"]
    )
    assert main.read_text() == draft["latex_source"]


def test_proofreading_does_not_change_experience_heading(cached_resume):
    store, parent = template_parent(cached_resume, role="recieve")
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    before = main.read_text()
    experience = parent["resume_content"]["experiences"][0]
    start = before.index("recieve", parent["item_ranges"][experience["id"]][0])
    patch = dict(
        start=start,
        end=start + 7,
        before="recieve",
        after="receive",
        kind="spelling",
        reason="Synthetic spelling change",
    )
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    store.prism_client.apply_proofread = lambda *a: pytest.fail("No heading write")
    result = store.finish_prism_edit(editing["id"])
    assert result["latex_source"] == before
    assert result["proofreading"]["status"] == "unavailable"
