"""Reconcile exact supported human TeX edits without changing fixed template data."""

from copy import deepcopy

from test_json_resume_content import fragment
from test_json_resume_template_content import TEMPLATE, plan

from career_evidence_graph.application_content_reconcile import reconcile_content
from career_evidence_graph.application_resume_content import assemble_content, validate_content
from career_evidence_graph.application_resume_render import render_resume


def test_career_headline_human_edit_and_deletion_round_trip():
    from career_evidence_graph.application_resume_content import content_revision
    from career_evidence_graph.validation.hashing import record_digest

    template = TEMPLATE.replace(
        "%% TOMORROWSTAR_SUMMARY %%", "%% TOMORROWSTAR_HEADLINE %%\n%% TOMORROWSTAR_SUMMARY %%"
    )
    planned = plan()
    planned.update(
        template_revision=record_digest(template),
        headline={
            "id": "career-headline",
            "text": "Quantitative Research",
            "fact_refs": ["fact-demo-1"],
        },
    )
    parent = assemble_content(planned, [fragment()])
    baseline = render_resume(parent, template=template)
    edited = baseline.tex.replace("Quantitative Research\\par", "Data Science \\& Research\\par")
    result = reconcile_content(parent, template, edited, "prism:headline")
    assert result["status"] == "mapped"
    headline = result["content"]["headline"]
    assert headline["text"] == "Data Science & Research"
    assert headline["origin"] == "human" and headline["protected"]
    assert headline["id"] == "career-headline"
    assert render_resume(result["content"], template=template).tex == edited
    first, last = baseline.ranges["career-headline"]
    deleted = baseline.tex[:first] + baseline.tex[last:]
    result = reconcile_content(parent, template, deleted, "prism:delete-headline")
    assert result["status"] == "mapped"
    assert "headline" not in result["content"]
    assert result["content"]["revision"] == content_revision(result["content"])


def test_human_item_replacement_round_trips_and_preserves_parent_and_template():
    parent = assemble_content(plan(), [fragment()])
    before = deepcopy(parent)
    edited = render_resume(parent, template=TEMPLATE).tex.replace(
        "Participated in planning a validation workflow.", r"Designed validation \& safety checks."
    )
    result = reconcile_content(parent, TEMPLATE, edited, "prism:commit-demo")
    assert result["status"] == "mapped"
    child = result["content"]
    item = child["experiences"][0]["items"][0]
    assert item["id"] == "item-demo-1"
    assert item["text"] == "Designed validation & safety checks."
    assert (item["origin"], item["protected"], item["edit_source"]) == (
        "human",
        True,
        "prism:commit-demo",
    )
    assert render_resume(validate_content(child), template=TEMPLATE).tex == edited
    assert "profile" not in child and "education" not in child
    assert parent == before


def test_item_and_experience_deletion_and_order_keep_existing_ids():
    parent = assemble_content(plan(), [fragment()])
    first = parent["experiences"][0]
    second = deepcopy(first)
    second.update(id="experience-second", candidate_id="candidate-second", title="Other work")
    second["items"][0].update(id="second-item", text="Other evidenced work.")
    first["items"].append(
        {**deepcopy(first["items"][0]), "id": "delete-item", "text": "Delete this."}
    )
    parent["experiences"].append(second)
    from career_evidence_graph.application_resume_content import content_revision

    parent["revision"] = content_revision(parent)
    expected = deepcopy(parent)
    expected["experiences"] = [second, {**first, "items": first["items"][:1]}]
    expected["revision"] = content_revision(expected)
    edited = render_resume(expected, template=TEMPLATE).tex
    result = reconcile_content(parent, TEMPLATE, edited, "git:human-reorder")
    assert result["status"] == "mapped"
    assert [row["id"] for row in result["content"]["experiences"]] == [
        "experience-second",
        "experience-demo-1",
    ]
    assert result["content"]["experiences"][1]["items"][0]["id"] == "item-demo-1"
    expected["experiences"] = expected["experiences"][:1]
    expected["revision"] = content_revision(expected)
    deleted = reconcile_content(
        parent, TEMPLATE, render_resume(expected, template=TEMPLATE).tex, "git:delete"
    )
    assert deleted["status"] == "mapped"
    assert [row["id"] for row in deleted["content"]["experiences"]] == ["experience-second"]


def test_summary_and_skills_edits_use_exact_template_slots():
    from career_evidence_graph.application_resume_content import content_revision

    parent = assemble_content(plan(), [fragment()])
    item = parent["experiences"][0]["items"][0]
    parent["summary"] = [{**deepcopy(item), "id": "summary-one", "text": "Original summary."}]
    parent["skills"] = [{**deepcopy(item), "id": "skill-one", "text": "Original skill."}]
    parent["revision"] = content_revision(parent)
    edited = (
        render_resume(parent, template=TEMPLATE)
        .tex.replace("Original summary.", "Human summary.")
        .replace("Original skill.", "Human skill.")
    )
    result = reconcile_content(parent, TEMPLATE, edited, "prism:wording")
    assert result["status"] == "mapped"
    assert result["content"]["summary"][0]["text"] == "Human summary."
    assert result["content"]["skills"][0]["text"] == "Human skill."


def test_fixed_content_and_unsupported_layout_are_unmerged_with_exact_human_tex():
    parent = assemble_content(plan(), [fragment()])
    baseline = render_resume(parent, template=TEMPLATE).tex
    for edited in (
        baseline.replace("Fixed Applicant", "Changed Applicant"),
        baseline.replace("Recorded degree, in progress", "New degree"),
        baseline.replace(r"\item Participated", r"\item \textbf{Participated}"),
        baseline.replace(r"\begin{itemize}", r"\begin{enumerate}"),
        baseline.replace(r"\documentclass{article}", r"\documentclass[11pt]{article}"),
    ):
        result = reconcile_content(parent, TEMPLATE, edited, "git:unsupported-edit")
        assert result["status"] == "unmerged"
        assert result["edited_tex"] == edited
        assert result["diff"]
        assert "content" not in result


def test_human_addition_links_and_escaped_literals_need_no_invented_fact_refs():
    parent = assemble_content(plan(), [fragment()])
    baseline = render_resume(parent, template=TEMPLATE).tex
    edited = baseline.replace(
        "\\end{itemize}\n",
        "\\item Human \\& text "
        "\\href{https://example.invalid/work\\_sample}{Work \\& sample}\n\\end{itemize}\n",
    )
    result = reconcile_content(parent, TEMPLATE, edited, "prism:addition")
    assert result["status"] == "mapped"
    item = result["content"]["experiences"][0]["items"][1]
    assert item["text"] == "Human & text"
    assert item["links"] == [
        {"url": "https://example.invalid/work_sample", "label": "Work & sample"}
    ]
    assert item["origin"] == "human" and item["protected"] is True
    assert item["fact_refs"] == item["inference_refs"] == []
    assert render_resume(result["content"], template=TEMPLATE).tex == edited


def test_stored_renderer_and_range_bindings_must_match_before_adoption():
    from hashlib import sha256

    parent = assemble_content(plan(), [fragment()])
    baseline = render_resume(parent, template=TEMPLATE)
    manifest = {
        "schema_version": "resume-render-manifest/v1",
        "content_revision": baseline.content_revision,
        "template_revision": baseline.template_revision,
        "renderer_revision": baseline.renderer_revision,
        "tex_sha256": sha256(baseline.tex.encode()).hexdigest(),
        "item_ranges": {key: list(value) for key, value in baseline.ranges.items()},
    }
    edited = baseline.tex.replace("Participated in planning", "Contributed to planning")
    valid = reconcile_content(parent, TEMPLATE, edited, "git:checked", render_manifest=manifest)
    assert valid["status"] == "mapped"
    for field, corrupted in (
        ("content_revision", "another-parent"),
        ("template_revision", "another-template"),
        ("renderer_revision", "another-renderer"),
        ("tex_sha256", "another-source"),
        ("item_ranges", {"item-demo-1": [0, 1]}),
    ):
        invalid = reconcile_content(
            parent, TEMPLATE, edited, "git:checked", render_manifest={**manifest, field: corrupted}
        )
        assert invalid["status"] == "unmerged"
        assert "content" not in invalid
        assert invalid["edited_tex"] == edited


def test_historical_complete_json_does_not_silently_migrate_fixed_information():
    from test_json_resume_content import plan as historical_plan

    parent = assemble_content(historical_plan(), [fragment()])
    edited = render_resume(parent).tex.replace(
        "Participated in planning", "Contributed to planning"
    )
    result = reconcile_content(parent, None, edited, "git:historical")
    assert result["status"] == "unmerged"
    assert result["edited_tex"] == edited and result["diff"]
    assert "content" not in result


def test_all_renderer_literal_escapes_round_trip_and_raw_whitespace_edits_stay_manual():
    parent = assemble_content(plan(), [fragment()])
    baseline = render_resume(parent, template=TEMPLATE).tex
    original = "Participated in planning a validation workflow."
    edited = baseline.replace(
        original,
        r"Human \% \& \_ \# \$ \{x\} \textasciitilde{} \textasciicircum{} "
        r"\textbackslash{}\mbox{}\newline{}second line.",
    )
    result = reconcile_content(parent, TEMPLATE, edited, "git:literal")
    assert result["status"] == "mapped"
    assert result["content"]["experiences"][0]["items"][0]["text"] == (
        "Human % & _ # $ {x} ~ ^ \\\nsecond line."
    )
    unchanged = reconcile_content(parent, TEMPLATE, baseline, "git:no-change")
    assert unchanged["status"] == "unchanged"
    assert unchanged["content"]["revision"] == parent["revision"]
    whitespace = reconcile_content(
        parent, TEMPLATE, baseline.replace(original, original + " "), "git:spaces"
    )
    assert whitespace["status"] == "mapped"
    raw_newline = reconcile_content(
        parent, TEMPLATE, baseline.replace(original, "Human text\nnext line"), "git:raw-newline"
    )
    assert raw_newline["status"] == "unmerged"
    assert raw_newline["edited_tex"].endswith("\\end{document}\n")


def test_simultaneous_rewording_and_reordering_cannot_guess_item_identity():
    from career_evidence_graph.application_resume_content import content_revision

    parent = assemble_content(plan(), [fragment()])
    items = parent["experiences"][0]["items"]
    items[0].update(id="alpha", text="Built Alpha.")
    items.append({**deepcopy(items[0]), "id": "beta", "text": "Built Beta."})
    parent["revision"] = content_revision(parent)
    edited = render_resume(parent, template=TEMPLATE).tex.replace(
        "\\item Built Alpha.\n\\item Built Beta.\n",
        "\\item Operated Beta.\n\\item Operated Alpha.\n",
    )
    result = reconcile_content(parent, TEMPLATE, edited, "prism:ambiguous-items")
    assert result["status"] == "unmerged"
    assert "content" not in result
    assert result["edited_tex"] == edited
    assert result["diff"]
