"""Saved, scoped applicant facts update current qualification without rewriting history."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from test_application_information import answer, library_with
from test_career_portal_http import portal as portal
from test_job_explanations import job_and_task, requirement

from career_evidence_graph.application_explanations import job_explanation
from career_evidence_graph.application_flow import job_input_revision
from career_evidence_graph.application_information import condition_from_library

STUDENT = "Be a penultimate or final-year student pursuing a master's or PhD degree."
INTERNSHIP = (
    "Be available for a 3-5 month internship starting in 2027 at an eligible Example location."
)
FACTS = {
    "Current Academic Degree": "PhD (in progress; expected graduation June 2028)",
    "Graduation Date (MM/YYYY)": "06/2028",
    "Internship Start Date (MM/YYYY)": "03/2027",
    "Internship Duration": "5 months",
    "First Preferred Location": "Lakeside",
}


@pytest.fixture(autouse=True)
def qualification_reference_month(monkeypatch):
    class ReferenceDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 10, 23, 12, tzinfo=UTC)
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr("career_evidence_graph.application_information.datetime", ReferenceDatetime)


def example_case(*texts, location="Lakeside, Switzerland"):
    application, task = job_and_task(
        [
            requirement(text, judgment="unknown", hard=True)
            for text in texts or (STUDENT, INTERNSHIP)
        ]
    )
    application.update(
        {
            "id": "synthetic-example-job",
            "company": "Example Quant Firm",
            "location": location,
            "country": "CHE",
            "job_description": "2027 Quantitative Research internship. " + " ".join(texts),
        }
    )
    task.update(
        {
            "application_id": application["id"],
            "job_binding": job_input_revision(application),
            "status": "materials_ready",
            "draft_id": "saved-draft",
            "resume_id": "saved-final-pdf",
            "codex_handoff_ref": {
                "task_id": "existing-upload",
                "status": "ready_for_review",
                "filename": "Synthetic_Example_CV.pdf",
            },
            "manual_edits": {"retained": "User-edited wording."},
            "history": [{"event": "uploaded", "receipt": "already-saved"}],
        }
    )
    task["artifacts"].append(
        {"stage": "export", "adopted": True, "result": {"id": "saved-final-pdf", "sha": "saved"}}
    )
    return application, task


def saved_facts(*, scope=None, state="confirmed", overrides=None, omit=()):
    values = FACTS | (overrides or {})
    return library_with(
        *(
            answer(question, value, scope=scope, state=state)
            for question, value in values.items()
            if question not in omit
        )
    )


def explain(application, task, library):
    return job_explanation(application, task, current_inputs=task["inputs"], library=library)


def test_confirmed_student_and_internship_facts_project_without_rewriting_saved_materials():
    application, task = example_case()
    library = saved_facts()
    before = deepcopy((application, task, library))
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "supported"
    assert all(row["status"] == "supported" for row in result["qualification"]["conditions"])
    assert result["score"]["lower"] == result["score"]["upper"] == 100
    assert result["score"]["coverage"] == 100
    assert result["documentary_score"]["lower"] == 0
    assert result["documentary_score"]["upper"] == 100
    assert result["documentary_score"]["coverage"] == 0
    for row in result["reasons"]:
        assert row["judgment"] == "supported"
        assert row["documentary_judgment"] == "unknown"
        assert row["library"]["references"]
    assert result["fresh"] and result["materials_fresh"]
    assert (application, task, library) == before


@pytest.mark.parametrize("text", [STUDENT, INTERNSHIP])
@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"company": "Example Quant Firm"},
        {"country": "CHE"},
        {"application_id": "synthetic-example-job"},
    ],
)
def test_confirmed_facts_reuse_only_within_their_applicable_scope(text, scope):
    application, task = example_case(text)
    library = saved_facts(scope=scope)
    before = deepcopy(library)
    result = condition_from_library({"text": text, "hard_condition": True}, application, library)
    assert result and result["status"] == "supported"
    assert result["references"]
    assert library == before
    assert explain(application, task, library)["score"]["lower"] == 100


@pytest.mark.parametrize("text", [STUDENT, INTERNSHIP])
@pytest.mark.parametrize(
    "scope",
    [
        {"company": "Other Employer"},
        {"country": "GBR"},
        {"application_id": "another-job"},
    ],
)
def test_other_company_country_or_job_facts_do_not_support_this_job(text, scope):
    application, task = example_case(text)
    library = saved_facts(scope=scope)
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "needs_input"
    assert result["score"]["lower"] == 0


@pytest.mark.parametrize("text", [STUDENT, INTERNSHIP])
@pytest.mark.parametrize("state", ["inferred", "sensitive", "missing"])
def test_unconfirmed_or_withdrawn_facts_never_support_current_qualification(text, state):
    application, task = example_case(text)
    result = explain(application, task, saved_facts(state=state))
    assert result["qualification"]["status"] == "needs_input"
    assert result["score"]["lower"] == 0


@pytest.mark.parametrize(
    ("text", "question"),
    [
        (STUDENT, "Current Academic Degree"),
        (STUDENT, "Graduation Date (MM/YYYY)"),
        (INTERNSHIP, "Internship Start Date (MM/YYYY)"),
        (INTERNSHIP, "Internship Duration"),
        (INTERNSHIP, "First Preferred Location"),
    ],
)
def test_missing_component_is_not_inferred_from_other_confirmed_facts(text, question):
    application, task = example_case(text)
    result = explain(application, task, saved_facts(omit=(question,)))
    assert result["qualification"]["status"] == "needs_input"
    assert result["score"]["lower"] == 0


@pytest.mark.parametrize(
    ("text", "question", "other"),
    [
        (STUDENT, "Graduation Date (MM/YYYY)", "06/2030"),
        (INTERNSHIP, "Internship Duration", "2 months"),
    ],
)
def test_conflicting_applicable_answers_need_reconciliation(text, question, other):
    application, task = example_case(text)
    library = saved_facts(scope={"company": application["company"]})
    library["records"].append(answer(question, other, scope={"country": "CHE"})[1])
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "needs_input"
    assert result["score"]["lower"] == 0


def test_visa_and_privacy_permission_do_not_become_general_qualifications():
    application, task = example_case("Be fluent in English.", "Hold applicable work authorization.")
    scope = {"application_id": application["id"]}
    library = saved_facts()
    library["records"].extend(
        [
            answer("Do you require visa sponsorship?", "No", scope=scope)[1],
            answer("Employer privacy consent", True, scope=scope)[1],
            answer("English proficiency", "Fluent", scope={"company": "Other Example Co"})[1],
        ]
    )
    before = deepcopy(library)
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "needs_input"
    assert result["score"]["lower"] == 0
    assert library == before


ADVANCED_DEGREE = (
    "Pursue an advanced degree in a quantitative field such as statistics, physics, "
    "or computer science."
)
EDUCATION_PROFILE = {
    "education": [
        {
            "degree": "Ph.D. candidate in Statistics",
            "institution": "Example University",
            "detail": "",
            "period": "Sep 2023 - Expected Jun 2028",
        }
    ],
    "source": {
        "id": "profile-source",
        "revision": "profile-v1",
        "source_name": "sources/profile.json",
        "locator": "profile",
    },
}


def test_advanced_quantitative_degree_reuses_canonical_education_and_confirmed_status():
    application, task = example_case(ADVANCED_DEGREE)
    library = saved_facts() | {"education_profile": deepcopy(EDUCATION_PROFILE)}
    before = deepcopy((task, library))
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "supported"
    assert result["score"]["lower"] == 100
    assert result["documentary_score"]["lower"] == 0
    references = result["reasons"][0]["library"]["references"]
    assert any(row.get("source_name") == "sources/profile.json" for row in references)
    assert (task, library) == before


@pytest.mark.parametrize(
    "profile",
    [
        None,
        {"education": [], "source": {}},
        {
            "education": [{"degree": "Ph.D. candidate in Music", "period": "2023 - 2027"}],
            "source": EDUCATION_PROFILE["source"],
        },
    ],
)
def test_missing_or_mismatched_education_field_does_not_claim_quantitative_degree(profile):
    application, task = example_case(ADVANCED_DEGREE)
    library = saved_facts()
    if profile is not None:
        library["education_profile"] = profile
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "needs_input"
    assert result["score"]["lower"] == 0


def test_job_scoped_withdrawal_does_not_fall_back_to_global_confirmed_degree():
    application, task = example_case(STUDENT)
    library = saved_facts()
    library["records"].append(
        answer(
            "Current Academic Degree",
            None,
            scope={"application_id": application["id"]},
            state="missing",
        )[1]
    )
    result = explain(application, task, library)
    assert result["qualification"]["status"] == "needs_input"
    assert result["score"]["lower"] == 0


def test_new_confirmed_references_do_not_repair_old_invalid_documentary_citations():
    application, task = example_case(STUDENT, INTERNSHIP)
    report = task["artifacts"][0]["result"]
    for row in report["requirements"]:
        row["citation_warning"] = "match_source_invalid"
        row["sources"] = []
    report["requirements"].append(
        requirement("Advanced C++ execution systems", judgment="unknown")
        | {"citation_warning": "match_source_invalid", "sources": []}
    )
    before = deepcopy(task)
    result = explain(application, task, saved_facts())
    assert result["qualification"]["status"] == "supported"
    assert [row["judgment"] for row in result["reasons"]] == ["supported", "supported", "unknown"]
    assert result["documentary_score"]["lower"] == 0
    assert all(row["library"]["references"] for row in result["reasons"][:2])
    assert task == before


def test_http_snapshot_reads_saved_facts_live_without_mutating_existing_flow_or_pdf(
    portal, tmp_path
):
    import json
    from types import SimpleNamespace

    from test_application_flow import wait_for
    from test_application_information import tree_bytes, write_library
    from test_job_explanation_browser import explanation_portal
    from test_pdf_export_http import SyntheticLatexClient
    from test_preparation_entry import snapshot

    from career_evidence_graph.career_portal_data import ApplicationStore

    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Example Quant Firm",
            "role_title": "2027 Research Internship",
            "location": "Lakeside, Switzerland",
            "job_description": " ".join([STUDENT, INTERNSHIP, ADVANCED_DEGREE]),
        }
    )
    library_root = tmp_path / "information"
    answers = dict(answer(question, value) for question, value in FACTS.items())
    write_library(library_root, answers=answers)
    hard_requirements = [
        {
            "text": text,
            "importance": "required",
            "judgment": "unknown",
            "hard_condition": True,
            "explanation": "The retained documentary citation was not verified.",
            "source_ids": [],
            "citations": [],
            "claim_scope": "unknown",
        }
        for text in (STUDENT, INTERNSHIP, ADVANCED_DEGREE)
    ]
    with explanation_portal(
        portal,
        tmp_path,
        extra_requirements={job["company"]: hard_requirements},
        information_library_root=library_root,
    ) as (instance, work):
        (portal.career / "sources/profile.json").write_text(
            json.dumps(
                {
                    "name": "Synthetic Person",
                    "education": EDUCATION_PROFILE["education"],
                }
            )
        )
        service = instance.server.application_flow_service
        store = instance.server.application_resume_store
        project = tmp_path / "qualification-latex"
        project.mkdir()
        (project / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nSynthetic Person\n"
            "\\section*{Experience}\nImplemented a Python service.\n\\end{document}\n"
        )

        def generate_model(config, prompt, **kwargs):
            payload = json.loads(prompt[prompt.index("{") :])
            work["calls"].append(payload)
            identity = next(s for s in payload["sources"] if s.get("source_kind") == "identity")
            work_source = next(
                s
                for s in payload["sources"]
                if s["source_id"] in payload["analysis_selected_source_ids"]
            )
            return SimpleNamespace(
                structured_result={
                    "groups": [
                        {
                            "title": "Identity",
                            "start_line": 1,
                            "end_line": 1,
                            "source_ids": [identity["source_id"]],
                            "latex": "Synthetic Person\n",
                            "disposition": "include",
                            "reason": "Preserve fixed identity",
                        },
                        {
                            "title": "Experience",
                            "start_line": 2,
                            "end_line": 3,
                            "source_ids": [work_source["source_id"]],
                            "latex": "\\section*{Experience}\nImplemented a Python service.\n",
                            "disposition": "include",
                            "reason": "Preserve documented service work",
                        },
                    ],
                    "limitations": [],
                },
                model_dump=lambda **kwargs: {"synthetic": True},
            )

        store.model_runner = generate_model
        store.prism_client = SyntheticLatexClient(
            on_compile=lambda: work["exports"].append("latex-compile")
        )
        task = service.create(job["id"], job["revision"])
        # Replay saved pre-JSON materials. This regression tests live qualification
        # readback without changing the historical task, draft or PDF.
        with service.applications.write_lock():
            state = service._load()
            service._task(state, task["id"]).pop("material_contract", None)
            service._save(state)
        task = service.snapshot(task["id"])["active_task"]
        service.start(task["id"], task["revision"], "analysis")
        task = wait_for(service, task["id"], lambda row: row["status"] == "analysis_ready")
        task = service.prepare_automatic_materials(
            task["id"], task["revision"], str(project), "main.tex"
        )
        service.start(task["id"], task["revision"], "resume")
        task = wait_for(service, task["id"], lambda row: row["status"] in {"draft_ready", "failed"})
        assert task["status"] == "draft_ready", task
        service.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
        task = wait_for(
            service,
            task["id"],
            lambda row: row["status"] in {"materials_ready", "export_failed", "needs_recheck"},
        )
        assert task["status"] == "materials_ready", task
        assert task["origin"] == "generated_latex"
        assert task["factual_review"] == "pending"
        assert not list(store.root.rglob("*.html"))
        before = tree_bytes(service.root)
        first = snapshot(instance)["active_explanation"]
        assert first["qualification"]["status"] == "supported"
        assert first["score"]["lower"] == 100
        assert first["documentary_score"]["lower"] == 25
        advanced = next(row for row in first["reasons"] if row["text"] == ADVANCED_DEGREE)
        assert any(
            ref.get("source_name") == "sources/profile.json"
            for ref in advanced["library"]["references"]
        )
        calls, exports = len(work["calls"]), len(work["exports"])
        key = answer("Internship Duration", "5 months")[0]
        answers[key]["value"] = "2 months"
        (library_root / "answers.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "answers": answers,
                    "metadata": {},
                }
            )
        )
        current = snapshot(instance)["active_explanation"]
        assert current["qualification"]["status"] != "supported"
        assert current["score"]["lower"] < first["score"]["lower"]
        assert current["documentary_score"] == first["documentary_score"]
        assert current["input_binding"] == first["input_binding"]
        assert tree_bytes(service.root) == before
        assert service.snapshot()["active_task"]["resume_id"] == task["resume_id"]
        assert len(work["calls"]) == calls and len(work["exports"]) == exports


def test_internship_location_must_appear_in_the_job_location():
    # The rule is employer-agnostic: eligibility comes from this job's own location field.
    application, task = example_case(INTERNSHIP, location="Hillside, Switzerland")
    result = condition_from_library(
        {"text": INTERNSHIP, "hard_condition": True}, application, saved_facts()
    )
    assert result and result["status"] == "needs_input"


@pytest.mark.parametrize(
    ("text", "duration", "status"),
    [
        ("Be available for a 6 month internship starting in 2027.", "6 months", "supported"),
        ("Be available for a 6 month internship starting in 2027.", "5 months", "needs_input"),
        ("Be available for a 3-5 month internship starting in 2028.", "5 months", "needs_input"),
    ],
)
def test_internship_duration_and_year_come_from_the_requirement(text, duration, status):
    application, task = example_case(text)
    library = saved_facts(overrides={"Internship Duration": duration})
    result = condition_from_library({"text": text, "hard_condition": True}, application, library)
    assert result and result["status"] == status


def test_quantitative_field_comes_from_the_requirement_list():
    text = "Pursue an advanced degree in a quantitative field such as physics or engineering."
    application, task = example_case(text)
    library = saved_facts() | {"education_profile": deepcopy(EDUCATION_PROFILE)}
    result = condition_from_library({"text": text, "hard_condition": True}, application, library)
    assert result and result["status"] == "needs_input"


@pytest.mark.parametrize(
    "text",
    [
        "Be a final-year student completing a bachelor's degree.",
        "Be a final-year student pursuing an undergraduate degree.",
    ],
)
def test_student_rule_does_not_judge_non_doctoral_requirements(text):
    application, task = example_case(text)
    library = saved_facts()
    assert (
        condition_from_library({"text": text, "hard_condition": True}, application, library) is None
    )


@pytest.mark.parametrize(
    ("text", "graduation", "status"),
    [
        ("Be a final-year student pursuing a PhD degree.", "06/2028", "needs_input"),
        ("Be a final-year student pursuing a Ph.D. degree.", "05/2027", "supported"),
        ("Be a penultimate or final-year student pursuing a Ph.D. degree.", "06/2028", "supported"),
    ],
)
def test_final_year_allows_one_year_and_penultimate_allows_two(text, graduation, status):
    month, year = graduation.split("/")
    names = {"05": "May", "06": "June"}
    library = saved_facts(
        overrides={
            "Graduation Date (MM/YYYY)": graduation,
            "Current Academic Degree": (
                f"PhD (in progress; expected graduation {names[month]} {year})"
            ),
        }
    )
    application, task = example_case(text)
    result = condition_from_library({"text": text, "hard_condition": True}, application, library)
    assert result and result["status"] == status


@pytest.mark.parametrize(
    ("fields", "degree"),
    [
        ("cs, statistics, or mathematics", "Ph.D. candidate in Politics"),
        ("statistics", "Ph.D. candidate in Music (minor: Statistics)"),
        ("mathematics", "Ph.D. candidate in History of Mathematics"),
    ],
)
def test_quantitative_field_must_be_the_degree_field_not_a_substring(fields, degree):
    text = f"Pursue an advanced degree in a quantitative field such as {fields}."
    application, task = example_case(text)
    profile = deepcopy(EDUCATION_PROFILE)
    profile["education"][0]["degree"] = degree
    library = saved_facts() | {"education_profile": profile}
    result = condition_from_library({"text": text, "hard_condition": True}, application, library)
    assert result and result["status"] == "needs_input"


@pytest.mark.parametrize(
    ("preferred", "location"), [("York", "New York, NY"), ("Rome", "Romeoville, IL")]
)
def test_internship_location_must_match_a_whole_location_part(preferred, location):
    application, task = example_case(INTERNSHIP, location=location)
    library = saved_facts(overrides={"First Preferred Location": preferred})
    result = condition_from_library(
        {"text": INTERNSHIP, "hard_condition": True}, application, library
    )
    assert result and result["status"] == "needs_input"
