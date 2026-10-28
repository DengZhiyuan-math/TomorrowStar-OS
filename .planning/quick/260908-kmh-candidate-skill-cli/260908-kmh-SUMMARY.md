---
quick_id: 260908-kmh
phase: quick-260908-kmh
plan: "01"
status: complete
---

# Candidate Skill CLI Summary

`career-evidence audit start` now accepts `--experience-candidate-id` and
`--candidate-skill-links <json-array>`. The CLI validates each link through
the existing strict Candidate Skill Link contract and delegates to the existing
audit workflow; no-candidate behavior is unchanged.

Verification passed: focused CLI/harness tests, Ruff lint/format, `git diff
--check`, and the full locked offline test suite. No private data, extractor,
or new storage path was added.
