# Synthetic calibration input succession

The current CLI default is `corpus-review-safe-v1.json`. It is a new,
source-bound **synthetic** journey with direct confirmation of its structured
capability entry. Its candidate and cases retain their `derived-counterfactual`
or `synthetic-negative` labels. These scripted confirmations do not establish
user capability, inherit a historical human review, or activate a policy.

`corpus.json` is retained byte-for-byte as historical negative evidence. Its
edit → confirm journey exposed a bug that erased the effective prose correction
and then let the original capability support an assessment. Current audit-journey
materialization and assessment admission reject this journey. Existing snapshots
with an erased correction remain ineligible when their review history records the edit.

| Artifact | SHA-256 of exact file bytes | Authority |
| --- | --- | --- |
| `corpus.json` | `5bbb737862799fad4574ba25151a2f76947191abc1f76f1bfc749427cb016121` | Historical input; correction-erasure regression |
| `corpus-review-safe-v1.json` | `66272ee5b259e95faf5e99e330ecaf313a039ea142a81914e9e0169dd8b4e00f` | Current synthetic positive input with its own audit and review lineage |
| `policy-calibration/history.json` | `812483e660b1b7989ac95342ef36d6a82395efbd8c7eda21c392e5dd32c96403` | Unchanged historical policy record; no authority transfer to the successor |

The successor changes only the scripted review journey and its resulting audit
snapshot and conclusion-lineage hashes. Fixture/source hashes, candidate scores,
judgment bases, cases, and policy definitions remain unchanged. Recomputing the
effective-conclusion hash yields the same value because direct confirmation
produces the same structured fields the historical bug left behind; the changed
snapshot and review-lineage hashes distinguish the two input histories.

Free-text corrections are preserved through later confirmation or rejection.
They do not rewrite structured capability claims automatically. A new structured
audit is required before a corrected entry can support an assessment. No personal
workspace was read, migrated, or rescored for this synthetic repair.
