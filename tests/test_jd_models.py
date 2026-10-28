"""Strict content-free contracts for accepted JD comparison inputs.

All strings here are synthetic boundary probes.  They are not Phase 5 JD
fixtures and do not describe an employer or role.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from career_evidence_graph.domain.invariants import (
    canonical_jd_contribution_selections,
    canonical_jd_evidence_citations,
    canonical_jd_gaps,
    canonical_jd_judgments,
    canonical_jd_requirements,
)
from career_evidence_graph.domain.models import (
    AcceptedJDPacket,
    JDContributionSelection,
    JDEvidenceCitation,
    JDGap,
    JDRequirementJudgment,
)
from career_evidence_graph.validation.hashing import sha256_digest

SOURCE = b"schema-only requirement; another schema-only requirement"


def _payload() -> dict[str, object]:
    source_hash = sha256_digest(SOURCE)
    proposal = {
        "source_hash": source_hash,
        "raw_source_id": "source-schema-only",
        "proposal_kind": "schema-only-contract-probe",
    }
    payload = {
        "schema_version": "accepted-jd-packet/v1",
        "packet_id": "packet-schema-only",
        "raw_source": {
            "schema_version": "jd-raw-source/v1",
            "source_id": "source-schema-only",
            "utf8_text": SOURCE.decode("utf-8"),
            "source_hash": source_hash,
        },
        "recorded_proposal": {
            "schema_version": "jd-recorded-proposal/v1",
            "proposal_id": "proposal-schema-only",
            "source_hash": source_hash,
            "raw_source_id": "source-schema-only",
            "proposal_json": json.dumps(proposal, sort_keys=True),
            "proposal_hash": sha256_digest(json.dumps(proposal, sort_keys=True).encode("utf-8")),
        },
        "requirements": [
            {
                "schema_version": "jd-requirement/v1",
                "requirement_id": "requirement-first",
                "source_span": {
                    "schema_version": "jd-source-span/v1",
                    "start_byte": 0,
                    "end_byte": 23,
                    "text_hash": sha256_digest(SOURCE[:23]),
                },
                "skill_ids": ["skill.alpha"],
                "decision_critical": True,
                "priority": "required",
                "core_hard": True,
            },
            {
                "schema_version": "jd-requirement/v1",
                "requirement_id": "requirement-second",
                "source_span": {
                    "schema_version": "jd-source-span/v1",
                    "start_byte": 25,
                    "end_byte": len(SOURCE),
                    "text_hash": sha256_digest(SOURCE[25:]),
                },
                "skill_ids": ["skill.beta", "skill.gamma"],
                "linked_requirement_group_id": "group-schema-only",
                "decision_critical": True,
                "priority": "required",
            },
        ],
    }
    proposal["requirements"] = payload["requirements"]
    recorded = json.dumps(proposal, sort_keys=True)
    payload["recorded_proposal"]["proposal_json"] = recorded
    payload["recorded_proposal"]["proposal_hash"] = sha256_digest(recorded.encode("utf-8"))
    return payload


def _packet() -> AcceptedJDPacket:
    return AcceptedJDPacket.model_validate(_payload())


def test_accepted_packet_reconstructs_exact_byte_spans_and_binds_one_recorded_proposal() -> None:
    packet = _packet()

    assert tuple(item.skill_ids for item in packet.requirements) == (
        ("skill.alpha",),
        ("skill.beta", "skill.gamma"),
    )
    assert packet.requirements[1].linked_requirement_group_id == "group-schema-only"

    for path, mutation in (
        (("requirements", 0, "source_span", "start_byte"), 1),
        (("requirements", 0, "source_span", "text_hash"), sha256_digest(b"wrong")),
        (("recorded_proposal", "proposal_hash"), sha256_digest(b"wrong")),
        (("recorded_proposal", "proposal_json"), "[]"),
    ):
        payload = _payload()
        target: object = payload
        for key in path[:-1]:
            target = target[key]  # type: ignore[index]
        target[path[-1]] = mutation  # type: ignore[index]
        with pytest.raises(ValidationError):
            AcceptedJDPacket.model_validate(payload)


def test_accepted_packet_fails_closed_on_empty_or_duplicate_or_extra_input() -> None:
    empty = _payload()
    empty["requirements"] = []
    with pytest.raises(ValidationError):
        AcceptedJDPacket.model_validate(empty)

    no_decision = _payload()
    no_decision["requirements"][0]["decision_critical"] = False  # type: ignore[index]
    no_decision["requirements"][1]["decision_critical"] = False  # type: ignore[index]
    with pytest.raises(ValidationError):
        AcceptedJDPacket.model_validate(no_decision)

    duplicate = _payload()
    duplicate["requirements"].append(duplicate["requirements"][0])  # type: ignore[index]
    with pytest.raises(ValidationError):
        AcceptedJDPacket.model_validate(duplicate)

    extra = _payload()
    extra["unexpected"] = True
    with pytest.raises(ValidationError):
        AcceptedJDPacket.model_validate(extra)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("requirement_id", "changed-requirement"),
        ("skill_ids", ["skill.changed"]),
        ("decision_critical", False),
        ("priority", "preferred"),
        ("core_hard", False),
        ("evidence_strong_eligible", True),
        ("linked_requirement_group_id", "changed-group"),
        ("minimum_mastery", 99),
        ("stated_strength", "Expert knowledge is required."),
        ("responsibility_expectation", "Own the release decision."),
        ("context_expectation", "Production operations."),
        ("seniority_expectation", "Senior engineer."),
        ("duration_expectation", "Five verified years."),
        ("experience_expectation", "Two completed migrations."),
    ),
)
def test_every_accepted_requirement_field_is_bound_to_the_recorded_proposal(
    field: str, value: object
) -> None:
    payload = _payload()
    payload["requirements"][0][field] = value

    with pytest.raises(ValidationError, match="requirements must match the recorded proposal"):
        AcceptedJDPacket.model_validate(payload)


def test_requirement_spans_and_order_cannot_reuse_a_recorded_proposal() -> None:
    changed_span = _payload()
    changed_span["requirements"][0]["source_span"] = changed_span["requirements"][1]["source_span"]
    reordered = _payload()
    reordered["requirements"].reverse()

    for payload in (changed_span, reordered):
        with pytest.raises(ValidationError, match="requirements must match the recorded proposal"):
            AcceptedJDPacket.model_validate(payload)


def test_a_valid_hash_of_metadata_alone_cannot_confirm_requirements() -> None:
    payload = _payload()
    proposal = json.loads(payload["recorded_proposal"]["proposal_json"])
    del proposal["requirements"]
    recorded = json.dumps(proposal, sort_keys=True)
    payload["recorded_proposal"]["proposal_json"] = recorded
    payload["recorded_proposal"]["proposal_hash"] = sha256_digest(recorded.encode("utf-8"))

    with pytest.raises(ValidationError, match="requirements must match the recorded proposal"):
        AcceptedJDPacket.model_validate(payload)


def test_positive_and_partial_judgments_require_evidence_and_limitation() -> None:
    base = {
        "schema_version": "jd-requirement-judgment/v1",
        "requirement_id": "requirement-first",
        "status": "partially-supported",
        "skill_ids": ["skill.alpha"],
        "contribution_ids": ["contribution-schema-only"],
        "evidence_ids": ["evidence-schema-only"],
        "evidence_skill_ids": ["skill.alpha"],
        "established_capability": "An admitted exact-Skill assessment exists.",
        "limitation": "The supplied boundary remains only partly met.",
    }
    assert JDRequirementJudgment.model_validate(base).status == "partially-supported"

    for field, value in (
        ("contribution_ids", []),
        ("evidence_ids", []),
        ("evidence_skill_ids", []),
        ("established_capability", None),
        ("limitation", None),
    ):
        invalid = dict(base)
        invalid[field] = value
        with pytest.raises(ValidationError):
            JDRequirementJudgment.model_validate(invalid)


def test_equal_ranked_outputs_have_one_source_offset_then_stable_identifier_order() -> None:
    packet = _packet()
    requirements = tuple(reversed(packet.requirements))
    assert [item.requirement_id for item in canonical_jd_requirements(requirements)] == [
        "requirement-first",
        "requirement-second",
    ]

    judgments = (
        JDRequirementJudgment(
            requirement_id="requirement-second",
            status="unsupported",
            skill_ids=("skill.beta", "skill.gamma"),
            limitation="No direct admitted evidence exists.",
        ),
        JDRequirementJudgment(
            requirement_id="requirement-first",
            status="unsupported",
            skill_ids=("skill.alpha",),
            limitation="No direct admitted evidence exists.",
        ),
    )
    assert [
        item.requirement_id for item in canonical_jd_judgments(judgments, packet.requirements)
    ] == [
        "requirement-first",
        "requirement-second",
    ]

    citations = (
        JDEvidenceCitation(evidence_id="evidence-b", source_byte_offset=5, rank=1),
        JDEvidenceCitation(evidence_id="evidence-a", source_byte_offset=5, rank=1),
    )
    assert [item.evidence_id for item in canonical_jd_evidence_citations(citations)] == [
        "evidence-a",
        "evidence-b",
    ]

    gaps = (
        JDGap(requirement_id="requirement-second", kind="uncertainty", detail="Unresolved."),
        JDGap(requirement_id="requirement-first", kind="uncertainty", detail="Unresolved."),
    )
    assert [item.requirement_id for item in canonical_jd_gaps(gaps, packet.requirements)] == [
        "requirement-first",
        "requirement-second",
    ]

    selections = (
        JDContributionSelection(
            contribution_id="contribution-b", source_byte_offset=4, rank=1, reason="Relevant."
        ),
        JDContributionSelection(
            contribution_id="contribution-a", source_byte_offset=4, rank=1, reason="Relevant."
        ),
    )
    assert [item.contribution_id for item in canonical_jd_contribution_selections(selections)] == [
        "contribution-a",
        "contribution-b",
    ]
