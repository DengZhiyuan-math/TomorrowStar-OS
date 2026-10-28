# Application automation handoff verification — 2026-10-09

Delivery scope: one saved application note → review-only Codex Job Apply task.
Browser execution belongs to the externally installed plugin. The user performs
the final live Submit/Send action. No real application was filled or submitted
in this verification, and the normal applicant profile store was not initialized.

Follow-up: [three synthetic replay rounds](three-rounds-01/README.md) completed
two full Lever/Greenhouse journeys and one expected missing-answer rejection.
The original interrupted result below remains unchanged.

## Results

| Check | Result | Evidence boundary |
| --- | --- | --- |
| Plugin installation | Job Apply `1.1.0` installed through the Codex plugin CLI | Marketplace HEAD was `370204c58b1137d08c5a7e7449538ae6447be0b9`; both skill files, helper and manifest matched the independently checked-out pin |
| Focused task/HTTP contracts | 72 passed | Synthetic temporary notes; stale revision, duplicate identity, unsupported link, state, CSRF and no-write checks |
| Complete system offline suite | 650 passed, 1 deselected | Current checkout launchers; 121.45 seconds; not live ATS acceptance |
| Pinned plugin Python suite | 308 passed | `python3 -B -m unittest discover -s tests -q`; 97.285 seconds; no personal data |
| Static checks | Passed | Ruff check and format check; JavaScript syntax; Git whitespace checks |
| Portal browser journey | Passed | Synthetic draft task generated; clipboard contained the skill invocation; unsaved input cleared the task; preparation was refused for an applied record |
| Relocated bundled App | Passed | New build's `acceptance.json`: review-only handoff, runtime, signature before/after reads, state retention, Host/CSRF and shutdown |
| Lever browser replay | Incomplete/failed | Required fields and synthetic resume were filled; filename matched; final action remained untouched. Browser session was interrupted before review and correlated lifecycle completion |
| Live ATS receipt and success rate | Not tested | No real applicant data sent and no real Submit action |

[Portal screenshot](portal-handoff.jpg) shows synthetic data only.
[Interrupted replay](lever-interrupted.json) preserves the upstream oracle's
failed assertions. The replay was evaluated in that state. Its helper then
sanitized temporary synthetic data and stopped the fixture server. The failure
was not rewritten as successful acceptance.

The App was built at `build/macos/application-automation/TomorrowStar.app`.
The existing release and installed App were not replaced. Open this new build
or run the checkout portal to use the new entry. Its relocated backend acceptance
does not establish native-window clipboard behavior or live form completeness.

## Commands

```sh
uv run --locked python scripts/run_pytest.py \
  tests/test_application_automation.py tests/test_career_portal_http.py -q
uv run --locked python scripts/run_pytest.py -q
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check src/career_evidence_graph/portal_static/app.js
git diff --check
uv run --locked python macos/build.py \
  --output build/macos/application-automation/TomorrowStar.app
uv run --locked python macos/verify.py \
  --app build/macos/application-automation/TomorrowStar.app \
  --report build/macos/application-automation/acceptance.json
```

This sandbox required `uv --cache-dir /private/tmp/tomorrowstar-uv-cache` because
the ordinary uv cache was not writable. This changed only the test cache location.
See [the integration guide](../../../docs/application-automation.md) for use,
upstream provenance and private-data boundaries.
