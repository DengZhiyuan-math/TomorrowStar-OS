"""Synthetic whole-letter writing and same-body delivery; no real author or compiler."""

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_cover_letter import (
    BEGIN_BODY,
    END_BODY,
    REVIEW_INSTRUCTIONS,
    ROLE_TITLE_SLOT,
    bind_letter_template,
    edit_cover_letter,
    export_cover_letter_pdf,
    generate_cover_letter,
    read_template,
    reconcile_letter_tex,
    render_cover_letter,
    validate_letter,
)
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.codex_cli import run_codex_exec
from career_evidence_graph.validation.hashing import record_digest as digest

TEMPLATE = (
    "\\documentclass[11pt]{article}\n\\begin{document}\n"
    "\\begin{center}\nSynthetic Person\n\\end{center}\n\n"
    "% Fixed greeting\nDear hiring team,\n\n"
    + BEGIN_BODY
    + "\n"
    + END_BODY
    + "\n\n\\nopagebreak[4]\nSincerely,\\\\\nSynthetic Person\n\\end{document}\n"
)


def inputs():
    app = {
        "id": "a" * 32,
        "company": "Synthetic",
        "role_title": "Engineer",
        "job_description": "Build Python services.",
    }
    fixed = {
        "analysis": {
            "id": "b" * 32,
            "jd_revision": "job-r1",
            "job_brief": {"role": "service reliability"},
            "material_packet": {"complete": True},
            "inference_result": {},
        },
        "handoff": None,
    }
    sources = {
        "items": [
            {
                "source_id": "fact-1",
                "text": "Built Python services with the team.",
                "resume_eligible": True,
                "attribution": "User",
            }
        ]
    }
    return app, fixed, sources


def output():
    return {
        "language": "en",
        "paragraphs": [
            {
                "id": "motivation",
                "kind": "motivation",
                "text": "I would like to contribute to reliable services.",
                "source_ids": [],
                "source_quotes": [],
            },
            {
                "id": "experience",
                "kind": "fact",
                "text": "Built Python services with the team.",
                "source_ids": ["fact-1"],
                "source_quotes": ["Built Python services with the team."],
            },
        ],
    }


def phase(prompt):
    """The letter call's role, read from its instructions (calls share one schema name)."""
    return "review-schema.json" if prompt.startswith(REVIEW_INSTRUCTIONS) else "schema.json"


def native(config, prompt, value):
    def process(argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, "synthetic-cli 1.0", "")
        event = {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": json.dumps(value)},
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(event) + "\n", "")

    return run_codex_exec(config, prompt, runner=process, environment={})


def result(value):
    return SimpleNamespace(
        structured_result=value, model_dump=lambda **_: {"structured_result": value}
    )


def writer(calls):
    def run(config, prompt, **_):
        calls.append((phase(prompt), prompt))
        return result(
            {"supported": True, "reason": "Supported expression."}
            if phase(prompt) == "review-schema.json"
            else output()
        )

    return run


def ready(tmp_path):
    return generate_cover_letter(
        tmp_path / "author", *inputs()[:2], sources=inputs()[2], runner=writer([])
    )


def test_generation_consumes_fixed_delivery_and_saves_body_without_pdf(tmp_path):
    calls = []
    app, fixed, sources = inputs()
    material = generate_cover_letter(
        tmp_path / "author", app, fixed, sources=sources, runner=writer(calls)
    )
    assert len(calls) == 2
    assert all(
        "service reliability" in prompt and "Built Python services" in prompt for _, prompt in calls
    )
    assert all("Do not retrieve" in prompt for _, prompt in calls)
    assert material["content"]["application_id"] == app["id"]
    assert "Dear" not in material["text"]
    assert material["content_revision"] == material["content"]["revision"]
    assert list((tmp_path / "author").glob("*.pdf")) == []
    repeated = generate_cover_letter(
        tmp_path / "author", app, fixed, sources=sources, runner=lambda *_: pytest.fail("No replay")
    )
    assert repeated == material


def test_successfully_delivered_source_scope_is_validated_before_review(tmp_path):
    app, fixed, sources = inputs()
    calls = []

    def foreign(config, prompt, **_):
        calls.append(True)
        value = output()
        value["paragraphs"][1]["source_ids"] = ["foreign-source"]
        return result(value)

    with pytest.raises(PortalDataError) as caught:
        generate_cover_letter(tmp_path / "bad", app, fixed, sources=sources, runner=foreign)
    assert caught.value.code == "letter_generation_failed"
    assert len(calls) == 1
    assert json.loads((tmp_path / "bad/failure.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("lost_stage", ["schema.json", "review-schema.json"])
def test_a_letter_call_without_answer_is_resent_alone(tmp_path, lost_stage):
    """Model Call Record: a retry resends only the call that produced no answer."""
    app, fixed, sources = inputs()
    calls = []

    def answer(config, prompt, **kwargs):
        calls.append(phase(prompt))
        if phase(prompt) == lost_stage and calls.count(lost_stage) == 1:
            raise TimeoutError("Synthetic call without answer")
        review = {"supported": True, "reason": "Supported expression."}
        return native(config, prompt, review if phase(prompt) == "review-schema.json" else output())

    with pytest.raises(PortalDataError) as caught:
        generate_cover_letter(tmp_path / "first", app, fixed, sources=sources, runner=answer)
    assert caught.value.code == "letter_generation_no_answer"
    assert json.loads((tmp_path / "first/failure.json").read_text())["status"] == "failed"
    assert (tmp_path / "first/draft.json").exists() == (lost_stage == "review-schema.json")
    # The attempt itself is never run twice; Flow retries in a successor attempt.
    with pytest.raises(PortalDataError, match="不能重放"):
        generate_cover_letter(
            tmp_path / "first",
            app,
            fixed,
            sources=sources,
            runner=lambda *_: pytest.fail("No replay"),
        )
    before = list(calls)
    letter = generate_cover_letter(
        tmp_path / "second",
        app,
        fixed,
        sources=sources,
        runner=answer,
        resume_from_directory=tmp_path / "first",
    )
    assert letter["status"] == "ready"
    resent = calls[len(before) :]
    assert resent[0] == lost_stage
    assert resent == (
        ["schema.json", "review-schema.json"] if lost_stage == "schema.json" else [lost_stage]
    )


def test_failed_review_preserves_body_and_has_known_failure(tmp_path):
    app, fixed, sources = inputs()

    def rejected(config, prompt, **kwargs):
        return (
            result({"supported": False, "reason": "Revise motivation only."})
            if phase(prompt) == "review-schema.json"
            else writer([])(config, prompt, **kwargs)
        )

    with pytest.raises(PortalDataError) as caught:
        generate_cover_letter(tmp_path / "rejected", app, fixed, sources=sources, runner=rejected)
    assert caught.value.code == "letter_generation_failed"
    assert (tmp_path / "rejected/draft.json").exists()
    assert not (tmp_path / "rejected/material.json").exists()


def test_render_preserves_fixed_template_bytes_and_same_semantic_body(tmp_path):
    content = ready(tmp_path)["content"]
    content = edit_cover_letter(
        content,
        "Used C++ & Python at 50% capacity: a_b #1 $x {y} ~ ^ \\ path.",
        expected_revision=content["revision"],
    )
    rendered = render_cover_letter(content, TEMPLATE)
    prefix, suffix = (
        TEMPLATE.split(BEGIN_BODY + "\n")[0] + BEGIN_BODY + "\n",
        END_BODY + "\n" + TEMPLATE.split(END_BODY + "\n")[1],
    )
    assert rendered["tex"].startswith(prefix) and rendered["tex"].endswith(suffix)
    assert rendered["text"].startswith("Dear hiring team,\n\n")
    assert rendered["text"].endswith("\n\nSincerely,\nSynthetic Person")
    assert "Synthetic Person" not in rendered["text"].split("\n\n")[0]
    assert "\\&" in rendered["tex"] and "\\%" in rendered["tex"]
    assert "\\" not in rendered["text"].replace("\\ path", "path")
    recovered = reconcile_letter_tex(content, TEMPLATE, rendered["tex"])
    assert recovered["status"] == "ready" and recovered["content"] == content


def test_fixed_introduction_and_thanks_are_shared_by_text_and_tex(tmp_path):
    content = ready(tmp_path)["content"]
    before = deepcopy(content)
    introduction = "My name is Synthetic Person, and I am applying for this position."
    thanks = "Thank you for your time and consideration."
    template = TEMPLATE.replace(
        "% Fixed greeting\nDear hiring team,\n\n",
        "% BEGIN LETTER OPENING\nDear hiring team,\n\n"
        + introduction
        + "\n% END LETTER OPENING\n\n",
    ).replace(END_BODY + "\n", END_BODY + "\n\n" + thanks + "\n")
    rendered = render_cover_letter(content, template)
    body = "\n\n".join(row["text"] for row in content["paragraphs"])
    assert rendered["text"] == (
        "Dear hiring team,\n\n"
        + introduction
        + "\n\n"
        + body
        + "\n\n"
        + thanks
        + "\n\nSincerely,\nSynthetic Person"
    )
    for fixed in (introduction, thanks):
        assert rendered["text"].count(fixed) == rendered["tex"].count(fixed) == 1
        assert all(fixed not in row["text"] for row in content["paragraphs"])
    prefix, _, suffix = template.partition(BEGIN_BODY + "\n")
    suffix = END_BODY + suffix.split(END_BODY, 1)[1]
    assert rendered["tex"].startswith(prefix + BEGIN_BODY + "\n")
    assert rendered["tex"].endswith(suffix)
    assert content == before
    for fixed in (introduction, thanks):
        modified = rendered["tex"].replace(fixed, "Changed fixed prose.")
        retained = reconcile_letter_tex(content, template, modified)
        assert retained["status"] == "needs_input" and retained["tex"] == modified


@pytest.mark.parametrize("damage", ["missing_end", "duplicate", "empty"])
def test_fixed_opening_markers_do_not_silently_drop_greeting_or_intro(tmp_path, damage):
    opening = "% BEGIN LETTER OPENING\nDear hiring team,\n\nI am Synthetic Person.\n"
    if damage == "duplicate":
        opening += "% BEGIN LETTER OPENING\n"
    elif damage == "empty":
        opening = "% BEGIN LETTER OPENING\n"
    if damage != "missing_end":
        opening += "% END LETTER OPENING\n\n"
    template = TEMPLATE.replace("% Fixed greeting\nDear hiring team,\n\n", opening)
    with pytest.raises(ValueError):
        render_cover_letter(ready(tmp_path)["content"], template)
    configured = tmp_path / "private-template.tex"
    configured.write_text(template)
    with pytest.raises(PortalDataError) as error:
        read_template(configured)
    assert error.value.code == "letter_template_invalid"


@pytest.mark.parametrize(
    "title",
    [
        "Quantitative Researcher",
        "Research & C++_Tools (100%)",
        # 2026-11-11: a raw en dash in the opening failed the PDF's missing-glyph guard.
        "Quantitative Researcher \u2013 Postgraduate",
    ],
)
def test_program_fills_fixed_opening_from_exact_application_role(tmp_path, title):
    from career_evidence_graph.application_materials import application_binding

    application, _, _ = inputs()
    application["role_title"] = title
    content = ready(tmp_path)["content"]
    content["job_revision"] = digest(application_binding(application))
    content["revision"] = digest({k: v for k, v in content.items() if k != "revision"})
    template = TEMPLATE.replace(
        "% Fixed greeting\nDear hiring team,\n\n",
        "% BEGIN LETTER OPENING\nDear hiring team,\n\n"
        "I am writing to apply for " + ROLE_TITLE_SLOT + ".\n% END LETTER OPENING\n\n",
    )
    rendered = render_cover_letter(content, template, application=application)
    assert rendered["text"].startswith(
        "Dear hiring team,\n\nI am writing to apply for " + title + ".\n\n"
    )
    assert ROLE_TITLE_SLOT not in rendered["tex"]
    if "&" in title:
        assert r"Research \& C++\_Tools (100\%)" in rendered["tex"]
    if "\u2013" in title:
        assert "Quantitative Researcher -- Postgraduate" in rendered["tex"]
        assert "\u2013" not in rendered["tex"]
        bound = bind_letter_template(template, application)
        assert reconcile_letter_tex(content, bound, rendered["tex"])["status"] == "ready"
    assert rendered == render_cover_letter(content, bind_letter_template(template, application))
    wrong_job = {**application, "role_title": "Other role"}
    with pytest.raises(ValueError):
        render_cover_letter(content, template, application=wrong_job)
    path = tmp_path / "private-template.tex"
    path.write_text(template)
    assert read_template(path) == template
    with pytest.raises(PortalDataError) as missing:
        render_cover_letter(content, template)
    assert missing.value.code == "letter_role_required"


@pytest.mark.parametrize("title", [None, "", "  ", "Engineer\nOther role"])
def test_missing_or_multiline_role_never_uses_a_default_title(title):
    template = (
        "% BEGIN LETTER OPENING\nApply for "
        + ROLE_TITLE_SLOT
        + ".\n% END LETTER OPENING\n"
        + BEGIN_BODY
        + "\n"
        + END_BODY
        + "\nSincerely,\nApplicant\n"
    )
    with pytest.raises(PortalDataError) as error:
        bind_letter_template(template, {"role_title": title})
    assert error.value.code == "letter_role_required"


def test_uniquely_mapped_tex_edit_protects_body_and_retains_other_regions(tmp_path):
    content = ready(tmp_path)["content"]
    original = render_cover_letter(content, TEMPLATE)
    edited = original["tex"].replace("Built Python services", "Maintained Python services")
    mapped = reconcile_letter_tex(content, TEMPLATE, edited)
    assert mapped["status"] == "ready"
    assert mapped["content"]["paragraphs"][1]["protected"] is True
    assert mapped["content"]["revision"] != content["revision"]
    for unsupported in [
        original["tex"].replace("Dear hiring team", "Hello team"),
        original["tex"].replace("Built Python", "\\textbf{Built} Python"),
    ]:
        retained = reconcile_letter_tex(content, TEMPLATE, unsupported)
        assert retained["status"] == "needs_input" and retained["tex"] == unsupported
        assert retained["diff"]


def test_template_configuration_is_explicit_private_and_not_bundled(tmp_path, monkeypatch):
    monkeypatch.delenv("TOMORROWSTAR_COVER_LETTER_TEMPLATE", raising=False)
    with pytest.raises(PortalDataError) as caught:
        read_template()
    assert caught.value.code == "letter_template_required"
    template = tmp_path / "private.tex"
    template.write_text(TEMPLATE)
    monkeypatch.setenv("TOMORROWSTAR_COVER_LETTER_TEMPLATE", str(template))
    assert read_template() == TEMPLATE
    for malformed in [TEMPLATE.replace(END_BODY, ""), TEMPLATE + BEGIN_BODY + "\n"]:
        with pytest.raises(ValueError):
            render_cover_letter(ready(tmp_path / str(len(malformed)))["content"], malformed)


class Compiler:
    def __init__(self, *, unknown=False):
        self.calls = 0
        self.unknown = unknown

    def compile(self, binding):
        self.calls += 1
        if self.unknown:
            raise TimeoutError("Synthetic lost build response")
        return {
            "pdf": (
                Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
            ).read_bytes(),
            "source_revision": binding["source_revision"],
            "build": {"exit": 0},
        }


def test_pdf_is_lazily_built_via_existing_prism_and_reuses_completed_result(tmp_path):
    content = ready(tmp_path)["content"]
    compiler = Compiler()
    exported = export_cover_letter_pdf(
        tmp_path / "pdf", content, TEMPLATE, client=compiler, pdf_inspector=lambda _: 1
    )
    assert compiler.calls == 1 and exported["page_count"] == 1
    assert exported["content_revision"] == content["revision"]
    assert (
        hashlib.sha256(Path(exported["file_path"]).read_bytes()).hexdigest() == exported["sha256"]
    )
    assert (
        export_cover_letter_pdf(
            tmp_path / "pdf", content, TEMPLATE, client=compiler, pdf_inspector=lambda _: 1
        )
        == exported
    )
    assert compiler.calls == 1


def test_unknown_build_keeps_body_and_a_longer_letter_is_delivered(tmp_path):
    content = ready(tmp_path)["content"]
    compiler = Compiler(unknown=True)
    for _ in range(2):
        with pytest.raises(PortalDataError) as caught:
            export_cover_letter_pdf(tmp_path / "unknown-pdf", content, TEMPLATE, client=compiler)
        assert caught.value.code == "letter_export_needs_recheck"
    assert compiler.calls == 1
    # 2026-11-10 (Harmattan AI): one page is only the writing target, never a stop.
    two_pages = export_cover_letter_pdf(
        tmp_path / "overflow", content, TEMPLATE, client=Compiler(), pdf_inspector=lambda _: 2
    )
    assert two_pages["page_count"] == 2
    assert (tmp_path / "overflow/letter.pdf").exists()
    assert validate_letter(content)["revision"] == content["revision"]
    assert (tmp_path / "overflow/project/main.tex").read_text().startswith("\\documentclass[11pt]")


def test_wrong_job_or_stale_content_cannot_be_reused(tmp_path):
    material = ready(tmp_path)
    app, _, sources = inputs()
    app["job_description"] = "Different job"
    with pytest.raises(ValueError, match="another application or JD"):
        validate_letter(material["content"], sources=sources, application=app)
    corrupted = deepcopy(material["content"])
    corrupted["paragraphs"][0]["text"] = "Changed without version"
    with pytest.raises(ValueError, match="revision"):
        validate_letter(corrupted)
    changed = deepcopy(material["content"])
    changed["paragraphs"][0]["protected"] = True
    changed["revision"] = digest(
        {key: value for key, value in changed.items() if key != "revision"}
    )
    with pytest.raises(ValueError):
        validate_letter(changed)


def test_explicit_malformed_review_retry_reuses_original_body_and_never_writer(tmp_path):
    app, fixed, sources = inputs()
    original = tmp_path / "rejected-review"

    def reject(config, prompt, **kwargs):
        if phase(prompt) == "review-schema.json":
            return native(config, prompt, {"supported": True, "reason": 123})
        return native(config, prompt, output())

    with pytest.raises(PortalDataError):
        generate_cover_letter(original, app, fixed, sources=sources, runner=reject)
    before = {path.name: path.read_bytes() for path in original.iterdir()}
    calls = []

    def only_review(config, prompt, **_):
        calls.append(phase(prompt))
        assert phase(prompt) == "review-schema.json"
        return native(config, prompt, {"supported": True, "reason": "Checked saved expression."})

    resumed = generate_cover_letter(
        tmp_path / "review-successor",
        app,
        fixed,
        sources=sources,
        runner=only_review,
        resume_from_directory=original,
    )
    assert calls == ["review-schema.json"]
    assert resumed["content"] == json.loads((original / "draft.json").read_text())
    assert before == {path.name: path.read_bytes() for path in original.iterdir()}


def test_prebuild_prism_capability_failure_is_known_and_keeps_body(tmp_path):
    content = ready(tmp_path)["content"]

    def unavailable(_):
        raise PortalDataError("prism_not_running", "Synthetic editor not served", 409)

    with pytest.raises(PortalDataError) as caught:
        export_cover_letter_pdf(
            tmp_path / "unserved", content, TEMPLATE, client=SimpleNamespace(compile=unavailable)
        )
    assert caught.value.code == "prism_not_running"
    assert json.loads((tmp_path / "unserved/export-failure.json").read_text())["status"] == "failed"
    assert validate_letter(content)["revision"] == content["revision"]


def test_human_edit_receipt_id_reconstructs_exact_same_protected_content(tmp_path):
    content = ready(tmp_path)["content"]
    arguments = {"expected_revision": content["revision"], "edit_id": "c" * 32}
    first = edit_cover_letter(content, "Explicit human body.", **arguments)
    assert edit_cover_letter(content, "Explicit human body.", **arguments) == first
    assert first["paragraphs"][0]["id"] == "human-" + "c" * 32


def test_explicit_known_invalid_writer_retry_runs_only_failed_material_again(tmp_path):
    app, fixed, sources = inputs()
    original = tmp_path / "invalid-writer"
    with pytest.raises(PortalDataError) as caught:
        generate_cover_letter(
            original,
            app,
            fixed,
            sources=sources,
            runner=lambda *_args, **_kwargs: result({"invalid": True}),
        )
    assert caught.value.code == "letter_generation_failed"
    calls = []
    saved = generate_cover_letter(
        tmp_path / "writer-successor",
        app,
        fixed,
        sources=sources,
        runner=writer(calls),
        resume_from_directory=original,
    )
    assert saved["status"] == "ready"
    assert [name for name, _ in calls] == ["schema.json", "review-schema.json"]
    assert json.loads((original / "failure.json").read_text())["status"] == "failed"


def test_render_does_not_silently_replace_an_existing_letter_as_a_template(tmp_path):
    content = ready(tmp_path)["content"]
    filled = TEMPLATE.replace(BEGIN_BODY + "\n", BEGIN_BODY + "\nExisting human body.\n")
    with pytest.raises(ValueError, match="existing body"):
        render_cover_letter(content, filled)


def test_completed_material_reuse_checks_text_against_its_body_revision(tmp_path):
    app, fixed, sources = inputs()
    material = ready(tmp_path)
    material["text"] = "A corrupt saved replacement."
    material["text_sha256"] = hashlib.sha256(material["text"].encode()).hexdigest()
    (tmp_path / "author/material.json").write_text(json.dumps(material))
    with pytest.raises(PortalDataError) as caught:
        generate_cover_letter(
            tmp_path / "author",
            app,
            fixed,
            sources=sources,
            runner=lambda *_args, **_kwargs: pytest.fail("No model replay"),
        )
    assert caught.value.code == "letter_generation_needs_recheck"


def test_semantic_rejection_retry_supplies_local_feedback_and_rewrites_only_letter(tmp_path):
    app, fixed, sources = inputs()
    original = tmp_path / "semantic-rejection"

    def reject(config, prompt, **kwargs):
        if phase(prompt) == "review-schema.json":
            return result({"supported": False, "reason": "Make prospective motivation concrete."})
        return writer([])(config, prompt, **kwargs)

    with pytest.raises(PortalDataError):
        generate_cover_letter(original, app, fixed, sources=sources, runner=reject)
    original_bytes = {path.name: path.read_bytes() for path in original.iterdir()}
    calls = []

    def revise(config, prompt, **kwargs):
        calls.append(phase(prompt))
        if phase(prompt) == "schema.json":
            assert '"local_rewrite"' in prompt
            assert "Make prospective motivation concrete." in prompt
            revised = output()
            revised["paragraphs"][0]["text"] = "I would like to work on reliable Python services."
            return result(revised)
        return writer([])(config, prompt, **kwargs)

    saved = generate_cover_letter(
        tmp_path / "local-rewrite",
        app,
        fixed,
        sources=sources,
        runner=revise,
        resume_from_directory=original,
    )
    assert calls == ["schema.json", "review-schema.json"]
    assert saved["content"]["paragraphs"][1]["text"] == output()["paragraphs"][1]["text"]
    assert original_bytes == {path.name: path.read_bytes() for path in original.iterdir()}


def test_semantic_reviewer_can_apply_located_wording_patch_without_new_writer(tmp_path):
    app, fixed, sources = inputs()
    calls = []

    def patch(config, prompt, **kwargs):
        calls.append(phase(prompt))
        if phase(prompt) == "review-schema.json":
            return result(
                {
                    "supported": True,
                    "reason": "More specific motivation.",
                    "patches": [
                        {
                            "paragraph_id": "motivation",
                            "text": "I would like to build reliable Python services.",
                        }
                    ],
                }
            )
        return writer([])(config, prompt, **kwargs)

    saved = generate_cover_letter(tmp_path / "patched", app, fixed, sources=sources, runner=patch)
    assert calls == ["schema.json", "review-schema.json"]
    assert (
        saved["content"]["paragraphs"][0]["text"]
        == "I would like to build reliable Python services."
    )
    assert (
        json.loads((tmp_path / "patched/draft.json").read_text())["revision"]
        != saved["content_revision"]
    )
    assert saved["source_binding"]["sources"] == sources["items"]


def test_letter_review_captures_exact_ready_resume_revision_without_waiting(tmp_path):
    from test_json_resume_content import assignment, fragment

    from career_evidence_graph.application_resume_content import assemble_content

    app, fixed, sources = inputs()
    resume = assemble_content(
        {
            "schema_version": "resume-plan/v1",
            "application_id": app["id"],
            "profile": {"name": "Synthetic Applicant", "contacts": []},
            "education": [],
            "assignments": [assignment()],
        },
        [fragment()],
    )
    calls = []

    def checked(config, prompt, **kwargs):
        if phase(prompt) == "review-schema.json":
            assert '"sibling_resume_content"' in prompt and resume["revision"] in prompt
        return writer(calls)(config, prompt, **kwargs)

    material = generate_cover_letter(
        tmp_path / "sibling",
        app,
        fixed,
        sources=sources,
        runner=checked,
        sibling_content_provider=lambda: resume,
    )
    assert material["review_binding"]["sibling_resume_revision"] == resume["revision"]
    assert len(calls) == 2


def test_unknown_material_publication_is_not_a_known_optional_expression_failure(
    tmp_path, monkeypatch
):
    import career_evidence_graph.application_cover_letter as module

    app, fixed, sources = inputs()
    atomic = module.helper.atomic_write_json

    def fail_publication(path, value):
        if path.name == "material.json":
            raise OSError("Synthetic unknown atomic publication")
        return atomic(path, value)

    monkeypatch.setattr(module.helper, "atomic_write_json", fail_publication)
    with pytest.raises(PortalDataError) as caught:
        generate_cover_letter(tmp_path / "publish", app, fixed, sources=sources, runner=writer([]))
    assert caught.value.code == "letter_generation_needs_recheck"
    failure = json.loads((tmp_path / "publish/failure.json").read_text())
    assert failure["status"] == "needs_recheck" and failure["stage"] == "publication"
    assert (tmp_path / "publish/review.json").exists()


@pytest.mark.parametrize("changed", ["sources", "grounding", "raw_review", "intent", "content"])
def test_pure_result_reader_checks_exact_sources_review_intent_and_body(tmp_path, changed):
    from career_evidence_graph.application_cover_letter import read_cover_letter_result

    app, fixed, sources = inputs()
    material = ready(tmp_path)
    path = tmp_path / "author/material.json"
    if changed == "sources":
        material["source_binding"]["sources"][0]["text"] = "Changed source text."
    elif changed == "grounding":
        material["grounding"] = {"supported": True, "reason": "Forged alternative approval"}
    elif changed == "raw_review":
        path = tmp_path / "author/review.json"
        material = json.loads(path.read_text())
        material["structured_result"]["supported"] = False
    elif changed == "intent":
        path = tmp_path / "author/intent.json"
        material = json.loads(path.read_text())
        material["sources_revision"] = "another-source-snapshot"
    else:
        material["content"]["paragraphs"][0]["text"] = "A changed unreviewed expression."
        material["content"]["revision"] = digest(
            {key: value for key, value in material["content"].items() if key != "revision"}
        )
    path.write_text(json.dumps(material))
    before = {file.name: file.read_bytes() for file in (tmp_path / "author").iterdir()}
    with pytest.raises(PortalDataError) as caught:
        read_cover_letter_result(tmp_path / "author", app, fixed, sources=sources)
    assert caught.value.code == "letter_generation_needs_recheck"
    assert before == {file.name: file.read_bytes() for file in (tmp_path / "author").iterdir()}


def test_pure_result_reader_reconciles_complete_raw_evidence_after_publication_loss(tmp_path):
    from career_evidence_graph.application_cover_letter import read_cover_letter_result

    app, fixed, sources = inputs()
    material = ready(tmp_path)
    (tmp_path / "author/material.json").unlink()
    before = {file.name: file.read_bytes() for file in (tmp_path / "author").iterdir()}
    assert read_cover_letter_result(tmp_path / "author", app, fixed, sources=sources) == material
    assert before == {file.name: file.read_bytes() for file in (tmp_path / "author").iterdir()}


def test_body_symbols_use_the_resume_tex_mapping_and_keep_other_characters(tmp_path):
    """2026-11-03: a body with π₀ and ₅ failed tectonic's missing-glyph guard."""
    content = ready(tmp_path)["content"]
    content = edit_cover_letter(
        content,
        "Trained π₀ policies, cut CO₂ by x² — 50% → 10% for 中.",
        expected_revision=content["revision"],
    )
    rendered = render_cover_letter(content, TEMPLATE)
    body = rendered["tex"].split(BEGIN_BODY + "\n")[1]
    assert rendered["renderer_revision"] == "cover-letter-renderer/v5"
    assert "\\ensuremath{\\pi}\\textsubscript{0}" in body
    assert "CO\\textsubscript{2}" in body and "x\\textsuperscript{2}" in body
    assert " --- 50\\% \\ensuremath{\\rightarrow} 10\\%" in body
    assert not set("π₀₂²—→") & set(rendered["tex"])
    assert "中" in body
    assert "π₀ policies" in rendered["text"] and "—" in rendered["text"]
    recovered = reconcile_letter_tex(content, TEMPLATE, rendered["tex"])
    assert recovered["status"] == "ready" and recovered["content"] == content
    legacy = render_cover_letter(content, TEMPLATE, renderer="cover-letter-renderer/v3")
    assert "π₀" in legacy["tex"] and legacy["renderer_revision"] == "cover-letter-renderer/v3"
    assert reconcile_letter_tex(content, TEMPLATE, legacy["tex"])["content"] == content


def test_letter_v5_maps_latin_one_signs_and_v4_keeps_its_own_table(tmp_path):
    """2026-11-12: "·" printed as "ů" in the 8-bit font without any warning."""
    content = ready(tmp_path)["content"]
    content = edit_cover_letter(
        content, "Research · modelling — 20 °C.", expected_revision=content["revision"]
    )
    rendered = render_cover_letter(content, TEMPLATE)
    body = rendered["tex"].split(BEGIN_BODY + "\n")[1]
    assert rendered["renderer_revision"] == "cover-letter-renderer/v5"
    assert r"Research \textperiodcentered{} modelling --- 20 \textdegree{}C." in body
    assert "Research · modelling — 20 °C." in rendered["text"]
    v4 = render_cover_letter(content, TEMPLATE, renderer="cover-letter-renderer/v4")
    assert "Research · modelling --- 20 °C." in v4["tex"]
