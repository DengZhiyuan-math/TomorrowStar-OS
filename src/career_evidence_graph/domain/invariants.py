"""Cross-record validation for strict career-evidence fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ..validation.hashing import canonical_json_bytes, sha256_digest
from .models import (
    CareerEvidenceFixture,
    FixtureValidationResult,
    InvariantViolation,
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


def _invariant_error(violations: list[InvariantViolation]) -> FixtureValidationError:
    ordered = tuple(sorted(violations, key=lambda item: (item.code, item.path)))
    return FixtureValidationError(ordered)


def validate_career_evidence_fixture(fixture: CareerEvidenceFixture) -> FixtureValidationResult:
    """Validate IDs and lineage without repairing any unsupported state."""
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
    contribution_ids = {item.id for item in fixture.contributions}
    claim_ids = {item.id for item in fixture.claims}
    evidence_ids = {item.id for item in fixture.evidence}
    skill_ids = {item.id for item in fixture.skills}

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

    seen_links: set[tuple[str, str]] = set()
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

    for assessment in fixture.assessments:
        path = f"assessments.{assessment.id}"
        contribution_exists = assessment.contribution_id in contribution_ids
        if not contribution_exists:
            violations.append(
                InvariantViolation(
                    code="assessment.contribution_missing", path=f"{path}.contribution_id"
                )
            )
        if assessment.skill_id not in skill_ids:
            violations.append(
                InvariantViolation(code="assessment.skill_missing", path=f"{path}.skill_id")
            )
        for claim_id in assessment.basis_claim_ids:
            claim = next((item for item in fixture.claims if item.id == claim_id), None)
            basis_path = f"{path}.basis_claim_ids.{claim_id}"
            if claim is None:
                violations.append(
                    InvariantViolation(code="assessment.basis_claim_missing", path=basis_path)
                )
            elif contribution_exists and claim.contribution_id != assessment.contribution_id:
                violations.append(
                    InvariantViolation(code="assessment.basis_claim_mismatch", path=basis_path)
                )
            elif assessment.assessment_status == "reviewed" and (
                claim.responsibility != "user" or claim.confirmation_status != "confirmed"
            ):
                violations.append(
                    InvariantViolation(
                        code="assessment.reviewed_claim_not_confirmed", path=basis_path
                    )
                )

    for view in fixture.user_skill_views:
        for assessment_id in view.assessment_ids:
            assessment = next(
                (item for item in fixture.assessments if item.id == assessment_id), None
            )
            path = f"user_skill_views.{view.skill_id}.assessment_ids.{assessment_id}"
            if assessment is None:
                violations.append(
                    InvariantViolation(code="user_skill_view.assessment_missing", path=path)
                )
            elif assessment.skill_id != view.skill_id:
                violations.append(
                    InvariantViolation(code="user_skill_view.skill_mismatch", path=path)
                )
    if violations:
        raise _invariant_error(violations)
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
