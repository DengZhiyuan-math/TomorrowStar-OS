# Saved PDF receipt across backend process death

Date: 2026-10-20

Support for [诊断原生会话中断并验证阶段恢复](../single-job-application-flow-2026-10-16/issues/27-native-interruption-recovery.md).
The ticket remains open under its existing assignee. No acceptance checkbox changes.

## Implemented verification

[Process-boundary regression](../../tests/test_pdf_recovery_process_boundary.py) adds a
boundary not covered by the existing same-interpreter close race or killed-analysis test:

1. Create a synthetic task and reviewed draft through ApplicationFlowService and
   ApplicationResumeStore. One synthetic model call creates the draft.
2. Reopen the flow in a separate backend Python process. Its exporter invokes a
   bounded child process that copies the existing synthetic PDF fixture and exits.
3. After export_for_draft returns a completed durable receipt, hold its callback
   before flow adoption. Only then SIGKILL that backend and observe its signal exit.
4. Reopen through ApplicationFlowService. The same inputs, draft, review and export
   attempt remain. Recovery records the interrupted attempt. No PDF is adopted and
   no material approval or worker exists. Snapshot reads do not repeat work.
5. Retry is blocked until explicit receipt reconciliation. Rechecking adopts the
   original attempt without model/export callbacks. Saved draft, source and PDF
   bytes remain unchanged, as does recovery history.

Injected renderer and model configuration snapshots are explicitly replayed across
processes. They do not establish real renderer identity or provider availability.
All children finish before the saved-receipt barrier, and the backend is reaped
with a five-second bound. Failure cleanup targets only the test-created process.

## Verification

Use a writable cache because the default uv cache is inaccessible in this session:

```sh
UV_CACHE_DIR=/private/tmp/tomorrowstar-recovery-uv-cache uv run --locked --offline --no-sync python scripts/run_pytest.py -q tests/test_pdf_recovery_process_boundary.py tests/test_pdf_export_shutdown_race.py tests/test_preparation_recovery_process.py
```

Result: **7 passed in 10.50s**. Final edited test rerun: **1 passed**.
Ruff check, Ruff format check and scoped diff whitespace check passed.
No production changes were needed. This is added passing coverage, not a reproduced
product failure. Initial setup failures (inaccessible default cache, catalog field
name and intentionally unstable injected configuration across processes) were test
harness errors and were corrected; they are not product RED evidence.

## Remaining acceptance

This test uses a fixed synthetic PDF copier. It does not run an installed native
window, its parent EOF shutdown, a real PDF compiler, Chrome or Prism. It does not
interrupt a still-running compiler child or prove its termination/ownership.
The original historical interruption remains unexplained. The installed native
in-flight compiler experiment and its precise process ownership/barrier remain
necessary, separately from this saved-result-before-adoption boundary. The full
backend suite and complete installed acceptance were not run by this support task.

No native App launch, installation, TCC operation, private data, network, model
provider, Gmail, ATS, real application, commit or remote write occurred.
