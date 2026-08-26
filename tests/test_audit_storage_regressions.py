from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit.store import AuditStorageError, AuditStore
from career_evidence_graph.audit.workflow import start_audit

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def test_complete_event_chain_rejects_historical_tampering(tmp_path: Path) -> None:
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-tamper",
    )
    events = AuditStore(tmp_path).path(snapshot.audit_id) / "events.jsonl"
    events.write_text("", encoding="utf-8")
    with pytest.raises(AuditStorageError):
        AuditStore(tmp_path).read(snapshot.audit_id)
