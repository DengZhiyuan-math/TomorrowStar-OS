"""Intake owns the saved source receipt; its callers consume stable delivery JSON."""

from copy import deepcopy

import pytest
from test_application_intake import applications as applications

from career_evidence_graph._vendor import job_apply_store as helper
from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.career_portal_data import PortalDataError


def test_source_delivery_is_read_only_and_preserves_saved_application_order(applications, tmp_path):
    def unexpected_read(*args, **kwargs):
        raise AssertionError("A saved delivery cannot read the mailbox or job site")

    intake = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=unexpected_read, fetcher=unexpected_read
    )
    try:
        run_id = "a" * 32
        receipt = intake.root / "runs" / run_id / "source-chain.json"
        raw = {
            "schemaVersion": 1,
            "sources": [
                {"application_id": "second-job", "save_status": "saved"},
                {"application_id": "first-job", "save_status": "saved"},
                {"application_id": "second-job", "save_status": "saved"},
                {"application_id": "not-delivered", "save_status": "failed"},
            ],
        }
        helper.atomic_write_json(receipt, raw)
        before = receipt.read_bytes()
        expected = {
            "schema_version": "intake-source-delivery/v1",
            "run_id": run_id,
            "application_ids": ["second-job", "first-job"],
        }
        assert intake.source_delivery(run_id) == expected
        result = intake.source_delivery(run_id)
        result["application_ids"].clear()
        assert intake.source_delivery(run_id) == deepcopy(expected)
        assert receipt.read_bytes() == before
    finally:
        intake.close()


@pytest.mark.parametrize(
    "fault", ["run_id", "missing", "version", "version_bool", "shape", "identity", "redirect"]
)
def test_invalid_source_delivery_stops_without_reacquiring_sources(applications, tmp_path, fault):
    def unexpected_read(*args, **kwargs):
        raise AssertionError("Invalid receipts must not replay acquisition")

    intake = ApplicationIntakeService(
        applications, tmp_path / "intake", reader=unexpected_read, fetcher=unexpected_read
    )
    try:
        run_id = "b" * 32
        path = intake.root / "runs" / run_id / "source-chain.json"
        raw = {"schemaVersion": 1, "sources": [{"application_id": "saved", "save_status": "saved"}]}
        if fault == "version":
            raw["schemaVersion"] = 2
        elif fault == "version_bool":
            raw["schemaVersion"] = True
        elif fault == "shape":
            raw["sources"] = [None]
        elif fault == "identity":
            raw["sources"][0]["application_id"] = ""
        if fault != "missing":
            helper.atomic_write_json(path, raw)
        if fault == "redirect":
            target = tmp_path / "redirected.json"
            path.rename(target)
            path.symlink_to(target)
        if fault == "run_id":
            run_id = "../other"
        with pytest.raises(PortalDataError) as error:
            intake.source_delivery(run_id)
        assert error.value.code == "intake_source_invalid"
    finally:
        intake.close()
