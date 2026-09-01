# Phase 07 MVP Simplification Addendum

**Version:** 2026-08-31
**Status:** Active implementation boundary for Phase 07
**Applies to:** Future Phase 07 execution beginning with `07-12-PLAN.md`

## Why this addendum exists

Phase 07 is a personal, single-user, local MVP. The previously executed plans established
important public/private and synthetic-fixture boundaries, but their later custody machinery
grew beyond the product need. This addendum changes future implementation work without
rewriting the evidence of completed plans or asserting that their mechanisms were never built.

## Decisions retained

- **D-07:** The public repository remains synthetic-only. It must retain no private workspace
  URL, path, personal data, private-derived fingerprint, count, or report.
- **D-08:** Readable personal records live only in a user-selected, existing private Git
  worktree. Its resolved worktree root must be neither the public TomorrowStar OS checkout nor
  an ancestor or child of that checkout; the public repository does not persist a pointer, URL,
  or submodule to it. Git establishes that local identity and boundary only, never a snapshot,
  commit, ref, remote, log, or history authority.
- **D-09:** Exact raw bodies remain beneath the private ignored raw-vault boundary and stay out
  of both Git histories. Backup and encryption remain the user's responsibility and are deferred.
- **D-10:** Every personal-data operation receives an explicit workspace argument to the one
  workspace-module entry point. It passes the existing-private-worktree and public/ancestor/child
  rejection checks. There is no implicit current workspace, persisted path, command-line route,
  or alternate workspace authority. Routine results and errors do not reveal either repository
  path or Git details.
- **D-11:** Routine module results and errors remain content-free; readable private data, if
  needed later, remains inside the explicit private workspace rather than a Phase 7 presentation
  interface.
- **D-12 through D-16:** The source boundary still records category/source coverage, cutoff,
  self-reported-source status, and unavailable sources. Each source has a required availability
  value drawn exactly from `available`, `temporarily-unavailable`, `permanently-lost`,
  `access-restricted`, `never-created`, `location-unknown`, or `user-declined`. An
  `unavailability_reason` is optional for a non-`available` source and absent for `available`;
  it never removes an unavailable source from the registry. This boundary does not establish
  facts, responsibility, Skill, assessment, or mastery authority.

## Decisions superseded for the MVP

- **D-17:** Replace source-type-specific immutable-original machinery with append-only private
  raw retention plus a content hash. No new parser, OCR, browser, provider, or document-format
  support is introduced.
- **D-18:** Replace the general capture-version graph, predecessor links, current pointers, and
  migration engine with one simple registry. It has one global cutoff, declared supported
  categories, and source entries carrying source ID, category, self-reported-or-other source
  type, availability, and optional reason. A capture adds capture-source ID, content hash, and
  capture time; no migration protocol or temporal lineage authority exists.
- **D-19:** Retain an input/output mapping only when the operator actually supplies derived
  text. The mapping includes input hash, output hash, transformer identity/version, and an
  optional locator; it is candidate provenance, never fact, assessment, or mastery authority.
  The MVP does not generate derived text automatically.
- **D-20:** Do not build a generic deduplication system. A raw object may be reused by its
  content hash, while logical source IDs remain explicit. Source repetition cannot affect any
  Skill or assessment because Phase 7 creates neither.

## Active minimal contract

The private workspace module owns one small source registry with one global cutoff, declared
supported categories, and source entries containing source ID, category, self-reported-or-other
source type, availability, and optional reason. A capture adds capture-source ID, content hash,
and captured-at time. When derived text actually exists, the registry additionally records
input/output hash, transformer identity/version, and an optional locator. Before raw writing, the
selected private workspace must designate `.career-evidence/raw/` as ignored in its own
`.gitignore`; this is a local raw-containment safeguard, not Git commit, snapshot, ref, or
repository authority. Raw writes are create-only and append-only; failed work may leave an orphan.
There is no automatic deletion, garbage collector, cleanup race protocol, commit OID, dedicated
ref, snapshot comparison, migration receipt, or retention authority.

The implementation has one function-based workspace module and no separate source store, source
Pydantic/domain-model layer, or `career-source` command interface. Registry/raw read-write logic
lives in that module. Tests call its direct module API. A thin `python -m` adapter is not retained
unless a concrete existing non-test consumer requires it; Phase 7 currently does not create such a
consumer.

The implementation retains only ordinary local safeguards: an explicit existing private
Git-worktree root that resolves outside the public checkout's ancestor/child authority, safe
identifiers, rejection of obvious path escape and symbolic links, and redacted routine
output/errors that contain neither private/public paths nor Git details. It does not claim
adversarial multi-process, TOCTOU, or Git-history-authority guarantees.

## Scope fence

This addendum does not create a separate store, a source model hierarchy, a user-facing CLI,
Skill, assessment, mastery, inventory acceptance, document parsing, LLM, OCR, database, UI,
deployment, backup, or encryption functionality. Those remain outside Phase 7 or deferred as
stated in the roadmap and historical context.
