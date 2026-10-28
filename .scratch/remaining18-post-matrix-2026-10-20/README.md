# Installed policy at the POST boundary

This is synthetic engineering evidence for the existing installed-write policy
ticket. The original owner and acceptance gates remain unchanged.

The added coverage exercises the loopback `POST /api/flow/worker-action` endpoint
using the existing synthetic installed-portal fixtures. Exact historical worker
compatibility permits explicit resume of the retained worker. Pre-existing
configuration inequivalence, missing allowlist evidence, an undeclared resume
command, missing basis, and a different source with the same version label deny
the request before business writes. Each denial preserves the retained worker.

See [the tests](../../tests/test_installed_policy_post_boundary.py) and the
[Boolean-only result](result.json). The production compatibility allowlist remains
empty. No native App, browser, permission grant, installation, provider, or real
application operation was performed. The ticket remains open for its installed
acceptance gates.

Verification uses checkout launchers with `--locked --offline --no-sync`:

```text
python scripts/run_pytest.py -q tests/test_installed_policy_post_boundary.py tests/test_installed_admission_matrix.py tests/test_installed_write_admission_http.py
ruff check --no-cache tests/test_installed_policy_post_boundary.py
ruff format --check --no-cache tests/test_installed_policy_post_boundary.py
```
