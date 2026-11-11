"""Career positioning follows the same durable write/review path as resume content."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_j05_content_generation import (
    delivery as delivery,
)
from test_j05_content_generation import (
    seed_payload,
    submit,
    template_delivery,
)

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import archive_sources, source_snapshot
from career_evidence_graph.application_resume_content import content_revision
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def headline_delivery(delivery):
    store, identifier, plan, template = template_delivery(delivery)
    template = template.replace(
        "\\section*{Education}", "%% TOMORROWSTAR_HEADLINE %%\n\\section*{Education}"
    )
    directory = store.root / identifier
    project = directory / "project"
    (project / "main.tex").write_text(template)
    binding = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    raw = archive_sources(binding)
    (directory / "base-sources.json").write_bytes(raw)
    plan["template_revision"] = digest(template)
    state_path = directory / "experience-generation.json"
    state = json.loads(state_path.read_text())
    state["request"]["latex_base"] = binding
    state["base_sha256"] = hashlib.sha256(raw).hexdigest()
    state_path.write_text(json.dumps(state))
    seed_payload(delivery, content_plan=plan, headline_required=True)
    plan["headline"] = {
        "id": "career-headline",
        "text": "Quantitative Research",
        "fact_refs": ["fact-demo-1"],
    }
    return store, identifier, plan


def test_career_headline_passes_through_writer_and_independent_review(delivery):
    store, identifier, plan = headline_delivery(delivery)
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-writer"
    )
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    assert "Quantitative Research\\par\n" in candidate["latex_source"]
    assert "\\item Quantitative Research" not in candidate["latex_source"]
    assert generation.review_context(store, identifier)["resume_content"]["headline"]["text"] == (
        "Quantitative Research"
    )
    generation.review_generation(
        store,
        identifier,
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="independent-reviewer",
        passed=True,
        issues=[],
        content_patch={
            "schema_version": "resume-content-patch/v1",
            "base_revision": candidate["resume_content"]["revision"],
            "changes": [
                {
                    "item_id": "career-headline",
                    "field": "text",
                    "expected": "Quantitative Research",
                    "value": "Quantitative Research | Data Science",
                }
            ],
        },
    )
    reviewed = generation.review_context(store, identifier)
    assert reviewed["resume_content"]["headline"]["text"] == (
        "Quantitative Research | Data Science"
    )
    assert reviewed["resume_content"]["revision"] != candidate["resume_content"]["revision"]


def test_headline_only_global_writer_requires_identity(delivery):
    store, identifier, plan = headline_delivery(delivery)
    with pytest.raises(PortalDataError):
        generation.configure_generation(store, identifier, writing_plan=plan)
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-writer"
    )


def test_opted_in_template_rejects_missing_career_positioning(delivery):
    store, identifier, plan = headline_delivery(delivery)
    plan.pop("headline")
    with pytest.raises(PortalDataError):
        generation.configure_generation(
            store, identifier, writing_plan=plan, main_writer_id="main-writer"
        )


def test_manual_headline_survives_regeneration_and_cannot_be_review_patched(delivery):
    store, identifier, plan = headline_delivery(delivery)
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-writer"
    )
    submit(delivery)
    prior = generation.assemble_generation(store, identifier)["resume_content"]
    human = prior["headline"]
    human.update(
        text="My chosen career positioning",
        origin="human",
        protected=True,
        edit_source="manual-editor",
    )
    prior["revision"] = content_revision(prior)
    seed_payload(delivery, retained_content=prior)
    plan["headline"]["text"] = "Data Science"
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-writer"
    )
    candidate = generation.assemble_generation(store, identifier)
    assert candidate["resume_content"]["headline"] == human
    with pytest.raises(PortalDataError):
        generation.review_generation(
            store,
            identifier,
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="independent-reviewer",
            passed=True,
            issues=[],
            content_patch={
                "schema_version": "resume-content-patch/v1",
                "base_revision": candidate["resume_content"]["revision"],
                "changes": [
                    {
                        "item_id": human["id"],
                        "field": "text",
                        "expected": human["text"],
                        "value": "Data Science",
                    }
                ],
            },
        )


def test_manual_headline_deletion_survives_regeneration(delivery):
    store, identifier, plan = headline_delivery(delivery)
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-writer"
    )
    submit(delivery)
    prior = generation.assemble_generation(store, identifier)["resume_content"]
    prior.pop("headline")
    prior["revision"] = content_revision(prior)
    seed_payload(delivery, retained_content=prior, retained_protected_scopes=["headline"])
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-writer"
    )
    candidate = generation.assemble_generation(store, identifier)
    assert "headline" not in candidate["resume_content"]
    assert "Quantitative Research" not in candidate["latex_source"]


def test_retained_headline_cannot_keep_references_outside_delivered_scope(delivery):
    store, identifier, plan = headline_delivery(delivery)
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-writer"
    )
    submit(delivery)
    prior = deepcopy(generation.assemble_generation(store, identifier)["resume_content"])
    prior["headline"].update(
        fact_refs=["no-longer-delivered"],
        origin="human",
        protected=True,
        edit_source="manual-editor",
    )
    prior["revision"] = content_revision(prior)
    seed_payload(delivery, retained_content=prior)
    with pytest.raises(PortalDataError):
        generation.configure_generation(
            store, identifier, writing_plan=plan, main_writer_id="main-writer"
        )
