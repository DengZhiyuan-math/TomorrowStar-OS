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
    return {
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
            "proposal_hash": sha256_digest(
                json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ),
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


def test_positive_and_partial_judgments_require_exact_skill_contribution_evidence_and_limitation() -> None:
    base = {
        "schema_version": "jd-requirement-judgment/v1",
        "requirement_id": "requirement-first",
        "status": "partially-supported",
        "skill_ids": ["skill.alpha"],
        "experience_ids": ["experience-schema-only"],
        "contribution_ids": ["contribution-schema-only"],
        "evidence_ids": ["evidence-schema-only"],
        "established_capability": "An admitted exact-Skill assessment exists.",
        "limitation": "The supplied boundary remains only partly met.",
    }
    assert JDRequirementJudgment.model_validate(base).status == "partially-supported"

    for field, value in (
        ("experience_ids", []),
        ("contribution_ids", []),
        ("evidence_ids", []),
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
    assert [item.requirement_id for item in canonical_jd_judgments(judgments, packet.requirements)] == [
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
