"""Shared execution ownership uses synthetic application stores."""

import pytest

from career_evidence_graph.application_execution import (
    release_execution,
    require_execution,
    reserve_execution,
)
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


def test_execution_claim_is_shared_across_services_and_never_stolen(tmp_path):
    applications = ApplicationStore(tmp_path)
    reserve_execution(applications, "synthetic-job", "codex-task-1", "codex")
    reserve_execution(applications, "synthetic-job", "codex-task-1", "codex")
    with pytest.raises(PortalDataError, match="占用"):
        reserve_execution(ApplicationStore(tmp_path), "synthetic-job", "worker-1", "automated")
    with pytest.raises(PortalDataError):
        release_execution(applications, "synthetic-job", "different-task", "codex")
    require_execution(applications, "synthetic-job", "codex-task-1", "codex")
    release_execution(applications, "synthetic-job", "codex-task-1", "codex")
    reserve_execution(applications, "synthetic-job", "worker-1", "automated")
    require_execution(applications, "synthetic-job", "worker-1", "automated")


def test_missing_or_corrupt_ownership_fails_closed(tmp_path):
    applications = ApplicationStore(tmp_path)
    with pytest.raises(PortalDataError) as raised:
        require_execution(applications, "synthetic-job", "worker-1", "automated")
    assert raised.value.code == "execution_missing"
    reserve_execution(applications, "synthetic-job", "worker-1", "automated")
    next((tmp_path / ".execution").glob("*.json")).write_text("not JSON")
    with pytest.raises(PortalDataError) as raised:
        reserve_execution(applications, "synthetic-job", "worker-2", "automated")
    assert raised.value.code == "execution_invalid"


@pytest.mark.parametrize("relation", ["same", "ancestor", "descendant"])
def test_mixed_lane_roots_are_rejected(tmp_path, relation):
    from career_evidence_graph.application_execution import reject_mixed_execution_root

    root = tmp_path / "runtime"
    root.mkdir()
    other = root if relation == "same" else tmp_path if relation == "ancestor" else root / "child"
    other.mkdir(exist_ok=True)
    (other / "handoff.json").write_text("{}")
    with pytest.raises(ValueError, match="separate"):
        reject_mixed_execution_root(root, "handoff.json")


def test_lab_preflight_preserves_old_evidence_without_starting_worker(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    evidence = tmp_path / "failed-run.md"
    evidence.write_text("Original failure evidence.\n")
    root = tmp_path / "lab"
    launcher = Path(__file__).parents[1] / "scripts/run_application_automation_lab.py"
    result = subprocess.run(
        [sys.executable, str(launcher), "--runtime", str(root), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    report = json.loads(Path(json.loads(result.stdout)["report"]).read_text())
    assert report["mode"] == "offline_preflight"
    assert report["new_model_calls"] == report["real_ats"] == 0
    assert report["native_verified"] is False
    assert not (root / "run.json").exists()
    assert not (root / "answer-library").exists()
    assert evidence.read_text() == "Original failure evidence.\n"
    (root / "run.json").write_text("preserved legacy state")
    refused = subprocess.run(
        [sys.executable, str(launcher), "--runtime", str(root)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused.returncode == 2
    assert (root / "run.json").read_text() == "preserved legacy state"


def test_release_retry_is_idempotent_for_exact_owner_only(tmp_path):
    applications = ApplicationStore(tmp_path)
    reserve_execution(applications, "synthetic-job", "codex-task", "codex")
    release_execution(applications, "synthetic-job", "codex-task", "codex")
    release_execution(applications, "synthetic-job", "codex-task", "codex")
    with pytest.raises(PortalDataError) as raised:
        release_execution(applications, "synthetic-job", "different-task", "codex")
    assert raised.value.code == "execution_conflict"


def test_late_release_recovers_from_history_without_changing_new_owner(tmp_path):
    applications = ApplicationStore(tmp_path)
    reserve_execution(applications, "synthetic-job", "old-codex", "codex")
    release_execution(applications, "synthetic-job", "old-codex", "codex")
    reserve_execution(applications, "synthetic-job", "new-worker", "automated")
    path = next((tmp_path / ".execution").glob("*.json"))
    before = path.read_bytes()
    release_execution(applications, "synthetic-job", "old-codex", "codex")
    assert path.read_bytes() == before
    require_execution(applications, "synthetic-job", "new-worker", "automated")


@pytest.mark.parametrize("history_active", [True, None])
def test_late_release_cannot_use_missing_or_unreleased_history(tmp_path, history_active):
    import json

    applications = ApplicationStore(tmp_path)
    reserve_execution(applications, "synthetic-job", "new-worker", "automated")
    path = next((tmp_path / ".execution").glob("*.json"))
    if history_active is True:
        record = json.loads(path.read_text())
        record["history"] = [{"owner": "old-codex", "lane": "codex", "active": True}]
        path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(PortalDataError) as raised:
        release_execution(applications, "synthetic-job", "old-codex", "codex")
    assert raised.value.code == "execution_conflict"
    assert path.read_bytes() == before
