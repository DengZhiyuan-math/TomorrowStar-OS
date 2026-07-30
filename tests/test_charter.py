from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from career_evidence_graph.validation.models import ValidationCharter
from career_evidence_graph.validation.store import load_charter


def test_phase_one_charter_has_no_fictional_case_or_product_claim(charter_path):
    charter = load_charter(charter_path)

    assert charter.claim_boundary == "functional-chain-only"
    assert charter.acceptance.case_count == 0
    assert charter.acceptance.holdout_eligible is False
    assert charter.acceptance.eligible_now is False
    assert len(charter.critical_blocking_failures) == 5
    assert "product effectiveness" in charter.prohibited_claims
    assert charter.product_effect_labels.authoritative_for_this_charter is False


def test_charter_rejects_unknown_fields(charter_path):
    payload = json.loads(charter_path.read_text(encoding="utf-8"))
    payload["unreviewed_rule"] = True

    with pytest.raises(ValidationError):
        ValidationCharter.model_validate(payload)


def test_charter_rejects_premature_acceptance(charter_path):
    payload = json.loads(charter_path.read_text(encoding="utf-8"))
    payload["acceptance"]["eligible_now"] = True

    with pytest.raises(ValidationError, match="cannot be acceptance-eligible"):
        ValidationCharter.model_validate(payload)


def test_charter_rejects_a_missing_product_effect_prohibition(charter_path):
    payload = json.loads(charter_path.read_text(encoding="utf-8"))
    payload["prohibited_claims"].remove("hiring outcomes")

    with pytest.raises(ValidationError, match="claim classes must be prohibited"):
        ValidationCharter.model_validate(payload)
