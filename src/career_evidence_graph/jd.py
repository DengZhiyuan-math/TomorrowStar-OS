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
from .validation.store import FormalRunStorageError, create_only_canonical_bundle


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


class JDIntakeStore:
    """Create-only private storage for prepared and explicitly accepted packets."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.root = self.workspace / ".career-evidence" / "phase-05"

    def _root_for_write(self) -> Path:
        private_root = self.workspace / ".career-evidence"
        if private_root.is_symlink() or self.root.is_symlink():
            raise JDIntakeError("jd-private-root-unsafe")
        private_root.mkdir(exist_ok=True)
        self.root.mkdir(exist_ok=True)
        if private_root.resolve() != private_root or self.root.resolve() != self.root:
            raise JDIntakeError("jd-private-root-unsafe")
        return self.root

    @staticmethod
    def _bundle_name(source_hash: str) -> str:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_hash):
            raise JDIntakeError("jd-source-hash-invalid")
        return source_hash.removeprefix("sha256:")

    def _version_name(self, source_hash: str, proposal_hash: str) -> str:
        self._bundle_name(source_hash)
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", proposal_hash):
            raise JDIntakeError("jd-proposal-hash-invalid")
        return sha256_digest(
            canonical_json_bytes({"source_hash": source_hash, "proposal_hash": proposal_hash})
        ).removeprefix("sha256:")

    def _bundles(self, kind: str) -> tuple[tuple[dict[str, object], AcceptedJDPacket], ...]:
        """Reopen immutable versions, including the original source-only layout."""
        directory = self.root / kind
        for parent in (self.workspace / ".career-evidence", self.root, directory):
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise JDIntakeError("jd-private-root-unsafe")
            if not parent.exists():
                return ()
        accepted = kind == "accepted"
        label = "accepted" if accepted else "prepared"
        bundles = []
        for path in sorted(directory.iterdir()):
            if path.name.startswith("."):
                continue
            manifest_path = path / "manifest.json"
            packet_path = path / "packet.json"
            if path.is_symlink() or manifest_path.is_symlink() or packet_path.is_symlink():
                raise JDIntakeError(f"jd-{label}-unsafe")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                packet = AcceptedJDPacket.model_validate_json(packet_path.read_bytes())
            except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
                raise JDIntakeError(f"jd-{label}-invalid") from exc
            source_hash = packet.raw_source.source_hash
            proposal_hash = packet.recorded_proposal.proposal_hash
            schema_version = "accepted-jd-intake/v1" if accepted else "jd-prepared-intake/v1"
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != schema_version
                or manifest.get("source_hash") != source_hash
                or manifest.get("proposal_hash") != proposal_hash
                or manifest.get("accepted") is not accepted
                or path.name
                not in {
                    self._bundle_name(source_hash),
                    self._version_name(source_hash, proposal_hash),
                }
                or (accepted and manifest.get("packet_id") != packet.packet_id)
                or (not accepted and manifest.get("source_id") != packet.raw_source.source_id)
            ):
                raise JDIntakeError(f"jd-{label}-invalid")
            bundles.append((manifest, packet))
        return tuple(bundles)

    def _prepared_bundle(
        self, source_hash: str, proposal_hash: str | None = None
    ) -> tuple[dict[str, object], AcceptedJDPacket]:
        self._bundle_name(source_hash)
        if proposal_hash is not None:
            self._version_name(source_hash, proposal_hash)
        matches = [
            item
            for item in self._bundles("prepared")
            if item[1].raw_source.source_hash == source_hash
        ]
        if not matches:
            raise JDIntakeError("jd-prepared-missing")
        if proposal_hash is not None:
            matches = [item for item in matches if item[0]["proposal_hash"] == proposal_hash]
            if not matches:
                raise JDIntakeError("jd-acceptance-hash-mismatch")
        if len(matches) != 1:
            raise JDIntakeError("jd-prepared-version-required")
        return matches[0]

    def prepare(self, intake: PreparedJDIntake) -> dict[str, object]:
        self._root_for_write()
        proposal_hash = intake.packet.recorded_proposal.proposal_hash
        if any(
            packet.raw_source.source_hash == intake.source_hash
            and packet.recorded_proposal.proposal_hash == proposal_hash
            for _manifest, packet in self._bundles("prepared")
        ):
            raise JDIntakeError("jd-prepared-already-exists")
        destination = self.root / "prepared" / self._version_name(intake.source_hash, proposal_hash)
        destination.parent.mkdir(exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise JDIntakeError("jd-prepared-already-exists")
        try:
            create_only_canonical_bundle(
                destination.parent,
                destination.name,
                {
                    "packet.json": intake.packet.model_dump(mode="json"),
                    "manifest.json": {
                        "schema_version": "jd-prepared-intake/v1",
                        "source_id": intake.source_id,
                        "source_hash": intake.source_hash,
                        "source_bytes": intake.source_bytes,
                        "proposal_hash": intake.packet.recorded_proposal.proposal_hash,
                        "disclosures": intake.disclosures,
                        "accepted": False,
                    },
                },
            )
        except FormalRunStorageError as exc:
            raise JDIntakeError("jd-prepared-already-exists") from exc
        return self.inspect_prepared(intake.source_hash, proposal_hash)

    def inspect_prepared(
        self, source_hash: str, proposal_hash: str | None = None
    ) -> dict[str, object]:
        manifest, packet = self._prepared_bundle(source_hash, proposal_hash)
        return {
            "accepted": False,
            "disclosures": manifest.get("disclosures", []),
            "proposal_hash": packet.recorded_proposal.proposal_hash,
            "source_bytes": manifest.get("source_bytes"),
            "source_hash": source_hash,
            "source_id": manifest.get("source_id"),
        }

    def accept(self, source_hash: str, proposal_hash: str) -> dict[str, object]:
        """Create one immutable accepted packet only after exact hash confirmation."""
        _manifest, packet = self._prepared_bundle(source_hash, proposal_hash)
        root = self._root_for_write()
        if any(
            stored.raw_source.source_hash == source_hash
            and stored.recorded_proposal.proposal_hash == proposal_hash
            for _manifest, stored in self._bundles("accepted")
        ):
            raise JDIntakeError("jd-accepted-already-exists")
        accepted_root = root / "accepted"
        accepted_root.mkdir(exist_ok=True)
        destination = accepted_root / self._version_name(source_hash, proposal_hash)
        if destination.exists() or destination.is_symlink():
            raise JDIntakeError("jd-accepted-already-exists")
        try:
            create_only_canonical_bundle(
                accepted_root,
                destination.name,
                {
                    "packet.json": packet.model_dump(mode="json"),
                    "manifest.json": {
                        "schema_version": "accepted-jd-intake/v1",
                        "packet_id": packet.packet_id,
                        "source_hash": source_hash,
                        "proposal_hash": proposal_hash,
                        "accepted": True,
                    },
                },
            )
        except FormalRunStorageError as exc:
            raise JDIntakeError("jd-accepted-already-exists") from exc
        return {
            "accepted": True,
            "packet_id": packet.packet_id,
            "proposal_hash": proposal_hash,
            "source_hash": source_hash,
        }

    def verify_accepted(self, packet: AcceptedJDPacket) -> None:
        """Require this exact packet's acceptance in the current workspace."""
        matches = [
            stored
            for _manifest, stored in self._bundles("accepted")
            if stored.raw_source.source_hash == packet.raw_source.source_hash
            and stored.recorded_proposal.proposal_hash == packet.recorded_proposal.proposal_hash
        ]
        if not matches:
            raise JDIntakeError("jd-accepted-missing")
        if any(stored != packet for stored in matches):
            raise JDIntakeError("jd-accepted-packet-mismatch")

    def _source_count(self, kind: str) -> int:
        return len({packet.raw_source.source_hash for _manifest, packet in self._bundles(kind)})

    def expectation_met(self, expectation: str) -> bool:
        if expectation == "prepared-exact-three":
            return self._source_count("prepared") == 3
        if expectation == "accepted-corpus-and-graph":
            if self._source_count("accepted") != 3:
                return False
            try:
                load_reviewed_user_graph(self.workspace)
            except JDComparisonError:
                return False
            return True
        expected_paths = {
            "existing-evaluation": self.root / "evaluation" / "manifest.json",
            "sealed-blind-review": self.root / "evaluation" / "blind-review.json",
            "finalized": self.root / "evaluation" / "finalized.json",
        }
        path = expected_paths.get(expectation)
        if path is None:
            raise JDIntakeError("jd-inspect-expectation-invalid")
        return path.is_file() and not path.is_symlink()

    def safe_status(self) -> dict[str, object]:
        """Expose workflow counts only; raw source text and packets stay private."""
        if not self.root.exists():
            return {
                "accepted_count": 0,
                "evaluation_present": False,
                "prepared_count": 0,
            }
        if self.root.is_symlink() or not self.root.is_dir():
            raise JDIntakeError("jd-private-root-unsafe")

        manifest = self.root / "evaluation" / "manifest.json"
        return {
            "accepted_count": self._source_count("accepted"),
            "evaluation_present": manifest.is_file() and not manifest.is_symlink(),
            "prepared_count": self._source_count("prepared"),
        }


def _normalized_company_identity(value: str) -> str:
    if _source_disclosures(value):
        raise JDIntakeError("jd-priority-company-unsafe")
    normalized = " ".join(value.split()).casefold()
    if not normalized:
        raise JDIntakeError("jd-priority-company-invalid")
    return normalized


@dataclass(frozen=True)
class PriorityCompanyInput:
    """One forward-only private preference input; never a capability signal."""

    version: str
    companies: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        if not _SAFE_SOURCE_ID.fullmatch(self.version):
            raise JDIntakeError("jd-priority-version-invalid")
        identities: dict[str, str] = {}
        for canonical_name, aliases in self.companies:
            canonical_identity = _normalized_company_identity(canonical_name)
            normalized_aliases = tuple(_normalized_company_identity(alias) for alias in aliases)
            for identity in (canonical_identity, *normalized_aliases):
                owner = identities.setdefault(identity, canonical_identity)
                if owner != canonical_identity:
                    raise JDIntakeError("jd-priority-alias-collision")
        if not identities:
            raise JDIntakeError("jd-priority-company-invalid")

    def canonical_name_for(self, company_name: str) -> str | None:
        requested = _normalized_company_identity(company_name)
        for canonical_name, aliases in self.companies:
            canonical_identity = _normalized_company_identity(canonical_name)
            normalized_aliases = tuple(_normalized_company_identity(alias) for alias in aliases)
            if requested in {canonical_identity, *normalized_aliases}:
                return canonical_name
        return None

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "jd-priority-company-input/v1",
            "version": self.version,
            "companies": [
                {"canonical_name": canonical_name, "aliases": list(aliases)}
                for canonical_name, aliases in self.companies
            ],
        }


@dataclass(frozen=True)
class PriorityRouteOverlay:
    """A route-only preference projection over an unchanged comparison result."""

    analysis: dict[str, object]
    final_route: str
    route_reason: str
    priority_list_version: str
    matched_company: str | None


def apply_priority_company_overlay(
    analysis: dict[str, object], priority_input: PriorityCompanyInput, company_name: str
) -> PriorityRouteOverlay:
    """Apply a confirmed preference after scoring without reinterpreting user truth."""
    matched_company = priority_input.canonical_name_for(company_name)
    if matched_company is not None:
        return PriorityRouteOverlay(
            analysis=analysis,
            final_route="customized-resume",
            route_reason="user-priority-company",
            priority_list_version=priority_input.version,
            matched_company=matched_company,
        )
    final_route = str(analysis.get("route", analysis.get("ordinary_route", "abandon")))
    return PriorityRouteOverlay(
        analysis=analysis,
        final_route=final_route,
        route_reason="ordinary",
        priority_list_version=priority_input.version,
        matched_company=None,
    )


class PriorityCompanyStore:
    """Store distinct private preference versions without overwriting their history."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.root = self.workspace / ".career-evidence" / "phase-05" / "priority-company-lists"

    def publish(self, priority_input: PriorityCompanyInput) -> Path:
        try:
            destination = create_only_canonical_bundle(
                self.root,
                priority_input.version,
                {"priority-company-list.json": priority_input.payload()},
            )
        except FormalRunStorageError as exc:
            raise JDIntakeError("jd-priority-version-already-exists") from exc
        return destination / "priority-company-list.json"


_CHARTER_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "charter_version",
        "case_inventory",
        "attempts_per_case",
        "route_scenarios",
        "baseline",
        "blind_review",
        "criteria",
        "zero_critical_fabricated_capability_claims",
        "limitation",
    }
)


def load_evaluation_charter(path: Path) -> dict[str, object]:
    """Read the pre-fixture charter and reject incomplete or post-hoc variants."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JDIntakeError("jd-evaluation-charter-invalid") from exc
    if not isinstance(value, dict) or set(value) != _CHARTER_TOP_LEVEL_FIELDS:
        raise JDIntakeError("jd-evaluation-charter-invalid")
    if (
        value.get("schema_version") != "jd-evaluation-charter/v1"
        or value.get("attempts_per_case") != 3
    ):
        raise JDIntakeError("jd-evaluation-charter-invalid")
    inventory = value.get("case_inventory")
    scenarios = value.get("route_scenarios")
    baseline = value.get("baseline")
    blind_review = value.get("blind_review")
    criteria = value.get("criteria")
    if (
        not isinstance(inventory, dict)
        or set(inventory) != {"EVAL-01", "EVAL-02"}
        or not all(isinstance(cases, list) and cases for cases in inventory.values())
        or not isinstance(scenarios, list)
        or set(scenarios)
        != {
            "evidence-strong-customized",
            "ordinary-standard-resume",
            "low-match-abandon",
            "unchanged-jd-priority-counterfactual",
        }
        or not isinstance(baseline, dict)
        or baseline.get("flat_resume_arm") != "when-supplied"
        or baseline.get("fallback") != "sorted-exact-skill-name-keyword-overlap"
        or not isinstance(blind_review, dict)
        or blind_review.get("opaque_ab_assignment") != "frozen-before-reviewer-execution"
        or not isinstance(criteria, list)
        or set(criteria) != {"EVAL-04", "EVAL-05"}
        or value.get("zero_critical_fabricated_capability_claims") is not True
        or not isinstance(value.get("limitation"), str)
        or "does not establish" not in value["limitation"]
    ):
        raise JDIntakeError("jd-evaluation-charter-invalid")
    return value


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
            or proposal.assessment_status != "reviewed"
            or proposal.origin_status == "derived-counterfactual"
            or not proposal.substantive_review_complete
            or not record.reviews
            or len(record.versions) < 2
            or record.reviews[-1].outcome not in {"confirm", "edit"}
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
    unverified_conditions = []
    for name in (
        "stated_strength",
        "responsibility_expectation",
        "context_expectation",
        "seniority_expectation",
        "duration_expectation",
        "experience_expectation",
    ):
        expectation = getattr(requirement, name)
        if not expectation or not expectation.strip():
            continue
        if name == "context_expectation" and all(
            expectation in result.supporting_contexts for result in resolved
        ):
            continue
        unverified_conditions.append(f"{name}: {expectation}")
    if unverified_conditions:
        return JDRequirementJudgment(
            requirement_id=requirement.requirement_id,
            status="uncertain",
            skill_ids=requirement.skill_ids,
            contribution_ids=contribution_ids,
            evidence_ids=evidence_ids,
            evidence_skill_ids=requirement.skill_ids,
            established_capability=(
                "Admitted reviewed-user-truth evidence exists for every exact Skill."
            ),
            limitation="JD conditions require separate verification: "
            + "; ".join(unverified_conditions),
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
    elif (
        requirement.context_expectation
        and requirement.context_expectation.strip()
        and judgment.evidence_ids
        and any(
            requirement.context_expectation not in results_by_skill[skill_id].supporting_contexts
            for skill_id in requirement.skill_ids
        )
    ):
        kind = "context-mismatch"
    elif judgment.status == "uncertain":
        kind = "missing-evidence"
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
