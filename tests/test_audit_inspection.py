from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_evidence_graph.audit import workflow
from career_evidence_graph.audit.store import AuditStorageError, AuditStore
from career_evidence_graph.audit.workflow import AuditWorkflowError, inspect_contribution
from career_evidence_graph.validation.store import FormalRunStorageError

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = ROOT / "validation/fixtures/stoa/v1/source-manifest.json"


@pytest.mark.phase03_original_probe
def test_inspection_order_is_stable() -> None:
    facts, limitations = inspect_contribution(
        FIXTURE, MANIFEST, "contrib-stoa-authorization-boundary"
    )
    assert facts == tuple(sorted(facts, key=lambda item: (item.evidence_id, item.source_locator)))
    assert facts and limitations
    assert all("ownership" not in fact.statement.lower() for fact in facts)


@pytest.mark.phase03_original_probe
def test_inspection_preserves_duplicate_source_locators(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = workflow._fixture(FIXTURE)
    links = fixture.claim_evidence_links
    duplicate_locator = links[0].model_copy(update={"evidence_id": links[1].evidence_id})
    monkeypatch.setattr(
        workflow,
        "_fixture",
        lambda _: fixture.model_copy(
            update={"claim_evidence_links": (links[0], duplicate_locator, *links[2:])}
        ),
    )
    facts, _ = inspect_contribution(FIXTURE, MANIFEST, "contrib-stoa-authorization-boundary")
    assert sum(fact.source_locator == links[0].section_locator for fact in facts) == 2


@pytest.mark.phase03_original_probe
def test_inspection_rejects_missing_contribution() -> None:
    with pytest.raises(AuditWorkflowError, match="Contribution is missing"):
        inspect_contribution(FIXTURE, MANIFEST, "contrib-stoa-does-not-exist")


@pytest.mark.phase03_original_probe
def test_inspection_rejects_empty_linked_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = workflow._fixture(FIXTURE)
    contribution = fixture.contributions[0]
    monkeypatch.setattr(
        workflow,
        "_fixture",
        lambda _: fixture.model_copy(
            update={
                "claim_evidence_links": tuple(
                    link
                    for link in fixture.claim_evidence_links
                    if link.claim_id not in contribution.claim_ids
                )
            }
        ),
    )
    with pytest.raises(AuditWorkflowError, match="no linked evidence"):
        inspect_contribution(FIXTURE, MANIFEST, contribution.id)


@pytest.mark.phase03_original_probe
def test_inspection_rejects_unverified_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    with pytest.raises((FormalRunStorageError, ValueError)):
        inspect_contribution(FIXTURE, manifest, "contrib-stoa-authorization-boundary")


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
