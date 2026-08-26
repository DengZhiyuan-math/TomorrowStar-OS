from __future__ import annotations

import pytest


def test_event_contract_rejects_unknown_action_and_bad_genesis() -> None:
    from career_evidence_graph.audit.models import AuditEventRecord

    with pytest.raises(ValueError):
        AuditEventRecord(
            sequence=0,
            action_type="unknown",
            action_id="action-start",
            action_digest="sha256:" + "0" * 64,
            snapshot_hash="sha256:" + "1" * 64,
            prev_event_hash=None,
            event_hash="sha256:" + "2" * 64,
        )
    with pytest.raises(ValueError):
        AuditEventRecord(
            sequence=1,
            action_type="start",
            action_id="action-start",
            action_digest="sha256:" + "0" * 64,
            snapshot_hash="sha256:" + "1" * 64,
            prev_event_hash=None,
            event_hash="sha256:" + "2" * 64,
        )
