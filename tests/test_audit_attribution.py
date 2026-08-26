from pathlib import Path

from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit

FIXTURE = Path("validation/fixtures/stoa/v1/known-good.json")
MANIFEST = FIXTURE.parent / "source-manifest.json"


def test_ownership_round_precedes_assistance_and_conflict_is_retained(tmp_path):
    snapshot = start_audit(
        workspace=tmp_path,
        fixture_path=FIXTURE,
        manifest_path=MANIFEST,
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-attribution",
    )
    store = AuditStore(tmp_path)
    answers = ("我做了设计并验证了结果", "我定位并修复了故障", "我完成了运行检查", "这部分不是我做的")
    for answer in answers:
        snapshot = transition_audit(store, snapshot, AuditAction(action="answer", answer=answer))
    assert snapshot.responsibility_round is not None
    assert snapshot.responsibility_round.ownership == "other-person-owned"
    assert snapshot.attribution_conflicts
    assert snapshot.assistance_round is None
