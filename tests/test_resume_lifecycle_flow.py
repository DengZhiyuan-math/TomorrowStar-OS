"""Default Flow preserves the distinct effects of Resume lifecycle operations."""

from pathlib import Path

import pytest
from test_application_flow import wait_for
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import finish_json_writing, start_json_writing
from test_j08_flow_combination import json_flow as json_flow

from career_evidence_graph.career_portal_data import PortalDataError


def test_unknown_export_recheck_cannot_start_a_new_prism_capture(json_flow):
    case = json_flow
    task, _ = finish_json_writing(case, start_json_writing(case))
    read_compiled = case.store.prism_client.read_compiled

    def unavailable(*args):
        raise OSError("Synthetic unavailable build result")

    case.store.prism_client.read_compiled = unavailable
    case.flow.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "needs_recheck")
    export_id = task["stages"]["export"]["attempt_id"]
    reads = []

    def available(binding):
        reads.append(binding)
        return read_compiled(binding)

    case.store.prism_client.read_compiled = available
    with pytest.raises(PortalDataError) as stopped:
        case.flow.recheck_export(task["id"], task["revision"])
    assert stopped.value.code == "resume_export_needs_recheck"
    assert reads == []
    assert not (case.store.root / export_id / "export.json").exists()
    current = case.flow.task_snapshot(task["id"])
    assert current["stages"]["export"] == task["stages"]["export"]
    assert current["resume_id"] is None


def test_lost_export_response_recovers_saved_pdf_after_live_source_changes(json_flow):
    case = json_flow
    task, _ = finish_json_writing(case, start_json_writing(case))
    build = case.store.build_pdf
    saved = []

    def lost_response(*args, **kwargs):
        result = build(*args, **kwargs)
        saved.append(result)
        raise OSError("Synthetic response lost after complete PDF persistence")

    case.store.build_pdf = lost_response
    case.flow.export_pdf(task["id"], task["revision"], task["draft_id"], task["draft_sha256"])
    task = wait_for(case.flow, task["id"], lambda row: row["status"] == "needs_recheck")
    assert len(saved) == 1
    original_pdf = case.store.pdf(saved[0]["id"])
    binding = task["source_checkpoint"]
    live_source = Path(binding["project_root"]) / binding["main"]
    live_source.write_text(live_source.read_text() + "\n% Later human edit, not yet exported\n")

    def forbidden(*args, **kwargs):
        pytest.fail("Receipt recovery must not contact Prism or start another build")

    case.store.prism_client.read_compiled = forbidden
    case.store.prism_client.compile = forbidden
    recovered = case.flow.recheck_export(task["id"], task["revision"])
    assert recovered["status"] == "materials_ready"
    assert recovered["resume_id"] == saved[0]["id"]
    assert recovered["resume_sha256"] == saved[0]["pdf_sha256"]
    assert case.store.pdf(recovered["resume_id"]) == original_pdf
    assert len(saved) == 1
    assert live_source.read_text().endswith("% Later human edit, not yet exported\n")
