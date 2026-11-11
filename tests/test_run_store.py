from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_evidence_graph.validation.hashing import canonical_json_bytes, sha256_digest
from career_evidence_graph.validation.models import CorrectionRecord
from career_evidence_graph.validation.store import (
    FormalRunStorageError,
    FormalRunStore,
    create_only_file_bundle,
    load_charter,
)


def _lineage(seed: str = "v1") -> dict[str, object]:
    return {
        "fixture": {"version": seed},
        "artifacts": [{"sha": seed}],
        "prompt": {"version": seed},
        "model": {"requested": "none", "version": seed},
        "configuration": {"version": seed},
        "policy": {"version": seed},
        "reviewer": {"version": seed},
    }


def _create(store: FormalRunStore, charter_path: Path, run_id: str = "run-1"):
    proposal = {"capability": "proposal"}
    return store.create(
        run_id=run_id,
        charter=load_charter(charter_path),
        raw_response={"result": {"capability": "confirmed"}},
        proposal=proposal,
        confirmed_result={"capability": "confirmed"},
        lineage_inputs=_lineage(),
    )


def test_duplicate_destination_preserves_original_bytes(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path)
    run_path = tmp_path / "formal-runs" / "run-1"
    original = {path.name: path.read_bytes() for path in run_path.iterdir()}

    with pytest.raises(FormalRunStorageError, match="already exists"):
        _create(store, charter_path)

    assert {path.name: path.read_bytes() for path in run_path.iterdir()} == original


def test_file_bundle_rejects_symlink_root_and_duplicate_destination(tmp_path):
    root = tmp_path / "bundles"
    assert create_only_file_bundle(root, "bundle-1", {"payload.txt": b"one"}) == root / "bundle-1"
    original = (root / "bundle-1" / "payload.txt").read_bytes()
    with pytest.raises(FormalRunStorageError, match="already exists"):
        create_only_file_bundle(root, "bundle-1", {"payload.txt": b"two"})
    assert (root / "bundle-1" / "payload.txt").read_bytes() == original

    external = tmp_path / "external"
    external.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(external, target_is_directory=True)
    with pytest.raises(FormalRunStorageError, match="symlink"):
        create_only_file_bundle(linked_root, "bundle-2", {"payload.txt": b"nope"})
    assert not (external / "bundle-2").exists()


def test_linked_rerun_preserves_parent_and_requires_change_reason(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path)
    parent_path = tmp_path / "formal-runs" / "run-1"
    parent_before = {path.name: path.read_bytes() for path in parent_path.iterdir()}

    child = store.create_linked_rerun(
        parent_run_id="run-1",
        run_id="run-2",
        change_reason="prompt version changed",
        diff={"prompt": ["v1", "v2"]},
        charter=load_charter(charter_path),
        raw_response={"result": {"capability": "confirmed-v2"}},
        proposal={"capability": "proposal-v2"},
        confirmed_result={"capability": "confirmed-v2"},
        lineage_inputs=_lineage("v2"),
    )

    assert child.run_id != child.parent_run_id
    assert child.parent_run_id == "run-1"
    assert store.verify("run-2") == child
    assert {path.name: path.read_bytes() for path in parent_path.iterdir()} == parent_before

    with pytest.raises(FormalRunStorageError, match="non-empty change reason"):
        store.create_linked_rerun(
            parent_run_id="run-1",
            run_id="run-3",
            change_reason=" ",
            diff={},
            charter=load_charter(charter_path),
            raw_response={"result": {}},
            proposal={},
            confirmed_result={},
            lineage_inputs=_lineage("v3"),
        )


def test_correction_retains_original_proposal_reviewer_and_reason(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    proposal = {"capability": "incorrect-original"}
    proposal_hash = sha256_digest(canonical_json_bytes(proposal))
    correction = CorrectionRecord(
        schema_version="correction-record/v1",
        correction_id="correction-1",
        created_at=datetime.now(UTC),
        original_proposal=proposal,
        original_proposal_hash=proposal_hash,
        correction={"capability": "reviewer-corrected"},
        reviewer_id="reviewer-1",
        reason="Responsibility belonged to the team.",
    )

    store.create(
        run_id="corrected-run",
        charter=load_charter(charter_path),
        raw_response={"result": {"capability": "reviewer-corrected"}},
        proposal=proposal,
        confirmed_result={"capability": "reviewer-corrected"},
        lineage_inputs=_lineage(),
        corrections=[correction],
    )

    stored_proposal = store.payload("corrected-run", "original_proposal.json")
    stored_corrections = store.payload("corrected-run", "corrections.json")
    assert sha256_digest(canonical_json_bytes(stored_proposal)) == proposal_hash
    assert stored_corrections[0]["original_proposal"] == proposal
    assert stored_corrections[0]["reviewer_id"] == "reviewer-1"
    assert stored_corrections[0]["reason"] == "Responsibility belonged to the team."


def test_verify_rejects_tampering_and_symlinked_run(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path)
    payload = tmp_path / "formal-runs/run-1/raw_response.json"
    payload.write_text('{"result":{"capability":"tampered"}}\n', encoding="utf-8")

    with pytest.raises(FormalRunStorageError, match="hash mismatch"):
        store.verify("run-1")

    _create(store, charter_path, "run-2")
    (tmp_path / "formal-runs/run-link").symlink_to(
        tmp_path / "formal-runs/run-2", target_is_directory=True
    )
    with pytest.raises(FormalRunStorageError, match="does not exist safely"):
        store.verify("run-link")


def test_run_id_cannot_traverse_workspace(tmp_path):
    with pytest.raises(FormalRunStorageError, match="unsafe path"):
        FormalRunStore(tmp_path).verify("../escape")
