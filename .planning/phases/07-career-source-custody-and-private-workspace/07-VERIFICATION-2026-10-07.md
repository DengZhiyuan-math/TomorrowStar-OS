# Phase 7 independent verification — 2026-10-07

Verdict: **passed** for the current single-user local source-custody contract.

This review applies to the active MVP simplification addendum and the later
captured-source successor clarification. The historical verification against the
removed custody architecture remains historical evidence.

## Verified boundary

- Each operation receives an explicit private-workspace argument. Worktree root
  and Git common-directory checks reject the public checkout, its ancestors and
  descendants, and worktrees sharing its Git storage.
- Raw writes require effective ignore rules and an empty raw-vault Git index.
  Source IDs and ordinary symlink/path checks prevent obvious escapes.
- The registry retains availability, cutoff, Source type, capture time and content
  hash. Captures remain create-only. Derived mappings record caller-supplied
  provenance and do not generate derived text.
- Source snapshots verify referenced raw bytes. Captured-source successors preserve
  the parent registry and caller-supplied Source type. Published successors freeze
  ordinary base-registry capture/mapping writes before side effects.
- Routine status/errors are content-free. Explicit detached snapshots are
  data-bearing internal handoffs and must stay in the selected private context.
- The module creates candidate provenance only. It creates no Experience
  acceptance, Contribution, Skill, assessment, mastery, or JD decision.

## Finding and repair recheck

The initial implementation required a reason for every unavailable Source,
although the active addendum makes that field optional. The implementation now
allows omission. An explicitly supplied reason must be a nonempty string for an
unavailable Source. An available Source must omit the field, including explicit
null. Independent synthetic probing and the added regressions confirm this repair.

The dated addendum and architecture now describe captured-source successors.
They preserve the earlier implementation note as historical evidence.

## Validation

Checkout-bound command:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/run_pytest.py -q -p no:cacheprovider tests/test_career_source_custody.py tests/test_career_source_security.py
```

Result: **50 passed**. All test inputs were synthetic temporary workspaces.
The independent optional-unavailability-reason probe also passed.

## Limits

This is a local, single-user verification. It does not certify Git history or
remote visibility, backup/encryption, adversarial concurrent writers, TOCTOU
resistance, existing-source recapture, or a migration/cleanup protocol.

Inventory acceptance and subsequent capability assessment remain separate gates.
Passing this source-custody review does not accept or seal a personal inventory.
No external publication, repository staging/commit, or personal-record mutation
was performed by the independent reviewer.

## Exact reviewed public inputs

| Public relative path | SHA-256 |
| --- | --- |
| `src/career_evidence_graph/workspace.py` | `sha256:45cfd17906e61e98738322b711586990b17c37f3818623421fb211ce05892d0d` |
| `src/career_evidence_graph/validation/hashing.py` | `sha256:ac6486aa977ba5634a10759cbba0d9e177667b6a76d72f8d3c53eb3d9977ce0b` |
| `src/career_evidence_graph/validation/store.py` | `sha256:1b20e91d26469be9d60da57bad77b220045f602d07d9704895c070b65ee89e34` |
| `src/career_evidence_graph/domain/models.py` | `sha256:b6693ecb5b045bb9678094d2c8a829bb00e1e1b1183504326cab154d81334043` |
| `src/career_evidence_graph/cli.py` | `sha256:f474bbf9a73a1d59ff6653621b2d8c7644612c5cc2e52c7e8a38ca49cdedcbf0` |
| `tests/test_career_source_custody.py` | `sha256:1f33d5bbd8471d14260d56f316f70c89f8ca9658f33a1dc19037d3c0f9a65a37` |
| `tests/test_career_source_security.py` | `sha256:dc56ad979fc9825c390e61a52a19b611cffc82870cf24836f2367d52f4ec47ae` |
| `scripts/run_pytest.py` | `sha256:ac854238b3687f729a96f46ca5771b5166a7ccc958a380a5a0adb3a99e20fe99` |
| `.planning/phases/07-career-source-custody-and-private-workspace/07-MVP-SIMPLIFICATION-ADDENDUM.md` | `sha256:e25bf3b10cc1e6dfecb0a17420a038ccc4564b3fa2aadbe102b2eab45def2e4b` |
| `docs/data-boundaries.md` | `sha256:154799bd807d0cc72304c028c22587dd367b1f3b2f4837e0700edd8ad98a0796` |
| `ARCHITECTURE.md` | `sha256:ba4bc5bb8995b780ab806551e5328399a2b1f3995888066cd1db26f889788e9d` |
