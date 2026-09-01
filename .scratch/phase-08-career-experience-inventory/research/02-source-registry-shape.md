# Characterize the Private Source Registry for Inventory Consumption

## Answer

Phase 8 should consume the Phase 7 registry through one new read-only seam in
`workspace.py`; it should not parse `.career-evidence/registry.json` independently and should
not create another source registry. The seam must return an exact, validated snapshot of the
registry plus only those referenced capture objects whose bytes have been verified against their
declared content identities. That snapshot is candidate-only provenance. It can drive coverage,
discovery, and source lineage, but it cannot establish an Experience or any downstream capability
claim.

The inspected private revision conforms to the strict public registry contract and its referenced
capture objects are internally consistent. This note intentionally omits all private labels,
locations, source-derived counts, dates, hashes, and findings.

## Exact registry contract

The registry is one JSON object with exactly three top-level fields:

| Field | Contract | Phase 8 meaning |
|---|---|---|
| `cutoff` | ISO calendar date | Career-fact scope boundary; not a source acquisition date. |
| `categories` | Non-empty, unique list of safe identifiers | Source-universe coverage groups; not Experience categories. |
| `sources` | Non-empty list of strict source rows | Complete source-disposition input for the bound registry snapshot. |

Each source row permits only:

- required `source_id`, `category`, `source_type`, and `availability`;
- required non-empty `unavailability_reason` when availability is not `available`, and no reason
  when it is `available`;
- optional `capture` with exactly `content_hash` and timezone-aware `captured_at`;
- optional `derived` with `input_hash`, `output_hash`, `transformer` identity/version, and an
  optional locator.

IDs are unique and path-safe. `category` must refer to the registry's declared category list.
`source_type` is closed over document, self-report, formal credential, repository, web snapshot,
cloud export, audit record, and examination record. Availability is closed over `available` plus
the six explicit unavailable states: temporary unavailability, permanent loss, restricted access,
never created, unknown location, and user decline. The implementation owns these constraints;
Phase 8 must reuse them rather than mirror them in a second validator.

Sources: `src/career_evidence_graph/workspace.py:14-38`,
`src/career_evidence_graph/workspace.py:222-314`.

## Capture and availability semantics

Availability and capture state are independent axes:

- `available` means the row is eligible for capture. It does not mean a capture exists, the source
  remains reachable now, or any statement in it is accepted.
- An unavailable row must retain its explicit status and reason and cannot be captured through the
  current API.
- A capture records exact payload bytes once in the ignored content-addressed vault, then adds the
  payload identity and acquisition time to the source row. The same logical source cannot be
  recaptured by this MVP API.
- Registry validation checks capture metadata syntax, but its current read path does not verify
  that the referenced raw object exists or that its bytes still match the declared identity.
- A failed registry publication may deliberately leave an unreferenced raw object. Therefore a
  reader must traverse from registry references to capture objects, never enumerate the raw vault
  as though every object were authoritative.
- `derived` is caller-supplied lineage only. It does not store or verify derived output bytes and
  cannot confer factual authority.

Sources: `src/career_evidence_graph/workspace.py:71-134`,
`src/career_evidence_graph/workspace.py:195-206`,
`tests/test_career_source_custody.py:67-120`,
`tests/test_career_source_custody.py:145-166`.

## Shape of the current capture payloads

Read-only inspection found repository and local-project schema-versioned provenance-manifest
shapes. Both explicitly label themselves candidate-only and bind themselves to a logical source
and cutoff.

1. A repository provenance manifest contains repository identity and descriptive metadata,
   including the default branch plus pinned commit and tree identities. It does not contain a
   repository file tree or source-document bytes.
2. A local-project provenance manifest contains an operational project locator, Git identity when
   present, a bounded file inventory, capture-policy metadata, and a summary. Its file rows
   distinguish Git-HEAD content from local changes and distinguish hashed content from missing,
   non-regular, oversized, or budget-exhausted content. It explicitly declares that it is not a
   byte-for-byte backup.

Consequently, a capture hash identifies the provenance manifest payload—not necessarily the
career-bearing document described by that manifest. Repository metadata and file-path inventory
can propose where to look, but a reviewed candidate fact needs a precise supporting locator and
content identity. For committed local content, the pinned Git HEAD plus repository-relative path
can provide that identity. For a hashed local change, Phase 8 must verify the current bytes against
the recorded per-file identity before using them. A row without a usable content identity can only
remain a discovery clue or unresolved source until exact supporting material is captured.

Private primary source: authorized private workspace registry and referenced content-addressed
provenance manifests, inspected read-only on 2026-09-01. The private locator and derived details
are intentionally not recorded here.

## Minimal safe Phase 8 seam

The current public API exposes `open_private_workspace` and a content-free `workspace_status`, but
the only full registry loader is private. Status is intentionally insufficient for inventory
generation. Add one small read-only API to the existing module with this behavior:

1. Accept the private workspace explicitly and re-run the separate-Git-worktree and symlink
   checks.
2. Load the registry through the existing strict loader.
3. Bind the exact canonical registry bytes to a snapshot identity. This is necessary because the
   source declaration is create-only, but capture and derived-lineage operations update the same
   registry file in place.
4. For each source with a capture, resolve only the content-addressed object referenced by that
   row; reject a symlink, missing/non-regular object, or byte-identity mismatch.
5. Return detached candidate-only data: cutoff, source-coverage categories, source rows, capture
   metadata, and verified capture payload bytes or a deliberately narrow decoded manifest view.
6. Keep all readable labels, operational locators, counts, hashes, and diagnostics inside the
   explicitly selected private workspace. Public status and errors stay content-free.

This is a read seam, not a new store, parser, registry, or evidence authority. The Inventory
Revision should retain the exact source-snapshot identity and per-candidate source locators so a
later correction creates linked lineage instead of silently following a changed registry.

Sources: `src/career_evidence_graph/workspace.py:49-68`,
`src/career_evidence_graph/workspace.py:137-206`,
`tests/test_career_source_security.py:35-123`,
`.planning/phases/08-full-career-inventory-review-and-seal/08-CONTEXT.md:157-181`.

## Field authority matrix

| Registry or manifest field | Safe use in Phase 8 | Forbidden interpretation |
|---|---|---|
| cutoff | Bind inventory scope | Proof that an event occurred by the cutoff |
| source ID | Stable lineage and disposition key | Experience identity or corroboration weight |
| source category | Source coverage/navigation | Direct mapping to an Experience category |
| source type | Choose a safe inspection adapter | Credibility, mastery, or independence weight |
| availability and reason | Coverage and unavailable disposition | Factual rejection or absence of an Experience |
| capture identity/time | Bind exact acquired manifest bytes | Truth of statements described by the manifest |
| derived mapping | Preserve claimed transformation lineage | Verified output, accepted fact, or accepted candidate |
| repository metadata | Candidate discovery and exact-revision lookup | Project ownership, responsibility, employment dates, or Skill |
| local project/path inventory | Find and verify possible supporting material | One repository or directory equals one Experience |
| repeated source descriptions | Merge-review clue with all lineage retained | Automatic merge or increased confidence |

The Phase 8 boundary independently requires candidate review, complete source/candidate
dispositions, and explicit user acceptance. Repository presence and repeated wording remain clues,
not career or capability authority.

Sources: `.planning/phases/08-full-career-inventory-review-and-seal/08-CONTEXT.md:9-23`,
`.planning/phases/08-full-career-inventory-review-and-seal/08-CONTEXT.md:32-68`,
`.planning/phases/07-career-source-custody-and-private-workspace/07-12-SUMMARY.md:29-35`.

## Planning implications

- Candidate generation can start after the read seam verifies and snapshots the registry; formal
  sealing remains separately blocked by the Phase 7 independent-verification prerequisite.
- Source coverage must include four distinguishable states: available/captured,
  available/uncaptured, unavailable-with-reason, and capture-integrity failure. None should be
  silently collapsed.
- The current private manifests are sufficient to enumerate the source universe and locate likely
  seed material, but they are not by themselves a complete content corpus. The first candidate
  pass must capture or precisely bind the supporting document/blob used for each factual proposal.
- Source-universe categories and Phase 8 Experience categories are different taxonomies and need
  an explicit review decision rather than automatic mapping.
- All candidate records must continue to carry `candidate-only` authority until the user assigns a
  disposition and accepts the exact Inventory Revision.
