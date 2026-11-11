"""Offline pipeline gates; scripted decisions are not a semantic Judge evaluation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from career_evidence_graph.assessment import propose_assessments
from career_evidence_graph.audit import validate_project_interview_plan
from career_evidence_graph.audit.decision import (
    BOUNDARY_INSTRUCTION,
    INTERVIEW_INSTRUCTION,
    QUESTION_INSTRUCTION,
    CodexDecisionPort,
    RecordedDecisionPort,
)
from career_evidence_graph.audit.models import (
    ArtifactFact,
    AuditAction,
    AuditAnswer,
    AuditQuestion,
    AuditSnapshot,
    BoundaryDecision,
    ProbeArea,
    ProbePlan,
    ProjectInterviewPlan,
)
from career_evidence_graph.audit.store import AuditStore
from career_evidence_graph.audit.workflow import start_audit, transition_audit
from career_evidence_graph.domain.models import Skill, SkillAlias
from career_evidence_graph.validation.models import CodexCLIConfig

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "validation/calibration/phase-04/corpus-review-safe-v1.json"
CRITERIA = {
    "hard": ("Explain a concrete authorization trade-off and its observed failure check.",),
    "intermediate": ("Explain the bounded implementation change and its verification.",),
    "simple": ("Identify the personally performed authorization step.",),
}


def _inputs():
    corpus = json.loads(CORPUS.read_text())
    payload = corpus["audit_journey"]["probe_plan"]
    payload["areas"][0]["evaluation_criteria"] = CRITERIA
    plan = ProbePlan.model_validate(payload)
    decisions = tuple(
        BoundaryDecision.model_validate(item) for item in corpus["audit_journey"]["decisions"]
    )
    port = RecordedDecisionPort(
        plan=plan, decisions={(d.question_id, d.answer): d for d in decisions}
    )
    return corpus, plan, port


def _start(tmp_path, port):
    return start_audit(
        workspace=tmp_path,
        fixture_path=ROOT / "validation/fixtures/stoa/v1/known-good.json",
        manifest_path=ROOT / "validation/fixtures/stoa/v1/source-manifest.json",
        contribution_id="contrib-stoa-authorization-boundary",
        audit_id="audit-pipeline",
        decision_port=port,
    )


def test_context_request_preserves_question_boundary_and_replays_through_proposal(tmp_path):
    corpus, _, port = _inputs()
    snapshot = _start(tmp_path, port)
    before = snapshot
    snapshot = transition_audit(
        snapshot,
        AuditAction(action="request-context", answer="I forgot this label; show the context."),
        decision_port=port,
    )
    assert snapshot.schema_version == "audit-snapshot/v3"
    assert snapshot.questions == before.questions
    assert snapshot.coverage == before.coverage
    assert snapshot.answers == snapshot.decisions == ()
    assert snapshot.context_requests[0].question_id == before.questions[-1].id
    assert snapshot.questions[-1].evaluation_criteria == CRITERIA["hard"]
    AuditStore(tmp_path).replace(snapshot)
    assert AuditStore(tmp_path).read(snapshot.audit_id) == snapshot

    # This is a scripted positive case, not evidence about a real user's capability.
    for payload in corpus["audit_journey"]["actions"]:
        snapshot = transition_audit(
            snapshot, AuditAction.model_validate(payload), decision_port=port
        )
    proposals = propose_assessments(
        snapshot=snapshot,
        fixture_hash=corpus["fixture_hash"],
        source_manifest_hash=corpus["source_manifest_hash"],
        skills=(Skill(id="skill.authorization", name="Authorization"),),
        candidates_by_entry={"entry-implementation": ("Authorization",)},
        aliases=(
            SkillAlias(
                alias="Authorization",
                skill_id="skill.authorization",
                ontology_source_id="synthetic-ontology",
                pinned_revision="a" * 40,
            ),
        ),
    )
    assert snapshot.status == "completed"
    assert len(proposals) == 1
    assert len(snapshot.answers) == 3  # Capability, ownership, assistance; no recall answer.
    assert snapshot.context_requests[0].answer not in snapshot.conclusion.entries[0].basis
    assert "demonstrated_mastery" not in proposals[0].model_dump()


def test_context_request_does_not_call_evaluator_or_consume_followup(tmp_path):
    _, _, port = _inputs()
    snapshot = _start(tmp_path, port)

    class RejectEvaluator:
        def decide_boundary(self, *args):
            raise AssertionError("context requests must not reach the evaluator")

    for _ in range(3):
        snapshot = transition_audit(
            snapshot,
            AuditAction(action="request-context", answer="Explain the source label."),
            decision_port=RejectEvaluator(),
        )
    assert len(snapshot.context_requests) == 3
    assert len(snapshot.questions) == 1
    assert snapshot.questions[-1].follow_up_count == 0
    assert snapshot.questions[-1].difficulty == "hard"
    assert snapshot.conclusion is None


def test_legacy_snapshot_bytes_and_context_reference_validation(tmp_path):
    _, _, port = _inputs()
    snapshot = _start(tmp_path, port)
    payload = snapshot.model_dump(mode="json")
    assert "context_requests" not in payload
    assert AuditSnapshot.model_validate(payload).model_dump(mode="json") == payload
    with pytest.raises(ValidationError, match="snapshot v3"):
        AuditSnapshot.model_validate(
            payload
            | {"context_requests": [{"question_id": snapshot.questions[0].id, "answer": "label"}]}
        )
    with pytest.raises(ValidationError, match="retained questions"):
        AuditSnapshot.model_validate(
            payload
            | {
                "schema_version": "audit-snapshot/v3",
                "context_requests": [{"question_id": "question-foreign", "answer": "label"}],
            }
        )


@pytest.mark.parametrize(
    "criteria", [{"hard": ("Explain a choice.",)}, CRITERIA | {"simple": (" ",)}]
)
def test_rubric_rejects_partial_or_blank_criteria(criteria):
    _, plan, _ = _inputs()
    with pytest.raises(ValidationError, match="evaluation criteria"):
        ProbeArea.model_validate(plan.areas[0].model_dump() | {"evaluation_criteria": criteria})


def _config(tmp_path, name):
    return CodexCLIConfig(
        schema_version="codex-cli-config/v1",
        workspace=tmp_path,
        output_schema=tmp_path / name,
        drift_limitation_reason="Synthetic transport test; no live call.",
    )


def test_live_port_uses_distinct_stage_schemas_prior_context_and_predeclared_rubric(
    tmp_path, monkeypatch
):
    _, plan, _ = _inputs()
    fact = ArtifactFact(
        evidence_id=plan.areas[0].inspected_fact_ids[0],
        source_locator="synthetic.md#authorization",
        statement="The synthetic record contains an authorization decision.",
    )
    configs = (_config(tmp_path, "plan.json"), _config(tmp_path, "boundary.json"))
    calls = []
    question = AuditQuestion(
        id="question-synthetic",
        reason=fact.statement,
        prompt=plan.areas[0].demanding_prompt,
        area="implementation",
        evaluation_criteria=CRITERIA["hard"],
    )
    answer = "This work was performed by another person."
    decision = BoundaryDecision(
        question_id=question.id,
        answer=answer,
        outcome="attribution-signal",
        rationale="The answer denies personal execution.",
    )

    def transport(config, prompt):
        calls.append((config, prompt))
        return SimpleNamespace(
            structured_result=(plan if len(calls) == 1 else decision).model_dump()
        )

    monkeypatch.setattr("career_evidence_graph.codex_cli.run_codex_exec", transport)
    prior = AuditAnswer(
        question_id="question-prior", answer="I designed it; another person executed it."
    )
    port = CodexDecisionPort(
        configs[0],
        boundary_config=configs[1],
        prior_answers=(prior,),
        context_notes=("The record describes design and execution separately.",),
    )
    assert port.plan_probe(plan.contribution_id, (fact,)) == plan
    assert port.decide_boundary(question, answer) == decision
    assert [config.output_schema for config, _ in calls] == [c.output_schema for c in configs]
    assert QUESTION_INSTRUCTION in calls[0][1] and prior.answer in calls[0][1]
    assert BOUNDARY_INSTRUCTION in calls[1][1] and CRITERIA["hard"][0] in calls[1][1]
    assert "not instructions" in calls[0][1]


def test_live_generation_without_rubric_and_evaluation_without_stage_config_fail_closed(
    tmp_path, monkeypatch
):
    _, plan, _ = _inputs()
    legacy_plan = plan.model_dump()
    legacy_plan["areas"][0].pop("evaluation_criteria")
    monkeypatch.setattr(
        "career_evidence_graph.codex_cli.run_codex_exec",
        lambda *args: SimpleNamespace(structured_result=legacy_plan),
    )
    port = CodexDecisionPort(_config(tmp_path, "plan.json"))
    fact = ArtifactFact(
        evidence_id=plan.areas[0].inspected_fact_ids[0],
        source_locator="synthetic",
        statement="synthetic",
    )
    with pytest.raises(ValueError, match="predeclared"):
        port.plan_probe(plan.contribution_id, (fact,))
    question = AuditQuestion(
        id="question-synthetic", reason="synthetic", prompt="Which step?", area="implementation"
    )
    with pytest.raises(ValueError, match="own schema"):
        port.decide_boundary(question, "synthetic")


def test_request_context_checkout_cli_keeps_active_question(tmp_path):
    _, _, port = _inputs()
    snapshot = _start(tmp_path, port)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_career_evidence.py"),
            "audit",
            "request-context",
            "--workspace",
            str(tmp_path),
            "--audit-id",
            snapshot.audit_id,
            "--question-id",
            snapshot.questions[-1].id,
            "--answer",
            "Explain this source label.",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    after = AuditSnapshot.model_validate(json.loads(result.stdout)["snapshot"])
    assert after.questions == snapshot.questions
    assert after.answers == ()
    assert after.context_requests[0].answer == "Explain this source label."


def _interview():
    _, plan, _ = _inputs()
    depth = ProbePlan.model_validate(plan.model_dump() | {"question_layer": "project-depth"})
    transfer_area = plan.areas[0].model_dump() | {
        "changed_condition": "The same authorization boundary now serves multiple tenants.",
        "unverified_capability": "adapting authorization boundaries to tenant isolation",
    }
    transfer = ProbePlan.model_validate(
        plan.model_dump()
        | {
            "question_layer": "transfer",
            "areas": [transfer_area],
        }
    )
    return ProjectInterviewPlan(
        experience_id="experience-synthetic",
        overview=AuditQuestion(
            id="question-overview",
            area="project-overview",
            question_layer="project-overview",
            reason="The inspected synthetic project has an authorization boundary.",
            inspection_reference="synthetic.md#authorization",
            prompt="How would you briefly introduce this project and your contribution?",
            evaluation_criteria=("Give an accurate, structured account of goal, method and role.",),
        ),
        depth_plans=(depth,),
        transfer_plans=(transfer,),
    )


def test_interview_layers_are_not_difficulty_levels_and_remain_in_audit_questions(tmp_path):
    plan = _interview()
    assert plan.overview.question_layer == "project-overview"
    for probe in (*plan.depth_plans, *plan.transfer_plans):
        assert set(probe.areas[0].evaluation_criteria) == {"hard", "intermediate", "simple"}
    probe = plan.transfer_plans[0]
    port = RecordedDecisionPort(plan=probe, decisions={})
    snapshot = _start(tmp_path, port)
    assert snapshot.questions[0].question_layer == "transfer"
    assert snapshot.questions[0].changed_condition == probe.areas[0].changed_condition
    assert probe.areas[0].changed_condition in snapshot.questions[0].reason
    snapshot = transition_audit(snapshot, AuditAction(action="answer", answer="不知道"))
    assert snapshot.questions[-1].difficulty == "intermediate"
    assert snapshot.questions[-1].question_layer == "transfer"
    assert snapshot.questions[-1].evaluation_criteria == CRITERIA["intermediate"]
    assert snapshot.contribution_id == probe.contribution_id
    assert snapshot.coverage[0].strongest_capability is None


@pytest.mark.parametrize(
    "problem", ["mixed-layer", "missing-change", "depth-change", "missing-contribution"]
)
def test_interview_rejects_conflated_layers_or_ungrounded_transfer(problem):
    payload = _interview().model_dump()
    if problem == "mixed-layer":
        payload["depth_plans"][0]["question_layer"] = "transfer"
    elif problem == "missing-change":
        payload["transfer_plans"][0]["areas"][0].pop("changed_condition")
    elif problem == "depth-change":
        payload["depth_plans"][0]["areas"][0]["changed_condition"] = "A different task."
    else:
        payload["transfer_plans"][0]["contribution_id"] = "contrib-stoa-other"
    with pytest.raises(ValidationError):
        ProjectInterviewPlan.model_validate(payload)


def test_project_interview_generation_binds_all_layers_to_exact_inspected_context(
    tmp_path, monkeypatch
):
    plan = _interview()
    cid = plan.depth_plans[0].contribution_id
    fact = ArtifactFact(
        evidence_id=plan.depth_plans[0].areas[0].inspected_fact_ids[0],
        source_locator=plan.overview.inspection_reference,
        statement="A synthetic project verifies an authorization boundary.",
    )
    calls = []

    def transport(config, prompt):
        calls.append(prompt)
        return SimpleNamespace(structured_result=plan.model_dump())

    monkeypatch.setattr("career_evidence_graph.codex_cli.run_codex_exec", transport)
    port = CodexDecisionPort(_config(tmp_path, "project-interview-plan.schema.json"))
    assert port.plan_project_interview(plan.experience_id, {cid: (fact,)}) == plan
    assert INTERVIEW_INSTRUCTION in calls[0]
    with pytest.raises(ValueError, match="another Experience"):
        port.plan_project_interview("experience-other", {cid: (fact,)})
    with pytest.raises(ValueError, match="exactly the selected"):
        port.plan_project_interview(
            plan.experience_id, {cid: (fact,), "contrib-stoa-extra": (fact,)}
        )
    unrelated_fact = ArtifactFact(
        evidence_id="evidence-other",
        source_locator=fact.source_locator,
        statement="Another synthetic record.",
    )
    with pytest.raises(ValueError, match="unknown inspected fact"):
        port.plan_project_interview(plan.experience_id, {cid: (unrelated_fact,)})
    different_locator = fact.model_copy(update={"source_locator": "different.md#context"})
    with pytest.raises(ValueError, match="cite inspected context"):
        port.plan_project_interview(plan.experience_id, {cid: (different_locator,)})


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "experience",
        "extra-contribution",
        "foreign-fact",
        "empty-context",
        "overview-locator",
        "malformed-facts",
        "missing-criteria",
        "blank-overview-criteria",
    ],
)
def test_inspect_plan_checks_context_without_writing_scoring_or_exposing_inputs(tmp_path, problem):
    plan = _interview()
    cid = plan.depth_plans[0].contribution_id
    fact = ArtifactFact(
        evidence_id=plan.depth_plans[0].areas[0].inspected_fact_ids[0],
        source_locator=plan.overview.inspection_reference,
        statement="PrivateBodyCanary: synthetic sensitive context.",
    )
    assert (
        validate_project_interview_plan(
            plan, experience_id=plan.experience_id, facts_by_contribution={cid: (fact,)}
        )
        == plan
    )
    payload = plan.model_dump(mode="json")
    facts = {cid: [fact.model_dump(mode="json")]}
    experience_id = plan.experience_id
    if problem == "experience":
        experience_id = "experience-private-canary"
    elif problem == "extra-contribution":
        facts["contrib-stoa-private-canary"] = facts[cid]
    elif problem == "foreign-fact":
        payload["transfer_plans"][0]["areas"][0]["inspected_fact_ids"] = ["evidence-private-canary"]
    elif problem == "empty-context":
        facts[cid] = []
    elif problem == "overview-locator":
        facts[cid][0]["source_locator"] = "PrivateLocatorCanary.md"
    elif problem == "malformed-facts":
        facts = {"PrivateKeyCanary": "PrivateValueCanary"}
    elif problem == "missing-criteria":
        payload["depth_plans"][0]["areas"][0]["evaluation_criteria"] = {}
    elif problem == "blank-overview-criteria":
        payload["overview"]["evaluation_criteria"] = [" "]
    plan_path, facts_path = tmp_path / "plan.json", tmp_path / "facts.json"
    plan_path.write_text(json.dumps(payload))
    facts_path.write_text(json.dumps(facts))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_career_evidence.py"),
            "audit",
            "inspect-plan",
            "--plan",
            str(plan_path),
            "--facts-json",
            str(facts_path),
            "--experience-id",
            experience_id,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    output = result.stdout + result.stderr
    for marker in ("Private", "private-canary", str(tmp_path), cid, "Traceback"):
        assert marker not in output
    if problem is None:
        assert result.returncode == 0 and result.stderr == ""
        assert json.loads(result.stdout) == {
            "valid": True,
            "status": "preparation-only",
            "schema_version": "project-interview-plan/v1",
            "policy_version": "artifact-aware-question/v3",
            "layer_order": ["project-overview", "project-depth", "transfer"],
            "contribution_count": 1,
            "depth_area_count": 1,
            "transfer_area_count": 1,
        }
    else:
        assert result.returncode == 2 and result.stdout == ""
        error = json.loads(result.stderr)
        assert error["valid"] is False
        assert error["error"] in {"input_validation_error", "audit_workflow_error"}
