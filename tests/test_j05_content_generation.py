"""Public JSON handoffs over synthetic fixed deliveries; no model calls."""

import hashlib
import json
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_json_resume_content import assignment, fragment

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_resume_content import assemble_content, content_revision
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def delivery(tmp_path):
    assigned = assignment()
    identifier = "a" * 32
    directory = tmp_path / identifier
    directory.mkdir()
    state = {
        "id": identifier,
        "kind": "experience_handoff",
        "status": "codex_required",
        "application_id": "application-demo",
        "generation_contract": "content-writing/v1",
        "request": {},
        "configuration": {},
        "base_sha256": "synthetic-base",
        "application_snapshot": {},
        "payload": {
            "job": {"role_title": "Engineer"},
            "content_plan": {
                "schema_version": "resume-plan/v1",
                "application_id": "application-demo",
                "profile": {"name": "Synthetic Applicant", "contacts": []},
                "education": [],
                "assignments": [assigned],
            },
        },
        "mapping_required": True,
        "experiences": [],
        "fragments": {},
    }
    state["fixed_inputs_revision"] = digest(
        {
            key: state[key]
            for key in (
                "request",
                "payload",
                "configuration",
                "base_sha256",
                "application_snapshot",
            )
        }
    )
    (directory / "experience-generation.json").write_text(json.dumps(state))
    store = SimpleNamespace(
        root=tmp_path,
        applications=SimpleNamespace(write_lock=nullcontext),
        _read_version_file=lambda eid, name, limit: (tmp_path / eid / name).read_bytes(),
    )
    plan = deepcopy(state["payload"]["content_plan"])
    return store, identifier, plan


def submit(delivery, *, writer_id="writer-one", response=None):
    store, identifier, _ = delivery
    context = generation.writer_context(store, identifier, "experience-demo-1")
    payload = fragment() if response is None else response
    payload["assignment_revision"] = context["input_revision"]
    return generation.submit_fragment(
        store,
        identifier,
        "experience-demo-1",
        input_revision=context["input_revision"],
        writer_id=writer_id,
        content_fragment=payload,
    )


def seed_payload(delivery, **changes):
    store, identifier, _ = delivery
    path = store.root / identifier / "experience-generation.json"
    state = json.loads(path.read_text())
    state["payload"].update(changes)
    state["fixed_inputs_revision"] = digest(
        {
            key: state[key]
            for key in (
                "request",
                "payload",
                "configuration",
                "base_sha256",
                "application_snapshot",
            )
        }
    )
    path.write_text(json.dumps(state))


def test_json_writer_is_scoped_and_program_renders_complete_document(delivery):
    store, identifier, plan = delivery
    generation.configure_generation(store, identifier, writing_plan=plan)
    context = generation.writer_context(store, identifier, "experience-demo-1")
    assert context["assignment"]["experience"]["title"] == "Validation workflow"
    assert "latex" not in json.dumps(context).lower()
    assert context["output_schema"]["oneOf"]
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    assert (
        candidate["resume_content"]["experiences"][0]["items"][0]["text"]
        == "Participated in planning a validation workflow."
    )
    assert "\\subsection*{Validation workflow}" in candidate["latex_source"]
    assert candidate["latex_source"].endswith("\\end{document}\n")
    review = generation.review_context(store, identifier)
    assert review["resume_content"] == candidate["resume_content"]
    assert "latex_source" not in review


def test_content_review_applies_located_patch_and_binds_new_revision(delivery):
    store, identifier, plan = delivery
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    content = candidate["resume_content"]
    review = generation.review_generation(
        store,
        identifier,
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer-one",
        passed=True,
        issues=[],
        content_patch={
            "schema_version": "resume-content-patch/v1",
            "base_revision": content["revision"],
            "changes": [
                {
                    "item_id": "item-demo-1",
                    "field": "text",
                    "expected": "Participated in planning a validation workflow.",
                    "value": "Contributed to planning a validation workflow.",
                }
            ],
        },
    )
    updated = generation.review_context(store, identifier)
    assert (
        updated["resume_content"]["experiences"][0]["items"][0]["text"]
        == "Contributed to planning a validation workflow."
    )
    assert updated["resume_content"]["revision"] != content["revision"]
    assert review["review"]["content_revision"] == updated["resume_content"]["revision"]
    assert review["review"]["candidate_sha256"] == updated["candidate_sha256"]
    assert review["review"]["candidate_sha256"] != candidate["candidate_sha256"]


def test_protected_human_words_and_item_order_survive_writer_and_review(delivery):
    store, identifier, plan = delivery
    prior = assemble_content(plan, [fragment()])
    human = prior["experiences"][0]["items"][0]
    human.update(
        text="My retained manual wording.",
        origin="human",
        protected=True,
        edit_source="manual-editor",
    )
    prior["revision"] = content_revision(prior)
    seed_payload(delivery, retained_content=prior)
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    assert candidate["resume_content"]["experiences"][0]["items"][0] == human
    with pytest.raises(PortalDataError):
        generation.review_generation(
            store,
            identifier,
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="reviewer-one",
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
                        "value": "Changed",
                    }
                ],
            },
        )


@pytest.mark.parametrize(
    "corruption", ["experience", "candidate", "reference", "human", "extra_field"]
)
def test_writer_cannot_change_identity_scope_or_human_provenance(delivery, corruption):
    store, identifier, plan = delivery
    generation.configure_generation(store, identifier, writing_plan=plan)
    response = fragment()
    if corruption == "experience":
        response["experience_id"] = "other-experience"
    elif corruption == "candidate":
        response["candidate_id"] = "other-candidate"
    elif corruption == "reference":
        response["items"][0]["fact_refs"] = ["foreign-fact"]
    elif corruption == "human":
        response["items"][0].update(origin="human", protected=True, edit_source="forged")
    else:
        response["latex_fragment"] = "arbitrary body"
    with pytest.raises(PortalDataError):
        submit(delivery, response=response)
    assert generation.generation_state(store, identifier)["completed_experience_ids"] == []


def test_material_request_stays_pending_instead_of_becoming_a_written_experience(delivery):
    store, identifier, plan = delivery
    generation.configure_generation(store, identifier, writing_plan=plan)
    response = fragment()
    response.pop("items")
    response.update(
        status="needs_material",
        requests=[
            {
                "id": "missing-role",
                "field": "role",
                "detail": "Confirm the applicable team role.",
                "fact_refs": ["fact-demo-1"],
            }
        ],
    )
    result = submit(delivery, response=response)
    assert result["completed_experience_ids"] == []
    assert result["fragment_status"] == {"experience-demo-1": "needs_material"}
    with pytest.raises(PortalDataError):
        generation.assemble_generation(store, identifier)


def test_only_affected_experience_returns_to_its_writer(delivery):
    store, identifier, plan = delivery
    second = json.loads(json.dumps(plan["assignments"][0]).replace("demo-1", "demo-2"))
    plan["assignments"].append(second)
    seed_payload(delivery, content_plan=plan)
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    context = generation.writer_context(store, identifier, "experience-demo-2")
    response = json.loads(json.dumps(fragment()).replace("demo-1", "demo-2"))
    response["assignment_revision"] = context["input_revision"]
    with pytest.raises(PortalDataError):
        generation.submit_fragment(
            store,
            identifier,
            "experience-demo-2",
            input_revision=context["input_revision"],
            writer_id="writer-one",
            content_fragment=response,
        )
    generation.submit_fragment(
        store,
        identifier,
        "experience-demo-2",
        input_revision=context["input_revision"],
        writer_id="writer-two",
        content_fragment=response,
    )
    unchanged = generation.writer_context(store, identifier, "experience-demo-2")[
        "previous_fragment"
    ]
    candidate = generation.assemble_generation(store, identifier)
    result = generation.review_generation(
        store,
        identifier,
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer-one",
        passed=False,
        issues=["Focus only the first experience."],
        rewrite_experience_ids=["experience-demo-1"],
    )
    assert result["completed_experience_ids"] == ["experience-demo-2"]
    assert (
        generation.writer_context(store, identifier, "experience-demo-2")["previous_fragment"]
        == unchanged
    )
    assert (
        generation.writer_context(store, identifier, "experience-demo-1")["previous_fragment"]
        is None
    )
    assert generation.writer_context(store, identifier, "experience-demo-1")["review_feedback"][
        "issues"
    ] == ["Focus only the first experience."]
    submit(delivery, writer_id="writer-three")
    rebuilt = generation.assemble_generation(store, identifier)
    assert rebuilt["fragments"]["experience-demo-2"] == unchanged


def test_global_writer_and_final_reviewer_are_independent(delivery):
    store, identifier, plan = delivery
    plan["summary"] = [
        {"id": "summary-demo", "text": "Plans validation workflows.", "fact_refs": ["fact-demo-1"]}
    ]
    with pytest.raises(PortalDataError):
        generation.configure_generation(store, identifier, writing_plan=plan)
    generation.configure_generation(
        store, identifier, writing_plan=plan, main_writer_id="main-agent"
    )
    with pytest.raises(PortalDataError):
        submit(delivery, writer_id="main-agent")
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    with pytest.raises(PortalDataError):
        generation.review_generation(
            store,
            identifier,
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="main-agent",
            passed=True,
            issues=[],
        )
    with pytest.raises(PortalDataError):
        generation.review_generation(
            store,
            identifier,
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="writer-one",
            passed=True,
            issues=[],
        )


def test_plan_cannot_change_fixed_facts_or_restore_retained_omission(delivery):
    store, identifier, plan = delivery
    bad = deepcopy(plan)
    bad["assignments"][0]["experience"]["facts"][0]["text"] = "Invented completed result."
    with pytest.raises(PortalDataError):
        generation.configure_generation(store, identifier, writing_plan=bad)
    seed_payload(delivery, retained_omitted_experience_ids=["experience-demo-1"])
    with pytest.raises(PortalDataError):
        generation.configure_generation(store, identifier, writing_plan=plan)


def test_reconfiguration_invalidates_only_changed_assignment(delivery):
    store, identifier, plan = delivery
    second = json.loads(json.dumps(plan["assignments"][0]).replace("demo-1", "demo-2"))
    plan["assignments"].append(second)
    seed_payload(delivery, content_plan=plan)
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    plan["assignments"][1]["writing_requirements"].append("Focus on the second role.")
    unchanged = generation.writer_context(store, identifier, "experience-demo-1")[
        "previous_fragment"
    ]
    configured = generation.configure_generation(store, identifier, writing_plan=plan)
    assert configured["completed_experience_ids"] == ["experience-demo-1"]
    assert (
        generation.writer_context(store, identifier, "experience-demo-1")["previous_fragment"]
        == unchanged
    )


def test_invalid_plan_uses_stable_error_without_changing_delivery(delivery):
    store, identifier, _ = delivery
    original = generation.generation_state(store, identifier)
    with pytest.raises(PortalDataError):
        generation.configure_generation(store, identifier, writing_plan=["not-a-plan"])
    assert generation.generation_state(store, identifier) == original


@pytest.mark.parametrize("operation", ["submit", "configure"])
def test_saved_reviewer_cannot_become_a_writer_during_returned_experience(delivery, operation):
    store, identifier, plan = delivery
    second = json.loads(json.dumps(plan["assignments"][0]).replace("demo-1", "demo-2"))
    plan["assignments"].append(second)
    seed_payload(delivery, content_plan=plan)
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    context = generation.writer_context(store, identifier, "experience-demo-2")
    response = json.loads(json.dumps(fragment()).replace("demo-1", "demo-2"))
    response["assignment_revision"] = context["input_revision"]
    generation.submit_fragment(
        store,
        identifier,
        "experience-demo-2",
        input_revision=context["input_revision"],
        writer_id="writer-two",
        content_fragment=response,
    )
    candidate = generation.assemble_generation(store, identifier)
    generation.review_generation(
        store,
        identifier,
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer-one",
        passed=False,
        issues=["Clarify only the first experience."],
        rewrite_experience_ids=["experience-demo-1"],
    )
    before = generation.generation_state(store, identifier)
    retained = generation.writer_context(store, identifier, "experience-demo-2")[
        "previous_fragment"
    ]
    with pytest.raises(PortalDataError):
        if operation == "submit":
            submit(delivery, writer_id="reviewer-one")
        else:
            generation.configure_generation(
                store, identifier, writing_plan=plan, main_writer_id="reviewer-one"
            )
    assert generation.generation_state(store, identifier) == before
    assert (
        generation.writer_context(store, identifier, "experience-demo-2")["previous_fragment"]
        == retained
    )
    submit(delivery, writer_id="writer-three")
    candidate = generation.assemble_generation(store, identifier)
    reviewed = generation.review_generation(
        store,
        identifier,
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="reviewer-one",
        passed=True,
        issues=[],
    )
    assert reviewed["review"]["passed"] is True


def template_delivery(delivery):
    from career_evidence_graph.application_prism import archive_sources, source_snapshot

    store, identifier, plan = delivery
    directory = store.root / identifier
    project = directory / "project"
    project.mkdir()
    template = (
        "\\documentclass{article}\n\\begin{document}\n"
        "Fixed Applicant \\href{mailto:fixed@example.test}{Email}\n"
        "\\section*{Education}\nFixed University, Fixed Degree\n"
        "\\section*{Summary}\n%% TOMORROWSTAR_SUMMARY %%\n"
        "\\section*{Skills}\n%% TOMORROWSTAR_SKILLS %%\n"
        "\\section*{Experience}\n%% TOMORROWSTAR_EXPERIENCES %%\n"
        "\\end{document}\n"
    )
    (project / "main.tex").write_text(template)
    base = source_snapshot(project, "main.tex", source_policy="generated-latex-project/v1")
    raw = archive_sources(base)
    (directory / "base-sources.json").write_bytes(raw)
    plan.pop("profile")
    plan.pop("education")
    plan.update(schema_version="resume-template-plan/v1", template_revision=digest(template))
    state_path = directory / "experience-generation.json"
    state = json.loads(state_path.read_text())
    state["request"]["latex_base"] = base
    state["base_sha256"] = hashlib.sha256(raw).hexdigest()
    state_path.write_text(json.dumps(state))
    seed_payload(delivery, content_plan=plan)
    return store, identifier, plan, template


def test_fixed_template_content_never_enters_writer_or_review_json(delivery):
    store, identifier, plan, template = template_delivery(delivery)
    generation.configure_generation(store, identifier, writing_plan=plan)
    writer = generation.writer_context(store, identifier, "experience-demo-1")
    assert "Fixed Applicant" not in json.dumps(writer)
    assert "Fixed University" not in json.dumps(writer)
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    content = candidate["resume_content"]
    assert content["schema_version"] == "resume-template-content/v1"
    assert content["template_revision"] == digest(template)
    assert not {"profile", "education"} & content.keys()
    assert "Fixed Applicant" in candidate["latex_source"]
    assert "Fixed University, Fixed Degree" in candidate["latex_source"]
    review = generation.review_context(store, identifier)
    assert "Fixed Applicant" not in json.dumps(review)
    assert "Fixed University" not in json.dumps(review)
    assert "%% TOMORROWSTAR_" not in candidate["latex_source"]


def test_changed_fixed_template_archive_cannot_render_an_old_plan(delivery):
    store, identifier, plan, _ = template_delivery(delivery)
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    (store.root / identifier / "base-sources.json").write_text("{}")
    with pytest.raises(PortalDataError):
        generation.assemble_generation(store, identifier)
