# Phase 05 private JD intake

This directory contains only public, content-free contracts. It must never contain a real job description, company fixture, raw source hash, accepted packet, score, route, or evaluation result.

Private runtime data is written only under the ignored `/.career-evidence/phase-05/` workspace. The `jd prepare` seam accepts exactly one pasted UTF-8 source or one regular local file and one separately recorded proposal JSON. It validates the exact source bytes, SHA-256 binding, and every requirement span, but does not accept, score, route, or call a model.

`max_raw_jd_bytes` defaults to `262144`. Exactly that many bytes proceed to normal validation; one byte more fails as `jd-source-too-large` before any write.

`jd accept` requires the exact prepared source hash, proposal hash, and explicit `--accept`; it creates a separate immutable accepted packet and never changes the prepared record. `jd inspect --expect` is read-only. Its five expectations are `prepared-exact-three`, `accepted-corpus-and-graph`, `existing-evaluation`, `sealed-blind-review`, and `finalized`; an unmet expectation emits its structured expected/actual state and exits with status 2.

Plan 05-03 is the explicit D-20 checkpoint for user-supplied fixture material. Do not create or substitute a JD before then.
