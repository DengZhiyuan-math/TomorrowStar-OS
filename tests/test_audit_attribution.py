from pathlib import Path

import pytest

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit

FIXTURE = Path("validation/fixtures/stoa/v1/known-good.json")
MANIFEST = FIXTURE.parent / "source-manifest.json"


def _start(tmp_path, audit_id="audit-attribution"):
    return start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id=audit_id,
    )


def _answer_until_responsibility(tmp_path, audit_id="audit-attribution"):
    snapshot = _start(tmp_path, audit_id)
    store = AuditStore(tmp_path)
    for answer in ("I designed it.", "I debugged it.", "I operated it."):
        snapshot = transition_audit(store, snapshot, AuditAction(action="answer", answer=answer))
    return store, snapshot


@pytest.mark.phase03_original_probe
def test_ownership_precedes_assistance(tmp_path):
    store, snapshot = _answer_until_responsibility(tmp_path)
    assert snapshot.questions[-1].area == "responsibility"
    assert snapshot.assistance_round is None
    snapshot = transition_audit(store, snapshot, AuditAction(action="answer", answer="I owned it."))
    assert snapshot.responsibility_round.ownership == "user-owned"
    assert snapshot.questions[-1].area == "assistance"


@pytest.mark.phase03_original_probe
def test_assistance_never_fills_ownership(tmp_path):
    store, snapshot = _answer_until_responsibility(tmp_path)
    snapshot = transition_audit(store, snapshot, AuditAction(action="answer", answer="not me"))
    snapshot = transition_audit(
        store, snapshot, AuditAction(action="answer", answer="A coding agent helped.")
    )
    assert snapshot.attribution.ownership == "other-person-owned"
    assert snapshot.attribution.assistance == "coding-agent-assisted"


@pytest.mark.phase03_original_probe
def test_attribution_values_round_trip_distinctly(tmp_path):
    cases = (
        ("I owned it.", "No outside assistance.", "user-owned", "none"),
        ("团队负责", "编码代理协助", "team-owned", "coding-agent-assisted"),
        ("not me", "external consultant", "other-person-owned", "third-party-assisted"),
    )
    for index, (ownership, assistance, expected_owner, expected_help) in enumerate(cases):
        store, snapshot = _answer_until_responsibility(tmp_path, f"audit-attribution-{index}")
        snapshot = transition_audit(store, snapshot, AuditAction(action="answer", answer=ownership))
        snapshot = transition_audit(
            store, snapshot, AuditAction(action="answer", answer=assistance)
        )
        assert (snapshot.attribution.ownership, snapshot.attribution.assistance) == (
            expected_owner,
            expected_help,
        )


@pytest.mark.phase03_original_probe
def test_conflict_preserves_documentary_and_user_claims(tmp_path):
    snapshot = _start(tmp_path)
    store = AuditStore(tmp_path)
    answers = (
        "我做了设计并验证了结果",
        "我定位并修复了故障",
        "我完成了运行检查",
        "这部分不是我做的",
    )
    for answer in answers:
        snapshot = transition_audit(store, snapshot, AuditAction(action="answer", answer=answer))
    assert snapshot.responsibility_round is not None
    assert snapshot.responsibility_round.ownership == "other-person-owned"
    assert snapshot.attribution_conflicts
    assert snapshot.assistance_round is None
