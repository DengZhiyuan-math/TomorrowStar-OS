---
quick_id: 260908-kmh
phase: quick-260908-kmh
plan: "01"
type: execute
wave: 1
depends_on: [260908-dbj]
files_modified:
  - src/career_evidence_graph/cli.py
  - tests/test_audit_cli.py
autonomous: true
---

<objective>
Expose the completed Candidate Skill Link audit context through the existing
offline harness CLI.

<tasks>
<task type="auto" tdd="true">
<name>Task 1: Pass a versioned candidate-link JSON array into audit start</name>
<files>src/career_evidence_graph/cli.py, tests/test_audit_cli.py</files>
<action>Add only explicit audit-start options for the selected Experience Candidate and a JSON array of Candidate Skill Links. Validate the array through the existing strict model and delegate to `start_audit`; preserve no-candidate CLI behavior unchanged.</action>
<verify>uv run --locked python scripts/run_pytest.py -q tests/test_audit_cli.py</verify>
</task>
</tasks>

<success_criteria>
The existing CLI can create a v2 candidate-aware audit with its unverified
recall reminder, rejects malformed links through normal CLI validation, and
adds no storage, extractor, provider, or private-data path.
</success_criteria>
