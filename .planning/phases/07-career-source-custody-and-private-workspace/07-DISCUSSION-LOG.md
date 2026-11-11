# Phase 7: Career Source Custody and Private Workspace - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-29
**Phase:** 7-career-source-custody-and-private-workspace
**Areas discussed:** Public/private workspace boundary, full-career source universe, clue/fact/evidence authority, raw-source capture and transformation lineage

---

## Private Workspace and Public/Private Boundary

### Product direction

| Option | Description | Selected |
|--------|-------------|----------|
| Resume-first graph | Infer the authoritative Skill graph from an existing resume. | |
| Skill-first product | Build and verify the Skill graph first, then use it to produce JD-targeted resumes. | ✓ |

**User's choice:** Skill-first product.
**Notes:** The assistant initially framed resumes as a representative graph-building source. The user corrected the direction: resumes are downstream outputs, not graph authority. Existing resumes may later be used only as non-authoritative omission clues.

### Existing resume role

| Option | Description | Selected |
|--------|-------------|----------|
| Exclude existing resumes | Never use an existing resume during discovery. | |
| Discovery clue only | Let resume statements nominate candidates, but require regrounding and later review. | ✓ |

**User's choice:** Discovery clue only.
**Notes:** Resume wording cannot establish completeness, responsibility, mastery, or evidence confidence.

### Skill, Experience, and evidence philosophy

| Option | Description | Selected |
|--------|-------------|----------|
| Experience-first | Treat projects, education, and employment as the person's primary career identity. | |
| Skill-first with evidence grounding | Treat Skills as the core asset and Experiences as acquisition, application, context, or persuasion paths. | ✓ |

**User's choice:** Skill-first with evidence grounding.
**Notes:** Stronger wording organizes confirmed truth. New inspectable work can create new Evidence; wording by itself cannot.

### Private repository contents

| Option | Description | Selected |
|--------|-------------|----------|
| Layered private repository | Track readable graph/resume/manifests in private Git; keep exact sensitive bytes in an ignored raw vault. | ✓ |
| Commit all raw sources | Put graph, resumes, manifests, and exact raw sources into private Git history. | |
| Thin private repository | Track only graph and resumes; keep all custody records outside Git. | |

**User's choice:** Layered private repository.
**Notes:** The raw vault needs a separate encrypted backup policy; raw bytes do not enter Git history.

### Public harness connection

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit workspace path | Pass the private repository path to each operation. | ✓ |
| User-level default | Persist a machine-level default path with CLI override. | |
| Git submodule | Couple the public and private repositories through Git. | |

**User's choice:** Explicit workspace path.
**Notes:** The public repository stores no private path, remote URL, submodule, or implicit current workspace.

### Public-repository fingerprints

| Option | Description | Selected |
|--------|-------------|----------|
| Ban all private-derived artifacts | Publish no real hashes, IDs, counts, paths, reports, or logs. | ✓ |
| Allow irreversible fingerprints | Permit hashes, opaque IDs, and aggregate counts. | |
| Individually approved summaries | Permit explicitly approved anonymized evaluation summaries. | |

**User's choice:** Ban all private-derived artifacts.
**Notes:** Public tests and examples must be wholly synthetic.

### Private readability and routine output

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit reveal gate | Keep normal views content-free and require an explicit reveal action. | |
| Readable private views | Let private graph/source/report views show content while routine status, logs, and errors remain content-free. | ✓ |
| Always content-free | Never render private labels or excerpts through the tool. | |
| Rich routine logs | Let routine status, logs, and errors show private content. | |

**User's choice:** Readable private views with the minimum INV-07 boundary.
**Notes:** The user preferred shipping the readable private workflow first and adding stronger privacy later. Rich routine logs were rejected because they conflict with INV-07. Encryption, reveal confirmations, permission hardening, and leak scanning were deferred; content-free status/log/error behavior was not deferred.

---

## Full-Career Source Universe

### Registry organization

| Option | Description | Selected |
|--------|-------------|----------|
| Two-level registry | Use category coverage to detect omissions and logical source entries for custody. | ✓ |
| Fully Skill-first source declaration | Start only from known Skills and list sources under them. | |
| Flat source list | Register sources without career-category coverage. | |

**User's choice:** Two-level registry.
**Notes:** The registry is a completeness control, not the product's conceptual center. Sources may support multiple Skills and the downstream experience remains Skill-first.

### Unsupported recollection

| Option | Description | Selected |
|--------|-------------|----------|
| `self-reported` source | Preserve remembered facts as candidates without treating them as independent corroboration. | ✓ |
| Wait for external material | Do not register the item until another source is found. | |
| User confirmation is ordinary Evidence | Treat explicit recollection as equivalent to independent evidence. | |

**User's choice:** `self-reported` source.
**Notes:** This prevents older or undocumented Skills and Experiences from disappearing without letting self-report inflate mastery or assessment confidence.

### Cutoff semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Career-fact cutoff plus capture times | Bound the career events in scope and record each source's acquisition time separately. | ✓ |
| Acquisition freeze | Define the revision only by which sources were collected before a timestamp. | |
| Rolling inventory | Keep one mutable current inventory without a reproducible cutoff. | |

**User's choice:** Career-fact cutoff plus capture times.
**Notes:** Later discoveries about earlier career history create linked revisions rather than rewriting old ones.

### Unavailable-source reasons

| Option | Description | Selected |
|--------|-------------|----------|
| Structured status plus explanation | Distinguish temporary, permanent, restricted, never-created, unknown, and declined sources. | ✓ |
| Single unavailable flag | Keep one state with a free-text note. | |
| Free text only | Record no normalized availability state. | |

**User's choice:** Structured status plus optional explanation.
**Notes:** Unavailable declarations remain visible in coverage reports and are never silently omitted.

---

## Clue, Fact, Evidence, and Assessment Authority

### Strong Skill with weak external proof

| Option | Description | Selected |
|--------|-------------|----------|
| `claimed-unverified` Skill | Keep the Skill and self-assessment visible while separating it from reviewed mastery. | ✓ |
| Hide until external evidence exists | Do not create the Skill before a project, credential, or other artifact exists. | |
| Provisional formal mastery | Let self-rating participate in matching and resume generation. | |

**User's choice:** `claimed-unverified` Skill.
**Notes:** The user rejected any interpretation that equates self-study or lack of official records with lower capability.

### Capability, confidence, and persuasion

| Option | Description | Selected |
|--------|-------------|----------|
| Three independent meanings | Separate mastery, assessment confidence, and market proof strength. | ✓ |
| Two meanings | Keep only mastery and evidence confidence; leave recruiter persuasion outside the model. | |
| Credential-weighted capability | Let institutional records increase mastery directly. | |

**User's choice:** Three independent meanings.
**Notes:** Formal courses and credentials prove neither independence nor mastery. Observable performance can verify a self-taught Skill directly.

### Direct capability verification

| Option | Description | Selected |
|--------|-------------|----------|
| Skill-specific high-intensity examination | Use relevant explanation, implementation, debugging, transfer, reproduction, decision, or operation probes. | ✓ |
| Oral questioning only | Assess through explanation and follow-up without applied work. | |
| External project required | Require portfolio work before any formal mastery can exist. | |

**User's choice:** Skill-specific high-intensity examination.
**Notes:** The desired system resembles a demanding self-exam for interviews and real work, not a credential check.

### Examination blueprint

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic-Skill blueprint with realistic compound questions | Start coverage from individual Skills, source real hiring material, and assemble multi-Skill questions. | ✓ |
| Resume-claim interview | Drive questions primarily from claims already written in a resume. | |
| Generic question bank | Ask broad questions without explicit Skill coverage. | |

**User's choice:** Atomic-Skill blueprint with realistic compound questions.
**Notes:** The future engine should collect provenance-bearing real interview questions, interview-experience reports, and representative work tasks. This capability is outside Phase 7.

### Multi-Skill attribution

| Option | Description | Selected |
|--------|-------------|----------|
| Primary and co-assessed Skills separately | Store separate observations, anchors, evidence, and proposals for every Skill. | ✓ |
| One question score with weights | Score the whole answer, then distribute the result. | |
| Primary Skill only | Keep other observed capabilities as narrative feedback only. | |

**User's choice:** Primary and co-assessed Skills separately.
**Notes:** Cross-Skill performance may be reported, but it cannot replace individual mastery.

### Examination admission

| Option | Description | Selected |
|--------|-------------|----------|
| Review proposals before admission | Let the user correct, accept, or reject per-Skill proposals before they become reviewed user truth. | ✓ |
| Automatic mastery update | Write examination scores directly into the graph. | |
| Separate practice-only report | Never connect examination evidence to the graph. | |

**User's choice:** Review proposals before admission.
**Notes:** This preserves one assessment authority and avoids a duplicate exam-score engine.

### Existing interview workflow reference

| Option | Description | Selected |
|--------|-------------|----------|
| Inspiration only | Borrow narrow questioning patterns but design a new Skill-first comprehensive engine. | ✓ |
| Adopt as the engine | Use the installed resume-driven interview workflow as the system architecture. | |

**User's choice:** Inspiration only.
**Notes:** The user judged the existing interview workflow too weak for this system. Its resume-driven entry point is specifically rejected.

---

## Raw-Source Capture and Transformation Lineage

### Immutable original by source type

| Option | Description | Selected |
|--------|-------------|----------|
| Source-type-specific capture | Preserve exact bytes, pinned Git identities, time-bound exports, or timestamped records as appropriate. | ✓ |
| Unified text first | Convert all material to Markdown/JSON before retaining it. | |
| External locator only | Keep paths and URLs without capturing immutable content. | |

**User's choice:** Source-type-specific immutable capture.
**Notes:** Capture mechanics differ; source prestige and format have no mastery weight.

### Logical source and capture history

| Option | Description | Selected |
|--------|-------------|----------|
| Stable `source_id` plus immutable `capture_id` | Link recaptures without overwriting history. | ✓ |
| New source for every update | Treat each version as unrelated. | |
| Overwrite current source | Keep only the latest bytes and metadata. | |

**User's choice:** Stable logical identity plus immutable captures.
**Notes:** Every current selection is explicit and historical graph/exam/resume results remain reproducible.

### Transformation trace depth

| Option | Description | Selected |
|--------|-------------|----------|
| Complete chain plus precise locator | Retain input, transformer identity/version/configuration, output hash, and page/line/byte/blob locator. | ✓ |
| Input/output hashes only | Retain content identity without transformation details or exact origin. | |
| Extracted text only | Discard reconstructable transformation history. | |

**User's choice:** Complete chain plus precise locator.
**Notes:** Whole-source support is an explicit fallback. Transformation output remains a candidate without truth or mastery authority.

### Duplicate material

| Option | Description | Selected |
|--------|-------------|----------|
| Deduplicate content, preserve source identities | Prevent evidence multiplication while retaining distribution and independence information. | ✓ |
| Merge duplicate sources | Remove duplicate content and its separate source identities. | |
| Count every occurrence | Treat every repeated presentation as new Evidence. | |

**User's choice:** Deduplicate content while preserving every source identity.
**Notes:** Repetition may affect market reach, but it cannot mechanically raise mastery or assessment confidence.

---

## the agent's Discretion

- Exact model, field, command, and semantic namespace names.
- Exact deterministic source-adapter protocol and initial supported formats, constrained to the actual private corpus.
- Exact safe identifier and diagnostic-code syntax.
- Exact read-only private inspection layout.

## Deferred Ideas

- Design a dedicated Skill-first comprehensive examination engine and revise or extend the later roadmap phases before implementation.
- Build the ASu-inspired truthful positioning and evidence-producing work loop after confirmed Skills exist.
- Generate JD-targeted resumes only from confirmed graph truth and separate market-proof state.
- Add stronger permissions, explicit reveal confirmation, leak scanning, encryption, backup, and recovery after the minimum INV-07 boundary is operational.
