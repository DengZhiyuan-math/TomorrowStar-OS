# Phase 7: Career Source Custody and Private Workspace - Research

**Researched:** 2026-08-29
**Domain:** Local-first source custody, private filesystem workspace, provenance lineage, and privacy-safe CLI operation
**Confidence:** HIGH for repository integration and existing primitives; MEDIUM for the initial corpus-specific source adapters and the exact private-repository bootstrap checklist.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Skill-first authority and resume direction

- **D-01:** Skill is the stable human capability at the center of the product. Projects,
  employment, degrees, courses, publications, and other Experiences are ways to acquire,
  exercise, contextualize, or demonstrate Skills; they are not more authoritative than the
  capability itself.
- **D-02:** The system direction is confirmed Skill graph → JD-specific relevance and
  Contribution selection → targeted resume. It is never resume → authoritative Skill graph.
- **D-03:** An existing resume may create non-authoritative discovery clues only. Every clue
  must be regrounded in real Experience, Contribution, Evidence, self-report, or direct
  capability-examination lineage before later phases may admit it. A resume cannot establish
  inventory completeness, responsibility, mastery, or evidence confidence.
- **D-04:** Formal transcripts, degrees, courses, and certificates receive no privileged mastery
  weight. Any self-taught Skill may reach reviewed mastery through observable capability;
  completing a formal course proves neither independence nor a mastery anchor.
- **D-05:** Keep three meanings independent: `mastery` answers what the user can actually do;
  `assessment confidence` answers how reliably that capability was examined; and `market proof
  strength` answers how convincingly the capability can be communicated to a recruiter. Source
  completeness and institutional prestige cannot substitute for any of these meanings. —
  **Reversibility:** costly — collapsing these meanings after personal graph history exists would
  require migrating assessment, JD-comparison, and resume-consumption contracts.
- **D-06:** A Skill may exist as `claimed-unverified`, retaining self-assessment and its evidence
  gap. This status means capability has not yet been examined; it does not mean self-taught,
  non-credentialed, or low mastery. Phase 7 must not turn source availability into the gate for
  creating or retaining such a Skill.

### Public harness and private career repository

- **D-07:** The public TomorrowStar OS Git repository contains only the generic harness,
  schemas, documentation, and fully synthetic examples. It must contain no real resume or Skill
  graph content and no private-data-derived hashes, opaque IDs, counts, paths, reports, or logs.
  — **Reversibility:** one-way — a personal artifact or fingerprint committed publicly cannot be
  reliably made private again by deleting a later Git revision.
- **D-08:** Create a separate private Git repository for readable personal Skill graph content,
  resume material, the source registry, source/capture hashes, and transformation records. Do
  not use a Git submodule or store its remote URL or local path in the public repository.
- **D-09:** Keep exact raw and sensitive source bodies under the private repository's ignored
  `.career-evidence/raw/` boundary. Raw bytes do not enter either public Git or private Git
  history. A separate encrypted backup policy may protect this vault without changing the Git
  authority boundary.
- **D-10:** Every public-harness operation targeting personal data receives the private
  repository through an explicit `--workspace /path/to/private-repo` argument. There is no
  hidden current workspace, persisted public pointer, submodule, or second workspace authority.
- **D-11:** Human-facing graph, resume, source, and report views inside the explicitly selected
  private workspace may display readable private content without an additional reveal
  confirmation in the first version. Routine status, background logs, committed output, and
  errors remain content-free and expose only safe identifiers, counts, hashes, byte counts, and
  stable redacted diagnostic codes as required by INV-07.

### Full-career source-universe declaration

- **D-12:** Use a two-level registry. The coverage level enumerates supported career categories
  such as employment, projects, research, publications, education, teaching, internships, open
  source, and related work so omissions remain visible. The source level declares each logical
  source and its availability. This registry supports completeness and provenance; it does not
  make Experience the product's conceptual center.
- **D-13:** A source may later support several Skills and Contributions. Category membership or
  source count has no mastery effect, and no resume or repository listing may be treated as a
  complete career universe by itself.
- **D-14:** User recollection is a first-class `self-reported` source type. It may preserve
  candidate Experiences, Contributions, or facts that would otherwise disappear, but it cannot
  masquerade as independent corroboration or independently increase mastery or assessment
  confidence.
- **D-15:** One revision declares a career-fact cutoff: the date through which career events are
  in scope. Each source capture separately records when and how it was acquired. Material found
  later about pre-cutoff history creates a linked new revision; it never rewrites the earlier
  revision.
- **D-16:** Every unavailable source remains visible with one structured status and an optional
  explanation: `temporarily-unavailable`, `permanently-lost`, `access-restricted`,
  `never-created`, `location-unknown`, or `user-declined`. Do not silently remove unavailable
  sources from coverage.

### Immutable captures, transformation lineage, and duplication

- **D-17:** Retain immutable originals according to source type: exact bytes for files and
  pasted content; repository identity, pinned commit, and relevant blob hashes for Git; a
  time-bound snapshot or export for web and cloud material; and timestamped immutable records
  for self-report, Grill-Me, and examination answers. Source type determines capture mechanics,
  not mastery weight.
- **D-18:** Separate one stable logical `source_id` from immutable `capture_id` versions. Every
  recapture records a new content hash, capture metadata, and predecessor link. Any current
  pointer is explicit, and older graph, examination, or resume results remain bound to their
  original captures. — **Reversibility:** costly — changing this identity split after capture
  history exists requires a manifest and dependent-lineage migration.
- **D-19:** Every derived text or structured proposal retains the input capture/hash,
  transformer or model identity, version, configuration, output hash, and the most precise
  available source locator: page, heading, line, byte span, Git blob, or an explicitly declared
  whole-source fallback. Transformation output is a candidate and receives no automatic fact,
  assessment, or mastery authority.
- **D-20:** Deduplicate identical content or the same underlying fact without erasing its
  logical source identities and provenance links. Repetition across a resume, README,
  portfolio, or another channel cannot mechanically increase mastery or assessment confidence.
  Independent corroboration and market reach remain separately inspectable.

### the agent's Discretion

- Exact strict model names, schema field names, semantic private-workspace namespaces, and CLI
  command names, provided there is one workspace authority and existing storage/hashing helpers
  are reused rather than duplicated.
- Exact source-adapter protocol and initial deterministic format support. Begin with formats in
  the declared private corpus and existing standard-library/Pydantic mechanisms; do not add
  PDF, DOCX, OCR, browser, model-provider, database, or graph-store dependencies speculatively.
- Exact safe error-code taxonomy, identifier syntax, and read-only inspection layout, provided
  routine output cannot echo private labels, paths, source text, or personal fingerprints.
- Exact mechanism for encrypted backup of the ignored raw vault is deferred; Phase 7 must define
  the boundary and report the absence of a backup without silently claiming durability.

### Deferred Ideas (OUT OF SCOPE)

- Design and implement a dedicated Skill-first comprehensive examination engine. It must collect
  provenance-bearing real interview questions, interview-experience reports, and representative
  work tasks; build atomic-Skill coverage; assemble realistic multi-Skill questions; produce
  separate per-Skill proposals plus cross-Skill diagnostics; and admit results only after user
  review. This likely requires restructuring Phases 9-10 or adding a dedicated roadmap phase and
  is not a Phase 7 implementation task.
- Build the ASu-informed evidence-producing packaging loop after the confirmed Skill graph
  exists: use strong-Skill/weak-market-proof states to improve truthful positioning or propose
  real evidence-producing work, then feed new artifacts back through audit. Resume generation
  and gap closure remain downstream capabilities.
- Add reveal confirmations, stronger local permissions, automated leak scanning, encrypted
  raw-vault backup, and recovery procedures after the first-version INV-07 boundary is working.
  Routine status, logs, errors, and public commits remain content-free from the start and are not
  deferred.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| INV-01 | The user can declare the career-source universe, unavailable sources, and a cutoff that define what “all known career history” means for one inventory revision. | Declare one immutable source-universe revision with category coverage, logical sources, availability/disposition, and cutoff; do not accept or seal inventory items. |
| INV-06 | An evaluator can trace every accepted inventory fact and Evidence item to a retained source identity, content hash, capture metadata, and any versioned transformation that produced derived text. | Preserve logical-source → immutable-capture → transformation lineage as strict, hash-bound create-only manifests for Phase 8 consumption. |
| INV-07 | The operator can process raw career sources in the ignored private workspace while committed artifacts, routine status output, logs, and errors expose only safe identifiers, counts, hashes, and redacted diagnostics. | Use the explicit private workspace boundary, raw-vault exclusion, safe status/error envelopes, and adversarial no-echo/no-public-leak tests. |
</phase_requirements>

## Project Constraints (from AGENTS.md)

- Follow this reuse order: omit unnecessary work; reuse repository code; use the standard library; use framework-native capability; reuse installed dependencies; prefer a clear one-line implementation; only then add the smallest tested custom code.
- Avoid over-design, duplicate implementations, unnecessary abstraction, and dependency expansion.
- Keep the project a bounded validation of the Grill-Me → Contribution–Skill assessment → Skill graph → JD-usefulness hypothesis; do not build the full résumé/gap pipeline.
- A Contribution is the minimum auditable fact unit; scores remain per specific Skill and mastery, evidence confidence, duration, context, and JD match retain separate meanings.
- Preserve truthful responsibility attribution and anchor integrity; credentials and source presence cannot establish mastery.
- Preserve upstream provenance when adapting code or patterns.
- Begin implementation only through a GSD execution workflow; this research artifact does not authorize direct implementation.

## Summary

Phase 7 should add one generic career-source custody seam to the existing Python modular monolith. It should own only declaration, capture, transformation lineage, and private-workspace boundary enforcement. It must not construct an inventory acceptance/seal, audit Contributions, resolve Skills, admit mastery, analyze JDs, or generate résumé content. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:1-137]

The repository already contains the primitives this seam needs: one SHA-256 helper, canonical JSON serialization, atomic replacement, create-only bundles, explicit workspace CLI arguments, and content-free raw-input status/error tests. Reuse and factor those primitives; no package or service is justified. [VERIFIED: src/career_evidence_graph/validation/hashing.py:12-27] [VERIFIED: src/career_evidence_graph/validation/store.py:47-89] [VERIFIED: src/career_evidence_graph/cli.py:296-325] [VERIFIED: tests/test_jd_security.py:90-207]

**Primary recommendation:** Create a `workspace.py`/career-source module pair that derives all private paths from an explicit workspace, publishes create-only capture and lineage manifests under semantic namespaces, keeps raw bytes only in ignored `.career-evidence/raw/`, and exposes separate safe versus human-facing inspection views.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Source-universe declaration and cutoff | API / Backend | Database / Storage | Strict domain records validate category/source availability and persist a create-only revision. |
| Raw capture and capture identity | Database / Storage | API / Backend | The private workspace owns bytes and manifests; application code validates and writes them. |
| Transformation lineage | API / Backend | Database / Storage | A pure lineage validator binds input/output hashes and locators before a bundle is published. |
| Private boundary and safe diagnostics | API / Backend | Database / Storage | CLI receives an explicit workspace and emits a redacted envelope; storage rejects unsafe paths. |
| Private readable source inspection | API / Backend | Database / Storage | It is an intentional operator view inside the selected private workspace, never a public-harness output. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---|---|---|---|
| Python standard library (`pathlib`, `hashlib`, `json`, `os`, `tempfile`, `argparse`) | project Python range `>=3.13,<3.14` | Paths, byte hashing, canonical records, atomic publication, CLI | Existing code already implements the required primitives without a new dependency. [VERIFIED: pyproject.toml:6-22] |
| Pydantic | `2.13.4` | Frozen, extra-forbidding source/capture/transformation contracts | It is the existing domain-contract system. [VERIFIED: pyproject.toml:10-13] |
| pytest | `9.1.1` | Offline unit, adversarial, CLI, and public/private-boundary tests | Existing test configuration is offline by default. [VERIFIED: pyproject.toml:18-30] |

### Supporting

| Existing component | Purpose | When to use |
|---|---|---|
| `sha256_digest` | The sole content identity helper | Hash every exact raw capture and deterministic manifest payload; do not add another hash API. Its source is exactly `return f"sha256:{hashlib.sha256(value).hexdigest()}"`. [VERIFIED: src/career_evidence_graph/validation/hashing.py:25-27] |
| `atomic_write_canonical_json` | Atomic current working snapshot/pointer write | Only for mutable working state or explicit current pointer; its writer fsyncs then calls `os.replace`. [VERIFIED: src/career_evidence_graph/validation/store.py:47-59] |
| `create_only_canonical_bundle` | Immutable source/capture/lineage publication | Every capture/revision/transform bundle; it rejects unsafe bundle names, symlink roots, escapes, and existing destinations. [VERIFIED: src/career_evidence_graph/validation/store.py:62-89] |
| Existing `JDIntakeStore` pattern | Narrow private-root safety and safe status | Generalize its path protection and no-echo approach; do not retain its phase-numbered storage path. [VERIFIED: src/career_evidence_graph/jd.py:72-123] [VERIFIED: src/career_evidence_graph/jd.py:225-251] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Canonical JSON + create-only bundles | SQLite/graph database | Rejected: no concurrent-write or query-scale requirement; adds a second persistence authority. [VERIFIED: .planning/research/ARCHITECTURE.md:330-405] |
| Concrete corpus adapters using stdlib | PDF/DOCX/OCR/model/browser packages | Deferred until an actual declared corpus proves the stdlib gap. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:124-135] |
| Separate private Git repo and ignored raw vault | Public submodule, public path/remote configuration, or shared checkout | Rejected by locked D-07 through D-10. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-57] |

**Installation:** None. Phase 7 must not add dependencies. [VERIFIED: pyproject.toml:10-22]

## Architecture Patterns

### System Architecture Diagram

```text
explicit --workspace private-repository path
                 |
                 v
          WorkspacePaths boundary
                 |
      +----------+-----------+
      |                      |
      v                      v
raw source bytes       source-universe declaration
.career-evidence/raw/       (category + logical source + availability + cutoff)
      |                      |
      v                      v
capture validation ----> create-only capture manifest
(regular/no link,             |
byte hash, metadata)          v
                         transformation manifests
                         (input hash + tool/version/config + locator + output hash)
                                      |
                                      v
                         Phase 8 reads declared revision and lineage

safe routine CLI: status/count/hash/code only
private human view: readable content, only inside selected workspace
```

### Recommended Project Structure

```text
src/career_evidence_graph/
├── workspace.py            # single explicit-root resolver and semantic paths
├── career_sources.py       # declaration/capture/transformation contracts and workflow
├── domain/models.py        # strict source-custody models only
├── validation/hashing.py   # existing sole hash authority
├── validation/store.py     # existing atomic/create-only publication
└── cli.py                  # declare, capture, inspect; explicit --workspace only

<private repository>/
├── .career-evidence/
│   ├── raw/                # ignored by private Git; exact source bodies
│   ├── sources/            # private Git: source/capture/transform manifests
│   └── current/            # explicit working/current pointers only
└── .gitignore              # ignores .career-evidence/raw/
```

The public checkout already ignores `/.career-evidence/`; preserve that public protection while the new private repository keeps only raw bodies in its own ignored raw-vault path. The public `.gitignore` entry is exactly `/.career-evidence/`. [VERIFIED: .gitignore:1-8]

### Pattern 1: Stable logical source plus immutable capture versions

**What:** Define one `source_id` for a logical source and one new `capture_id` for every acquisition. Each capture has the raw content hash, byte count, acquisition time/method, immutable predecessor link when recaptured, and a raw-vault relative locator. Every derived artifact references the capture, never a mutable “current source.” [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:82-107]

**When to use:** Files/pastes, Git objects, web/cloud exports, self-report, existing Grill-Me records, and later examination answers; source-type mechanics vary but the logical/capture identity split does not. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:82-107]

**Implementation rule:** Build a tagged strict model for capture mechanics rather than nullable repository fields. The existing STOA `SourceManifest` hard-codes repository/document cardinality, so it remains a legacy regression fixture rather than the production source model. Its literals are exactly `schema_version: Literal["stoa-source-manifest/v1"]`, `repositories: tuple[StoaRepositoryPin, ...] = Field(min_length=4, max_length=4)`, and `documents: tuple[PermittedDocument, ...] = Field(min_length=10, max_length=10)`. [VERIFIED: src/career_evidence_graph/domain/fixtures.py:79-95]

### Pattern 2: Raw-vault / manifest split

**What:** Raw bytes go only to the private repository’s ignored raw vault. The private repository tracks readable source registry, capture manifest, and transformation manifest; the public repository tracks only generic contracts and synthetic test fixtures. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-57]

**Why:** Git ignores apply only to intentionally untracked files and do not untrack a file already committed; therefore initialize and verify the private raw-vault rule before placing real bytes, and gate public commits with a no-private-path/no-private-content check. [CITED: https://git-scm.com/docs/gitignore/2.20.0.html]

### Pattern 3: Candidate-only transformations

**What:** A transformation record binds `input_capture_id`, input hash, transformer identity/version/configuration, output hash, and precise source locator. It may create candidate text or structured proposals but no accepted fact, Evidence, assessment, or mastery state. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:93-107]

**When to use:** Deterministic extraction/normalization immediately; parser/model adapters later only when the actual corpus requires them.

### Pattern 4: One explicit workspace authority

**What:** Commands require `--workspace`; resolve it before use, reject a symlinked root or a derived path outside it, and generate namespace paths from that root. Do not put a local path, remote URL, submodule, persisted pointer, or fallback current-working-directory selection in the public repository. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-57]

**Example:**

```python
# Reuse the existing helpers; field names are planning skeletons, not locked API values.
workspace = Path(args.workspace).resolve(strict=True)
if workspace.is_symlink():
    raise CareerSourceError("career-workspace-unsafe")
bundle = create_only_canonical_bundle(
    workspace / ".career-evidence" / "sources",
    capture_hash.removeprefix("sha256:"),
    {"manifest.json": manifest.model_dump(mode="json")},
)
```

`Path.resolve` makes a path absolute and resolves symlinks; use it together with the existing `is_relative_to`-style containment checks, not as a substitute for those checks. [CITED: https://docs.python.org/3/library/pathlib.html] The existing bundle helper already validates root/destination containment before writing. [VERIFIED: src/career_evidence_graph/validation/store.py:62-89]

### Anti-Patterns to Avoid

- **Phase-number runtime paths:** do not permanently store generic career sources under a `phase-07` namespace; use stable semantic names. [VERIFIED: .planning/research/ARCHITECTURE.md:330-405]
- **Second storage/hash/parser authority:** do not fork the existing helper implementations or build a generic repository framework. [VERIFIED: src/career_evidence_graph/validation/hashing.py:12-27] [VERIFIED: src/career_evidence_graph/validation/store.py:47-89]
- **Public redacted manifests that retain private-derived identifiers/hashes/counts:** D-07 prohibits them; public artifacts must be wholly synthetic rather than “anonymized” personal outputs. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-45]
- **Parser output as fact authority:** a valid extraction only becomes a source-bound candidate; Phase 8 owns item reconciliation/acceptance. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:93-107]
- **Read-only inspect that creates directories:** the existing JD tests prove inspect must not materialize `.career-evidence` when no state exists; retain that behavior. [VERIFIED: tests/test_jd_security.py:187-207]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Content digest | Another local hash wrapper or a per-adapter hash | `sha256_digest` | One canonical digest prefix and byte identity prevent incompatible manifests. [VERIFIED: src/career_evidence_graph/validation/hashing.py:25-27] |
| Canonical JSON | Ad-hoc `json.dumps` options in every workflow | `canonical_json_bytes` | It fixes UTF-8, key order, separators, and NaN behavior in one source. [VERIFIED: src/career_evidence_graph/validation/hashing.py:12-22] |
| Immutable publication | Custom copy/rename loop per source type | `create_only_canonical_bundle` | It rejects unsafe names/symlinks/escapes and refuses overwrite. [VERIFIED: src/career_evidence_graph/validation/store.py:62-89] |
| Atomic mutable state | Direct writes to current pointer/work snapshot | `atomic_write_canonical_json` | It writes, flushes, fsyncs, then replaces. [VERIFIED: src/career_evidence_graph/validation/store.py:47-59] |
| Error redaction | Formatting user source/path into exceptions | Stable error code plus safe structured envelope | Existing JD flow shows the error code is emitted instead of source text. [VERIFIED: src/career_evidence_graph/jd.py:48-57] [VERIFIED: src/career_evidence_graph/cli.py:762-790] |

**Key insight:** Hashing and filesystem safety are cross-cutting custody semantics. Centralizing them is necessary for traceability; a source adapter should supply bytes/metadata only.

## Common Pitfalls

### Pitfall 1: Public leakage through “safe” artifacts

**What goes wrong:** A hash, source ID, count, private path, error string, test fixture, or test assertion derived from real material is committed to the public harness.

**Why it happens:** D-11 permits safe routine output inside private operation, but D-07 is stricter for public-repository content.

**How to avoid:** Separate `safe_private_status` from public fixtures; tests use sentinel-only synthetic private data and assert public-tree scans have no real workspace strings or `.career-evidence` artifacts. Stage named files only and inspect the public diff before commit. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-57]

**Warning signs:** A public plan/test/log contains a source-derived digest or count, or `git status --ignored` reveals real data beneath the public checkout.

### Pitfall 2: Treating ignored raw storage as a complete privacy control

**What goes wrong:** Raw files are committed before ignore rules exist, copied into manifests/logs, or written outside the selected private repository.

**Why it happens:** `.gitignore` does not change the tracking status of already tracked files. [CITED: https://git-scm.com/docs/gitignore/2.20.0.html]

**How to avoid:** Bootstrap the separate private repository and its raw-vault ignore rule before capture; fail when workspace root/raw directory is symlinked or escaped; never write raw bytes into a JSON bundle.

### Pitfall 3: Source/capture identity collapse

**What goes wrong:** A recapture overwrites the earlier source file or a current pointer is used as historical evidence.

**How to avoid:** Create a new capture with predecessor link and immutable hash; references bind capture ID/hash, while any current pointer remains explicit and non-authoritative. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:89-93]

### Pitfall 4: Transformation laundering

**What goes wrong:** Extracted text loses its source locator/configuration or is accepted as a career fact automatically.

**How to avoid:** Validate full transformation lineage and retain whole-source fallback explicitly when no finer locator exists; output remains a candidate for Phase 8 review. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:93-96]

### Pitfall 5: Misusing source availability as capability evidence

**What goes wrong:** Missing documents lower a self-taught Skill or duplicate résumé/README evidence inflates confidence/mastery.

**How to avoid:** Keep availability, independent corroboration, assessment confidence, market proof, and mastery as separate data; self-report is a first-class source but is never independent corroboration. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:20-38] [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:68-80]

## Code Examples

### Source capture publication

```python
# Source: existing canonical helpers, adapted in the Phase 7 custody seam.
source_hash = sha256_digest(raw_bytes)
create_only_canonical_bundle(
    source_bundles_root,
    source_hash.removeprefix("sha256:"),
    {"manifest.json": capture_manifest.model_dump(mode="json")},
)
```

The helper’s source contract is exactly `return f"sha256:{hashlib.sha256(value).hexdigest()}"`, and it accepts only safe bundle names plus filename-only payloads. [VERIFIED: src/career_evidence_graph/validation/hashing.py:25-27] [VERIFIED: src/career_evidence_graph/validation/store.py:62-89]
The variable and manifest names in this planning skeleton are [ASSUMED]; the planner must choose them once in the new strict source-custody contract rather than treating them as pre-existing API values.

### Content-free failure boundary

```python
try:
    capture_source(...)
except CareerSourceError as exc:
    _emit_error({"valid": False, "error": exc.code})
    return 2
```

The exact existing boundary follows the equivalent `JDIntakeError` code pattern: it stores `self.code` and formats only code/detail; CLI emission uses `{"valid": False, "error": exc.code, "message": str(exc)}`. Phase 7 must make the message content-free too. [VERIFIED: src/career_evidence_graph/jd.py:48-57] [VERIFIED: src/career_evidence_graph/cli.py:762-790]
`capture_source` and `CareerSourceError` are [ASSUMED] planning placeholders; their names are deliberately left to the permitted implementation discretion.

## State of the Art

| Old Approach | Current Approach | Impact |
|---|---|---|
| STOA source fixture with fixed repository/document counts and `src-stoa-*` IDs | Generic logical-source/capture/transform lineage, retaining STOA only as a legacy regression fixture | Real career sources can be captured without weakening fixture provenance. [VERIFIED: src/career_evidence_graph/domain/fixtures.py:53-103] [VERIFIED: .planning/research/ARCHITECTURE.md:330-405] |
| JD-only narrow private intake under phase-number storage | Stable semantic career-source custody shared by later inventory/audit/JD workflows | Avoids per-phase private stores and incompatible lineage. [VERIFIED: src/career_evidence_graph/jd.py:72-123] [VERIFIED: .planning/research/ARCHITECTURE.md:330-405] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | [ASSUMED] The initial declared private corpus can be captured with standard-library deterministic adapters before PDF/DOCX/OCR/model extraction is needed. | Standard Stack / Architecture Patterns | A concrete source may require a later gated adapter task; do not silently omit it. |
| A2 | [ASSUMED] The user will create/select the separate private Git repository during execution rather than expecting the public repository to create or record it. | Environment Availability | The plan needs a human checkpoint because D-08 forbids public path/remote storage. |

## Open Questions

1. **Which source formats are present in the first declared personal corpus?**
   - What we know: dependencies for PDF/DOCX/OCR/browser/model conversion are explicitly prohibited until a measured corpus gap. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:124-135]
   - Recommendation: plan an operator checkpoint after declaration; implement only declared deterministic format adapters and fail closed with a safe code for unsupported types.
2. **What capture metadata can be safely emitted in private routine status?**
   - What we know: safe identifiers/counts/hashes/byte counts are allowed in private routine operation, while public artifacts may contain none derived from real material. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-57]
   - Recommendation: make separate private-status and public-fixture contracts and test their boundary explicitly.
3. **Is an encrypted backup available for the ignored raw vault?**
   - What we know: encryption/backup mechanism is deferred, and absence must be reported rather than masked. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:124-135]
   - Recommendation: include a human-visible private diagnostic such as a backup-state code; do not implement encryption in Phase 7.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---:|---|---|
| Python | domain/CLI/tests | ✓ | `3.14.5` system; project requires `>=3.13,<3.14` | Use project-managed Python 3.13 via `uv`, not the system interpreter. [VERIFIED: pyproject.toml:6-13] |
| uv | locked project commands | ✓ | `0.12.6` | — |
| Git | separate private repository and ignore verification | ✓ | `2.54.0` | — |

**Missing dependencies with no fallback:** None. The only execution prerequisite not machine-detectable is the user’s separate private repository selection/creation; it requires a human checkpoint and must never be written into the public checkout. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-57]

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest `9.1.1` [VERIFIED: pyproject.toml:18-30] |
| Config file | `pyproject.toml` [VERIFIED: pyproject.toml:24-30] |
| Quick run command | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py` |
| Full suite command | `uv run --locked python scripts/run_pytest.py -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| INV-01 | Reject duplicate logical sources, unknown category, invalid cutoff, and missing/invalid unavailable-source disposition; preserve valid source-universe revision byte-for-byte. | unit + golden | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py -k declaration` | ❌ Wave 0 |
| INV-06 | Every capture has source/capture identity, content hash, acquisition metadata, predecessor validity; every transformation binds input/output hashes and locator; tamper/substitution fails closed. | unit + lineage mutation | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py -k 'capture or lineage or transform'` | ❌ Wave 0 |
| INV-07 | Raw body, private label/path, and injection-like text never appear in routine stdout/stderr, exceptions, public test fixtures, or public-tree scans; unsafe links/IDs/control characters fail with stable codes. | adversarial CLI + filesystem | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_security.py` | ❌ Wave 0 |

### Required adversarial fixtures

- Synthetic sentinel raw body, private label, private path, and source-derived hash: assert none appear in status/error output or public fixture/public-tree scan results.
- Unsafe `source_id`, `capture_id`, path traversal, absolute path, nested separator, symlinked workspace/root/raw target, and symlinked manifest tests.
- Invalid UTF-8, NUL/control, zero-width, bidi, oversized source, and instruction-like source text; instruction-like text is retained inertly only if otherwise permitted and never treated as a command. The JD seam already tests no-source echo and inert instruction-like text. [VERIFIED: tests/test_jd_security.py:101-149]
- Mutation of raw bytes, capture hash, predecessor, transform input/output hash, transformer configuration, locator, and manifest path; each must make lineage verification fail.
- A read-only `inspect` on a nonexistent workspace state: exit/status without materializing `.career-evidence`, following the existing JD test pattern. [VERIFIED: tests/test_jd_security.py:187-207]
- A simulated public commit/preflight scan over the repository tree: only synthetic known sentinels are permitted; fail if any private-workspace artifact or private-derived value is staged/tracked.

### Sampling Rate

- **Per task commit:** quick custody/security tests plus Ruff on changed Python files.
- **Per wave merge:** `uv run --locked python scripts/run_pytest.py -q`.
- **Phase gate:** full suite green; private repository bootstrap is human-verified; real-source execution is not claimed complete until the user has declared a source universe and confirmed the raw-vault boundary.

### Wave 0 Gaps

- [ ] `tests/test_career_source_custody.py` — declaration, capture, recapture, duplicate, and transformation-lineage tests for INV-01/INV-06.
- [ ] `tests/test_career_source_security.py` — public/private boundary, path/symlink, no-echo, raw-vault, and operator failure-mode tests for INV-07.
- [ ] Synthetic fixture builders only — no real resume, graph, hash, count, path, report, or raw source may enter the public repository.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | No | Single-user local workflow has no authentication surface in this phase. |
| V3 Session Management | No | No browser/session state. |
| V4 Access Control | Yes, local boundary | Explicit workspace selection, private-root containment, no public pointer/submodule, and distinct private/public output contracts. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:39-57] |
| V5 Input Validation / File Handling | Yes | Strict Pydantic models, safe IDs, byte limits, UTF-8/control validation, regular-file and symlink checks, resolved containment, create-only bundles. OWASP ASVS V5.3.2 requires internally generated/trusted file paths or strict validation/sanitization of supplied file metadata. [CITED: https://cornucopia.owasp.org/taxonomy/asvs-5.0/05-file-handling/03-file-storage] |
| V6 Cryptography | Yes, integrity only | Reuse SHA-256 content identity; it is a tamper-detection/provenance key, not encryption or password protection. Python documents `sha256` as a guaranteed hash constructor. [CITED: https://docs.python.org/3/library/hashlib.html] |
| V7 Error Handling and Logging / Data Protection | Yes | Stable redacted codes and safe envelopes; raw source never enters routine error/log/public artifacts. |

### Known Threat Patterns for the local custody stack

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Path traversal or symlink escape | Tampering / Elevation | Reject unsafe IDs, symlink roots/files, and paths not contained in the resolved explicit workspace; reuse bundle containment checks. [VERIFIED: src/career_evidence_graph/validation/store.py:62-89] |
| Raw/private data in stdout, stderr, logs, fixtures, or Git | Information disclosure | Content-free routine envelopes; public-tree/staged-diff tests; synthetic fixtures only. |
| Capture or transform substitution | Tampering | Raw/capture/output hashes, predecessor links, input/output hash validation, create-only bundles, no overwrite. |
| Prompt-like source text causing workflow action | Elevation / Tampering | Treat source as inert bytes/text; never invoke a provider or command from capture content. Existing hostile-input test demonstrates inert handling. [VERIFIED: tests/test_jd_security.py:142-149] |
| Duplicate evidence treated as corroboration/mastery | Tampering | Preserve all source links but dedupe same content/fact and retain zero mastery/assessment side effect. [VERIFIED: .planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md:100-107] |

## Sources

### Primary (HIGH confidence)

- [Phase 7 CONTEXT.md](/Users/zhdeng/Documents/TomorrowStar%20OS/.planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md) — locked custody, privacy, source identity, and scope decisions.
- [Existing hashing helper](/Users/zhdeng/Documents/TomorrowStar%20OS/src/career_evidence_graph/validation/hashing.py) and [immutable bundle store](/Users/zhdeng/Documents/TomorrowStar%20OS/src/career_evidence_graph/validation/store.py) — reusable canonical identity and publication primitives.
- [JD custody seam](/Users/zhdeng/Documents/TomorrowStar%20OS/src/career_evidence_graph/jd.py) and [hostile-input tests](/Users/zhdeng/Documents/TomorrowStar%20OS/tests/test_jd_security.py) — safe root, no-echo, explicit workspace, and read-only inspection patterns.
- [Milestone architecture research](/Users/zhdeng/Documents/TomorrowStar%20OS/.planning/research/ARCHITECTURE.md) — one semantic private workspace and no-phase-runtime-path direction.

### Secondary (MEDIUM confidence)

- [Python pathlib documentation](https://docs.python.org/3/library/pathlib.html) — `Path.resolve` behavior.
- [Python hashlib documentation](https://docs.python.org/3/library/hashlib.html) — SHA-256 API capability.
- [Git gitignore documentation](https://git-scm.com/docs/gitignore/2.20.0.html) — ignored-versus-tracked boundary.
- [OWASP ASVS project](https://owasp.org/www-project-application-security-verification-standard/) and [ASVS V5 file storage](https://cornucopia.owasp.org/taxonomy/asvs-5.0/05-file-handling/03-file-storage) — validation/control framing for local file handling.

### Tertiary (LOW confidence)

- None. Corpus-specific adapter needs are intentionally logged as assumptions rather than recommendations.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — every recommended primitive is installed and opened in this repository.
- Architecture: HIGH — constrained by locked Phase 7 decisions and current custody seams.
- Pitfalls: HIGH — directly covered by locked privacy/custody decisions and hostile-input tests.

**Research date:** 2026-08-29
**Valid until:** 2026-09-28 for repository findings; revisit immediately if the private-repository arrangement or initial source corpus changes.
