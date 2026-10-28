"""Fixed matching inferences stay closed over each writer's assigned facts."""

import json
from copy import deepcopy

from test_application_experience_latex import configure, submit
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_worker import digest


def _inference(requirement_id, source_ids, *, basis="Recorded work supports this requirement."):
    return {
        "requirement_id": requirement_id,
        "type": "semantic",
        "relation": "supports",
        "basis": basis,
        "expression_scope": "Explain only the recorded work.",
        "calculation": None,
        "facts": [
            {
                "id": f"fact-{index}",
                "source_id": sid,
                "source_revision": "fixed-source-revision",
                "quote_start": 0,
                "quote_end": len(f"Recorded work from {sid}"),
                "quote": f"Recorded work from {sid}",
            }
            for index, sid in enumerate(source_ids)
        ],
    }


def _set_inferences(data):
    analysis, output = data[3], data[6]
    source_ids = [group["source_ids"][0] for group in output["groups"][1:]]
    first, second = source_ids[:2]
    requirements = []
    cases = [("local-first", [first]), ("local-second", [second])]
    cases += [(f"local-{index}", [sid]) for index, sid in enumerate(source_ids[2:], 3)]
    cases.append(("joint", [first, second]))
    for rid, ids in cases:
        inference = _inference(rid, ids)
        requirements.append(
            {
                "source_ids": ids,
                "sources": [
                    {"source_id": sid, "quote": f"Recorded work from {sid}"} for sid in ids
                ],
                "citations": [
                    {"source_id": sid, "quote": f"Recorded work from {sid}"} for sid in ids
                ],
                "judgment": "supported",
                "inference": inference,
            }
        )
    analysis["selected_source_ids"] = source_ids
    analysis["requirements"] = requirements
    analysis["inference_result"] = {
        "schema_version": "controlled-inference/v1",
        "policy": {"scope": "This job only."},
        "job_brief_revision": "fixed-brief-revision",
        "material_packet_revision": "full-packet-revision",
        "requirements": [
            {"judgment": row["judgment"], **deepcopy(row["inference"])} for row in requirements
        ],
    }
    analysis["inference_result"]["revision"] = digest(analysis["inference_result"])
    return source_ids


def _prepare(data):
    store, job, sources, analysis, _, project, _, inputs = data
    return generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        task_inputs=inputs,
        latex_base=source_snapshot(project, "main.tex"),
    )


def test_fixed_result_reaches_main_and_review_but_writer_receives_only_closed_inferences(
    full_latex,
):
    source_ids = _set_inferences(full_latex)
    store, analysis = full_latex[0], full_latex[3]
    state = configure(full_latex, _prepare(full_latex))
    assert (
        generation.generation_context(store, state["id"])["inference_result"]
        == analysis["inference_result"]
    )
    writer = generation.writer_context(store, state["id"], "experience-1")
    assert [row["inference"]["requirement_id"] for row in writer["requirements"]] == ["local-first"]
    result = writer["inference_result"]
    assert [row["requirement_id"] for row in result["requirements"]] == ["local-first"]
    assert result["source_ids"] == [source_ids[0]]
    assert source_ids[1] not in json.dumps(writer)
    assert "material_packet_revision" not in result
    assert result["revision"] != analysis["inference_result"]["revision"]
    # The boundary requires all cited facts together, rather than silently
    # stripping the second fact and presenting the joint conclusion as complete.
    joint = generation._scoped_inference_result(analysis, source_ids[:2])
    assert [row["requirement_id"] for row in joint["requirements"]] == [
        "local-first",
        "local-second",
        "joint",
    ]
    for index in range(6):
        submit(full_latex, state, index)
    generation.assemble_generation(store, state["id"])
    assert (
        generation.review_context(store, state["id"])["inference_result"]
        == analysis["inference_result"]
    )


def test_unrelated_inference_and_packet_revision_do_not_discard_completed_writer(full_latex):
    _set_inferences(full_latex)
    store, analysis = full_latex[0], full_latex[3]
    state = configure(full_latex, _prepare(full_latex))
    submit(full_latex, state, 0)
    submit(full_latex, state, 1)
    before = {row["experience_id"]: row["input_revision"] for row in state["experiences"]}
    analysis["requirements"][1]["inference"]["basis"] = (
        "A revised explanation for the second source."
    )
    result = analysis["inference_result"]
    result["requirements"][1]["basis"] = analysis["requirements"][1]["inference"]["basis"]
    result["material_packet_revision"] = "unrelated-packet-revision"
    result["revision"] = "new-global-inference-revision"
    successor = configure(full_latex, _prepare(full_latex))
    after = {row["experience_id"]: row["input_revision"] for row in successor["experiences"]}
    assert after["experience-1"] == before["experience-1"]
    assert after["experience-2"] != before["experience-2"]
    assert generation.generation_state(store, successor["id"])["completed_experience_ids"] == [
        "experience-1"
    ]


def test_related_expression_change_invalidates_only_assigned_writer(full_latex):
    _set_inferences(full_latex)
    store, analysis = full_latex[0], full_latex[3]
    state = configure(full_latex, _prepare(full_latex))
    submit(full_latex, state, 0)
    submit(full_latex, state, 1)
    scope = "Explain the recorded work using a narrower responsibility statement."
    analysis["requirements"][0]["inference"]["expression_scope"] = scope
    analysis["inference_result"]["requirements"][0]["expression_scope"] = scope
    successor = configure(full_latex, _prepare(full_latex))
    assert generation.generation_state(store, successor["id"])["completed_experience_ids"] == [
        "experience-2"
    ]


def test_requirement_citations_cannot_leak_foreign_sources_even_if_fact_list_is_local():
    local, foreign = "source-local", "source-foreign"
    payload = {
        "requirements": [
            {
                "source_ids": [local],
                "sources": [{"source_id": foreign, "quote": "Foreign recorded work."}],
                "inference": _inference("mismatched", [local]),
            }
        ]
    }
    assert generation._writer_requirements(payload, [local]) == []
