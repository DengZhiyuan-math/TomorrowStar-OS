"""Human list structure survives later real writer and terminal-review handoffs."""

from copy import deepcopy

import pytest
from test_j05_content_generation import delivery as delivery
from test_j05_content_generation import seed_payload, submit
from test_j05_preparation import content_delivery as content_delivery
from test_j05_preparation import full_latex as full_latex
from test_j05_preparation import task_resume as task_resume
from test_json_resume_content import fragment

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_resume_content import assemble_content, content_revision
from career_evidence_graph.career_portal_data import PortalDataError


def test_locked_human_list_keeps_order_and_deleted_items_out_of_next_writer(delivery):
    store, identifier, plan = delivery
    response = fragment()
    first = response["items"][0]
    second = {**deepcopy(first), "id": "second-item", "text": "Second work."}
    removed = {**deepcopy(first), "id": "deleted-item", "text": "Deleted work."}
    response["items"] = [first, removed, second]
    retained = assemble_content(plan, [response])
    first, _, second = retained["experiences"][0]["items"]
    retained["experiences"][0]["items"] = [second, first]
    retained["revision"] = content_revision(retained)
    seed_payload(
        delivery, retained_content=retained, retained_protected_scopes=["experience-demo-1"]
    )
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery, response=response)
    candidate = generation.assemble_generation(store, identifier)
    assert candidate["resume_content"]["experiences"][0]["items"] == [second, first]
    review = generation.review_context(store, identifier)
    assert review["retained_protected_scopes"] == ["experience-demo-1"]


def test_terminal_review_cannot_change_items_in_locked_human_list(delivery):
    store, identifier, plan = delivery
    retained = assemble_content(plan, [fragment()])
    seed_payload(
        delivery, retained_content=retained, retained_protected_scopes=["experience-demo-1"]
    )
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    with pytest.raises(PortalDataError, match="人工保护"):
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
                        "item_id": "item-demo-1",
                        "field": "text",
                        "expected": retained["experiences"][0]["items"][0]["text"],
                        "value": "Replacement wording.",
                    }
                ],
            },
        )


def test_manual_list_structure_is_carried_through_prepare(content_delivery):
    from pathlib import Path
    from types import SimpleNamespace

    from test_j05_preparation import adopt, prepare

    store, *_ = content_delivery
    parent = adopt(content_delivery)
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    source = Path(editing["project_root"]) / editing["main"]
    source.write_text(
        source.read_text().replace(
            "\\end{itemize}\n", "\\item New human work.\n\\end{itemize}\n", 1
        )
    )
    child = store.finish_prism_edit(editing["id"])
    assert child["content_reconciliation"]["status"] == "mapped"
    state = prepare(content_delivery, retained_draft=child)
    context = generation.generation_context(store, state["id"])
    assert context["retained_protected_scopes"] == ["experience-0"]
    assert context["retained_content"] == child["resume_content"]
    configured = generation.configure_generation(store, state["id"])
    for number, row in enumerate(configured["experiences"]):
        eid = row["experience_id"]
        writer = generation.writer_context(store, state["id"], eid)
        generation.submit_fragment(
            store,
            state["id"],
            eid,
            input_revision=writer["input_revision"],
            writer_id=f"later-author-{number}",
            content_fragment={
                "schema_version": "experience-writing/v1",
                "status": "complete",
                "assignment_revision": writer["input_revision"],
                "experience_id": eid,
                "candidate_id": writer["candidate_id"],
                "items": [
                    {
                        "id": eid + "-replacement",
                        "text": "New writer output.",
                        "fact_refs": writer["assignment"]["allowed_fact_refs"],
                    }
                ],
            },
        )
    candidate = generation.assemble_generation(store, state["id"])
    assert (
        candidate["resume_content"]["experiences"][0]["items"]
        == child["resume_content"]["experiences"][0]["items"]
    )
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="later-reviewer",
        passed=True,
        issues=[],
    )
    regenerated = generation.adopt_generation(store, state["id"])
    assert regenerated["retained_protected_scopes"] == ["experience-0"]
    third = prepare(content_delivery, retained_draft=regenerated)
    assert generation.generation_context(store, third["id"])["retained_protected_scopes"] == [
        "experience-0"
    ]


def test_deleted_global_list_stays_empty_despite_new_global_writer(delivery):
    store, identifier, plan = delivery
    retained = assemble_content(plan, [fragment()])
    seed_payload(delivery, retained_content=retained, retained_protected_scopes=["summary"])
    proposed = deepcopy(plan)
    proposed["summary"] = [{**deepcopy(fragment()["items"][0]), "id": "new-summary"}]
    generation.configure_generation(
        store, identifier, writing_plan=proposed, main_writer_id="global-writer"
    )
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    assert candidate["resume_content"]["summary"] == []
    assert generation.review_context(store, identifier)["retained_protected_scopes"] == ["summary"]


def _write_original_pairs(store, identifier):
    state = generation.generation_context(store, identifier)
    for number, assigned in enumerate(state["content_plan"]["assignments"]):
        eid = assigned["experience_id"]
        writer = generation.writer_context(store, identifier, eid)
        generation.submit_fragment(
            store,
            identifier,
            eid,
            input_revision=writer["input_revision"],
            writer_id=f"pair-author-{number}",
            content_fragment={
                "schema_version": "experience-writing/v1",
                "status": "complete",
                "assignment_revision": writer["input_revision"],
                "experience_id": eid,
                "candidate_id": writer["candidate_id"],
                "items": [
                    {
                        "id": eid + "-" + key,
                        "text": text,
                        "fact_refs": writer["assignment"]["allowed_fact_refs"],
                    }
                    for key, text in (
                        ("first", "First recorded work."),
                        ("second", "Second recorded work."),
                    )
                ],
            },
        )


def _pair_parent(delivery, *, summary=False):
    from types import SimpleNamespace

    from test_j05_preparation import prepare

    store, *_ = delivery
    state = prepare(delivery)
    plan = generation.generation_context(store, state["id"])["content_plan"]
    if summary:
        plan["summary"] = [
            {
                "id": "summary-first",
                "text": "Recorded summary.",
                "fact_refs": plan["assignments"][0]["allowed_fact_refs"],
            }
        ]
    generation.configure_generation(
        store,
        state["id"],
        writing_plan=plan,
        main_writer_id="pair-global-author" if summary else None,
    )
    _write_original_pairs(store, state["id"])
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="pair-reviewer",
        passed=True,
        issues=[],
    )
    parent = generation.adopt_generation(store, state["id"])
    store.prism_client = SimpleNamespace(open=lambda binding: "http://127.0.0.1:8799/")
    store.model_runner = lambda *a, **k: SimpleNamespace(
        structured_result={"patches": [], "notices": []}
    )
    return store, parent


def _manual_version(store, parent, transform):
    from pathlib import Path

    editing = store.begin_prism_edit(
        parent["id"], parent["draft_sha256"], task_inputs=parent["task_inputs"]
    )
    source = Path(editing["project_root"]) / editing["main"]
    source.write_text(transform(source.read_text()))
    child = store.finish_prism_edit(editing["id"])
    return store.draft(child["id"])


@pytest.mark.parametrize("first_edit", ["delete", "reorder"])
@pytest.mark.parametrize("second_edit", ["unchanged", "wording"])
def test_consecutive_manual_versions_keep_list_intent_for_later_writers(
    content_delivery, first_edit, second_edit
):
    from test_j05_preparation import prepare

    store, parent = _pair_parent(content_delivery)

    def transform(source):
        if first_edit == "delete":
            return source.replace("\\item First recorded work.\n", "", 1)
        return source.replace(
            "\\item First recorded work.\n\\item Second recorded work.\n",
            "\\item Second recorded work.\n\\item First recorded work.\n",
            1,
        )

    manual1 = _manual_version(store, parent, transform)
    manual2 = _manual_version(
        store,
        manual1,
        lambda source: (
            source
            if second_edit == "unchanged"
            else source.replace("recorded work.", "documented work.", 1)
        ),
    )
    assert manual1["retained_protected_scopes"] == ["experience-0"]
    assert manual2["retained_protected_scopes"] == ["experience-0"]
    state = prepare(content_delivery, retained_draft=manual2)
    assert generation.generation_context(store, state["id"])["retained_protected_scopes"] == [
        "experience-0"
    ]
    generation.configure_generation(store, state["id"])
    _write_original_pairs(store, state["id"])
    candidate = generation.assemble_generation(store, state["id"])
    assert (
        candidate["resume_content"]["experiences"][0]["items"]
        == manual2["resume_content"]["experiences"][0]["items"]
    )
    ids = [item["id"] for item in candidate["resume_content"]["experiences"][0]["items"]]
    assert ids == (
        ["experience-0-second"]
        if first_edit == "delete"
        else ["experience-0-second", "experience-0-first"]
    )


def test_empty_summary_intent_survives_two_manual_versions(content_delivery):
    from test_j05_preparation import prepare

    store, parent = _pair_parent(content_delivery, summary=True)
    manual1 = _manual_version(
        store,
        parent,
        lambda source: source.replace(
            "\\begin{itemize}\n\\item Recorded summary.\n\\end{itemize}\n", "", 1
        ),
    )
    manual2 = _manual_version(store, manual1, lambda source: source)
    assert manual2["retained_protected_scopes"] == ["summary"]
    state = prepare(content_delivery, retained_draft=manual2)
    plan = generation.generation_context(store, state["id"])["content_plan"]
    plan["summary"] = parent["resume_content"]["summary"]
    generation.configure_generation(
        store, state["id"], writing_plan=plan, main_writer_id="later-global-author"
    )
    _write_original_pairs(store, state["id"])
    candidate = generation.assemble_generation(store, state["id"])
    assert candidate["resume_content"]["summary"] == []


@pytest.mark.parametrize("scopes", [[], ["experience-0", "skills"]])
def test_manual_scope_integrity_is_derived_from_parent_not_self_reported(content_delivery, scopes):
    import hashlib
    import json

    store, parent = _pair_parent(content_delivery)
    manual = _manual_version(
        store, parent, lambda source: source.replace("\\item First recorded work.\n", "", 1)
    )
    directory = store.root / manual["id"]
    path = directory / "draft.json"
    payload = json.loads(path.read_bytes())
    payload["retained_protected_scopes"] = scopes
    path.write_text(json.dumps(payload))
    integrity_path = directory / "draft-integrity.json"
    integrity = json.loads(integrity_path.read_bytes())
    integrity["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    integrity_path.write_text(json.dumps(integrity))
    with pytest.raises(PortalDataError):
        store.draft(manual["id"])


def test_manual_experience_omission_survives_a_narrow_packet_and_later_reintroduction(
    content_delivery,
):
    from test_j05_preparation import prepare

    from career_evidence_graph.application_worker import digest

    store, parent = _pair_parent(content_delivery)
    start, end = parent["item_ranges"]["experience-0"]
    removed = parent["latex_source"][start:end]
    manual = _manual_version(store, parent, lambda source: source.replace(removed, "", 1))
    assert [row["id"] for row in manual["resume_content"]["experiences"]] == ["experience-1"]
    assert manual["retained_omitted_experience_ids"] == ["experience-0"]
    full = prepare(content_delivery, retained_draft=manual)
    assert generation.generation_context(store, full["id"])["retained_omitted_experience_ids"] == [
        "experience-0"
    ]
    analysis = content_delivery[3]
    saved_packet = deepcopy(analysis["material_packet"])
    saved_inference = deepcopy(analysis["inference_result"])
    packet = analysis["material_packet"]
    packet["sources"] = {
        key: row
        for key, row in packet["sources"].items()
        if row.get("record_context", {}).get("experience_id") != "experience-0"
    }
    packet["revision"] = digest({key: value for key, value in packet.items() if key != "revision"})
    inference = analysis["inference_result"]
    inference["material_packet_revision"] = packet["revision"]
    inference["revision"] = digest(
        {key: value for key, value in inference.items() if key != "revision"}
    )
    narrow = prepare(content_delivery, retained_draft=manual)
    context = generation.generation_context(store, narrow["id"])
    assert [row["experience_id"] for row in context["content_plan"]["assignments"]] == [
        "experience-1"
    ]
    assert context["retained_omitted_experience_ids"] == ["experience-0"]
    generation.configure_generation(store, narrow["id"])
    _write_original_pairs(store, narrow["id"])
    candidate = generation.assemble_generation(store, narrow["id"])
    generation.review_generation(
        store,
        narrow["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="narrow-reviewer",
        passed=True,
        issues=[],
    )
    regenerated = generation.adopt_generation(store, narrow["id"])
    assert regenerated["retained_omitted_experience_ids"] == ["experience-0"]
    assert {
        row["record_context"]["experience_id"] for row in regenerated["available_review_sources"]
    } == {"experience-1"}
    analysis["material_packet"] = saved_packet
    analysis["inference_result"] = saved_inference
    next_state = prepare(content_delivery, retained_draft=regenerated)
    context = generation.generation_context(store, next_state["id"])
    assert context["retained_omitted_experience_ids"] == ["experience-0"]
    with pytest.raises(PortalDataError, match="本轮已交付"):
        generation.configure_generation(store, next_state["id"])
    plan = context["content_plan"]
    plan["assignments"] = [
        row for row in plan["assignments"] if row["experience_id"] != "experience-0"
    ]
    configured = generation.configure_generation(store, next_state["id"], writing_plan=plan)
    assert [row["experience_id"] for row in configured["experiences"]] == ["experience-1"]
