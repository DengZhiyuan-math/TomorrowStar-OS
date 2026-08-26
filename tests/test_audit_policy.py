from career_evidence_graph.audit.models import AuditAction
from career_evidence_graph.audit.workflow import start_audit, transition_audit
from career_evidence_graph.audit.store import AuditStore
from pathlib import Path

FIXTURE = Path("validation/fixtures/stoa/v1/known-good.json")
MANIFEST = FIXTURE.parent / "source-manifest.json"


def test_questions_descend_after_one_incomplete_followup(tmp_path):
    snap = start_audit(workspace=tmp_path, fixture_path=FIXTURE, manifest_path=MANIFEST,
                       contribution_id="contrib-stoa-authorization-boundary", audit_id="audit-policy")
    assert snap.questions[0].difficulty == "hard"
    snap = transition_audit(AuditStore(tmp_path), snap, AuditAction(action="answer", answer="不完整"))
    assert snap.questions[-1].follow_up_count == 1
    snap = transition_audit(AuditStore(tmp_path), snap, AuditAction(action="answer", answer="不知道"))
    assert snap.questions[-1].difficulty == "intermediate"
    assert len({q.id for q in snap.questions}) == len(snap.questions)


def test_skip_preserves_verbatim_self_rating(tmp_path):
    snap = start_audit(workspace=tmp_path, fixture_path=FIXTURE, manifest_path=MANIFEST,
                       contribution_id="contrib-stoa-authorization-boundary", audit_id="audit-skip")
    snap = transition_audit(AuditStore(tmp_path), snap, AuditAction(action="skip", answer="自评：大约 7/10"))
    assert snap.coverage[0].status == "skipped"
    assert snap.coverage[0].self_rating == "自评：大约 7/10"
