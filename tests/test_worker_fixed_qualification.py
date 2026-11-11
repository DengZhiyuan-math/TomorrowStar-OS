"""Bound single workers consume validated upstream qualification once."""

from copy import deepcopy

import pytest
from test_canonical_career_sources import canonical as canonical
from test_j08_flow_combination import json_flow as json_flow
from test_j08_material_binding import json_material as json_material
from test_j08_material_binding import recorded_pipeline_clock as recorded_pipeline_clock
from test_j08_worker_information import bound_worker

from career_evidence_graph.application_worker_browser import ApplicationRunner
from career_evidence_graph.career_portal_data import PortalDataError


def test_validated_single_job_does_not_run_legacy_language_screening(json_material, monkeypatch):
    worker, current = bound_worker(json_material)

    def no_second_screen(*args, **kwargs):
        raise AssertionError("Bound P04 qualifications must not be screened again")

    monkeypatch.setattr(worker.store, "check_language_requirement", no_second_screen)
    ApplicationRunner(worker.store, None).check_inputs(current)


@pytest.mark.parametrize("code", ["single_binding_invalid", "single_eligibility_required"])
def test_binding_or_qualification_rejection_still_stops_single_checks(
    json_material, monkeypatch, code
):
    worker, current = bound_worker(json_material)
    before = worker.store.path.read_bytes()

    def unverified(*args, **kwargs):
        raise PortalDataError(code, "Recorded binding or qualification cannot be verified", 409)

    def forbidden(*args, **kwargs):
        pytest.fail("Legacy screening cannot replace a failed upstream check")

    monkeypatch.setattr(worker.store, "single_validator", unverified)
    monkeypatch.setattr(worker.store, "check_language_requirement", forbidden)
    with pytest.raises(PortalDataError) as caught:
        ApplicationRunner(worker.store, None).check_inputs(current)
    assert caught.value.code == code
    assert worker.store.path.read_bytes() == before


def test_changed_delivered_analysis_binding_is_rejected_before_legacy_screening(
    json_material, monkeypatch
):
    worker, current = bound_worker(json_material)
    changed = deepcopy(current)
    changed["single_binding"]["analysis_id"] = "0" * 32
    before = worker.store.path.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("Changed bindings must stop before any language screening")

    monkeypatch.setattr(worker.store, "check_language_requirement", forbidden)
    with pytest.raises(PortalDataError) as caught:
        ApplicationRunner(worker.store, None).check_inputs(changed)
    assert caught.value.code == "single_binding_invalid"
    assert worker.store.path.read_bytes() == before
