from __future__ import annotations

import subprocess

import pytest

from career_evidence_graph.validation.replay import replay_recorded_response
from career_evidence_graph.validation.store import (
    FormalRunStorageError,
    FormalRunStore,
    load_charter,
)


def _lineage() -> dict[str, object]:
    return {
        "fixture": {},
        "artifacts": [],
        "prompt": {},
        "model": {},
        "configuration": {},
        "policy": {},
        "reviewer": {},
    }


def test_exact_replay_uses_only_recorded_response(tmp_path, charter_path, monkeypatch):
    store = FormalRunStore(tmp_path)
    store.create(
        run_id="offline",
        charter=load_charter(charter_path),
        raw_response={"result": {"stable": True}},
        proposal={"stable": True},
        confirmed_result={"stable": True},
        lineage_inputs=_lineage(),
    )

    def fail_live_call(*args, **kwargs):
        raise AssertionError("exact replay must not invoke a live subprocess")

    monkeypatch.setattr(subprocess, "run", fail_live_call)

    assert replay_recorded_response(store, "offline").matched is True


def test_replay_fails_closed_after_payload_tampering(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    store.create(
        run_id="tampered",
        charter=load_charter(charter_path),
        raw_response={"result": {"stable": True}},
        proposal={"stable": True},
        confirmed_result={"stable": True},
        lineage_inputs=_lineage(),
    )
    (tmp_path / "formal-runs/tampered/confirmed_result.json").write_text(
        '{"stable":false}\n', encoding="utf-8"
    )

    with pytest.raises(FormalRunStorageError, match="hash mismatch"):
        replay_recorded_response(store, "tampered")
