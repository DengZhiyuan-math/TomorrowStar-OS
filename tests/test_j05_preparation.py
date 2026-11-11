"""The existing handoff fills a fixed TeX template from variable content JSON."""

from copy import deepcopy

import pytest
from test_application_experience_latex import _fixed_job_brief, _fixed_material_packet
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_json_resume_template_content import TEMPLATE

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_worker import digest


@pytest.fixture
def content_delivery(full_latex, tmp_path):
    store, job, snapshot, analysis, _, _, _, inputs = full_latex
    analysis["role_understanding"] = {
        "business_objective": "Improve service decisions.",
        "work_outputs": ["Validated decisions"],
        "methods_role": "Use recorded research methods.",
    }
    analysis["job_brief"] = _fixed_job_brief(store, analysis, tmp_path)
    analysis["requirements"] = []
    packet = _fixed_material_packet(full_latex, tmp_path)
    rows = [row for row in packet["sources"].values() if row.get("source_kind") != "identity"][:2]
    for index, row in enumerate(rows):
        candidate = f"candidate-{index}"
        row["candidate_id"] = candidate
        row["record_context"] = {
            "candidate_id": candidate,
            "experience_id": f"experience-{index}",
            "content_revision": f"content-{index}",
            "title": f"Research {index}",
            "role": "Researcher",
            "fact_id": "fact-1",
            "source_refs": ["note-1"],
            "sources": [{"id": "note-1", "locator": f"notes/project-{index}.txt"}],
            "responsibility": "team",
            "status": "in_progress",
            "scope": "Experimental validation, no deployment.",
        }
    packet["sources"] = {row["source_id"]: row for row in rows}
    packet["revision"] = digest({k: v for k, v in packet.items() if k != "revision"})
    analysis["material_packet"] = packet
    receipt = {
        "schema_version": "controlled-inference/v1",
        "job_brief_revision": analysis["job_brief"]["revision"],
        "material_packet_revision": packet["revision"],
        "requirements": [],
    }
    receipt["revision"] = digest(receipt)
    analysis["inference_result"] = receipt
    project = tmp_path / "fixed-template"
    project.mkdir()
    (project / "main.tex").write_text(TEMPLATE)
    return store, job, snapshot, analysis, inputs, source_snapshot(project, "main.tex")


def prepare(delivery, **kwargs):
    store, job, snapshot, analysis, inputs, template = delivery
    kwargs.setdefault("latex_base", template)
    return generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=analysis,
        task_inputs=inputs,
        **kwargs,
    )


def test_semantic_handoff_only_delivers_variable_json_and_a_template_reference(content_delivery):
    store, *_ = content_delivery
    state = prepare(content_delivery)
    assert state["generation_contract"] == "content-writing/v1"
    context = generation.generation_context(store, state["id"])
    plan = context["content_plan"]
    assert plan["schema_version"] == "resume-template-plan/v1"
    assert plan["template_revision"] == digest(TEMPLATE)
    assert "profile" not in plan
    assert "education" not in plan
    assert "Fixed Applicant" not in str(context)
    assert "Fixed University" not in str(context)
    assert len(plan["assignments"]) == 2
    first, second = plan["assignments"]
    assert first["allowed_fact_refs"] != second["allowed_fact_refs"]
    assert first["experience"]["facts"][0]["responsibility"] == "team"
    assert first["experience"]["sources"][0]["locator"] == "notes/project-0.txt"
    assert "base" not in context
    assert "body_lines" not in context
    assert prepare(content_delivery)["id"] == state["id"]


def test_content_handoff_requires_a_fixed_tex_template(content_delivery):
    from career_evidence_graph.career_portal_data import PortalDataError

    with pytest.raises(PortalDataError) as caught:
        prepare(content_delivery, latex_base=None)
    assert caught.value.code == "resume_template_required"


def test_mixed_legacy_candidate_cannot_silently_disappear(content_delivery):
    from career_evidence_graph.career_portal_data import PortalDataError

    packet = content_delivery[3]["material_packet"]
    raw = deepcopy(next(iter(packet["sources"].values())))
    raw.update(
        source_id="legacy-source",
        candidate_id="legacy-experience",
        text="Unique recorded responsibility.",
    )
    raw["record_context"] = {"title": "Unconverted experience", "metadata": {}}
    packet["sources"][raw["source_id"]] = raw
    content_delivery[3]["selected_source_ids"].append(raw["source_id"])
    packet["revision"] = digest({k: v for k, v in packet.items() if k != "revision"})
    inference = content_delivery[3]["inference_result"]
    inference["material_packet_revision"] = packet["revision"]
    inference["revision"] = digest({k: v for k, v in inference.items() if k != "revision"})
    with pytest.raises(PortalDataError) as caught:
        prepare(content_delivery)
    assert caught.value.code == "resume_content_material_required"
    assert "legacy-source" in caught.value.message


def adopt(delivery, plan=None):
    store, *_ = delivery
    state = prepare(delivery)
    state = generation.configure_generation(store, state["id"], writing_plan=plan)
    for number, experience in enumerate(state["experiences"]):
        eid = experience["experience_id"]
        context = generation.writer_context(store, state["id"], eid)
        generation.submit_fragment(
            store,
            state["id"],
            eid,
            input_revision=context["input_revision"],
            writer_id=f"recorded-author-{number}",
            content_fragment={
                "schema_version": "experience-writing/v1",
                "status": "complete",
                "assignment_revision": context["input_revision"],
                "experience_id": eid,
                "candidate_id": context["candidate_id"],
                "items": [
                    {
                        "id": eid + "-item",
                        "text": "Contribute to recorded ongoing team work.",
                        "fact_refs": context["assignment"]["allowed_fact_refs"],
                    }
                ],
            },
        )
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="recorded-reviewer",
        passed=True,
        issues=[],
    )
    return generation.adopt_generation(store, state["id"])


def test_retained_json_is_the_baseline_without_requiring_a_tex_argument(content_delivery):
    store, *_ = content_delivery
    previous = adopt(content_delivery)
    state = prepare(content_delivery, retained_draft=previous)
    context = generation.generation_context(store, state["id"])
    assert context["retained_content"] == previous["resume_content"]
    generation.configure_generation(store, state["id"])
    assert store.draft(previous["id"])["resume_content"] == previous["resume_content"]


def test_newly_delivered_experience_is_not_misclassified_as_a_prior_omission(content_delivery):
    store, *_ = content_delivery
    initial = prepare(content_delivery)
    plan = generation.generation_context(store, initial["id"])["content_plan"]
    plan["assignments"] = plan["assignments"][:1]
    previous = adopt(content_delivery, plan)
    packet = content_delivery[3]["material_packet"]
    extra = deepcopy(next(iter(packet["sources"].values())))
    extra.update(source_id="newly-delivered", candidate_id="candidate-2")
    extra["record_context"].update(
        candidate_id="candidate-2", experience_id="experience-2", title="New research"
    )
    packet["sources"][extra["source_id"]] = extra
    packet["revision"] = digest({k: v for k, v in packet.items() if k != "revision"})
    inference = content_delivery[3]["inference_result"]
    inference["material_packet_revision"] = packet["revision"]
    inference["revision"] = digest({k: v for k, v in inference.items() if k != "revision"})
    state = prepare(content_delivery, retained_draft=previous)
    context = generation.generation_context(store, state["id"])
    assert context["retained_omitted_experience_ids"] == ["experience-1"]
    plan = context["content_plan"]
    plan["assignments"] = [
        row for row in plan["assignments"] if row["experience_id"] != "experience-1"
    ]
    configured = generation.configure_generation(store, state["id"], writing_plan=plan)
    assert [row["experience_id"] for row in configured["experiences"]] == [
        "experience-0",
        "experience-2",
    ]


def test_old_group_edit_cannot_replace_content_version_with_an_empty_body(content_delivery):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, *_ = content_delivery
    draft = adopt(content_delivery)
    before = {
        str(p.relative_to(store.root)): p.read_bytes() for p in store.root.rglob("*") if p.is_file()
    }
    with pytest.raises(PortalDataError) as caught:
        store.prepare_group_review(
            draft["id"], draft["draft_sha256"], task_inputs=draft["task_inputs"]
        )
    assert caught.value.code == "resume_content_edit_required"
    assert {
        str(p.relative_to(store.root)): p.read_bytes() for p in store.root.rglob("*") if p.is_file()
    } == before


def test_one_experience_cannot_mix_conflicting_documentary_headers(content_delivery):
    from career_evidence_graph.career_portal_data import PortalDataError

    packet = content_delivery[3]["material_packet"]
    first, second = packet["sources"].values()
    second["candidate_id"] = first["candidate_id"]
    second["record_context"] = deepcopy(first["record_context"])
    second["record_context"].update(fact_id="fact-2", title="Conflicting title")
    packet["revision"] = digest({k: v for k, v in packet.items() if k != "revision"})
    inference = content_delivery[3]["inference_result"]
    inference["material_packet_revision"] = packet["revision"]
    inference["revision"] = digest({k: v for k, v in inference.items() if k != "revision"})
    with pytest.raises(PortalDataError) as caught:
        prepare(content_delivery)
    assert caught.value.code == "resume_model_invalid"
