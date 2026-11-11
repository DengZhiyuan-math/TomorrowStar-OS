# Define the Adversarial Verifier Contract

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

Which smallest synthetic end-to-end and negative cases must the harness run to
prove candidate-only ingress, Contribution-grounded assessment, user-Skill
lineage, and verifier alignment without duplicating existing invariant tests?

## Answer

Reuse the existing direct-mastery, Contribution/claim/evidence lineage, and
user-Skill graph invariants. Add only candidate-link-specific synthetic cases:

1. a Candidate Skill Link alone cannot create an assessment or user Skill;
2. a link cannot be attached across its Experience Candidate boundary to an
   unrelated Contribution;
3. candidate wording may appear as a recall reminder but cannot satisfy an
   assessment basis; and
4. a complete, attributed Grill-Me Contribution may support a Skill even when
   no Candidate Skill Link exists.

Candidate links are therefore optional discovery and audit-context provenance,
not a scoring prerequisite. The positive case still uses the existing
completed-audit, confirmed-conclusion, Contribution, attribution, evidence,
and assessment/admission path. The negative cases must assert the existing or
new stable boundary codes without duplicating generic direct-source tests.
