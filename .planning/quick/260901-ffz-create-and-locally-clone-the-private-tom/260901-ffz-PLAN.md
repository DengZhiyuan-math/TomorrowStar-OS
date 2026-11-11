---
quick_id: 260901-ffz
mode: quick
status: planned
description: Create and locally clone the private tomorrowstar-career-data repository with a minimal safe career-source workspace scaffold
files:
  - /Users/zhdeng/Documents/tomorrowstar-career-data/README.md
  - /Users/zhdeng/Documents/tomorrowstar-career-data/.gitignore
  - .planning/quick/260901-ffz-create-and-locally-clone-the-private-tom/260901-ffz-SUMMARY.md
  - .planning/STATE.md
---

# Quick Task 260901-ffz Plan

Create `DengZhiyuan-math/tomorrowstar-career-data` as a private GitHub repository and clone it to `/Users/zhdeng/Documents/tomorrowstar-career-data`, separate from the public TomorrowStar OS checkout.

## Task 1: Create the private repository and verify its boundary

- Confirm the authenticated GitHub owner, the absence of an existing remote repository, and the absence of the intended local path.
- Create the repository with private visibility and clone it to the exact sibling path.
- Verify GitHub reports `PRIVATE`, the local `origin` points to the intended repository, and the checkout is not the same as or nested within the public repository.

## Task 2: Add the minimum safe workspace scaffold

- Add a concise README that states the repository is private career-source custody, that registry entries are candidate-only until later review, and that no source presence creates Skill or mastery authority.
- Add `.career-evidence/raw/` to `.gitignore` so captured source bytes cannot be committed accidentally.
- Do not create `.career-evidence/registry.json` yet: the current API is create-only, so the first declaration must contain the user's real cutoff, categories, sources, and availability decisions rather than placeholders.
- Commit and push the scaffold to the private repository.

## Task 3: Verify readiness without claiming inventory or graph completion

- Run `open_private_workspace` against the new checkout and verify the private/public separation contract.
- Verify the ignored raw-vault rule and remote visibility.
- Record that no personal career data, source registry, capture, Phase 8 inventory acceptance, Skill assessment, or mastery claim has yet been created.

## Done

The private repository exists on GitHub, is cloned locally at the exact sibling path, contains only the minimal privacy/authority scaffold, and is ready for the user's first real source-universe declaration and capture.
