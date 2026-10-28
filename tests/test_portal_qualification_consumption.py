"""Portal preparation and witnesses reuse material-bound P04 qualification."""

import json

import pytest
from test_canonical_career_sources import canonical as canonical
from test_installed_write_admission import prepared_inputs
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import json_material as json_material
from test_j08_material_binding import prepared_pdf
from test_j08_material_binding import recorded_pipeline_clock as recorded_pipeline_clock

from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import PortalDataError


def qualification_case(tmp_path, qualification):
    applications, root, career, task = prepared_inputs(tmp_path)
    if qualification != "not_specified":
        state = json.loads((root / "flow.json").read_text())
        task = state["tasks"][0]
        analysis = task["artifacts"][0]["result"]
        analysis["requirements"] = [
            {
                "text": "Required synthetic qualification",
                "hard_condition": True,
                "judgment": "unknown" if qualification == "needs_input" else "gap",
            }
        ]
        (root / "analyses" / analysis["id"] / "analysis.json").write_text(json.dumps(analysis))
        task["revision"] = digest({key: value for key, value in task.items() if key != "revision"})
        (root / "flow.json").write_text(json.dumps(state))
    return applications, root, career, task


@pytest.mark.parametrize("qualification", ["not_specified", "needs_input", "conflict"])
def test_legacy_portal_preserves_upstream_unknown_and_gap_policy(
    tmp_path, monkeypatch, qualification
):
    apps, root, career, task = qualification_case(tmp_path, qualification)
    with create_server(
        apps.root, career, flow_root=root, worker_root=tmp_path / "worker", worker_live=True
    ) as server:
        worker = server.worker_service
        if qualification == "conflict":
            with pytest.raises(PortalDataError) as failure:
                server.application_flow_service.prepare_worker(
                    task["id"], task["revision"], "CHE", True
                )
            assert failure.value.code == "flow_eligibility_required"
            assert worker.store.load()["jobs"] == []
        else:
            prepared = server.application_flow_service.prepare_worker(
                task["id"], task["revision"], "CHE", True
            )
            assert prepared["status"] == "queued"
            result, _ = server.application_readiness(
                task["id"], _with_witness=True, _write_stage="resume", _country="CHE"
            )
            assert result["inputs"]["state"] == "current"
            assert result["inputs"]["qualification"] == qualification


def test_portal_missing_analysis_archive_stops_before_qualification_or_legacy_screen(
    tmp_path, monkeypatch
):
    apps, root, career, task = qualification_case(tmp_path, "not_specified")
    (root / "analyses" / task["analysis_id"] / "analysis.json").unlink()
    with create_server(
        apps.root, career, flow_root=root, worker_root=tmp_path / "worker", worker_live=True
    ) as server:
        monkeypatch.setattr(
            server.worker_service.store,
            "check_language_requirement",
            lambda *a, **kw: pytest.fail("Missing lineage cannot fall back to JD screen"),
        )
        with pytest.raises(PortalDataError):
            server.application_flow_service.prepare_worker(
                task["id"], task["revision"], "CHE", True
            )
        assert server.worker_service.store.load()["jobs"] == []


def test_real_fixed_portal_delivery_never_rescreens_jd(json_material, monkeypatch):
    case = json_material
    task = prepared_pdf(case, None)
    worker = case.server.worker_service
    monkeypatch.setattr(
        worker.store, "check_language_requirement", lambda *a, **kw: pytest.fail("fixed P04")
    )
    prepared = case.flow.prepare_worker(task["id"], task["revision"], "CHE", True)
    result, _ = case.server.application_readiness(
        prepared["id"], _with_witness=True, _write_stage="resume", _country="CHE"
    )
    assert result["inputs"]["state"] == "current"
