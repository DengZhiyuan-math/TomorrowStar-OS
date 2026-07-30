"""Schema-versioned contracts for the Phase 1 validation boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model that rejects silent schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpectedResultPolicy(StrictModel):
    structurally_exact: bool
    semantic_comparisons: Literal["declared_sets_and_ranges_only"]
    approved_set_fields: list[str]
    approved_range_fields: dict[str, tuple[float, float]]


class AcceptanceState(StrictModel):
    eligible_now: bool
    case_count: int = Field(ge=0)
    holdout_eligible: bool
    missing_prerequisites: list[str]


class ProductEffectLabels(StrictModel):
    labels: list[Literal["supported", "partially-supported", "rejected"]]
    authoritative_for_this_charter: bool
    reason: str = Field(min_length=1)


class ValidationCharter(StrictModel):
    schema_version: Literal["validation-charter/v1"]
    charter_version: Literal["1.0.0"]
    target_chain: list[str]
    claim_boundary: Literal["functional-chain-only"]
    prohibited_claims: list[str]
    expected_result_policy: ExpectedResultPolicy
    critical_blocking_failures: list[
        Literal[
            "capability_fabrication",
            "incorrect_attribution",
            "broken_lineage",
            "material_instability",
            "unreproducible_formal_run",
        ]
    ]
    required_negative_classes: list[str]
    acceptance: AcceptanceState
    product_effect_labels: ProductEffectLabels

    @model_validator(mode="after")
    def validate_frozen_decisions(self) -> ValidationCharter:
        required_chain = [
            "Grill-Me",
            "Contribution-Skill assessment",
            "user Skill graph",
            "JD comparison",
        ]
        required_prohibited_claims = {
            "product effectiveness",
            "job application outcomes",
            "interview outcomes",
            "hiring outcomes",
        }
        required_prerequisites = {
            "future user-completed STOA flow",
            "one human-confirmed replay case",
            "coverage of every required negative class",
        }
        if self.target_chain != required_chain:
            raise ValueError("target_chain must name the complete intended functional chain")
        if set(self.prohibited_claims) != required_prohibited_claims:
            raise ValueError("all product-effectiveness claim classes must be prohibited")
        if not self.expected_result_policy.structurally_exact:
            raise ValueError("formal expectations must be structurally exact")
        if len(self.critical_blocking_failures) != 5:
            raise ValueError("all five critical blocking failure classes are required")
        if len(set(self.critical_blocking_failures)) != 5:
            raise ValueError("critical blocking failure classes must be unique")
        if not set(self.critical_blocking_failures).issubset(self.required_negative_classes):
            raise ValueError("every blocker must have a required negative class")
        if "duplicate_evidence_inflation" not in self.required_negative_classes:
            raise ValueError("duplicate evidence inflation coverage is required")
        if self.acceptance.eligible_now:
            raise ValueError("Phase 1 cannot be acceptance-eligible before real cases exist")
        if self.acceptance.case_count != 0 or self.acceptance.holdout_eligible:
            raise ValueError("Phase 1 must not invent a case or sealed holdout")
        if set(self.acceptance.missing_prerequisites) != required_prerequisites:
            raise ValueError("acceptance must retain every future evidence prerequisite")
        if self.product_effect_labels.authoritative_for_this_charter:
            raise ValueError("product-effect labels are non-authoritative for this charter")
        if set(self.product_effect_labels.labels) != {
            "supported",
            "partially-supported",
            "rejected",
        }:
            raise ValueError("all legacy product-effect labels must be reconciled")
        return self


class FormalRunManifest(StrictModel):
    schema_version: Literal["formal-run/v1"]
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    run_kind: Literal["synthetic-offline-tracer"]
    created_at: datetime
    charter_version: str
    input_hashes: dict[str, str]
    content_manifest: dict[str, str]
    replay_mode: Literal["exact-recorded-response"]


class ReplayResult(StrictModel):
    schema_version: Literal["replay-result/v1"]
    run_id: str
    matched: bool
    expected_hash: str
    actual_hash: str
