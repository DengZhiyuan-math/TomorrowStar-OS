"""Retained human content can reuse exact facts from the fixed upstream snapshot."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_j05_preparation import content_delivery as content_delivery
from test_j05_preparation import prepare
from test_json_resume_template_content import TEMPLATE

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume_content import assemble_content, content_revision
from career_evidence_graph.application_resume_render import render_resume
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


def _revision(value):
    value["revision"] = digest({key: item for key, item in value.items() if key != "revision"})


def _packet_revision(analysis):
    _revision(analysis["material_packet"])
    analysis["inference_result"]["material_packet_revision"] = analysis["material_packet"][
        "revision"
    ]
    _revision(analysis["inference_result"])


@pytest.fixture
def retained_delivery(content_delivery, tmp_path, request):
    store, job, snapshot, analysis, inputs, _template = content_delivery
    packet = analysis["material_packet"]
    original = next(iter(packet["sources"].values()))
    extras = []
    for number in range(getattr(request, "param", 1)):
        extra = deepcopy(original)
        extra.update(
            source_id="retained-source" + (f"-{number}" if number else ""),
            text=f"Recorded retained validation work {number}.",
        )
        extra["record_context"]["fact_id"] = f"fact-{number + 2}"
        packet["sources"][extra["source_id"]] = extra
        extras.append(extra)
    _packet_revision(analysis)
    initial = prepare(content_delivery)
    planned = generation.generation_context(store, initial["id"])["content_plan"]
    fragments = []
    for index, assigned in enumerate(planned["assignments"]):
        fragments.append(
            {
                "schema_version": "experience-writing/v1",
                "assignment_revision": assigned["assignment_revision"],
                "experience_id": assigned["experience_id"],
                "candidate_id": assigned["candidate_id"],
                "status": "complete",
                "items": [
                    {
                        "id": f"human-{index}-{number}",
                        "text": f"Retained human wording {index}-{number}.",
                        "fact_refs": [
                            assigned["allowed_fact_refs"][1 + number % len(extras)]
                            if index == 0
                            else assigned["allowed_fact_refs"][-1]
                        ],
                    }
                    for number in range(15 if index == 0 else 1)
                ],
            }
        )
    content = assemble_content(planned, fragments)
    for experience in content["experiences"]:
        for item in experience["items"]:
            item.update(origin="human", protected=True, edit_source="synthetic:accepted-content")
    content["revision"] = content_revision(content)
    rendered = render_resume(content, template=TEMPLATE)
    project = tmp_path / "retained-project"
    project.mkdir()
    (project / "main.tex").write_text(rendered.tex)
    retained = store.import_latex_for_task(
        job["id"],
        job["revision"],
        task_inputs=inputs,
        prism=source_snapshot(project, "main.tex"),
        content_mapping={
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
                "source_locator": "synthetic:accepted-content",
                "source_sha256": digest(content),
            },
        },
    )
    # The fixed career snapshot holds native facts, while P04 selected a subset.
    snapshot["items"] = deepcopy(list(packet["sources"].values()))
    unused = deepcopy(extra)
    unused.update(source_id="unselected-source", text="Unselected canonical fact.")
    unused["record_context"]["fact_id"] = "fact-unselected"
    snapshot["items"].append(unused)
    _revision(snapshot)
    analysis["source_snapshot_revision"] = snapshot["revision"]
    for extra in extras:
        packet["sources"].pop(extra["source_id"])
    _packet_revision(analysis)
    return content_delivery, retained


def test_fixed_snapshot_delivers_only_missing_retained_facts_without_changing_p04(
    retained_delivery,
):
    delivery, retained = retained_delivery
    store, _job, _snapshot, analysis, *_ = delivery
    before = deepcopy(analysis)
    state = prepare(delivery, retained_draft=retained)
    context = generation.generation_context(store, state["id"])
    configured = generation.configure_generation(store, state["id"])
    payload = json.loads((store.root / state["id"] / "input.json").read_text())
    assert payload["material_packet"] == before["material_packet"]
    assert payload["inference_result"] == before["inference_result"]
    assert payload["retained_source_ids"] == ["retained-source"]
    assert {row["source_id"] for row in payload["sources"]} == {
        *before["material_packet"]["sources"],
        "retained-source",
    }
    first = context["content_plan"]["assignments"][0]
    assert first["allowed_fact_refs"] == ["candidate-0::fact-1", "candidate-0::fact-2"]
    for number, assigned in enumerate(configured["experiences"]):
        writer = generation.writer_context(store, state["id"], assigned["experience_id"])
        generation.submit_fragment(
            store,
            state["id"],
            assigned["experience_id"],
            input_revision=writer["input_revision"],
            writer_id=f"new-writer-{number}",
            content_fragment={
                "schema_version": "experience-writing/v1",
                "status": "complete",
                "assignment_revision": writer["input_revision"],
                "experience_id": writer["experience_id"],
                "candidate_id": writer["candidate_id"],
                "items": [
                    {
                        "id": "new-" + str(number),
                        "text": "New wording.",
                        "fact_refs": writer["assignment"]["allowed_fact_refs"][:1],
                    }
                ],
            },
        )
    candidate = generation.assemble_generation(store, state["id"])
    for current, previous in zip(
        candidate["resume_content"]["experiences"],
        retained["resume_content"]["experiences"],
        strict=True,
    ):
        assert current["items"][: len(previous["items"])] == previous["items"]
        assert [item for item in current["items"] if item["origin"] == "human"] == previous["items"]
    assert analysis == before


@pytest.mark.parametrize("unavailable", ["absent", "document_changed", "candidate", "experience"])
def test_missing_current_fact_still_stops_at_existing_retention_guard(
    retained_delivery, unavailable
):
    delivery, retained = retained_delivery
    store, _job, snapshot, analysis, *_ = delivery
    extra = next(row for row in snapshot["items"] if row["source_id"] == "retained-source")
    if unavailable == "absent":
        snapshot["items"].remove(extra)
    elif unavailable == "document_changed":
        extra["source_revision"] = "another-document-revision"
    elif unavailable == "candidate":
        extra["candidate_id"] = "another-candidate"
    else:
        extra["record_context"]["experience_id"] = "another-experience"
    _revision(snapshot)
    analysis["source_snapshot_revision"] = snapshot["revision"]
    state = prepare(delivery, retained_draft=retained)
    with pytest.raises(PortalDataError) as stopped:
        generation.configure_generation(store, state["id"])
    assert stopped.value.code == "resume_latex_invalid"
    assert store.draft(retained["id"])["resume_content"] == retained["resume_content"]


@pytest.mark.parametrize("field", ["title", "content_revision"])
def test_retained_fact_cannot_mix_conflicting_current_metadata(retained_delivery, field):
    delivery, retained = retained_delivery
    _store, _job, snapshot, analysis, *_ = delivery
    extra = next(row for row in snapshot["items"] if row["source_id"] == "retained-source")
    extra["record_context"][field] = "conflicting-current-value"
    _revision(snapshot)
    analysis["source_snapshot_revision"] = snapshot["revision"]
    with pytest.raises(PortalDataError) as stopped:
        prepare(delivery, retained_draft=retained)
    assert stopped.value.code == "resume_model_invalid"


def test_native_fact_cannot_replace_a_packet_source_with_the_same_id(retained_delivery):
    delivery, retained = retained_delivery
    store, _job, snapshot, analysis, *_ = delivery
    extra = next(row for row in snapshot["items"] if row["source_id"] == "retained-source")
    extra["source_id"] = next(iter(analysis["material_packet"]["sources"]))
    _revision(snapshot)
    analysis["source_snapshot_revision"] = snapshot["revision"]
    state = prepare(delivery, retained_draft=retained)
    with pytest.raises(PortalDataError) as stopped:
        generation.configure_generation(store, state["id"])
    assert stopped.value.code == "resume_latex_invalid"


def test_retained_experience_missing_from_p04_keeps_its_human_order(retained_delivery):
    delivery, retained = retained_delivery
    store, _job, _snapshot, analysis, *_ = delivery
    packet = analysis["material_packet"]
    packet["sources"] = {
        sid: source
        for sid, source in packet["sources"].items()
        if source["record_context"]["experience_id"] != "experience-0"
    }
    _packet_revision(analysis)
    state = prepare(delivery, retained_draft=retained)
    configured = generation.configure_generation(store, state["id"])
    assert [row["experience_id"] for row in configured["experiences"]] == [
        "experience-0",
        "experience-1",
    ]
    context = generation.generation_context(store, state["id"])
    assert context["content_plan"]["assignments"][0]["allowed_fact_refs"] == ["candidate-0::fact-2"]


def _background_profile(delivery):
    analysis = delivery[3]
    packet = analysis["material_packet"]
    profile = deepcopy(next(iter(packet["sources"].values())))
    profile.update(
        source_id="background-profile",
        candidate_id="unique-profile-project",
        text='{"detail": "Unique documented background work."}',
        record_context={"title": "Unique documented project"},
    )
    analysis["selected_source_ids"] = list(packet["sources"])
    packet["sources"][profile["source_id"]] = profile
    _packet_revision(analysis)
    return profile


@pytest.mark.parametrize("retained_delivery", [8], indirect=True)
def test_unselected_profile_background_stays_delivered_outside_writer_assignments(
    retained_delivery,
):
    delivery, retained = retained_delivery
    store, _job, _snapshot, analysis, *_ = delivery
    profile = _background_profile(delivery)
    before = deepcopy(analysis)
    state = prepare(delivery, retained_draft=retained)
    generation.configure_generation(store, state["id"])
    context = generation.generation_context(store, state["id"])
    payload = json.loads((store.root / state["id"] / "input.json").read_text())
    assert payload["context_only_source_ids"] == ["background-profile"]
    assert payload["retained_source_ids"] == [
        "retained-source",
        "retained-source-1",
        "retained-source-2",
        "retained-source-3",
        "retained-source-4",
        "retained-source-5",
        "retained-source-6",
        "retained-source-7",
    ]
    assert payload["material_packet"] == before["material_packet"]
    assert payload["inference_result"] == before["inference_result"]
    assert payload["material_packet"]["sources"]["background-profile"] == profile
    delivered = next(row for row in payload["sources"] if row["source_id"] == "background-profile")
    assert delivered["text"] == profile["text"]
    assert delivered["record_context"] == profile["record_context"]
    assert [row["candidate_id"] for row in context["content_plan"]["assignments"]] == [
        "candidate-0",
        "candidate-1",
    ]
    assert context["content_plan"]["assignments"][0]["allowed_fact_refs"] == [
        "candidate-0::fact-1",
        "candidate-0::fact-2",
        "candidate-0::fact-3",
        "candidate-0::fact-4",
        "candidate-0::fact-5",
        "candidate-0::fact-6",
        "candidate-0::fact-7",
        "candidate-0::fact-8",
        "candidate-0::fact-9",
    ]
    assert context["retained_content"] == retained["resume_content"]
    assert analysis == before


@pytest.mark.parametrize("selection", ["selected_raw", "absent"])
def test_selected_or_historically_unscoped_profile_still_requires_structured_material(
    retained_delivery, selection
):
    delivery, retained = retained_delivery
    analysis = delivery[3]
    _background_profile(delivery)
    if selection == "selected_raw":
        analysis["selected_source_ids"].append("background-profile")
    else:
        analysis.pop("selected_source_ids")
    before = deepcopy(analysis)
    with pytest.raises(PortalDataError) as stopped:
        prepare(delivery, retained_draft=retained)
    assert stopped.value.code == "resume_content_material_required"
    assert "background-profile" in stopped.value.message
    assert analysis == before
