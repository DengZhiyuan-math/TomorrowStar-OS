# Phase 7: Career Source Custody and Private Workspace - Context

**Gathered:** 2026-08-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 establishes the custody boundary for one full-career source-universe revision. It lets
the user declare the career-history cutoff, the categories and logical sources considered, and
every unavailable source; captures immutable source versions and transformation lineage; and
keeps all personal material outside the public TomorrowStar OS repository.

The public repository remains a generic agent-harness project containing code, contracts,
documentation, and wholly synthetic fixtures. A separately created private Git repository holds
the user's readable Skill graph, resume material, source registry, hashes, and transformation
records. Exact sensitive source bodies remain in an ignored raw vault within that private
workspace.

This phase does **not** reconcile or seal the full-career inventory (Phase 8), run the generic
Contribution audit (Phase 9), implement the Skill-first comprehensive examination described
during discussion, admit mastery (Phase 10), compare real JDs, or generate resumes. Source
coverage and provenance support those capabilities but are not mastery gates.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Current milestone scope and phase boundary

- `.planning/PROJECT.md` — Defines the Skill-graph-to-JD-to-resume product direction, stable
  Skill semantics, truthfulness constraints, and the v1.1 validation boundary.
- `.planning/REQUIREMENTS.md` — Defines Phase 7 requirements INV-01, INV-06, and INV-07 and the
  downstream inventory, graph, JD, evaluation, resume, and evidence-producing gap boundaries.
- `.planning/ROADMAP.md` — Defines Phase 7 success criteria and assigns inventory reconciliation
  and sealing to Phase 8, generic auditing to Phase 9, and mastery admission to Phase 10.
- `.planning/STATE.md` — Records Phase 7 as the current v1.1 focus and preserves prior milestone
  constraints.

### Prior accepted assessment decisions

- `.planning/milestones/v1.0-phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md`
  — Locks hard-to-simple, one-question capability probing, direct responsibility/assistance
  separation, resumability, and non-authoritative self-rating.
- `.planning/milestones/v1.0-phases/04-contribution-skill-assessment-and-aggregation-calibration/04-CONTEXT.md`
  — Locks specific-Skill mastery, separate mastery/centrality/confidence, human review,
  `self-assessed-unverified` lineage, anchor-based admission, and no-inflation aggregation.
- `.planning/milestones/v1.0-phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md`
  — Locks private JD handling, JD isolation from mastery, content-free status/error boundaries,
  and resume selection as a downstream result rather than a Skill source.

### Milestone research and custody design

- `.planning/research/ARCHITECTURE.md` — Defines the one-private-workspace architecture,
  immutable captures, source lineage, semantic namespaces, and rejection of parallel stores.
- `.planning/research/STACK.md` — Defines the Python/Pydantic/JSON baseline and the rule to add
  source-format adapters only for concrete corpus needs.
- `.planning/research/PITFALLS.md` — Defines completeness, privacy, source-substitution, and
  evidence-inflation failure modes that Phase 7 must prevent.

### Existing reusable implementation

- `src/career_evidence_graph/jd.py` — Provides the current source-ID/content-hash split,
  create-only private intake, safe status output, and non-echoing diagnostic pattern to
  generalize beyond the phase-numbered JD namespace.
- `src/career_evidence_graph/domain/fixtures.py` — Provides source manifests, proof limits,
  source-section lineage, candidate-only documentary status, conflict preservation, and
  duplicate Evidence identity guards.
- `src/career_evidence_graph/validation/store.py` — Provides canonical atomic writes,
  create-only bundles, workspace containment, immutable run history, and manifest verification.
- `src/career_evidence_graph/validation/hashing.py` — Provides the canonical JSON and SHA-256
  identity helpers that must remain the single hashing authority.
- `tests/test_jd_security.py` — Provides hostile-input, no-source-echo, read-only inspection,
  exact-byte, unsafe-ID, and content-free status tests to adapt for generic career sources.
- `.gitignore` — Already ignores `/.career-evidence/`; planning must preserve this public-repo
  protection while establishing the separate private repository boundary.

### User-referenced workflow inspirations

- External installed Skill `asu` — Inspiration for truthful positioning, claim/evidence
  separation, and evidence organization only; wording cannot create capability evidence. Its
  machine-local path is intentionally omitted from this public-repository artifact.
- External installed Skill `interview` — Weak inspiration for layered questioning, question
  trees, and review only. Its resume-claim-driven entry point and limited coverage are explicitly
  not the comprehensive examination architecture. Its machine-local path is intentionally
  omitted from this public-repository artifact.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `JDIntakeStore` already keeps logical source IDs separate from source hashes, publishes
  create-only bundles, rejects unsafe roots, and exposes content-free counts. Generalize its
  custody pattern into semantic career-source namespaces instead of adding a parallel store.
- `atomic_write_canonical_json`, `create_only_canonical_bundle`, and `sha256_digest` already
  provide the atomicity and canonical content identity Phase 7 needs.
- `SourceManifest`, `PermittedDocument`, `CandidateEvidence`, and
  `SourceSectionDisposition` already demonstrate bounded proof roles, source-section locators,
  candidate-only authority, and duplicate identity rejection.
- The public checkout already ignores `/.career-evidence/`, and the current CLI already accepts
  explicit workspace paths that can point to the separate private repository.

### Established Patterns

- Pydantic contracts are frozen, schema-versioned, and fail closed on extra, stale, corrupt, or
  lineage-invalid state.
- Immutable versions, explicit current selection, canonical hashes, and create-only publication
  replace in-place mutation.
- Documentary presence, repository presence, titles, credentials, and repeated Evidence cannot
  establish mastery.
- Private source text remains inert data; routine commands and errors expose safe structured
  status rather than echoing source content.

### Integration Points

- Add one generic career-source custody seam beside the current narrow JD intake, extracting
  shared storage and source-capture behavior where reuse is cheaper than duplication. Do not
  build a second hashing, workspace, parser, or evidence authority.
- Extend the stdlib CLI with explicit private-workspace source declare/capture/inspect commands;
  public-repository defaults and tests must remain synthetic.
- Phase 8 consumes the declared source-universe revision and immutable capture manifests for
  candidate inventory reconciliation. Phase 7 must not create inventory acceptance or sealing
  commands.
- Later audit and assessment phases may consume self-report and direct-examination artifacts,
  but Phase 7 only preserves their source identity, capture, and transformation lineage.

</code_context>

<specifics>
## Specific Ideas

- A self-taught technical Skill must not be discounted for lacking an official transcript or
  formal course. Observable capability decides mastery.
- A future comprehensive self-examination should resemble a high-intensity interview and
  real-work hiring assessment. It starts from atomic Skills, uses provenance-bearing real
  interview questions, interview-experience reports, and representative tasks, and may pose
  multi-Skill questions such as implementing a data structure in Python.
- For a multi-Skill question, one Skill is primary and all co-assessed Skills receive separate
  observations, anchor fits, evidence, unmet boundaries, and assessment proposals. A cross-Skill
  performance report is derived but never replaces individual mastery.
- Truthful packaging has two effects: stronger wording organizes existing verified truth and
  improves market proof; new real work such as a case study, demo, benchmark, article, or open
  source contribution creates inspectable artifacts that may become new Evidence after audit.

</specifics>

<deferred>
## Deferred Ideas

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

</deferred>

---

*Phase: 7-career-source-custody-and-private-workspace*
*Context gathered: 2026-08-29*
