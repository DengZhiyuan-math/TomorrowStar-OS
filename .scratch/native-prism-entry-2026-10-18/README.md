# Native local LaTeX review entry

The fixed helper reads the dedicated local review configuration and returns one safe JSON line. It validates the configuration file, reuses the existing Prism source and instance validators, and connects only to an already running project. It does not compile, approve a résumé, or create or resume a job task.

The App invokes the bundled helper with isolated Python. The native UI uses the fixed configuration location; a test-only CLI option accepts synthetic configuration paths. Success returns `status`, a verified local editor URL and a generic title. Errors return a readable generic message without private source paths, contents, tokens or tracebacks.

The bundle inventory explicitly copies and hashes the three native helpers. Installed Resources loads its review engine only from `system/src`. Missing engine files fail closed. Checkout execution can use the sibling source tree only from the `macos` directory.

## Validation

- Initial missing-helper behavior: RED then GREEN.
- Explicit native resource copy: RED then GREEN.
- Incomplete package with an ambient engine: RED then GREEN.
- Final helper, package and Prism regression: **44 passed in 8.29 seconds**.
- Ruff check, format check and diff whitespace check passed.
- Tests cover the fixed default location, relocated complete packages, invalid configuration, unavailable services, safe error output and no build or state writes.

The pre-fix package is retained by the parent and is not an installation candidate. The parent owns the successor package, real configuration readback and native menu acceptance. These source tests do not establish installed App acceptance. Real applications remain paused.

`verification.json` records source hashes. `evidence-manifest.json` binds these evidence files. Earlier logs are retained unchanged.
