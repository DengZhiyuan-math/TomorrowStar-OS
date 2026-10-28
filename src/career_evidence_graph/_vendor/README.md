# Job Apply storage helper

- Upstream: https://github.com/neonwatty/job-apply-plugin
- Revision: `370204c58b1137d08c5a7e7449538ae6447be0b9`, plugin 1.1.0.
- Source: `scripts/job-apply-store.py`.
- License: MIT, retained in `JOB_APPLY_LICENSE`.
- SHA-256: `aeff412145497a87929c04b712a2f87bf4521256c67c98f6b4bc0271c5655d03`.
- Local divergence: none; the filename is changed for Python import.

The worker adapter supplies an explicit private root, prevents legacy import,
serializes writes, checks actual answer scopes and binds content revisions.
It does not modify the installed plugin or inherit its final-action policy.
