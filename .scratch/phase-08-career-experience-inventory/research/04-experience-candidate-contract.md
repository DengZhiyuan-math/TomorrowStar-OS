# Experience Candidate and Inventory Revision Contract

## Question

What is the smallest domain contract that can represent Experience Candidates, multiple Source
links, merge and split proposals, uncertainty, every required Disposition, immutable Inventory
Revisions, and downstream admission blocks without creating placeholder Contributions or a second
source authority?

## Inputs

This decision applies the accepted Phase 8 boundary in
[08-CONTEXT.md](../../../.planning/phases/08-full-career-inventory-review-and-seal/08-CONTEXT.md)
and the three resolved frontier notes:

- [resume and website seed interfaces](01-career-seed-interfaces.md);
- [Phase 7 source-registry consumption](02-source-registry-shape.md);
- [repository identity and Experience clustering signals](03-repository-clustering-signals.md).

It also preserves the existing final
[`Experience` contract](../../../src/career_evidence_graph/domain/models.py), reuses only the
review-before-materialization pattern from
[`CandidateLedger`](../../../src/career_evidence_graph/domain/fixtures.py), and keeps canonical
hashing, immutable publication, and Source authority in their existing modules.

## Decision

Use one immutable, source-bound proposal graph with six private contract shapes:

1. `SourceLink` binds a candidate fact or grouping clue to one declared Source and an exact private
   locator.
2. `ExperienceCandidate` records only the identity of a proposed real-world undertaking.
3. `SourceDisposition` assigns one explicit outcome to every Source in the bound universe.
4. `CandidateDisposition` assigns one explicit outcome to every candidate and represents edit,
   merge, and split replacement edges.
5. `InventoryRevision` is the canonical immutable proposal-and-decision snapshot.
6. `AcceptedInventoryRevision` seals the exact revision only after deterministic coverage,
   current Phase 7 verification, and explicit user acceptance pass.

`InventoryCoverage` is a deterministic report derived from the first five records and the bound
Source Universe Revision. It is not another ledger or authority.

Do not instantiate the existing final `Experience` model in Phase 8. That model requires at least
one Contribution, and placeholder Contributions would falsely cross the Phase 9 audit boundary.
An accepted Phase 8 candidate establishes inventory identity only; Phase 9 later materializes the
contribution-linked `Experience` using that accepted identity.

## Canonical graph

```text
Source Universe Revision
        |
        | exact snapshot identity
        v
Inventory Revision ---- parent hash ----> prior Inventory Revision
  |        |       |
  |        |       +---- Candidate Dispositions ---- replacement edges
  |        +------------ Source Dispositions
  +--------------------- Experience Candidates ---- Source Links ----> Sources
        |
        +---- deterministic Inventory Coverage
        |
        +---- explicit user checkpoint + current Phase 7 PASS
                      |
                      v
              Accepted Inventory Revision
                      |
                      +---- confirmed leaves only ----> Phase 9 audit input
```

The graph is a complete snapshot, not an event log. A later correction creates a new complete
revision with the prior revision hash and an explicit change reason. Earlier revisions are never
rewritten or silently retargeted.

## Minimal record shapes

Field names below are contract-level recommendations. Exact Pydantic names may change during
planning, but their meanings and invariants should not.

### `SourceLink`

| Field | Meaning |
|---|---|
| `source_id` | ID from the exact bound Source Universe Revision; never an inline replacement Source |
| `locator` | Exact private source-local location supporting the identity or relationship clue |
| `content_identity` | Exact content identity when the located material is independently bound; absent only for a discovery-only or unavailable clue |
| `role` | `identity`, `grouping`, `conflict`, or `discovery-only` |

The Inventory Revision already binds the exact source snapshot, so a link does not repeat mutable
registry metadata. A Source may appear in several links or candidates. Equal bytes, repeated
wording, or repeated links do not increase confidence or establish responsibility.

A confirmed candidate must have at least one non-discovery Source link with an exact content
identity. An unresolved candidate may remain visible with discovery-only links. All readable
values and locators stay in the explicitly selected private workspace.

### `ExperienceCandidate`

| Field | Meaning |
|---|---|
| `candidate_id` | Safe opaque identity for one immutable proposal node |
| `category` | One Phase 8 inventory category: employment, project, research, publication, education, teaching, open source, internship, or related |
| `title` | Source-grounded identity label, not a resume headline |
| `organization_or_context` | Optional identity context when explicitly sourced or self-reported |
| `period_text` | Optional source-facing period; normalized dates may be added only when unambiguous |
| `description` | Short identity description without responsibility or capability conclusions |
| `source_links` | One or more unique `SourceLink` records |
| `uncertainty_notes` | Zero or more explicit private notes about identity, grouping, category, date, or source conflict |

The candidate has no Contribution, responsibility, assistance, Skill, mastery, confidence, JD,
resume-quality, or employment-effectiveness field. Tags, credentials, repository ownership, and
repeated descriptions remain discovery clues.

A user-added candidate is still source-grounded. It must link to a declared, exact self-report
Source in the bound Source Universe Revision. If that Source does not exist, the working review
may retain the item as unresolved, but confirming it requires the Phase 7 source authority to
produce a successor Source Universe Revision. Phase 8 must not invent an inline Source namespace.

### `SourceDisposition`

Each Source ID in the bound Source Universe Revision appears exactly once with one outcome:

| Outcome | Required relation |
|---|---|
| `used-in-candidate` | One or more existing candidate IDs |
| `background-only` | Non-empty reason; no candidate acceptance implied |
| `conflict` | Non-empty reason and any affected candidate IDs |
| `excluded-with-reason` | Non-empty reason |
| `unavailable` | Registry row is unavailable; the registry remains the reason authority |
| `unresolved` | Non-empty reason and any affected candidate IDs |

The disposition does not copy availability, capture metadata, or source payload. Those remain in
the one Phase 7 workspace registry and its exact snapshot.

### `CandidateDisposition`

Each candidate in the Inventory Revision appears exactly once with one outcome:

| Outcome | Successor rule | Meaning |
|---|---|---|
| `confirmed` | none | User accepts this candidate's inventory identity |
| `edited` | exactly one | This proposal is replaced by one corrected candidate |
| `merged` | exactly one | Two or more proposals are replaced by the same combined candidate |
| `split` | two or more | One proposal is replaced by several candidates |
| `excluded-with-reason` | none | Deliberately omitted from the accepted Experience set |
| `unresolved` | none | Deliberately retained but blocked from downstream admission |

Every non-confirm outcome carries a reason. Every successor is an `ExperienceCandidate` in the
same complete revision and receives its own disposition. Replacement edges are acyclic and cannot
target the originating candidate.

The replacement graph enforces operation shape without a separate merge/split authority:

- one `edited` input points to one successor;
- at least two `merged` inputs point to the same one successor;
- one `split` input points to at least two successors;
- no candidate can be consumed by more than one replacement operation;
- every replacement chain terminates in `confirmed`, `excluded-with-reason`, or `unresolved`.

A candidate added by the user is simply a new source-grounded proposal node with its own final
disposition. It does not need an `add` event or a second mutable action log.

### `InventoryRevision`

The canonical revision contains only:

- schema version and safe revision label;
- exact Source Universe Revision or registry-snapshot hash and career-fact cutoff;
- optional parent Inventory Revision hash plus a required change reason for a child;
- the complete tuple of Experience Candidates;
- exactly one SourceDisposition per Source;
- exactly one CandidateDisposition per candidate;
- creation time and private reviewer-session identity where operationally needed.

Its canonical JSON bytes receive the revision hash through the existing hashing authority. The
private workspace publishes the revision create-only through the existing atomic-write pattern.
There is no database, second Source registry, event journal, current-pointer authority, or generic
mutable candidate store.

The revision validator rejects duplicate IDs, dangling Source/candidate links, incomplete
dispositions, cyclic or malformed replacement edges, a cutoff inconsistent with the bound Source
Universe Revision, and a parent reference without an explicit change reason.

Pending review is deliberately outside this contract. A hash-bound, non-authoritative review
draft may contain empty decision slots while the user works, but `pending` is not a Disposition
and cannot appear in an `InventoryRevision`. Only a complete draft materializes the immutable
revision. The exact review and coverage interaction is defined in
[Human Review and Coverage Checkpoint Design](05-review-coverage-checkpoint.md).

### `InventoryCoverage` — derived view

Coverage is recomputed from the exact Inventory Revision plus its bound Source snapshot. It shows,
inside the private workspace:

- every supported inventory category and whether it has confirmed, unresolved, or no candidates;
- every declared Source and its one disposition;
- every candidate and its one disposition;
- conflicts, exclusions, unresolved candidates, and unavailable Sources;
- dangling or malformed replacement relations;
- stable reason codes for every seal blocker.

The report binds the Inventory Revision hash and receives its own content hash so the user can
accept the exact view inspected. Counts, labels, locators, hashes, and private findings never
enter public logs or committed public artifacts. A cached report is never trusted without
recomputation from the named revision.

### `AcceptedInventoryRevision`

The seal is a small immutable envelope containing:

- exact Inventory Revision hash;
- exact derived coverage-report hash;
- exact Source Universe Revision or registry-snapshot hash and cutoff;
- exact current Phase 7 independent-verification artifact hash;
- explicit user acceptance identity and time;
- optional parent accepted-revision hash for a later correction.

Seal creation fails unless every Source and candidate has a disposition, all replacement chains
close, coverage has no silent omissions, Phase 7 independently passes against the current
implementation, and the user accepts the displayed revision and coverage identities. Unresolved
candidates may remain in a sealed revision because they are explicitly dispositioned; they do not
become accepted Experiences.

## Downstream admission rule

Do not store an `eligible` boolean. It would become a second, drift-prone authority. Admission is
derived from immutable state:

| State | Permitted consumer |
|---|---|
| Candidate in an unsealed revision | Phase 8 review only |
| `edited`, `merged`, or `split` candidate | Lineage display only |
| `excluded-with-reason` candidate | Coverage and history only |
| `unresolved` candidate, even in a seal | Coverage and later inventory correction only |
| `confirmed` candidate in the exact accepted revision | Phase 9 Contribution audit input only |
| Phase 9 materialized `Experience` with audited Contributions | May proceed to the later assessment gates, subject to their own review rules |

Thus an accepted inventory does not establish personal responsibility, capability, mastery, JD
match, resume truth, or job-search effectiveness. Phase 10 and later consumers must require the
contribution-linked final `Experience`; they cannot accept a Phase 8 candidate or seal directly.

## Boundary scenarios

1. **Repeated resume and website entry.** One candidate may retain both Source links. Repetition
   proposes grouping but does not add confidence or create a second Experience.
2. **Ambiguous same-name projects.** Keep two candidates or retain them unresolved. Similarity
   alone creates no merge edge.
3. **Multi-repository product.** Several candidates may receive `merged` dispositions pointing to
   one successor only after user review; every original Source link remains attached to the graph.
4. **One source entry describes two undertakings.** The candidate receives `split`; both successors
   retain distinct locators into the same Source and each receives its own disposition.
5. **Forgotten internship added during review.** Bind the self-report to the existing Source
   authority. Without a declared exact self-report Source, retain it unresolved until a successor
   Source Universe Revision exists.
6. **Unavailable source.** Record `unavailable`; do not infer that its possible Experience is false
   or silently omit it from coverage.
7. **Explicitly unresolved identity.** It may remain in an accepted Inventory Revision, stays
   visible in coverage, and cannot enter Phase 9.
8. **Later correction.** Publish a child Inventory Revision and, after a new checkpoint, a child
   accepted seal. The prior revision and seal remain unchanged.
9. **Source capture drift or missing bytes.** The Phase 8 read seam fails closed before candidate
   confirmation; a registry path or cached report cannot substitute for the exact snapshot.

## Reuse and rejection decisions

Reuse the existing strict-model style, canonical JSON/hash functions, atomic create-only write
pattern, safe identifiers, and exact-hash correction lineage. Reuse `CandidateLedger` only as a
review-before-materialization pattern.

Do not reuse its STOA-specific IDs, fixed source counts, claim-level review dimensions,
Contribution candidates, source manifest, or unresolved-is-unsealable rule. Phase 8 has different
semantics: unresolved identity prevents downstream audit but may remain in a complete accepted
inventory when its disposition is explicit.

Do not add a graph database, workflow framework, provisional Contribution, skill field, generic
event log, second workspace, or second Source parser. The existing Phase 7 workspace remains the
sole Source authority, and the Inventory Revision remains the sole candidate/review authority.

## Result

Adopt the six-shape contract and derived coverage view above. It represents all required review
operations as one closed immutable proposal graph, preserves exact Source lineage, permits
explicit uncertainty without silent omission, and makes downstream admission a deterministic
consequence of the accepted revision rather than a mutable flag.
