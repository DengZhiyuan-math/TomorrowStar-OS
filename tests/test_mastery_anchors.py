"""Exact, anchor-first mastery assessment contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from career_evidence_graph.domain.invariants import validate_mastery_anchor_fit
from career_evidence_graph.domain.models import (
    MASTERY_ANCHORS,
    AssessmentJudgmentBasis,
    MasteryAnchorFit,
)


def _fit(anchor_id: str, score_basis: str = "The bounded task was independently completed.") -> MasteryAnchorFit:
    anchor = next(item for item in MASTERY_ANCHORS if item.anchor_id == anchor_id)
    return MasteryAnchorFit(
        anchor_id=anchor.anchor_id,
        anchor_range=anchor.inclusive_range,
        anchor_text=anchor.capability_text,
        anchor_basis="Observed behavior fits this exact capability anchor.",
        exact_score_basis=score_basis,
        next_anchor_not_established="The next higher observable behavior was not established.",
    )


@pytest.mark.parametrize(
    ("score", "anchor_id"),
    (
        (0, "anchor-0-19"),
        (19, "anchor-0-19"),
        (20, "anchor-20-39"),
        (39, "anchor-20-39"),
        (40, "anchor-40-54"),
        (54, "anchor-40-54"),
        (55, "anchor-55-69"),
        (69, "anchor-55-69"),
        (70, "anchor-70-79"),
        (79, "anchor-70-79"),
        (80, "anchor-80-89"),
        (89, "anchor-80-89"),
        (90, "anchor-90-95"),
        (95, "anchor-90-95"),
        (96, "anchor-96-100"),
        (100, "anchor-96-100"),
    ),
)
def test_every_integer_boundary_maps_to_exactly_one_accepted_anchor(
    score: int, anchor_id: str
) -> None:
    fit = _fit(anchor_id)

    assert validate_mastery_anchor_fit(score, fit).anchor_id == anchor_id


def test_anchor_fit_rejects_wrong_text_missing_next_anchor_and_higher_band_mismatch() -> None:
    fit = _fit("anchor-70-79")

    with pytest.raises(ValueError, match="inside its anchor"):
        validate_mastery_anchor_fit(69, fit)
    with pytest.raises(ValidationError, match="anchor_text"):
        _fit("anchor-70-79").model_copy(update={"anchor_text": "wrong text"}).model_validate(
            _fit("anchor-70-79").model_copy(update={"anchor_text": "wrong text"}).model_dump()
        )
    with pytest.raises(ValidationError, match="next_anchor_not_established"):
        MasteryAnchorFit(
            anchor_id=fit.anchor_id,
            anchor_range=fit.anchor_range,
            anchor_text=fit.anchor_text,
            anchor_basis=fit.anchor_basis,
            exact_score_basis=fit.exact_score_basis,
            next_anchor_not_established=" ",
        )


def test_judgment_bases_are_non_empty_and_do_not_change_each_other() -> None:
    basis = AssessmentJudgmentBasis(
        demonstrated_mastery_basis="Audited bounded implementation behavior.",
        skill_centrality_basis="Authorization was central to this contribution.",
        evidence_confidence_basis="Two source-bound artifacts and audited answers agree.",
    )

    assert basis.demonstrated_mastery_basis != basis.skill_centrality_basis
    assert basis.skill_centrality_basis != basis.evidence_confidence_basis
    with pytest.raises(ValidationError):
        AssessmentJudgmentBasis(
            demonstrated_mastery_basis=" ",
            skill_centrality_basis="Centrality is independent.",
            evidence_confidence_basis="Confidence is independent.",
        )
