# Pitfalls Research

**Domain:** v1.1 full-career evidence graph and real-JD validation
**Researched:** 2026-08-28
**Confidence:** HIGH for codebase-specific authority and custody failures; MEDIUM for phase-level policy details that require real fixtures

## Critical Pitfalls

### Pitfall 1: Declaring Full-Career Completeness From Discovered Files

**What goes wrong:** A scan of resumes, repositories, and documents is treated as the user's complete career history even though private, offline, non-code, older, or forgotten Experiences were never inventoried.

**Why it happens:** Automated discovery is easy to count, while completeness is a human claim about the declared source universe and cutoff.

**How to avoid:** Bind every inventory revision to a declared source set and cutoff; preserve missing-source and pending-item states; require item-level review plus explicit user confirmation that no material known Experience is omitted as of that cutoff.

**Warning signs:** Completeness is inferred from file count, repository count, resume sections, or a successful parser run; there is no user-confirmed inventory hash.

**Phase to address:** Full-career inventory and cutoff.

---

### Pitfall 2: Turning Pending or Unresolved Coverage Into Mastery

**What goes wrong:** A present Experience, Contribution, candidate Skill, repository, or evidence item becomes a zero/default score or a positive capability signal before audit and review.

**Why it happens:** Coverage, evidence resolution, graph authority, and assessment admission are compressed into one generic status or missing values are silently defaulted.

**How to avoid:** Keep their state machines distinct. The canonical graph must retain pending, insufficient-evidence, and unresolved-responsibility nodes, while aggregation consumes only admitted `reviewed-user-truth` assessments.

**Warning signs:** Unreviewed nodes appear in mastery inputs; a missing assessment is serialized as `0`; graph completeness changes a Skill score.

**Phase to address:** Canonical graph projection and reviewed-user-truth production.

---

### Pitfall 3: Duplicate and Alias Inflation

**What goes wrong:** The same Skill, Contribution, or Evidence appears under several names or sources and mechanically increases mastery, confidence, duration, or cross-context promotion.

**Why it happens:** Display names, paths, keywords, and ontology aliases are used as identity; merge/split decisions discard source-local lineage.

**How to avoid:** Assign stable source-local IDs first, make equivalence and merge/split decisions reviewable, preserve all source ancestry, and rerun existing duplicate/no-inflation invariants over the full-career corpus.

**Warning signs:** Skill counts fall sharply after normalization; duplicated resume/repository evidence changes aggregation; two aliases enter separate user-level scores.

**Phase to address:** Generic identity and Skill resolution.

---

### Pitfall 4: Responsibility or Coding-Agent Transfer

**What goes wrong:** Team output, another person's implementation, or coding-agent-generated work is attributed to the user and used to justify a higher capability anchor.

**Why it happens:** Artifact authorship, commit identity, polished explanation, or project ownership is substituted for decisions, implementation, debugging, operation, and maintenance responsibility.

**How to avoid:** Preserve user/team/other-person/coding-agent/third-party attribution as separate review facts; keep unresolved conflicts unresolved; require the capability probe and the assistance boundary to be reviewed independently.

**Warning signs:** “The repository contains it” becomes assessment basis; assistance metadata is absent; a responsibility correction does not invalidate downstream assessments.

**Phase to address:** Generic Contribution audit and reassessment lineage.

---

### Pitfall 5: Heterogeneous Source Tampering or Privacy Leakage

**What goes wrong:** Derived text no longer matches raw PDF/DOCX/image/text bytes, path or symlink tricks cross the private workspace boundary, or raw career/JD content leaks into Git, logs, errors, or planning artifacts.

**Why it happens:** Convenience copies become authority; converter identity and hashes are omitted; each adapter invents its own storage behavior.

**How to avoid:** Retain raw source identity and hash before interpretation, bind derived text to adapter/version/hash, reuse one hardened private store, reject unsafe links and controls, and expose only IDs/counts/hashes outside `.career-evidence/`.

**Warning signs:** A proposal cannot reconstruct its source; absolute private paths appear in committed files; public CLI errors echo source text; adapter output is accepted without raw custody.

**Phase to address:** Generic source and private-workspace foundation.

---

### Pitfall 6: Incomplete or Invented JD Interpretation

**What goes wrong:** A JD proposal omits a decision-critical requirement, invents seniority/duration/context not present in the source, or splits/merges linked requirements incorrectly while remaining schema-valid.

**Why it happens:** Structured output proves shape, not semantic completeness; acceptance reviews only selected fields or excerpts.

**How to avoid:** Bind every proposed requirement to reconstructable byte spans, preserve absent fields as absent, review item-level include/edit/reject/split/merge decisions, and require an explicit completeness decision before immutable acceptance.

**Warning signs:** Accepted proposals contain no coverage accounting; optional fields are populated without spans; analysis re-runs extraction instead of loading the reviewed packet.

**Phase to address:** Raw-JD interpretation and immutable corpus.

---

### Pitfall 7: JD-to-Mastery Backflow

**What goes wrong:** JD keywords, desired routing, baseline results, or gap labels modify Skill identity, assessment admission, mastery, or graph content.

**Why it happens:** Matching and assessment share mutable objects or evaluation is allowed to “improve” the graph after viewing target outcomes.

**How to avoid:** Compare one immutable graph hash with immutable JD packets; assert the graph hash before and after every comparison; make corrections only through upstream review and create a new graph version before a separately declared rerun.

**Warning signs:** Different JDs yield different mastery; a failed route triggers automatic reassessment; graph versions change during evaluation.

**Phase to address:** Workspace-bound JD comparison and evaluation isolation.

---

### Pitfall 8: Stale or Substituted Manifests

**What goes wrong:** An evaluation claims to use the confirmed graph or three accepted JDs but actually loads stale sidecars, a different current pointer, duplicated source bytes, or an unreviewed replacement.

**Why it happens:** Paths or filenames stand in for content identities, and current pointers move without expected-prior-hash checks.

**How to avoid:** Bind runs to exact graph-confirmation, ordered three-JD corpus, charter, policy, and baseline hashes; reopen and verify complete ancestry before execution; make accepted bundles create-only.

**Warning signs:** Results name paths but not hashes; the corpus count is not exactly three distinct source hashes; a rerun silently replaces prior output.

**Phase to address:** Graph confirmation, JD corpus sealing, and evaluation orchestration.

---

### Pitfall 9: Reviewer or Baseline Leakage

**What goes wrong:** Reviewers know which arm is graph-based, target routes are used to select evidence, or the baseline is tuned after graph results are visible.

**Why it happens:** Blind assignment, reviewer independence, and preregistration are treated as documentation rather than executable custody.

**How to avoid:** Freeze opaque A/B assignment, baseline, criteria, corpus, graph, and reviewer roles before execution; retain disagreement and adjudication; prohibit outcome-driven evidence selection.

**Warning signs:** Assignment is generated after results; reviewers can infer arm labels from filenames; the baseline changes without a new charter version.

**Phase to address:** Human/blind evaluation.

---

### Pitfall 10: Overclaiming Product or Employment Effectiveness

**What goes wrong:** Deterministic correctness, reviewer preference, or three-JD usefulness is presented as proof of better resumes, interviews, offers, hiring, or general career outcomes.

**Why it happens:** A polished report or supported technical hypothesis is confused with downstream product and field effectiveness.

**How to avoid:** Apply only the frozen `supported` / `partially supported` / `rejected for expansion` meanings, state blockers and generalization limits, and keep employment-effectiveness claims explicitly outside this milestone.

**Warning signs:** The final decision omits limitations; “supported” automatically authorizes full product expansion; no holdout or non-STOA evidence accompanies a generalization statement.

**Phase to address:** Replication and core-hypothesis decision.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Widen STOA regexes without a generic identity/source contract | Fast fixture reuse | Production remains fixture-shaped and sealed v1 meanings drift | Never for production ingress |
| Add a second inventory, graph, or parser for “real data” | Avoids refactoring | Competing facts, review paths, and hashes | Never |
| Store copied facts inside graph/JD/evaluation bundles | Easier display | Corrections diverge from owning authority | Only immutable non-authoritative summaries with source hashes |
| Use one generic status field | Smaller schema | Coverage, responsibility, authority, and admission become ambiguous | Never |
| Accept parser/model output automatically | Fewer checkpoints | Schema-valid invention becomes user truth | Never |
| Add PDF/DOCX/OCR/provider dependencies before inventory | Apparent format coverage | Supply-chain, fidelity, and lockfile burden without a real need | Only after the confirmed corpus proves necessity |
| Calibrate policies after seeing desired routes | Faster “success” | Invalid experiment and hidden overfitting | Never; create a new declared experiment instead |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| STOA fixture → generic inventory | Mutate sealed fixture schemas and IDs | Keep a legacy adapter and introduce generic v1.1 contracts |
| Source adapters → private store | Let each adapter own persistence | One source envelope and hardened workspace store |
| Audit → assessment | Treat a completed conversation as admitted mastery | Require reviewed conclusion, Skill resolution, substantive assessment review, and admission |
| Inventory → graph | Drop uncovered/unassessed nodes | Project all accepted inventory with explicit non-authoritative states |
| JD extraction → acceptance | Re-run extraction during accept | Accept the exact reviewed proposal hash only |
| Graph/JD → evaluation | Load moving “current” paths | Resolve exact immutable hashes before the run starts |

## Security and Privacy Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Commit raw career sources, audit answers, JDs, or graph snapshots | Permanent private-data disclosure | Gitignored private root, status-only committed artifacts, staged-path review |
| Trust extensions or MIME labels | Malicious or mismatched input handling | Validate bytes, size, controls, regular-file/link constraints, and explicit adapter |
| Log source excerpts in routine errors | Accidental disclosure through terminals/reports | Redacted identifiers, hashes, byte offsets, and safe code-point diagnostics |
| Follow symlinks or reuse writable accepted files | Source substitution/tampering | No-follow checks, single-link regular files, create-only bundles, reopen verification |
| Upload evidence or add telemetry by default | Unauthorized external transfer | Local-only processing unless a separately approved boundary exists |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Asking for all documents before showing inventory progress | Unbounded, exhausting intake | Incremental source batches with visible coverage and cutoff state |
| Treating “I don't know” like “I didn't do that” | Incorrect mastery and responsibility | Separate uncertainty, evidence insufficiency, and non-responsibility decisions |
| Showing unreviewed candidate scores | Anchoring and false authority | Show state and missing decision; no mastery until admission |
| Requiring blanket approval of a large graph/JD packet | Hidden errors and weak authority | Item-level corrections followed by exact-hash final confirmation |
| Presenting one match percentage | Conceals capability/evidence/context differences | Requirement-level judgments and separate gap categories |

## “Looks Done But Isn't” Checklist

- [ ] **Full-career inventory:** User confirmed the declared source universe and cutoff; successful discovery alone is insufficient.
- [ ] **Canonical graph:** Every accepted inventory item is represented with a coverage/authority state, including unassessed items.
- [ ] **Mastery:** Every score traces only to admitted reviewed-user-truth assessments; no candidate/default/ontology/JD input is present.
- [ ] **Deduplication:** Alias and merge/split decisions preserve source ancestry and cannot inflate aggregation.
- [ ] **Attribution:** Responsibility and coding-agent assistance are explicitly resolved or remain visibly unresolved.
- [ ] **Private custody:** Raw sources and JDs remain uncommitted; public output cannot reconstruct them.
- [ ] **JD corpus:** Exactly three distinct user-selected packets reconstruct from retained bytes and have item-level completeness approval.
- [ ] **Isolation:** Comparison and evaluation leave the graph hash unchanged.
- [ ] **Stability:** Critical cases run three times under one frozen configuration and material variance is reported.
- [ ] **Blind baseline:** Assignment, criteria, and baseline were frozen before review and disagreement is retained.
- [ ] **Decision:** The final verdict applies the frozen meanings, names blockers, and states generalization/employment-effectiveness limits.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| False completeness | MEDIUM | Reopen inventory with a new declared source set/cutoff, retain old revision, repeat user confirmation |
| Unauthorized mastery | HIGH | Quarantine affected assessments, rebuild aggregation and graph from admitted lineage, rerun every bound comparison/evaluation |
| Duplicate/alias inflation | MEDIUM | Add reviewed identity resolutions, rebuild deterministic projection, compare old/new scores and preserve regression evidence |
| Source/JD tampering or leakage | HIGH | Stop processing, preserve custody evidence, rotate affected workspace records, remove publication path where recoverable, disclose limits |
| Incomplete JD acceptance | MEDIUM | Create a new proposal/review/accepted packet and a new corpus; never patch the old packet |
| Stale evaluation inputs | MEDIUM | Mark run invalid, bind verified immutable hashes, create a linked rerun with reason |
| Blind-review leakage | HIGH | Discard affected comparative judgment and repeat with new frozen opaque assignment and eligible reviewer |
| Overclaiming | LOW technically / HIGH evidentially | Correct the report, narrow the verdict, and require separate downstream effectiveness validation |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention phase topic | Verification |
|---------|------------------------|--------------|
| False completeness | Full-career inventory and cutoff | User-confirmed inventory hash plus missing/pending coverage report |
| Pending-to-mastery leakage | Graph and reviewed-user-truth production | Aggregation rejects every non-admitted state; graph retains nodes without scores |
| Alias inflation | Generic identity and Skill resolution | Duplicate/alias/split/merge invariants leave mastery unchanged absent higher-anchor evidence |
| Responsibility transfer | Generic Contribution audit | Corrected attribution invalidates stale downstream lineage; unresolved remains non-authoritative |
| Source/privacy failure | Source and private-workspace foundation | Hash reconstruction, permission/link tests, Git/public-output leakage checks |
| JD omission/invention | Raw-JD interpretation and corpus | Byte-span reconstruction, absence preservation, item-level completeness review |
| JD backflow | JD comparison | Before/after graph hashes identical across all three packets and counterfactuals |
| Stale/substituted inputs | Graph/JD sealing and evaluation orchestration | Exact ancestry and expected hashes reopen before every run |
| Reviewer/baseline leakage | Human/blind evaluation | Frozen opaque assignment and baseline hashes precede reviewer records |
| Effectiveness overclaim | Replication and final decision | Verdict schema requires limitations, blockers, holdout/replication status, and no employment claim |

## Sources

### Verified project sources

- `.planning/PROJECT.md` — v1.1 scope, authority boundaries, and explicit exclusions. **Confidence: HIGH**
- `.planning/milestones/v1.0-REQUIREMENTS.md` — frozen evaluation and decision requirements plus unfinished empirical work. **Confidence: HIGH**
- `validation/jd/evaluation-charter.json` — exact repetition, baseline, blind-review, fabrication, and limitation rules. **Confidence: HIGH**
- `src/career_evidence_graph/domain/fixtures.py`, `audit/models.py`, `assessment.py`, and `jd.py` — STOA coupling, attribution, authority, graph projection, source custody, and comparison seams. **Confidence: HIGH**
- `.planning/research/STACK.md`, `FEATURES.md`, and `ARCHITECTURE.md` — verified milestone-specific technology, capability, and integration findings. **Confidence: HIGH**

---
*Pitfalls research for: v1.1 Full Career Graph and Real JD Validation*
*Researched: 2026-08-28*
