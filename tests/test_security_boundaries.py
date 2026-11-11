from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from career_evidence_graph.validation.acceptance import (
    evaluate_functional_acceptance,
)
from career_evidence_graph.validation.models import CriticalNegativeCase
from career_evidence_graph.validation.replay import replay_recorded_response
from career_evidence_graph.validation.store import (
    FormalRunStorageError,
    FormalRunStore,
    load_charter,
)

CRITICAL_CLASSES = (
    "capability_fabrication",
    "incorrect_attribution",
    "duplicate_evidence_inflation",
    "broken_lineage",
    "material_instability",
    "unreproducible_formal_run",
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


def _create(store: FormalRunStore, charter_path: Path, run_id: str = "accepted"):
    return store.create(
        run_id=run_id,
        charter=load_charter(charter_path),
        raw_response={"result": {"accepted": True}},
        proposal={"accepted": True},
        confirmed_result={"accepted": True},
        lineage_inputs=_lineage(),
    )


def _bytes(run_path: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in run_path.iterdir()}


@pytest.mark.parametrize("blocker_class", CRITICAL_CLASSES)
def test_each_critical_class_blocks_independently(blocker_class):
    case = CriticalNegativeCase(
        schema_version="critical-negative-case/v1",
        case_id=f"regression-{blocker_class.replace('_', '-')}",
        blocker_class=blocker_class,
        triggered=True,
        evidence=["deterministic regression triggered"],
    )

    evaluation = evaluate_functional_acceptance(
        [case],
        strengths_observed=["100 unrelated strengths cannot offset a blocker"],
    )

    assert evaluation.decision == "block"
    assert evaluation.blocking_classes == [blocker_class]


def test_non_triggered_cases_are_not_silently_converted_to_failures():
    cases = [
        CriticalNegativeCase(
            schema_version="critical-negative-case/v1",
            case_id=f"clear-{blocker_class.replace('_', '-')}",
            blocker_class=blocker_class,
            triggered=False,
            evidence=["regression did not trigger"],
        )
        for blocker_class in CRITICAL_CLASSES
    ]

    assert evaluate_functional_acceptance(cases).decision == "pass"


@pytest.mark.parametrize("unsafe_run_id", ("../escape", "/tmp/escape", "a/b", r"a\b"))
def test_unsafe_run_paths_are_rejected_before_any_write(tmp_path, unsafe_run_id):
    store = FormalRunStore(tmp_path)

    with pytest.raises(FormalRunStorageError, match="unsafe path"):
        store.verify(unsafe_run_id)

    assert not (tmp_path / "formal-runs").exists()


def test_external_symlink_and_preexisting_directory_preserve_accepted_bytes(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path)
    accepted_path = tmp_path / "formal-runs/accepted"
    accepted_before = _bytes(accepted_path)
    external = tmp_path / "external"
    external.mkdir()
    (external / "sentinel").write_text("do not touch", encoding="utf-8")
    (tmp_path / "formal-runs/external-link").symlink_to(external, target_is_directory=True)

    with pytest.raises(FormalRunStorageError):
        store.verify("external-link")
    with pytest.raises(FormalRunStorageError, match="already exists"):
        _create(store, charter_path)

    assert _bytes(accepted_path) == accepted_before
    assert (external / "sentinel").read_text(encoding="utf-8") == "do not touch"


@pytest.mark.parametrize(
    ("filename", "replacement"),
    (
        ("manifest.json", b"{not-json\n"),
        (
            "manifest.json",
            b'{"schema_version":"formal-run/v1","unexpected":true}\n',
        ),
        ("raw_response.json", b'{"result":{"accepted":false}}\n'),
        ("corrections.json", b'[{"replacement":"history erased"}]\n'),
    ),
)
def test_corrupt_or_replaced_bundle_fails_without_mutating_another_run(
    tmp_path, charter_path, filename, replacement
):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path, "control")
    _create(store, charter_path, "target")
    control_path = tmp_path / "formal-runs/control"
    control_before = _bytes(control_path)
    (tmp_path / "formal-runs/target" / filename).write_bytes(replacement)

    with pytest.raises(FormalRunStorageError):
        store.verify("target")

    assert _bytes(control_path) == control_before


def test_undeclared_file_invalidates_the_complete_formal_bundle(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path)
    (tmp_path / "formal-runs/accepted/injected.txt").write_text(
        "undeclared",
        encoding="utf-8",
    )

    with pytest.raises(FormalRunStorageError, match="undeclared files"):
        store.verify("accepted")


def test_missing_parent_lineage_is_rejected(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)

    with pytest.raises(FormalRunStorageError, match="does not exist safely"):
        store.create_linked_rerun(
            parent_run_id="missing-parent",
            run_id="child",
            change_reason="code changed",
            diff={"code": ["old", "new"]},
            charter=load_charter(charter_path),
            raw_response={"result": {}},
            proposal={},
            confirmed_result={},
            lineage_inputs=_lineage(),
        )

    assert not (tmp_path / "formal-runs/child").exists()


def test_child_verification_fails_when_parent_is_later_tampered(tmp_path, charter_path):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path, "parent")
    store.create_linked_rerun(
        parent_run_id="parent",
        run_id="child",
        change_reason="controlled rerun",
        diff={"configuration": ["old", "new"]},
        charter=load_charter(charter_path),
        raw_response={"result": {"accepted": True}},
        proposal={"accepted": True},
        confirmed_result={"accepted": True},
        lineage_inputs=_lineage(),
    )
    (tmp_path / "formal-runs/parent/raw_response.json").write_text(
        '{"result":{"accepted":false}}\n',
        encoding="utf-8",
    )

    with pytest.raises(FormalRunStorageError, match="payload hash mismatch"):
        store.verify("child")


def test_exact_replay_has_no_live_runner_escape_hatch(tmp_path, charter_path, monkeypatch):
    store = FormalRunStore(tmp_path)
    _create(store, charter_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("live runner was reached")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert replay_recorded_response(store, "accepted").matched is True
    with pytest.raises(TypeError):
        replay_recorded_response(store, "accepted", runner=forbidden)
