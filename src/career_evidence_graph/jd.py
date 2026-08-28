"""Pure, source-bound comparison of one accepted JD packet and reviewed user truth."""

from __future__ import annotations

from pathlib import Path

from .assessment import (
    AssessmentRun,
    AssessmentWorkflowError,
    aggregate_user_skills,
    list_assessment_runs,
)
from .domain.models import (
    AcceptedJDPacket,
    CalibratedUserSkillResult,
    JDAnalysisResult,
    JDGap,
    JDMatchPolicy,
    JDReport,
    JDRequirement,
    JDRequirementJudgment,
)
from .validation.hashing import canonical_json_bytes, sha256_digest


class JDComparisonError(ValueError):
    """A packet or reviewed graph cannot truthfully be compared."""


def _graph_payload(
    records: tuple[AssessmentRun, ...], results: tuple[CalibratedUserSkillResult, ...]
) -> list[dict[str, object]]:
    return [
        {
            "assessment_id": record.proposal.id,
            "version_hash": record.version_hash,
            "admitted_assessment_ids": result.admitted_assessment_ids,
            "authority_label": result.authority_label,
            "skill_id": result.skill_id,
            "mastery": result.mastery,
            "contribution_id": record.proposal.contribution_id,
            "evidence_ids": record.proposal.source_envelope.evidence_ids
            if record.proposal.source_envelope
            else (),
        }
        for record, result in zip(records, results, strict=True)
    ]


def load_reviewed_user_graph(
    workspace: Path,
) -> tuple[tuple[AssessmentRun, ...], tuple[CalibratedUserSkillResult, ...], str]:
    """Reopen only complete, current, reviewed-user-truth assessment sidecars."""
    stored = list_assessment_runs(workspace)
    records = tuple(record for _run_id, record in stored)
    if not records:
        raise JDComparisonError("reviewed user graph is missing")
    for record in records:
        proposal = record.proposal
        if (
            proposal.source_envelope is None
            or proposal.source_envelope.authority_label != "reviewed-user-truth"
            or proposal.assessment_status == "derived-counterfactual"
            or record.admission.admission_status != "admitted"
            or not record.version_hash
        ):
            raise JDComparisonError(
                "reviewed user graph contains a non-user-truth or incomplete run"
            )
    try:
        results = aggregate_user_skills(records)
    except AssessmentWorkflowError as exc:
        raise JDComparisonError("reviewed user graph lineage is invalid") from exc
    if not results or any(result.authority_label != "reviewed-user-truth" for result in results):
        raise JDComparisonError("reviewed user graph did not produce user truth")
    results_by_assessment = {
        assessment_id: result
        for result in results
        for assessment_id in result.admitted_assessment_ids
    }
    if set(results_by_assessment) != {record.proposal.id for record in records}:
        raise JDComparisonError("reviewed user graph has detached admitted-assessment lineage")
    ordered = tuple(
        (record, results_by_assessment[record.proposal.id])
        for record in sorted(records, key=lambda item: item.proposal.id)
    )
    ordered_records = tuple(item[0] for item in ordered)
    ordered_results = tuple(item[1] for item in ordered)
    return (
        ordered_records,
        ordered_results,
        sha256_digest(canonical_json_bytes(_graph_payload(ordered_records, ordered_results))),
    )


def _judgment_for(
    requirement: JDRequirement,
    records: tuple[AssessmentRun, ...],
    results: tuple[CalibratedUserSkillResult, ...],
) -> JDRequirementJudgment:
    by_skill = {result.skill_id: result for result in results}
    record_by_assessment = {record.proposal.id: record for record in records}
    matched = [by_skill.get(skill_id) for skill_id in requirement.skill_ids]
    if any(item is None for item in matched):
        return JDRequirementJudgment(
            requirement_id=requirement.requirement_id,
            status="unsupported",
            skill_ids=requirement.skill_ids,
            limitation="No admitted reviewed-user-truth evidence exists for every exact Skill.",
        )
    resolved = tuple(item for item in matched if item is not None)
    evidence_records = tuple(
        record_by_assessment[result.baseline_assessment_id] for result in resolved
    )
    if any(
        record.proposal.source_envelope is None
        or record.proposal.source_envelope.authority_label != "reviewed-user-truth"
        for record in evidence_records
    ):
        raise JDComparisonError("requirement evidence is detached from reviewed user truth")
    contribution_ids = tuple(
        sorted({record.proposal.contribution_id for record in evidence_records})
    )
    evidence_ids = tuple(
        sorted(
            {
                evidence_id
                for record in evidence_records
                for evidence_id in record.proposal.source_envelope.evidence_ids
            }
        )
    )
    if not contribution_ids or not evidence_ids:
        return JDRequirementJudgment(
            requirement_id=requirement.requirement_id,
            status="uncertain",
            skill_ids=requirement.skill_ids,
            limitation="Exact-Skill result lacks admitted Contribution evidence.",
        )
    if all(result.mastery >= requirement.minimum_mastery for result in resolved):
        return JDRequirementJudgment(
            requirement_id=requirement.requirement_id,
            status="supported",
            skill_ids=requirement.skill_ids,
            contribution_ids=contribution_ids,
            evidence_ids=evidence_ids,
            evidence_skill_ids=requirement.skill_ids,
            established_capability=(
                "Admitted reviewed-user-truth evidence meets every supplied exact-Skill boundary."
            ),
            limitation="No requirement-specific limitation was supplied for this comparison.",
        )
    return JDRequirementJudgment(
        requirement_id=requirement.requirement_id,
        status="partially-supported",
        skill_ids=requirement.skill_ids,
        contribution_ids=contribution_ids,
        evidence_ids=evidence_ids,
        evidence_skill_ids=requirement.skill_ids,
        established_capability=(
            "Admitted reviewed-user-truth evidence exists for every exact Skill."
        ),
        limitation=(
            "Admitted exact-Skill evidence does not reach the supplied requirement boundary."
        ),
    )


def _weight(requirement: JDRequirement, policy: JDMatchPolicy) -> int:
    return policy.required_weight if requirement.priority == "required" else policy.preferred_weight


def _route(score: int, policy: JDMatchPolicy) -> str:
    if score >= policy.customized_min_score:
        return "customized-resume"
    if score >= policy.standard_min_score:
        return "standard-resume"
    return "abandon"


def compare_accepted_jd(
    packet: AcceptedJDPacket, workspace: Path, policy: JDMatchPolicy
) -> JDAnalysisResult:
    """Compare read-only reviewed truth with a validated packet and return one report."""
    records, results, graph_hash_before = load_reviewed_user_graph(workspace)
    judgments = tuple(
        _judgment_for(requirement, records, results) for requirement in packet.requirements
    )
    total_weight = sum(_weight(requirement, policy) for requirement in packet.requirements)
    earned = sum(
        _weight(requirement, policy)
        * (
            100
            if judgment.status == "supported"
            else policy.partially_supported_percent
            if judgment.status == "partially-supported"
            else 0
        )
        for requirement, judgment in zip(packet.requirements, judgments, strict=True)
    )
    raw_score = earned // total_weight
    core_missing = any(
        requirement.core_hard and judgment.status in {"unsupported", "uncertain"}
        for requirement, judgment in zip(packet.requirements, judgments, strict=True)
    )
    score = min(raw_score, policy.missing_core_cap) if core_missing else raw_score
    ordinary_route = _route(score, policy)
    gaps = tuple(
        JDGap(
            requirement_id=requirement.requirement_id,
            kind="missing-capability" if judgment.status == "unsupported" else "uncertainty",
            detail=judgment.limitation or "A supplied core requirement remains unresolved.",
        )
        for requirement, judgment in zip(packet.requirements, judgments, strict=True)
        if judgment.status in {"unsupported", "uncertain"}
    )
    graph_hash_after = sha256_digest(canonical_json_bytes(_graph_payload(records, results)))
    if graph_hash_before != graph_hash_after:
        raise JDComparisonError("comparison changed the reviewed graph")
    policy_hash = sha256_digest(canonical_json_bytes(policy))
    selected_contribution_ids = tuple(
        sorted({item for judgment in judgments for item in judgment.contribution_ids})
    )
    return JDAnalysisResult(
        packet_id=packet.packet_id,
        score=score,
        raw_score=raw_score,
        route=ordinary_route,
        ordinary_route=ordinary_route,
        route_reason=(
            "Core hard requirement capped the ordinary route."
            if core_missing
            else "Ordinary route follows the supplied inclusive policy threshold."
        ),
        judgments=judgments,
        gaps=gaps,
        selected_contribution_ids=selected_contribution_ids,
        policy_version=policy.policy_version,
        policy_hash=policy_hash,
        graph_hash_before=graph_hash_before,
        graph_hash_after=graph_hash_after,
        report=JDReport(
            concise=f"{score}/100 · {ordinary_route}",
            technical=(
                "Read-only comparison of reviewed-user-truth Contribution evidence; "
                "this report makes no application, interview, offer, hiring, or employment "
                "effectiveness claim."
            ),
        ),
    )
