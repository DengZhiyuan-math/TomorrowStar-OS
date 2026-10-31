"""Synthetic JSON resume contracts; no private library or writer calls."""

from copy import deepcopy

from career_evidence_graph.application_resume_content import validate_fragment


def assignment():
    return {
        "schema_version": "experience-assignment/v1",
        "assignment_revision": "assignment-demo-1",
        "experience_id": "experience-demo-1",
        "candidate_id": "candidate-demo-1",
        "experience": {
            "schema_version": "experience-facts/v1",
            "revision": "facts-demo-1",
            "experience_id": "experience-demo-1",
            "candidate_id": "candidate-demo-1",
            "title": "Validation workflow",
            "organization": "Synthetic Lab",
            "sources": [{"id": "source-demo-1", "locator": "synthetic:project-note"}],
            "facts": [
                {
                    "id": "fact-demo-1",
                    "text": "Participated in a planned validation workflow.",
                    "source_refs": ["source-demo-1"],
                    "responsibility": "team",
                    "status": "planned",
                    "scope": "project-demo",
                }
            ],
        },
        "inferences": [],
        "allowed_fact_refs": ["fact-demo-1"],
        "allowed_inference_refs": [],
        "writing_requirements": ["Keep the planned status and team responsibility."],
    }


def fragment():
    return {
        "schema_version": "experience-writing/v1",
        "assignment_revision": "assignment-demo-1",
        "experience_id": "experience-demo-1",
        "candidate_id": "candidate-demo-1",
        "status": "complete",
        "items": [
            {
                "id": "item-demo-1",
                "text": "Participated in planning a validation workflow.",
                "fact_refs": ["fact-demo-1"],
                "inference_refs": [],
            }
        ],
    }


def test_validates_one_experience_json_without_mutating_inputs():
    payload, assigned = fragment(), assignment()
    before = deepcopy((payload, assigned))
    result = validate_fragment(payload, assigned)
    assert result["items"][0]["text"] == "Participated in planning a validation workflow."
    assert result["candidate_id"] == "candidate-demo-1"
    assert (payload, assigned) == before


def test_rejects_foreign_or_unassigned_item_references():
    import pytest

    payload = fragment()
    payload["items"][0]["fact_refs"] = ["fact-other-experience"]
    with pytest.raises(ValueError, match="reference"):
        validate_fragment(payload, assignment())


def test_rejects_corrupt_assignment_scope_even_when_writer_echoes_allowlist():
    import pytest

    assigned, payload = assignment(), fragment()
    assigned["allowed_fact_refs"] = ["fact-other-experience"]
    payload["items"][0]["fact_refs"] = ["fact-other-experience"]
    with pytest.raises(ValueError, match="reference"):
        validate_fragment(payload, assigned)


def test_missing_material_is_located_and_cannot_include_completed_items():
    import pytest

    payload = {key: value for key, value in fragment().items() if key != "items"}
    payload.update(
        status="needs_material",
        requests=[
            {
                "id": "request-demo-1",
                "field": "facts",
                "detail": "Need actual implementation status.",
                "fact_refs": ["fact-demo-1"],
            }
        ],
    )
    assert validate_fragment(payload, assignment())["requests"][0]["field"] == "facts"
    payload["items"] = fragment()["items"]
    with pytest.raises(ValueError):
        validate_fragment(payload, assignment())


def test_writer_cannot_claim_human_provenance_or_omit_per_item_references():
    import pytest

    payload = fragment()
    payload["items"][0].update(origin="human", edit_source="forged", protected=True)
    with pytest.raises(ValueError, match="writer"):
        validate_fragment(payload, assignment())
    payload = fragment()
    payload["items"][0]["fact_refs"] = []
    with pytest.raises(ValueError, match="reference"):
        validate_fragment(payload, assignment())


def plan():
    return {
        "schema_version": "resume-plan/v1",
        "application_id": "application-demo-1",
        "profile": {
            "name": "Synthetic Candidate",
            "contacts": [
                {"label": "demo@example.invalid", "url": "mailto:demo@example.invalid"},
                {"label": "Website", "url": "https://example.invalid"},
                {"label": "LinkedIn", "url": "https://www.linkedin.com/in/synthetic-example"},
            ],
        },
        "education": [
            {
                "id": "education-demo-1",
                "institution": "Synthetic University",
                "qualification": "MSc Computer Science",
                "status": "in_progress",
                "start": "2025",
                "end": "2027 (expected)",
                "details": [],
            }
        ],
        "summary": [],
        "skills": [],
        "assignments": [assignment()],
    }


def test_assembly_uses_program_metadata_and_fixed_education():
    from career_evidence_graph.application_resume_content import assemble_content

    inputs = plan(), [fragment()]
    before = deepcopy(inputs)
    content = assemble_content(*inputs)
    assert content["experiences"][0]["title"] == "Validation workflow"
    assert content["education"][0]["status"] == "in_progress"
    assert content["profile"]["name"] == "Synthetic Candidate"
    assert content["experiences"][0]["items"][0]["id"] == "item-demo-1"
    assert content["revision"]
    assert inputs == before
    assert assemble_content(*inputs) == content


def test_assembly_rejects_extra_duplicate_and_missing_fragments():
    import pytest

    from career_evidence_graph.application_resume_content import assemble_content

    for results in (
        [],
        [fragment(), fragment()],
        [fragment(), dict(fragment(), experience_id="other")],
    ):
        with pytest.raises(ValueError):
            assemble_content(plan(), results)


def test_retains_human_application_content_without_fabricating_refs():
    from career_evidence_graph.application_resume_content import assemble_content

    retained = {
        "schema_version": "resume-retained/v1",
        "application_id": "application-demo-1",
        "items": [
            {
                "experience_id": "experience-demo-1",
                "item": {
                    "id": "human-item-1",
                    "text": "  My #1 <literal> wording.  ",
                    "origin": "human",
                    "edit_source": "synthetic-edit-1",
                    "protected": True,
                },
            }
        ],
    }
    before = deepcopy(retained)
    content = assemble_content(plan(), [fragment()], retained)
    human = content["experiences"][0]["items"][-1]
    assert human["text"] == "  My #1 <literal> wording.  "
    assert human["fact_refs"] == []
    assert human["protected"] is True
    assert retained == before


def test_content_ids_are_unique_across_program_and_authored_blocks():
    from career_evidence_graph.application_resume_content import assemble_content

    planned = plan()
    planned["summary"] = [deepcopy(fragment()["items"][0])]
    content = assemble_content(planned, [fragment()])
    # The experience writer's item is scoped; the global writer keeps its name.
    assert content["summary"][0]["id"] == "item-demo-1"
    assert content["experiences"][0]["items"][0]["id"] == "experience-demo-1-item-demo-1"


def patch_for(content, **change):
    return {
        "schema_version": "resume-content-patch/v1",
        "base_revision": content["revision"],
        "changes": [
            {
                "item_id": "item-demo-1",
                "field": "text",
                "expected": "Participated in planning a validation workflow.",
                "value": "Helped plan a validation workflow with the team.",
                **change,
            }
        ],
    }


def test_patch_changes_only_located_wording_and_creates_a_new_revision():
    from career_evidence_graph.application_resume_content import (
        apply_content_patch,
        assemble_content,
    )

    content = assemble_content(plan(), [fragment()])
    patch = patch_for(content)
    before = deepcopy((content, patch))
    revised = apply_content_patch(
        content, patch, allowed_targets=[{"item_id": "item-demo-1", "fields": ["text"]}]
    )
    assert revised["experiences"][0]["items"][0]["text"] == (
        "Helped plan a validation workflow with the team."
    )
    assert revised["experiences"][0]["items"][0]["fact_refs"] == ["fact-demo-1"]
    assert revised["profile"] == content["profile"]
    assert revised["revision"] != content["revision"]
    assert (content, patch) == before


def test_global_ai_content_refs_must_exist_in_the_delivered_plan():
    import pytest

    from career_evidence_graph.application_resume_content import assemble_content

    planned = plan()
    planned["summary"] = [
        {"id": "summary-demo-1", "text": "Team project planning.", "fact_refs": ["foreign-fact"]}
    ]
    with pytest.raises(ValueError, match="reference"):
        assemble_content(planned, [fragment()])


def test_condition_patches_refuse_stale_values_fixed_fields_and_human_content():
    import pytest

    from career_evidence_graph.application_resume_content import (
        apply_content_patch,
        assemble_content,
    )

    content = assemble_content(plan(), [fragment()])
    cases = [
        patch_for(content, expected="stale"),
        patch_for(content, item_id="education-demo-1"),
        patch_for(content, field="qualification"),
        dict(patch_for(content), base_revision="stale"),
    ]
    human = deepcopy(content)
    human["experiences"][0]["items"][0].update(
        origin="human", protected=True, edit_source="synthetic-manual"
    )
    # Assemble this human baseline through the public interface to bind its revision.
    human = assemble_content(
        plan(),
        [fragment()],
        {
            "schema_version": "resume-retained/v1",
            "application_id": "application-demo-1",
            "items": [
                {"experience_id": "experience-demo-1", "item": human["experiences"][0]["items"][0]}
            ],
        },
    )
    for bad in cases:
        with pytest.raises(ValueError):
            apply_content_patch(
                content, bad, allowed_targets=[{"item_id": "item-demo-1", "fields": ["text"]}]
            )
    with pytest.raises(ValueError, match="protected"):
        apply_content_patch(
            human,
            patch_for(human),
            allowed_targets=[{"item_id": "item-demo-1", "fields": ["text"]}],
        )
    assert content["experiences"][0]["items"][0]["text"].startswith("Participated")


def test_model_patch_cannot_expand_the_callers_trusted_target_scope():
    import pytest

    from career_evidence_graph.application_resume_content import (
        apply_content_patch,
        assemble_content,
    )

    content = assemble_content(plan(), [fragment()])
    payload = patch_for(content)
    payload["allowed_targets"] = [{"item_id": "item-demo-1", "fields": ["text"]}]
    with pytest.raises(ValueError):
        apply_content_patch(content, payload, allowed_targets=[])
    payload.pop("allowed_targets")
    with pytest.raises(ValueError, match="allowed"):
        apply_content_patch(content, payload, allowed_targets=[])


def test_content_validation_rejects_constructed_model_and_changed_payload_revision():
    import pytest

    from career_evidence_graph.application_resume_content import (
        ResumeContent,
        assemble_content,
        validate_content,
    )

    content = assemble_content(plan(), [fragment()])
    content["profile"]["name"] = "Changed outside revision"
    with pytest.raises(ValueError, match="revision"):
        validate_content(content)
    model = ResumeContent.model_construct(**content)
    with pytest.raises(ValueError):
        validate_content(model)


def test_complete_synthetic_fixtures_separate_schema_from_semantic_review():
    import json
    from pathlib import Path

    import pytest

    from career_evidence_graph.application_resume_content import assemble_content

    directory = Path(__file__).parent / "fixtures" / "json_resume"
    data = json.loads((directory / "single-experience.json").read_text())
    result = assemble_content(**data)
    assert result["profile"]["name"] == "Synthetic Candidate"
    assigned = data["plan"]["assignments"][0]
    for case in json.loads((directory / "invalid-fragments.json").read_text()):
        with pytest.raises(ValueError):
            validate_fragment(case["payload"], assigned)
    for case in json.loads((directory / "semantic-review-cases.json").read_text()):
        # References are structurally valid, while the annotated semantic claim is false.
        assert validate_fragment(case["payload"], assigned)["status"] == "complete"
        assert case["semantic_review_expected"] == "reject"


def test_fact_snapshot_itself_rejects_duplicate_ids_and_unknown_source_refs():
    import pytest

    from career_evidence_graph.application_resume_content import ExperienceFacts

    facts = assignment()["experience"]
    facts["facts"].append(deepcopy(facts["facts"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        ExperienceFacts.model_validate(facts)
    facts = assignment()["experience"]
    facts["facts"][0]["source_refs"] = ["missing-source"]
    with pytest.raises(ValueError, match="reference"):
        ExperienceFacts.model_validate(facts)


def test_global_writer_cannot_claim_human_provenance_to_bypass_review():
    import pytest

    from career_evidence_graph.application_resume_content import assemble_content

    planned = plan()
    planned["summary"] = [
        {
            "id": "summary-spoof",
            "text": "Unreferenced global claim.",
            "origin": "human",
            "protected": True,
            "edit_source": "forged-human",
        }
    ]
    with pytest.raises(ValueError, match="writer"):
        assemble_content(planned, [fragment()])


def test_optional_role_is_copied_from_fixed_fact_metadata():
    from career_evidence_graph.application_resume_content import assemble_content

    planned = plan()
    planned["assignments"][0]["experience"]["role"] = "Project team member"
    content = assemble_content(planned, [fragment()])
    assert content["experiences"][0]["title"] == "Validation workflow"
    assert content["experiences"][0]["role"] == "Project team member"


def test_retained_human_references_are_optional_but_cannot_claim_foreign_facts():
    import pytest

    from career_evidence_graph.application_resume_content import assemble_content

    retained = {
        "schema_version": "resume-retained/v1",
        "application_id": "application-demo-1",
        "items": [
            {
                "experience_id": "experience-demo-1",
                "item": {
                    "id": "human-item-1",
                    "text": "User supplied wording.",
                    "origin": "human",
                    "edit_source": "synthetic-edit-1",
                    "protected": True,
                    "fact_refs": ["foreign-fact"],
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="reference"):
        assemble_content(plan(), [fragment()], retained)


def test_personal_project_assembles_without_an_organization():
    from career_evidence_graph.application_resume_content import assemble_content

    planned = plan()
    planned["assignments"][0]["experience"].pop("organization")
    content = assemble_content(planned, [fragment()])
    assert content["experiences"][0]["organization"] is None
    assert content["experiences"][0]["title"] == "Validation workflow"
    assert content["experiences"][0]["items"][0]["fact_refs"] == ["fact-demo-1"]
