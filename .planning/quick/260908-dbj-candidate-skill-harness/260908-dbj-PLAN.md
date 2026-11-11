---
quick_id: 260908-dbj
phase: quick-260908-dbj
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified:
  - src/career_evidence_graph/audit/models.py
  - src/career_evidence_graph/audit/workflow.py
  - src/career_evidence_graph/assessment.py
  - tests/test_candidate_skill_harness.py
autonomous: true
---

<objective>
Deploy the approved Candidate Skill Link execution boundary into the synthetic
offline harness.

Purpose: External-source candidate skills may guide and remind an audit without
becoming capability authority; only completed, attributed Contributions remain
score-eligible.
Output: A small versioned candidate-link contract carried through audit context,
conclusion/proposal provenance, and focused synthetic acceptance tests.
</objective>

<tasks>

<task type="auto" tdd="true">
<name>Task 1: Add optional Experience-Candidate-scoped audit context</name>
<files>src/career_evidence_graph/audit/models.py, src/career_evidence_graph/audit/workflow.py, tests/test_candidate_skill_harness.py</files>
<action>Add the smallest strict Candidate Skill Link model and optional audit inputs that preserve its source/capture identity, locator, wording, extraction version, and exactly one Experience Candidate. Candidate links may be supplied only for the matching selected Experience Candidate and may create an explicitly unverified recall reminder. They cannot alter question validity, ownership, assistance, coverage, or capability decisions. Preserve all existing no-candidate callers unchanged.</action>
<verify>uv run --locked pytest -q tests/test_candidate_skill_harness.py</verify>
</task>

<task type="auto" tdd="true">
<name>Task 2: Retain optional candidate provenance without creating assessment authority</name>
<files>src/career_evidence_graph/audit/models.py, src/career_evidence_graph/audit/workflow.py, src/career_evidence_graph/assessment.py, tests/test_candidate_skill_harness.py</files>
<action>Carry selected Candidate Skill Link IDs to audit conclusions and any resulting specific-Skill proposal as optional provenance. Reject cross-Experience attachment and any attempt to use candidate text/link alone as an assessment basis. Prove that a complete audit remains score-eligible without a link. Reuse the existing generic direct-source and lineage checks rather than duplicating them.</action>
<verify>uv run --locked pytest -q tests/test_candidate_skill_harness.py tests/test_audit_policy.py tests/test_assessment_proposal.py</verify>
</task>

</tasks>

<success_criteria>
- Candidate links are scoped, source/capture-bound, versioned, and non-assessing.
- A selected link can appear as a clearly unverified recall reminder.
- Cross-Experience candidate context is rejected.
- Candidate-free audited Contributions preserve the existing proposal path.
- Focused tests, the full offline suite, and Ruff pass without private data or new dependencies.
</success_criteria>
