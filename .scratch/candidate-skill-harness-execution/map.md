# Candidate-Skill Harness Execution Logic

## Destination

The offline harness can reproducibly prove that external materials create only
candidate Skills and source links, while only Grill-Me-derived Contributions
and their Contribution-Skill assessments can support the evidence-backed user
Skill graph.

## Notes

Domain: Career Evidence Graph. Consult `grilling` and `domain-modeling` for
each HITL decision. Preserve the current source-custody and Phase 7 boundaries:
use synthetic fixtures only, do not read or import private career-data, and do
not change calibration or JD scoring semantics while establishing this ingress
and lineage contract. Follow the project YAGNI/reuse order.

## Decisions so far

<!-- Resolved tickets are indexed here. -->

- [Define the Candidate-Source Contract](issues/01-candidate-source-contract.md): Candidate
  Skill Links are scoped to one Experience Candidate, source-bound and non-assessing; repeated
  candidate wording is represented by separate links.
- [Define the Audit Retrieval Boundary](issues/02-audit-retrieval-boundary.md): Candidate links
  select and trace audit coverage, and may be a non-leading recall reminder; they never replace
  the completed, attributed Contribution evidence needed for assessment.
- [Define the Adversarial Verifier Contract](issues/03-adversarial-verifier-contract.md): Reuse
  existing lineage invariants and add only candidate-link ingress, Experience-boundary, reminder,
  and no-candidate positive cases; candidate links are optional audit provenance.

## Not yet specified

None. The harness contract and its minimum adversarial acceptance boundary are
specified.

## Out of scope

- Importing, scoring, or otherwise operating on real private career-data.
- Changing mastery calibration, confidence admission, JD matching, or résumé
  generation policy.
- Choosing or implementing a model-assisted candidate-skill extractor; the
  harness accepts versioned candidate links regardless of how they were found.
- Binding a real accepted private-workspace revision or private career-data to
  this synthetic harness.
