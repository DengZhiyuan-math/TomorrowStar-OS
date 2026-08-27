"""Pure cross-record validation for strict career-evidence fixtures."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from pydantic import ValidationError

from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import (
    MASTERY_ANCHORS,
    CareerEvidenceFixture,
    FixtureValidationResult,
    InvariantViolation,
    MasteryAnchor,
    MasteryAnchorFit,
    OntologyRelation,
    Skill,
    SkillAlias,
    SkillNormalizationRecord,
)


def validate_mastery_anchor_fit(score: int, fit: MasteryAnchorFit) -> MasteryAnchor:
    """Fail closed unless one accepted anchor contains this exact integer score."""
    matching = tuple(
        anchor
        for anchor in MASTERY_ANCHORS
        if anchor.inclusive_range[0] <= score <= anchor.inclusive_range[1]
    )
    if len(matching) != 1:
        raise ValueError("score must map to exactly one accepted mastery anchor")
    anchor = matching[0]
    if fit.anchor_id != anchor.anchor_id or fit.anchor_range != anchor.inclusive_range:
        raise ValueError("demonstrated mastery must fall inside its anchor")
    if fit.anchor_text != anchor.capability_text:
        raise ValueError("mastery anchor text does not match the accepted anchor")
    if not fit.anchor_basis.strip() or not fit.exact_score_basis.strip():
        raise ValueError("mastery anchor requires observable and exact-score bases")
    if not fit.next_anchor_not_established.strip():
        raise ValueError("mastery anchor requires the next anchor not established")
    return anchor


DIRECT_MASTERY_SOURCES = frozenset(
    {
        "experience",
        "credential",
        "title",
        "repository",
        "resume-skill-list",
        "ontology-relation",
    }
)


class FixtureValidationError(ValueError):
    """Raised when fixture schema or cross-record invariants reject input."""

    def __init__(self, violations: tuple[InvariantViolation, ...]) -> None:
        self.violations = violations
        super().__init__("career evidence fixture is invalid")


def _duplicate_violations(items: tuple[object, ...], name: str) -> list[InvariantViolation]:
    seen: set[str] = set()
    violations: list[InvariantViolation] = []
    for item in items:
        item_id = item.id  # type: ignore[attr-defined]
        if item_id in seen:
            violations.append(
                InvariantViolation(code=f"{name}.duplicate_id", path=f"{name}.{item_id}")
            )
        seen.add(item_id)
    return violations


def validate_contribution_lineage(
    fixture: CareerEvidenceFixture,
) -> tuple[InvariantViolation, ...]:
    """Reject every assessment path that is not Contribution-grounded."""
    contribution_ids = {item.id for item in fixture.contributions}
    violations: list[InvariantViolation] = []
    for assessment in fixture.assessments:
        path = f"assessments.{assessment.id}"
        if assessment.lineage.source_kind in DIRECT_MASTERY_SOURCES:
            violations.append(
                InvariantViolation(
                    code="assessment.direct-source-forbidden",
                    path=f"{path}.lineage.source_kind",
                )
            )
            continue
        if assessment.contribution_id not in contribution_ids:
            violations.append(
                InvariantViolation(
                    code="assessment.contribution_missing", path=f"{path}.contribution_id"
                )
            )
        if assessment.lineage.contribution_id != assessment.contribution_id:
            violations.append(
                InvariantViolation(
                    code="assessment.lineage_mismatch", path=f"{path}.lineage.contribution_id"
                )
            )
    return tuple(violations)


def validate_evidence_links(fixture: CareerEvidenceFixture) -> tuple[InvariantViolation, ...]:
    """Validate Evidence links without treating repeated links as new evidence."""
    claim_ids = {item.id for item in fixture.claims}
    evidence_ids = {item.id for item in fixture.evidence}
    seen_links: set[tuple[str, str]] = set()
    violations: list[InvariantViolation] = []
    for link in fixture.claim_evidence_links:
        link_key = (link.claim_id, link.evidence_id)
        path = f"claim_evidence_links.{link.claim_id}.{link.evidence_id}"
        if link_key in seen_links:
            violations.append(InvariantViolation(code="claim_evidence_link.duplicate", path=path))
        seen_links.add(link_key)
        if link.claim_id not in claim_ids:
            violations.append(
                InvariantViolation(code="claim_evidence_link.claim_missing", path=path)
            )
        if link.evidence_id not in evidence_ids:
            violations.append(
                InvariantViolation(code="claim_evidence_link.evidence_missing", path=path)
            )
    return tuple(violations)


def validate_claim_attribution(
    fixture: CareerEvidenceFixture,
) -> tuple[InvariantViolation, ...]:
    """Require definite fixture conclusions to retain user claim provenance."""
    claims_by_id = {claim.id: claim for claim in fixture.claims}
    contribution_ids = {contribution.id for contribution in fixture.contributions}
    evidence_ids = {evidence.id for evidence in fixture.evidence}
    resolved_evidence_by_claim: dict[str, set[str]] = {}
    for link in fixture.claim_evidence_links:
        if link.claim_id in claims_by_id and link.evidence_id in evidence_ids:
            resolved_evidence_by_claim.setdefault(link.claim_id, set()).add(link.evidence_id)
    violations: list[InvariantViolation] = []
    for assessment in fixture.assessments:
        path = f"assessments.{assessment.id}"
        if not assessment.basis_claim_ids:
            violations.append(InvariantViolation(code="assessment.basis_missing", path=path))
            continue
        if assessment.contribution_id not in contribution_ids:
            # A missing Contribution is a primary lineage failure. Basis claims cannot
            # be compared to that absent record, so avoid derivative mismatch noise.
            continue
        for claim_id in assessment.basis_claim_ids:
            claim = claims_by_id.get(claim_id)
            basis_path = f"{path}.basis_claim_ids.{claim_id}"
            if claim is None:
                violations.append(
                    InvariantViolation(code="assessment.basis_claim_missing", path=basis_path)
                )
                continue
            if not resolved_evidence_by_claim.get(claim_id):
                violations.append(
                    InvariantViolation(
                        code="assessment.basis_claim_evidence_missing", path=basis_path
                    )
                )
            if claim.contribution_id != assessment.contribution_id:
                violations.append(
                    InvariantViolation(code="assessment.basis_claim_mismatch", path=basis_path)
                )
            if assessment.assessment_status != "reviewed":
                continue
            if claim.responsibility != "user":
                violations.append(
                    InvariantViolation(code="assessment.definite_claim_not_user", path=basis_path)
                )
            if claim.confirmation_status != "confirmed":
                violations.append(
                    InvariantViolation(
                        code="assessment.definite_claim_unconfirmed", path=basis_path
                    )
                )
            if claim.completion_status in {"partial", "unresolved", "planned_only"}:
                violations.append(
                    InvariantViolation(code="assessment.definite_claim_unresolved", path=basis_path)
                )
            if claim.assistance != "none":
                violations.append(
                    InvariantViolation(code="assessment.definite_claim_assisted", path=basis_path)
                )
    return tuple(violations)


def validate_user_skill_views(
    fixture: CareerEvidenceFixture,
) -> tuple[InvariantViolation, ...]:
    """Keep one exact Skill view separate from confidence, duration, and JD data."""
    assessments_by_id = {assessment.id: assessment for assessment in fixture.assessments}
    skill_ids = {skill.id for skill in fixture.skills}
    assessed_skill_ids = {assessment.skill_id for assessment in fixture.assessments}
    views_by_skill: dict[str, list[object]] = {}
    violations: list[InvariantViolation] = []
    for assessment in fixture.assessments:
        if assessment.skill_id not in skill_ids:
            violations.append(
                InvariantViolation(
                    code="assessment.skill_missing",
                    path=f"assessments.{assessment.id}.skill_id",
                )
            )
    for view in fixture.user_skill_views:
        views_by_skill.setdefault(view.skill_id, []).append(view)
        view_path = f"user_skill_views.{view.skill_id}"
        if view.skill_id not in skill_ids:
            violations.append(InvariantViolation(code="user-skill.skill_missing", path=view_path))
        if view.skill_id not in assessed_skill_ids:
            violations.append(
                InvariantViolation(code="user-skill.without-assessment", path=view_path)
            )
        for assessment_id in view.assessment_ids:
            assessment = assessments_by_id.get(assessment_id)
            path = f"{view_path}.assessment_ids.{assessment_id}"
            if assessment is None:
                violations.append(
                    InvariantViolation(code="user-skill.assessment_missing", path=path)
                )
            elif assessment.skill_id != view.skill_id:
                violations.append(InvariantViolation(code="user-skill.skill_mismatch", path=path))
    for skill_id in sorted(views_by_skill):
        if len(views_by_skill[skill_id]) > 1:
            violations.append(
                InvariantViolation(code="user-skill.duplicate", path=f"user_skill_views.{skill_id}")
            )
    for skill_id in sorted(assessed_skill_ids - set(views_by_skill)):
        violations.append(InvariantViolation(code="user-skill.missing", path=skill_id))
    return tuple(violations)


def _normalized_text(value: str) -> str:
    """Normalize display variants deterministically without altering their source text."""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def normalize_skill_metadata(
    skills: tuple[Skill, ...],
    aliases: tuple[SkillAlias, ...] = (),
    ontology_relations: tuple[OntologyRelation, ...] = (),
) -> tuple[SkillNormalizationRecord, ...]:
    """Return reviewable alias and relation metadata without changing any fixture."""
    skills_by_id = {skill.id: skill for skill in skills}
    alias_groups: dict[str, list[SkillAlias]] = {}
    for alias in aliases:
        alias_groups.setdefault(_normalized_text(alias.alias), []).append(alias)

    records: list[SkillNormalizationRecord] = []
    for normalized_text, group in alias_groups.items():
        ordered_group = sorted(
            group,
            key=lambda alias: (
                alias.alias,
                alias.skill_id,
                alias.ontology_source_id,
                alias.pinned_revision,
            ),
        )
        representative = ordered_group[0]
        candidate_skill_ids = tuple(
            sorted({alias.skill_id for alias in group if alias.skill_id in skills_by_id})
        )
        if len(candidate_skill_ids) == 1:
            review_status = "matched"
        elif candidate_skill_ids:
            review_status = "review-required"
        else:
            review_status = "unmatched"
        records.append(
            SkillNormalizationRecord(
                original_text=representative.alias,
                normalized_text=normalized_text,
                matched_alias=representative.alias,
                candidate_skill_ids=candidate_skill_ids,
                ontology_source_id=representative.ontology_source_id,
                pinned_revision=representative.pinned_revision,
                review_status=review_status,
            )
        )

    unique_relations = {
        (
            relation.source_skill_id,
            relation.target_skill_id,
            relation.relation_kind,
            relation.ontology_source_id,
            relation.pinned_revision,
        ): relation
        for relation in ontology_relations
    }
    for relation_key in sorted(unique_relations):
        relation = unique_relations[relation_key]
        source = skills_by_id.get(relation.source_skill_id)
        records.append(
            SkillNormalizationRecord(
                original_text=source.name if source else relation.source_skill_id,
                normalized_text=_normalized_text(source.name)
                if source
                else relation.source_skill_id,
                candidate_skill_ids=(relation.target_skill_id,)
                if relation.target_skill_id in skills_by_id
                else (),
                ontology_source_id=relation.ontology_source_id,
                pinned_revision=relation.pinned_revision,
                review_status="descriptive-only",
                relation_kind=relation.relation_kind,
            )
        )
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.normalized_text,
                record.candidate_skill_ids,
                record.review_status,
                record.relation_kind or "",
                record.ontology_source_id or "",
                record.pinned_revision or "",
                record.original_text,
            ),
        )
    )


def mastery_snapshot_bytes(fixture: CareerEvidenceFixture) -> bytes:
    """Serialize only mastery-bearing records for non-propagation assertions."""
    assessments = sorted(
        (
            {
                "id": assessment.id,
                "contribution_id": assessment.contribution_id,
                "skill_id": assessment.skill_id,
                "demonstrated_mastery": assessment.demonstrated_mastery,
            }
            for assessment in fixture.assessments
        ),
        key=lambda assessment: assessment["id"],
    )
    views = sorted(
        (
            {
                "skill_id": view.skill_id,
                "mastery": view.mastery,
                "assessment_ids": tuple(sorted(view.assessment_ids)),
            }
            for view in fixture.user_skill_views
        ),
        key=lambda view: view["skill_id"],
    )
    return canonical_json_bytes({"assessments": assessments, "user_skill_views": views})


def collect_invariant_violations(
    fixture: CareerEvidenceFixture,
) -> tuple[InvariantViolation, ...]:
    """Collect stable, unique invariant results without repairing the fixture."""
    violations: list[InvariantViolation] = []
    for items, name in (
        (fixture.experiences, "experience"),
        (fixture.contributions, "contribution"),
        (fixture.claims, "claim"),
        (fixture.evidence, "evidence"),
        (fixture.skills, "skill"),
        (fixture.assessments, "assessment"),
    ):
        violations.extend(_duplicate_violations(items, name))

    experience_ids = {item.id for item in fixture.experiences}
    contribution_ids_by_experience: dict[str, set[str]] = {}
    for experience in fixture.experiences:
        contribution_ids_by_experience[experience.id] = set(experience.contribution_ids)
        for contribution_id in experience.contribution_ids:
            contribution = next(
                (item for item in fixture.contributions if item.id == contribution_id), None
            )
            path = f"experiences.{experience.id}.contribution_ids.{contribution_id}"
            if contribution is None:
                violations.append(
                    InvariantViolation(code="experience.contribution_missing", path=path)
                )
            elif contribution.experience_id != experience.id:
                violations.append(
                    InvariantViolation(code="contribution.parent_mismatch", path=path)
                )
    for contribution in fixture.contributions:
        if contribution.experience_id not in experience_ids:
            violations.append(
                InvariantViolation(
                    code="contribution.experience_missing",
                    path=f"contributions.{contribution.id}.experience_id",
                )
            )
        elif contribution.id not in contribution_ids_by_experience[contribution.experience_id]:
            violations.append(
                InvariantViolation(
                    code="experience.contribution_unlisted",
                    path=(
                        f"experiences.{contribution.experience_id}.contribution_ids."
                        f"{contribution.id}"
                    ),
                )
            )
        for claim_id in contribution.claim_ids:
            claim = next((item for item in fixture.claims if item.id == claim_id), None)
            path = f"contributions.{contribution.id}.claim_ids.{claim_id}"
            if claim is None:
                violations.append(InvariantViolation(code="contribution.claim_missing", path=path))
            elif claim.contribution_id != contribution.id:
                violations.append(InvariantViolation(code="claim.parent_mismatch", path=path))
    violations.extend(validate_contribution_lineage(fixture))
    violations.extend(validate_evidence_links(fixture))
    violations.extend(validate_claim_attribution(fixture))
    violations.extend(validate_user_skill_views(fixture))
    unique = {(item.code, item.path): item for item in violations}
    return tuple(sorted(unique.values(), key=lambda item: (item.code, item.path)))


def validate_career_evidence_fixture(fixture: CareerEvidenceFixture) -> FixtureValidationResult:
    """Validate relationships without repairing an unsupported fixture state."""
    violations = collect_invariant_violations(fixture)
    if violations:
        raise FixtureValidationError(violations)
    return FixtureValidationResult(
        fixture_hash=sha256_digest(canonical_json_bytes(fixture)),
        experience_count=len(fixture.experiences),
        contribution_count=len(fixture.contributions),
        assessment_count=len(fixture.assessments),
        user_skill_count=len(fixture.user_skill_views),
    )


def load_and_validate_fixture(path: Path) -> FixtureValidationResult:
    """Load JSON into the frozen model boundary and validate relationships."""
    try:
        raw_fixture = json.loads(path.read_text(encoding="utf-8"))
        fixture = CareerEvidenceFixture.model_validate(raw_fixture)
    except (OSError, json.JSONDecodeError):
        raise
    except ValidationError as exc:
        raise FixtureValidationError(
            (
                InvariantViolation(
                    code="fixture.schema_invalid",
                    path=".".join(str(part) for error in exc.errors() for part in error["loc"]),
                ),
            )
        ) from exc
    return validate_career_evidence_fixture(fixture)
