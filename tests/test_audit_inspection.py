from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph.audit.store import AuditStorageError, AuditStore
from career_evidence_graph.audit.workflow import inspect_contribution
from career_evidence_graph.validation.store import FormalRunStorageError

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = ROOT / "validation/fixtures/stoa/v1/source-manifest.json"


def test_inspection_is_sorted_and_non_personal() -> None:
    facts, limitations = inspect_contribution(
        FIXTURE, MANIFEST, "contrib-stoa-authorization-boundary"
    )
    assert facts == tuple(sorted(facts, key=lambda item: (item.evidence_id, item.source_locator)))
    assert facts and limitations
    assert all("ownership" not in fact.statement.lower() for fact in facts)


def test_store_rejects_corrupt_snapshot_and_symlink(tmp_path: Path) -> None:
    store = AuditStore(tmp_path)
    with pytest.raises(AuditStorageError):
        store.read("audit-missing")


def test_inspection_rejects_duplicate_declared_links(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["fixture"]["claim_evidence_links"].append(payload["fixture"]["claim_evidence_links"][0])
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((FormalRunStorageError, ValueError)):
        inspect_contribution(altered, MANIFEST, "contrib-stoa-authorization-boundary")
