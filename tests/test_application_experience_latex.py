"""Synthetic agent handoffs test persistence and guards, not real agent quality."""

from copy import deepcopy

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


def prepare(data):
    store, job, sources, analysis, calls, project, output, inputs = data
    selected = [row["source_ids"][0] for row in output["groups"][1:]]
    analysis["selected_source_ids"] = selected
    analysis["requirements"] = [{"source_ids": selected}]
    state = generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        task_inputs=inputs,
        latex_base=source_snapshot(project, "main.tex"),
    )
    return state


def configure(data, state):
    store, _, _, _, _, _, output, _ = data
    experiences = [
        {
            "experience_id": f"experience-{index}",
            "source_ids": row["source_ids"],
            "group_indexes": [index],
        }
        for index, row in enumerate(output["groups"])
        if index
    ]
    return generation.configure_generation(
        store, state["id"], groups=output["groups"], experiences=experiences
    )


def submit(data, state, index=0, *, issues=None):
    store = data[0]
    experience = state["experiences"][index]
    eid = experience["experience_id"]
    context = generation.writer_context(store, state["id"], eid)
    source = generation.read_source(store, state["id"], eid, experience["source_ids"][0])
    receipt = {key: source[key] for key in ("source_id", "offset", "end", "source_revision")}
    return generation.submit_fragment(
        store,
        state["id"],
        eid,
        input_revision=experience["input_revision"],
        groups=context["groups"],
        source_notes=[
            {
                "source_id": source["source_id"],
                "reason": "Supports the bounded service claim",
                "read": receipt,
            }
        ],
        issues=issues or [],
        writer_id=f"synthetic-writer-{index}",
    )


def test_handoff_preserves_base_and_requires_all_writers_and_independent_review(full_latex):
    store, _, _, _, calls, project, _, _ = full_latex
    original = (project / "main.tex").read_bytes()
    state = prepare(full_latex)
    assert prepare(full_latex)["id"] == state["id"]
    assert state["kind"] == "experience_handoff"
    assert calls == []
    state = configure(full_latex, state)
    submit(full_latex, state)
    with pytest.raises(PortalDataError):
        generation.assemble_generation(store, state["id"])
    for index in range(1, 6):
        submit(full_latex, state, index)
    candidate = generation.assemble_generation(store, state["id"])
    assert (project / "main.tex").read_bytes() == original
    assert len(candidate["fragments"]) == 6
    assert (
        generation.review_context(store, state["id"])["latex_source"] == candidate["latex_source"]
    )
    with pytest.raises(PortalDataError):
        generation.review_generation(
            store,
            state["id"],
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="synthetic-writer-0",
            passed=True,
            issues=[],
        )
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="synthetic-final-reviewer",
        passed=True,
        issues=[],
    )
    result = generation.adopt_generation(store, state["id"])
    assert result["origin"] == "generated_latex"
    assert result["latex_source"] == candidate["latex_source"]
    assert generation.adopt_generation(store, state["id"])["id"] == result["id"]
    assert prepare(full_latex)["id"] == result["id"]
    assert calls == []


def test_writer_scope_and_stale_review_fail_closed(full_latex):
    store = full_latex[0]
    state = configure(full_latex, prepare(full_latex))
    first, second = state["experiences"][:2]
    with pytest.raises(PortalDataError):
        generation.read_source(store, state["id"], first["experience_id"], second["source_ids"][0])
    for index in range(6):
        submit(full_latex, state, index)
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="synthetic-final-reviewer",
        passed=True,
        issues=[],
    )
    submit(full_latex, state)
    with pytest.raises(PortalDataError):
        generation.adopt_generation(store, state["id"])
    context = generation.writer_context(store, state["id"], first["experience_id"])
    assert context["previous_fragment"]["writer_id"] == "synthetic-writer-0"


def test_duplicate_and_missing_experiences_rejected(full_latex):
    store = full_latex[0]
    state = configure(full_latex, prepare(full_latex))
    bad = deepcopy(state["experiences"])
    bad[1]["experience_id"] = bad[0]["experience_id"]
    with pytest.raises(PortalDataError):
        generation.configure_generation(
            store, state["id"], groups=full_latex[6]["groups"], experiences=bad
        )
    with pytest.raises(PortalDataError):
        generation.configure_generation(
            store,
            state["id"],
            groups=full_latex[6]["groups"],
            experiences=state["experiences"][:-1],
        )


def test_changed_input_reuses_only_unaffected_fragments(full_latex, tmp_path):
    from career_evidence_graph.application_resume import career_source_snapshot

    store = full_latex[0]
    full_latex[3]["material_packet"] = _fixed_material_packet(full_latex, tmp_path / "first")
    state = configure(full_latex, prepare(full_latex))
    for index in range(6):
        submit(full_latex, state, index)
    source = store.catalog.root / "contributions/project-1.md"
    source.write_text(source.read_text().replace("Analyzed strategy", "Analyzed revised strategy"))
    newer = list(full_latex)
    newer[2] = career_source_snapshot(store.catalog)
    newer[3] = deepcopy(newer[3])
    newer[3]["source_snapshot_revision"] = newer[2]["revision"]
    newer[7] = {**newer[7], "sources_revision": newer[2]["revision"]}
    newer[3]["material_packet"] = _fixed_material_packet(newer, tmp_path / "next")
    next_state = configure(newer, prepare(newer))
    assert next_state["id"] != state["id"]
    completed = generation.generation_state(store, next_state["id"])["completed_experience_ids"]
    assert completed == [f"experience-{i}" for i in range(2, 7)]
    with pytest.raises(PortalDataError):
        generation.assemble_generation(store, next_state["id"])
    submit(newer, next_state, 0)
    assert generation.assemble_generation(store, next_state["id"])["candidate_sha256"]


def test_concurrent_fragment_handoffs_preserve_every_completed_writer(full_latex):
    from concurrent.futures import ThreadPoolExecutor

    store = full_latex[0]
    state = configure(full_latex, prepare(full_latex))
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(submit, full_latex, state, index) for index in range(6)]
        for future in futures:
            future.result()
    assert len(generation.generation_state(store, state["id"])["completed_experience_ids"]) == 6
    assert generation.assemble_generation(store, state["id"])["candidate_sha256"]


def test_large_source_reads_are_scoped_and_bounded_without_whole_library_call(full_latex):
    from career_evidence_graph.application_resume import career_source_snapshot

    store = full_latex[0]
    source = store.catalog.root / "contributions/project-1.md"
    text = source.read_text().replace(
        "## Responsibility attribution",
        ("Supported detail. " * 10000) + "\n\n## Responsibility attribution",
    )
    source.write_text(text)
    large = list(full_latex)
    large[2] = career_source_snapshot(store.catalog)
    large[3] = deepcopy(large[3])
    large[3]["source_snapshot_revision"] = large[2]["revision"]
    large[7] = {**large[7], "sources_revision": large[2]["revision"]}
    state = configure(large, prepare(large))
    experience = state["experiences"][0]
    contents = []
    while True:
        result = generation.read_source(
            store,
            state["id"],
            experience["experience_id"],
            experience["source_ids"][0],
            offset=sum(map(len, contents)),
            limit=16000,
        )
        assert len(result["text"]) <= 16000
        contents.append(result["text"])
        if result["complete"]:
            break
    assert len("".join(contents).encode()) > 128000
    assert full_latex[4] == []


def test_retained_source_update_preserves_manual_unaffected_groups(full_latex):
    from test_full_latex_generation import generate

    from career_evidence_graph.application_resume import career_source_snapshot

    store, job, _, analysis, _, _, _, inputs = full_latex
    original = generate(full_latex)
    editable = store.prepare_group_review(
        original["id"], original["draft_sha256"], task_inputs=inputs
    )
    text = editable["latex_source"].replace(
        "Analyzed strategy; built 6 Python services.", "Built 6 Python services; analyzed strategy."
    )
    manual = store.save_automatic_source(
        editable["id"], editable["draft_sha256"], task_inputs=inputs, latex_source=text
    )
    source = store.catalog.root / "contributions/project-1.md"
    source.write_text(source.read_text().replace("built 1 Python", "built 11 Python"))
    snapshot = career_source_snapshot(store.catalog)
    selected = [
        source["source_id"]
        for source in snapshot["items"]
        if source["title"].startswith("Project ")
    ]
    analysis = deepcopy(analysis) | {
        "source_snapshot_revision": snapshot["revision"],
        "selected_source_ids": selected,
        "requirements": [{"source_ids": selected}],
    }
    state = generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=snapshot,
        analysis=analysis,
        task_inputs={"sources_revision": snapshot["revision"]},
        latex_base=manual["source_checkpoint"],
        retained_draft=manual,
    )
    context = generation.generation_context(store, state["id"])
    groups = context["update_context"]["retained_groups"]
    experiences = [
        {"experience_id": f"experience-{i}", "source_ids": row["source_ids"], "group_indexes": [i]}
        for i, row in enumerate(groups)
        if i
    ]
    state = generation.configure_generation(
        store, state["id"], groups=groups, experiences=experiences
    )
    for index in range(6):
        experience = state["experiences"][index]
        eid = experience["experience_id"]
        writer = generation.writer_context(store, state["id"], eid)
        updated = deepcopy(writer["groups"])
        if index == 0:
            updated[0]["latex"] = updated[0]["latex"].replace("built 1 Python", "built 11 Python")
        receipt = generation.read_source(store, state["id"], eid, experience["source_ids"][0])
        generation.submit_fragment(
            store,
            state["id"],
            eid,
            input_revision=experience["input_revision"],
            groups=updated,
            source_notes=[
                {
                    "source_id": receipt["source_id"],
                    "reason": "Bounded changed fact",
                    "read": {
                        k: receipt[k] for k in ("source_id", "offset", "end", "source_revision")
                    },
                }
            ],
            issues=[],
            writer_id=f"writer-{index}",
        )
    candidate = generation.assemble_generation(store, state["id"])
    assert "built 11 Python services." in candidate["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in candidate["latex_source"]


def test_nonselected_base_experience_is_explicitly_omitted_without_writer(full_latex):
    from career_evidence_graph.application_full_latex import _body

    data = list(full_latex)
    original_groups = deepcopy(data[6]["groups"])
    data[6] = {**data[6], "groups": original_groups[:-1]}
    state = prepare(data)
    groups = deepcopy(original_groups)
    _, body, _ = _body((data[5] / "main.tex").read_text())
    groups[-1]["latex"] = "".join(body.splitlines(keepends=True)[-2:])
    groups[-1]["disposition"] = "omit"
    groups[-1]["reason"] = "Explicitly omit the nonselected experience for this JD"
    experiences = [
        {
            "experience_id": f"experience-{i}",
            "source_ids": group["source_ids"],
            "group_indexes": [i],
        }
        for i, group in enumerate(groups[:-1])
        if i
    ]
    state = generation.configure_generation(
        data[0], state["id"], groups=groups, experiences=experiences
    )
    for i in range(5):
        submit(data, state, i)
    assembled = generation.assemble_generation(data[0], state["id"])
    assert "Project 6" not in assembled["latex_source"]
    assert "Project 5" in assembled["latex_source"]
    import json

    plan = json.loads((data[0].root / state["id"] / "assembled-plan.json").read_text())
    assert len(plan["omitted_groups"]) == 1
    assert plan["omitted_groups"][0]["original"] == groups[-1]["latex"]


def test_boundary_evidence_has_separate_bounded_reads(full_latex):
    state = configure(full_latex, prepare(full_latex))
    store = full_latex[0]
    experience = state["experiences"][0]
    context = generation.writer_context(store, state["id"], experience["experience_id"])
    assert "boundaries" in context["sources"][0]["readable_fields"]
    boundary = generation.read_source(
        store,
        state["id"],
        experience["experience_id"],
        experience["source_ids"][0],
        field="boundaries",
        limit=8,
    )
    assert boundary["field"] == "boundaries"
    assert len(boundary["text"]) <= 8


def test_one_experience_can_group_multiple_sources_and_body_blocks(full_latex):
    store = full_latex[0]
    state = configure(full_latex, prepare(full_latex))
    first, second, *rest = state["experiences"]
    combined = {
        "experience_id": "combined-experience",
        "source_ids": first["source_ids"] + second["source_ids"],
        "group_indexes": first["group_indexes"] + second["group_indexes"],
    }
    state = generation.configure_generation(
        store, state["id"], groups=full_latex[6]["groups"], experiences=[combined, *rest]
    )
    context = generation.writer_context(store, state["id"], combined["experience_id"])
    notes = []
    for sid in combined["source_ids"]:
        read = generation.read_source(store, state["id"], combined["experience_id"], sid)
        notes.append(
            {
                "source_id": sid,
                "reason": "Each source supports its own mapped body block",
                "read": {
                    key: read[key] for key in ("source_id", "offset", "end", "source_revision")
                },
            }
        )
    generation.submit_fragment(
        store,
        state["id"],
        combined["experience_id"],
        input_revision=context["input_revision"],
        groups=context["groups"],
        source_notes=notes,
        issues=[],
        writer_id="one-combined-writer",
    )
    for i in range(1, 5):
        submit(full_latex, state, i)
    assert len(generation.generation_state(store, state["id"])["completed_experience_ids"]) == 5
    assert generation.assemble_generation(store, state["id"])["candidate_sha256"]


@pytest.mark.parametrize("empty_candidate", ["", " \n\n"])
def test_empty_pending_candidate_keeps_manual_source_and_omissions(full_latex, empty_candidate):
    from test_full_latex_generation import generate

    from career_evidence_graph.application_group_review import unwrapped_group

    store, job, sources, analysis, calls, _, output, inputs = full_latex
    selected = [row["source_ids"][0] for row in output["groups"][1:]]
    analysis["selected_source_ids"] = selected
    analysis["requirements"] = [{"source_ids": selected}]
    output["groups"][1].update(
        latex=empty_candidate, disposition="verify", reason="Responsibility remains unresolved"
    )
    output["groups"][2].update(disposition="omit", reason="Keep the user's omission")
    output["groups"][6]["latex"] = output["groups"][6]["latex"].replace(
        "Analyzed strategy; built 6 Python services.",
        "Built 6 Python services; analyzed strategy.",
    )
    retained = generate(full_latex)
    calls.clear()
    original = retained["latex_source"]
    assert "TomorrowStar group" not in original
    assert "Project 1" not in original and "Project 2" not in original
    state = generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        task_inputs=inputs,
        latex_base=retained["source_checkpoint"],
        retained_draft=retained,
    )
    context = generation.generation_context(store, state["id"])
    groups = context["update_context"]["retained_groups"]
    assert context["update_context"]["pending_group_indexes"] == [1]
    assert unwrapped_group(groups[1]["latex"]).strip() == ""
    assert "Project 1" not in context["base"]
    state = generation.configure_generation(
        store,
        state["id"],
        groups=groups,
        experiences=[
            {
                "experience_id": "selected-projects",
                "source_ids": selected,
                "group_indexes": list(range(1, len(groups))),
            }
        ],
    )
    writer = generation.writer_context(store, state["id"], "selected-projects")
    fragment = deepcopy(writer["groups"])
    fragment[0].update(disposition="omit", reason="Explicitly omit the unresolved empty candidate")
    notes = []
    for sid in selected:
        read = generation.read_source(store, state["id"], "selected-projects", sid)
        notes.append(
            {
                "source_id": sid,
                "reason": "Read selected project facts and retain manual wording",
                "read": {
                    key: read[key] for key in ("source_id", "offset", "end", "source_revision")
                },
            }
        )
    generation.submit_fragment(
        store,
        state["id"],
        "selected-projects",
        input_revision=writer["input_revision"],
        groups=fragment,
        source_notes=notes,
        issues=[],
        writer_id="synthetic-writer",
    )
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="synthetic-reviewer",
        passed=True,
        issues=[],
    )
    adopted = generation.adopt_generation(store, state["id"])
    assert adopted["verification_queue"] == []
    assert "Project 1" not in adopted["latex_source"]
    assert "Project 2" not in adopted["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in adopted["latex_source"]
    assert store.draft(retained["id"])["latex_source"] == original
    assert store.draft(retained["id"])["verification_queue"][0]["rewritten"] == empty_candidate
    assert store.draft(adopted["id"])["latex_source"] == adopted["latex_source"]
    assert calls == []


def test_retained_selected_group_keeps_existing_supporting_reference(full_latex):
    from test_full_latex_generation import generate

    store, job, sources, analysis, calls, _, output, inputs = full_latex
    primary = output["groups"][1]["source_ids"][0]
    supporting = output["groups"][2]["source_ids"][0]
    unrelated = output["groups"][3]["source_ids"][0]
    output["groups"][1]["source_ids"].append(supporting)
    output["groups"][1].update(disposition="verify", reason="Recheck this selected experience")
    retained = generate(full_latex)
    calls.clear()
    analysis["selected_source_ids"] = [primary]
    analysis["requirements"] = [{"source_ids": [primary]}]
    state = generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        task_inputs=inputs,
        latex_base=retained["source_checkpoint"],
        retained_draft=retained,
    )
    context = generation.generation_context(store, state["id"])
    groups = context["update_context"]["retained_groups"]
    experience = {
        "experience_id": "selected-project",
        "source_ids": [primary, supporting],
        "group_indexes": [1],
    }
    configured = generation.configure_generation(
        store,
        state["id"],
        groups=groups,
        experiences=[experience],
    )
    assert configured["experiences"][0]["source_ids"] == [primary, supporting]
    writer = generation.writer_context(store, state["id"], "selected-project")
    assert writer["groups"][0]["source_ids"] == [primary, supporting]
    assert (
        generation.read_source(store, state["id"], "selected-project", supporting)["source_id"]
        == supporting
    )
    with pytest.raises(PortalDataError):
        generation.configure_generation(
            store,
            state["id"],
            groups=groups,
            experiences=[experience | {"source_ids": [primary, supporting, unrelated]}],
        )
    with pytest.raises(PortalDataError):
        generation.configure_generation(
            store,
            state["id"],
            groups=groups,
            experiences=[
                experience
                | {"source_ids": [primary, supporting, unrelated], "group_indexes": [1, 2, 3]}
            ],
        )
    notes = []
    for sid in (primary, supporting):
        read = generation.read_source(store, state["id"], "selected-project", sid)
        notes.append(
            {
                "source_id": sid,
                "reason": "Retain the selected group's existing evidence",
                "read": {
                    key: read[key] for key in ("source_id", "offset", "end", "source_revision")
                },
            }
        )
    generation.submit_fragment(
        store,
        state["id"],
        "selected-project",
        input_revision=writer["input_revision"],
        groups=writer["groups"],
        source_notes=notes,
        issues=[],
        writer_id="synthetic-writer",
    )
    candidate = generation.assemble_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="synthetic-reviewer",
        passed=True,
        issues=[],
    )
    adopted = generation.adopt_generation(store, state["id"])
    project = next(g for g in adopted["review_groups"] if g["title"] == "Project 1")
    assert [s["source_id"] for s in project["sources"]] == [primary, supporting]
    assert store.draft(adopted["id"])["latex_source"] == adopted["latex_source"]
    assert store.draft(retained["id"])["latex_source"] == retained["latex_source"]
    assert calls == []


@pytest.fixture
def retained_source_selection(full_latex, request):
    from test_application_source_reuse import write_retained_material
    from test_full_latex_generation import generate

    from career_evidence_graph.application_resume import career_source_snapshot

    data = list(full_latex)
    store, job, _, analysis, calls, project, output, inputs = data
    original_ids = [g["source_ids"][0] for g in output["groups"][1:3]]
    unknown = getattr(request, "param", None) == "unknown"
    write_retained_material(
        store.catalog.root,
        (project / "main.tex").read_text(),
        groups=[
            {
                "title": f"Accepted project {i + 1}",
                "start_line": 4 + i * 2,
                "end_line": 5 + i * 2,
                "source_kind": "accepted_resume",
                "context_source_ids": [] if unknown else [sid],
                "education_profile_locator": None,
                "education_profile_sha256": None,
            }
            for i, sid in enumerate(original_ids)
        ],
    )
    for number in (1, 2):
        path = store.catalog.root / f"contributions/project-{number}.md"
        text = path.read_text().split("## Responsibility attribution")[0]
        attribution = "Unknown" if unknown else "Editorial statement; review required"
        path.write_text(text + "## Responsibility attribution\n\n" + attribution + "\n")
    sources = career_source_snapshot(store.catalog)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    accepted = [
        s["source_id"]
        for s in sources["retained_materials"]
        if s.get("source_kind") == "accepted_resume"
    ]
    assert len(accepted) == 2
    for index, sid in enumerate(accepted, 1):
        output["groups"][index]["source_ids"].append(sid)
    output["groups"][2]["latex"] = ""
    output["groups"][3].update(disposition="omit", reason="Existing manual omission")
    output["groups"][6]["latex"] = output["groups"][6]["latex"].replace(
        "Analyzed strategy; built 6 Python services.",
        "Built 6 Python services; analyzed strategy.",
    )
    retained = generate(data)
    assert len(retained["verification_queue"]) == 2
    calls.clear()
    analysis["selected_source_ids"] = [original_ids[0]]
    analysis["requirements"] = [{"source_ids": [original_ids[0]]}]
    state = generation.prepare_generation(
        store,
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        task_inputs=inputs,
        latex_base=retained["source_checkpoint"],
        retained_draft=retained,
    )
    context = generation.generation_context(store, state["id"])
    groups = context["update_context"]["retained_groups"]
    groups[2].update(
        source_ids=[accepted[1]],
        disposition="omit",
        reason="Omit unresolved unselected wording; retain accepted provenance",
    )
    state = generation.configure_generation(
        store,
        state["id"],
        groups=groups,
        experiences=[
            {
                "experience_id": "selected-project",
                "source_ids": [original_ids[0], accepted[0]],
                "group_indexes": [1],
            }
        ],
    )
    writer = generation.writer_context(store, state["id"], "selected-project")
    return data, retained, state, writer, accepted


def select_supporting_sources(case, source_ids):
    data, _, state, writer, _ = case
    store = data[0]
    groups = deepcopy(writer["groups"])
    groups[0].update(
        source_ids=source_ids,
        reason="Accepted wording supports this claim; editorial record is context only",
    )
    notes = []
    for sid in writer["source_ids"]:
        read = generation.read_source(store, state["id"], "selected-project", sid)
        notes.append(
            {
                "source_id": sid,
                "reason": "Check accepted text and distinguish editorial context",
                "read": {
                    key: read[key] for key in ("source_id", "offset", "end", "source_revision")
                },
            }
        )
    generation.submit_fragment(
        store,
        state["id"],
        "selected-project",
        input_revision=writer["input_revision"],
        groups=groups,
        source_notes=notes,
        issues=[],
        writer_id="synthetic-writer",
    )


def test_pending_source_selection_requires_independent_review_and_preserves_provenance(
    retained_source_selection,
):
    data, retained, state, writer, accepted = retained_source_selection
    store = data[0]
    select_supporting_sources(retained_source_selection, [accepted[0]])
    candidate = generation.assemble_generation(store, state["id"])
    review = generation.review_context(store, state["id"])
    selection = next(g for g in review["source_selections"] if g["group_index"] == 1)
    assert selection["original_source_ids"] == writer["groups"][0]["source_ids"]
    assert selection["actual_source_ids"] == [accepted[0]]
    assert "editorial record is context only" in selection["reason"]
    with pytest.raises(PortalDataError):
        generation.adopt_generation(store, state["id"])
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="synthetic-reviewer",
        passed=True,
        issues=[],
    )
    adopted = generation.adopt_generation(store, state["id"])
    assert adopted["verification_queue"] == []
    assert "Project 2" not in adopted["latex_source"] and "Project 3" not in adopted["latex_source"]
    assert "Built 6 Python services; analyzed strategy." in adopted["latex_source"]
    assert store.draft(retained["id"])["latex_source"] == retained["latex_source"]
    assert store.draft(adopted["id"])["latex_source"] == adopted["latex_source"]
    import json

    saved = json.loads((store.root / adopted["id"] / "draft.json").read_text())
    assert set(writer["source_ids"]) <= {s["source_id"] for s in saved["generation_sources"]}
    assert data[4] == []


@pytest.mark.parametrize("selection", ["empty", "editorial", "other_group"])
def test_pending_source_selection_rejects_missing_accepted_or_other_group(
    retained_source_selection, selection
):
    data, _, state, writer, accepted = retained_source_selection
    ids = {"empty": [], "editorial": [writer["source_ids"][0]], "other_group": [accepted[1]]}[
        selection
    ]
    with pytest.raises(PortalDataError):
        select_supporting_sources(retained_source_selection, ids)
        generation.assemble_generation(data[0], state["id"])


@pytest.mark.parametrize("retained_source_selection", ["unknown"], indirect=True)
def test_pending_selection_cannot_hide_unknown_contribution_on_included_group(
    retained_source_selection,
):
    data, _, state, _, accepted = retained_source_selection
    select_supporting_sources(retained_source_selection, [accepted[0]])
    with pytest.raises(PortalDataError):
        generation.assemble_generation(data[0], state["id"])


def test_pending_selection_keeps_fact_guards_and_unaffected_groups(retained_source_selection):
    data, _, state, writer, _ = retained_source_selection
    select_supporting_sources(retained_source_selection, writer["source_ids"])
    with pytest.raises(PortalDataError, match="组装稿仍有无法核验的正文"):
        generation.assemble_generation(data[0], state["id"])
    context = generation.generation_context(data[0], state["id"])
    groups = context["update_context"]["retained_groups"]
    groups[-1]["source_ids"] = [groups[-1]["source_ids"][0], writer["source_ids"][1]]
    with pytest.raises(PortalDataError, match="未受影响"):
        generation.configure_generation(
            data[0],
            state["id"],
            groups=groups,
            experiences=state["experiences"],
        )


def test_legacy_model_still_cannot_shrink_retained_source_references(retained_source_selection):
    import json
    from types import SimpleNamespace

    data, retained, _, _, accepted = retained_source_selection
    store, job, sources, analysis, _, _, _, inputs = data

    def model(_config, prompt, **_options):
        payload = json.loads(prompt[prompt.index("{") :])
        groups = deepcopy(payload["update_context"]["retained_groups"])
        groups[1]["source_ids"] = [accepted[0]]
        groups[2].update(source_ids=[accepted[1]], disposition="omit")
        return SimpleNamespace(
            structured_result={"groups": groups, "limitations": []}, model_dump=lambda **_: {}
        )

    store.model_runner = model
    with pytest.raises(PortalDataError, match="职业更正须对应"):
        store.generate_for_task(
            job["id"],
            job["revision"],
            source_snapshot=sources,
            analysis=analysis,
            draft_only=True,
            task_inputs=inputs,
            latex_base=retained["source_checkpoint"],
            retained_draft=retained,
        )


def _fixed_job_brief(store, analysis, tmp_path):
    from test_application_job_brief import runner_for

    from career_evidence_graph.application_job_brief import create_job_brief

    job = store.applications.get_application(analysis["application_id"])
    return create_job_brief(
        job,
        tmp_path / "job-brief",
        runner=runner_for(
            {
                "business_object": "Operational delivery",
                "role_understanding": analysis["role_understanding"],
                "groups": [
                    {
                        "label": "Recorded duties",
                        "jd_quote": job["job_description"],
                        "operator": "all",
                        "importance": "required",
                        "hard_condition": False,
                        "weight": 1,
                        "weight_reason": "Only recorded duty group",
                        "requirements": [
                            {"text": job["job_description"], "jd_quote": job["job_description"]}
                        ],
                    }
                ],
            }
        ),
    )


def _fixed_material_packet(full_latex, tmp_path):
    from career_evidence_graph.application_material_packet import prepare_material_packet

    _, job, sources, analysis, *_ = full_latex
    _, packet = prepare_material_packet(
        job,
        sources,
        tmp_path / "fixed-packet",
        runner=lambda *args, **kwargs: pytest.fail("Small fixed sources need no extra model call"),
        job_brief=analysis.get("job_brief"),
        requirements=analysis["requirements"],
    )
    return packet


def test_business_goal_and_selection_reasons_reach_orchestrator(full_latex, tmp_path):
    store, _, _, analysis, _, _, _, _ = full_latex
    analysis["role_understanding"] = {
        "business_objective": "Improve delivery decisions using reliable operational evidence.",
        "work_outputs": ["Validated operational recommendations"],
        "methods_role": "Python and statistics support the operational decisions.",
    }
    analysis["selection_rationale"] = []
    analysis["job_brief"] = _fixed_job_brief(store, analysis, tmp_path)
    analysis["material_packet"] = _fixed_material_packet(full_latex, tmp_path)
    state = prepare(full_latex)
    context = generation.generation_context(store, state["id"])
    assert context["role_understanding"] == analysis["role_understanding"]
    assert context["selection_rationale"] == []
    assert context["requirements"] == analysis["requirements"]
    assert context["job_brief"] == analysis["job_brief"]
    assert context["material_packet"] == analysis["material_packet"]


def test_business_plan_is_required_and_reaches_writers_and_final_review(full_latex, tmp_path):
    store, _, _, analysis, _, _, output, _ = full_latex
    analysis["role_understanding"] = {
        "business_objective": "Improve operational delivery decisions.",
        "work_outputs": ["Validated operational recommendations"],
        "methods_role": "Python supports analysis of operational evidence.",
    }
    analysis["job_brief"] = _fixed_job_brief(store, analysis, tmp_path)
    analysis["material_packet"] = _fixed_material_packet(full_latex, tmp_path)
    state = prepare(full_latex)
    with pytest.raises(PortalDataError, match="业务"):
        configure(full_latex, state)
    experiences = [
        {
            "experience_id": f"experience-{index}",
            "source_ids": row["source_ids"],
            "group_indexes": [index],
            "business_relevance": "Service delivery provides evidence for operational decisions.",
            "evidence_role": "direct_domain",
            "focus": "Explain the operational problem, contribution and supported outcome.",
        }
        for index, row in enumerate(output["groups"])
        if index
    ]
    plan = {
        "summary_focus": "Operational research supported by Python service delivery.",
        "ordering_rationale": "Lead with operational contributions before implementation methods.",
    }
    state = generation.configure_generation(
        store,
        state["id"],
        groups=output["groups"],
        experiences=experiences,
        organization_plan=plan,
    )
    writer = generation.writer_context(store, state["id"], "experience-1")
    assert writer["role_understanding"] == analysis["role_understanding"]
    assert writer["job_brief"] == analysis["job_brief"]
    assert writer["material_packet"]["parent_revision"] == analysis["material_packet"]["revision"]
    assert set(writer["material_packet"]["sources"]) <= set(writer["source_ids"])
    assert set(writer["material_packet"]["source_reads"]) <= set(writer["source_ids"])
    assert set(writer["material_packet"]["sources"]) < set(analysis["material_packet"]["sources"])
    assert writer["organization_plan"] == plan
    assert writer["business_relevance"] == experiences[0]["business_relevance"]
    for index in range(6):
        submit(full_latex, state, index)
    candidate = generation.assemble_generation(store, state["id"])
    review = generation.review_context(store, state["id"])
    assert review["role_understanding"] == analysis["role_understanding"]
    assert review["job_brief"] == analysis["job_brief"]
    assert review["material_packet"] == analysis["material_packet"]
    assert review["organization_plan"] == plan
    with pytest.raises(PortalDataError, match="业务"):
        generation.review_generation(
            store,
            state["id"],
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="independent-reviewer",
            passed=True,
            issues=[],
        )
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="independent-reviewer",
        passed=True,
        issues=[],
        business_alignment="The summary and leading experiences address operational decisions; "
        "Python appears as a supporting method, with no added domain claims.",
    )
    # A new selection interpretation is new writer input, even with unchanged facts and JD.
    analysis["selection_rationale"] = [
        {
            "source_id": experiences[0]["source_ids"][0],
            "business_relevance": "Transferable service methods, not direct operational research.",
            "evidence_role": "transferable",
        }
    ]
    successor = prepare(full_latex)
    reconfigured = generation.configure_generation(
        store,
        successor["id"],
        groups=output["groups"],
        experiences=experiences,
        organization_plan=plan,
    )
    assert "experience-1" not in reconfigured["completed_experience_ids"]
    assert "experience-2" in reconfigured["completed_experience_ids"]
    changed_plan = dict(plan, summary_focus="Transferable research for operational decisions.")
    changed = generation.configure_generation(
        store,
        state["id"],
        groups=output["groups"],
        experiences=experiences,
        organization_plan=changed_plan,
    )
    assert changed["completed_experience_ids"] == []
    with pytest.raises(PortalDataError):
        generation.adopt_generation(store, state["id"])
