"""Completed retrieval analyses retain frozen consumed facts across unrelated changes."""

import json
from copy import deepcopy

import pytest
from test_career_experiences import library as library
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement
from test_structured_career_library import content

from career_evidence_graph.application_match import analyze_job, reuse_analysis
from career_evidence_graph.career_experiences import ExperienceStore

pytestmark = pytest.mark.usefixtures("planner_path")


@pytest.fixture
def completed(library, tmp_path):
    adapter, root, descriptor, rows, write = library
    store = ExperienceStore(root)
    for identifier in ("alpha", "beta"):
        facts = content(identifier)
        store.save(identifier, title=facts["title"], content=facts)
    base = {"schemaVersion": 1, "documents": [], "items": []}
    initial = adapter.snapshot_for_analysis(base)
    runner = RecordedPipeline([requirement("Validate a team model")])
    original = tmp_path / "original"
    report = analyze_job(
        APPLICATION,
        initial,
        original,
        runner=runner,
        source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
    )
    return adapter, base, descriptor, rows, write, store, original, report, runner


def test_unselected_fact_and_directory_change_reuse_completed_analysis(completed, tmp_path):
    adapter, base, descriptor, rows, write, store, original, report, runner = completed
    before = {
        str(path.relative_to(original)): path.read_bytes() for path in original.rglob("*.json")
    }
    beta = store.get("beta")
    changed = deepcopy(beta["content"])
    changed["facts"][0]["text"] = "Tutored a different synthetic class."
    store.save("beta", title=changed["title"], content=changed, expected_revision=beta["revision"])
    rows[1]["accepted_reading_summary"] = "Updated unrelated directory summary"
    descriptor["catalog"] = write("catalog.json", {"records": rows})
    adapter.manifest.write_text(json.dumps(descriptor))
    current = adapter.snapshot_for_analysis(base)
    call_count = len(runner.calls)
    reused = reuse_analysis(
        APPLICATION,
        current,
        report,
        original,
        tmp_path / "reused",
        source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
    )
    assert reused is not None
    assert reused["score"] == report["score"]
    assert reused["requirements"] == report["requirements"]
    assert reused["input_source_snapshot_revision"] == current["revision"]
    assert reused["reused_from"]["model_called"] is False
    assert len(runner.calls) == call_count
    assert before == {
        str(path.relative_to(original)): path.read_bytes() for path in original.rglob("*.json")
    }
    assert (
        reuse_analysis(
            APPLICATION,
            current,
            reused,
            tmp_path / "reused",
            tmp_path / "reused-again",
            source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
        )["score"]
        == report["score"]
    )


@pytest.mark.parametrize("change", ["text", "responsibility", "source_refs", "source_locator"])
def test_changed_consumed_fact_or_reference_cannot_reuse(completed, tmp_path, change):
    adapter, base, _, _, _, store, original, report, runner = completed
    alpha = store.get("alpha")
    facts = deepcopy(alpha["content"])
    fact = facts["facts"][0]
    if change == "text":
        fact["text"] = "Observed an incomplete team experiment."
    elif change == "responsibility":
        fact["responsibility"] = "third_party"
    elif change == "source_refs":
        facts["sources"].append({"id": "note-2", "locator": "notes/corrected.txt"})
        fact["source_refs"] = ["note-2"]
    else:
        facts["sources"][0]["locator"] = "notes/corrected-location.txt"
    store.save("alpha", title=facts["title"], content=facts, expected_revision=alpha["revision"])
    count = len(runner.calls)
    destination = tmp_path / "must-not-publish"
    assert (
        reuse_analysis(
            APPLICATION,
            adapter.snapshot_for_analysis(base),
            report,
            original,
            destination,
            source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
        )
        is None
    )
    assert not destination.exists()
    assert len(runner.calls) == count


def test_completed_analysis_survives_only_diagnostic_configuration_changes(
    completed, tmp_path, monkeypatch
):
    from career_evidence_graph import application_match

    adapter, base, _, _, _, _, original, report, _ = completed
    configuration = application_match.match_configuration()
    configuration.update(
        engine_sha256="new-app-source-hash",
        retrieval_engine_sha256="new-app-loader-hash",
        retrieval_component_sha256={"diagnostic": "updated"},
        resolved_executable="/diagnostic/new-resolved-path",
        executable_status="unavailable",
        executable_metadata_revision="new-binary-stat",
    )
    monkeypatch.setattr(application_match, "match_configuration", lambda: configuration)
    reused = reuse_analysis(
        APPLICATION,
        adapter.snapshot_for_analysis(base),
        report,
        original,
        tmp_path / "diagnostic-reuse",
        source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
    )
    assert reused["reused_from"]["model_called"] is False
    configuration["requested_model"] = "a-different-requested-model"
    assert (
        reuse_analysis(
            APPLICATION,
            adapter.snapshot_for_analysis(base),
            report,
            original,
            tmp_path / "model-setting-changed",
            source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
        )
        is None
    )


@pytest.mark.parametrize("changed_input", ["job", "information", "fixed_education"])
def test_changed_job_information_or_fixed_education_cannot_reuse(
    completed, tmp_path, changed_input
):
    from test_application_information import answer, library_with

    adapter, base, _, _, _, _, original, report, _ = completed
    application = deepcopy(APPLICATION)
    information = None
    if changed_input == "job":
        application["job_description"] = "Assess a different physical process."
    elif changed_input == "information":
        information = library_with(answer("English fluency", "professional"))
    else:
        base["documents"].append({"id": "fixed-education", "revision": "r1", "available": True})
        base["items"].append(
            {
                "source_id": "fixed-education:degree",
                "source_revision": "r1",
                "source_name": "profile.json",
                "evidence_id": "fixed-education",
                "locator": "profile.education[0]",
                "source_kind": "education",
                "resume_eligible": False,
                "text": "MSc studies in progress; no awarded degree.",
            }
        )
    assert (
        reuse_analysis(
            application,
            adapter.snapshot_for_analysis(base),
            report,
            original,
            tmp_path / "changed-input",
            source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
            information_library=information,
        )
        is None
    )


@pytest.mark.parametrize(
    "filename",
    [
        "selected-read-snapshot.json",
        "material-packet.json",
        "evaluation-1/context-input.json",
        "evaluation-1/analysis.json",
    ],
)
def test_damaged_frozen_analysis_does_not_publish_an_adoption(completed, tmp_path, filename):
    from career_evidence_graph.career_portal_data import PortalDataError

    adapter, base, _, _, _, _, original, report, _ = completed
    path = original / filename
    value = json.loads(path.read_text())
    if filename == "evaluation-1/analysis.json":
        value["role_understanding"] = "Tampered interpretation of the synthetic role."
    else:
        value["prompt" if "context-input" in filename else "revision"] = "damaged"
    path.write_text(json.dumps(value))
    with pytest.raises(PortalDataError) as caught:
        reuse_analysis(
            APPLICATION,
            adapter.snapshot_for_analysis(base),
            report,
            original,
            tmp_path / "damaged-input",
            source_loader=lambda ids: adapter.snapshot_for_analysis(base, ids),
        )
    assert caught.value.code == "flow_analysis_mismatch"
    assert not (tmp_path / "damaged-input").exists()
