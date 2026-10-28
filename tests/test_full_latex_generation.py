"""Independent complete LaTeX versions retain evidence and pending human gates."""

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_application_resume import task_resume as task_resume
from test_application_source_reuse import retained_capture as retained_capture

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_resume import career_source_snapshot


@pytest.fixture
def full_latex(task_resume, tmp_path):
    store, job, _, analysis, calls = task_resume
    for number in range(1, 7):
        (store.catalog.root / f"contributions/project-{number}.md").write_text(
            f"# Project {number}\n\n## Scope\n\n"
            f"Analyzed strategy and built {number} Python services.\n\n"
            "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
            "| Delivery | User |\n"
        )
    sources = career_source_snapshot(store.catalog)
    analysis["source_snapshot_revision"] = sources["revision"]
    project = tmp_path / "complete-base"
    project.mkdir()
    main = "\\documentclass[a4paper]{article}\n\\begin{document}\nSynthetic Person\n"
    for number in range(1, 7):
        main += (
            f"\\section*{{Project {number}}}\n"
            f"Analyzed strategy and built {number} Python services.\n"
        )
    main += "\\end{document}\n"
    (project / "main.tex").write_text(main)
    (project / "style-note.txt").write_text("Original ancillary source; keep unchanged")
    output = {"groups": [], "limitations": []}
    profile_id = sources["profile_source"]["id"] + ":profile.identity"
    output["groups"].append(
        {
            "title": "Identity",
            "start_line": 1,
            "end_line": 1,
            "source_ids": [profile_id],
            "latex": "Synthetic Person\n",
            "disposition": "include",
            "reason": "Existing identity",
        }
    )
    for number in range(1, 7):
        source = next(s for s in sources["items"] if s["title"] == f"Project {number}")
        output["groups"].append(
            {
                "title": f"Project {number}",
                "start_line": number * 2,
                "end_line": number * 2 + 1,
                "source_ids": [source["source_id"]],
                "latex": (
                    f"\\section*{{Project {number}}}\n"
                    f"Analyzed strategy; built {number} Python services.\n"
                ),
                "disposition": "include",
                "reason": "Emphasize evidenced strategy for this JD",
            }
        )

    def model(config, prompt, **kwargs):
        calls.append(json.loads(prompt[prompt.index("{") :]))
        return SimpleNamespace(
            structured_result=output, model_dump=lambda **kwargs: {"synthetic": True}
        )

    store.model_runner = model
    store.exporter = lambda *_: pytest.fail("Generation must not compile or export")
    inputs = {"sources_revision": sources["revision"], "policy": "v1.0"}
    return store, job, sources, analysis, calls, project, output, inputs


def generate(data, **kwargs):
    store, job, sources, analysis, _, project, _, inputs = data
    return store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        draft_only=True,
        task_inputs=inputs,
        latex_base=source_snapshot(project, "main.tex"),
        **kwargs,
    )


def test_full_version_keeps_more_than_four_experiences_and_leaves_base_untouched(full_latex):
    store, _, _, _, calls, project, _, _ = full_latex
    before = {p.name: p.read_bytes() for p in project.iterdir()}
    result = generate(full_latex)
    assert result["origin"] == "generated_latex"
    assert result["factual_review"] == "pending"
    assert result["kind"] == "draft"
    assert result["review_status"] == "review_required"
    assert len(result["review_groups"]) == 7
    assert "\\section*{Project 6}" in result["latex_source"]
    assert "Analyzed strategy; built 6 Python services." in result["latex_source"]
    assert result["latex_source"].startswith("\\documentclass[a4paper]{article}")
    assert result["latex_source"].endswith("\\end{document}\n")
    assert result["omitted_groups"] == result["verification_queue"] == []
    assert before == {p.name: p.read_bytes() for p in project.iterdir()}
    destination = store.root / result["id"] / "project"
    assert (destination / "main.tex").read_text() == result["latex_source"]
    assert (destination / "style-note.txt").read_bytes() == before["style-note.txt"]
    assert result["source_checkpoint"]["project_root"] == str(destination)
    assert result["base_checkpoint"]["project_root"] == str(project)
    assert not list(store.root.rglob("*.pdf"))
    assert len(calls) == 1
    assert (
        sum(
            event["kind"] == "stage_start" and event.get("stage") == "model"
            for event in store.measurements.read()
        )
        == 1
    )
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]
    raw = (store.root / result["id"] / "draft.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result["draft_sha256"]


def test_generation_in_private_git_workspace_keeps_review_pending(full_latex, tmp_path):
    store, _, _, _, calls, base, _, _ = full_latex
    private = tmp_path / "private-career"
    (private / ".git").mkdir(parents=True)
    (private / "unrelated-private.txt").write_text("Never archive sibling records")
    store.root = private / ".career-evidence/flow/resumes"
    store.root.mkdir(parents=True)
    before = {p.name: p.read_bytes() for p in base.iterdir()}
    result = generate(full_latex)
    assert result["origin"] == "generated_latex"
    assert result["review_status"] == "review_required"
    assert result["factual_review"] == "pending"
    assert result["source_checkpoint"]["source_policy"] == "generated-latex-project/v1"
    assert set(result["source_checkpoint"]["files"]) == {"main.tex", "style-note.txt"}
    assert before == {p.name: p.read_bytes() for p in base.iterdir()}
    assert store.draft(result["id"])["draft_sha256"] == result["draft_sha256"]
    assert len(calls) == 1
    assert not list(store.root.rglob("*.pdf"))


def test_unwritable_generation_project_stops_before_model(full_latex, monkeypatch):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, _, calls, _, _, _ = full_latex
    mkdir = Path.mkdir

    def deny_project(path, *args, **kwargs):
        if path.name == "project":
            raise PermissionError("Synthetic destination is not writable")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny_project)
    with pytest.raises(PortalDataError) as failure:
        generate(full_latex)
    assert failure.value.code == "resume_destination_invalid"
    assert calls == []
    receipts = list(store.root.glob("*/project-preflight.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text())
    assert receipt["status"] == "not_started"
    assert receipt["error_type"] == "PermissionError"
    assert not list(store.root.glob("*/model-result.json"))
    assert not list(store.root.glob("*/draft.json"))


@pytest.mark.parametrize("damage", ["ancillary", "main", "redirect"])
def test_generation_preflight_is_saved_before_model_and_target_drift_is_not_adopted(
    full_latex, damage
):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, _, calls, base, _, _ = full_latex
    runner = store.model_runner

    def change_destination(config, prompt, **kwargs):
        receipt = json.loads((config.workspace / "project-preflight.json").read_text())
        assert receipt["status"] == "ready"
        assert receipt["binding"]["source_policy"] == "generated-latex-project/v1"
        project = config.workspace / "project"
        assert (project / "main.tex").read_bytes() == (base / "main.tex").read_bytes()
        result = runner(config, prompt, **kwargs)
        if damage == "redirect":
            outside = base.parent / "outside-note.txt"
            outside.write_text("Preserve outside bytes")
            (project / "style-note.txt").unlink()
            (project / "style-note.txt").symlink_to(outside)
        else:
            name = "main.tex" if damage == "main" else "style-note.txt"
            (project / name).write_text("Changed during the model call")
        return result

    store.model_runner = change_destination
    with pytest.raises(PortalDataError) as failure:
        generate(full_latex)
    assert failure.value.code == (
        "prism_source_invalid" if damage == "redirect" else "prism_source_changed"
    )
    assert len(calls) == 1
    assert len(list(store.root.glob("*/model-result.json"))) == 1
    assert not list(store.root.glob("*/draft.json"))
    assert (base / "style-note.txt").read_text() == "Original ancillary source; keep unchanged"
    if damage == "redirect":
        assert (base.parent / "outside-note.txt").read_text() == "Preserve outside bytes"


def test_model_failure_retains_preflight_project_without_a_retry(full_latex):
    from career_evidence_graph.career_portal_data import PortalDataError
    from career_evidence_graph.codex_cli import CodexCLIError

    store, _, _, _, calls, base, _, _ = full_latex

    def fail_once(config, prompt, **kwargs):
        calls.append(config.workspace)
        raise CodexCLIError("Synthetic model failure")

    store.model_runner = fail_once
    with pytest.raises(PortalDataError) as failure:
        generate(full_latex)
    assert failure.value.code == "resume_model_unavailable"
    assert len(calls) == 1
    directory = calls[0]
    assert json.loads((directory / "project-preflight.json").read_text())["status"] == "ready"
    assert json.loads((directory / "model-result.json").read_text())["status"] == "failed"
    assert (directory / "project/main.tex").read_bytes() == (base / "main.tex").read_bytes()
    assert not (directory / "draft.json").exists()
    assert not list(store.root.rglob("*.pdf"))


def test_git_metadata_inside_destination_is_rejected_before_model(full_latex, monkeypatch):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, _, calls, _, _, _ = full_latex
    mkdir = Path.mkdir

    def insert_git(path, *args, **kwargs):
        result = mkdir(path, *args, **kwargs)
        if path.name == "project":
            (path / ".git").write_text("gitdir: /synthetic/outside")
        return result

    monkeypatch.setattr(Path, "mkdir", insert_git)
    with pytest.raises(PortalDataError) as failure:
        generate(full_latex)
    assert failure.value.code == "resume_destination_invalid"
    assert calls == []
    assert not list(store.root.glob("*/model-input.json"))
    assert not list(store.root.glob("*/draft.json"))


def test_generation_schema_limits_citations_to_supplied_source_ids(full_latex):
    store, _, _, _, calls, _, _, _ = full_latex
    runner = store.model_runner

    def check_schema(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        schema = json.loads(config.output_schema.read_text())
        references = schema["properties"]["groups"]["items"]["properties"]["source_ids"]
        assert references["items"] == {
            "type": "string",
            "enum": [source["source_id"] for source in payload["sources"]],
        }
        assert references["items"]["enum"]
        assert all(references["items"]["enum"])
        assert references.get("minItems", 0) == 0
        assert {doc["id"] for doc in payload["document_context"]}.isdisjoint(
            references["items"]["enum"]
        )
        return runner(config, prompt, **kwargs)

    store.model_runner = check_schema
    result = generate(full_latex)
    assert len(calls) == 1
    assert len(result["review_groups"]) == 7
    assert result["review_groups"][1]["sources"][0]["source_id"] in {
        source["source_id"] for source in calls[0]["sources"]
    }


@pytest.mark.parametrize(
    "model_span", ["valid", "cross_education", "missing_first_blank", "missing_final_blank"]
)
def test_generation_numbers_every_original_body_line_and_marks_education(full_latex, model_span):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, _, calls, project, output, _ = full_latex
    lines = [
        "\n",
        " \t\n",
        "Synthetic Person\r\n",
        "\\section*{Education}\r\n",
        "MSc Mathematics, Synthetic University, 2020.\r\n",
        " \t\r\n",
        "\\section*{Project 1}\n",
        "Analyzed strategy and built 1 Python services.\n",
        "\n",
        "\t",
    ]
    original = (
        "\\documentclass[a4paper]{article}\n\\begin{document}\n"
        + "".join(lines)
        + "\\end{document}\n"
    ).encode()
    (project / "main.tex").write_bytes(original)
    identity, project_group = output["groups"][:2]
    identity.update(start_line=1, end_line=3, latex="".join(lines[:3]))
    project_group.update(start_line=7, end_line=10, latex="".join(lines[6:]))
    output["groups"] = [
        identity,
        {
            "title": "Education",
            "start_line": 4,
            "end_line": 6,
            "source_ids": [],
            "latex": "".join(lines[3:6]),
            "disposition": "verify",
            "reason": "Documentary confirmation required",
        },
        project_group,
    ]
    if model_span == "cross_education":
        output["groups"][1].update(end_line=7, latex="".join(lines[3:7]))
        project_group.update(start_line=8, latex="".join(lines[7:]))
    elif model_span == "missing_first_blank":
        identity.update(start_line=2, latex="".join(lines[1:3]))
    elif model_span == "missing_final_blank":
        project_group.update(end_line=9, latex="".join(lines[6:9]))
    if model_span == "valid":
        result = generate(full_latex)
        assert result["verification_queue"][0]["original"] == "".join(lines[3:6])
    else:
        with pytest.raises(PortalDataError) as failure:
            generate(full_latex)
        assert failure.value.code == "resume_latex_invalid"
        assert not list(store.root.glob("*/draft.json"))
    payload = calls[0]
    assert payload["body_lines"] == [
        {"line_number": number, "text": text} for number, text in enumerate(lines, 1)
    ]
    assert payload["body_line_count"] == 10
    assert payload["fixed_education_lines"] == [4, 5, 6]
    assert "".join(row["text"] for row in payload["body_lines"]) == "".join(lines)
    assert payload["base"].encode() == original
    assert (project / "main.tex").read_bytes() == original


def test_generation_schema_with_no_sources_allows_only_empty_citations(full_latex):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, job, _, analysis, calls, project, output, inputs = full_latex
    for path in store.catalog.root.rglob("*"):
        if path.is_file():
            path.unlink()
    sources = career_source_snapshot(store.catalog)
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    for group in output["groups"]:
        group["source_ids"] = []
    runner = store.model_runner

    def check_schema(config, prompt, **kwargs):
        payload = json.loads(prompt[prompt.index("{") :])
        assert payload["sources"] == []
        schema = json.loads(config.output_schema.read_text())
        assert schema["properties"]["groups"]["items"]["properties"]["source_ids"] == {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 0,
        }
        return runner(config, prompt, **kwargs)

    store.model_runner = check_schema
    with pytest.raises(PortalDataError) as failure:
        generate((store, job, sources, analysis, calls, project, output, inputs))
    assert failure.value.code == "resume_material_insufficient"
    assert len(calls) == 1
    assert not list(store.root.glob("*/draft.json"))


def test_oversized_context_retains_inputs_without_starting_model(full_latex):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, analysis, calls, project, _, inputs = full_latex
    report = store.catalog.root / "reports/large-report.md"
    report.parent.mkdir(exist_ok=True)
    original = "# Historical context\n" + "未审阅的历史资料" * 10_000
    report.write_text(original)
    sources = career_source_snapshot(store.catalog)
    full_latex = (*full_latex[:2], sources, *full_latex[3:])
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    before = {p.name: p.read_bytes() for p in project.iterdir()}

    with pytest.raises(PortalDataError) as failure:
        generate(full_latex)

    assert failure.value.code == "resume_latex_context_too_large"
    assert calls == []
    assert {p.name: p.read_bytes() for p in project.iterdir()} == before
    assert report.read_text() == original
    retained = json.loads(next(store.root.glob("*/source-snapshot.json")).read_text())
    assert retained == sources
    payload = json.loads(next(store.root.glob("*/input.json")).read_text())
    assert any(doc.get("content") == original for doc in payload["document_context"])
    receipt = json.loads(next(store.root.glob("*/model-result.json")).read_text())
    assert receipt["status"] == "not_started"
    assert receipt["error_code"] == "resume_latex_context_too_large"
    assert receipt["model_started"] is False
    assert not any(
        event["kind"] == "stage_start" and event.get("stage") == "model"
        for event in store.measurements.read()
    )
    for episode in store.measurements.summary()["episodes"]:
        assert episode["model_calls"] == 0
        assert episode["synthetic_model_calls"] == 0
        assert episode["model_calls_unknown"] == 0
    assert not list(store.root.glob("*/draft.json"))
    assert not list(store.root.rglob("*.pdf"))


def test_relevance_omission_and_unverifiable_original_are_preserved_separately(full_latex):
    _, _, _, _, _, _, output, _ = full_latex
    output["groups"][5].update(disposition="omit", reason="Weaker relevance to this JD")
    output["groups"][6].update(source_ids=[], disposition="omit", reason="Cannot identify source")
    result = generate(full_latex)
    assert "\\section*{Project 5}" not in result["latex_source"]
    assert "\\section*{Project 6}" not in result["latex_source"]
    assert result["omitted_groups"][0]["title"] == "Project 5"
    assert result["omitted_groups"][0]["reason"] == "Weaker relevance to this JD"
    assert "built 5 Python services" in result["omitted_groups"][0]["original"]
    assert result["verification_queue"][0]["title"] == "Project 6"
    assert result["verification_queue"][0]["reason"].startswith("source_or_attribution_unresolved")
    assert "built 6 Python services" in result["verification_queue"][0]["original"]
    assert result["verification_queue"][0]["review_status"] == "review_required"


def test_identity_reference_cannot_be_used_as_evidence_for_a_project(full_latex):
    _, _, _, _, _, _, output, _ = full_latex
    output["groups"][6]["source_ids"] = output["groups"][0]["source_ids"]
    # Keeping original bytes must not allow identity evidence to support work claims.
    output["groups"][6]["latex"] = output["groups"][6]["latex"].replace(
        "strategy; built", "strategy and built"
    )
    result = generate(full_latex)
    assert "\\section*{Project 6}" not in result["latex_source"]
    assert result["verification_queue"][0]["title"] == "Project 6"


def test_reuses_applicable_confirmed_identity_without_disclosing_application_answers(full_latex):
    _, _, _, _, calls, _, output, inputs = full_latex
    records = [
        {
            "key": "identity-key",
            "question": "Full name",
            "value": "Synthetic Person",
            "state": "confirmed",
            "scope": {},
        },
        {
            "key": "visa-key",
            "question": "Do you currently have work authorization in this country",
            "value": "Private application-only answer",
            "state": "confirmed",
            "scope": {},
        },
        {
            "key": "foreign-key",
            "question": "Email",
            "value": "foreign@example.invalid",
            "state": "confirmed",
            "scope": {"company": "Another Company"},
        },
        {
            "key": "pending-key",
            "question": "Phone",
            "value": "Unconfirmed phone",
            "state": "proposed",
            "scope": {},
        },
    ]
    inputs["information_library_revision"] = "a" * 64
    output["groups"][0]["source_ids"] = ["answer:identity-key"]
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "a" * 64,
            "records": records,
            "preferences": {},
        },
    )
    assert result["review_groups"][0]["sources"][0]["confirmation_state"] == "confirmed"
    assert result["review_groups"][0]["sources"][0]["locator"] == "answers.identity-key"
    assert result["information_library_revision"] == "a" * 64
    assert "Private application-only answer" not in json.dumps(calls[-1])
    assert "foreign@example.invalid" not in json.dumps(calls[-1])
    assert "Unconfirmed phone" not in json.dumps(calls[-1])


@pytest.mark.parametrize("archive", ["base-sources.json", "latex-sources.json"])
def test_saved_full_source_read_rejects_changed_archives(full_latex, archive):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, *_ = full_latex
    result = generate(full_latex)
    (store.root / result["id"] / archive).write_text("{}")
    with pytest.raises(PortalDataError) as error:
        store.draft(result["id"])
    assert error.value.code == "resume_draft_invalid"


@pytest.mark.parametrize(
    "model_choice",
    [
        "omit",
        "verify",
        "change_degree_and_date",
        "base_missing_status",
        "wrong_source_heading",
        "cross_credentials",
        "multiple_wrong_sources",
    ],
)
def test_documented_education_is_reused_without_a_separate_answer_record(full_latex, model_choice):
    store, _, _, analysis, _, project, output, _ = full_latex
    path = store.catalog.root / "sources/profile.json"
    path.write_text(
        json.dumps(
            {
                "name": "Synthetic Person",
                "education": [
                    {
                        "degree": "MSc Mathematics (in progress)"
                        if model_choice == "base_missing_status"
                        else "MSc Mathematics",
                        "institution": "Synthetic University",
                        "period": "2020",
                        "detail": "Probability. Expected; not awarded."
                        if model_choice == "base_missing_status"
                        else "Probability",
                    }
                ],
            }
        )
    )
    sources = career_source_snapshot(store.catalog)
    if model_choice in {"cross_credentials", "multiple_wrong_sources"}:
        profile = json.loads(path.read_text())
        profile["education"][0]["degree"] = "BSc Mathematics"
        profile["education"].append(
            {
                "degree": "MSc Mathematics",
                "institution": "Other University",
                "period": "2022",
                "detail": "Probability",
            }
        )
        path.write_text(json.dumps(profile))
        sources = career_source_snapshot(store.catalog)
    full_latex = list(full_latex)
    full_latex[2] = sources
    full_latex[7]["sources_revision"] = sources["revision"]
    analysis["source_snapshot_revision"] = sources["revision"]
    education = "\\section*{Education}\nMSc Mathematics, Synthetic University, 2020. Probability.\n"
    if model_choice == "wrong_source_heading":
        education = education.replace("{Education}", "{Academic Qualifications}")
    elif model_choice == "multiple_wrong_sources":
        education = (
            "\\section*{Education}\n"
            "\\entry{BSc Mathematics}{Synthetic University}{2020}{Probability}"
            "\\entry{MSc Mathematics}{Other University}{2022}{Probability}\n"
        )
    main = project / "main.tex"
    main.write_text(main.read_text().replace("\\end{document}", education + "\\end{document}"))
    output["groups"].append(
        {
            "title": "Education",
            "start_line": 14,
            "end_line": 15,
            "source_ids": [sources["profile_source"]["id"] + ":profile.education[0]"],
            "latex": education,
            "disposition": "include",
            "reason": "Documented degree",
        }
    )
    # The JD/model cannot omit a documented fixed education entry.
    if model_choice == "change_degree_and_date":
        output["groups"][-1]["latex"] = education.replace("MSc", "PhD").replace("2020", "2025")
    elif model_choice in {"wrong_source_heading", "multiple_wrong_sources"}:
        output["groups"][-1].update(
            source_ids=output["groups"][1]["source_ids"],
            disposition="omit",
            reason="Model misclassified as work",
        )
    elif model_choice == "cross_credentials":
        output["groups"][-1]["source_ids"].append(
            sources["profile_source"]["id"] + ":profile.education[1]"
        )
    elif model_choice != "base_missing_status":
        output["groups"][-1].update(
            disposition=model_choice, latex="", reason="Less relevant to this JD"
        )
    result = generate(full_latex)
    if model_choice in {"base_missing_status", "cross_credentials"}:
        assert education not in result["latex_source"]
        assert result["verification_queue"][0]["title"] == "Education"
        assert (
            result["verification_queue"][0]["content_policy"] == "education_verification_required"
        )
        return
    assert education in result["latex_source"]
    assert result["review_groups"][-1]["sources"][0]["locator"] == "profile.education[0]"
    assert result["review_groups"][-1]["content_policy"] == "fixed_education"
    assert result["verification_queue"] == []
    assert result["review_status"] == "review_required"


def test_generated_cv_rejects_tool_assistance_disclosure_but_keeps_internal_sources(full_latex):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, analysis, _, _, output, _ = full_latex
    source_path = store.catalog.root / "contributions/project-1.md"
    source_path.write_text(
        source_path.read_text() + "\nCodex-assisted implementation recorded internally.\n"
    )
    sources = career_source_snapshot(store.catalog)
    full_latex = list(full_latex)
    full_latex[2] = sources
    full_latex[7]["sources_revision"] = sources["revision"]
    analysis["source_snapshot_revision"] = sources["revision"]
    output["groups"][1]["latex"] += "Implemented with AI assistance.\n"
    with pytest.raises(PortalDataError) as error:
        generate(full_latex)
    assert error.value.code == "resume_tool_attribution_disclosure"
    assert not list(store.root.glob("*/draft.json"))
    retained = json.loads(next(store.root.glob("*/source-snapshot.json")).read_text())
    assert any("Codex-assisted" in item.get("content", "") for item in retained["documents"])


def test_skill_and_work_wording_can_follow_jd_without_disclosing_tool_provenance(full_latex):
    _, _, _, _, calls, _, output, _ = full_latex
    output["groups"][1]["latex"] = "\\section*{Skills}\nPython services; strategy analysis.\n"
    result = generate(full_latex)
    assert "\\section*{Skills}\nPython services; strategy analysis." in result["latex_source"]
    group = result["review_groups"][1]
    assert group["content_policy"] == "jd_tailored"
    assert "built 1 Python services" in group["original"]
    assert group["sources"]
    assert calls[-1]["presentation_policy"] == "resume-presentation/v1"
    assert result["factual_review"] == "pending"


def test_internal_latex_comment_does_not_become_a_public_tool_disclosure(full_latex):
    _, _, _, _, _, _, output, _ = full_latex
    output["groups"][1]["latex"] += "% Codex-assisted implementation retained internally\n"
    result = generate(full_latex)
    assert "% Codex-assisted" in result["latex_source"]
    assert result["factual_review"] == "pending"


@pytest.mark.parametrize(
    "change",
    [
        "uncovered",
        "overlap",
        "foreign_source",
        "bare_document_id",
        "embedded_experience_id",
        "read_command",
        "write_command",
    ],
)
def test_incomplete_or_executable_model_fragments_cannot_become_a_draft(full_latex, change):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, _, _, _, _, _, output, _ = full_latex
    if change == "uncovered":
        output["groups"].pop()
    elif change == "overlap":
        output["groups"][2]["start_line"] = 2
    elif change == "foreign_source":
        output["groups"][2]["source_ids"] = ["other:source"]
    elif change == "bare_document_id":
        output["groups"][2]["source_ids"] = [full_latex[2]["documents"][0]["id"]]
    elif change == "embedded_experience_id":
        output["groups"][2]["source_ids"] = ["exp-synthetic-body-label"]
    elif change == "read_command":
        output["groups"][2]["latex"] += "\\input{/private/file}\n"
    else:
        output["groups"][2]["latex"] += "\\immediate\\write18{touch /private/tmp/unwanted}\n"
    with pytest.raises(PortalDataError):
        generate(full_latex)
    assert not list(store.root.glob("*/draft.json"))


@pytest.mark.parametrize(
    "declaration", ["\\documentclass{article}", "\\documentclass[10pt,letterpaper]{article}"]
)
def test_independent_version_sets_default_a4_without_modifying_base(full_latex, declaration):
    _, _, _, _, _, project, _, _ = full_latex
    main = project / "main.tex"
    main.write_text(main.read_text().replace("\\documentclass[a4paper]{article}", declaration))
    before = main.read_bytes()
    result = generate(full_latex)
    assert "a4paper" in result["latex_source"].splitlines()[0]
    assert "letterpaper" not in result["latex_source"].splitlines()[0]
    assert main.read_bytes() == before


def test_new_unsupported_result_number_stays_outside_resume_body(full_latex):
    _, _, _, _, _, _, output, _ = full_latex
    output["groups"][6]["latex"] = output["groups"][6]["latex"].replace("6 Python", "99 Python")
    result = generate(full_latex)
    assert "99 Python" not in result["latex_source"]
    assert result["verification_queue"][0]["title"] == "Project 6"
    assert "99 Python" in result["verification_queue"][0]["rewritten"]


@pytest.mark.parametrize("separator", ["", " ", "% comment\n"])
def test_model_cannot_add_a_file_writing_environment(full_latex, separator):
    from career_evidence_graph.career_portal_data import PortalDataError

    _, _, _, _, _, _, output, _ = full_latex
    output["groups"][1]["latex"] += (
        f"\\begin{separator}{{filecontents*}}{{/private/tmp/should-not-write.txt}}\n"
        f"untrusted\n\\end{separator}{{filecontents*}}\n"
    )
    with pytest.raises(PortalDataError) as error:
        generate(full_latex)
    assert error.value.code == "resume_latex_invalid"


@pytest.mark.parametrize("change", ["base", "career", "job", "configuration"])
def test_input_drift_preserves_attempt_without_adopting_full_draft(full_latex, change):
    from career_evidence_graph.career_portal_data import PortalDataError

    store, job, _, _, calls, project, _, _ = full_latex
    runner = store.model_runner

    def changed(config, prompt, **kwargs):
        result = runner(config, prompt, **kwargs)
        if change == "base":
            (project / "main.tex").write_text((project / "main.tex").read_text() + "% changed\n")
        elif change == "career":
            (store.catalog.root / "contributions/project-1.md").write_text("# Changed source")
        elif change == "job":
            store.applications.update_application(
                job["id"], {"job_description": "A changed JD"}, job["revision"]
            )
        else:
            store.tailorer = lambda *_: None
        return result

    store.model_runner = changed
    with pytest.raises(PortalDataError) as error:
        generate(full_latex)
    assert error.value.code in {"resume_inputs_stale", "prism_source_changed"}
    assert len(calls) == 1
    assert len(list(store.root.glob("*/model-result.json"))) == 1
    assert not list(store.root.glob("*/draft.json"))


def test_explicit_new_generation_retains_previous_complete_version(full_latex):
    store, *_ = full_latex
    first = generate(full_latex)
    before = {p: p.read_bytes() for p in (store.root / first["id"]).rglob("*") if p.is_file()}
    second = generate(full_latex, force_regenerate=True)
    assert second["id"] != first["id"]
    assert store.draft(first["id"])["latex_source"] == first["latex_source"]
    assert before == {p: p.read_bytes() for p in before}


def test_full_generation_preserves_language_and_confirmation_revision_guards(full_latex):
    from career_evidence_graph.application_flow import job_input_revision
    from career_evidence_graph.career_portal_data import PortalDataError

    store, job, _, analysis, calls, _, _, inputs = full_latex
    inputs["information_library_revision"] = "b" * 64
    with pytest.raises(PortalDataError) as error:
        generate(full_latex, information_library={"revision": "c" * 64})
    assert error.value.code == "resume_inputs_stale"
    job = store.applications.update_application(
        job["id"], {"job_description": "Submit your CV in German."}, job["revision"]
    )
    data = list(full_latex)
    data[1] = job
    analysis["jd_revision"] = job_input_revision(job)
    with pytest.raises(PortalDataError) as error:
        generate(data)
    assert error.value.code == "resume_language_needs_input"
    assert calls == []


def test_conflicting_confirmed_name_cannot_be_avoided_by_citing_profile_instead(full_latex):
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "d" * 64,
            "records": [
                {
                    "key": "name",
                    "question": "Full name",
                    "value": "Another Person",
                    "state": "confirmed",
                    "scope": {},
                }
            ],
        },
    )
    assert "Synthetic Person\n" not in result["latex_source"]
    assert result["verification_queue"][0]["title"] == "Identity"


def test_documented_work_dates_supply_context_without_claiming_personal_responsibility(full_latex):
    store, _, _, analysis, _, project, output, inputs = full_latex
    path = store.catalog.root / "sources/profile.json"
    path.write_text(
        json.dumps(
            {
                "name": "Synthetic Person",
                "experience": [
                    {
                        "role": "Founder",
                        "organization": "STOA",
                        "period": "2021–2024",
                        "detail": "Team work",
                    }
                ],
            }
        )
    )
    sources = career_source_snapshot(store.catalog)
    data = list(full_latex)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    main = project / "main.tex"
    main.write_text(
        main.read_text().replace("\\end{document}", "Founder, STOA, 2021–2024.\n\\end{document}")
    )
    group = output["groups"][6]
    group["end_line"] = 14
    group["latex"] += "Founder, STOA, 2021–2024.\n"
    group["source_ids"].append(sources["profile_source"]["id"] + ":profile.experience[0].context")
    result = generate(data)
    assert "Founder, STOA, 2021–2024." in result["latex_source"]
    assert result["verification_queue"] == []
    assert result["review_groups"][-1]["attribution"] == [
        "User",
        "Documented career context; no contribution attribution",
    ]


def test_career_context_alone_cannot_be_rewritten_into_personal_capability(full_latex):
    store, _, _, analysis, _, project, output, inputs = full_latex
    path = store.catalog.root / "sources/profile.json"
    path.write_text(
        json.dumps(
            {
                "name": "Synthetic Person",
                "experience": [
                    {
                        "role": "Founder",
                        "organization": "STOA",
                        "period": "2021",
                        "detail": "Team work",
                    }
                ],
            }
        )
    )
    sources = career_source_snapshot(store.catalog)
    data = list(full_latex)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    main = project / "main.tex"
    main.write_text(
        main.read_text().replace(
            "\\section*{Project 6}\nAnalyzed strategy and built 6 Python services.",
            "Founder, STOA, 2021\n",
        )
    )
    group = output["groups"][6]
    group["source_ids"] = [sources["profile_source"]["id"] + ":profile.experience[0].context"]
    group["latex"] = "Led engineering and strategy decisions.\n"
    result = generate(data)
    assert "Led engineering" not in result["latex_source"]
    assert result["verification_queue"][0]["title"] == "Project 6"


def test_existing_centered_identity_layout_is_not_mistaken_for_an_unverified_claim(full_latex):
    _, _, _, _, _, project, output, _ = full_latex
    header = "\\begin{center}\\fontsize{24}{26}\\selectfont Synthetic Person\\end{center}\n"
    main = project / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", header))
    output["groups"][0]["latex"] = header
    result = generate(full_latex)
    assert header in result["latex_source"]
    assert result["verification_queue"] == []


@pytest.mark.parametrize("scenario", ["reuse", "changed_base", "education_cannot_support_work"])
@pytest.mark.parametrize("profile_form", ["equivalent", "exact"])
@pytest.mark.parametrize("model_citation", ["retained", "work"])
def test_retained_material_supplies_sources_and_reuses_unchanged_education(
    full_latex, retained_capture, profile_form, model_citation, scenario
):
    from career_evidence_graph.application_worker import digest

    store, _, _, analysis, _, project, output, inputs = full_latex
    case = retained_capture
    if case["catalog"].root != store.catalog.root:
        shutil.copytree(case["catalog"].root / ".retained", store.catalog.root / ".retained")
    profile = {"name": "Synthetic Person", **case["profile"]}
    if profile_form == "equivalent":
        profile["education"][0]["degree"] = "Doctor of Philosophy candidate"
        profile["education"][0]["detail"] += "; documentary additional detail"
    (store.catalog.root / "sources/profile.json").write_text(json.dumps(profile))
    manifest = case["manifest"]
    manifest["groups"][0]["education_profile_sha256"] = digest(profile["education"][0])
    scope = store.catalog.root / "contributions/project-1.md"
    scope.write_text(
        "# Project 1\n\n## Scope\n\nDefined the service design.\n\n"
        "## Responsibility attribution\n\n| Area | Attribution |\n| --- | --- |\n"
        "| Design | User |\n| Implementation | Codex |\n\n"
        "## Boundaries\n\nDesign does not establish personal implementation.\n"
    )
    manifest["groups"][1]["context_source_ids"] = [output["groups"][1]["source_ids"][0]]
    (store.catalog.root / "sources/retained-resume-sources.json").write_text(json.dumps(manifest))
    sources = career_source_snapshot(store.catalog)
    retained = sources["retained_materials"]
    assert len(retained) == 2
    assert retained[1]["design_only"] is True
    assert "Codex" in retained[1]["attribution"]
    assert "personal implementation" in retained[1]["boundaries"]
    (project / "main.tex").write_text(case["source"])
    output["groups"] = [
        {
            "title": "Education",
            "start_line": 1,
            "end_line": 2,
            "source_ids": [retained[0 if model_citation == "retained" else 1]["source_id"]],
            "latex": "PhD awarded in 2028.\n",
            "disposition": "omit",
            "reason": "Model should not alter fixed education",
        },
        {
            "title": "Service",
            "start_line": 3,
            "end_line": 4,
            "source_ids": [retained[1]["source_id"]],
            "latex": "\\section{Experience}\nBuilt a Python service with the engineering team.\n",
            "disposition": "include",
            "reason": "Reuse factual team scope",
        },
    ]
    data = list(full_latex)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    if scenario == "changed_base":
        main = project / "main.tex"
        main.write_text(main.read_text().replace("{article}", "[10pt]{article}"))
        with pytest.raises(Exception) as error:
            generate(data)
        assert error.value.code == "resume_latex_invalid"
        return
    if scenario == "education_cannot_support_work":
        output["groups"][1]["source_ids"] = [retained[0]["source_id"]]
    result = generate(data)
    if scenario == "education_cannot_support_work":
        assert len(result["verification_queue"]) == 1
        assert "Built a Python service" not in result["latex_source"]
    else:
        assert result["verification_queue"] == []
    assert result["review_groups"][0]["content_policy"] == "fixed_education"
    assert "PhD in progress" in result["latex_source"]
    assert "Expected July 2028" in result["latex_source"]
    assert "awarded" not in result["latex_source"]
    assert result["factual_review"] == "pending"
    assert not list(store.root.rglob("*.pdf"))
    wire = data[4][-1]
    wire_education = next(s for s in wire["sources"] if s["source_id"] == retained[0]["source_id"])
    assert wire_education["text_from_base_lines"] == {"start_line": 1, "end_line": 2}
    assert "accepted_latex" not in wire_education.get("text", "")
    assert "retained_source_sha256" not in wire_education
    assert all(
        d["source_name"] != "sources/retained-resume-sources.json" for d in wire["document_context"]
    )
    saved = json.loads(next(store.root.glob("*/input.json")).read_text())
    canonical_education = next(
        s for s in saved["sources"] if s["source_id"] == retained[0]["source_id"]
    )
    assert "accepted_latex" in canonical_education["text"]


def test_json_context_compaction_preserves_exact_decimal_and_string_values(full_latex):
    store, _, _, analysis, calls, _, _, inputs = full_latex
    text = (
        "{\n"
        '  "measurement": 0.12345678901234567890123456789,\n'
        '  "note": "keep  two spaces and \\"quotes\\""\n'
        "}\n"
    )
    (store.catalog.root / "reports").mkdir(exist_ok=True)
    (store.catalog.root / "reports/measurement.json").write_text(text)
    snapshot = career_source_snapshot(store.catalog)
    data = list(full_latex)
    data[2] = snapshot
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = snapshot["revision"]
    generate(data)
    wire = next(
        d["content"]
        for d in calls[-1]["document_context"]
        if d["source_name"] == "reports/measurement.json"
    )
    assert "0.12345678901234567890123456789" in wire
    assert 'keep  two spaces and \\"quotes\\"' in wire
    assert "\n" not in wire


def test_full_generation_uses_job_contact_exception_over_general_and_profile(full_latex):
    store, job, _, analysis, calls, base, output, inputs = full_latex
    main = base / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", "job@example.invalid\n"))
    profile_path = store.catalog.root / "sources/profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "Synthetic Person",
                "links": [
                    {"label": "Email", "href": "mailto:profile@example.invalid"},
                ],
            }
        )
    )
    sources = career_source_snapshot(store.catalog)
    full_latex = list(full_latex)
    full_latex[2] = sources
    inputs["sources_revision"] = sources["revision"]
    inputs["information_library_revision"] = "a" * 64
    analysis["source_snapshot_revision"] = sources["revision"]
    output["groups"][0].update(source_ids=["answer:job-email"], latex="job@example.invalid\n")
    records = [
        {
            "key": "global-email",
            "question": "Email",
            "value": "global@example.invalid",
            "state": "confirmed",
            "scope": {},
        },
        {
            "key": "job-email",
            "question": "Email",
            "value": "job@example.invalid",
            "state": "confirmed",
            "scope": {"application_id": job["id"]},
        },
    ]
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "a" * 64,
            "records": records,
            "preferences": {},
        },
    )
    assert "job@example.invalid" in result["latex_source"]
    assert result["verification_queue"] == []
    assert result["review_groups"][0]["sources"][0]["scope"] == {"application_id": job["id"]}
    assert "global@example.invalid" not in json.dumps(calls[-1])
    assert "profile@example.invalid" not in json.dumps(calls[-1]["sources"])
    assert "profile@example.invalid" in profile_path.read_text()


@pytest.mark.parametrize(
    "question,global_value,job_value",
    [
        ("Full name", "General Person", "Job Person"),
        ("Phone", "+41 111 111 111", "+41 222 222 222"),
    ],
)
def test_full_generation_uses_applicable_name_and_phone(
    full_latex, question, global_value, job_value
):
    _, job, _, _, calls, base, output, inputs = full_latex
    main = base / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", job_value + "\n"))
    output["groups"][0].update(source_ids=["answer:job-contact"], latex=job_value + "\n")
    inputs["information_library_revision"] = "b" * 64
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "b" * 64,
            "preferences": {},
            "records": [
                {
                    "key": "general-contact",
                    "question": question,
                    "value": global_value,
                    "state": "confirmed",
                    "scope": {},
                },
                {
                    "key": "job-contact",
                    "question": question,
                    "value": job_value,
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                },
            ],
        },
    )
    assert job_value in result["latex_source"]
    assert result["verification_queue"] == []
    assert global_value not in json.dumps(calls[-1])


def test_full_generation_keeps_incomparable_contact_scopes_unresolved(full_latex):
    _, job, _, _, _, _, output, inputs = full_latex
    output["groups"][0].update(
        source_ids=["answer:company-contact"], latex="company@example.invalid\n"
    )
    inputs["information_library_revision"] = "c" * 64
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "c" * 64,
            "preferences": {},
            "records": [
                {
                    "key": "company-contact",
                    "question": "Email",
                    "value": "company@example.invalid",
                    "state": "confirmed",
                    "scope": {"company": job["company"]},
                },
                {
                    "key": "country-contact",
                    "question": "Email",
                    "value": "country@example.invalid",
                    "state": "confirmed",
                    "scope": {"country": "OTHER"},
                },
            ],
        },
    )
    assert "company@example.invalid" not in result["latex_source"]
    assert result["verification_queue"][0]["title"] == "Identity"
    assert result["verification_queue"][0]["sources"][0]["resume_eligible"] is False


@pytest.mark.parametrize(
    "question,old_value,current_value",
    [
        ("Full name", "Original Person", "Current Person"),
        ("Email", "old@example.invalid", "current@example.invalid"),
        ("Phone", "+41 111 111 111", "+41 222 222 222"),
    ],
)
def test_current_contact_replaces_bound_historical_header_without_repeat_review(
    full_latex,
    question,
    old_value,
    current_value,
):
    store, job, _, _, _, base, output, inputs = full_latex
    prompts = []
    runner = store.model_runner

    def capture_prompt(config, prompt, **kwargs):
        prompts.append(prompt)
        return runner(config, prompt, **kwargs)

    store.model_runner = capture_prompt
    profile_path = store.catalog.root / "sources/profile.json"
    original_profile = profile_path.read_bytes()
    main = base / "main.tex"
    original_base = main.read_text().replace("Synthetic Person\n", old_value + "\n")
    main.write_text(original_base)
    output["groups"][0].update(
        source_ids=["answer:current-contact"],
        latex=current_value + "\n",
    )
    inputs["information_library_revision"] = "d" * 64
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "d" * 64,
            "preferences": {},
            "records": [
                {
                    "key": "general-contact",
                    "question": question,
                    "value": old_value,
                    "state": "confirmed",
                    "scope": {},
                },
                {
                    "key": "current-contact",
                    "question": question,
                    "value": current_value,
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                },
            ],
        },
    )
    assert current_value in result["latex_source"]
    assert old_value not in result["latex_source"]
    assert result["verification_queue"] == []
    assert result["review_groups"][0]["original"] == old_value + "\n"
    assert result["review_groups"][0]["sources"][0]["scope"] == {"application_id": job["id"]}
    assert main.read_text() == original_base
    assert profile_path.read_bytes() == original_profile
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]
    assert result["factual_review"] == "pending"
    assert "identity/contact header before the first section" in prompts[0]
    assert "complete current applicable confirmed contact value" in prompts[0]
    assert "Do not use this exception in\neducation, work or capability groups" in prompts[0]


@pytest.mark.parametrize("section", ["Project 1", "Education"])
def test_current_contact_header_exception_does_not_rewrite_work_or_education(full_latex, section):
    _, job, _, _, _, base, output, inputs = full_latex
    main = base / "main.tex"
    main.write_text(
        main.read_text().replace("\\section*{Project 1}", "\\section*{" + section + "}")
    )
    output["groups"][1].update(
        source_ids=["answer:current-contact"],
        latex="current@example.invalid\n",
    )
    inputs["information_library_revision"] = "e" * 64
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "e" * 64,
            "preferences": {},
            "records": [
                {
                    "key": "current-contact",
                    "question": "Email",
                    "value": "current@example.invalid",
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                },
            ],
        },
    )
    assert "current@example.invalid" not in result["latex_source"]
    assert result["verification_queue"][0]["original"].startswith("\\section*{" + section + "}")
    assert result["verification_queue"][0]["disposition"] == "verify"


@pytest.mark.parametrize(
    "rewrite", ["current\n", "current@example.invalid Implemented Python services.\n"]
)
def test_current_contact_header_requires_complete_value_and_no_capability_claim(
    full_latex, rewrite
):
    _, job, _, _, _, base, output, inputs = full_latex
    main = base / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", "old@example.invalid\n"))
    output["groups"][0].update(source_ids=["answer:current-contact"], latex=rewrite)
    inputs["information_library_revision"] = "f" * 64
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "f" * 64,
            "preferences": {},
            "records": [
                {
                    "key": "current-contact",
                    "question": "Email",
                    "value": "current@example.invalid",
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                },
            ],
        },
    )
    assert rewrite not in result["latex_source"]
    assert result["verification_queue"][0]["title"] == "Identity"


def test_identity_header_can_remove_internal_group_comment_without_changing_facts(full_latex):
    store, _, _, _, _, base, output, _ = full_latex
    main = base / "main.tex"
    main.write_text(
        main.read_text().replace(
            "Synthetic Person\n", "% internal group: identity\nSynthetic Person\n"
        )
    )
    output["groups"][0]["end_line"] = 2
    for group in output["groups"][1:]:
        group["start_line"] += 1
        group["end_line"] += 1
    result = generate(full_latex)
    assert result["verification_queue"] == []
    assert (
        result["review_groups"][0]["original"] == "% internal group: identity\nSynthetic Person\n"
    )
    assert result["review_groups"][0]["rewritten"] == "Synthetic Person\n"
    assert "% internal group: identity" not in result["latex_source"]
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]


def test_identity_format_exception_does_not_change_contact_punctuation(full_latex):
    _, job, _, _, _, base, output, inputs = full_latex
    main = base / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", "first.last@example.invalid\n"))
    output["groups"][0].update(
        source_ids=["answer:current-contact"], latex="first-last@example.invalid\n"
    )
    inputs["information_library_revision"] = "1" * 64
    with pytest.raises(Exception) as error:
        generate(
            full_latex,
            information_library={
                "status": "available",
                "revision": "1" * 64,
                "preferences": {},
                "records": [
                    {
                        "key": "current-contact",
                        "question": "Email",
                        "value": "first.last@example.invalid",
                        "state": "confirmed",
                        "scope": {"application_id": job["id"]},
                    },
                ],
            },
        )
    assert error.value.code == "resume_latex_invalid"


@pytest.mark.parametrize(
    "question,old,current,protocol",
    [
        (
            "Email",
            "synthetic-person@example.invalid",
            "synthetic.person@example.invalid",
            "mailto:",
        ),
        ("Phone", "+41 79 123 45 67", "+41 67 45 123 79", "tel:"),
        (
            "LinkedIn",
            "https://www.linkedin.com/in/synthetic-person",
            "https://www.linkedin.com/in/synthetic.person",
            "",
        ),
    ],
)
@pytest.mark.parametrize("layout", ["plain", "stale-href-target"])
def test_current_contact_header_rejects_extra_unconfirmed_contact_with_the_same_words(
    full_latex, question, old, current, protocol, layout
):
    store, job, _, _, _, base, output, inputs = full_latex
    original = old + "\n"
    rewritten = old + "\n" + current + "\n"
    if layout == "stale-href-target":
        original = "\\href{" + protocol + old + "}{" + old + "}\n"
        rewritten = "\\href{" + protocol + old + "}{" + current + "}\n"
    main = base / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", original))
    output["groups"][0].update(source_ids=["answer:current-contact"], latex=rewritten)
    inputs["information_library_revision"] = "2" * 64
    from career_evidence_graph.career_portal_data import PortalDataError

    before = main.read_bytes()
    with pytest.raises(PortalDataError) as error:
        generate(
            full_latex,
            information_library={
                "status": "available",
                "revision": "2" * 64,
                "preferences": {},
                "records": [
                    {
                        "key": "current-contact",
                        "question": question,
                        "value": current,
                        "state": "confirmed",
                        "scope": {"application_id": job["id"]},
                    }
                ],
            },
        )
    assert error.value.code == "resume_latex_invalid"
    assert main.read_bytes() == before
    assert len(list(store.root.glob("*/model-result.json"))) == 1
    assert not list(store.root.glob("*/draft.json"))
    assert not list(store.root.rglob("*.pdf"))


@pytest.mark.parametrize("layout", ["full-values", "named-links"])
@pytest.mark.parametrize("slug", ["synthetic.person", "synthetic%20person"])
def test_current_header_keeps_multiple_contacts_and_bound_link_targets(full_latex, layout, slug):
    store, job, _, _, _, base, output, inputs = full_latex
    url = "https://www.linkedin.com/in/" + slug
    latex_url = url.replace("%", r"\%")
    old = (
        "\\href{mailto:synthetic-person@example.invalid}{synthetic-person@example.invalid}"
        " \\href{tel:+41791234567}{+41 79 123 45 67}"
        " \\url{" + latex_url + "}\n"
    )
    current = old.replace("synthetic-person@example.invalid", "synthetic.person@example.invalid")
    if layout == "named-links":
        current = (
            "\\href{mailto:synthetic.person@example.invalid}{Email}"
            " \\href{tel:+41791234567}{Phone}"
            " \\url{" + latex_url + "}\n"
        )
    main = base / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", old))
    output["groups"][0].update(
        source_ids=["answer:email", "answer:phone", "answer:linkedin"], latex=current
    )
    inputs["information_library_revision"] = "3" * 64
    result = generate(
        full_latex,
        information_library={
            "status": "available",
            "revision": "3" * 64,
            "preferences": {},
            "records": [
                {
                    "key": key,
                    "question": question,
                    "value": value,
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                }
                for key, question, value in [
                    ("email", "Email", "synthetic.person@example.invalid"),
                    ("phone", "Phone", "+41 79 123 45 67"),
                    ("linkedin", "LinkedIn", url),
                ]
            ],
        },
    )
    assert result["verification_queue"] == []
    assert current in result["latex_source"]
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]
    edited = store.prepare_group_review(result["id"], result["draft_sha256"], task_inputs=inputs)
    saved = store.save_automatic_source(
        edited["id"],
        edited["draft_sha256"],
        task_inputs=inputs,
        latex_source=edited["latex_source"].replace(
            "Analyzed strategy; built 6 Python services.",
            "Built 6 Python services; analyzed strategy.",
        ),
    )
    assert current in store.draft(saved["id"])["latex_source"]
    assert store.draft(result["id"])["latex_source"] == result["latex_source"]
    assert main.read_text().endswith("\\end{document}\n")
    assert old in main.read_text()


def test_full_generation_and_material_binding_share_country_contact_context(full_latex):
    from career_evidence_graph.application_flow import job_input_revision
    from career_evidence_graph.application_information import material_information_library

    store, job, _, analysis, _, base, output, inputs = full_latex
    updated = store.applications.update_application(
        job["id"], {"location": "Zurich, Switzerland"}, job["revision"]
    )
    data = list(full_latex)
    data[1] = updated
    analysis["application_revision"] = updated["revision"]
    analysis["jd_revision"] = job_input_revision(updated)
    main = base / "main.tex"
    main.write_text(main.read_text().replace("Synthetic Person\n", "old@example.invalid\n"))
    output["groups"][0].update(source_ids=["answer:swiss-email"], latex="swiss@example.invalid\n")
    library = {
        "status": "available",
        "revision": "country-source",
        "preferences": {},
        "records": [
            {
                "key": "swiss-email",
                "question": "Email",
                "value": "swiss@example.invalid",
                "state": "confirmed",
                "scope": {"country": "CHE"},
            },
        ],
    }
    material_library = material_information_library(updated, library)
    inputs["information_library_revision"] = material_library["revision"]
    result = generate(data, information_library=material_library)
    assert "swiss@example.invalid" in result["latex_source"]
    assert result["verification_queue"] == []
    assert result["information_library_revision"] == material_library["revision"]


@pytest.mark.parametrize("change", [None, "title", "summary", "work", "base", "span"])
def test_accepted_header_is_fixed_identity_with_exact_retained_provenance(full_latex, change):
    from test_application_source_reuse import _write_retained_fixture

    store, _, _, analysis, _, project, output, inputs = full_latex
    header = (
        "Synthetic Person | Statistics PhD candidate | Expected July 2028\n"
        "Research interests: systematic quantitative methods.\n"
        "\\href{https://portfolio.example.invalid/}{Portfolio}\n"
    )
    main = project / "main.tex"
    original = main.read_text().replace("Synthetic Person\n", header)
    main.write_text(original)
    _write_retained_fixture(
        store.catalog.root,
        source_text=original,
        groups=[
            {
                "title": "Accepted header",
                "start_line": 3,
                "end_line": 5 if change != "span" else 7,
                "source_kind": "accepted_resume",
                "context_source_ids": [],
                "education_profile_locator": None,
                "education_profile_sha256": None,
            }
        ],
    )
    sources = career_source_snapshot(store.catalog)
    accepted = next(s for s in sources["retained_materials"] if s.get("retained_receipt_revision"))
    assert accepted["source_kind"] == "accepted_resume"
    data = list(full_latex)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    for group in output["groups"][1:]:
        group["start_line"] += 2
        group["end_line"] += 2
    output["groups"][0].update(end_line=3, source_ids=[accepted["source_id"]], latex=header)
    if change == "title":
        output["groups"][0]["latex"] = header.replace("PhD candidate", "PhD")
    elif change == "summary":
        output["groups"][0]["latex"] = header.replace(
            "Research interests: systematic quantitative methods.",
            "Research methods: systematic quantitative interests.",
        )
    elif change == "work":
        output["groups"][1]["source_ids"] = [accepted["source_id"]]
    elif change == "base":
        main.write_text(original.replace("{article}", "[10pt]{article}"))
    if change == "base":
        with pytest.raises(Exception, match="已接受来源与本次底稿行段不符"):
            generate(data)
        return
    result = generate(data)
    assert main.read_text() == original
    if change in {"title", "summary", "work"}:
        assert result["verification_queue"]
        assert result["verification_queue"][0]["reason"].startswith(
            "source_or_attribution_unresolved:"
        )
    elif change == "span":
        # A slice crossing into an experience is never promoted to identity.
        assert result["review_groups"][0]["sources"][0]["source_kind"] == "accepted_resume"
    else:
        assert result["verification_queue"] == []
        source = result["review_groups"][0]["sources"][0]
        assert source["source_kind"] == "identity"
        assert source["rewrite_allowed"] is False
        for key in (
            "source_id",
            "retained_receipt_revision",
            "retained_source_sha256",
            "retained_text_sha256",
            "retained_start_line",
            "retained_end_line",
        ):
            assert source[key] == accepted[key]
        assert json.loads(source["text"])["accepted_latex"] == header
        assert "Expected July 2028" in result["latex_source"]
        assert result["factual_review"] == "pending"


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "contact",
        "manual_work",
        "manual_header",
        "split_none",
        "split_contact",
        "ambiguous_name",
    ],
)
def test_accepted_header_continuation_preserves_lineage_contacts_and_manual_edits(
    full_latex, change
):
    from test_application_source_reuse import _write_retained_fixture

    store, job, _, analysis, _, project, output, inputs = full_latex
    profile_path = store.catalog.root / "sources/profile.json"
    profile = json.loads(profile_path.read_text())
    profile["links"] = [{"label": "Email", "href": "mailto:old@example.invalid"}]
    if change == "ambiguous_name":
        profile["name"] = "Jane"
    profile_path.write_text(json.dumps(profile))
    header = (
        "Synthetic Person | Statistics PhD candidate | Expected July 2028\n"
        "Research interests: systematic quantitative methods.\n"
        "old@example.invalid\n"
    )
    if change == "ambiguous_name":
        header = header.replace("Synthetic Person", "Jane").replace(
            "Research interests: systematic quantitative methods.",
            "Research interests: models at Jane Street.",
        )
    main = project / "main.tex"
    original = main.read_text().replace("Synthetic Person\n", header)
    main.write_text(original)
    _write_retained_fixture(
        store.catalog.root,
        source_text=original,
        groups=[
            {
                "title": "Accepted header",
                "start_line": 3,
                "end_line": 5,
                "source_kind": "accepted_resume",
                "context_source_ids": [],
                "education_profile_locator": None,
                "education_profile_sha256": None,
            }
        ],
    )
    split = change.startswith("split_")
    if split:
        manifest_path = store.catalog.root / "sources/retained-resume-sources.json"
        manifest = json.loads(manifest_path.read_text())
        contact = dict(manifest["groups"][0], title="Accepted contact", start_line=5, end_line=5)
        manifest["groups"][0]["end_line"] = 4
        manifest["groups"].append(contact)
        manifest_path.write_text(json.dumps(manifest))
    sources = career_source_snapshot(store.catalog)
    accepted = next(s for s in sources["retained_materials"] if s.get("retained_receipt_revision"))
    data = list(full_latex)
    data[2] = sources
    analysis["source_snapshot_revision"] = inputs["sources_revision"] = sources["revision"]
    for group in output["groups"][1:]:
        group["start_line"] += 2
        group["end_line"] += 2
    output["groups"][0].update(end_line=3, source_ids=[accepted["source_id"]], latex=header)
    if split:
        output["groups"][0].update(end_line=2, latex="".join(header.splitlines(keepends=True)[:2]))
        second = next(s for s in sources["retained_materials"] if s.get("locator") == "groups[1]")
        output["groups"].insert(
            1,
            {
                "title": "Contact",
                "start_line": 3,
                "end_line": 3,
                "source_ids": [second["source_id"]],
                "latex": "old@example.invalid\n",
                "disposition": "include",
                "reason": "Fixed accepted contact",
            },
        )
    first = generate(data)
    retained = first
    if change.startswith("manual"):
        editable = store.prepare_group_review(
            first["id"], first["draft_sha256"], task_inputs=inputs
        )
        text = editable["latex_source"]
        if change == "manual_work":
            text = text.replace(
                "Analyzed strategy; built 6 Python services.",
                "Built 6 Python services; analyzed strategy.",
            )
        else:
            text = text.replace("Research interests:", "Research methods:")
            # An external editor's unverified change must stay on disk when
            # continuation rejects its mismatch with the saved checkpoint.
            manual_path = Path(editable["source_checkpoint"]["project_root"]) / "main.tex"
            manual_path.write_text(text)
            with pytest.raises(Exception) as caught:
                store.generate_for_task(
                    job["id"],
                    job["revision"],
                    source_snapshot=sources,
                    analysis=analysis,
                    draft_only=True,
                    task_inputs=inputs,
                    latex_base=source_snapshot(
                        manual_path.parent, "main.tex", source_policy="generated-latex-project/v1"
                    ),
                    retained_draft=editable,
                )
            assert caught.value.code == "resume_latex_invalid"
            assert manual_path.read_text() == text
            assert store.draft(first["id"])["latex_source"] == first["latex_source"]
            return
        retained = store.save_automatic_source(
            editable["id"], editable["draft_sha256"], task_inputs=inputs, latex_source=text
        )
    library = None
    if change in {"contact", "split_contact"}:
        library = {
            "status": "available",
            "revision": "a" * 64,
            "records": [
                {
                    "key": "email",
                    "question": "Email",
                    "value": "new@example.invalid",
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                }
            ],
        }
        inputs = inputs | {"information_library_revision": library["revision"]}
    if change == "ambiguous_name":
        library = {
            "status": "available",
            "revision": "b" * 64,
            "records": [
                {
                    "key": "name",
                    "question": "Full name",
                    "value": "Jane Smith",
                    "state": "confirmed",
                    "scope": {"application_id": job["id"]},
                }
            ],
        }
        inputs = inputs | {"information_library_revision": library["revision"]}
        with pytest.raises(Exception, match="姓名在页眉中没有唯一可核验位置"):
            store.generate_for_task(
                job["id"],
                job["revision"],
                source_snapshot=sources,
                analysis=analysis,
                draft_only=True,
                task_inputs=inputs,
                latex_base=retained["source_checkpoint"],
                retained_draft=retained,
                information_library=library,
            )
        assert store.draft(first["id"])["latex_source"] == first["latex_source"]
        return
    result = store.generate_for_task(
        job["id"],
        job["revision"],
        source_snapshot=sources,
        analysis=analysis,
        draft_only=True,
        task_inputs=inputs,
        latex_base=retained["source_checkpoint"],
        retained_draft=retained,
        information_library=library,
    )
    assert not result["verification_queue"]
    assert result["review_groups"][0]["sources"][0]["source_kind"] == "identity"
    assert store.draft(first["id"])["latex_source"] == first["latex_source"]
    if change in {"contact", "split_contact"}:
        assert "new@example.invalid" in result["latex_source"]
        assert "old@example.invalid" not in result["latex_source"]
        assert "Research interests: systematic quantitative methods." in result["latex_source"]
    elif change == "manual_work":
        assert "Built 6 Python services; analyzed strategy." in result["latex_source"]
    else:
        assert result["latex_source"] == first["latex_source"]


def test_accepted_header_identity_guard_cannot_rewrite_a_repeated_name_in_summary():
    from career_evidence_graph.application_full_latex import _identity_matches

    header = "Jane | Statistics PhD candidate\nResearch interests: models at Jane Street.\n"
    sources = [
        {
            "source_kind": "identity",
            "retained_receipt_revision": "a" * 64,
            "retained_start_line": 3,
            "retained_text_sha256": hashlib.sha256(header.encode()).hexdigest(),
            "text": json.dumps(
                {"accepted_latex": header, "accepted_contact_facts": {"name": "Jane"}}
            ),
        },
        {"source_kind": "identity", "text": json.dumps({"name": "Jane Smith"})},
    ]
    with pytest.raises(Exception, match="姓名在页眉中没有唯一可核验位置"):
        _identity_matches(header.replace("Jane", "Jane Smith"), sources)
