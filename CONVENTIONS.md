# Conventions

Follow the repository's YAGNI/reuse order in [AGENTS.md](AGENTS.md). Keep domain
meaning in [CONTEXT.md](CONTEXT.md), module boundaries in
[ARCHITECTURE.md](ARCHITECTURE.md), and current acceptance status in the
[roadmap](.planning/ROADMAP.md). Plans, completed implementation, synthetic
verification, and accepted personal data are distinct states.

## Implementation

- Use the locked Python 3.13 toolchain and existing standard-library/Pydantic
  patterns. Add a dependency or abstraction only for a concrete unmet need.
- Keep validated domain data separate from orchestration and persistence. Reuse
  existing hashing and store helpers instead of creating parallel validators or
  sources of truth.
- Follow [single-job flow](docs/single-job-flow.md) for the current application
  design and [development plan](docs/development-plan.md) for implementation order.
  Keep jobs strictly sequential. Important missing facts, actual conflicts and
  unknown results wait on the current job; only the user's skip moves past it.
  Waiting may collect new mail, but does not start work on another job. Normal
  reopening continues work; explicit pause and pending user input retain waiting.
  Manual intervention preserves edits and needs one Continue. Submit remains manual.
- Do not add approval states for package/version diagnostics, receipt freshness,
  controller leases, privacy or individual platform requests. Use actual OS
  permissions for capabilities that need them and check real operation results.
  Direct corrections to saved facts do not require a research inventory seal.
- Retain original proposals and explicit review decisions where existing
  contracts require them. Candidate wording, document presence, and JD relevance
  must not become capability evidence.
- Preserve immutable fixture, formal-run, and review evidence. Changes to sealed
  inputs require their existing successor/reissue workflow, not an in-place edit.
- Keep private material out of public docs, fixtures, logs, and tests. Tests use
  synthetic temporary workspaces; see [data boundaries](docs/data-boundaries.md).

## Verification

For application-page acceptance, randomly select a different real job for each
run. Keep the tested URLs and outcomes in the private evidence workspace and
exclude recorded targets from the next selection. Use the existing main App.
Generated pages do not establish product acceptance. Offline unit and API
regressions remain code checks. Final Submit stays with the user.

Run from the repository root against checkout source:

```bash
uv run --locked python scripts/run_pytest.py -q
uv run --locked ruff check --no-cache --extend-exclude .scratch .
uv run --locked ruff format --check --no-cache --extend-exclude .scratch .
git diff --check
```

Exclude sealed `.scratch` inputs and disable the Ruff cache so verification cannot
refresh historical cache files.

For offline verification, keep the default marker selection and do not add `-m`.
An explicit `-m` replaces the exclusions in `pyproject.toml`; `not browser` does
not exclude this repository's `worker_browser` tests.

For a bounded behavioral change, first run the affected tests. Add regression
coverage for the violated behavior or invariant, and run the complete offline
suite when shared contracts or workflow/storage behavior changes. Documentation
changes need relevant command/link checks, not a new test framework. Provider
calls remain explicitly opt-in; follow [validation runs](docs/validation-runs.md).

## Workflow records

### Native App installation

Use `/Users/zhdeng/Applications/TomorrowStar.app` with bundle ID
`dev.tomorrowstar.desktop` as the single installed App. Integrate accepted fixes
there; do not install separate test identities that require repeated permission
grants. Run acceptance with isolated synthetic inputs. Keep rollback copies in
private archives or directories without an `.app` extension outside Applications.
Use the pinned local certificate in the private `signing.json` configuration.
Normal builds and updates must verify its certificate pin and the fixed main App
designated requirement before writing output. Never fall back to ad-hoc signing
or create another `.app`; private staging and verification copies use non-App
extensions under `.noindex` directories. Use `macos/main_app.py` for checked
updates and rollback preservation. Finish signing before any permission repair.
Use `macos/check_main_permissions.py` against a fresh private evidence root when
diagnosing actual host permissions; its responsibility-chain checks are optional
diagnostic evidence, not a prerequisite for every application or local data write.
Check the actual permissions required by the selected capability. Keep the same
signing identity for later updates. Do not recreate the certificate or reset TCC
as a routine development step.

Keep active decisions easy to find and link superseded plans to their replacement
contract. Preserve historical failed or partial verification as evidence; record
a dated correction or a new result instead of relabeling the old run. A quick
task can implement a harness feature without completing its surrounding phase.
Do not duplicate personal records into planning summaries or infer user
acceptance from an implementation/test result.
