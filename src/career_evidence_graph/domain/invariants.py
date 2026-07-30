"""Pure cross-record validation for strict career-evidence fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import CareerEvidenceFixture, FixtureValidationResult, InvariantViolation

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
    violations: list[InvariantViolation] = []
    for assessment in fixture.assessments:
        path = f"assessments.{assessment.id}"
        if not assessment.basis_claim_ids:
            violations.append(InvariantViolation(code="assessment.basis_missing", path=path))
            continue
        for claim_id in assessment.basis_claim_ids:
            claim = claims_by_id.get(claim_id)
            basis_path = f"{path}.basis_claim_ids.{claim_id}"
            if claim is None:
                violations.append(
                    InvariantViolation(code="assessment.basis_claim_missing", path=basis_path)
                )
                continue
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
                    InvariantViolation(
                        code="assessment.definite_claim_unresolved", path=basis_path
                    )
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
    assessed_skill_ids = {assessment.skill_id for assessment in fixture.assessments}
    views_by_skill: dict[str, list[object]] = {}
    violations: list[InvariantViolation] = []
    for view in fixture.user_skill_views:
        views_by_skill.setdefault(view.skill_id, []).append(view)
        view_path = f"user_skill_views.{view.skill_id}"
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
                violations.append(
                    InvariantViolation(code="user-skill.skill_mismatch", path=path)
                )
    for skill_id in sorted(views_by_skill):
        if len(views_by_skill[skill_id]) > 1:
            violations.append(
                InvariantViolation(code="user-skill.duplicate", path=f"user_skill_views.{skill_id}")
            )
    for skill_id in sorted(assessed_skill_ids - set(views_by_skill)):
        violations.append(InvariantViolation(code="user-skill.missing", path=skill_id))
    return tuple(violations)


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
    for experience in fixture.experiences:
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
