"""Career headlines survive template preparation, manual edits and adoption."""

from pathlib import Path

from test_j05_preparation import content_delivery as content_delivery
from test_j05_preparation import full_latex as full_latex
from test_j05_preparation import prepare
from test_j05_preparation import task_resume as task_resume

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot


def _headline_delivery(delivery):
    *values, binding = delivery
    source = Path(binding["project_root"]) / binding["main"]
    source.write_text(
        source.read_text().replace(
            "\\begin{document}\n", "\\begin{document}\n%% TOMORROWSTAR_HEADLINE %%\n"
        )
    )
    return (*values, source_snapshot(source.parent, source.name))


def test_opted_in_template_requires_job_specific_headline(content_delivery):
    delivery = _headline_delivery(content_delivery)
    store, *_ = delivery
    state = prepare(delivery)
    context = generation.generation_context(store, state["id"])
    assert context["headline_required"] is True


def _adopt_headline(delivery):
    store, *_ = delivery
    state = prepare(delivery)
    plan = generation.generation_context(store, state["id"])["content_plan"]
    plan["headline"] = {
        "id": "career-headline",
        "text": "Quantitative Research",
        "fact_refs": plan["assignments"][0]["allowed_fact_refs"],
    }
    generation.configure_generation(
        store, state["id"], writing_plan=plan, main_writer_id="career-focus-writer"
    )
    for number, assigned in enumerate(plan["assignments"]):
        eid = assigned["experience_id"]
        context = generation.writer_context(store, state["id"], eid)
        generation.submit_fragment(
            store,
            state["id"],
            eid,
            input_revision=context["input_revision"],
            writer_id=f"experience-writer-{number}",
            content_fragment={
                "schema_version": "experience-writing/v1",
                "status": "complete",
                "assignment_revision": context["input_revision"],
                "experience_id": eid,
                "candidate_id": context["candidate_id"],
                "items": [
                    {
                        "id": eid + "-item",
                        "text": "Contribute to recorded research.",
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
        reviewer_id="independent-reviewer",
        passed=True,
        issues=[],
    )
    return generation.adopt_generation(store, state["id"])


def test_human_headline_deletion_survives_preparation(content_delivery):
    from types import SimpleNamespace

    delivery = _headline_delivery(content_delivery)
    store, *_ = delivery
    parent = _adopt_headline(delivery)
    assert (
        store.draft(parent["id"])["resume_content"]["headline"]["text"] == "Quantitative Research"
    )
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    start, end = parent["item_ranges"]["career-headline"]
    before = main.read_text()
    main.write_text(before[:start] + before[end:])
    child = store.finish_prism_edit(editing["id"])
    assert child["content_reconciliation"]["status"] == "mapped"
    assert "headline" not in child["resume_content"]
    assert child["retained_protected_scopes"] == ["headline"]
    state = prepare(delivery, retained_draft=child)
    context = generation.generation_context(store, state["id"])
    assert context["headline_required"] is True
    assert context["retained_protected_scopes"] == ["headline"]
    assert "headline" not in context["retained_content"]


def test_small_headline_spelling_patch_is_within_variable_content(content_delivery):
    from types import SimpleNamespace

    delivery = _headline_delivery(content_delivery)
    store, *_ = delivery
    parent = _adopt_headline(delivery)
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    main = Path(editing["project_root"]) / editing["main"]
    before = main.read_text().replace("Quantitative Research", "Quantitative reserch")
    main.write_text(before)
    start = before.index("reserch")
    patch = {
        "start": start,
        "end": start + len("reserch"),
        "before": "reserch",
        "after": "research",
        "kind": "spelling",
        "reason": "Correct a spelling error.",
    }
    writes = []

    def writer(binding, expected, replacement):
        assert main.read_text() == expected
        writes.append(True)
        main.write_text(replacement)

    store.prism_client.apply_proofread = writer
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [patch], "notices": []}
    )
    child = store.finish_prism_edit(editing["id"])
    assert writes == [True]
    assert child["latex_source"] == before.replace("reserch", "research")
    assert child["resume_content"]["headline"]["text"] == "Quantitative research"
    assert child["proofreading"]["patches"] == [patch]


def test_adoption_rejects_headline_reference_outside_delivered_facts(content_delivery):
    import json

    import pytest

    from career_evidence_graph.application_resume_content import content_revision
    from career_evidence_graph.application_resume_render import render_resume
    from career_evidence_graph.application_resume_versions import persist_content_generation

    delivery = _headline_delivery(content_delivery)
    store, *_ = delivery
    parent = _adopt_headline(delivery)
    directory = store.root / parent["id"]
    state = json.loads((directory / "experience-generation.json").read_text())
    candidate = json.loads((directory / "assembled-plan.json").read_text())
    content = candidate["resume_content"]
    content["headline"]["fact_refs"] = ["foreign-fact"]
    content["revision"] = content_revision(content)
    template = (Path(delivery[-1]["project_root"]) / delivery[-1]["main"]).read_text()
    rendered = render_resume(content, template=template)
    candidate.update(
        latex_source=rendered.tex,
        renderer_revision=rendered.renderer_revision,
        item_ranges={key: list(value) for key, value in rendered.ranges.items()},
    )
    with pytest.raises(ValueError, match="references are outside assigned experience"):
        persist_content_generation(store, state, candidate)


def test_adoption_preserves_human_headline_wording_and_deletion(content_delivery):
    import json
    from copy import deepcopy

    import pytest

    from career_evidence_graph.application_resume_content import content_revision
    from career_evidence_graph.application_resume_versions import persist_content_generation

    delivery = _headline_delivery(content_delivery)
    store, *_ = delivery
    parent = _adopt_headline(delivery)
    directory = store.root / parent["id"]
    state = json.loads((directory / "experience-generation.json").read_text())
    candidate = json.loads((directory / "assembled-plan.json").read_text())
    retained = deepcopy(candidate["resume_content"])
    retained["headline"].update(origin="human", protected=True, edit_source="synthetic:human-edit")
    retained["revision"] = content_revision(retained)
    state["payload"]["retained_content"] = retained
    with pytest.raises(ValueError, match="Protected human content was removed or replaced"):
        persist_content_generation(store, state, candidate)
    retained.pop("headline")
    retained["revision"] = content_revision(retained)
    state["payload"]["retained_protected_scopes"] = ["headline"]
    with pytest.raises(ValueError, match="Protected human item list or ordering differs"):
        persist_content_generation(store, state, candidate)
