"""Public Phase 2 career-evidence domain contracts and validation seam."""

from .invariants import (
    FixtureValidationError,
    collect_invariant_violations,
    load_and_validate_fixture,
    mastery_snapshot_bytes,
    normalize_skill_metadata,
    validate_career_evidence_fixture,
    validate_claim_attribution,
    validate_contribution_lineage,
    validate_evidence_links,
    validate_user_skill_views,
)
from .models import (
    AssessmentSourceKind,
    CareerEvidenceFixture,
    FixtureValidationResult,
    InvariantViolation,
    OntologyRelation,
    SkillAlias,
    SkillNormalizationRecord,
    UserSkillView,
)

__all__ = [
    "AssessmentSourceKind",
    "CareerEvidenceFixture",
    "FixtureValidationError",
    "FixtureValidationResult",
    "InvariantViolation",
    "OntologyRelation",
    "SkillAlias",
    "SkillNormalizationRecord",
    "UserSkillView",
    "collect_invariant_violations",
    "load_and_validate_fixture",
    "mastery_snapshot_bytes",
    "normalize_skill_metadata",
    "validate_claim_attribution",
    "validate_career_evidence_fixture",
    "validate_contribution_lineage",
    "validate_evidence_links",
    "validate_user_skill_views",
]
