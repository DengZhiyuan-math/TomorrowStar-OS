"""Application trust accepts library facts without changing their content or provenance."""

from copy import deepcopy

import pytest

from career_evidence_graph.application_full_latex import (
    BUSINESS_FIRST_INSTRUCTIONS,
    _application_rewrite_allowed,
    _application_usable,
    _plan,
)
from career_evidence_graph.career_portal_data import PortalDataError


def plan(source, *, rewritten=None):
    original = "\\section*{Research internship}\nPlanned neural research with a team.\n"
    output = {
        "groups": [
            {
                "title": "Research internship",
                "start_line": 1,
                "end_line": 2,
                "source_ids": ["library-source"],
                "latex": rewritten or original,
                "disposition": "include",
                "reason": "Relevant interdisciplinary experience from the career library",
            }
        ],
        "limitations": [],
    }
    return _plan(
        output,
        "\\documentclass{article}\n\\begin{document}\n" + original + "\\end{document}\n",
        [source],
    )


def source(**updates):
    return {
        "source_id": "library-source",
        "source_kind": "career_library",
        "title": "Research internship",
        "text": "Planned neural research with a team.",
        "source_revision": "a" * 64,
        "attribution": "Editorial statement; review required",
        "review_status": "not-audited",
        "resume_eligible": False,
        "rewrite_allowed": False,
        **updates,
    }


@pytest.mark.parametrize(
    "attribution", ["Unknown", "Editorial statement; review required", "User self-report"]
)
def test_trusted_library_bypasses_research_review_only(attribution):
    record = source(application_trusted=True, attribution=attribution)
    before = deepcopy(record)
    result = plan(
        record,
        rewritten="\\section*{Research internship}\nPlanned team research in neural systems.\n",
    )
    group = result["review_groups"][0]
    assert group["disposition"] == "include"
    assert group["sources"] == [before]
    assert record == before
    assert (
        group["rewritten"]
        == "\\section*{Research internship}\nPlanned team research in neural systems.\n"
    )
    assert "planned/completed status" in BUSINESS_FIRST_INSTRUCTIONS
    assert "downgrade self-reported proficiency" in BUSINESS_FIRST_INSTRUCTIONS


def test_legacy_untrusted_source_keeps_existing_gate():
    with pytest.raises(PortalDataError, match="没有来源"):
        plan(source())


def test_trust_does_not_allow_new_dates_or_numbers():
    with pytest.raises(PortalDataError, match="没有来源"):
        plan(
            source(application_trusted=True),
            rewritten="\\section*{Research internship}\nPlanned research with 30 people in 2028.\n",
        )


def test_trust_does_not_expose_application_only_answers_or_unlock_fixed_sources():
    assert not _application_usable(
        source(application_trusted=True, source_kind="confirmed_information")
    )
    for kind in ("identity", "education", "accepted_resume"):
        assert not _application_rewrite_allowed(source(application_trusted=True, source_kind=kind))
    assert not _application_rewrite_allowed(
        source(application_trusted=True, retained_receipt_revision="receipt")
    )


def test_language_projection_uses_scoped_answers_without_certificate_gate():
    import json

    from career_evidence_graph.application_full_latex import _language_sources

    app = {"id": "job-one", "company": "Company", "location": "Zurich"}
    records = [
        {
            "key": "english",
            "question": "English proficiency CEFR",
            "value": "C2",
            "state": "confirmed",
            "scope": {},
            "source": "User report, no examination",
        },
        {
            "key": "german",
            "question": "German proficiency CEFR",
            "value": "A2",
            "state": "confirmed",
            "scope": {},
        },
        {
            "key": "visa",
            "question": "Do you require visa sponsorship?",
            "value": "No",
            "state": "confirmed",
            "scope": {"application_id": "job-one"},
        },
        {
            "key": "private",
            "question": "French proficiency CEFR",
            "value": "A1",
            "state": "confirmed",
            "scope": {"company": "Other"},
        },
    ]
    library = {"status": "available", "records": records, "revision": "library"}
    before = deepcopy(library)
    sources = _language_sources(app, library)
    assert {json.loads(row["text"])["language"] for row in sources} == {"English", "German"}
    assert {json.loads(row["text"])["proficiency"] for row in sources} == {"C2", "A2"}
    assert all(row["application_trusted"] and row["resume_eligible"] for row in sources)
    assert all(set(json.loads(row["text"])) == {"language", "proficiency"} for row in sources)
    assert library == before
    records[0]["value"] = "C1"
    assert sources[0] not in _language_sources(app, library)


def test_only_used_language_facts_are_bound_during_generation():
    from career_evidence_graph.application_experience_latex import _validate_language_sources
    from career_evidence_graph.application_full_latex import _language_sources

    app = {"id": "job-one", "company": "Company", "location": "Zurich"}
    library = {
        "status": "available",
        "records": [
            {
                "key": "english",
                "question": "English proficiency CEFR",
                "value": "C2",
                "state": "confirmed",
                "scope": {},
            },
            {
                "key": "german",
                "question": "German proficiency CEFR",
                "value": "A2",
                "state": "confirmed",
                "scope": {},
            },
        ],
    }
    sources = _language_sources(app, library)
    english = next(row for row in sources if row["title"] == "English proficiency")
    state = {
        "payload": {"analysis_selected_source_ids": [], "sources": sources},
        "groups": [{"source_ids": [english["source_id"]]}],
    }
    _validate_language_sources(state, app, library)
    library["records"][1]["value"] = "B1"
    _validate_language_sources(state, app, library)
    library["records"][0]["value"] = "C1"
    with pytest.raises(PortalDataError, match="已选语言资料已变化"):
        _validate_language_sources(state, app, library)
    assert state["payload"]["sources"] == sources


def test_public_language_projection_requires_application_library_policy():
    from career_evidence_graph.application_full_latex import _sources

    app = {"id": "job-one", "company": "Company", "location": "Zurich"}
    library = {
        "status": "available",
        "records": [
            {
                "key": "english",
                "question": "English proficiency CEFR",
                "value": "C2",
                "state": "confirmed",
                "scope": {},
            }
        ],
    }
    snapshot = {"items": [source()]}
    assert _sources(snapshot, library, app) == [source()]
    snapshot["application_library_policy"] = "trusted-library/v1"
    actual = _sources(snapshot, library, app)
    assert actual[0]["application_trusted"] is True
    assert actual[0]["text"] == snapshot["items"][0]["text"]
    assert actual[1]["source_kind"] == "language"
    assert actual[1]["application_trusted"] is True
    assert "application_trusted" not in snapshot["items"][0]
