"""Fixed writing handoffs preserve upstream decisions and use one semantic review."""

import json
from copy import deepcopy

import pytest
from test_application_experience_latex import _fixed_job_brief, _fixed_material_packet
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def fixed(full_latex, tmp_path):
    store, job, snapshot, analysis, _, project, output, inputs = full_latex
    analysis["role_understanding"] = {
        "business_objective": "Improve service operations.",
        "work_outputs": ["Reliable service decisions"],
        "methods_role": "Python supports the service decisions.",
    }
    analysis["job_brief"] = _fixed_job_brief(store, analysis, tmp_path)
    source_ids = [group["source_ids"][0] for group in output["groups"][1:]]
    # Matching selected only one item; writing is free to use all delivered facts.
    analysis["selected_source_ids"] = source_ids[:1]
    analysis["requirements"] = []
    for index, sid in enumerate(source_ids):
        inference = {
            "requirement_id": f"requirement-{index}",
            "type": "semantic",
            "relation": "supports",
            "basis": "Recorded service work supports this requirement.",
            "expression_scope": "Describe the recorded service contribution.",
            "calculation": None,
            "facts": [{"id": f"fact-{index}", "source_id": sid, "quote": "Recorded work"}],
        }
        analysis["requirements"].append(
            {"source_ids": [sid], "judgment": "supported", "inference": inference}
        )
    analysis["material_packet"] = _fixed_material_packet(full_latex, tmp_path)
    receipt = {
        "schema_version": "controlled-inference/v1",
        "job_brief_revision": analysis["job_brief"]["revision"],
        "material_packet_revision": analysis["material_packet"]["revision"],
        "requirements": [
            {"judgment": row["judgment"], **deepcopy(row["inference"])}
            for row in analysis["requirements"]
        ],
    }
    receipt["revision"] = digest(receipt)
    analysis["inference_result"] = receipt
    state = generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=analysis,
        task_inputs=inputs,
        latex_base=source_snapshot(project, "main.tex"),
    )
    experiences = [
        {
            "experience_id": f"experience-{i}",
            "source_ids": group["source_ids"],
            "group_indexes": [i],
            "business_relevance": "Recorded service delivery.",
            "evidence_role": "direct_domain",
            "focus": "Explain contribution and result.",
        }
        for i, group in enumerate(output["groups"])
        if i
    ]
    plan = {
        "summary_focus": "Service delivery",
        "ordering_rationale": "Lead with relevant service work.",
    }
    state = generation.configure_generation(
        store, state["id"], groups=output["groups"], experiences=experiences, organization_plan=plan
    )
    return full_latex, state, experiences, plan


def submit(fixed, index=0, **kwargs):
    data, state, *_ = fixed
    store = data[0]
    experience = state["experiences"][index]
    context = generation.writer_context(store, state["id"], experience["experience_id"])
    return generation.submit_fragment(
        store,
        state["id"],
        experience["experience_id"],
        input_revision=context["input_revision"],
        groups=context["groups"],
        used_refs=[context["source_ids"][0]],
        issues=[],
        writer_id=f"writer-{index}",
        **kwargs,
    )


def complete(fixed):
    for index in range(6):
        submit(fixed, index)
    return generation.assemble_generation(fixed[0][0], fixed[1]["id"])


def test_fixed_writing_uses_nonpreselected_sources_without_read_approval(fixed):
    data, state, *_ = fixed
    store = data[0]
    assert state["generation_contract"] == "fixed-writing/v1"
    assert len(state["experiences"]) == 6
    context = generation.writer_context(store, state["id"], "experience-2")
    assert "requirement-1" in context["allowed_refs"]
    assert "fact-1" in context["allowed_refs"]
    assert "credibility" in context["instructions"]
    candidate = complete(fixed)
    assert len(candidate["fragments"]) == 6
    assert data[4] == []
    assert data[3]["selected_source_ids"] == [state["experiences"][0]["source_ids"][0]]
    assert (
        not (store.root / state["id"] / "experience-generation.json").read_text().count('"reads"')
    )


def test_fixed_work_survives_live_library_jd_configuration_and_base_changes(fixed, monkeypatch):
    data, state, *_ = fixed
    store = data[0]
    complete(fixed)
    (data[5] / "main.tex").write_text("Changed current external template")
    monkeypatch.setattr(store, "_task_current", lambda *a, **k: pytest.fail("No live task check"))
    monkeypatch.setattr(store, "configuration", lambda: pytest.fail("No live configuration check"))
    generation.generation_state(store, state["id"])
    context = generation.review_context(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=context["candidate_sha256"],
        reviewer_id="reviewer",
        passed=True,
        issues=[],
    )
    draft = generation.adopt_generation(store, state["id"])
    assert draft["latex_source"] == context["latex_source"]
    assert generation.adopt_generation(store, state["id"])["id"] == draft["id"]


def test_unrelated_global_plan_change_preserves_successful_fragments(fixed):
    data, state, experiences, plan = fixed
    for index in range(6):
        submit(fixed, index)
    changed = generation.configure_generation(
        data[0],
        state["id"],
        groups=data[6]["groups"],
        experiences=experiences,
        organization_plan=plan | {"summary_focus": "Revised global summary focus."},
    )
    assert len(changed["completed_experience_ids"]) == 6


def test_missing_fragment_stops_assembly_and_only_failed_writer_resumes(fixed):
    data, state, *_ = fixed
    for index in range(5):
        submit(fixed, index)
    experience = state["experiences"][5]
    generation.submit_fragment(
        data[0],
        state["id"],
        experience["experience_id"],
        input_revision=experience["input_revision"],
        status="missing_details",
        used_refs=[],
        issues=["Need an explicit detail"],
        writer_id="writer-5",
    )
    with pytest.raises(PortalDataError):
        generation.assemble_generation(data[0], state["id"])
    submit(fixed, 5)
    assert len(generation.assemble_generation(data[0], state["id"])["fragments"]) == 6


def test_single_review_applies_local_patch_and_adopts_patched_candidate(fixed):
    data, state, *_ = fixed
    store = data[0]
    candidate = complete(fixed)
    block = next(row for row in state["writing_plan"]["blocks"] if row["owner"] == "experience-1")
    original = data[6]["groups"][1]["latex"]
    patched = original.replace("Analyzed strategy;", "Analyzed the recorded strategy;")
    result = generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer",
        passed=True,
        issues=[],
        patches=[{"block_id": block["block_id"], "expected_latex": original, "latex": patched}],
    )
    assert result["candidate_sha256"] != candidate["candidate_sha256"]
    assert result["review"]["candidate_sha256"] == result["candidate_sha256"]
    draft = generation.adopt_generation(store, state["id"])
    assert patched in draft["latex_source"]
    assert draft["final_review"]["candidate_sha256"] == result["candidate_sha256"]


def test_review_rewrite_reuses_other_fragments_and_requires_same_reviewer(fixed):
    data, state, *_ = fixed
    store = data[0]
    candidate = complete(fixed)
    result = generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer",
        passed=False,
        issues=["Rewrite only the first experience"],
        rewrite_experience_ids=["experience-1"],
    )
    assert len(result["completed_experience_ids"]) == 5
    submit(fixed)
    candidate = generation.assemble_generation(store, state["id"])
    with pytest.raises(PortalDataError, match="同一"):
        generation.review_generation(
            store,
            state["id"],
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="second-reviewer",
            passed=True,
            issues=[],
        )
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer",
        passed=True,
        issues=[],
    )
    assert generation.adopt_generation(store, state["id"])["origin"] == "generated_latex"


@pytest.mark.parametrize("damage", ["foreign_ref", "stale_input", "full_document"])
def test_fragment_rejects_unassigned_references_stale_versions_and_document_structure(
    fixed, damage
):
    data, state, *_ = fixed
    context = generation.writer_context(data[0], state["id"], "experience-1")
    groups = deepcopy(context["groups"])
    revision, refs = context["input_revision"], context["source_ids"]
    if damage == "foreign_ref":
        refs = ["not-delivered"]
    elif damage == "stale_input":
        revision = "old"
    else:
        groups[0]["latex"] = "\\documentclass{article}"
    with pytest.raises(PortalDataError):
        generation.submit_fragment(
            data[0],
            state["id"],
            "experience-1",
            input_revision=revision,
            groups=groups,
            used_refs=refs,
            issues=[],
            writer_id="writer",
        )


def test_review_cannot_patch_fixed_identity_or_stale_text(fixed):
    data, state, *_ = fixed
    candidate = complete(fixed)
    for block, expected in [
        (state["writing_plan"]["blocks"][0], data[6]["groups"][0]["latex"]),
        (state["writing_plan"]["blocks"][1], "wrong old text"),
    ]:
        with pytest.raises(PortalDataError):
            generation.review_generation(
                data[0],
                state["id"],
                candidate_sha256=candidate["candidate_sha256"],
                reviewer_id="reviewer",
                passed=True,
                issues=[],
                patches=[
                    {
                        "block_id": block["block_id"],
                        "expected_latex": expected,
                        "latex": "Changed\n",
                    }
                ],
            )


def test_fixed_input_tampering_is_detected_without_live_scan(fixed):
    data, state, *_ = fixed
    path = data[0].root / state["id"] / "experience-generation.json"
    saved = json.loads(path.read_text())
    saved["payload"]["job"]["role_title"] = "Changed silently"
    path.write_text(json.dumps(saved))
    with pytest.raises(PortalDataError, match="固定"):
        generation.generation_state(data[0], state["id"])


def test_identical_fixed_request_reuses_saved_task_after_configuration_changes(fixed, monkeypatch):
    data, state, *_ = fixed
    saved = json.loads((data[0].root / state["id"] / "experience-generation.json").read_text())
    monkeypatch.setattr(
        data[0],
        "configuration",
        lambda: pytest.fail("Saved task needs no fresh model configuration"),
    )
    assert (
        generation.prepare_generation(
            data[0], data[1]["id"], data[1]["revision"], **saved["request"]
        )["id"]
        == state["id"]
    )


def test_main_global_block_has_unique_owner_and_does_not_require_writer_read_approval(fixed):
    data, state, experiences, plan = fixed
    groups = deepcopy(data[6]["groups"])
    groups[1]["latex"] = (
        "\\section*{Summary}\nService delivery supported by recorded Python work.\n"
    )
    plan |= {"positioning_group_indexes": [1], "positioning_writer_id": "main-agent"}
    state = generation.configure_generation(
        data[0], state["id"], groups=groups, experiences=experiences[1:], organization_plan=plan
    )
    local = (data, state, experiences[1:], plan)
    assert (
        next(block for block in state["writing_plan"]["blocks"] if block["group_index"] == 1)[
            "owner"
        ]
        == "main"
    )
    for index in range(5):
        submit(local, index)
    candidate = generation.assemble_generation(data[0], state["id"])
    assert groups[1]["latex"] in candidate["latex_source"]
    with pytest.raises(PortalDataError, match="独立"):
        generation.review_generation(
            data[0],
            state["id"],
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="main-agent",
            passed=True,
            issues=[],
        )


def test_explicit_block_order_and_omission_are_preserved(fixed):
    data, state, experiences, plan = fixed
    groups = deepcopy(data[6]["groups"])
    # Nonselected base material may be deliberately omitted by the main plan.
    groups[-1]["disposition"] = "omit"
    # Keep the exact archived source for an unassigned omission.
    groups[-1]["latex"] = "\\section*{Project 6}\nAnalyzed strategy and built 6 Python services.\n"
    order = [block["block_id"] for block in state["writing_plan"]["blocks"]]
    order[1], order[2] = order[2], order[1]
    state = generation.configure_generation(
        data[0],
        state["id"],
        groups=groups,
        experiences=experiences[:-1],
        organization_plan=plan,
        writing_plan={"block_order": order},
    )
    local = (data, state, experiences[:-1], plan)
    for index in range(5):
        submit(local, index)
    candidate = generation.assemble_generation(data[0], state["id"])
    assert candidate["latex_source"].index("Project 2") < candidate["latex_source"].index(
        "Project 1"
    )
    assert "Project 6" not in candidate["latex_source"]


def test_experience_cannot_claim_fixed_header_under_another_source_id(fixed):
    data, state, experiences, plan = fixed
    bad = deepcopy(experiences)
    bad[0]["group_indexes"] = [0, 1]
    groups = deepcopy(data[6]["groups"])
    groups[0]["source_ids"] = groups[1]["source_ids"]
    with pytest.raises(PortalDataError, match="固定"):
        generation.configure_generation(
            data[0], state["id"], groups=groups, experiences=bad, organization_plan=plan
        )


def test_fixed_writing_does_not_require_matching_preselection(fixed):
    data, state, experiences, plan = fixed
    saved = json.loads((data[0].root / state["id"] / "experience-generation.json").read_text())
    request = saved["request"]
    request["analysis"]["selected_source_ids"] = []
    successor = generation.prepare_generation(
        data[0], data[1]["id"], data[1]["revision"], **request
    )
    successor = generation.configure_generation(
        data[0],
        successor["id"],
        groups=data[6]["groups"],
        experiences=experiences,
        organization_plan=plan,
    )
    assert len(successor["experiences"]) == 6
    assert generation.generation_context(data[0], successor["id"])["selected_source_ids"] == []


def test_cli_prepare_consumes_explicit_saved_snapshot_after_live_career_changes(fixed, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    data, state, *_ = fixed
    store = data[0]
    subprocess.run(["git", "init", "--quiet", "--template=", str(store.catalog.root)], check=True)
    saved = json.loads((store.root / state["id"] / "experience-generation.json").read_text())
    request = saved["request"] | {"identifier": data[1]["id"], "revision": data[1]["revision"]}
    request_path = tmp_path / "fixed-cli-request.json"
    request_path.write_text(json.dumps(request))
    (store.catalog.root / "contributions/project-1.md").write_text(
        "Changed live fact outside the saved task"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).resolve().parents[1] / "scripts/run_experience_generation.py"),
            "--applications",
            str(store.applications.root),
            "--career-workspace",
            str(store.catalog.root),
            "--resume-root",
            str(store.root),
            "prepare",
            "--request",
            str(request_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["id"] == state["id"]


def test_each_experience_has_a_distinct_writer_and_reserved_owners_stay_unambiguous(fixed):
    data, state, experiences, plan = fixed
    submit(fixed, 0)
    context = generation.writer_context(data[0], state["id"], "experience-2")
    with pytest.raises(PortalDataError, match="独立写作者"):
        generation.submit_fragment(
            data[0],
            state["id"],
            "experience-2",
            input_revision=context["input_revision"],
            groups=context["groups"],
            used_refs=context["source_ids"],
            issues=[],
            writer_id="writer-0",
        )
    bad = deepcopy(experiences)
    bad[0]["experience_id"] = "main"
    with pytest.raises(PortalDataError, match="归属"):
        generation.configure_generation(
            data[0], state["id"], groups=data[6]["groups"], experiences=bad, organization_plan=plan
        )


def test_adopted_fixed_task_is_immutable_and_repeated_adopt_returns_exact_draft(fixed):
    data, state, experiences, plan = fixed
    store = data[0]
    candidate = complete(fixed)
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer",
        passed=True,
        issues=[],
    )
    draft = generation.adopt_generation(store, state["id"])
    with pytest.raises(PortalDataError, match="已采用"):
        submit(fixed)
    with pytest.raises(PortalDataError, match="已采用"):
        generation.configure_generation(
            store,
            state["id"],
            groups=data[6]["groups"],
            experiences=experiences,
            organization_plan=plan,
        )
    with pytest.raises(PortalDataError, match="已采用"):
        generation.review_generation(
            store,
            state["id"],
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="reviewer",
            passed=True,
            issues=[],
        )
    with pytest.raises(PortalDataError, match="已采用"):
        generation.assemble_generation(store, state["id"])
    assert generation.adopt_generation(store, state["id"])["draft_sha256"] == draft["draft_sha256"]
    assert generation.generation_context(store, state["id"])["adopted_draft"]["id"] == draft["id"]


def test_repeated_adopt_checks_saved_final_review_against_adopted_draft(fixed):
    data, state, *_ = fixed
    candidate = complete(fixed)
    generation.review_generation(
        data[0],
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer",
        passed=True,
        issues=[],
    )
    generation.adopt_generation(data[0], state["id"])
    path = data[0].root / state["id"] / "experience-generation.json"
    saved = json.loads(path.read_text())
    # A mismatched receipt must not silently return a previously adopted version.
    saved["candidate_sha256"] = "different-version"
    path.write_text(json.dumps(saved))
    with pytest.raises(PortalDataError, match="已采用版本"):
        generation.adopt_generation(data[0], state["id"])


def test_reordering_group_array_cannot_move_fixed_header_or_bypass_block_order(fixed):
    data, state, experiences, plan = fixed
    groups = deepcopy(data[6]["groups"])
    groups[0], groups[1] = groups[1], groups[0]
    changed = deepcopy(experiences)
    changed[0]["group_indexes"] = [0]
    with pytest.raises(PortalDataError, match="原稿位置"):
        generation.configure_generation(
            data[0], state["id"], groups=groups, experiences=changed, organization_plan=plan
        )
