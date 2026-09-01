# Design the Human Review and Coverage Checkpoint

Type: prototype
Status: resolved
Blocked by: 04

## Question

What is the smallest realistic review packet and coverage report that lets the user confirm,
edit, add, split, merge, exclude with a reason, or retain unresolved candidates while proving that
every Source and candidate received a visible Disposition before acceptance?

## Comments

Resolved through the disposable logic prototype recorded in
[Human Review and Coverage Checkpoint Design](../research/05-review-coverage-checkpoint.md).

The smallest realistic checkpoint has two review queues—Experience Candidates and Sources—plus
one derived coverage view. An immutable candidate proposal is reviewed through one resumable,
hash-bound draft. Pending slots are not Dispositions and cannot enter an `InventoryRevision`.
Edits, merges, and splits add successor candidates back to the queue; confirming a candidate does
not silently disposition any Source.

When every candidate and Source has a final outcome and the replacement graph closes, the system
materializes one immutable Inventory Revision and recomputes coverage from it. The user then makes
one explicit `accept-exact-revision` or `return-for-correction` decision bound to the revision and
coverage hashes. Explicit unresolved items remain visible and do not block checkpoint readiness;
they remain blocked from Phase 9. Formal sealing still waits for current Phase 7 verification.
