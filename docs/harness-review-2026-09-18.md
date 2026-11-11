# Harness organization and review — 2026-09-18

## Review basis

Reviewed the current checkout at base commit `e4a26d0`, including pre-existing
uncommitted Candidate Skill Link implementation and documentation. Those local
changes were preserved. Results describe the resulting checkout, not that commit
alone. No files were staged, committed, pushed or deployed.

Scope: project navigation, active workflow authority, source containment,
Contribution audit transitions, attribution, assessment admission, CLI diagnostics
and offline verification. Defect reproduction used synthetic temporary data.
The private repository's organizational documentation and script layout were
inspected; personal source bodies, answers and graph records were not audited.

## Organization completed

- Added the root README, architecture, conventions, workflow guide and data-boundary
  map. Existing source, fixture and evidence paths remain stable.
- Reconciled AGENTS with the active v1.1 scope and linked executable ownership.
  Historical stack research remains labelled as research rather than an instruction
  to reintroduce unused architecture.
- Added a dated STATE handoff that distinguishes implemented local candidate
  support from pending phase acceptance. Clarified active Phase 3/7 simplifications
  and corrected the stale Phase 2 regression statement in current milestone indexes.
- Standardized verification examples on checkout-source launchers. Excluded both
  declared live-test markers by default. Added ignore rules for nested worktrees
  and research caches without deleting their contents.
- Updated private README/workflow navigation and preserved its prior workflow note
  in a private archive. Personal records and private operator paths remain in place.

## Confirmed defects and repairs

| Defect | Consequence | Minimal repair / regression boundary |
| --- | --- | --- |
| Public and private worktrees could share a Git common directory | A supposed private workspace shared the public object database | Compare local Git common-dir identity; reject linked public worktrees |
| Raw containment checked only a literal ignore line | Negation rules or already tracked raw files bypassed intended exclusion | Check effective ignore for the target and reject raw-vault index entries before writes |
| Base registry mutation after immutable successors | Stored parent hash became unresolvable | Freeze base capture/mapping once successors exist; reject before side effects; preserve all prior bytes |
| Duplicate-prompt guard and attribution resume | Multi-area audits and interrupted capability follow-ups could dead-end | Scope attribution duplicates to their area/turn, distinguish resumed prompts and reuse already answered attribution |
| Mixed assistance and negated ownership heuristics | Assistant involvement could disappear or negated work become user ownership | Keep conflicting assistance or negated apparent ownership unresolved, retaining the answer and assistance scope |
| Candidate identity without links used snapshot v1 | Optional candidate links effectively became required for a candidate-scoped audit | Use v2 for candidate identity even with zero links; preserve candidate-free legacy serialization |
| Decision port could return a different Contribution plan | Probe context was not bound to the selected audit target | Reject foreign Contribution IDs at the workflow boundary |
| Later review could erase a prose correction | Original structured capability could re-enter proposals despite correction | Preserve corrections through subsequent review; corrected prose cannot authorize an unchanged structured assessment |
| Pydantic/file exceptions echoed input or paths | Malformed private input could leak through routine stderr | Emit stable schema error types and content-free read errors; retain synthetic sentinel regression cases |

The ownership/assistance classifier remains a conservative heuristic. The changes
cover demonstrated failures, not arbitrary natural-language understanding. Human
review and explicit unresolved states remain necessary.

## Verification

Focused source custody/security tests: **34 passed**. Charter validation and the
upstream provenance registry verification passed. CLI diagnostics were reproduced
with synthetic sentinels; the original formatted Pydantic exception exposed its
input value.

An isolated marker probe passed its offline control and deselected both live
markers (1 passed, 2 deselected), without invoking a provider. Public and private
navigation links were checked locally.

Final integration on the repaired checkout:

| Check | Result |
| --- | --- |
| `uv run --locked python scripts/run_pytest.py -q` | **446 passed, 1 live-model test deselected** |
| Focused workflow/assessment/calibration/JD consumers | 165 passed |
| Focused source custody/security | 34 passed |
| `uv run --locked ruff check .` | Passed |
| `uv run --locked ruff format --check .` | Passed; 94 files already formatted |
| `git diff --check --ignore-submodules=all` | Passed |
| Charter and provenance CLI verification | Passed |
| Public/private navigation links and documented calibration hashes | Passed |
| Original corpus, policy history, STOA fixture and dependency lock | No diff from base HEAD |

Commands used a writable temporary `UV_CACHE_DIR`. No live provider execution,
new policy activation or private-record migration was part of verification.

The correction-retention repair exposed three failures in focused positive tests:
the old calibration corpus itself used an edit-then-confirm journey with erased
correction. That red evidence was retained. The original `corpus.json` and policy
history are preserved byte-for-byte; a separately named synthetic positive corpus
uses direct confirmation and newly computed audit hashes. Explicit negative tests
keep the old journey ineligible. This is fixture succession for a repaired
contract, not recalibration, score adjustment, or transfer of historical acceptance.
The [calibration input succession record](../validation/calibration/phase-04/README.md)
pins both file identities and the unchanged historical policy record. The legacy
regression reconstructs the original erased-correction snapshot at its exact
historical hashes and verifies that all assessment entrypoints reject it.

## Remaining limits and next work

1. **Acceptance remains pending.** This review does not complete independent Phase
   7 verification, reconcile or accept private inventory, build a reviewed personal
   graph, or establish real-JD usefulness. Existing checkpoints remain binding.
2. **Generic full-career admission is incomplete.** The fixture audit foundation
   does not provide a complete Phase 8 seal-to-Phase 9 runtime adapter. Keep unsealed
   inventory out of downstream scoring until that path is implemented and tested.
3. **Source successors constrain updates.** Finish base capture/mapping before the
   first successor. A general successor-based later-capture API is not implemented;
   never bypass `registry-frozen` with manual edits or deleted revisions.
4. **Private inventory adapters remain local.** Separate their source-specific seeds
   before extracting reusable code; do not copy personal assumptions or fixtures
   into the public harness merely to consolidate directories.
5. **Local safeguards have a bounded threat model.** No claim is made about
   multi-process races, malicious same-user filesystem changes, remote visibility,
   backup/encryption, or historic Git disclosure. The stores retain their trusted
   single-user scope.
6. **Historical evidence stays historical.** Legacy STOA documentary fixtures and
   prior planning records were preserved. No new private material was imported into
   public fixtures, and past public history was not certified or rewritten.

The fixes add no dependencies, database, provider integration or general workflow
engine. The system remains an inspectable Python core with explicit local review.

## Subsequent requested application integration

The user subsequently requested one local workspace joining career evidence and
existing application tracking. The [career workspace guide](career-portal.md)
records this additional scope, startup, storage and compatibility boundaries.
It adds application-note edits and read-only documentary navigation; no assessment
or phase acceptance changes follow from its existence.

The implementation reuses the separate-workspace guard and independently supports
the existing Markdown note format. There are no new dependencies. Private records
stay in the selected folders; optional folder configuration stays in user
Application Support. Updates require the viewed revision, retain exact original
bytes, and preserve unrelated properties. Career links retain documentary meaning.

Integration checks identified and repaired additional concrete issues: disappeared
roots appearing empty, non-ASCII CSRF header exceptions, malformed startup config,
out-of-range ports, leaked listening sockets on startup failure, nested JD heading
truncation, cloud-file reads blocking the dashboard, unknown dates sorting above
real dates, disabled editors not recovering after read failure, and unsaved inputs
being lost when switching records. Browser confirmation prompts were replaced
with page dialogs after they blocked the embedded-browser recovery path.

Verification on the integrated checkout:

- Complete offline suite: **520 passed, 1 live-model test deselected**.
- After the final date-ordering fix: **75 portal tests passed**, including its
  new regression. These use only disposable synthetic workspaces.
- Ruff lint and formatting, JavaScript syntax and Git whitespace checks passed.
- Browser checks covered search, status filters, create, edit, reload persistence,
  multiline text, documentary association and preview, stale-revision rejection,
  retained inputs, cancel/confirm recovery, and a 389 CSS-pixel layout with no
  horizontal page overflow. The fresh final test tab reported no console errors.
- Existing private sources were connected and read-only smoke-tested. This was
  operational verification, not a capability or content audit. No personal record
  was changed by browser testing; all browser writes used temporary synthetic data.

The running UI remains loopback-only and single-user. Some original career files
may be cloud placeholders; their metadata remains visible and unavailable detail
reads return an actionable download message. The file catalog is not full-text
search, a canonical Skill graph editor, or a replacement for milestone review.
