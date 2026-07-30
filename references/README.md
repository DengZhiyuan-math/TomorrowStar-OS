# Open-Source Reference Baseline

This directory pins the open-source projects that inform the first Career Evidence Graph validation project. They are upstream references, not runtime dependencies and not evidence that their complete architecture should be copied.

Clone them with:

```bash
git submodule update --init --recommend-shallow
```

## Pinned upstreams

| Reference | Pinned commit | License | Primary use |
|-----------|---------------|---------|-------------|
| [Tabiya Compass](https://github.com/tabiya-tech/compass) | `8470bea7f68d0990898f441a12bbb6a261a0ef34` | MIT | Experience exploration, responsibility separation, interview state, extraction/transition boundaries |
| [Matt Pocock Skills](https://github.com/mattpocock/skills) | `2ab958093e83e0ec752e6c1c5932da465bf23e0c` | MIT | One-question-at-a-time grilling, domain-language clarification, evidence-before-questioning discipline |
| [MIND Tech Ontology](https://github.com/MIND-TechAI/MIND-tech-ontology) | `2367527d1a2f5665f595d6e0518294cc69dfb0fe` | MIT | Skill aliases, normalization, concepts, domains, tasks, and ontology relations |
| [CV Market Learning Planner](https://github.com/sangowu/cv-market-learning-planner) | `ea507847c7a42a1a54becc853fadd15506479b38` | MIT | Versioned career workspace, analysis history, deterministic helper scripts, gap and learning artifacts |
| [Hiring Agent](https://github.com/interviewstreet/hiring-agent) | `70fd3ea9aa74d8f76519ec643a99f9871003e70d` | MIT | Structured résumé parsing, Pydantic contracts, staged caching, role-specific evaluation and evidence explanations |
| [Resume Matcher](https://github.com/srbhr/Resume-Matcher) | `ad7754c8b2c3ecee21314ee0b49b0e07d89e3e09` | Apache-2.0 | JD-tailored résumé interaction, layouts, export pipeline, and downstream presentation patterns |

Each submodule preserves its upstream repository and license. Code copied or adapted into this project must retain the attribution and notices required by its license.

## Reuse matrix

### Tabiya Compass

**Adapt**

- Separation of conversational questioning, structured extraction, coverage auditing, and transition control.
- Experience types and explicit separation of the user’s responsibilities, non-responsibilities, and other people’s work.
- Resumable interview state and complete question/answer history.

**Do not inherit by default**

- Its complete frontend or deployment stack.
- Fixed informal-employment categories.
- Gemini-specific infrastructure.
- Occupation-first assumptions or top-skill ranking as a substitute for mastery assessment.

### Matt Pocock Skills

**Adapt**

- Ask one question at a time.
- Inspect available files and artifacts before asking the user.
- Challenge vague language and test concepts with concrete boundary cases.
- Maintain a canonical domain vocabulary as decisions become stable.

**Do not inherit by default**

- General engineering-planning workflows unrelated to career capability assessment.
- A plain conversation transcript as a substitute for structured Experience, Contribution, Skill, Evidence, and assessment entities.

### MIND Tech Ontology

**Adapt**

- Canonical names, aliases, common misspellings, technical domains, concepts, tasks, and explicit ontology relations.
- A versioned, read-only upstream snapshot behind an internal adapter.

**Do not inherit by default**

- Automatic propagation from `impliesKnowingSkills` to user mastery.
- The complete class hierarchy when a smaller internal Skill model is sufficient.
- Unpinned online updates.

### CV Market Learning Planner

**Adapt**

- Separation of current analysis from historical snapshots.
- Append-only reviews, deterministic helpers, progress snapshots, and explicit gap/learning artifacts.

**Do not inherit by default**

- A fixed learning-level model.
- Exercise generation as the center of the product.
- Any CV profile that lacks Contribution-level grounding.
- Free-form LLM gap scores without capability assessment.

### Hiring Agent

**Adapt**

- Pydantic-based structured extraction boundaries.
- Pipeline staging, intermediate-result caching, role configurations, and evidence-bearing explanations.
- Adversarial fixtures for unstable scoring, hidden text, and prompt injection.

**Do not inherit by default**

- GitHub activity as a privileged measure of skill.
- LLM-generated final scores without calibration and human-confirmable assessment basis.
- Hidden-text or repository-keyword signals that bypass Grill-Me.

### Resume Matcher

**Adapt later**

- JD input, tailored content review, résumé layouts, document export, cover-letter, and interview-preparation presentation patterns.

**Do not inherit by default**

- A master résumé as the sole source of truth.
- A flat résumé model without Experience → Contribution → Skill relationships.
- Keyword or presentation quality as a replacement for capability assessment.

## Integration rule

Before implementing a subsystem:

1. Identify the closest upstream reference.
2. Record the exact upstream file or pattern being considered.
3. Classify the action as `reuse`, `adapt`, `inspired-by`, or `reject`.
4. Confirm license obligations.
5. Add a local test that expresses this project’s distinct requirement.

The upstreams are evidence for design decisions, not authorities that override this project’s product model.

## Implemented provenance registry

The machine-readable source of truth is
`validation/provenance/registry.json`. These entries describe patterns actually
introduced in Phase 1; none claims verbatim copied code or data.

| Record ID | Classification | Pinned commit | Local subsystem | Local divergence |
|---|---|---|---|---|
| `cv-market-formal-history` | `adapt` | `ea507847c7a42a1a54becc853fadd15506479b38` | `formal-run storage and linked history` | Immutable directories, complete hashes, atomic publication, explicit parent links, and no overwrite/delete operation |
| `tabiya-run-store-boundary` | `inspired-by` | `8470bea7f68d0990898f441a12bbb6a261a0ef34` | `FormalRunStore directory-per-run boundary` | Reject overwrites and symlinks; validate manifests; expose no mutable save/delete API |
| `hiring-agent-validation-contracts` | `adapt` | `70fd3ea9aa74d8f76519ec643a99f9871003e70d` | `strict structured validation contracts` | Forbid unknown fields, retain formal history, hash full lineage, and prohibit résumé/repository-derived mastery |
| `hiring-agent-provider-port` | `adapt` | `70fd3ea9aa74d8f76519ec643a99f9871003e70d` | `Codex CLI provider process boundary` | Fixed shell-free argv, read-only sandbox, allowlisted environment, retained JSONL, redacted diagnostics, and snapshot-or-drift enforcement |

Codex CLI itself is an invoked runtime interface, not copied upstream source.
Its exact CLI version and model configuration are recorded per live run rather
than represented as a pinned source-code adaptation.
