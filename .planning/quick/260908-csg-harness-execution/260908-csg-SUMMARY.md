# Quick Summary: Candidate-Skill Graph Harness Execution Logic

## Outcome

Charted and completed the Wayfinder decision map for the synthetic harness
boundary. No harness code, test, fixture, or private career-data was changed.

## Decisions

- A Candidate Skill Link is versioned and scoped to exactly one Experience
  Candidate; repeated candidate wording is represented by independent links.
- It retains source/capture identity, locator, wording, and extraction version,
  and has no scoring, responsibility, confidence, or mastery authority.
- Candidate wording may be a clearly non-conclusive recall reminder during
  Grill-Me. Forgetting source wording or a detail is not negative capability
  evidence.
- Candidate links are optional audit provenance. A complete, attributed
  Contribution may support an assessment without one.
- The later harness work reuses existing generic lineage invariants and adds
  only candidate-link-specific positive and adversarial cases.

## Next Step

Hand the completed map to a normal implementation workflow to add the minimal
synthetic contract and verifier cases. This planning result does not authorize
private-data import, calibration changes, or product execution.
