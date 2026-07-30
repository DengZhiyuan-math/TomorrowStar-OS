---
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
reviewed: 2026-07-30T17:02:59Z
depth: standard
files_reviewed: 45
files_reviewed_list:
  - _career_evidence_build.py
  - pyproject.toml
  - scripts/run_career_evidence.py
  - scripts/run_pytest.py
  - src/career_evidence_graph/cli.py
  - src/career_evidence_graph/domain/__init__.py
  - src/career_evidence_graph/domain/fixtures.py
  - src/career_evidence_graph/domain/invariants.py
  - src/career_evidence_graph/domain/models.py
  - tests/fixtures/domain_fixture.json
  - tests/test_cli_tracer.py
  - tests/test_domain_invariants.py
  - tests/test_domain_models.py
  - tests/test_fixture_mutations.py
  - tests/test_stoa_fixture.py
  - validation/fixtures/stoa/v1/candidates.json
  - validation/fixtures/stoa/v1/review.json
  - validation/fixtures/stoa/v1/source-manifest.json
  - validation/fixtures/stoa/v1/known-good.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/manifest.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/raw_response.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/original_proposal.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/confirmed_result.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good/corrections.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/manifest.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/raw_response.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/original_proposal.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/confirmed_result.json
  - validation/fixtures/stoa/v1/formal-runs/stoa-known-good-v2/corrections.json
  - validation/fixtures/stoa/v1/known-bad/dimension-confusion.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-experience.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-ontology.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-repository.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-resume-skill-list.json
  - validation/fixtures/stoa/v1/known-bad/direct-mastery-title.json
  - validation/fixtures/stoa/v1/known-bad/duplicate-evidence-link.json
  - validation/fixtures/stoa/v1/known-bad/missing-assessment-basis.json
  - validation/fixtures/stoa/v1/known-bad/missing-context.json
  - validation/fixtures/stoa/v1/known-bad/missing-contribution-lineage.json
  - validation/fixtures/stoa/v1/known-bad/missing-duration.json
  - validation/fixtures/stoa/v1/known-bad/obscured-codex-assistance.json
  - validation/fixtures/stoa/v1/known-bad/ontology-mastery-change.json
  - validation/fixtures/stoa/v1/known-bad/score-above-hundred.json
  - validation/fixtures/stoa/v1/known-bad/score-below-zero.json
  - validation/fixtures/stoa/v1/known-bad/wrong-responsibility.json
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 02: Code Review Report

**Reviewed:** 2026-07-30T17:02:59Z
**Depth:** standard
**Files Reviewed:** 45
**Status:** clean

## Summary

Final adversarial consistency audit of commit `4470947` found no actionable correctness, security, or robustness issue. The restored, standard-library PEP 517/660 backend is `_career_evidence_build.py`; there is no tracked current file named `_build_backend.py`, so the reviewed-artifact list now names the actual backend rather than retaining the former deletion marker.

Regular wheels are self-contained and deterministic: two fresh-cache offline builds with the same `SOURCE_DATE_EPOCH` were byte-identical. The inspected wheel had 18 unique, safe relative archive members, no `sitecustomize.py`, `.pth`, absolute checkout path, or global startup hook. Its generated metadata is consistent with `pyproject.toml`, and every member has a valid SHA-256/size entry in `RECORD` except `RECORD` itself, which correctly has empty hash and size. The editable hook is confined to `build_editable`: its wheel alone contains `career_evidence_graph-editable.pth`; the regular wheel contains none.

Verification performed with `PYTHONPATH` removed where applicable:

- `uv run --locked python scripts/run_pytest.py -p no:cacheprovider -q` — `173 passed, 1 deselected`.
- `uv run --locked python scripts/run_pytest.py -p no:cacheprovider -q tests/test_cli_tracer.py` — `9 passed`, including a fresh empty `UV_CACHE_DIR` plus `UV_OFFLINE=1` wheel build, external venv install, and installed-artifact import probe.
- `uv run --locked ruff check .` and `uv run --locked ruff format --check .` — passed.
- Fresh-cache direct `uv build --wheel --offline` twice — passed with byte-identical wheels; archive and editable-wheel containment probes passed.
- Sealed fixture validation, all 16 one-fault known-bad cases, both FormalRun verify/replay paths, and provenance verification — passed. The v2 source-manifest/review/checkpoint binding, confirmed-reviewer requirement, evidence basis, Contribution containment, declared-Skill binding, and user versus Codex-assisted semantics remain enforced.

## Narrative Findings (AI reviewer)

No Critical Issues, Warnings, or Info findings.

### Closure note for `4470947`

The prior regression (a fresh-empty-cache offline wheel build requiring uncached Flit) is closed by the in-tree backend. Its regular-wheel path does not call the editable-wheel implementation and cannot emit the editable `.pth`; the focused regression verifies both the build/install boundary and the installed distribution paths outside the checkout.

---

_Reviewed: 2026-07-30T17:02:59Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
