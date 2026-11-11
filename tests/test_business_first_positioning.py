"""Editable global positioning goes through the formal generator, not a separate CV writer."""

from copy import deepcopy

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.mark.parametrize("missing_global_support", [False, True, "boundaries", "empty"])
def test_formal_generation_can_replace_template_positioning_from_selected_evidence(
    full_latex, missing_global_support
):
    store, job, _, analysis, _, project, output, inputs = full_latex
    source_file = store.catalog.root / "contributions/project-1.md"
    source_file.write_text(
        "# Project 1\n\n## Scope\n\n"
        "Compared option returns, transaction costs and drawdowns.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Research | User |\n"
    )
    sources = career_source_snapshot(store.catalog)
    analysis["source_snapshot_revision"] = sources["revision"]
    analysis["role_understanding"] = {
        "business_objective": "Research systematic investment strategies.",
        "work_outputs": ["Tested investment hypotheses with costs and risk"],
        "methods_role": "Programming supports financial hypothesis testing.",
    }
    inputs["sources_revision"] = sources["revision"]
    old_summary = "\\section*{Profile}\nAI researcher focused on model evaluation.\n"
    new_summary = "\\section*{Profile}\nCompared option returns, transaction costs and drawdowns.\n"
    main = project / "main.tex"
    original = main.read_text().replace("Synthetic Person\n", "Synthetic Person\n" + old_summary)
    main.write_text(original)
    groups = deepcopy(output["groups"])
    for group in groups[1:]:
        group["start_line"] += 2
        group["end_line"] += 2
    groups.insert(
        1,
        {
            "title": "Profile",
            "start_line": 2,
            "end_line": 3,
            "source_ids": groups[1]["source_ids"],
            "latex": new_summary,
            "disposition": "include",
            "reason": "Use investment evidence for the role positioning",
        },
    )
    selected = list(dict.fromkeys(sid for group in groups[1:] for sid in group["source_ids"]))
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
    experiences = [
        {
            "experience_id": f"experience-{index}",
            "source_ids": group["source_ids"],
            "group_indexes": [index],
            "business_relevance": "Supports the investment research work.",
            "evidence_role": "direct_domain",
            "focus": "State the supported research contribution.",
        }
        for index, group in enumerate(groups)
        if index > 1
    ]
    if missing_global_support is True:
        experiences[0]["source_ids"] = list(
            dict.fromkeys(experiences[0]["source_ids"] + experiences[1]["source_ids"])
        )
    state = generation.configure_generation(
        store,
        state["id"],
        groups=groups,
        experiences=experiences,
        organization_plan={
            "summary_focus": "Investment research with costs and risk.",
            "ordering_rationale": "Use direct investment evidence before transferable methods.",
            "positioning_group_indexes": [1],
            "positioning_writer_id": "orchestrator",
        },
    )
    for index, experience in enumerate(state["experiences"]):
        eid = experience["experience_id"]
        context = generation.writer_context(store, state["id"], eid)
        source_id = experience["source_ids"][0]
        if missing_global_support is True and source_id in groups[1]["source_ids"]:
            source_id = experience["source_ids"][-1]
        read_options = {}
        if source_id in groups[1]["source_ids"]:
            if missing_global_support == "boundaries":
                read_options = {"field": "boundaries"}
            elif missing_global_support == "empty":
                full = generation.read_source(store, state["id"], eid, source_id)
                read_options = {"offset": full["total"]}
        source = generation.read_source(store, state["id"], eid, source_id, **read_options)
        receipt = {key: source[key] for key in ("source_id", "offset", "end", "source_revision")}
        if "field" in source:
            receipt["field"] = source["field"]
        fragment_groups = deepcopy(context["groups"])
        notes = [
            {
                "source_id": source["source_id"],
                "reason": "Supports the bounded contribution",
                "read": receipt,
            }
        ]
        if missing_global_support is True:
            for group in fragment_groups:
                group["source_ids"] = [source_id]
        generation.submit_fragment(
            store,
            state["id"],
            eid,
            input_revision=context["input_revision"],
            groups=fragment_groups,
            source_notes=notes,
            issues=[],
            writer_id=f"writer-{index}",
        )
    if missing_global_support:
        with pytest.raises(PortalDataError, match="全局定位引用"):
            generation.assemble_generation(store, state["id"])
        return
    candidate = generation.assemble_generation(store, state["id"])
    assert new_summary in candidate["latex_source"]
    assert old_summary not in candidate["latex_source"]
    assert "Synthetic Person\n" in candidate["latex_source"]
    assert main.read_text() == original
    with pytest.raises(PortalDataError, match="终审者须独立"):
        generation.review_generation(
            store,
            state["id"],
            candidate_sha256=candidate["candidate_sha256"],
            reviewer_id="orchestrator",
            passed=True,
            issues=[],
            business_alignment="The main writer should not approve its own global prose.",
        )
    generation.review_generation(
        store,
        state["id"],
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="independent-reviewer",
        passed=True,
        issues=[],
        business_alignment="The global profile now describes the cited financial research; "
        "the fixed identity is unchanged.",
    )
    adopted = generation.adopt_generation(store, state["id"])
    assert new_summary in adopted["latex_source"]
    assert "AI researcher" not in adopted["latex_source"]


@pytest.mark.parametrize("macro_header", [False, True, "comment", "inline", "heading"])
def test_positioning_cannot_reclassify_fixed_identity_as_experience_prose(full_latex, macro_header):
    from test_application_experience_latex import prepare

    store, _, _, analysis, _, project, output, _ = full_latex
    analysis["role_understanding"] = {
        "business_objective": "Research investment strategies.",
        "work_outputs": ["Investment research"],
        "methods_role": "Programming supports the research.",
    }
    if macro_header:
        main = project / "main.tex"
        main.write_text(
            main.read_text()
            .replace(
                "\\begin{document}", "\\newcommand{\\fullname}{Synthetic Person}\n\\begin{document}"
            )
            .replace("Synthetic Person\n", "\\fullname\n")
        )
    if macro_header == "comment":
        main.write_text(
            main.read_text().replace("\\fullname\n", "% \\section*{Comment}\n\\fullname\n")
        )
    elif macro_header == "inline":
        main.write_text(
            main.read_text().replace("\\fullname\n", "\\fullname\\par\\section*{Profile}\n")
        )
    if macro_header == "heading":
        main.write_text(main.read_text().replace("\\fullname\n", "\\section*{\\fullname}\n"))
    state = prepare(full_latex)
    original = (project / "main.tex").read_text()
    groups = deepcopy(output["groups"])
    if macro_header == "comment":
        groups[0]["end_line"] += 1
        for group in groups[1:]:
            group["start_line"] += 1
            group["end_line"] += 1
    groups[0].update(source_ids=groups[1]["source_ids"], latex="Different Person\n")
    experiences = [
        {
            "experience_id": f"experience-{index}",
            "source_ids": group["source_ids"],
            "group_indexes": [index],
            "business_relevance": "Research contribution.",
            "evidence_role": "transferable",
            "focus": "Supported work only.",
        }
        for index, group in enumerate(groups)
        if index
    ]
    with pytest.raises(PortalDataError, match="固定身份"):
        generation.configure_generation(
            store,
            state["id"],
            groups=groups,
            experiences=experiences,
            organization_plan={
                "summary_focus": "Investment research.",
                "ordering_rationale": "Direct evidence.",
                "positioning_group_indexes": [0],
                "positioning_writer_id": "orchestrator",
            },
        )
    assert (project / "main.tex").read_text() == original
