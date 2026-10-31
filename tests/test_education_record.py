"""The Education Record is the one education source for matching and qualification."""

import pytest
from test_career_experiences import library as library
from test_structured_career_library import content

from career_evidence_graph.application_information import (
    information_source_snapshot,
    with_education,
)
from career_evidence_graph.career_education import (
    EducationStore,
    education_answers,
    education_profile,
    education_text,
)
from career_evidence_graph.career_experiences import ExperienceStore
from career_evidence_graph.career_portal_data import PortalDataError

RECORDS = [
    {
        "id": "doctorate",
        "level": "doctorate",
        "degree": "Ph.D. in Mathematics",
        "field": "Mathematics",
        "institution": "Synthetic University",
        "start": "2023-02",
        "end": "2027-07",
        "status": "in_progress",
        "details": ["Research in dynamics."],
        "sources": [{"id": "profile-0", "locator": "sources/profile.json#education[0]"}],
    },
    {
        "id": "master",
        "level": "master",
        "degree": "M2 in Fundamental Mathematics",
        "field": "Fundamental Mathematics",
        "institution": "Synthetic Institute",
        "start": "2021-09",
        "end": "2022-06",
        "status": "awarded",
        "details": [],
        "sources": [{"id": "profile-1", "locator": "sources/profile.json#education[1]"}],
    },
]


def test_records_save_with_revision_check_and_immutable_history(tmp_path):
    store = EducationStore(tmp_path)
    assert store.read() is None
    first = store.save(RECORDS, expected_revision=None, actor="user")
    assert store.read() == first
    with pytest.raises(PortalDataError):
        store.save(RECORDS[:1], expected_revision=None, actor="user")
    second = store.save(RECORDS[:1], expected_revision=first["revision"], actor="user")
    history = sorted(path.name for path in (tmp_path / ".tomorrowstar-education/history").iterdir())
    assert history == sorted([first["revision"] + ".json", second["revision"] + ".json"])
    with pytest.raises(PortalDataError):
        store.save(
            [RECORDS[0] | {"status": "graduated"}],
            expected_revision=second["revision"],
            actor="user",
        )


def test_derived_values_keep_the_earlier_answer_and_profile_shapes(tmp_path):
    collection = EducationStore(tmp_path).save(RECORDS, expected_revision=None, actor="user")
    assert education_answers(collection) == {
        "academic_degree": "PhD (in progress; expected graduation July 2027)",
        "graduation_date": "07/2027",
    }
    assert [row["period"] for row in education_profile(collection)["education"]] == [
        "Feb 2023 - Expected Jul 2027",
        "Sep 2021 - Jun 2022",
    ]
    assert education_text(collection["records"][1]) == (
        "M2 in Fundamental Mathematics, Synthetic Institute, 2021-09 to 2022-06 (awarded)."
    )
    stored = {
        "status": "available",
        "revision": "answers",
        "records": [
            {
                "key": "a",
                "question": "Current Academic Degree",
                "value": "old",
                "state": "confirmed",
                "scope": {},
            },
            {
                "key": "b",
                "question": "Full-time availability after graduation",
                "value": "July 2027",
                "state": "confirmed",
                "scope": {},
            },
        ],
        "preferences": {},
    }
    library = with_education(stored, collection)
    assert {row["key"]: row["value"] for row in library["records"]} == {
        "b": "July 2027",
        "education.academic_degree": "PhD (in progress; expected graduation July 2027)",
        "education.graduation_date": "07/2027",
    }
    assert library["revision"] != stored["revision"]


def test_matching_sees_each_degree_once_and_no_other_education_copy(tmp_path):
    collection = EducationStore(tmp_path).save(RECORDS, expected_revision=None, actor="user")
    base = {
        "documents": [],
        "items": [{"source_id": "old", "source_kind": "education", "text": "M2 study"}],
        "profile": {
            "education": [{"degree": "M2", "institution": "x", "period": "", "detail": ""}]
        },
    }
    library = with_education({"status": "unconfigured", "records": []}, collection)
    snapshot = information_source_snapshot({"id": "job"}, library, base)
    assert snapshot["profile"]["education"] == []
    assert [item["source_id"] for item in snapshot["items"]] == [
        "education-record:doctorate",
        "education-record:master",
    ]
    assert all(not item["resume_eligible"] for item in snapshot["items"])


def test_education_experiences_retire_once_the_record_exists(library):
    adapter, root, _, _, _ = library
    ExperienceStore(root).save("alpha", title="Reviewed research", content=content())
    ExperienceStore(root).save(
        "beta",
        title="Teaching",
        content=content("beta") | {"title": "Teaching"},
        metadata={"category": "education"},
    )
    ids = lambda: {row["candidate_id"] for row in adapter.index()["records"]}  # noqa: E731
    assert ids() == {"alpha", "beta"}
    adapter.save_education(RECORDS, expected_revision=None)
    assert ids() == {"alpha"}
    items = adapter.snapshot_for_analysis({"documents": [], "items": []}, ["alpha", "beta"])
    assert {item["candidate_id"] for item in items["items"]} == {"alpha"}


def test_confirmed_answers_still_validate_beside_education_items(tmp_path):
    from test_application_information import answer, library_with

    from career_evidence_graph.application_information import validate_information_source

    collection = EducationStore(tmp_path).save(RECORDS, expected_revision=None, actor="user")
    library = with_education(library_with(answer("English fluency", "professional")), collection)
    snapshot = information_source_snapshot({"id": "job"}, library, {"documents": [], "items": []})
    confirmed = next(i for i in snapshot["items"] if i["source_kind"] == "confirmed_information")
    # Installed MC-11: rebinding an answer crashed on the education items beside it.
    assert validate_information_source({"id": "job"}, library, confirmed)
