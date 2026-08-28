"""Pure, source-bound comparison of one accepted JD packet and reviewed user truth."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .assessment import (
    AssessmentRun,
    AssessmentWorkflowError,
    aggregate_user_skills,
    list_assessment_runs,
)
from .domain.invariants import (
    canonical_jd_contribution_selections,
    canonical_jd_gaps,
    canonical_jd_judgments,
    canonical_jd_requirements,
)
from .domain.models import (
    AcceptedJDPacket,
    CalibratedUserSkillResult,
    JDAnalysisResult,
    JDContributionSelection,
    JDGap,
    JDMatchPolicy,
    JDReport,
    JDRequirement,
    JDRequirementJudgment,
)
from .validation.hashing import canonical_json_bytes, sha256_digest


class JDComparisonError(ValueError):
    """A packet or reviewed graph cannot truthfully be compared."""


MAX_RAW_JD_BYTES = 262144
_UNSAFE_CODEPOINTS = frozenset({"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"})
_SAFE_SOURCE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


class JDIntakeError(ValueError):
    """A raw JD source cannot become a prepared packet.

    Error text intentionally names only a stable code and never echoes private source text.
    """

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}: {detail}")


@dataclass(frozen=True)
class PreparedJDIntake:
    """Validated, still-unaccepted source and recorded packet custody."""

    source_id: str
    source_hash: str
    source_bytes: int
    disclosures: tuple[str, ...]
    packet: AcceptedJDPacket
    accepted: bool = False


def _source_disclosures(text: str) -> tuple[str, ...]:
    """Return safe code-point labels without copying any private source text."""
    disclosures: set[str] = set()
    for codepoint in text:
        ordinal = ord(codepoint)
        if codepoint == "\x00" or (ordinal < 32 and codepoint not in {"\n", "\r", "\t"}):
            disclosures.add(f"control-U+{ordinal:04X}")
        elif codepoint in _UNSAFE_CODEPOINTS:
            disclosures.add(f"zero-width-U+{ordinal:04X}")
        elif 0x202A <= ordinal <= 0x202E or 0x2066 <= ordinal <= 0x2069:
            disclosures.add(f"bidi-U+{ordinal:04X}")
    return tuple(sorted(disclosures))


def _decode_raw_source(source: bytes, max_raw_jd_bytes: int) -> tuple[str, tuple[str, ...]]:
    if max_raw_jd_bytes < 1:
        raise JDIntakeError("jd-source-limit-invalid")
    if len(source) > max_raw_jd_bytes:
        raise JDIntakeError("jd-source-too-large")
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise JDIntakeError("jd-source-invalid-utf8") from exc
    disclosures = _source_disclosures(text)
    if disclosures:
        code = (
            "jd-source-unsafe-control"
            if any(item.startswith("control-") for item in disclosures)
            else "jd-source-unsafe-codepoint"
        )
        raise JDIntakeError(code, ",".join(disclosures))
    return text, disclosures


def prepare_jd_intake(
    source: bytes,
    source_id: str,
    recorded_proposal_json: bytes,
    *,
    max_raw_jd_bytes: int = MAX_RAW_JD_BYTES,
) -> PreparedJDIntake:
    """Validate one exact source and its independently recorded proposal without writes.

    The caller is responsible for collecting source bytes and proposal JSON.  This seam
    never invokes a provider, repairs input, accepts the packet, scores a JD, or writes
    any workspace state.
    """
    text, disclosures = _decode_raw_source(source, max_raw_jd_bytes)
    if not _SAFE_SOURCE_ID.fullmatch(source_id):
        raise JDIntakeError("jd-source-id-invalid")
    try:
        proposal_value = json.loads(recorded_proposal_json.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JDIntakeError("jd-proposal-invalid-json") from exc
    if not isinstance(proposal_value, dict):
        raise JDIntakeError("jd-proposal-invalid-json")
    try:
        packet = AcceptedJDPacket.model_validate(proposal_value)
    except ValidationError as exc:
        raise JDIntakeError("jd-proposal-invalid") from exc
    source_hash = sha256_digest(source)
    if packet.raw_source.source_id != source_id:
        raise JDIntakeError("jd-source-id-mismatch")
    if packet.raw_source.utf8_text != text or packet.raw_source.source_hash != source_hash:
        raise JDIntakeError("jd-source-hash-mismatch")
    return PreparedJDIntake(
        source_id=source_id,
        source_hash=source_hash,
        source_bytes=len(source),
        disclosures=disclosures,
        packet=packet,
    )


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


def _gap_for(
    requirement: JDRequirement,
    judgment: JDRequirementJudgment,
    results_by_skill: dict[str, CalibratedUserSkillResult],
) -> JDGap | None:
    """Preserve one non-interchangeable reason for each unsatisfied requirement."""
    if judgment.status == "supported":
        return None
    if judgment.status == "unsupported":
        kind = "missing-capability"
    elif judgment.status == "uncertain":
        kind = "missing-evidence"
    elif requirement.context_expectation and all(
        requirement.context_expectation not in results_by_skill[skill_id].supporting_contexts
        for skill_id in requirement.skill_ids
    ):
        kind = "context-mismatch"
    else:
        kind = "uncertainty"
    return JDGap(
        requirement_id=requirement.requirement_id,
        kind=kind,
        detail=judgment.limitation or "The accepted requirement remains unresolved.",
    )


def _is_evidence_strong_group(
    requirements: tuple[JDRequirement, ...],
    judgments_by_requirement: dict[str, JDRequirementJudgment],
    records: tuple[AssessmentRun, ...],
    results: tuple[CalibratedUserSkillResult, ...],
    policy: JDMatchPolicy,
) -> bool:
    """Allow the named route overlay only for direct high-confidence exact-Skill evidence."""
    records_by_id = {record.proposal.id: record for record in records}
    results_by_skill = {result.skill_id: result for result in results}
    eligible = tuple(
        requirement
        for requirement in requirements
        if requirement.core_hard and requirement.evidence_strong_eligible
    )
    for requirement in eligible:
        group = (
            tuple(
                item
                for item in requirements
                if item.linked_requirement_group_id == requirement.linked_requirement_group_id
            )
            if requirement.linked_requirement_group_id
            else (requirement,)
        )
        if all(
            judgments_by_requirement[item.requirement_id].status == "supported"
            and all(
                results_by_skill[skill_id].baseline_assessment_id in records_by_id
                and records_by_id[
                    results_by_skill[skill_id].baseline_assessment_id
                ].proposal.evidence_confidence
                >= policy.evidence_strong_min_confidence
                and records_by_id[
                    results_by_skill[skill_id].baseline_assessment_id
                ].proposal.source_envelope
                is not None
                and records_by_id[
                    results_by_skill[skill_id].baseline_assessment_id
                ].proposal.source_envelope.authority_label
                == "reviewed-user-truth"
                for skill_id in item.skill_ids
            )
            for item in group
        ):
            return True
    return False


def _selected_contributions(
    requirements: tuple[JDRequirement, ...],
    judgments_by_requirement: dict[str, JDRequirementJudgment],
) -> tuple[JDContributionSelection, ...]:
    """Select only Contribution evidence that already grounds a judgment."""
    selections_by_id: dict[str, JDContributionSelection] = {}
    for requirement in requirements:
        judgment = judgments_by_requirement[requirement.requirement_id]
        if judgment.status not in {"supported", "partially-supported"}:
            continue
        for contribution_id in judgment.contribution_ids:
            candidate = JDContributionSelection(
                contribution_id=contribution_id,
                source_byte_offset=requirement.source_span.start_byte,
                rank=0 if requirement.decision_critical else 1,
                reason=(
                    "Direct admitted reviewed-user-truth evidence grounds the exact Skill "
                    "constituent for this accepted requirement."
                ),
            )
            existing = selections_by_id.get(contribution_id)
            if existing is None or (
                candidate.rank,
                candidate.source_byte_offset,
                candidate.contribution_id,
            ) < (existing.rank, existing.source_byte_offset, existing.contribution_id):
                selections_by_id[contribution_id] = candidate
    return canonical_jd_contribution_selections(tuple(selections_by_id.values()))


def compare_accepted_jd(
    packet: AcceptedJDPacket, workspace: Path, policy: JDMatchPolicy
) -> JDAnalysisResult:
    """Compare read-only reviewed truth with a validated packet and return one report."""
    records, results, graph_hash_before = load_reviewed_user_graph(workspace)
    requirements = canonical_jd_requirements(packet.requirements)
    judgments = tuple(_judgment_for(requirement, records, results) for requirement in requirements)
    judgments = canonical_jd_judgments(judgments, requirements)
    judgments_by_requirement = {item.requirement_id: item for item in judgments}
    total_weight = sum(_weight(requirement, policy) for requirement in requirements)
    earned = sum(
        _weight(requirement, policy)
        * (
            100
            if judgment.status == "supported"
            else policy.partially_supported_percent
            if judgment.status == "partially-supported"
            else 0
        )
        for requirement, judgment in zip(requirements, judgments, strict=True)
    )
    raw_score = earned // total_weight
    core_missing = any(
        requirement.core_hard and judgment.status in {"unsupported", "uncertain"}
        for requirement, judgment in zip(requirements, judgments, strict=True)
    )
    capped_score = min(raw_score, policy.missing_core_cap) if core_missing else raw_score
    ordinary_route = _route(capped_score, policy)
    evidence_strong = _is_evidence_strong_group(
        requirements, judgments_by_requirement, records, results, policy
    )
    route = "customized-resume" if evidence_strong else ordinary_route
    route_trigger = "evidence-strong-match" if evidence_strong else "ordinary"
    results_by_skill = {result.skill_id: result for result in results}
    gaps = canonical_jd_gaps(
        tuple(
            gap
            for requirement in requirements
            if (
                gap := _gap_for(
                    requirement,
                    judgments_by_requirement[requirement.requirement_id],
                    results_by_skill,
                )
            )
            is not None
        ),
        requirements,
    )
    graph_hash_after = sha256_digest(canonical_json_bytes(_graph_payload(records, results)))
    if graph_hash_before != graph_hash_after:
        raise JDComparisonError("comparison changed the reviewed graph")
    policy_hash = sha256_digest(canonical_json_bytes(policy))
    selected_contributions = _selected_contributions(requirements, judgments_by_requirement)
    selected_contribution_ids = tuple(item.contribution_id for item in selected_contributions)
    strongest_match = next(
        (
            item.requirement_id
            for item in requirements
            if judgments_by_requirement[item.requirement_id].status == "supported"
        ),
        None,
    )
    core_gap = next(
        (
            item.requirement_id
            for item in requirements
            if item.core_hard and item.requirement_id in {gap.requirement_id for gap in gaps}
        ),
        None,
    )
    route_reason = (
        "evidence-strong-match"
        if evidence_strong
        else "Core hard requirement capped the ordinary route."
        if core_missing
        else "Ordinary route follows the supplied inclusive policy threshold."
    )
    return JDAnalysisResult(
        packet_id=packet.packet_id,
        score=capped_score,
        raw_score=raw_score,
        capped_score=capped_score,
        core_cap_applied=core_missing,
        route=route,
        ordinary_route=ordinary_route,
        route_trigger=route_trigger,
        route_reason=route_reason,
        judgments=judgments,
        gaps=gaps,
        selected_contribution_ids=selected_contribution_ids,
        selected_contributions=selected_contributions,
        policy_version=policy.policy_version,
        policy_hash=policy_hash,
        policy_snapshot=policy,
        graph_hash_before=graph_hash_before,
        graph_hash_after=graph_hash_after,
        report=JDReport(
            concise=f"{capped_score}/100 · {route}",
            technical=(
                "Read-only comparison of reviewed-user-truth Contribution evidence; "
                "this report makes no application, interview, offer, hiring, or employment "
                "effectiveness claim."
            ),
            header_score=capped_score,
            header_route=route,
            key_reasons=(route_reason,),
            strongest_match_requirement_id=strongest_match,
            most_important_core_gap_requirement_id=core_gap,
            customization_reason=route_reason,
            decision_critical_requirement_ids=tuple(
                item.requirement_id for item in requirements if item.decision_critical
            ),
            expanded_requirement_ids=tuple(item.requirement_id for item in requirements),
            selected_contribution_ids=selected_contribution_ids,
        ),
    )
