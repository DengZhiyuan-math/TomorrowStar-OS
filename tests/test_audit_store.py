from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStorageError, AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _start(workspace: Path, audit_id: str = "audit-store"):
    return start_audit(
        workspace=workspace,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=audit_id,
    )


def test_pause_and_resume_replace_one_snapshot_without_losing_business_history(
    tmp_path: Path,
) -> None:
    started = _start(tmp_path)
    store = AuditStore(tmp_path)
    answered = transition_audit(
        store.read(started.audit_id), AuditAction(action="answer", answer="I designed it.")
    )
    store.replace(answered)
    paused = transition_audit(store.read(started.audit_id), AuditAction(action="pause"))
    store.replace(paused)
    resumed = transition_audit(store.read(started.audit_id), AuditAction(action="resume"))
    store.replace(resumed)

    restored = store.read(started.audit_id)
    assert restored == resumed
    assert restored.inspected_facts == started.inspected_facts
    assert restored.questions == answered.questions
    assert restored.answers == answered.answers
    assert restored.coverage == answered.coverage
    assert restored.contradictions == answered.contradictions
    assert restored.attribution == answered.attribution
    assert restored.conclusion == answered.conclusion
    assert restored.conclusion_reviews == answered.conclusion_reviews


def test_store_rejects_duplicate_missing_corrupt_unsafe_and_directly_linked_records(
    tmp_path: Path,
) -> None:
    started = _start(tmp_path)
    store = AuditStore(tmp_path)

    with pytest.raises(AuditStorageError, match="already exists"):
        store.create(started)
    with pytest.raises(AuditStorageError, match="missing"):
        store.read("audit-missing")
    with pytest.raises(AuditStorageError, match="unsafe"):
        store.read("../../audit-escape")

    path = store.path(started.audit_id)
    path.write_text('{"unexpected": true}', encoding="utf-8")
    with pytest.raises(AuditStorageError, match="corrupt"):
        store.read(started.audit_id)

    linked_id = "audit-linked"
    linked_path = store.path_for(linked_id)
    linked_path.parent.mkdir(parents=True, exist_ok=True)
    linked_path.symlink_to(path)
    with pytest.raises(AuditStorageError, match="linked"):
        store.read(linked_id)


def test_failed_replacement_preserves_the_prior_complete_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = _start(tmp_path)
    store = AuditStore(tmp_path)
    before = store.path(started.audit_id).read_bytes()
    paused = transition_audit(store.read(started.audit_id), AuditAction(action="pause"))

    def interrupted_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr("career_evidence_graph.audit.store.os.replace", interrupted_replace)
    with pytest.raises(AuditStorageError, match="replacement"):
        store.replace(paused)
    assert store.path(started.audit_id).read_bytes() == before
