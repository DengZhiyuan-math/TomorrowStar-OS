"""Completed JD-only interpretation remains reusable across fresh source analyses."""

import json
import os

import pytest
from test_application_job_brief import application as application
from test_application_job_brief import output as output
from test_application_job_brief import runner_for

from career_evidence_graph import application_job_brief
from career_evidence_graph.career_portal_data import PortalDataError


def test_legacy_brief_without_progress_is_found_without_writing_or_calling_again(
    tmp_path, application, output
):
    root = tmp_path / "analyses"
    original = root / "legacy" / "job-brief"
    calls = []
    expected = application_job_brief.create_job_brief(
        application, original, runner=runner_for(output, calls)
    )
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*.json")}
    assert not (original.parent / "analysis-progress.json").exists()

    assert application_job_brief.find_saved_job_brief(application, root) == (
        expected,
        original / "job-brief.json",
    )
    assert len(calls) == 1
    assert {path.relative_to(root): path.read_bytes() for path in root.rglob("*.json")} == before


def test_tampered_job_fields_do_not_hide_a_corrupt_matching_artifact(tmp_path, application, output):
    root = tmp_path / "analyses"
    directory = root / "legacy" / "job-brief"
    value = application_job_brief.create_job_brief(
        application, directory, runner=runner_for(output)
    )
    value["job"]["company"] = "Tampered employer"
    (directory / "job-brief.json").write_text(json.dumps(value))

    with pytest.raises(PortalDataError) as caught:
        application_job_brief.find_saved_job_brief(application, root)
    assert caught.value.code == "job_brief_invalid"


@pytest.mark.parametrize("malformed", ["{", "[" * 10000 + "]" * 10000], ids=["truncated", "nested"])
def test_unrelated_malformed_brief_does_not_hide_a_completed_matching_job(
    tmp_path, application, output, malformed
):
    root = tmp_path / "analyses"
    matching = root / "matching" / "job-brief"
    expected = application_job_brief.create_job_brief(
        application, matching, runner=runner_for(output)
    )
    unrelated = root / "unrelated" / "job-brief"
    application_job_brief.create_job_brief(
        application | {"company": "Another employer"}, unrelated, runner=runner_for(output)
    )
    (unrelated / "job-brief.json").write_text(malformed)
    os.utime(matching / "job-brief.json", ns=(1, 1))

    assert application_job_brief.find_saved_job_brief(application, root) == (
        expected,
        matching / "job-brief.json",
    )


@pytest.mark.parametrize("damage", ["hash", "schema", "malformed", "empty"])
def test_matching_damaged_brief_is_an_explicit_error(tmp_path, application, output, damage):
    root = tmp_path / "analyses"
    directory = root / "matching" / "job-brief"
    value = application_job_brief.create_job_brief(
        application, directory, runner=runner_for(output)
    )
    if damage == "hash":
        value["revision"] = "damaged"
    elif damage == "schema":
        value["schema_version"] = "obsolete"
    else:
        value = {} if damage == "empty" else None
    (directory / "job-brief.json").write_text("{" if value is None else json.dumps(value))

    with pytest.raises(PortalDataError) as caught:
        application_job_brief.find_saved_job_brief(application, root)
    assert caught.value.code == "job_brief_invalid"


def test_changed_job_is_not_adopted_and_newest_exact_job_wins(tmp_path, application, output):
    root = tmp_path / "analyses"
    for name in ("older", "newest"):
        directory = root / name / "job-brief"
        saved = application_job_brief.create_job_brief(
            application, directory, runner=runner_for(output)
        )
        os.utime(directory / "job-brief.json", ns=(1, 1 if name == "older" else 2))
    unrelated = root / "unrelated" / "job-brief"
    application_job_brief.create_job_brief(
        application | {"role_title": "Another role"}, unrelated, runner=runner_for(output)
    )
    assert application_job_brief.find_saved_job_brief(application, root) == (
        saved,
        root / "newest" / "job-brief" / "job-brief.json",
    )
    assert (
        application_job_brief.find_saved_job_brief(
            application | {"job_description": "A changed JD."}, root
        )
        is None
    )


@pytest.mark.parametrize("link", ["root", "analysis", "brief", "file"])
def test_saved_brief_lookup_rejects_symlink_paths(tmp_path, application, output, link):
    root = tmp_path / "analyses"
    directory = root / "matching" / "job-brief"
    application_job_brief.create_job_brief(application, directory, runner=runner_for(output))
    path = {
        "root": root,
        "analysis": directory.parent,
        "brief": directory,
        "file": directory / "job-brief.json",
    }[link]
    target = tmp_path / "retained-original"
    path.rename(target)
    path.symlink_to(target, target_is_directory=link != "file")

    with pytest.raises(PortalDataError) as caught:
        application_job_brief.find_saved_job_brief(application, root)
    assert caught.value.code == "job_brief_invalid"
