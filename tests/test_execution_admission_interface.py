"""Execution owns admission decisions; diagnostics retain only import compatibility."""

from copy import deepcopy


def test_execution_policy_keeps_verified_prepare_and_rejects_missing_evidence():
    from career_evidence_graph.application_execution import write_admission_reason

    receipt = {
        "package": {"status": "verified", "loaded_mapping": "verified"},
        "controller": {"source_matches_disk": True, "ui_matches_disk": True},
        "native_host": {
            "state": "verified",
            "session_open": True,
            "invalidation_epoch": 0,
            "bridge_binding_verified": True,
        },
        "inputs": {"state": "current", "materials_confirmed": True, "qualification": "supported"},
        "worker": {"last_error": None},
        "reasons": [],
    }
    state = {"control": "paused", "commands": [], "jobs": []}
    task = {"status": "materials_ready"}
    before = deepcopy((receipt, state, task))
    assert write_admission_reason(receipt, "prepare", state, task, None, 1000) is None
    assert (receipt, state, task) == before
    receipt["package"]["loaded_mapping"] = "unknown"
    assert write_admission_reason(receipt, "prepare", state, task, None, 1000) == (
        "installed_evidence_required"
    )
    from career_evidence_graph.application_readiness import (
        write_admission_reason as historical_import,
    )

    assert historical_import is write_admission_reason
