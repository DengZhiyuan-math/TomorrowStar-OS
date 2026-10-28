# Durable synthetic acceptance evidence

The new helper preserves a preparation candidate, original App stand-in, configuration,
source context and rollback references before creating an isolated work directory. It
reuses the preparation candidate freezer and its independent byte verification.

The completed demonstration preserved its evidence in an explicit persistent private
workspace outside the checkout and temporary trees. Raw requested commands, observed
return codes, stdout and stderr remain there. The Boolean-only public result is
[result.json](result.json). Private locators, inventories, measurements and fingerprints
are deliberately absent from this report.

The demonstration created a local synthetic Git source fixture. It retained its revision,
raw status and diff, dirty tracked bytes, included untracked source and an explicit excluded
change. A child interpreter executed the retained candidate entrypoint. Its raw stdout
identified the loaded file and its bytes. The resulting PDF matched the existing fixed
synthetic PDF fixture. This proves preservation and transport, not compilation or layout.

After successful exit, the helper compared the retained output with the owned work copy,
removed only that work copy, and repeated cleanup without deleting retained evidence.
After the demonstration removed all temporary inputs, a fresh process independently
verified the persistent candidate, baseline, rollback references, raw run and cleanup
receipt. Missing, corrupt and permission-drift copies failed verification. Their original
failure receipts remain private. A later permission normalization has a separate correction
record and does not replace those observed failures.

## Reproduce

Choose a **new** explicit directory in an existing persistent private workspace. Do not
use the repository or a temporary directory. Run from the checkout root:

```sh
uv run --locked --offline --no-sync python -B .scratch/durable-evidence-2026-10-20/run_synthetic_demo.py \
  --private-root /absolute/persistent/private/new-evidence
```

Reopen its retained evidence without recreating inputs or running the child again:

```sh
uv run --locked --offline --no-sync python -B scripts/preserve_acceptance_evidence.py verify \
  --evidence /absolute/persistent/private/new-evidence/evidence
```

For a different synthetic entrypoint, use the helper's `begin`, `run`, `verify` and
`cleanup` commands. `begin --help` lists its input arguments. Source context contains the
source revision, exact loaded entrypoint inventory entry, included untracked inputs,
raw source command observations, explicit excluded changes and `historical_baseline:
"unknown"`. This context is caller-supplied provenance; the helper does not independently
reconstruct a deleted checkout. The demonstration retains actual Git observations and
binds the executed entrypoint through its observed stdout.

## Failure and cleanup rules

Evidence destinations are append-only by operation: existing files cannot be overwritten.
Partial failed copies remain and require a new destination. Directories use 0700 and files
use 0600. Source permission facts remain in the baseline; copied permissions are independently
verified. Permission drift stops verification instead of being silently repaired.

`run_receipt_verified` establishes receipt integrity. `run_verified` also requires a
successful observed exit without timeout or retained descendants. Cleanup requires that
successful result, an absent owned process group, an exact ownership marker and matching
retained work bytes. A timeout or failed run retains its work and evidence. Missing,
corrupt, ambiguous, inaccessible and symlink inputs stop the chain. The helper does not
restore Apps or delete persistent evidence.

## Limits

Only a trusted synthetic Python entrypoint is executed. It receives no interactive stdin
and has a bounded execution time and per-file output limit. Execution is not a filesystem
or network sandbox; review the synthetic entrypoint before using it. The demonstration
uses no external services, models, Gmail, ATS, uploads or Submit.

The original App in this run was an inert synthetic stand-in. Symlinks are rejected, so
real App bundles with symlinks need a separately reviewed preservation method. No installed
App identity, signature, permission behavior, interruption behavior, cross-version
compatibility, real application state or human acceptance is established. Lost historical
baselines remain unknown. This new baseline cannot retroactively certify an older run.

Verification also requires the original `sys.executable` path string and evidence
location because it matches the recorded command template. A different alias of the
same Python binary can return unverified; this does not authenticate interpreter bytes.
The parent observed and privately retained that conservative alias rejection, then
independently verified the documented locked uv invocation. Portable verification after
interpreter-path changes or archive relocation is not established by this demonstration.
