"""A later fixed handoff retains actual TeX and historical omissions separately."""

from copy import deepcopy

from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_p05_generation import fixed as fixed
from test_p05_generation import submit

from career_evidence_graph import application_experience_latex as generation


def test_retained_current_spans_and_omission_history_survive_next_fixed_handoff(fixed):
    data, state, *_ = fixed
    store = data[0]
    for index in range(5):
        submit(fixed, index)
    context = generation.writer_context(store, state["id"], "experience-6")
    omitted = deepcopy(context["groups"])
    omitted[0]["disposition"] = "omit"
    generation.submit_fragment(
        store,
        state["id"],
        "experience-6",
        input_revision=context["input_revision"],
        groups=omitted,
        used_refs=context["source_ids"],
        issues=[],
        writer_id="writer-6",
    )
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer",
        passed=True,
        issues=[],
    )
    first = generation.adopt_generation(store, state["id"])
    assert "Project 6" not in first["latex_source"]
    request = dict(
        source_snapshot=data[2],
        analysis=data[3],
        task_inputs=data[7],
        latex_base=first["source_checkpoint"],
        retained_draft=first,
    )
    later = generation.prepare_generation(store, data[1]["id"], data[1]["revision"], **request)
    context = generation.generation_context(store, later["id"])
    groups = context["retained_output"]["groups"]
    assert len(groups) == 6
    later = generation.configure_generation(
        store,
        later["id"],
        groups=groups,
        experiences=[],
        organization_plan={
            "summary_focus": "Retain human content",
            "ordering_rationale": "Keep order",
        },
    )
    kept = generation.assemble_generation(store, later["id"])
    assert kept["latex_source"] == first["latex_source"]
    generation.review_generation(
        store,
        later["id"],
        candidate_sha256=kept["candidate_sha256"],
        reviewer_id="later-reviewer",
        passed=True,
        issues=[],
    )
    adopted = generation.adopt_generation(store, later["id"])
    assert adopted["latex_source"] == first["latex_source"]
    assert adopted["retained_omissions"][0]["title"] == "Project 6"
    assert generation.adopt_generation(store, later["id"])["id"] == adopted["id"]


def test_public_generation_entry_keeps_fixed_delivery_with_a_custom_model_runner(fixed):
    import json

    import pytest

    data, state, *_ = fixed
    store = data[0]
    request = json.loads((store.root / state["id"] / "experience-generation.json").read_text())[
        "request"
    ]
    store.model_runner = lambda *a, **k: pytest.fail(
        "Fixed writing cannot use the legacy model call"
    )
    result = store.generate_for_task(data[1]["id"], data[1]["revision"], draft_only=True, **request)
    assert result["kind"] == "experience_handoff"
    assert result["generation_contract"] == "fixed-writing/v1"
    assert result["id"] == state["id"]
