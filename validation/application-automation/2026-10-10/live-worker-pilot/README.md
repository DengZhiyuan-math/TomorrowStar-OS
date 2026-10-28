# Supervised hosted ATS integration — 2026-10-10

The existing independent worker now has an explicit live mode for hosted Lever
and Greenhouse jobs. It reuses the queue, scoped answers, per-job PDF binding,
revision checks, controller lease and original-note writer. Synthetic mode
remains the default. No new dependency or model provider was added.

## Evidence boundary

| Check | Result | What it establishes |
| --- | --- | --- |
| Real Lever form, read only | Passed: 14 fields, 10 required, empty values and attachment | Current labels, URL and exact company/role title pass the hosted adapter identity check. |
| Real Greenhouse form, read only | Passed: 30 fields, 23 required, empty values and attachments | Current native/ARIA/grouped controls and non-S3 resume path pass inspection. |
| Scoped worker offline checks | 37 passed, 5 browser cases deselected | Queue/store contracts and live guards, including explicit incomplete-page handoff. |
| Complete default offline regression | 687 passed, 21 deselected; 524.32 seconds | Checkout launcher; excludes 20 browser cases and one live case. |
| Combined Lever / Greenhouse browser regression | 20 passed, 16 deselected; 155.46 seconds | Three-round replay, shared answers, dynamic controls, native multipart bytes, pause/recovery and manual handoff using synthetic data. |
| Real workbench browser check | Passed | Live banner, two separate empty PDF controls, disabled Start, no form error. The batch remains paused. |
| Ruff, JavaScript syntax and diff whitespace | Passed | Repository lint/format checks, `node --check` and `git diff --check`. |
| Personal-data filling or actual resume upload | Not run | Per-job PDFs and required answers are still awaiting user selection/confirmation. |
| Final submission or employer receipt | Not run | The user retains final Submit. No application-success claim is made. |

The live selector test fixtures use an offline browser context. Requests are
fulfilled locally only after the real guard decides. The runner reaches
`ready_for_review`, keeps the source note at `drafting`, then yields the page;
subsequent ticks preserve a manual edit. This is synthetic execution evidence,
not completion of either real application.

Earlier browser probes failed because the installed full Chromium was not
selected explicitly. A later runner probe exposed a duplicate route that
bypassed the context fixture and received a public GET error. Both were corrected.
The final combined run above passed. No personal values or real attachments
were involved in those failed probes.

## Public pages inspected

- A real Lever posting (company, role, location and URL kept in the private records). The form requires language levels, start date, work authorization, source and a short motivation. These answers were not inferred.
- A real Greenhouse posting (company, role, locations and URL kept in the private records). Required answers include education, internship timing, location, sponsorship and motivation. These answers were not inferred.
- [Lever public posting API](https://github.com/lever/postings-api) and [Greenhouse Job Board documentation](https://docs.greenhouse.io/job-board.html) were used for platform context. Hosted-page DOM and attachment behavior were inspected separately.

Inspection ran through the connected browser CLI. The source-owned DOM reader
did not fill a field, choose a file, click Submit or execute page-provided code.
Exact URL and title checks were then run against those read-only captures.
The temporary inspection tab was closed; prior preview pages were retained.
Private notes, applicant records, resume paths, answers, screenshots and source
fingerprints are excluded from this report.

## Bounded sending and remaining limits

Before handoff, the live browser context blocks final application requests.
It allows bounded reads and the Lever native resume parser POST only when its
multipart body contains accountId and the selected PDF with matching SHA-256.
Greenhouse's inspected non-S3 form keeps the attachment local until manual
submission. React file-input replacement is supported; the replaced control
provides a filename, not file bytes. The checkpoint records the worker's local
selection. A subsequent user selection of a different same-name file cannot
be detected from that filename alone.

S3 pre-upload, extra required attachments, ambiguous dynamic choices and
unverified form variants pause the affected job. Authentication and challenge
handling stay manual. Incomplete-page handoff requires an explicit user action
and excludes that page from further worker ticks until explicit recheck.
Restart does not promise DOM recovery. Unknown upload or submission outcomes
must not be retried automatically.

See [operation guide](../../../../docs/live-application-worker.md).

## Commands

```sh
uv run --locked python scripts/run_pytest.py -q
uv run --locked python scripts/run_pytest.py -q -m worker_browser \
  tests/test_lever_worker_browser.py tests/test_greenhouse_worker_browser.py tests/test_hosted_ats.py
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check src/career_evidence_graph/portal_static/worker.js
git diff --check
```

`source-manifest.json` hashes only source code and synthetic tests. No private
application state is included. Historical preview evidence remains unchanged.
