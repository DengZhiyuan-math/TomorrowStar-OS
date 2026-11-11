"""A bounded source-only reuse keeps changed or unverifiable input conservative."""

import json

import pytest
from test_analysis_consumed_source_reuse import analyzed_omitted_source as analyzed_omitted_source

from career_evidence_graph import application_match
from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal_data import PortalDataError


def correct_omitted(case):
    before = case.catalog.get_evidence(case.before_sources["profile_source"]["id"])
    return case.catalog.update_evidence(
        before["id"],
        before["revision"],
        before["content"].replace("Ruby", "Rust"),
        source="synthetic omitted-source correction",
    )


def analysis_files(case):
    directory = case.flow.root / "analyses" / case.task["analysis_id"]
    return directory, {path.name: path.read_bytes() for path in directory.iterdir()}


def test_consumed_source_change_keeps_analysis_pending(analyzed_omitted_source):
    case = analyzed_omitted_source
    directory, before = analysis_files(case)
    path = case.catalog.root / "contributions/00-consumed.md"
    # Research Contributions are read-only through fact correction; model an external
    # source refresh only in this disposable fixture, inside the consumed prefix.
    path.write_text(path.read_text().replace("Python", "Kotlin", 1))
    call_count = len(case.calls)
    refreshed = case.flow.update_inputs(
        case.task["id"], case.task["revision"], case.job["revision"]
    )
    assert refreshed["analysis_id"] is None
    assert refreshed["stages"]["analysis"]["status"] == "pending"
    assert refreshed["artifacts"] == case.task["artifacts"]
    assert len(case.calls) == call_count
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize("changed_input", ["jd", "configuration"])
def test_omitted_change_does_not_reuse_changed_job_or_engine(
    analyzed_omitted_source, monkeypatch, changed_input
):
    case = analyzed_omitted_source
    correct_omitted(case)
    job = case.job
    if changed_input == "jd":
        job = case.flow.applications.update_application(
            job["id"], {"job_description": "Build reliable Kotlin systems."}, job["revision"]
        )
    else:
        monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(case.root / "different-codex"))
    call_count = len(case.calls)
    directory, before = analysis_files(case)
    refreshed = case.flow.update_inputs(case.task["id"], case.task["revision"], job["revision"])
    assert refreshed["analysis_id"] is None
    assert refreshed["stages"]["analysis"]["status"] == "pending"
    assert refreshed["artifacts"] == case.task["artifacts"]
    assert len(case.calls) == call_count
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize("filename", ["context-input.json", "source-snapshot.json"])
def test_corrupt_original_evidence_rejects_without_fallback(analyzed_omitted_source, filename):
    case = analyzed_omitted_source
    correct_omitted(case)
    directory, _ = analysis_files(case)
    damaged = directory / filename
    document = json.loads(damaged.read_text())
    document["prompt" if filename == "context-input.json" else "revision"] = "corrupt-original"
    damaged.write_text(json.dumps(document))
    files_before = {path.name: path.read_bytes() for path in directory.iterdir()}
    flow_before = case.flow.path.read_bytes()
    directories_before = set(directory.parent.iterdir())
    call_count = len(case.calls)
    with pytest.raises(PortalDataError) as error:
        case.flow.update_inputs(case.task["id"], case.task["revision"], case.job["revision"])
    assert error.value.code == "flow_analysis_mismatch"
    assert case.flow.path.read_bytes() == flow_before
    assert set(directory.parent.iterdir()) == directories_before
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == files_before
    assert len(case.calls) == call_count


def test_adoption_write_failure_keeps_original_flow_and_analysis(
    analyzed_omitted_source, monkeypatch
):
    case = analyzed_omitted_source
    correct_omitted(case)
    directory, before = analysis_files(case)
    flow_before = case.flow.path.read_bytes()
    call_count = len(case.calls)
    write = application_match.helper.atomic_write_json

    def fail_new_analysis(path, value):
        if path.name == "analysis.json" and path.parent != directory:
            raise OSError("Synthetic adoption write failed")
        return write(path, value)

    monkeypatch.setattr(application_match.helper, "atomic_write_json", fail_new_analysis)
    with pytest.raises(OSError, match="Synthetic adoption write failed"):
        case.flow.update_inputs(case.task["id"], case.task["revision"], case.job["revision"])
    assert case.flow.path.read_bytes() == flow_before
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
    assert len(case.calls) == call_count
    assert case.flow.snapshot(case.task["id"])["active_task"] == case.task


def test_repeat_update_and_cold_flow_reopen_keep_one_adoption(analyzed_omitted_source):
    case = analyzed_omitted_source
    correct_omitted(case)
    call_count = len(case.calls)
    adopted = case.flow.update_inputs(case.task["id"], case.task["revision"], case.job["revision"])
    assert adopted["analysis_id"] != case.task["analysis_id"]
    records = set((case.flow.root / "analyses").iterdir())
    repeated = case.flow.update_inputs(adopted["id"], adopted["revision"], case.job["revision"])
    assert repeated["analysis_id"] == adopted["analysis_id"]
    assert repeated["artifacts"] == adopted["artifacts"]
    case.flow.close()
    reopened = ApplicationFlowService(
        case.flow.applications,
        case.flow.root,
        callbacks=case.flow.callbacks,
        input_provider=case.flow.input_provider,
        information_provider=case.flow.information_provider,
    )
    try:
        observed = reopened.snapshot(adopted["id"])["active_task"]
        assert observed["analysis_id"] == adopted["analysis_id"]
        assert observed["artifacts"] == adopted["artifacts"]
        refreshed = reopened.update_inputs(
            observed["id"], observed["revision"], case.job["revision"]
        )
        assert refreshed["artifacts"] == adopted["artifacts"]
        assert set((case.flow.root / "analyses").iterdir()) == records
        assert len(case.calls) == call_count
    finally:
        reopened.close()
