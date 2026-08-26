from __future__ import annotations

import pytest
from pydantic import ValidationError

from career_evidence_graph.audit.models import AuditAction, AuditQuestion, AuditSnapshot


def test_audit_models_are_strict_and_schema_versioned() -> None:
    question = AuditQuestion(
        id="question-1",
        reason="The record establishes a bounded delivery fact; capability remains unverified.",
        prompt="What did you decide and verify?",
        area="implementation",
        status="unanswered",
    )
    assert question.schema_version == "audit-question/v1"
    with pytest.raises(ValidationError):
        AuditAction(action="answer", answer="x", unexpected=True)
    with pytest.raises(ValidationError):
        AuditSnapshot(
            audit_id="audit-1",
            contribution_id="contrib-stoa-authorization-boundary",
            status="active",
            questions=(question,),
            answers=(),
            inspected_facts=(),
            limitations=(),
            attribution=None,
            conclusion=None,
            bogus="nope",
        )
