"""Maintenance diagnostics do not approve local application preparation."""

import json

import pytest
from test_installed_write_admission import prepared_inputs

from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import PortalDataError


def test_local_preparation_keeps_business_checks_without_package_or_native_receipts(tmp_path):
    applications, root, career, task = prepared_inputs(tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
        package_resources=tmp_path / "missing-installed-package",
    ) as server:
        prepared = server.application_flow_service.prepare_worker(
            task["id"], task["revision"], "CHE", True
        )
        assert prepared["status"] == "queued"
        state = server.worker_service.store.load()
        assert state["control"] == "paused"
        assert len(state["jobs"]) == 1 and state["jobs"][0]["intent"] is None
        assert state["jobs"][0]["application_id"] == task["application_id"]
        assert server.worker_service.process is None


def test_language_conflict_stops_before_saving_preparation_or_approval(tmp_path):
    applications, root, career, task = prepared_inputs(
        tmp_path, job_description="German B2 required."
    )
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
    ) as server:
        worker = server.worker_service
        for question, value in [("German level", "B2"), ("German proficiency CEFR", "C1")]:
            worker.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        before = (root / "flow.json").read_bytes(), worker.store.path.read_bytes()
        with pytest.raises(PortalDataError) as stopped:
            server.application_flow_service.prepare_worker(
                task["id"], task["revision"], "CHE", True
            )
        assert stopped.value.code == "language_information_required"
        assert ((root / "flow.json").read_bytes(), worker.store.path.read_bytes()) == before
        assert worker.process is None


def test_bound_materials_are_verified_before_saving_preparation(tmp_path):
    applications, root, career, task = prepared_inputs(tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
    ) as server:
        flow = server.application_flow_service
        worker = server.worker_service
        verified = []

        def verify_materials(current):
            verified.append(current["id"])
            raise PortalDataError("flow_materials_changed", "材料身份已变化。", 409)

        flow.callbacks["verify_materials"] = verify_materials
        before = flow.path.read_bytes(), worker.store.path.read_bytes()
        with pytest.raises(PortalDataError) as stopped:
            flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert stopped.value.code == "flow_materials_changed"
        assert verified == [task["id"]]
        assert (flow.path.read_bytes(), worker.store.path.read_bytes()) == before
        assert worker.process is None


def test_changed_adopted_analysis_stops_before_saving_preparation(tmp_path):
    applications, root, career, task = prepared_inputs(tmp_path)
    analysis_path = root / "analyses" / task["analysis_id"] / "analysis.json"
    report = json.loads(analysis_path.read_text())
    report["policy_version"] = "changed-after-adoption"
    analysis_path.write_text(json.dumps(report))
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
    ) as server:
        flow = server.application_flow_service
        worker = server.worker_service
        before = flow.path.read_bytes(), worker.store.path.read_bytes()
        with pytest.raises(PortalDataError) as stopped:
            flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert stopped.value.code == "single_binding_invalid"
        assert (flow.path.read_bytes(), worker.store.path.read_bytes()) == before
        assert worker.process is None


def test_new_duplicate_between_scan_and_write_stops_before_saving_preparation(
    tmp_path, monkeypatch
):
    from career_evidence_graph import application_single_binding

    applications, root, career, task = prepared_inputs(tmp_path)
    with create_server(
        applications.root,
        career,
        flow_root=root,
        worker_root=tmp_path / "worker",
        worker_live=True,
    ) as server:
        flow = server.application_flow_service
        worker = server.worker_service
        scan = application_single_binding.validate_application_target
        duplicates = []

        def add_duplicate_after_scan(*arguments, **options):
            target = scan(*arguments, **options)
            application = applications.get_application(task["application_id"])
            duplicates.append(
                applications.create_application(
                    {
                        "company": "New recommendation",
                        "role_title": "Same target",
                        "url": application["url"],
                    }
                )
            )
            return target

        monkeypatch.setattr(
            application_single_binding, "validate_application_target", add_duplicate_after_scan
        )
        before = flow.path.read_bytes(), worker.store.path.read_bytes()
        with pytest.raises(PortalDataError) as stopped:
            flow.prepare_worker(task["id"], task["revision"], "CHE", True)
        assert stopped.value.code == "conflict"
        assert len(duplicates) == 1
        assert (flow.path.read_bytes(), worker.store.path.read_bytes()) == before
        assert worker.process is None
