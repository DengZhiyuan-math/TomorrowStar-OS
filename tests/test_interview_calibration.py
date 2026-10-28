import pytest

from career_evidence_graph.audit.models import AuditQuestion, BoundaryDecision
from career_evidence_graph.interview_calibration import (
    CalibrationCase,
    CalibrationObservation,
    evaluate_calibration,
)


def test_recall_failure_and_borrowed_work_block_calibration_even_with_stable_outputs():
    question = AuditQuestion(
        id="question-synthetic",
        reason="Inspect the design scope.",
        prompt="How does the design work?",
        area="technical-design",
        question_layer="project-depth",
        evaluation_criteria=("Explain the invariant.",),
    )
    case = CalibrationCase(
        case_id="recall",
        question=question,
        answer="Please explain this label.",
        inspected_context="Synthetic context.",
        expected_route="request-context",
        expected_outcome=None,
        expected_anchor_id=None,
    )
    observation = CalibrationObservation(
        case_id="recall",
        route="capability",
        boundary=BoundaryDecision(
            question_id=question.id,
            answer=case.answer,
            outcome="established",
            rationale="Incorrectly treated recall as capability.",
            strongest_capability="Expert implementation",
            next_higher_not_established="Operate the system",
        ),
        supported_anchor_id="anchor-90-95",
        rationale="Incorrect calibration result.",
    )
    result = evaluate_calibration((case,), ((observation,), (observation,), (observation,)))
    assert result["passed"] is False
    assert result["critical_failure_count"] == 3
    assert result["personal_scoring_authorized"] is False


def test_exact_case_coverage_and_three_attempts_are_required():
    with pytest.raises(ValueError, match="three attempts"):
        evaluate_calibration((), ())


def test_native_plan_schema_uses_exact_criteria_properties():
    import json
    import runpy
    from pathlib import Path

    from career_evidence_graph.audit.models import ProjectInterviewPlan

    module = runpy.run_path(str(Path(__file__).parents[1] / "scripts/run_interview_calibration.py"))
    schema = module["strict_output_schema"](ProjectInterviewPlan)
    assert "propertyNames" not in json.dumps(schema)
    criteria = schema["$defs"]["ProbeArea"]["properties"]["evaluation_criteria"]
    assert set(criteria["properties"]) == {"hard", "intermediate", "simple"}
    assert criteria["additionalProperties"] is False


def test_higher_anchor_inflation_is_critical_and_repeated_disagreement_is_retained():
    import json
    from pathlib import Path

    corpus = json.loads(
        (Path(__file__).parents[1] / "validation/calibration/interview-v1/corpus.json").read_text()
    )
    case = CalibrationCase.model_validate(
        next(c for c in corpus["cases"] if c["case_id"] == "bounded-task")
    )
    correct = CalibrationObservation(
        case_id=case.case_id,
        route=case.expected_route,
        boundary=BoundaryDecision(
            question_id=case.question.id,
            answer=case.answer,
            outcome="established",
            rationale="Retained independent bounded task evidence.",
            strongest_capability="Complete a common bounded task",
            next_higher_not_established="Own a system",
        ),
        supported_anchor_id=case.expected_anchor_id,
        rationale="Correct bounded anchor.",
    )
    inflated = correct.model_copy(update={"supported_anchor_id": "anchor-90-95"})
    result = evaluate_calibration((case,), ((correct,), (inflated,), (correct,)))
    assert result["passed"] is False
    assert result["critical_failure_count"] == 1
    assert result["unstable_cases"] == [case.case_id]
    assert len(result["results"]) == 3
