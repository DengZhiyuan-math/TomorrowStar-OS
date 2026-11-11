"""Imported human wording uses verified content mapping without invented generation."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_flow import application as application
from test_j05_preparation import adopt
from test_j05_preparation import content_delivery as content_delivery
from test_j05_preparation import full_latex as full_latex
from test_j05_preparation import task_resume as task_resume
from test_json_resume_content import fragment
from test_json_resume_template_content import TEMPLATE, plan

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.application_resume_content import assemble_content, content_revision
from career_evidence_graph.application_resume_render import render_resume
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


@pytest.fixture
def mapped_import(application, tmp_path):
    applications, job = application
    planned = plan() | {"application_id": job["id"]}
    content = assemble_content(planned, [fragment()])
    item = content["experiences"][0]["items"][0]
    item.update(origin="human", protected=True, edit_source="synthetic:accepted-tex")
    content["revision"] = content_revision(content)
    rendered = render_resume(content, template=TEMPLATE)
    project = tmp_path / "accepted-project"
    project.mkdir()
    (project / "main.tex").write_text(rendered.tex, encoding="utf-8")
    career = tmp_path / "career"
    career.mkdir()
    store = ApplicationResumeStore(applications, CareerCatalog(career), tmp_path / "resumes")
    store.model_runner = lambda *_args, **_kwargs: pytest.fail("No model calls on import")
    mapping = {
        "content": content,
        "template": TEMPLATE,
        "render_manifest": {
            "content_revision": rendered.content_revision,
            "template_revision": rendered.template_revision,
            "renderer_revision": rendered.renderer_revision,
            "ranges": {key: list(value) for key, value in rendered.ranges.items()},
            "tex_sha256": hashlib.sha256(rendered.tex.encode()).hexdigest(),
        },
        "provenance": {
            "source_locator": "synthetic:accepted-content.json",
            "source_sha256": hashlib.sha256(json.dumps(content).encode()).hexdigest(),
        },
    }
    return store, job, project, mapping


def import_mapped(fixture, mapping=None):
    store, job, project, original = fixture
    return store.import_latex_for_task(
        job["id"],
        job["revision"],
        task_inputs={"synthetic": "current"},
        prism=source_snapshot(project, "main.tex"),
        content_mapping=original if mapping is None else mapping,
    )


def test_public_import_preserves_content_and_truthful_origin_on_read(mapped_import):
    store, job, project, mapping = mapped_import
    before = deepcopy(mapping)
    imported = import_mapped(mapped_import)
    assert imported == store.draft(imported["id"])
    assert imported["origin"] == "existing_latex"
    assert imported["analysis_binding"] == {}
    assert imported["model_mode"] == "not_used"
    assert "generation_contract" not in imported
    assert imported["resume_content"] == mapping["content"]
    assert imported["content_template"] == TEMPLATE
    assert imported["render_manifest"] == mapping["render_manifest"]
    assert imported["item_ranges"] == mapping["render_manifest"]["ranges"]
    assert imported["latex_source"] == (project / "main.tex").read_text()
    assert imported["application_id"] == job["id"]
    assert mapping == before


def test_explicit_retained_pointer_is_verified_first_generation_fallback(mapped_import):
    store, job, _project, mapping = mapped_import
    imported = import_mapped(mapped_import)
    task = {
        "application_id": job["id"],
        "retained_baseline": {"id": imported["id"], "draft_sha256": imported["draft_sha256"]},
        "artifacts": [],
    }
    retained = store.retained_career_draft(task)
    assert retained == imported
    assert retained["resume_content"] == mapping["content"]
    task["retained_baseline"]["draft_sha256"] = "0" * 64
    with pytest.raises(PortalDataError) as changed:
        store.retained_career_draft(task)
    assert changed.value.code == "flow_draft_mismatch"
    task["retained_baseline"]["draft_sha256"] = imported["draft_sha256"]
    task["application_id"] = "another-application"
    with pytest.raises(PortalDataError) as foreign:
        store.retained_career_draft(task)
    assert foreign.value.code == "flow_draft_mismatch"


def test_explicit_baseline_does_not_bypass_missing_manual_history(mapped_import):
    store, job, _project, _mapping = mapped_import
    imported = import_mapped(mapped_import)
    with pytest.raises(PortalDataError) as missing:
        store.retained_career_draft(
            {
                "application_id": job["id"],
                "retained_baseline": {
                    "id": imported["id"],
                    "draft_sha256": imported["draft_sha256"],
                },
                "manual_latex_base": {"source_revision": "missing-saved-history"},
            }
        )
    assert missing.value.code == "flow_draft_mismatch"


def test_latest_adopted_human_edit_takes_precedence_over_initial_import(content_delivery):
    store, job, *_ = content_delivery
    generated = adopt(content_delivery)
    manifest = generated["render_manifest"]
    imported = store.import_latex_for_task(
        job["id"],
        job["revision"],
        task_inputs=generated["task_inputs"],
        prism=generated["source_checkpoint"],
        content_mapping={
            "content": generated["resume_content"],
            "template": TEMPLATE,
            "render_manifest": {
                key: manifest[key]
                for key in (
                    "content_revision",
                    "template_revision",
                    "renderer_revision",
                    "tex_sha256",
                )
            }
            | {"ranges": manifest["item_ranges"]},
            "provenance": {
                "source_locator": "synthetic:first-import-content.json",
                "source_sha256": "a" * 64,
            },
        },
    )
    task = {
        "application_id": job["id"],
        "retained_baseline": {"id": imported["id"], "draft_sha256": imported["draft_sha256"]},
        "artifacts": [{"stage": "resume", "adopted": True, "result": generated}],
    }
    assert store.retained_career_draft(task)["id"] == generated["id"]
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    editing = store.begin_prism_edit(
        generated["id"], generated["draft_sha256"], task_inputs=generated["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    main.write_text(
        main.read_text().replace(
            "Contribute to recorded ongoing team work.", "Human retained later wording.", 1
        )
    )
    child = store.finish_prism_edit(editing["id"])
    assert child["resume_content"]["experiences"][0]["items"][0]["origin"] == "human"
    task["artifacts"].append({"stage": "resume", "adopted": True, "result": child})
    retained = store.retained_career_draft(task)
    assert retained["id"] == child["id"]
    assert retained["resume_content"] == child["resume_content"]
    assert "Human retained later wording." in retained["latex_source"]
    task["retained_baseline"]["draft_sha256"] = "0" * 64
    with pytest.raises(PortalDataError) as bad_baseline:
        store.retained_career_draft(task)
    assert bad_baseline.value.code == "flow_draft_mismatch"
    task["retained_baseline"]["draft_sha256"] = imported["draft_sha256"]
    task["artifacts"][-1]["result"] = child | {"draft_sha256": "0" * 64}
    with pytest.raises(PortalDataError) as bad_latest:
        store.retained_career_draft(task)
    assert bad_latest.value.code == "flow_draft_mismatch"


@pytest.mark.parametrize(
    "mismatch",
    [
        "application",
        "content",
        "template",
        "renderer",
        "range",
        "tex_sha256",
        "extra_manifest",
        "tex",
    ],
)
def test_invalid_mapping_stops_before_new_material_version(mapped_import, mismatch):
    store, _job, project, original = mapped_import
    mapping = deepcopy(original)
    if mismatch == "application":
        mapping["content"]["application_id"] = "another-application"
        mapping["content"]["revision"] = content_revision(mapping["content"])
    elif mismatch == "content":
        mapping["content"]["experiences"][0]["items"][0]["text"] = "Changed human text."
    elif mismatch == "template":
        mapping["template"] = TEMPLATE.replace("Fixed Applicant", "Another Applicant")
    elif mismatch == "renderer":
        mapping["render_manifest"]["renderer_revision"] = "future-renderer/v2"
    elif mismatch == "range":
        mapping["render_manifest"]["ranges"]["item-demo-1"][0] += 1
    elif mismatch == "tex_sha256":
        mapping["render_manifest"]["tex_sha256"] = "0" * 64
    elif mismatch == "extra_manifest":
        mapping["render_manifest"]["unverified"] = True
    elif mismatch == "tex":
        with (project / "main.tex").open("a") as source:
            source.write("% Unmapped manual edit\n")
    before = list(store.root.iterdir())
    with pytest.raises(PortalDataError) as invalid:
        import_mapped(mapped_import, mapping)
    assert invalid.value.code == "resume_content_mapping_invalid"
    assert list(store.root.iterdir()) == before


def test_optional_tex_hash_and_tuple_ranges_are_normalized(mapped_import):
    store, _job, _project, original = mapped_import
    mapping = deepcopy(original)
    manifest = mapping["render_manifest"]
    del manifest["tex_sha256"]
    manifest["ranges"] = {key: tuple(value) for key, value in manifest["ranges"].items()}
    imported = import_mapped(mapped_import, mapping)
    assert imported == store.draft(imported["id"])
    assert imported["item_ranges"] == original["render_manifest"]["ranges"]


def test_each_read_rechecks_archived_mapping_even_after_successful_read(mapped_import):
    store, _job, _project, _mapping = mapped_import
    imported = import_mapped(mapped_import)
    assert store.draft(imported["id"]) == imported
    path = store.root / imported["id"] / "content-mapping.json"
    archived = json.loads(path.read_bytes())
    archived["provenance"]["source_locator"] = "synthetic:tampered-source"
    path.write_text(json.dumps(archived))
    with pytest.raises(PortalDataError) as tampered:
        store.draft(imported["id"])
    assert tampered.value.code == "resume_draft_invalid"
    with pytest.raises(PortalDataError) as retained:
        store.retained_career_draft(
            {
                "application_id": imported["application_id"],
                "retained_baseline": {
                    "id": imported["id"],
                    "draft_sha256": imported["draft_sha256"],
                },
            }
        )
    assert retained.value.code == "resume_draft_invalid"


def test_plain_tex_import_stays_unmapped_and_requires_no_new_mapping(mapped_import):
    store, job, project, _mapping = mapped_import
    imported = store.import_latex_for_task(
        job["id"],
        job["revision"],
        task_inputs={"synthetic": "current"},
        prism=source_snapshot(project, "main.tex"),
    )
    assert imported["origin"] == "existing_latex"
    assert not {"resume_content", "content_template", "render_manifest"} & imported.keys()
    assert store.draft(imported["id"]) == imported


def test_mapped_import_prism_edit_publishes_readable_human_content(mapped_import):
    store, _job, project, _mapping = mapped_import
    parent = import_mapped(mapped_import)
    parent_bytes = {p.name: p.read_bytes() for p in (store.root / parent["id"]).iterdir()}
    calls = []
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")

    def proofread(*_args, **_kwargs):
        calls.append("proofread")
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    store.model_runner = proofread
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = project / "main.tex"
    main.write_text(
        main.read_text().replace(
            "Participated in planning a validation workflow.", "Human retained validation work."
        )
    )
    child = store.finish_prism_edit(session["id"])
    assert child["content_reconciliation"]["status"] == "mapped"
    item = child["resume_content"]["experiences"][0]["items"][0]
    assert (item["text"], item["origin"], item["protected"]) == (
        "Human retained validation work.",
        "human",
        True,
    )
    assert child == store.finish_prism_edit(session["id"])
    assert store.draft(child["id"]) == {
        key: value for key, value in child.items() if key != "prism_edit"
    }
    assert child["parent_content_ref"]["draft_id"] == parent["id"]
    assert calls == ["proofread"]
    saved = json.loads((store.root / child["id"] / "draft.json").read_bytes())
    assert not {"content_mapping", "content_template", "request", "final_review"} & saved.keys()
    assert saved["manual_source"]["actor"] == "user"
    assert store.draft(parent["id"]) == parent
    assert {p.name: p.read_bytes() for p in (store.root / parent["id"]).iterdir()} == parent_bytes


@pytest.mark.parametrize("optional_hash", [False, True])
def test_unchanged_mapped_import_accepts_original_manifest_forms(mapped_import, optional_hash):
    store, _job, _project, original = mapped_import
    mapping = deepcopy(original)
    mapping["render_manifest"]["ranges"] = {
        key: tuple(value) for key, value in mapping["render_manifest"]["ranges"].items()
    }
    if not optional_hash:
        mapping["render_manifest"].pop("tex_sha256")
    parent = import_mapped(mapped_import, mapping)
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    child = store.finish_prism_edit(session["id"])
    assert child["content_reconciliation"]["status"] == "unchanged"
    assert child["resume_content"] == parent["resume_content"]
    assert child["latex_source"] == parent["latex_source"]
    assert (
        "content_mapping" not in child
        and "generation_contract" not in child
        and "final_review" not in child
    )
    assert store.draft(child["id"])["resume_content"] == parent["resume_content"]


def test_two_imported_human_successors_keep_order_omissions_and_template(mapped_import):
    store, job, project, mapping = mapped_import
    content = deepcopy(mapping["content"])
    first = content["experiences"][0]
    first["items"].append(
        {**deepcopy(first["items"][0]), "id": "deleted-item", "text": "Remove this detail."}
    )
    second = deepcopy(first)
    second.update(id="experience-second", candidate_id="candidate-second", title="Second work")
    second["items"] = [
        {**deepcopy(first["items"][0]), "id": "second-item", "text": "Second evidenced work."}
    ]
    content["experiences"].append(second)
    content["revision"] = content_revision(content)
    rendered = render_resume(content, template=TEMPLATE)
    mapping = {
        **mapping,
        "content": content,
        "render_manifest": {
            "content_revision": rendered.content_revision,
            "template_revision": rendered.template_revision,
            "renderer_revision": rendered.renderer_revision,
            "ranges": {key: list(value) for key, value in rendered.ranges.items()},
        },
    }
    (project / "main.tex").write_text(rendered.tex)
    parent = import_mapped(mapped_import, mapping)
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    expected = deepcopy(content)
    expected["experiences"] = [second, {**first, "items": first["items"][:1]}]
    expected["revision"] = content_revision(expected)
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    (project / "main.tex").write_text(render_resume(expected, template=TEMPLATE).tex)
    child = store.finish_prism_edit(session["id"])
    assert [row["id"] for row in child["resume_content"]["experiences"]] == [
        "experience-second",
        "experience-demo-1",
    ]
    assert child["retained_protected_scopes"] == ["experience-demo-1"]
    assert child["resume_content"]["experiences"][1]["items"][0]["origin"] == "human"
    assert (
        store.draft(child["id"])["latex_source"] == render_resume(expected, template=TEMPLATE).tex
    )
    session2 = store.begin_prism_edit(
        child["id"], child["draft_sha256"], task_inputs=child["task_inputs"]
    )
    expected2 = deepcopy(child["resume_content"])
    expected2["experiences"] = expected2["experiences"][:1]
    expected2["revision"] = content_revision(expected2)
    (project / "main.tex").write_text(render_resume(expected2, template=TEMPLATE).tex)
    grandchild = store.finish_prism_edit(session2["id"])
    assert grandchild["retained_omitted_experience_ids"] == ["experience-demo-1"]
    assert grandchild["base_checkpoint"] == child["base_checkpoint"]
    assert grandchild["parent_content_ref"]["draft_id"] == child["id"]
    assert store.draft(grandchild["id"])["resume_content"] == grandchild["resume_content"]
    retained = store.retained_career_draft(
        {
            "application_id": job["id"],
            "retained_baseline": {"id": parent["id"], "draft_sha256": parent["draft_sha256"]},
            "artifacts": [{"stage": "resume", "adopted": True, "result": grandchild}],
        }
    )
    assert retained["id"] == grandchild["id"]
    assert (
        Path(grandchild["base_checkpoint"]["project_root"]) / grandchild["base_checkpoint"]["main"]
    ).read_text() == TEMPLATE


def test_unmerged_imported_edit_keeps_exact_tex_and_can_return_to_mapping(mapped_import):
    store, _job, project, _mapping = mapped_import
    parent = import_mapped(mapped_import)
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    edited = parent["latex_source"].replace("Fixed Applicant", "Different fixed identity")
    (project / "main.tex").write_text(edited)
    child = store.finish_prism_edit(session["id"])
    assert child["content_reconciliation"]["status"] == "unmerged"
    assert child["latex_source"] == edited
    assert (
        not {
            "resume_content",
            "content_revision",
            "render_manifest",
            "content_mapping",
            "content_template",
        }
        & child.keys()
    )
    assert child["parent_content_ref"]["draft_id"] == parent["id"]
    assert store.draft(child["id"])["latex_source"] == edited
    session2 = store.begin_prism_edit(
        child["id"], child["draft_sha256"], task_inputs=child["task_inputs"]
    )
    restored = parent["latex_source"].replace(
        "Participated in planning a validation workflow.", "Human restored variable text."
    )
    (project / "main.tex").write_text(restored)
    grandchild = store.finish_prism_edit(session2["id"])
    assert grandchild["content_reconciliation"]["status"] == "mapped"
    assert grandchild["latex_source"] == restored
    assert (
        store.draft(grandchild["id"])["resume_content"]["experiences"][0]["items"][0]["text"]
        == "Human restored variable text."
    )


def test_imported_human_successor_supplies_real_template_for_retained_generation(content_delivery):
    from test_j05_preparation import prepare

    from career_evidence_graph import application_experience_latex as generation

    store, job, *_ = content_delivery
    generated = adopt(content_delivery)
    manifest = generated["render_manifest"]
    imported = store.import_latex_for_task(
        job["id"],
        job["revision"],
        task_inputs=generated["task_inputs"],
        prism=generated["source_checkpoint"],
        content_mapping={
            "content": generated["resume_content"],
            "template": TEMPLATE,
            "render_manifest": {
                key: manifest[key]
                for key in (
                    "content_revision",
                    "template_revision",
                    "renderer_revision",
                    "tex_sha256",
                )
            }
            | {"ranges": manifest["item_ranges"]},
            "provenance": {
                "source_locator": "synthetic:retained-import.json",
                "source_sha256": "a" * 64,
            },
        },
    )
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    session = store.begin_prism_edit(
        imported["id"], imported["draft_sha256"], task_inputs=imported["task_inputs"]
    )
    main = Path(session["project_root"]) / session["main"]
    main.write_text(
        main.read_text().replace(
            "Contribute to recorded ongoing team work.", "Retain this human wording.", 1
        )
    )
    child = store.finish_prism_edit(session["id"])
    store.model_runner = lambda *_a, **_k: pytest.fail(
        "Preparation must not call an author or compiler"
    )
    state = prepare(content_delivery, retained_draft=child, latex_base=child["base_checkpoint"])
    context = generation.generation_context(store, state["id"])
    assert context["retained_content"] == child["resume_content"]
    assert context["content_plan"]["template_revision"] == child["template_revision"]
    generation.configure_generation(store, state["id"])
    assert (
        store.draft(child["id"])["resume_content"]["experiences"][0]["items"][0]["text"]
        == "Retain this human wording."
    )


def test_imported_successor_rejects_forged_template_location(mapped_import):
    store, _job, _project, _mapping = mapped_import
    parent = import_mapped(mapped_import)
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    child = store.finish_prism_edit(session["id"])
    directory = store.root / child["id"]
    document = json.loads((directory / "draft.json").read_bytes())
    document["base_checkpoint"]["project_root"] = str(directory / "unrelated-template")
    (directory / "draft.json").write_text(json.dumps(document))
    integrity = json.loads((directory / "draft-integrity.json").read_bytes())
    integrity["sha256"] = hashlib.sha256((directory / "draft.json").read_bytes()).hexdigest()
    (directory / "draft-integrity.json").write_text(json.dumps(integrity))
    with pytest.raises(PortalDataError):
        store.draft(child["id"])


@pytest.mark.parametrize(
    "damage",
    [
        "mapping",
        "mapping_template",
        "mapping_range",
        "template_archive",
        "manifest",
        "parent_hash",
        "content_parent",
    ],
)
def test_mapped_import_successor_revalidates_all_saved_dependencies(mapped_import, damage):
    store, _job, _project, _mapping = mapped_import
    parent = import_mapped(mapped_import)
    calls = []
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")

    def runner(*_a, **_k):
        calls.append("proofread")
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    store.model_runner = runner
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    child = store.finish_prism_edit(session["id"])
    assert store.draft(child["id"])["id"] == child["id"]
    directory = store.root / child["id"]
    if damage.startswith("mapping"):
        path = store.root / parent["id"] / "content-mapping.json"
        data = json.loads(path.read_bytes())
        if damage == "mapping_template":
            data["template"] = data["template"].replace("Fixed Applicant", "Tampered identity")
        elif damage == "mapping_range":
            data["render_manifest"]["ranges"]["item-demo-1"][0] += 1
        else:
            data["provenance"]["source_locator"] = "synthetic:tampered"
        path.write_text(json.dumps(data))
    elif damage == "template_archive":
        (directory / "base-sources.json").write_text("{}")
    else:
        data = json.loads((directory / "draft.json").read_bytes())
        if damage == "manifest":
            data["render_manifest"]["item_ranges"]["item-demo-1"][0] += 1
        elif damage == "parent_hash":
            data["manual_source"]["parent_draft_sha256"] = "0" * 64
        else:
            data["parent_content_ref"]["draft_sha256"] = "0" * 64
        (directory / "draft.json").write_text(json.dumps(data))
        integrity = json.loads((directory / "draft-integrity.json").read_bytes())
        integrity["sha256"] = hashlib.sha256((directory / "draft.json").read_bytes()).hexdigest()
        (directory / "draft-integrity.json").write_text(json.dumps(integrity))
    before = len(list(store.root.glob("*/draft-integrity.json")))
    with pytest.raises(PortalDataError):
        store.draft(child["id"])
    with pytest.raises(PortalDataError):
        store.finish_prism_edit(session["id"])
    assert len(list(store.root.glob("*/draft-integrity.json"))) == before
    assert calls == ["proofread"]


def test_mapped_import_return_preserves_newer_live_source(mapped_import):
    store, _job, project, _mapping = mapped_import
    parent = import_mapped(mapped_import)
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = project / "main.tex"
    captured = main.read_text()
    calls = []

    def runner(*_a, **_k):
        calls.append("proofread")
        main.write_text(
            captured.replace(
                "Participated in planning a validation workflow.", "A newer human edit."
            )
        )
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    store.model_runner = runner
    child = store.finish_prism_edit(session["id"])
    assert child["prism_edit"]["status"] == "source_changed"
    assert child["latex_source"] == captured
    assert "A newer human edit." in main.read_text()
    assert store.draft(child["id"])["latex_source"] == captured
    assert store.finish_prism_edit(session["id"])["id"] == child["id"]
    assert calls == ["proofread"]


def test_mapped_import_finish_response_loss_reuses_saved_version(mapped_import, monkeypatch):
    from career_evidence_graph._vendor import job_apply_store as helper

    store, _job, _project, _mapping = mapped_import
    parent = import_mapped(mapped_import)
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    calls = []

    def runner(*_a, **_k):
        calls.append("proofread")
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    store.model_runner = runner
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    original = helper.atomic_write_json
    lost = []

    def save(path, value):
        if Path(path).name == "edit-session.json" and value.get("draft_id") and not lost:
            lost.append(value["draft_id"])
            raise OSError("Synthetic lost completion response")
        return original(path, value)

    monkeypatch.setattr(helper, "atomic_write_json", save)
    with pytest.raises(OSError, match="lost completion"):
        store.finish_prism_edit(session["id"])
    assert len(list(store.root.glob("*/draft-integrity.json"))) == 2
    child = store.finish_prism_edit(session["id"])
    assert child["id"] == lost[0]
    assert child["content_reconciliation"]["status"] == "unchanged"
    assert store.finish_prism_edit(session["id"]) == child
    assert len(list(store.root.glob("*/draft-integrity.json"))) == 2
    assert calls == ["proofread"]


def test_plain_import_prism_edit_does_not_gain_content_or_generation(mapped_import):
    store, job, project, _mapping = mapped_import
    parent = store.import_latex_for_task(
        job["id"],
        job["revision"],
        task_inputs={"synthetic": "current"},
        prism=source_snapshot(project, "main.tex"),
    )
    store.prism_client = SimpleNamespace(open=lambda _binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    edited = (
        (project / "main.tex").read_text().replace("Fixed Applicant", "Manually changed applicant")
    )
    (project / "main.tex").write_text(edited)
    child = store.finish_prism_edit(session["id"])
    assert child["latex_source"] == edited
    assert (
        not {
            "resume_content",
            "content_mapping",
            "content_template",
            "generation_contract",
            "final_review",
            "parent_content_ref",
        }
        & child.keys()
    )
    assert store.draft(child["id"])["latex_source"] == edited


@pytest.mark.parametrize("fixed_text", [False, True])
def test_imported_mapping_limits_proofreading_to_variable_content(mapped_import, fixed_text):
    store, _job, project, _mapping = mapped_import
    parent = import_mapped(mapped_import)
    writes = []
    main = project / "main.tex"

    def apply(_binding, before, after):
        assert main.read_text() == before
        writes.append(after)
        main.write_text(after)

    store.prism_client = SimpleNamespace(
        open=lambda _binding: "http://127.0.0.1:8799/", apply_proofread=apply
    )
    session = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    manual = main.read_text().replace(
        "Participated in planning a validation workflow.", "I recieve reliable output."
    )
    main.write_text(manual)
    before, after = ("progress", "progres") if fixed_text else ("recieve", "receive")
    offset = manual.index(before)
    patch = {
        "start": offset,
        "end": offset + len(before),
        "before": before,
        "after": after,
        "kind": "spelling",
        "reason": "Clear local spelling correction.",
    }
    store.model_runner = lambda *_a, **_k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    child = store.finish_prism_edit(session["id"])
    if fixed_text:
        assert writes == []
        assert child["prism_edit"]["status"] == "proofreading_unavailable"
        assert child["latex_source"] == manual
    else:
        assert writes == [manual.replace(before, after)]
        assert child["latex_source"] == main.read_text() == manual.replace(before, after)
        assert child["proofreading"]["patches"] == [patch]
    assert child["content_reconciliation"]["status"] == "mapped"
    assert store.draft(child["id"])["latex_source"] == child["latex_source"]
