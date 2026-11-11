"""A newer unknown evaluator remains authoritative over older upstream receipts."""

from copy import deepcopy

import pytest
from test_canonical_career_sources import canonical as canonical
from test_career_portal_http import portal as portal
from test_normal_retrieval_pipeline import APPLICATION, RecordedPipeline, requirement

from career_evidence_graph import application_material_packet
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.mark.parametrize("changed_budget", [False, True])
def test_a_newer_unknown_evaluation_is_sent_again_by_the_next_retry(
    canonical, portal, tmp_path, monkeypatch, changed_budget
):
    monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "128000")
    monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "60000")
    job = ApplicationStore(portal.applications).create_application(
        {
            key: value
            for key, value in APPLICATION.items()
            if key not in {"id", "revision", "country"}
        }
    )
    requirements = [requirement("Scientific collaboration")]
    runners = {name: RecordedPipeline(requirements) for name in ("older", "newer", "retry")}
    active = {"name": "older"}

    def run(config, prompt, **kwargs):
        if active["name"] == "newer" and config.output_schema.name == "match-schema.json":
            raise KeyboardInterrupt("Synthetic evaluator dispatched without a saved response")
        return runners[active["name"]](config, prompt, **kwargs)

    server = create_server(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        career_library_manifest=canonical[5],
        flow_match_runner=run,
        write_admission_policy="development",
    )
    try:
        flow = server.application_flow_service
        original = flow.create(job["id"], job["revision"])
        older_id, newer_id, retry_id = "a" * 32, "b" * 32, "c" * 32
        older = deepcopy(original)
        older["stages"]["analysis"]["attempt_id"] = older_id
        actual_packet = application_material_packet.prepare_material_packet

        def persist_attempt(row):
            # A real attempt must be registered before its per-call admission.
            with flow.applications.write_lock():
                state = flow._load()
                current = flow._task(state, row["id"])
                current["stages"]["analysis"] = deepcopy(row["stages"]["analysis"])
                current["analysis_attempts"] = deepcopy(row.get("analysis_attempts", []))
                flow._save(state)

        persist_attempt(older)

        def unavailable(*args, **kwargs):
            # Preserve completed native reading proof before the callback stops.
            _, packet = actual_packet(*args, **kwargs)
            assert packet["status"] == "complete"
            raise PortalDataError(
                "retrieval_execution_incomplete", "Stopped after completed reading", 409
            )

        with monkeypatch.context() as patch:
            patch.setattr(application_material_packet, "prepare_material_packet", unavailable)
            with pytest.raises(PortalDataError):
                flow.callbacks["analysis"](older)

        active["name"] = "newer"
        newer = deepcopy(original)
        newer["stages"]["analysis"]["attempt_id"] = newer_id
        newer["stages"]["analysis"]["resume_from_attempt_id"] = older_id
        persist_attempt(newer)
        with pytest.raises(KeyboardInterrupt):
            flow.callbacks["analysis"](newer)
        preserved = {
            path: path.read_bytes()
            for path in (flow.root / "analyses").rglob("*")
            if path.is_file()
        }

        if changed_budget:
            monkeypatch.setenv("TOMORROWSTAR_MATCH_CONTEXT_BYTES", "384000")
            monkeypatch.setenv("TOMORROWSTAR_MATERIAL_CONTEXT_BYTES", "300000")
        current = flow.create(job["id"], job["revision"])
        current["stages"]["analysis"]["attempt_id"] = retry_id
        current["analysis_attempts"] = [
            {
                "stage": {"status": "failed", "attempt_id": identifier},
                "inputs": deepcopy(original["inputs"]),
                "job_binding": original["job_binding"],
            }
            for identifier in (older_id, newer_id)
        ]
        persist_attempt(current)
        active["name"] = "retry"
        # The newer attempt's unknown evaluation is sent again (Model Call Record,
        # decided 2026-11-09); a changed context budget analyses the job from the start.
        flow.callbacks["analysis"](current)
        assert "evaluate" in runners["retry"].phases
        assert all(path.read_bytes() == raw for path, raw in preserved.items())
    finally:
        server.server_close()
