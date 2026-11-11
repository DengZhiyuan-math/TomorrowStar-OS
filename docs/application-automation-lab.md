# Automated application lab

## Scope — 2026-10-20

This is an explicit development and synthetic-replay entrypoint. Daily product
behavior is defined by the [single-job flow](single-job-flow.md); changes are
ordered in the [development plan](development-plan.md). The lab's fresh runtime,
fixture isolation, historical reservations and request grants do not define
product approval steps, platform eligibility or recovery behavior.

The product handles jobs sequentially and stops at the current job for an
important missing fact, actual conflict or unknown result. Only mail ingestion
may continue while waiting. It reuses login state, facts and usable materials,
supports one-click continuation after manual edits and resumes normal work after
reopen. Final Submit stays manual; the system records a clear result automatically.
This document update does not run the lab or authorize a new real-site experiment.

## Daily applications and the explicit lab lane

Daily applications use **自动申请**, not this lab: the system reads recommendation
mail or organizes a pasted JD/job URL, calculates the match, generates and checks
complete materials, then fills and uploads. The user supplies important missing
facts once and performs final Submit on the original site. There is no routine
request to provide a résumé PDF or approve a generated draft.

The explicit lab still uses `WorkerService`, the browser runner, answer storage
and `ApplicationResumeStore`. Its standalone **生成岗位简历草稿**, generated/file
PDF selector and draft-review checkbox remain compatibility/development controls.
That generation call uses the old short résumé/HTML export path; it is not the
default complete LaTeX path. A server with a Flow disables the standalone worker
API and its batch preparation UI. The lab is therefore not a second default
application scheduler. Retain an old active owner, page, attachments and unknown
attempts; switching the displayed page does not transfer execution ownership.

The [source call and retention map](../.scratch/ticket39-41-source-2026-10-21/materials-entrypoints.md)
lists the current shared and retained branches. No lab, App update or real
application is authorized by these instructions; the current pause remains.

The native source now defaults to the [single-job workspace](single-job-flow.md),
which reuses WorkerService, the browser runner and native driver. This page retains the separate experimental entrypoint
and historical diagnostics. Installed-window and real-job acceptance are tracked
in the single-job guide's execution map.

The lab must use a fresh private runtime. Do not reuse or migrate the installed
`application-worker` directory, its `run.json`, browser profile, answer library,
or old test evidence. Codex handoff and automated worker roots must be separate.

Run an offline preflight from this checkout:

```sh
uv run --locked python scripts/run_application_automation_lab.py \
  --runtime /private/tmp/tomorrowstar-automation-lab-NEW \
  --evidence /absolute/path/to/previous/final-report.md
```

This creates a private, unique JSON report with hashes of supplied evidence. It
does not start native tools, a browser, a model, or ATS traffic. The original
files remain unchanged. This records the known diagnostic boundary; it does not
probe current TCC permissions or certify current native availability.

Explicit synthetic execution is available with `--run-synthetic`,
`--applications /absolute/path/to/synthetic-applications` and
`--fixture-origin http://127.0.0.1:PORT`. It retains the worker's existing request,
upload and no-final-submit guards. The default synthetic browser is headless;
`--cua` explicitly selects the existing native runner. Only use fixture job
records with that mode. There is no live ATS or provider option in this launcher.
Prepare and control the resulting worker through the existing experimental
portal API, using the same runtime and synthetic applications root.

For explicit desktop development, `macos/server.py --automation-lab` enables
the old automated path with a new `application-automation-lab` default root.
That switch retains the existing live worker capabilities and therefore needs
separate authorization for real-site testing. The installed package and running
instances are not changed by checkout edits or offline preflight.

## Existing lab ownership and recovery implementation

Both updated execution paths share persistent reservations under the selected
application store. Reservations bind an application ID, execution lane and
stable task/batch owner. Another owner cannot overwrite or release a claim.
Reservations do not expire. A crash or unknown page/action outcome keeps the
reservation. Cancellation alone cannot release an open page or unresolved
intent. After explicit page release and action settlement, a cancelled automated
job may release its reservation. Replaced batches preserve their old records.

Legacy worker jobs can reserve their original batch at resume/start only if no
other executor holds the application. Browser authorization requires exact
ownership. An already installed old binary does not contain this new check;
stop its application automation before using the updated handoff against the
same records. A filesystem claim cannot retrofit enforcement into old code.

## Historical native blockers retained

The previous native suite stopped before its intended form interactions: the
default driver failed background attachment admission, and the reviewed driver
could not prove LaunchServices process ownership for the new isolated profile.
The next diagnostic must capture the same launch's returned PID, actual argv,
target profile and exit status. Keep the profile guard. Do not interpret this as
proof of a new product defect, a current TCC failure, or complete driver failure.

After launch ownership is established, align the legacy tests' window state,
second-origin scope, `list_windows` permission and daemon diagnostic fields.
Original failures, diagnostic profiles and failed-run reports remain evidence;
append successor results instead of rewriting them.
