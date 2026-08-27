from __future__ import annotations

from pathlib import Path

import pytest

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.workflow import AuditWorkflowError, start_audit, transition_audit

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _start(tmp_path: Path, audit_id: str = "audit-regression"):
    return start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=audit_id,
    )


def test_early_attribution_signal_requires_ownership_then_assistance_before_resuming(
    tmp_path: Path,
):
    snapshot = _start(tmp_path)
    signalled = transition_audit(
        snapshot,
        AuditAction(action="answer", answer="This implementation was not me; the team did it."),
    )
    assert signalled.questions[-1].turn == "ownership"

    owned = transition_audit(
        signalled,
        AuditAction(action="answer", answer="The team owned this work."),
    )
    assert owned.questions[-1].turn == "assistance"
    resumed = transition_audit(
        owned,
        AuditAction(action="answer", answer="No outside assistance."),
    )
    assert resumed.status == "active"
    assert resumed.questions[-1].turn == "capability"
    assert resumed.coverage[0].strongest_capability is None
    assert resumed.attribution_records[0].ownership == "team-owned"


def test_question_target_must_match_the_one_active_question(tmp_path: Path):
    snapshot = _start(tmp_path)
    with pytest.raises(AuditWorkflowError, match="active question"):
        transition_audit(
            snapshot,
            AuditAction(
                action="answer",
                answer="I designed and verified it.",
                question_id="question-implementation-hard-0-99",
            ),
        )


def test_area_skip_never_creates_an_attribution_capability_entry(tmp_path: Path):
    snapshot = _start(tmp_path)
    skipped = transition_audit(
        snapshot, AuditAction(action="skip", answer="Self-rating: uncertain")
    )
    entry = skipped.conclusion.entries[0]
    assert entry.area == "implementation"
    assert entry.verification == "self-assessed-unverified"
    assert entry.area not in {"responsibility", "assistance"}
