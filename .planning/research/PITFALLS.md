# Pitfalls Research

**Domain:** Contribution-level conversational skill assessment and career-evidence graph validation  
**Project:** Career Evidence Graph — Core Hypothesis Validation  
**Researched:** 2026-07-30  
**Confidence:** HIGH for risks derived from project invariants and pinned source code; MEDIUM for general validation/security guidance obtained through web search

## Read This First: Validity Risks vs. Engineering Risks

The most dangerous failure is not a crash. It is a polished, internally consistent graph that assigns plausible 0–100 scores and selects sensible-looking résumé evidence while measuring the wrong thing.

| Risk class | Examples | Roadmap treatment |
|---|---|---|
| **Product-validity risk** | Leading interview, self-report inflation, circular LLM judging, mastery inferred from ontology or keywords, STOA/JD overfit | Must be falsified with preregistered cases, human judgments, baselines, perturbation tests, and held-out data before the hypothesis is called validated |
| **Data-integrity risk that threatens validity** | Team/Codex work attributed to the user, overlapping durations summed, confidence folded into mastery, stale assessment reused in a new context | Must be prevented by the domain model and tested as invariants |
| **Security/provenance risk that threatens validity** | Prompt injection in a repository/JD, hidden PDF text, copied upstream code without provenance | Must have trust boundaries, adversarial fixtures, and an adaptation ledger before evaluation |
| **Ordinary engineering risk** | Slow test suite, CLI ergonomics, storage performance, deployment complexity | Important later, but must not consume validation scope or be mistaken for evidence that the product hypothesis works |

## Required Roadmap Gates

The phase names below are recommendations; phase numbers may change, but the gates and ordering should not.

| Gate | Purpose | Exit condition |
|---|---|---|
| **V0 — Validation Charter & Provenance** | Freeze constructs, hypotheses, baselines, success/failure rules, source trust policy, upstream ledger | A result can fail; test and holdout sets are identified before prompt/scoring tuning |
| **V1 — Domain Contracts & Gold Fixtures** | Encode Experience → Contribution → Skill, assessment dimensions, attribution, duration, context, and ontology boundaries | Deterministic invariants and adversarial fixtures pass; two humans can apply the rubric |
| **V2 — Grill-Me Audit Workflow** | Elicit capability without revealing desired answers; preserve transcript and evidence trail | Standardized probe families, contribution coverage, attribution challenges, and work-sample checks operate on STOA fixtures |
| **V3 — Scoring & Ontology Calibration** | Normalize skills and aggregate assessments without dimension collapse or inflation | Anchor, perturbation, split/merge, overlap, and propagation tests pass; inter-rater/model variation is reported |
| **V4 — JD Utility & Adversarial Evaluation** | Test whether the graph improves JD decisions and survives hostile inputs | Beats preregistered baselines on held-out JDs without reducing truthfulness; injection suite passes |
| **V5 — Replication & Decision Gate** | Test limits of generalization and decide validate/revise/reject | Findings reproduce on held-out contributions and at least one non-STOA experience or are explicitly scoped as a single-case result |

## Critical Pitfalls

### 1. Non-falsifiable success criteria and weak baselines

**What goes wrong:**  
The team declares success because the graph looks coherent, the user agrees with flattering scores, or relevant STOA contributions appear for a JD. This only proves that an LLM can restate supplied material. A keyword matcher, résumé-only extractor, or human reading the same artifacts may perform equally well.

**Why it happens:**  
“Useful,” “defensible,” and “accurate” are left undefined until after results are seen. The same people who designed the rubric choose cases and judge success. Only positive examples are tested.

**Warning signs:**

- Success is expressed as “reasonable,” “high quality,” or “helpful” without thresholds and failure conditions.
- No artifact-only, résumé-only, self-report-only, or simple keyword baseline exists.
- No intentionally weak, misleading, or unsupported contribution is in the gold set.
- Evaluation reports only average scores, not false positives, false negatives, disagreements, or uncertainty.

**How to avoid:**

- In V0, preregister the construct: the audit should establish observable capability for a specific Skill from a specific Contribution, not eloquence, evidence volume, or JD vocabulary.
- Define separate endpoints: contribution factuality, responsibility attribution, anchor-band agreement, evidence traceability, test-retest stability, and incremental JD utility.
- Use at least four baselines: raw résumé/JD keyword match; artifacts without interview; interview self-report without artifacts; structured human review without the graph.
- Define a stop/revise rule. Example: do not validate if the graph fails to beat the strongest baseline on held-out JD relevance, if unsupported high-mastery false positives exceed the agreed limit, or if independent raters cannot reproduce anchor bands.

**Detection/test:**

- Run all methods on the same frozen cases and blind the utility reviewer to method identity.
- Include null cases where no defensible assessment is possible; a good system must abstain or remain provisional.
- Publish per-case errors and confidence intervals/ranges, not only a composite score.
- Verify that a negative result is possible without changing the charter.

**Phase to address:** V0; enforced again at V4 and V5.  
**Confidence:** HIGH — direct consequence of the project hypothesis; supported by NIST’s requirement for documented benchmarks, representative test sets, independent review, uncertainty, and limits on generalizability.

---

### 2. Leading interview and JD-conditioned questioning

**What goes wrong:**  
The interviewer teaches the answer, names the desired skill, supplies a recommended response, or probes only JD-relevant branches. The resulting explanation then “confirms” the skill the system planted. The audit measures agreement and verbal accommodation, not independent understanding.

**Why it happens:**  
Matt Pocock’s grilling pattern is useful for one-question-at-a-time exploration, but it explicitly recommends providing a recommended answer. That is appropriate for design decisions and inappropriate for capability measurement. Showing the target JD or expected ontology terms to the interviewer also creates demand characteristics.

**Warning signs:**

- Questions contain the expected technology, trade-off, failure mode, or mastery-anchor language.
- The transcript shifts toward terms introduced first by the assistant.
- High scores depend on answers to “Would you say…?” or “So you used X because Y?”.
- Different candidates/contributions receive materially different levels of hinting.
- The audit knows which skills the JD rewards before open elicitation is complete.

**How to avoid:**

- Separate discovery from assessment. First ask open, behaviorally anchored questions about what happened; only then use standardized neutral probes.
- Hide target JD weights and expected skill labels from the Grill-Me question generator until the contribution account is frozen.
- Maintain probe families for every claimed capability: reproduce, explain a boundary case, diagnose a failure, defend a trade-off, distinguish own work, and state what was not done.
- Log every hint. Treat answers following substantive hints as weaker evidence or rerun with an unhinted work sample.
- Preserve one-question-at-a-time and artifact-before-questioning from Matt Pocock Skills, but reject its “recommended answer” behavior for scored questions.

**Detection/test:**

- Create paired transcripts differing only in leading versus neutral wording; mastery should not rise because the interviewer supplied terminology.
- Run “term-introduction attribution”: flag scored concepts first introduced by the assistant.
- Have a blinded reviewer label questions as open, neutral probe, or leading; set a maximum leading-question rate of zero for scored evidence.
- Replay a subset with question order randomized within dependency-safe blocks and compare outcomes.

**Phase to address:** V2, with question-policy fixtures defined in V1.  
**Confidence:** HIGH for project mechanism; MEDIUM for external interview guidance. OPM supports standardized, job-related questions, probes, scales, and proficiency benchmarks.

---

### 3. Self-report fluency mistaken for capability

**What goes wrong:**  
A persuasive user receives high mastery for a contribution that cannot be reproduced or independently verified, while a terse but capable user is underrated. Confidence rises because the story is detailed, internally consistent, or uses expert vocabulary.

**Why it happens:**  
The primary witness and beneficiary are the same person. Memory is reconstructive; social-desirability and hindsight effects are normal even without deliberate deception. LLMs reward coherent prose.

**Warning signs:**

- Assessment basis cites only the user explanation.
- Longer answers correlate with mastery or confidence after capability content is controlled.
- Claimed metrics, decisions, or ownership have no source, counterfactual, or reproducible trace.
- The system never records “unverified,” “cannot recall,” or contradictions.

**How to avoid:**

- Ask for observable, verifiable behaviors rather than trait labels or “years of experience.”
- Triangulate material claims with artifacts, work samples, commit/decision history, or a second source where proportionate.
- Preserve contradictions and failed answers; never overwrite them with a polished summary.
- Use an explicit admissibility policy: self-report can propose a Contribution and guide probes, but cannot by itself establish high confidence or advanced repeated responsibility.
- Permit “insufficient evidence” without forcing a score.

**Detection/test:**

- Seed fixtures with a fluent unsupported claim and a terse artifact-supported claim; the latter must not score lower because of style.
- Redact verbosity/style while preserving propositions and rerate.
- Compare assessment before and after artifact revelation; confidence may change, but mastery changes require new capability evidence.
- Include confirmatory work samples for high bands and record pass/fail independently of interview impression.

**Phase to address:** V1 evidence policy and V2 workflow; verified in V3.  
**Confidence:** HIGH — OPM explicitly treats self-report inflation as a known issue and recommends observable behavior, verification sources, and confirmatory assessments; APA defines self-report bias as error from limited knowledge or impression management.

---

### 4. Circular extraction, scoring, and judging

**What goes wrong:**  
One model, prompt family, or hidden rubric generates questions, extracts claims, assigns scores, and judges whether the score is good. Shared biases produce impressive agreement. “Evidence” text merely rationalizes the score.

**Why it happens:**  
Structured Pydantic output and evidence fields, as seen positively in Hiring Agent, enforce shape but not truth or calibration. An LLM judge favors familiar wording and may agree with outputs produced from the same context.

**Warning signs:**

- The evaluator receives the candidate score or chain-of-reasoning before judging evidence.
- Gold labels were generated by the same model/prompt being evaluated.
- Agreement is reported only between repeated runs of one model.
- Rationale quality is used as a proxy for score validity.
- Changing the score while keeping the evidence fixed changes the judge’s verdict.

**How to avoid:**

- Freeze human-authored gold cases before tuning; require at least two independent ratings for ambiguous/high-stakes cases.
- Blind raters to system score, JD target, and method identity.
- Separate deterministic contract checks from semantic human judgment.
- Use model/provider variation as a robustness test, never as ground truth.
- Preserve raw evidence references and let reviewers reconstruct the assessment without the generated rationale.

**Detection/test:**

- Measure exact/adjacent anchor-band agreement, disagreement direction, and inter-rater reliability; do not reduce all disagreement to pass/fail.
- Run rationale-swap and score-swap tests.
- Compare same-model judge, different-model judge, and human judge; large gaps are a calibration failure.
- Re-score frozen transcripts after prompt/model changes and publish drift.

**Phase to address:** V0 evaluation ownership, V1 gold fixtures, V3 calibration.  
**Confidence:** HIGH — directly testable; NIST recommends independent assessors and objective, repeatable TEVV.

---

### 5. Wrong Contribution granularity and double-counted evidence

**What goes wrong:**  
A large STOA responsibility is lumped into a Contribution so broad that team work and multiple skills become inseparable, or it is fragmented into many near-duplicate Contributions whose repeated evidence inflates mastery, centrality, or duration.

**Why it happens:**  
“Distinguishable piece of work” needs operational boundary rules. Artifact structure (folders, tickets, commits) is mistaken for contribution structure. The model creates one Contribution per sentence or per skill.

**Warning signs:**

- One Contribution contains unrelated outcomes, owners, time periods, and verification modes.
- Several Contributions cite the same artifact lines and describe the same decision in different words.
- Splitting one contribution changes the user mastery score materially.
- Contribution count, rather than anchor-satisfying evidence diversity, predicts mastery.

**How to avoid:**

- Define a Contribution identity test: coherent outcome, responsibility owner(s), bounded context/time, and separable evidence trail.
- Store evidence-to-contribution links explicitly and track shared evidence; shared support is not independent replication.
- Deduplicate semantically equivalent contributions before aggregation.
- Aggregate by observable anchor satisfaction and independent contexts, not row count.

**Detection/test:**

- **Split/merge invariance:** represent the same work as one versus several equivalent Contributions; user mastery should remain within a small preregistered tolerance.
- **Duplicate evidence test:** clone/rephrase a Contribution or attach the same artifact repeatedly; mastery must not rise.
- Human boundary review on STOA contributions with reasons for split/merge decisions.

**Phase to address:** V1 contracts and fixtures; enforced in V3 aggregation.  
**Confidence:** HIGH — follows directly from the project’s Contribution-as-audit-unit invariant.

---

### 6. Skill granularity errors and ontology propagation masquerading as evidence

**What goes wrong:**  
Skills are too broad (“backend,” “AI,” “leadership”) to support stable mastery, too narrow to compare across Contributions/JDs, or merged despite distinct capability demands. MIND aliases or `impliesKnowingSkills` relations silently create mastery for skills never audited.

**Why it happens:**  
Normalization, inference, and assessment are collapsed. Ontology proximity looks authoritative. Exact-name matching encourages premature canonicalization.

**Warning signs:**

- A user Skill node exists only because another ontology node implies it.
- Parent/related skills inherit a numeric score.
- One score combines implementation, operation, design, and tool familiarity without a common anchor.
- Alias resolution changes after seeing the JD.
- Ambiguous terms such as “React,” “deployment,” or “research” are canonicalized without context.

**How to avoid:**

- Put MIND behind a versioned, read-only adapter used for candidate aliases and relations only.
- Require a ContributionSkillAssessment with direct assessment basis before any user mastery exists.
- Mark ontology edges as semantic metadata (`alias_of`, `related_to`, `may_require`) and never as evidence.
- Keep an unresolved/ambiguous state; perform context-sensitive normalization before scoring.
- Define skill-scope tests: a Skill must have one coherent capability scale whose anchors make sense from 0–100.

**Detection/test:**

- **No-evidence propagation invariant:** removing all direct Contribution links must remove user mastery even when ontology relations remain.
- Adversarial alias cases, homonyms, parent/child skills, and framework/language implications.
- Version-diff test against the pinned MIND snapshot; an ontology update cannot change mastery without new evidence and review.
- Compare JD match with and without related-skill expansion; related terms may aid retrieval but cannot become exact matches.

**Phase to address:** V1 adapter contract and V3 calibration.  
**Confidence:** HIGH — pinned MIND data contains explicit implication relations; the project explicitly prohibits using them as mastery.

---

### 7. Score inflation and semantic collapse of mastery, centrality, confidence, duration, context, and JD match

**What goes wrong:**  
Several distinct numbers become hidden ingredients of one “skill score.” Abundant evidence, long duration, high centrality, recent use, or JD relevance pushes mastery upward even when demonstrated capability remains bounded.

**Why it happens:**  
A weighted formula is easy to implement and yields precise rankings. Hiring Agent’s additive categories/bonuses are a useful warning: arithmetic can enforce caps while still combining constructs that should remain separate.

**Warning signs:**

- Increasing `evidence_confidence` changes the claimed capability anchor.
- An incidental but sophisticated use is downscored solely because centrality is low, or a central routine use is upscored.
- Many 40–54 Contributions yield 80+ without evidence of system ownership.
- JD keywords affect the stable user mastery score.
- A score has more precision than the underlying anchor decision.

**How to avoid:**

- Treat `demonstrated_mastery` as the capability signal; use confidence for admissibility/uncertainty, centrality for contribution importance, duration/context for claims about repetition, and JD match only for target relevance.
- Make anchor satisfaction the primary aggregation rule. A higher user band requires observable conditions of that band, not a weighted average or evidence count.
- Store the unaggregated assessments and reason for every band transition.
- Prefer bands/ranges and provisional status during validation; do not optimize decimal formulas prematurely.

**Detection/test:**

| Perturbation | Required behavior |
|---|---|
| Duplicate low-level Contributions | No advanced-band promotion |
| Raise confidence with identical capability evidence | Confidence/status may change; mastery anchor does not |
| Raise centrality with identical capability evidence | Relevance within Contribution may change; mastery does not |
| Swap target JD | User mastery remains unchanged |
| Add verbose documentation | Confidence may rise only if it verifies facts; capability does not rise automatically |
| Add repeated advanced responsibility in a truly independent context | Higher band is allowed only if the next anchor’s observable conditions are met |

**Phase to address:** V1 semantic invariants and V3 aggregation calibration.  
**Confidence:** HIGH — direct project invariant.

---

### 8. Centrality misuse and evidence-volume bias

**What goes wrong:**  
The most central skill in a Contribution is treated as the skill the user knows best. Highly documented or GitHub-visible work dominates private, operational, teaching, decision, or collaborative work.

**Why it happens:**  
Centrality is easy to confuse with proficiency. Hiring Agent enriches evaluation with GitHub activity and project selection; that is useful retrieval evidence but creates a negative lesson if public activity becomes privileged capability evidence.

**Warning signs:**

- Centrality and mastery are highly correlated by construction.
- GitHub stars, repository count, commit count, file count, or lines changed appear in mastery formulas.
- Skills from private/product/teaching work systematically have lower confidence or mastery without an evidentiary reason.
- “Used everywhere” is accepted as proof of advanced responsibility.

**How to avoid:**

- Define centrality as counterfactual contribution importance: how necessary was the Skill to completing this Contribution?
- Define mastery through observable difficulty, independence, failure handling, trade-offs, maintenance, and repeated responsibility.
- Treat repository metrics as discovery signals only until contribution ownership and task content are verified.
- Support non-code evidence types with equivalent verification paths.

**Detection/test:**

- Paired fixtures: central routine skill versus peripheral advanced skill; mastery ordering must follow capability, not centrality.
- Paired public/private contributions with equivalent verified capability.
- Remove popularity and volume metadata and re-score; mastery should not change.

**Phase to address:** V1 rubric and V3 calibration.  
**Confidence:** HIGH — direct semantic risk; pinned Hiring Agent shows how GitHub data can be appended before evaluation.

---

### 9. Duration overlap, calendar arithmetic, and false repetition

**What goes wrong:**  
Concurrent skills or Contributions are summed into impossible experience durations. Repeated records from one project are treated as multiple contexts. Employment tenure is copied into every skill used briefly.

**Why it happens:**  
Duration is derived from Experience dates or Contribution count rather than verified active intervals. Resume parsers preserve overlapping roles but do not solve allocation.

**Warning signs:**

- Skill duration exceeds elapsed career time.
- Every skill inherits the full STOA project duration.
- Parallel Contributions each add the same months to user-level duration.
- “Multiple contexts” all point to the same system, team, decision, and artifact set.

**How to avoid:**

- Store contribution/skill-specific intervals with precision and provenance; represent unknown or intermittent duration honestly.
- Aggregate duration by interval union, not sum, and keep intensity separate if ever needed.
- Define independent context using meaningful changes in system, responsibility, constraints, or organization—not row count.
- Never let duration directly raise mastery; it can support repeated-responsibility anchor conditions only with capability evidence.

**Detection/test:**

- Interval-union unit tests for nested, overlapping, partial, and unknown dates.
- Metamorphic test: split one interval into overlapping subrecords; verified duration and mastery remain unchanged.
- Manual audit of all STOA 80+ or “repeated contexts” claims.

**Phase to address:** V1 temporal model and V3 aggregation.  
**Confidence:** HIGH — deterministic and directly tied to project semantics.

---

### 10. Context leakage and stale assessment reuse

**What goes wrong:**  
Information from other Contributions, the whole Experience, prior model summaries, ontology implications, or the target JD leaks into a specific Contribution–Skill assessment. Later, a score earned in one context is treated as universal or silently changes when a different JD is loaded.

**Why it happens:**  
Long conversation memory is convenient. Cached intermediate results, as positively demonstrated by Hiring Agent and historical snapshots in CV Market Learning Planner, improve reproducibility but can also preserve poisoned or outdated assumptions.

**Warning signs:**

- An assessment cites facts not linked to the audited Contribution.
- Reordering Contributions changes scores.
- Loading a JD changes user mastery before new audit evidence exists.
- Cache keys omit prompt, model, ontology, evidence, rubric, or source-version hashes.
- A corrected attribution does not invalidate dependent assessments.

**How to avoid:**

- Build an explicit assessment context packet containing only the Contribution, linked Evidence, relevant Q&A, and provenance.
- Keep JD matching downstream and read-only with respect to stable mastery.
- Version every derived artifact by source/evidence/rubric/prompt/model/ontology identifiers; invalidate dependents on material change.
- Adapt CV Market Learning Planner’s append-only history and deterministic helpers, not a mutable “current truth” without lineage.

**Detection/test:**

- Context canary: insert irrelevant high-skill evidence in a neighboring Contribution; the target score must not move.
- Order-invariance and fresh-session replay tests.
- JD-swap test: mastery graph hash stays stable while match output changes.
- Cache invalidation matrix and stale-cache adversarial case.

**Phase to address:** V1 lineage contract, V2 state handling, V3/V4 regression tests.  
**Confidence:** HIGH — deterministic design risk supported by pinned upstream cache/history patterns.

---

### 11. User, team, Codex, and third-party attribution collapse

**What goes wrong:**  
The user receives mastery for work performed by collaborators, a template/library, Codex, an upstream project, or an automated service. Conversely, legitimate user direction, debugging, integration, review, or operation is erased because the final code was generated.

**Why it happens:**  
First-person plural is ambiguous; repositories show final state, not responsibility; commits do not prove authorship or understanding. Tabiya’s explicit responsibility/other-person/non-responsibility buckets are a strong precedent, but its “when in doubt, classify first-person entity as responsibility” fallback is unsafe for scored evidence.

**Warning signs:**

- “We built” becomes “I implemented.”
- Generated/copied files are cited without identifying source and user action.
- Commit author, repository owner, or file presence is treated as proof of capability.
- The system has no attribution value for assisted, reviewed, directed, integrated, operated, or independently implemented work.
- The same artifact supports both the user’s and team’s full ownership.

**How to avoid:**

- For each Contribution and material subtask, capture actor, role, assistance type, source, user decisions, verification, and what the user can reproduce now.
- Require neutral follow-ups for plural claims: who did what, what did the user decide/change/debug, what would fail without their work?
- Treat Codex/third-party output as Evidence of the resulting system, not automatically of user implementation mastery.
- Credit capabilities actually demonstrated around assisted work—specification, evaluation, debugging, integration, operation—without relabeling them as unaided coding.
- Use Tabiya’s separation and structured extraction, but replace permissive ambiguity defaults with `unresolved_attribution`.

**Detection/test:**

- Gold fixtures for solo, pair, team, managed, reviewed-only, Codex-generated-and-accepted, Codex-generated-and-debugged, forked, and third-party-integrated work.
- Attribution holdback: remove user-specific evidence and verify the system abstains rather than inheriting repository capability.
- Ask the user to reproduce/defend a representative boundary or failure; compare with claimed role.
- Every high-mastery basis must be reconstructable from attribution-tagged evidence.

**Phase to address:** V1 attribution schema and V2 audit workflow; gate V3 high scores.  
**Confidence:** HIGH — explicit project constraint and pinned Tabiya implementation precedent.

---

### 12. Overfitting STOA, one articulate user, and the chosen JD set

**What goes wrong:**  
Prompts, contribution boundaries, skills, and score thresholds are tuned until STOA looks right and the selected JDs produce satisfying matches. The system then fails on a different experience type, writing style, negative case, or JD family.

**Why it happens:**  
STOA is both development material and evaluation target. A small JD set invites repeated inspection. One user cannot establish population-level reliability or fairness.

**Warning signs:**

- Every prompt change is evaluated on the same STOA transcript.
- Skill taxonomy mirrors wording in the chosen JDs.
- No held-out Contribution or JD remains untouched.
- “Works for STOA” is generalized to career histories broadly.
- Evaluation does not include sparse evidence, non-code work, failed work, or mixed ownership.

**How to avoid:**

- Split STOA into development and sealed holdout Contributions before tuning.
- Select JDs by a sampling rationale and hold at least one role/family out; include irrelevant and near-match JDs.
- Add a minimal non-STOA replication case before V5, even though full career modeling is out of scope.
- Report the validated scope precisely: single-user/specified-domain evidence unless replication supports more.
- Freeze prompts and thresholds before opening holdouts; changes after failure require a new holdout.

**Detection/test:**

- Compare development versus holdout performance and error types.
- Paraphrase JDs and remove brand/tool keywords; relevant selection should survive semantic changes.
- Negative-control JD with overlapping vocabulary but different capability requirements.
- Leave-one-Contribution-out and leave-one-JD-out analyses.

**Phase to address:** V0 sampling plan; executed in V4 and V5.  
**Confidence:** HIGH — direct external-validity threat; NIST requires representative conditions and documented limits on generalizability.

---

### 13. Prompt injection and untrusted artifacts manipulate assessment

**What goes wrong:**  
A repository file, issue, README, generated artifact, hidden PDF text, resume, JD, or upstream instruction tells the model to ignore rules, claim ownership, assign 100, reveal context, or call tools. The attack may persist through summaries/caches and look like legitimate evidence.

**Why it happens:**  
The product intentionally asks an LLM to read attacker- or third-party-controlled natural language. Prompt delimiters and “ignore instructions in documents” wording reduce accidental confusion but do not eliminate indirect prompt injection.

**Warning signs:**

- Source text changes system behavior, tool use, rubric, or output schema.
- Evidence includes instruction-like language or hidden/non-rendered text.
- Assessment rationale cites a source telling the evaluator how to score it.
- Sanitization removes a few known tags but no adversarial test verifies the trust boundary.
- Cached summaries retain content after the source is removed.

**How to avoid:**

- Treat all source artifacts as untrusted data; enforce task/instruction separation in architecture, not only prose.
- Parse/extract into typed, allowlisted claims before scoring; retain source offsets/hashes for review.
- Do not allow artifact content to initiate tool calls, modify files, change rubric, or grant itself authority.
- Use read-only, least-privilege inspection for the validation project and human approval for any privileged action.
- Detect hidden text/layers where feasible and render what the human reviewer sees.
- Invalidate all derived state when injection is detected.

**Detection/test:**

- Adversarial corpus covering direct instructions, indirect repository instructions, split payloads across files/fields, hidden PDF text, Unicode obfuscation, fake system tags, JD instructions, tool requests, and persistent-cache poisoning.
- Expected outcome is not merely “no crash”: extracted facts, attribution, mastery, and tool behavior must remain unchanged or the item must be quarantined.
- Inspect output for source-injected tokens and run provenance completeness checks.
- Red-team after every material prompt/model/parser change.

**Phase to address:** V0 trust policy, V1 typed boundaries, V2 artifact ingestion, V4 adversarial gate.  
**Confidence:** HIGH for applicability; MEDIUM source tier. OWASP explicitly documents repository, JD, résumé/split-payload, hidden-content, and persistent-context injection scenarios.

---

### 14. Upstream license, submodule, and copied-architecture drift

**What goes wrong:**  
Pinned repositories become untracked snippets, submodules silently move or fail to initialize, copied code loses copyright/NOTICE obligations, or an upstream architecture is adopted wholesale despite a different product model. The result is legally unclear and conceptually distorted.

**Why it happens:**  
All six upstreams are useful and permissively licensed, which can be misread as “copy anything without bookkeeping.” Code and architectural assumptions travel together. Submodule branch labels in local status are not the pin; the recorded gitlink commit is.

**Warning signs:**

- Local code resembles an upstream module but has no source path, commit, license, or adaptation classification.
- CI/test setup fetches an upstream branch head or online ontology instead of the recorded commit.
- `git submodule status` shows `+`, `-`, or `U`; `.gitmodules`, gitlinks, and `references/README.md` disagree.
- Tabiya’s occupation-first ranking, Hiring Agent’s GitHub-weighted scoring, CV Planner’s learning levels, or Resume Matcher’s master-resume/keyword model appears in the core domain.
- A copied Apache-2.0 file lacks modification notice or relevant license/NOTICE handling.

**How to avoid:**

- In V0, create a per-subsystem ledger: upstream repository, exact commit, exact source file/pattern, `reuse|adapt|inspired-by|reject`, license, copied lines/files, required notices, and local divergence.
- Verify gitlink SHAs against `references/README.md` in an automated check; initialize offline/pinned where possible and never treat upstreams as runtime dependencies.
- For MIT substantial copies, preserve the copyright and permission notice. For Apache-2.0 redistribution, include the license, mark modified files, retain pertinent notices, and propagate relevant NOTICE content when present.
- Write a local invariant test for every adapted pattern. Pattern provenance does not make upstream behavior correct for this project.
- Copy seams, not stacks: Tabiya’s separation of conversation/extraction/transition, Matt’s one-question flow, MIND’s normalization adapter, CV Planner’s history, Hiring Agent’s typed boundaries, and Resume Matcher’s golden truthfulness cases.

**Detection/test:**

- Provenance-lint changed files for upstream identifiers and ledger entries.
- Verify all six recorded commits and clean submodule states in the validation environment.
- License review before merging copied/adapted code; compare distributed artifacts with required LICENSE/NOTICE files.
- Architecture fitness review asks which local invariant each borrowed component satisfies and which upstream assumptions are explicitly rejected.

**Phase to address:** V0 before original implementation; verify at every later phase gate.  
**Confidence:** HIGH — pinned repository code/licenses and project reuse matrix are primary sources; OSI/Apache guidance is authoritative.

## Upstream Precedents and Negative Lessons

| Upstream | Positive precedent to adapt | Convincing-but-false result if inherited blindly | Required local countermeasure |
|---|---|---|---|
| **Tabiya Compass** | Separate conversation, extraction, coverage/transition; distinguish user, other-person, and non-responsibility work; repeat nondeterministic evals | Occupation-constrained/top-skill ranking appears to prove mastery; permissive “when in doubt” responsibility classification over-attributes work; basic pass/fail eval hides nuanced errors | `unresolved_attribution`; Contribution-level gold cases; exact semantic metrics; no occupation rank as mastery |
| **Matt Pocock Skills** | One question at a time; inspect artifacts before asking facts; challenge vague language and boundary cases | Recommended answers lead the witness; relentless/open-ended grilling causes fatigue and selective completion; transcript is mistaken for structured evidence | Neutral standardized probes, hint log, stopping/coverage criteria, structured extraction with source links |
| **MIND Tech Ontology** | Canonical names, aliases, misspellings, domains, concepts, tasks, explicit relations; pin behind adapter | `impliesKnowingSkills` or parent relations create unsupported mastery; broad/narrow nodes are treated as commensurate | No-evidence propagation invariant; ambiguity state; ontology version cannot change mastery |
| **CV Market Learning Planner** | Append-only reviews/history, current versus snapshots, deterministic helpers, preserved raw submissions | Free-form levels/gap outputs are treated as calibrated mastery; repeated exercises or history volume create score progress | Versioned assessment lineage; capability-anchor calibration; repetition without higher-order evidence cannot promote |
| **Hiring Agent** | Pydantic contracts, staged extraction/caching, role configuration, evidence-bearing outputs | GitHub activity/public popularity is privileged; LLM scores and rationales appear objective without calibration; stale cache contaminates reevaluation | GitHub as discovery only; independent gold/human review; complete cache keys/invalidation; no additive category score reuse |
| **Resume Matcher** | Golden good/bad truthfulness cases, diff-based changes, structural scoring, anti-fabrication intent | Master résumé/keywords become source of truth; JD phrasing leaks into stable skill scores; prompt-only guards miss invented narrative (noted by its own test comments) | Evidence graph remains source of truth; JD read-only for mastery; deterministic provenance/alignment validators plus adversarial cases |

## Moderate Pitfalls

| Pitfall | Warning signs | Prevention | Detection/test | Phase |
|---|---|---|---|---|
| **Interview fatigue/selective stopping** | Difficult skills get fewer probes; session ends after a flattering answer | Coverage matrix, resumable state, user pause, consistent minimum evidence per claimed high band | Compare probe count/coverage by score and skill; incomplete audits stay provisional | V2 |
| **Contradictions summarized away** | Final assessment contains only supportive evidence | Append-only Q&A and evidence state; explicit contradiction records | Fixture where later answer conflicts; confidence/status must reflect conflict | V1–V2 |
| **Anchor boundary false precision** | Scores such as 73 vs. 76 lack distinct observable basis | Calibrate bands first; numeric point is secondary and documented | Rater agreement by band and point; report ranges | V3 |
| **Model/prompt drift** | Same frozen case changes bands after dependency update | Pin model/prompt/schema; version outputs; replay regression suite | Drift report over gold corpus | V3–V5 |
| **Language and communication-style bias** | Mastery changes under equivalent paraphrase/translation | Score propositions/work samples, not polish; allow clarification | Paraphrase and concise/verbose paired fixtures | V2–V4 |
| **Evidence absence treated as negative mastery** | Private work or missing artifact becomes low capability | Separate confidence/availability from mastery; provisional/unknown state | Paired equal-capability cases with different artifact availability | V1–V3 |

## Technical Debt Patterns

| Shortcut | Immediate benefit | Long-term cost | When acceptable |
|---|---|---|---|
| One LLM call from transcript to final graph | Fast demo | Circular errors are untraceable and untestable | Never for hypothesis validation |
| Exact scoring formula before gold-case calibration | Easy implementation | Optimizes arbitrary numbers and fossilizes semantic errors | Never before V3 |
| Store only latest assessment | Simple files | Cannot reproduce, compare drift, or recover from poisoning | Never |
| Treat ontology as database schema | Rapid breadth | Imports irrelevant hierarchy and propagation assumptions | Never; use adapter |
| Use only STOA positives | Fast happy path | No falsification or generalization evidence | Prototype exploration only, never phase exit |
| Prompt-only truthfulness/security controls | Minimal code | Silent fabrication/injection survives | Only as defense-in-depth, never sole control |
| Copy upstream subsystem wholesale | Less design work | License/provenance ambiguity and wrong domain assumptions | Never by default |

## Security Mistakes

| Mistake | Risk | Prevention | Phase |
|---|---|---|---|
| Mixing source text with system/rubric instructions | Artifact controls assessment | Typed extraction and explicit untrusted-content boundary | V1–V2 |
| Allowing audit model write/tool privileges | Injection causes state mutation or exfiltration | Read-only least privilege; human approval; deterministic tool allowlist | V0–V2 |
| Rendering hidden PDF/repository content only to model | Human cannot review manipulation | Visible rendering/source offsets; hidden-layer detection/quarantine | V2 |
| Persisting untrusted summaries as trusted memory | Injection and false claims survive source removal | Provenance on every derived claim; invalidation cascade | V1–V2 |
| Logging sensitive employment artifacts without policy | Privacy harm and inhibited honest audit | Data-minimization, local fixtures, redaction, retention policy | V0 |

## UX Pitfalls That Corrupt Measurement

| Pitfall | User impact and validity effect | Better approach |
|---|---|---|
| Displaying target score/skill during audit | User optimizes answers toward the desired result | Reveal hypotheses after unconditioned elicitation |
| Forcing a numeric answer when evidence is insufficient | Creates false precision and discourages uncertainty | Offer provisional/unknown with explicit next evidence |
| Treating challenges as accusations | User becomes defensive or abandons audit, creating selective data | Explain that neutral verification is applied to every claim |
| Endless “relentless” interview | Fatigue makes coverage non-random | Resumable sessions, coverage display, bounded probe blocks |
| Hiding why a score changed | User agrees with flattering output but cannot contest errors | Show evidence, attribution, anchor basis, uncertainty, and version diff separately |

## Performance Traps Relevant to This Validation

Traditional scale optimization is out of scope. The relevant “scale” is evaluation combinatorics and human-review load.

| Trap | Symptoms | Prevention | When it breaks |
|---|---|---|---|
| Full cross-product of every Contribution × Skill × JD | Huge token use encourages truncation and shallow probes | Candidate retrieval followed by direct-evidence gate; mastery computed independently of JD | Even STOA with dozens of contributions/skills |
| Re-running nondeterministic extraction without caching/versioning | Cost rises and results cannot be compared | Content-addressed, version-complete cache plus replay fixtures | First calibration iterations |
| Automating all review because human labeling is slow | Fast but circular “validation” | Spend human review on stratified gold/high-disagreement cases | Immediately; this is a validity failure, not only cost |

## “Looks Done But Isn’t” Checklist

- [ ] **Interview:** one-question flow exists, but scored questions have been audited for leading language and hint introduction.
- [ ] **Contribution graph:** entities serialize, but split/merge and duplicate-evidence invariance pass.
- [ ] **Attribution:** a responsibility field exists, but team/Codex/third-party gold cases and unresolved attribution pass.
- [ ] **Ontology:** aliases resolve, but no mastery can arise from implication/parent/related edges.
- [ ] **Scores:** values fit 0–100, but each high band has observable anchor evidence and no dimension-collapse perturbation failure.
- [ ] **Confidence:** evidence text exists, but confidence changes do not silently change mastery.
- [ ] **Duration:** dates parse, but interval union, unknown precision, and overlap tests pass.
- [ ] **JD usefulness:** STOA examples look relevant, but held-out JDs beat simple baselines under blinded review.
- [ ] **Reliability:** repeated runs agree, but independent human raters and model/prompt drift are measured.
- [ ] **Security:** prompts say “ignore source instructions,” but direct, indirect, split, hidden, and persistent injection fixtures pass.
- [ ] **Provenance:** submodules are present, but exact gitlinks, licenses, adaptation ledger, and copied-file notices are verified.
- [ ] **Validation claim:** the demo is persuasive, but preregistered failure criteria and scoped generalization statement are published.

## Recovery Strategies

| Pitfall | Recovery cost | Recovery steps |
|---|---|---|
| Leading/circular interview corpus | HIGH | Quarantine affected transcripts, revise neutral protocol, recollect blinded audits, rerun gold ratings |
| Ontology-propagated mastery | MEDIUM | Remove derived mastery edges, rebuild only from direct assessments, add no-evidence invariant |
| Dimension-collapsed score formula | HIGH | Return to raw ContributionSkillAssessments, relabel anchors, recalibrate aggregation |
| Attribution collapse | HIGH | Re-audit affected Contributions with actor/subtask matrix; downgrade unverifiable high bands to provisional |
| Duration double counting | LOW | Recompute interval unions from sourced intervals; preserve old version for audit |
| Context/cache poisoning | MEDIUM | Invalidate descendants by provenance hash, rebuild from trusted sources, add cache-key/injection regression |
| STOA/JD overfit | HIGH | Freeze tuned system, acquire new sealed holdouts, report original result as development-only |
| Missing upstream attribution | MEDIUM/HIGH | Stop distribution of affected artifact, reconstruct source mapping, restore notices/license, replace unclear copies |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention phase | Verification required for exit |
|---|---|---|
| Weak/non-falsifiable validation | V0 | Preregistered endpoints, baselines, holdouts, fail/revise rule |
| Leading/self-report bias | V1–V2 | Neutral-question audit, hint log, work-sample and style-pair fixtures |
| Circular LLM judging | V0–V3 | Blind independent ratings, agreement/drift report |
| Contribution granularity | V1–V3 | Split/merge, duplicate-evidence invariance |
| Ontology propagation | V1–V3 | No-evidence propagation and version-diff tests |
| Score/dimension collapse | V1–V3 | Perturbation matrix and observable-anchor review |
| Centrality/evidence-volume misuse | V1–V3 | Paired centrality and public/private cases |
| Duration overlap | V1–V3 | Interval-union and metamorphic tests |
| Context leakage/stale cache | V1–V4 | Canary, order, JD-swap, invalidation tests |
| Team/Codex/third-party attribution | V1–V3 | Attribution fixture suite; high-band reconstruction |
| STOA/JD overfit | V0, V4–V5 | Sealed holdouts, negative controls, non-STOA replication |
| Prompt injection | V0–V4 | Full adversarial corpus and no unauthorized behavior |
| Upstream/license/architecture drift | V0 and every gate | Pin/license/provenance checks plus local invariant per adaptation |

## Sources

### Project and pinned primary sources

- `.planning/PROJECT.md` — product hypothesis, score semantics, anchors, scope, and truthfulness constraints.
- `references/README.md` — pinned commits, reuse/rejection matrix, integration rule, and license boundaries.
- `references/upstream/tabiya-compass/backend/app/agent/skill_explorer_agent/_responsibilities_extraction_llm.py` — positive responsibility separation and negative permissive ambiguity default.
- `references/upstream/tabiya-compass/backend/app/agent/linking_and_ranking_pipeline/skill_linking_tool/skills_linking_tool.py` — occupation/embedding/top-skill ranking that must not become mastery.
- `references/upstream/tabiya-compass/backend/EVALUATION_TESTS_README.md` — repeat-run evaluation precedent and acknowledged pass/fail granularity limitation.
- `references/upstream/mattpocock-skills/skills/productivity/grilling/SKILL.md` — one-question/artifact-first precedent and recommended-answer leading-risk lesson.
- `references/upstream/mind-tech-ontology/__aggregated_skills.json` and `skills/*.json` — aliases/concepts and `impliesKnowingSkills` edges.
- `references/upstream/cv-market-learning-planner/SKILL.md`, `scripts/run_cycle.py`, and `references/schemas.md` — append-only history, snapshots, deterministic-helper boundaries, and learning-level assumptions.
- `references/upstream/hiring-agent/models.py`, `evaluator.py`, `score.py`, and `github.py` — structured score/evidence contracts, direct LLM scoring, staged cache, and GitHub enrichment.
- `references/upstream/resume-matcher/apps/backend/tests/unit/test_prompt_guardrails.py`, `tests/evals/golden/cases.py`, and `app/prompts/templates.py` — truthfulness cases plus the documented gap where prompt clauses are the only guard for some invented narratives.
- All six pinned `LICENSE` files and root `.gitmodules`/gitlinks — five MIT upstreams and one Apache-2.0 upstream.

### External authoritative guidance

- [NIST AI Risk Management Framework — Measure](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) — repeatable TEVV, benchmarks, independent review, representative conditions, and generalizability limits. **Confidence: MEDIUM** (Brave provider classified MEDIUM, authoritative primary source).
- [U.S. OPM — Structured Interviews](https://www.opm.gov/policy-data-oversight/assessment-and-selection/other-assessment-methods/structured-interviews/) — standardized questions/probes, proficiency benchmarks, and independent panel rating. **Confidence: MEDIUM**.
- [U.S. OPM — Minimizing self-report response inflation](https://www.opm.gov/frequently-asked-questions/assessment-policy-faq/occupational-questionnaires/how-can-i-minimize-response-inflation-when-using-self-report-occupational-questionnaires/) — observable behavior, verification, and confirmatory assessments. **Confidence: MEDIUM**.
- [OWASP GenAI LLM01 — Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) — direct/indirect injection, repositories, JDs, résumés, hidden inputs, least privilege, and adversarial tests. **Confidence: MEDIUM**.
- [Open Source Initiative — MIT License](https://opensource.org/license/mit) — notice retention for copies/substantial portions. **Confidence: MEDIUM**.
- [Apache Software Foundation — Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.html) — redistribution, modification, notice, and attribution requirements. **Confidence: MEDIUM**.

## Research Gaps to Carry Forward

- The exact quantitative success thresholds and inter-rater statistic require the final fixture count and label distribution; choose them in V0 before results.
- A single-user validation cannot estimate population fairness or subgroup effects. V5 must state this limit rather than imply broad hiring validity.
- Appropriate work samples differ by Skill (product reasoning, software implementation, teaching, deployment, research). V2 may need skill-family-specific research.
- Legal obligations depend on what is actually copied and distributed. The ledger is mandatory; obtain legal review if substantial adaptation or distribution makes obligations unclear.

---
*Pitfalls research for: Career Evidence Graph core-hypothesis validation*  
*Researched: 2026-07-30*
