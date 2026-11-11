# Phase 5: JD Usefulness and Adversarial Evaluation - Pattern Map

**Mapped:** 2026-08-28
**Files/directories classified:** 15
**Analogs found:** 14 / 15

This map covers implementation shape only. It does not search for, select, copy, synthesize,
or embed any JD. The three real evaluation JDs remain a user-supplied execution checkpoint,
and no active numeric routing policy may be claimed before those inputs and the authoritative
reviewed-user-truth graph are accepted.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/career_evidence_graph/domain/models.py` | model | transform/validation | same file, especially `PolicyRunResult` and `CalibratedUserSkillResult` | exact |
| `src/career_evidence_graph/domain/invariants.py` | utility | transform | same file, especially `validate_user_skill` and `mastery_snapshot_bytes` | exact |
| `src/career_evidence_graph/jd.py` | service | request-response/transform | `src/career_evidence_graph/assessment.py` | role-match |
| `src/career_evidence_graph/validation/store.py` | store | file-I/O | same file, `FormalRunStore` | exact |
| `src/career_evidence_graph/cli.py` | controller | request-response/file-I/O | same file, `assessment` command family | exact |
| `tests/test_jd_models.py` | test | transform | `tests/test_domain_models.py` | exact |
| `tests/test_jd_comparison.py` | test | transform/metamorphic | `tests/test_policy_calibration.py` | exact |
| `tests/test_jd_evaluation.py` | test | batch/evaluation | `tests/test_fixture_mutations.py`; custody supplement `tests/test_run_store.py` | role-match |
| `tests/test_jd_security.py` | test | request-response/file-I/O | `tests/test_security_boundaries.py` | exact |
| `.gitignore` | config | file boundary | same file's existing local-workspace exclusions | exact |
| `validation/jd/README.md` | documentation/config contract | operator input | `references/README.md` for explicit provenance/use boundaries | role-match |
| `validation/jd/proposal.schema.json` | schema | transform/validation | `validation/schemas/audit-probe-plan.schema.json` | exact |
| `validation/jd/evaluation-charter.json` | config/acceptance charter | batch/evaluation | `validation/charter/v1.json` | exact |
| `validation/jd/policies.json` (anticipated name) | config | batch/transform | `validation/calibration/phase-04/policies.json` | exact |
| `validation/jd/intake/` (content-free checkpoint location) | config/workspace | file-I/O | none | no analog |

Runtime-generated accepted-source manifests, priority-company input versions, analysis
bundles, repeated attempts, blinded packets, reviews, and adjudications belong under the
chosen local workspace. They are outputs of the models/store, not additional checked-in
sources of capability truth. In particular, the actual private priority-company list should
not be committed to this public repository merely to satisfy a directory layout.

## Pattern Assignments

### `src/career_evidence_graph/domain/models.py` (model, transform/validation)

**Analog:** existing records in the same file

**Imports and constrained-type pattern** (`domain/models.py:7-21`):

```python
from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..validation.models import StrictModel

ID_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
Identifier = Annotated[str, Field(pattern=ID_PATTERN)]
```

**Versioned policy/result pattern** (`domain/models.py:430-447`):

```python
class PolicyRunResult(StrictModel):
    schema_version: Literal["policy-run-result/v1"] = "policy-run-result/v1"
    policy_version: str = Field(min_length=1)
    policy_snapshot: AggregationPolicy
    input_hashes: tuple[str, ...] = Field(min_length=1)
    policy_hash: str = Field(pattern=SHA256_PATTERN)
    run_sequence: int = Field(ge=1)
    case_results: tuple[CalibrationCaseResult, ...] = Field(min_length=1)
    result_hash: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_case_identity(self) -> PolicyRunResult:
        _unique_ids(tuple(item.case_id for item in self.case_results), "case_results")
        if self.policy_snapshot.policy_version != self.policy_version:
            raise ValueError("policy snapshot must match the retained policy version")
        return self
```

**Authority-preservation pattern** (`domain/models.py:666-690`):

```python
class CalibratedUserSkillResult(StrictModel):
    schema_version: Literal["calibrated-user-skill-result/v1"] = (
        "calibrated-user-skill-result/v1"
    )
    result_id: Identifier = Field(pattern=ID_PATTERN)
    skill_id: Identifier = Field(pattern=ID_PATTERN)
    mastery: int = Field(ge=0, le=100)
    admitted_assessment_ids: tuple[Identifier, ...] = Field(min_length=1)
    source_envelope: AssessmentSourceEnvelope
    authority_label: Literal["reviewed-user-truth", "derived-counterfactual"]

    @model_validator(mode="after")
    def validate_baseline(self) -> CalibratedUserSkillResult:
        _unique_ids(self.admitted_assessment_ids, "admitted_assessment_ids")
        if self.authority_label != self.source_envelope.authority_label:
            raise ValueError("result authority must retain source authority")
        # Additional anchor and promotion checks follow.
        return self
```

**Apply:** add only the strict source/proposal/accepted-requirement, requirement-judgment,
score-policy, route, analysis, priority-input-version, repeated-attempt, and review records the
phase actually needs. Each record should inherit the existing `StrictModel`, carry a literal
schema version, constrain 0-100 values with `Field`, and use whole-model validators for span
reconstruction, source-hash binding, policy/version binding, route-overlay restrictions, and
lineage completeness. Do not define another `Skill`, mastery result, or base model. Do not use
the three-state `ProductEffectLabels` as the four-state JD requirement judgment.

---

### `src/career_evidence_graph/domain/invariants.py` (utility, transform)

**Analog:** existing pure fail-closed validators in the same file

**Exact-Skill lineage pattern** (`domain/invariants.py:49-69`):

```python
def validate_user_skill(
    result: CalibratedUserSkillResult,
    admitted_assessments: tuple[ContributionSkillAssessment, ...],
) -> CalibratedUserSkillResult:
    if not admitted_assessments:
        raise ValueError("user Skill result requires admitted assessments")
    if any(assessment.skill_id != result.skill_id for assessment in admitted_assessments):
        raise ValueError("user Skill result may reference only the exact same Skill")
    assessments_by_id = {assessment.id: assessment for assessment in admitted_assessments}
    if set(result.admitted_assessment_ids) != set(assessments_by_id):
        raise ValueError("user Skill result must retain every admitted assessment")
    baseline = assessments_by_id.get(result.baseline_assessment_id)
    if baseline is None:
        raise ValueError("user Skill result baseline is missing")
    return result
```

**Canonical non-propagation snapshot** (`domain/invariants.py:359-384`):

```python
def mastery_snapshot_bytes(fixture: CareerEvidenceFixture) -> bytes:
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
    # User-Skill view projection follows.
    return canonical_json_bytes({"assessments": assessments, "user_skill_views": views})
```

**Stable failure collection** (`domain/invariants.py:387-456`): existing validators collect
explicit `(code, path)` violations, deduplicate them, sort them deterministically, and then
raise `FixtureValidationError` without repairing input.

**Apply:** keep source-span reconstruction, accepted-packet/source-hash binding, exact-Skill
judgment lineage, the four distinct gap meanings, and graph isolation as pure functions. Hash
the mastery projection before and after comparison, and also hash a fuller graph-input
envelope containing assessment versions and source lineage; the mastery snapshot alone is not
full custody evidence. No invariant may write to assessment, audit, policy, or routing state.

---

### `src/career_evidence_graph/jd.py` (service, request-response/transform)

**Analog:** `src/career_evidence_graph/assessment.py`

**Read-only authority partition pattern** (`assessment.py:939-963`):

```python
def aggregate_user_skills(
    records: tuple[AssessmentRun, ...],
    *,
    promotion_decisions: tuple[AnchorPromotionDecision, ...] = (),
) -> tuple[CalibratedUserSkillResult, ...]:
    admitted_by_partition: dict[tuple[str, str], list[ContributionSkillAssessment]] = {}
    policy_by_partition: dict[tuple[str, str], str] = {}
    records_by_assessment_id: dict[str, AssessmentRun] = {}
    for record in records:
        proposal = record.proposal
        if record.admission.assessment_id != proposal.id:
            raise AssessmentWorkflowError("admission does not bind the effective assessment")
        if record.admission.admission_status != AssessmentAdmissionStatus.ADMITTED:
            continue
        if proposal.source_envelope is None or proposal.mastery_anchor_fit is None:
            raise AssessmentWorkflowError("admitted assessment lacks effective lineage")
        partition = (proposal.skill_id, proposal.source_envelope.authority_label)
        admitted_by_partition.setdefault(partition, []).append(proposal)
```

**Stable isolation projection** (`assessment.py:751-762`):

```python
def aggregation_snapshot_bytes(results: tuple[CalibratedUserSkillResult, ...]) -> bytes:
    return canonical_json_bytes(
        [
            {
                "skill_id": result.skill_id,
                "mastery": result.mastery,
                "anchor_id": result.anchor_id,
            }
            for result in sorted(results, key=lambda item: item.skill_id)
        ]
    )
```

**Apply:** make the comparison core a pure function over an accepted JD packet, a fully
verified immutable graph envelope, candidate/active score policy, and versioned priority
input. It should perform these stages in order:

1. admit only normal-use graph results with exact authority `reviewed-user-truth` and resolve
   every cited assessment back to Experience, Contribution, Evidence, context, assistance,
   and limitation lineage;
2. produce and retain one of `supported`, `partially-supported`, `unsupported`, or `uncertain`
   for every accepted requirement before aggregating a score;
3. compute the transparent weighted score and apply the non-compensatory missing-core cap;
4. derive the ordinary route;
5. apply a pure route overlay for only `evidence-strong-match` or
   `user-priority-company`, leaving score, judgments, evidence, and graph unchanged;
6. select evidence-bearing Contributions and produce the concise/default plus expanded
   technical report projection in deterministic order.

No store writes belong inside the comparison function. A proposer, if added later, may only
produce an untrusted proposal; it cannot accept requirements, score, route, or mutate graph
truth.

**Do not copy this behavior for EVAL-03** (`assessment.py:1464-1467`):

```python
existing = next((item for item in history.runs if item.result_hash == result_hash), None)
if existing is not None:
    return existing
```

Phase 4 intentionally deduplicates identical semantic results. Phase 5 must retain three
distinct immutable attempt IDs even when all semantic result hashes are equal.

---

### `src/career_evidence_graph/validation/store.py` (store, file-I/O)

**Analog:** existing `FormalRunStore`

**Safe path and atomic canonical JSON pattern** (`validation/store.py:62-90`):

```python
class FormalRunStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.runs_root = self.workspace / "formal-runs"

    def _run_path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise FormalRunStorageError("run_id contains unsafe path characters")
        candidate = self.runs_root / run_id
        if candidate.parent.resolve() != self.runs_root.resolve():
            raise FormalRunStorageError("run destination escapes the formal-runs root")
        return candidate

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        data = canonical_json_bytes(value) + b"\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
```

**Create-only and linked-rerun guards** (`validation/store.py:111-125`):

```python
destination = self._run_path(run_id)
self.runs_root.mkdir(parents=True, exist_ok=True)
if destination.exists():
    raise FormalRunStorageError(f"formal run already exists: {run_id}")
if set(lineage_inputs) != set(REQUIRED_INPUTS):
    raise FormalRunStorageError("lineage inputs must contain the exact required keys")
if parent_run_id is not None:
    self.verify(parent_run_id)
    if not change_reason or not change_reason.strip():
        raise FormalRunStorageError("linked rerun requires a non-empty change reason")
    if diff is None:
        raise FormalRunStorageError("linked rerun requires an explicit diff")
```

**Full verification pattern** (`validation/store.py:252-331`): verification rejects ancestry
cycles, unsafe directories, invalid manifests, missing or undeclared payloads, symlinks,
resolved-path escapes, content-hash mismatch, correction drift, live-model identity drift, and
invalid parents before returning a manifest.

**Apply:** refactor or reuse the generic safe-path, canonical-write, atomic-directory,
manifest, hash, correction, and ancestry primitives rather than creating another serializer or
store. Keep a normal personal analysis record semantically distinct from a formal evaluation
run. Use one immutable attempt bundle per EVAL-03 attempt; identical results still have three
distinct attempt IDs. Any intake/lineage/trust failure publishes no partial score, route, or
formal result.

---

### `src/career_evidence_graph/cli.py` (controller, request-response/file-I/O)

**Analog:** existing `assessment` command family

**JSON emission pattern** (`cli.py:56-81`):

```python
def _json_file(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _emit(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
```

The actual helper uses a Pydantic-aware `default` lambda; preserve that existing helper rather
than adding another encoder.

**Nested argparse pattern** (`cli.py:103-105,218-287`):

```python
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    # ...
    assessment = commands.add_parser("assessment")
    assessment_commands = assessment.add_subparsers(
        dest="assessment_command", required=True
    )
```

**Stable error boundary** (`cli.py:290-292,681-718`): `main()` parses once, dispatches inside
one `try`, emits successful JSON to stdout, emits structured workflow/storage errors to stderr,
and returns `2` for rejected input or workflow failure.

**Apply:** add one narrow `jd` command family for prepare/accept, analyze, inspect, and
development evaluation. Reuse `_emit`, `_emit_error`, `Path`, and the existing main dispatch.
Trust failures must return nonzero without writing an analysis, and errors must not echo raw
private JD text. Do not add an API, web UI, CLI framework, or normal-use reviewer workflow.

---

### `tests/test_jd_models.py` (test, transform)

**Analog:** `tests/test_domain_models.py`

**Single-fault boundary parameterization** (`test_domain_models.py:262-271`):

```python
@pytest.mark.parametrize(
    "field", ["demonstrated_mastery", "skill_centrality", "evidence_confidence"]
)
@pytest.mark.parametrize("value", [-1, 101])
def test_assessment_rejects_each_out_of_range_score_independently(field, value):
    payload = deepcopy(_assessment_payload())
    payload[field] = value

    with pytest.raises(ValidationError):
        ContributionSkillAssessment.model_validate(payload)
```

**Apply:** build small, explicitly non-real schema objects; deep-copy and mutate exactly one
field per case. Cover exact source spans, source-hash mismatch, required/preferred/core flags,
all four judgment values, score bounds, strict unknown-field rejection, duplicate IDs,
accepted-versus-unaccepted state, and cross-field validators. These unit objects are schema
fixtures only, not substitutes for the three user JDs.

---

### `tests/test_jd_comparison.py` (test, transform/metamorphic)

**Analog:** `tests/test_policy_calibration.py`

**Same-input comparison assertions** (`test_policy_calibration.py:94-100`):

```python
assert baseline.input_hashes == conservative.input_hashes
assert baseline.policy_hash != conservative.policy_hash
assert baseline.result_hash != conservative.result_hash
assert comparison.input_hashes == baseline.input_hashes
assert comparison.active_policy_version is None
assert comparison.run_variance == 0
```

**Apply:** compare candidate policies against identical accepted inputs without activation;
assert deterministic hashes, explicit per-requirement deltas, and no graph/policy authority
mutation. Add metamorphic tests showing:

- different accepted requirement relevance changes only the derived comparison;
- a missing core hard requirement caps the score/route despite numerous preferred matches;
- priority-company status changes only final route and reason;
- evidence volume, duplicate relationships, ontology adjacency, centrality, confidence, and JD
  wording cannot inflate mastery or create support;
- positive/partial judgments always cite admitted Contribution evidence and limitations;
- missing capability, missing evidence, context mismatch, and uncertainty remain distinct.

---

### `tests/test_jd_evaluation.py` (test, batch/evaluation)

**Primary analog:** `tests/test_fixture_mutations.py`

**Order-independent deterministic matrix** (`test_fixture_mutations.py:144-153`):

```python
first = validate_mutation_suite(sealed, _cases())
second = validate_mutation_suite(sealed, list(reversed(_cases())))

assert first.model_dump(mode="json") == second.model_dump(mode="json")
assert canonical_json_bytes(first.model_dump(mode="json")) == canonical_json_bytes(
    second.model_dump(mode="json")
)
assert [result.case_id for result in first.results] == sorted(EXPECTED_CODES)
```

**Custody supplement:** `tests/test_run_store.py:41-50`

```python
_create(store, charter_path)
run_path = tmp_path / "formal-runs" / "run-1"
original = {path.name: path.read_bytes() for path in run_path.iterdir()}

with pytest.raises(FormalRunStorageError, match="already exists"):
    _create(store, charter_path)

assert {path.name: path.read_bytes() for path in run_path.iterdir()} == original
```

**Apply:** declare a complete named adversarial/counterfactual inventory; mutate one trust fact
at a time; require one stable expected blocker/result per case; retain the accepted base and
graph bytes unchanged. Retain three distinct attempt bundles and compare canonical semantic
results rather than deduplicating attempts. Build the preregistered opaque A/B packet,
independent judgment, preserved disagreement, and separate adjudication as immutable records.
The actual three-JD matrix remains blocked until all three user-supplied files and the graph
snapshot are accepted.

---

### `tests/test_jd_security.py` (test, request-response/file-I/O)

**Analog:** `tests/test_security_boundaries.py`

**Reject-before-write pattern** (`test_security_boundaries.py:90-97`):

```python
@pytest.mark.parametrize("unsafe_run_id", ("../escape", "/tmp/escape", "a/b", r"a\b"))
def test_unsafe_run_paths_are_rejected_before_any_write(tmp_path, unsafe_run_id):
    store = FormalRunStore(tmp_path)

    with pytest.raises(FormalRunStorageError, match="unsafe path"):
        store.verify(unsafe_run_id)

    assert not (tmp_path / "formal-runs").exists()
```

**Apply:** cover path traversal, absolute paths, separators, symlinks/aliases, undeclared or
tampered payloads, missing/tampered parents, stale graph versions, broken lineage, hidden
controls/bidi/zero-width/NUL input, prompt injection, ambiguous company identity, and
zero-publication on every blocker. Assert the output tree and mastery/full graph snapshots are
byte-identical after rejection. Optional replay tests must prove no live runner can be reached.

---

### `validation/jd/policies.json` (config, batch/transform)

**Analog:** `validation/calibration/phase-04/policies.json`

**Root declarations plus inactive versioned candidates** (`policies.json:1-24`):

```json
{
  "schema_version": "assessment-policy-corpus/v1",
  "integer_semantics": "All mastery and confidence cutoffs are exact inclusive integers; no average, tolerance, rounding, or float coercion is permitted.",
  "policies": [
    {
      "schema_version": "aggregation-policy/v1",
      "policy_version": "policy-04-baseline-60",
      "activation_status": "candidate",
      "notice": "Unresolved Phase 4 calibration candidate; it is not an active product policy."
    }
  ]
}
```

**Apply:** use a Phase 5-specific root and policy schema, but copy the explicit semantics,
individually versioned policy snapshots, `candidate`/`active` lifecycle, and non-authoritative
notice. Store required/preferred weights, status points, core cap, score bounds, ordinary-route
thresholds, and evidence-exception gates as inspectable values. Do not copy Phase 4 mastery
threshold fields or imply the Phase 4 active pointer activates a JD policy. No Phase 5 numeric
policy becomes active before accepted user fixtures and reviewed calibration.

---

### `validation/jd/intake/` (content-free checkpoint location, file-I/O)

**Analog:** none. The repository has no tracked empty validation directory or `.gitkeep`, and
the STOA fixture tree is intentionally not an intake analog because it contains checked-in
payloads.

**Apply:** follow the Phase 5 context/research contract directly. If the planner needs a
tracked sentinel, it must be content-free and state that no JD body is present. Do not populate
it with examples, sourced text, synthetic requirements, company names, or guessed hashes. The
execution checkpoint must create accepted manifests from the three user-supplied files rather
than treating a Wave 0 sentinel as evaluation evidence.

## Shared Patterns

### Strict Contracts

**Source:** `src/career_evidence_graph/validation/models.py:12-15`

**Apply to:** every Phase 5 model and persisted record

```python
class StrictModel(BaseModel):
    """Base model that rejects silent schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)
```

Use one existing base; validate cross-field custody with `@model_validator(mode="after")`.

### Canonical Identity

**Source:** `src/career_evidence_graph/validation/hashing.py:12-27`

**Apply to:** accepted JD sources, structured packets, graph envelopes, policies, analysis
results, attempts, review packets, and adjudication

```python
def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

def sha256_digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"
```

Do not add another JSON serializer, float tolerance, filename-only cache key, or hash format.

### Read-Only Capability Truth

**Sources:** `domain/models.py:328-350,544-595,666-701`;
`assessment.py:939-1027`; `domain/invariants.py:49-69,359-384`

**Apply to:** comparison, reporting, selection, counterfactuals, and evaluation

Require current admitted assessment versions and `reviewed-user-truth` authority for normal
use. Resolve every cited assessment to Contribution/Evidence/attribution/assistance lineage.
Never infer capability from a JD, résumé wording, title, repository, credential, ontology
relation, company priority, selected route, or evidence count.

### Immutable History and Reruns

**Sources:** `validation/store.py:92-125,158-218,252-331`;
`validation/models.py:208-267`

**Apply to:** analysis history, priority-input versions, policy versions, formal attempts,
corrections, independent review, and adjudication

Publish create-only canonical bundles. A rerun links to a verified parent and records reason and
diff; it never overwrites history. Preserve proposal and reviewer disagreement. Normal analysis
and formal evaluation may share storage primitives but must use distinct semantic record types.

### Fail-Closed Input and Privacy Boundary

**Sources:** `validation/store.py:62-90,252-331`; `cli.py:681-718`

**Apply to:** local-file intake, pasted text, accepted packets, graph loading, and reports

Decode declared UTF-8 once, retain/hash exact bytes, detect hidden controls instead of silently
normalizing them, reject unsafe paths/symlinks, require reconstructable source spans and
explicit acceptance, and publish no score or route after a trust failure. Keep private JD and
company content out of routine console errors and checked-in fixtures.

### Testing Discipline

**Sources:** `tests/test_domain_models.py`, `tests/test_fixture_mutations.py`,
`tests/test_policy_calibration.py`, `tests/test_run_store.py`, and
`tests/test_security_boundaries.py`

**Apply to:** all four Wave 0 test files

Use complete small builders, one-fault mutations, explicit `pytest.param(..., id=...)` labels,
canonical byte comparisons, pre/post snapshots, exact error codes, and output-tree assertions.
Deterministic offline runs must be byte-identical. Three equal semantic outcomes still require
three separately retained attempt manifests; material variance is retained and blocks rather
than being averaged.

## No Analog Found

| File/Area | Role | Data Flow | Reason |
|-----------|------|-----------|--------|
| `validation/jd/intake/` | config/workspace | file-I/O | No tracked empty-directory convention exists, and existing STOA payloads must not be copied as placeholder JDs. |

There is also no reason to create a standalone renderer or web component. The existing CLI
emits deterministic JSON, and the smallest readable report projection can remain in `jd.py`
until a separate presentation requirement exists.

## Metadata

**Analog search scope:** `src/career_evidence_graph/`, `tests/`, `validation/`

**Files inventoried:** 91

**Primary analogs read:** `domain/models.py`, `domain/invariants.py`, `assessment.py`,
`validation/models.py`, `validation/store.py`, `validation/hashing.py`, `cli.py`,
`test_domain_models.py`, `test_policy_calibration.py`, `test_fixture_mutations.py`,
`test_run_store.py`, `test_security_boundaries.py`, and Phase 4 policy/history configuration

**Project skills:** no project-local `SKILL.md` exists under `.codex/skills/` or
`.agents/skills/`

**Pattern extraction date:** 2026-08-28

**Fixture custody:** no JD was searched for, selected, copied, synthesized, or added while
mapping these patterns.
