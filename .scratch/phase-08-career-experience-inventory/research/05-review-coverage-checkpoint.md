# Human Review and Coverage Checkpoint Design

## Question

What is the smallest realistic review packet and coverage report that lets the user confirm,
edit, add, split, merge, exclude with a reason, or retain unresolved candidates while proving that
every Source and candidate received a visible Disposition before acceptance?

## Inputs

This design applies the immutable proposal graph from
[the Experience Candidate contract](04-experience-candidate-contract.md), the review and sealing
boundary in
[08-CONTEXT.md](../../../.planning/phases/08-full-career-inventory-review-and-seal/08-CONTEXT.md),
and the existing hash-bound candidate/review pattern in
[`domain/fixtures.py`](../../../src/career_evidence_graph/domain/fixtures.py).

The STOA fixture pattern is useful only for separating an immutable proposal from a human response,
binding the response to the proposal hash, rejecting incomplete review, and materializing only
reviewed results. Its claim-level review groups, one-shot checked-in packet, fixed reviewer, and
rule that unresolved facts cannot seal do not carry into the inventory domain.

## Prototype method

A disposable standard-library terminal prototype exercised synthetic-only state. It showed the
full candidate queue, Source queue, category coverage, blockers, revision identity, and coverage
identity after every action. It wrote nothing and was deleted after this decision was captured.

The exercised paths were:

- attempting acceptance with pending candidate and Source slots;
- confirming one candidate without implicitly deciding its Sources;
- merging two candidates and observing the generated successor return as pending;
- splitting one candidate and observing both successors return as pending;
- adding a candidate through an exact declared self-report Source;
- retaining a merged successor as explicitly unresolved;
- assigning every Source a separate disposition, including an unavailable Source;
- reaching checkpoint-ready state with an unresolved candidate still visible;
- accepting the exact revision and coverage identities;
- attempting mutation after acceptance and receiving an immutable-revision block.

## Prototype findings

| Observation | Design consequence |
|---|---|
| A candidate table alone cannot prove Source reconciliation | Show separate candidate and Source queues in one checkpoint |
| Discovery produces pending work, not an outcome | Keep pending review slots outside `InventoryRevision`; `pending` is not a Disposition |
| Merge and split decisions create new undecided identities | Every successor re-enters the candidate queue and must receive its own outcome |
| Candidate confirmation does not explain unused or conflicting Sources | Never auto-disposition a Source from a candidate action |
| Explicit unresolved items do not create silent omissions | They remain visible, allow checkpoint readiness, and stay downstream-blocked |
| Empty categories disappear in item-only views | Always render all nine category rows and an add action, including `none discovered` rows |
| A generic “done” button hides what was accepted | Bind one explicit decision to exact Inventory Revision and coverage hashes |
| Editing after acceptance changes the accepted object | Freeze the accepted revision; corrections start a linked child review |

The model was sufficient without a browser UI, database, event log, or second candidate store.

## Decision

Use one private review checkpoint with five state layers:

```text
immutable candidate proposal
          |
          | proposal hash
          v
resumable review draft  <---- candidate and Source actions
          |
          | all slots final; replacement graph closed
          v
immutable Inventory Revision
          |
          +---- deterministic coverage report
          |
          +---- exact user checkpoint response
                            |
                            +---- current Phase 7 verification ----> seal
```

Only the Inventory Revision and later accepted seal are domain authorities. The candidate proposal
preserves generation input. The review draft is a resumable form. Coverage is a deterministic
view. The checkpoint response is user authority bound to exact hashes; it is not a second copy of
the career inventory.

## Review-time artifacts

The smallest private artifact set before acceptance is:

1. **Candidate proposal.** Create-only JSON containing the exact Source snapshot identity, cutoff,
   generated Experience Candidates, Source links, uncertainty, and reviewable grouping proposals.
   It contains no favorable decisions.
2. **Review draft.** One atomic JSON snapshot bound to the proposal hash. It contains the complete
   candidate graph, one decision slot per candidate, one decision slot per Source, reviewer
   identity when known, and the latest explicit actions. It may contain empty slots and is never
   seal authority.
3. **Coverage view.** Recomputed from the exact proposal/draft while review is active and from the
   exact Inventory Revision after materialization. A private renderer may show it as terminal text
   or Markdown, but the rendered copy is not a second ledger.

Once every slot is final, materialize a create-only `InventoryRevision`. Then recompute and retain
the exact coverage report the user inspects. The explicit checkpoint response is created only at
the final action.

Do not add a persistent HTML application, database, per-action event journal, mutable “accepted”
pointer, or public report. The existing private workspace, canonical JSON/hash functions, and
atomic write pattern are sufficient.

## Review packet layout

The renderer presents one stable frame with five sections. Large inventories may paginate within
a section, but every row remains reachable and the coverage section always reflects the whole
draft rather than the current page.

### 1. Exact identity header

Show privately:

- candidate proposal hash;
- Source Universe Revision or registry-snapshot hash;
- career-fact cutoff;
- current review-draft hash and reviewer identity;
- whether the view is `review-incomplete`, `revision-ready`, `accepted`, or `stale`.

No friendly alias such as “latest” may substitute for these identities. Public routine output may
say only that review is incomplete or ready; it must not emit private names, paths, counts, hashes,
or findings.

### 2. Category wayfinder

Render all nine categories in the canonical order:

`employment`, `project`, `research`, `publication`, `education`, `teaching`, `open_source`,
`internship`, and `related`.

For each category, show confirmed, unresolved, excluded, replaced, and pending items, plus an
explicit `none discovered` row when empty. The row links into the candidate queue and exposes the
add action. Category assignment is navigation and coverage only; it has no capability meaning.

The final exact acceptance covers the displayed empty-category rows. A separate “no experience in
this category” domain record is unnecessary.

### 3. Candidate review queue

Each candidate card contains only:

- candidate ID and current review state;
- category, title, organization/context, period, and short identity description;
- every Source link with private locator, role, and bound/discovery-only state;
- uncertainty, conflict, merge/split signals, and proposed alternatives;
- predecessor and successor IDs where review created a replacement;
- one explicit action surface.

Available actions are:

| Action | Required input | Draft effect |
|---|---|---|
| confirm | exact candidate | records `confirmed` |
| edit | corrected identity fields and reason | records `edited`; creates one pending successor |
| add | identity fields and exact self-report Source link | creates one pending candidate |
| merge | two or more candidates, combined identity, reason | records `merged` on inputs; creates one pending successor |
| split | one candidate, two or more identities, reason | records `split`; creates pending successors |
| exclude | non-empty reason | records `excluded-with-reason` |
| retain unresolved | non-empty reason | records `unresolved` and preserves the item visibly |

There is no “confirm all.” Batching may change display order or submit several individually named
decisions, but the response must still contain one explicit outcome per candidate. Edit, merge,
and split never inherit a favorable outcome onto a successor.

Suggested review order is the resume/website backbone first, explicit repository-cluster proposals
next, ambiguous candidates next, and user-added or category-gap items last. The user can always
filter to pending, conflict, or unresolved without hiding other items from total coverage.

### 4. Source reconciliation queue

Each Source row shows privately:

- Source ID, source category/type, availability, and capture-integrity state from the bound Phase 7
  snapshot;
- every candidate link and the exact role of that link;
- grouping signals, conflicts, and discovery-only limitations;
- one explicit SourceDisposition action.

Allowed outcomes remain `used-in-candidate`, `background-only`, `conflict`,
`excluded-with-reason`, `unavailable`, and `unresolved`. The registry is the authority for
availability and its reason. A review response cannot mark an available Source unavailable or
silently turn an unavailable Source into accepted evidence.

`used-in-candidate` must name one or more current leaf candidates that retain that Source link.
Pointing only to an edited, merged, or split predecessor is invalid; predecessor lineage remains
visible through the replacement graph rather than substituting for current coverage.

Candidate actions may update the list of suggested Source links, but they never record a Source
outcome. This separate pass is what proves that repositories, documents, unavailable records, and
background sources were not lost behind an Experience grouping decision.

### 5. Coverage and checkpoint gate

Always show:

- all nine category rows, including empty categories;
- every Source and whether it has a final disposition;
- every candidate, including replaced and generated successors, and whether it has a final
  disposition;
- unresolved candidates and Sources;
- conflicts, exclusions, unavailable Sources, and discovery-only links;
- replacement-graph closure;
- stable blocker codes and the exact coverage hash.

Keep two readiness meanings separate:

- `review-incomplete`: at least one decision slot is empty, a replacement relation is invalid, or
  a confirmed candidate lacks a bound Source;
- `checkpoint-ready`: every Source and candidate has a final outcome and the graph closes. Explicit
  unresolved, conflict, exclusion, unavailable, and empty-category rows remain visible but are not
  silent-omission blockers.

`checkpoint-ready` is not `sealable`. Formal sealing separately requires the user's exact
acceptance response and a current passing Phase 7 independent verification.

## Deterministic coverage contract

The machine coverage report binds the proposal or Inventory Revision hash and contains private ID
sets rather than only aggregate counts:

- category rows with candidate IDs by final state;
- Source IDs by disposition;
- candidate IDs by disposition;
- unresolved, conflict, exclusion, unavailable, and discovery-only ID sets;
- predecessor/successor closure findings;
- blocker codes;
- `review_status` equal to `review-incomplete` or `checkpoint-ready`.

Counts are a presentation convenience derived from those exact sets. A report with totals but no
ID closure cannot prove omission freedom. Conversely, public output must not reproduce either the
private sets or source-derived totals.

At minimum, use these blocker classes:

- `candidate-disposition-missing`;
- `source-disposition-missing`;
- `replacement-successor-missing`;
- `replacement-graph-invalid`;
- `candidate-source-unknown`;
- `confirmed-source-unbound`;
- `source-disposition-link-invalid`;
- `self-report-source-required`;
- `source-snapshot-mismatch`.

The report is recomputed before display, revision materialization, checkpoint response, and seal.
A cached `checkpoint-ready` value has no authority.

## Exact user checkpoint

After a complete draft materializes the immutable Inventory Revision, show the final category,
Source, candidate, unresolved, conflict, exclusion, and unavailable summaries together with the
exact revision and coverage identities. Offer exactly two decisions:

1. `accept-exact-revision`;
2. `return-for-correction` with a non-empty reason.

The structured response contains:

- reviewer identity and time;
- Source snapshot identity and cutoff;
- Inventory Revision hash;
- coverage-report hash;
- decision and optional correction reason.

Acceptance does not rely on the user retyping a long hash. A CLI command or UI button may carry
the displayed identities in its structured action, provided the retained response binds those
exact values. Any hash mismatch or source drift rejects the response.

`accept-exact-revision` freezes that revision. A later edit starts a linked child review and later
produces a child Inventory Revision; it never mutates the accepted object. `return-for-correction`
leaves the proposed revision unaccepted and starts a linked draft with the stated reason.

The checkpoint response does not by itself seal Phase 8. Ticket
[Refresh the Current Phase 7 Independent Verification](../issues/08-refresh-the-phase-7-independent-verification.md)
must establish the current prerequisite, and ticket
[Seal the User-Accepted Inventory Revision](../issues/09-seal-the-user-accepted-inventory-revision.md)
must verify all bound inputs before publishing the accepted seal.

## Synthetic acceptance cases for implementation

1. Acceptance with any pending candidate or Source slot is blocked and identifies the exact IDs.
2. Confirming every candidate while one Source remains pending is still blocked.
3. Merge creates one pending successor; split creates all pending successors.
4. A successor cannot inherit confirmation, exclusion, or unresolved status from its predecessor.
5. A user-added item without an exact declared self-report Source is blocked.
6. All nine category rows render even when several have no candidates.
7. An explicit unresolved candidate appears in coverage, allows checkpoint readiness, and remains
   Phase 9-ineligible.
8. An unavailable Source receives a visible disposition without implying factual rejection.
9. Complete ID-set coverage produces one stable hash independent of display order.
10. Any draft mutation changes the would-be revision and coverage identities.
11. Exact acceptance freezes the revision; a later correction requires a linked child.
12. A stale coverage report, changed Source snapshot, or mismatched checkpoint response fails
    closed.

## Result

Adopt the five-section checkpoint and the proposal → draft → immutable revision → coverage → exact
response flow. It is the smallest design that remains usable for a real career ledger, proves
Source and candidate closure, keeps unresolved items visible, and preserves the single inventory
and Source authorities.
