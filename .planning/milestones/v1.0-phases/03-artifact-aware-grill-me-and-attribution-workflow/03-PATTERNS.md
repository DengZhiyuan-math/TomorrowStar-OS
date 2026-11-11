# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow - Pattern Map

**Mapped:** 2026-08-26  
**Files analyzed:** 15  
**Analogs found:** 14 / 15

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/career_evidence_graph/audit/__init__.py` | config/package | transform | `src/career_evidence_graph/validation/__init__.py` | role-match |
| `src/career_evidence_graph/audit/models.py` | model | transform | `src/career_evidence_graph/domain/models.py` | exact |
| `src/career_evidence_graph/audit/store.py` | service | file-I/O | `src/career_evidence_graph/validation/store.py` | exact |
| `src/career_evidence_graph/audit/workflow.py` | utility + thin service | event-driven + request-response | `src/career_evidence_graph/domain/invariants.py`; `src/career_evidence_graph/domain/fixtures.py` | role-match |
| `src/career_evidence_graph/domain/models.py` | model | transform | itself | modification |
| `src/career_evidence_graph/cli.py` | route | request-response | itself | modification |
| `tests/test_audit_models.py` | test | transform | `tests/test_domain_models.py` | exact |
| `tests/test_audit_inspection.py` | test | file-I/O | `tests/test_stoa_fixture.py` | exact |
| `tests/test_audit_policy.py` | test | event-driven | `tests/test_domain_invariants.py` | role-match |
| `tests/test_audit_store.py` | test | file-I/O | `tests/test_run_store.py` | exact |
| `tests/test_audit_attribution.py` | test | event-driven | `tests/test_domain_models.py` | role-match |
| `tests/test_assistance_migration.py` | test | transform | `tests/test_domain_models.py` | role-match |
| `tests/test_audit_conclusion.py` | test | event-driven | `tests/test_run_store.py` | role-match |
| `tests/test_audit_cli.py` | test | request-response | `tests/test_cli_tracer.py` | exact |

## Pattern Assignments

### Intentional cohesive `workflow.py` shape

Phase 3 deliberately uses one `audit/workflow.py` instead of separate `policy.py` and `service.py`. The workflow is small, deterministic, and has one consumer (the CLI), so splitting pure transitions from sealed-fixture orchestration would add files and forwarding abstractions without independent reuse. Per AGENTS.md YAGNI, keep pure transition functions and the thin start/answer/inspect orchestration in this cohesive module; keep all file I/O in `audit/store.py`. Revisit a split only when a second caller or independently reusable policy boundary exists.

### `src/career_evidence_graph/audit/models.py` (model, transform)

**Analog:** `src/career_evidence_graph/domain/models.py`, with `StrictModel` from `src/career_evidence_graph/validation/models.py`.

**Imports and strict-contract pattern** (`domain/models.py:7-19`; `validation/models.py:9-16`):

```python
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..validation.models import StrictModel

Identifier = Annotated[str, Field(pattern=ID_PATTERN)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Versioned record and local invariant pattern** (`domain/models.py:73-83`):

```python
class Contribution(StrictModel):
    schema_version: Literal["contribution/v1"] = "contribution/v1"
    id: Identifier = Field(pattern=ID_PATTERN)
    experience_id: Identifier = Field(pattern=ID_PATTERN)
    summary: str = Field(min_length=1)
    claim_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_claim_ids(self) -> Contribution:
        _unique_ids(self.claim_ids, "claim_ids")
        return self
```

Create frozen, schema-versioned records for inspection facts, question/reason, answer/action, area coverage, ownership and assistance rounds, conflict, snapshot/event, conclusion entry, and review outcome. Model the verified capability boundary as prose/levels, not `ContributionSkillAssessment` or any numeric mastery field.

### `src/career_evidence_graph/audit/workflow.py` — pure transition portion (utility, event-driven)

**Analog:** `src/career_evidence_graph/domain/invariants.py` (pure deterministic validation), augmented with audit models rather than a live model call.

**Fail-closed deterministic aggregation pattern** (`domain/invariants.py:402-416`):

```python
def validate_career_evidence_fixture(fixture: CareerEvidenceFixture) -> FixtureValidationResult:
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
```

**State-independent review readiness pattern** (`domain/fixtures.py:496-519`):

```python
pending = {
    group: tuple(
        item.candidate_id for item in review.items if getattr(item, group).status == "pending"
    )
    for group in _REVIEW_GROUPS
}
...
return ReviewStatus(
    sealable=(not any(pending.values()) and any(item.fact.status == "accepted" for item in review.items)),
    pending_ids_by_group=pending,
)
```

Make transitions pure: accept one action and current `AuditSnapshot`, return a validated next snapshot plus one next question or a terminal/review state. Encode D-02 through D-09 as guards: one question only, demanding-to-simple order, at most one same-level follow-up, branch “not my work” to ownership clarification, and no capability conclusion until the strongest established and immediate higher unestablished levels are known.

### `src/career_evidence_graph/audit/store.py` (service, file-I/O)

**Analog:** `src/career_evidence_graph/validation/store.py`.

**Workspace containment and identifier allowlist** (`validation/store.py:62-75`):

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
```

**Atomic canonical JSON write** (`validation/store.py:77-90`):

```python
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

Use an `AuditStore` limited to its resolved audit root. Persist current snapshot atomically and audit history append-only/hash-linked; validate every loaded JSON payload through the strict models; reject unsafe IDs, symlinks, undeclared files, and corruption. Do not repurpose `FormalRunStore`, whose fixed formal-run manifest and charter fields are phase-1-specific.

### `src/career_evidence_graph/audit/workflow.py` — thin orchestration portion (service, request-response)

**Analog:** `src/career_evidence_graph/domain/fixtures.py`.

**Bounded, verified source-input pattern** (`domain/fixtures.py:418-437`):

```python
def verify_source_manifest(path: Path) -> SourceManifestVerification:
    try:
        manifest = SourceManifest.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise _source_scope_error(f"manifest is invalid: {exc}") from exc
    _validate_manifest_scope(manifest)
    for document in manifest.documents:
        ...
        if sha256_digest(object_bytes) != document.content_sha256:
            raise _source_scope_error("pinned document content hash mismatch")
```

**Documentary-proof boundary** (`domain/fixtures.py:53-76`):

```python
class PermittedDocument(StrictModel):
    ...
    personal_claim_proof: Literal["none"]

    @model_validator(mode="after")
    def validate_proof_limit(self) -> PermittedDocument:
        ...
        if self.proof_limit != expected or self.personal_claim_proof != "none":
            raise ValueError("document proof role must remain non-personal and bounded")
```

Load the sealed fixture through its existing loader, select one existing Contribution, derive only linked claims/evidence/manifest facts and limitations into an inspectable `ArtifactInspectionRecord`, then hand that record to pure policy. Artifact contents can justify a reason-preface but cannot settle ownership, assistance, or capability. This service should orchestrate start/answer/skip/pause/resume/inspect/review without embedding transition rules.

### `src/career_evidence_graph/domain/models.py` (model, transform — modification)

**Analog:** existing attribution separation in the same file.

**Current independent axes** (`domain/models.py:32-35`, `86-95`):

```python
ResponsibilityKind = Literal["user", "team", "other_person", "non_responsibility"]
AssistanceKind = Literal["none", "codex_assisted", "third_party"]

class ContributionClaim(StrictModel):
    ...
    responsibility: ResponsibilityKind
    assistance: AssistanceKind
    confirmation_status: ConfirmationStatus
```

Evolve only the assistance contract needed for D-12: read-compatibly accept legacy sealed `codex_assisted`; write new audit/domain records using canonical `coding-agent-assisted`; retain provider/tool/model in separate provenance metadata. Preserve responsibility as a separate axis and do not rewrite `known-good.json` bytes.

### `src/career_evidence_graph/cli.py` (route, request-response — modification)

**Analog:** existing nested argparse commands and JSON/error boundary.

**Parser/subcommand pattern** (`cli.py:48-79`):

```python
parser = argparse.ArgumentParser(prog="career-evidence")
commands = parser.add_subparsers(dest="command", required=True)

fixture = commands.add_parser("fixture")
fixture_commands = fixture.add_subparsers(dest="fixture_command", required=True)
fixture_source = fixture_commands.add_parser("source")
fixture_source_commands = fixture_source.add_subparsers(dest="source_command", required=True)
fixture_source_verify = fixture_source_commands.add_parser("verify")
fixture_source_verify.add_argument("--manifest", required=True)
```

**Structured output and fail-closed command dispatch** (`cli.py:42-45`, `123-128`, `277-302`):

```python
def _emit(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
...
except (..., ValidationError, OSError, json.JSONDecodeError) as exc:
    print(f"error: {exc}", file=sys.stderr)
    return 2
```

Add one `audit` command group with the smallest subcommands needed for start, answer, skip, pause/resume, inspect, entry review, and whole-conclusion review. Read action JSON explicitly; emit one JSON object; wire service/store dependencies at dispatch only. Keep the existing live-model command separate and opt-in.

### Audit tests (test roles)

**Contracts and migration:** `tests/test_audit_models.py`, `tests/test_audit_attribution.py`, and `tests/test_assistance_migration.py` copy `tests/test_domain_models.py`.

**Independent-axis parametrization** (`tests/test_domain_models.py:227-241`):

```python
@pytest.mark.parametrize("responsibility", ["user", "team", "other_person", "non_responsibility"])
@pytest.mark.parametrize("assistance", ["none", "codex_assisted", "third_party"])
def test_claim_responsibility_and_assistance_are_independent(...):
    claim = ContributionClaim(...)
    assert (claim.responsibility, claim.assistance) == (responsibility, assistance)
```

**Strict unknown-field rejection** (`tests/test_domain_models.py:324-329`):

```python
payload["surprise"] = True
with pytest.raises(ValidationError):
    CareerEvidenceFixture.model_validate(payload)
```

Test every audit model’s unknown fields/invalid IDs/invalid state combinations; separately prove ownership then assistance turns, conflict preservation, and legacy read/new canonical write without mutation of sealed fixture bytes.

**Inspection:** `tests/test_audit_inspection.py` copies `tests/test_stoa_fixture.py`.

**Pinned-boundary negative matrix** (`tests/test_stoa_fixture.py:63-79`):

```python
@pytest.mark.parametrize(("field", "replacement"), [("tracked_path", "../private.txt"), ...])
def test_source_manifest_rejects_scope_escape(...):
    ...
    with pytest.raises(SourceScopeError, match="source-scope"):
        verify_source_manifest(altered)
```

Assert inspection includes only the selected contribution’s sealed linked sources, preserves proof limits/conflicts, and cannot create personal-responsibility/capability facts.

**Policy and conclusion:** `tests/test_audit_policy.py` and `tests/test_audit_conclusion.py` copy `tests/test_domain_invariants.py`/`tests/test_run_store.py`. Build deterministic snapshots/actions and assert exact next state/question: hard-to-simple, one same-level follow-up, not-known descent, attribution branch, no repeated answered question on resume, skip labelling, completion coverage, and immutable proposal/correction/rejection lineage.

**Store:** `tests/test_audit_store.py` copies `tests/test_run_store.py`.

**No-overwrite and tamper tests** (`tests/test_run_store.py:41-50`, `123-142`):

```python
original = {path.name: path.read_bytes() for path in run_path.iterdir()}
with pytest.raises(FormalRunStorageError, match="already exists"):
    _create(store, charter_path)
assert {path.name: path.read_bytes() for path in run_path.iterdir()} == original
```

Cover atomic snapshot replacement, invalid IDs, symlink/path escape, malformed/corrupt JSON, append-only events, and immutable original proposal.

**CLI:** `tests/test_audit_cli.py` copies `tests/test_cli_tracer.py`.

**Source-tree subprocess helper** (`tests/test_cli_tracer.py:168-183`):

```python
def _run_source(*args: str, pythonpath_prefix: Path | None = None) -> subprocess.CompletedProcess[str]:
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment = os.environ | {"PYTHONPATH": os.pathsep.join([source_root])}
    return subprocess.run(
        [sys.executable, "-m", "career_evidence_graph.cli", *args],
        check=False, capture_output=True, text=True, env=environment,
    )
```

Exercise the offline sequence start → answer/clarify → pause → resume → inspect → review, assert JSON output and persistence, and prove no live adapter/network process is needed.

### `src/career_evidence_graph/audit/__init__.py` (config/package, transform)

**Analog:** `src/career_evidence_graph/validation/__init__.py`.

Keep this package marker minimal; export no duplicate domain types. No substantive analog is necessary beyond the repository’s empty package initializers.

## Shared Patterns

### Strict inputs and schema evolution

**Sources:** `src/career_evidence_graph/validation/models.py:12-16`; `src/career_evidence_graph/domain/models.py:32-35`  
**Apply to:** audit models, migration parser, CLI action envelopes.

All records are frozen and reject extras. Version every persisted audit record. Implement explicit legacy read compatibility; do not mutate sealed source fixtures.

### Artifact and attribution boundary

**Sources:** `src/career_evidence_graph/domain/fixtures.py:53-76`, `418-437`; `src/career_evidence_graph/domain/models.py:86-95`  
**Apply to:** inspection service, question reasons, policy, conclusion generator.

Documents are non-personal proof only. Responsibility and assistance are distinct user-confirmed facts; conflict records retain both documentary and user claims.

### Atomic, bounded persistence

**Source:** `src/career_evidence_graph/validation/store.py:65-90`, `252-331`  
**Apply to:** audit store and all pause/resume/review writes.

Resolve a single workspace root, validate identifiers, canonicalize and hash JSON, write atomically, and verify before returning persisted values. Reject tampered/aliased payloads rather than repairing them in place.

### Immutable review lineage

**Sources:** `src/career_evidence_graph/validation/models.py:259-267`; `src/career_evidence_graph/validation/store.py:160-180`  
**Apply to:** per-entry and whole-conclusion review.

Store an original proposal and its hash in every correction/confirmation/rejection record with reviewer and reason. A user edit must create a new lineage record, never overwrite the proposed conclusion.

### Offline CLI and tests

**Sources:** `src/career_evidence_graph/cli.py:42-45`, `277-302`; `tests/test_cli_tracer.py:190-247`  
**Apply to:** audit commands and all default tests.

Use argparse and one sorted JSON result. Default tests must use deterministic fixture/action data and temporary local workspaces; no provider call is needed to test audit state transitions.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| None | — | — | The repository has close patterns for every substantive Phase 3 file; `audit/__init__.py` is intentionally minimal. |

## Metadata

**Analog search scope:** `src/career_evidence_graph/{domain,validation}`, `src/career_evidence_graph/cli.py`, `tests/`  
**Files scanned:** 12 source/test analogs plus Phase 3 context and research  
**Pattern extraction date:** 2026-08-26
