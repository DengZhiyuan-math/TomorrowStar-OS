# Feature Research

**Domain:** User-authoritative career inventory, evidence-governed Skill graph, and real-JD hypothesis validation
**Project:** Career Evidence Graph — v1.1 Full Career Graph and Real JD Validation
**Researched:** 2026-08-28
**Confidence:** HIGH for project boundaries and acceptance behavior; MEDIUM for external product and governance analogues

## Executive Recommendation

Build v1.1 as a sequence of user- and evaluator-visible acceptance checkpoints, not as a graph expansion project:

1. account for every known career item as of a recorded cutoff and obtain an explicit user seal;
2. materialize one canonical, status-aware graph in which unresolved content remains visible but non-authoritative;
3. admit mastery only through the already implemented reviewed Contribution–Skill path;
4. obtain exactly three user-selected raw JDs, correct every extracted requirement against its source, and seal each accepted packet immutably; and
5. run the already frozen evaluation protocol and issue the evidence-backed decision even when the result is partial or negative.

The graph is an internal source of reviewed user truth. The milestone outcome is whether that truth is useful for JD-relevant career decisions. A visually complete graph, a high match score, or a polished report is not the outcome.

## Existing Capability vs New Work

Do not reimplement the v1.0 foundation. Extend it only where the real full-career and real-JD workflow requires new behavior.

| Capability | v1.0 status | v1.1 feature decision |
|---|---|---|
| Strict `Experience → Contribution → Skill`, with Evidence supporting Contribution | Existing | Reuse unchanged; broaden the data from the sealed STOA fixture to the user's confirmed career inventory |
| Artifact-aware, one-question audit with pause/resume and separate responsibility/assistance rounds | Existing | Reuse per Contribution; add scheduling and coverage over the full inventory, not a second interview engine |
| Immutable conclusion and assessment review lineage | Existing | Reuse as the only route from audited Contribution to score-eligible assessment |
| Anchor-aware, no-inflation aggregation | Existing | Reuse; pending, evidence-insufficient, or responsibility-unresolved items must never enter it |
| Content-free, source-bound JD packet and read-only graph comparison | Existing foundation | Add real raw-JD interpretation, item-level correction, whole-packet acceptance, and exactly-three corpus custody |
| Frozen deterministic/adversarial/stability/human/blind evaluation charter | Existing contract | Execute it on the sealed real graph and three JDs; retain every failure, disagreement, and limitation |
| Full-career inventory completeness and user cutoff seal | Missing | New P1 feature |
| One canonical graph containing both authoritative and unresolved known content | Missing | New P1 feature |
| Status-aware JD uncertainty | Missing | New P1 feature: unreviewed or unresolved evidence must produce uncertainty, not fabricated capability or an automatic zero |
| Evidence-backed `supported` / `partially-supported` / `rejected` decision | Missing | New P1 milestone terminus; `rejected` blocks expansion |

## Authority and Status Semantics

The requested labels must not become one overloaded lifecycle enum. The same item can be a confirmed career fact and still have insufficient evidence or unresolved personal responsibility. Surface a simple primary status to the user, but retain separate authority axes underneath.

| Visible state | User meaning | Evaluator meaning | Mastery effect |
|---|---|---|---|
| `pending` | This known item is recorded but still needs decomposition, audit, correction, or review | Coverage is explicit; the next required action and blocker are named | None |
| `confirmed` | The user confirms that the Experience, Contribution, Evidence reference, or candidate Skill belongs in the inventory as represented | Establishes inventory authority only; it is not an assessment review | None by itself |
| `insufficient-evidence` | The item remains part of career history, but available material cannot support the claimed capability boundary | Must preserve what is missing and what was checked | None; JD use is `uncertain` / `missing-evidence`, not positive support |
| `unresolved-responsibility` | The work exists, but user/team/other-person/agent/third-party responsibility is not resolved | Attribution gate is incomplete and must fail closed | None; never borrow team or tool work into user mastery |
| `reviewed` | A human reviewed attribution, anchor fit, all three assessment judgments, and the complete basis | Eligible for the existing admission policy and immutable review lineage | May establish mastery only if admitted |

Two consequences are non-negotiable:

- Inventory completeness can be confirmed while some items remain pending or unresolved. “Complete” means all known items are accounted for as of the cutoff, not that every item is proven or scored.
- Absence of a reviewed assessment is not a mastery score of zero. A relevant pending or unresolved item must keep a JD judgment uncertain; only reviewed evidence can support a positive claim, and only reviewed evidence below a requirement boundary can justify a capability shortfall.

## Feature Landscape

### Table Stakes (Required for v1.1)

| Feature | Why expected | Complexity | Acceptance-oriented behavior |
|---|---|---:|---|
| Declared source and cutoff manifest | “Full career” is otherwise an untestable claim | MEDIUM | Records cutoff time, included source snapshots, hashes/locators, declared unavailable sources, and the user's scope statement |
| All-known-item inventory review | Users must be able to see omissions and incorrect merges before the graph becomes authoritative | HIGH | Every discovered or user-added item is confirmed, corrected, split, merged with lineage, or retained with an explicit blocker; no silent drop is allowed |
| Coverage by supported Experience type | A resume alone commonly omits projects, research, publications, teaching, open source, or earlier work | MEDIUM | Coverage report accounts for employment, project, research, publication, education, teaching, open-source, internship, and related history, including explicit “none known” responses |
| User confirmation seal | The system cannot declare someone else's career inventory complete | HIGH — USER BLOCKING | User reviews final counts and unresolved states, adds missing items, and signs the exact inventory hash and cutoff; later changes create a new version |
| One canonical status-aware graph | Downstream comparison needs one identity and lineage for every known item, not separate reviewed and unreviewed truth stores | HIGH | Stable IDs and merge/split/revision lineage prevent duplicates; reviewed and unresolved nodes are queryable in one snapshot |
| Review-only mastery projection | The graph must remain complete without inflating capability | HIGH | Aggregated Skill mastery reads only admitted, substantively reviewed Contribution–Skill assessments; status-only and candidate edges are excluded deterministically |
| Status-aware uncertainty in JD comparison | Pending evidence is unknown, not proof of absence | HIGH | A JD requirement touching only pending, insufficient-evidence, or unresolved-responsibility content returns `uncertain` with the precise missing review/evidence/attribution reason |
| Full-career audit work queue | Reviewing every Contribution in one uninterrupted session would block the user | MEDIUM | Prioritizes unresolved items needed by the three JDs while retaining complete coverage; pause/resume and “why this is next” are visible |
| Exactly three user-selected raw JDs | The empirical test requires real source authority and a bounded corpus | HIGH — USER BLOCKING | System accepts neither two nor four; selection belongs to the user; exact UTF-8 source bytes, source identity, hash, and acquisition metadata are retained privately |
| Source-bound JD requirement proposal | A parsed requirement without a reconstructable source is not reviewable | HIGH | Every item links to a valid source span/hash and separates explicit text from reviewer-supplied interpretation; prompt-like JD text remains inert data |
| Item-level JD correction | Extraction errors must be correctable before scoring | HIGH — USER BLOCKING | User can edit fields, split/merge items, add omitted requirements, and mark false requirements; original proposal and every correction remain in lineage |
| Immutable whole-JD acceptance | Evaluation inputs must not change after results are visible | MEDIUM — USER BLOCKING | Each corrected packet receives explicit whole-packet acceptance bound to raw-source and proposal hashes; any later change creates a new packet and invalidates dependent runs |
| Sealed three-JD evaluation corpus | Evaluators need to prove which graph and JDs were tested | MEDIUM | Corpus manifest binds one canonical graph hash, exactly three accepted packet hashes, charter version, policy/configuration versions, and baseline assignment |
| Frozen evaluation execution | Happy-path output is insufficient evidence | HIGH | Runs deterministic, adversarial, three-attempt stability, human, blind-baseline, holdout/leave-one-out, and feasible minimal replication checks exactly as preregistered |
| Decision ledger and limitations | The milestone must close with an empirical decision, including a negative one | HIGH | Records gate-by-gate evidence, critical failures, disagreements/adjudication, deviations, and the frozen `supported` / `partially-supported` / `rejected` result |

### Differentiators (Core Value)

| Feature | Value proposition | Complexity | Observable proof |
|---|---|---:|---|
| Completeness with truthful unknowns | Builds a reusable career record without pretending every career fact is already auditable | HIGH | User can seal all-known-item coverage while unresolved items remain visible and excluded from mastery |
| Separate inventory, assessment, and admission authority | Prevents a user confirmation, parser confidence, or reviewer action from silently becoming a Skill score | HIGH | Tests show `confirmed ≠ reviewed ≠ admitted`; only the final authority path changes mastery |
| Uncertainty-preserving matching | Avoids the common error “not in the reviewed graph, therefore cannot do it” | HIGH | Counterfactual pending/unresolved records change a requirement from unsupported to uncertain without creating positive support |
| Immutable raw-JD interpretation | Makes each requirement disputable and reproducible instead of treating model extraction as the JD | HIGH | Reviewer can reconstruct each accepted item from the exact raw bytes and trace every correction from proposal to acceptance |
| Same truthful graph, three different relevance views | Tests whether a reusable capability graph helps across real roles | MEDIUM | Each JD may change selected Contributions, gaps, and route while graph and mastery hashes remain unchanged |
| A product hypothesis allowed to fail | Prevents roadmap momentum or UI polish from substituting for evidence | HIGH | The finalizer emits the frozen negative or partial result when gates fail and blocks unsupported expansion claims |

### Anti-Features (Do Not Build)

| Anti-feature | Why requested | Why problematic | Required alternative |
|---|---|---|---|
| Resume-as-complete-career import | Fast bootstrap | Resumes are selective artifacts and can omit older or non-targeted work | Treat each resume as one declared source; require category coverage and user addition/confirmation |
| Automatic “full career” declaration | Removes a user checkpoint | Completeness is unknowable without the subject's scope and cutoff authority | Seal “all known items as of cutoff,” with explicit unavailable sources and unresolved states |
| One universal status field | Appears simpler | Collapses confirmed existence, evidence sufficiency, responsibility, review, and admission; valid combinations become impossible | Preserve separate authority axes and derive the visible work state |
| Bulk accept for inventory or JD extraction | Saves clicks | One bad merge or requirement can contaminate the canonical graph or evaluation | Require item review plus one hash-bound whole-artifact confirmation |
| Scoring pending or unresolved nodes as zero | Produces total coverage | Confuses missing review with missing capability and biases the JD result | Return uncertainty/missing evidence and keep mastery absent |
| Letting unreviewed claims contribute a discounted score | Feels nuanced | Any nonzero contribution launders an unreviewed claim into mastery | Exclude it completely until the existing review/admission path succeeds |
| Skill propagation from JD wording, résumé wording, ontology adjacency, repository presence, or title | Fills sparse graphs | None proves personal capability or responsibility | Use these only to propose audit candidates and follow-up questions |
| Choosing the three JDs for the user | Creates a tidy experiment | Allows cherry-picking and removes source authority | User selects exactly three; system records the selection without substituting examples |
| Re-parsing a live URL during evaluation | Keeps postings current | The source can disappear or change after acceptance | Evaluate retained raw bytes; a changed posting is a new source/version |
| Silent correction of an accepted JD | Keeps workflow moving | Rewrites experimental input after results are known | Create a new immutable packet and rerun all dependent evaluation |
| One composite career/JD score | Easy headline | Mixes stable mastery with confidence, context, duration, and target-specific relevance | Keep these values separate and report requirement-level judgments and limitations |
| Averaging away a critical fabrication or unstable run | Preserves a good mean | Hides exactly the truthfulness failure the milestone tests | Treat the frozen critical-fabrication rule as a hard failure and report each attempt |
| Graph explorer as the milestone goal | Visually persuasive | Can consume the phase while proving neither completeness nor JD usefulness | Use inspectable reports/CLI views sufficient for review; defer graph visualization |
| Hiring, interview, offer, or employment-effectiveness claim | Makes results sound commercially strong | The three-JD development evaluation cannot establish these outcomes | State only the bounded core-hypothesis result and its generalization limits |

## Acceptance Behavior by Actor

| Checkpoint | User must be able to | Evaluator must be able to | Blocking condition |
|---|---|---|---|
| Inventory proposal | Inspect sources and every proposed item; add, edit, split, merge, or flag uncertainty | Reconcile source candidates to final IDs and see no unexplained omission | Any source candidate lacks a disposition or any supported Experience category lacks a user response |
| Inventory seal | Confirm the exact snapshot and cutoff without being forced to resolve every unknown | Verify signature/reviewer, counts, hash, and unresolved-state summary | No explicit user confirmation or snapshot changed after confirmation |
| Assessment readiness | See why a Contribution is pending and pause/resume its existing audit | Prove unresolved/evidence-insufficient items never entered aggregation | Any mastery result cites a non-reviewed or detached assessment |
| JD selection | Supply and identify exactly three real JDs | Verify corpus count, distinct source hashes, and user-selection record | Count is not exactly three or a source is synthetic/substituted without disclosure |
| JD item review | Correct every interpreted field with adjacent source context | Reconstruct spans, proposal, corrections, and reviewer decisions | Missing/invalid span, unreviewed item, or silent model repair |
| JD acceptance | Accept each corrected packet as a whole | Verify immutable acceptance against raw and proposal hashes | Accepted bytes differ from reviewed bytes or an accepted packet was overwritten |
| Evaluation | Provide only scheduled reviews; not be asked to change truth to improve results | Reproduce every run, see all attempts, blind assignment, baseline, disagreements, and holdouts | Graph/JD/charter drift, hidden exclusion, missing attempt, or unsealed review |
| Decision | See a plain explanation of what is supported, what failed, and what remains uncertain | Reapply frozen decision rules mechanically and enumerate blockers | Decision label cannot be regenerated from retained gate evidence |

## Feature Dependencies

```text
[Declared career sources + cutoff]
              │
              v
[All-known-item proposal] ──> [item correction / split / merge / missing-item add]
              │                                      │
              └──────────────────────────────────────┘
                                                     v
                                      [user-confirmed inventory seal]
                                                     │
                                                     v
                                      [canonical status-aware graph]
                                         │                       │
                                         │                       └──> pending / insufficient /
                                         │                            unresolved stay non-scoring
                                         v
                              [existing Contribution audit]
                                         │
                                         v
                              [existing assessment review]
                                         │
                                         v
                              [review-only mastery projection]

[Raw JD 1] ─┐
[Raw JD 2] ─┼──> [source-bound proposals] ──> [item correction] ──> [three immutable packets]
[Raw JD 3] ─┘                                                               │
                                                                            │
[frozen charter + sealed graph] ─────────────────────────────────────────────┘
                                      │
                                      v
 [deterministic + adversarial + stability + human + blind + holdout evaluation]
                                      │
                                      v
                 [supported / partially-supported / rejected decision]
```

### Dependency Notes

- **Inventory proposal precedes canonicalization:** merging first can erase omissions and responsibility distinctions.
- **Inventory seal precedes evaluation readiness:** the system must know the coverage denominator before claiming a full-career graph.
- **Complete inventory does not require complete mastery:** explicit unresolved states prevent an endless audit from blocking the experiment while keeping uncertainty truthful.
- **Assessment review precedes mastery projection:** existing admission and aggregation code remains the sole score authority.
- **All three JD packets must be accepted before any final evaluation output:** otherwise the corpus can be tuned after results are visible.
- **The evaluation reads but never writes the graph:** any graph change requires a new graph snapshot and full rerun.
- **Decision finalization follows human/blind review and adjudication:** automated checks cannot substitute for the frozen usefulness criteria.

## v1.1 MVP Definition

### Launch With

- [ ] One user-confirmed, hash-bound inventory of all known career items as of a recorded cutoff, including explicit source/category coverage and unresolved states.
- [ ] One canonical graph containing every confirmed and unresolved known item with stable identity and revision lineage.
- [ ] A deterministic review-only mastery projection using the existing audit, assessment, admission, and no-inflation aggregation paths.
- [ ] A status-aware comparison rule that treats pending, insufficient-evidence, and unresolved-responsibility content as uncertainty rather than capability or zero mastery.
- [ ] Exactly three user-selected raw JDs with source-bound proposals, item-level correction, and immutable whole-packet acceptance.
- [ ] One sealed evaluation corpus binding the graph, three JDs, policies/configuration, baseline assignment, and frozen charter.
- [ ] Complete deterministic, adversarial, stability, human, blind-baseline, holdout/leave-one-out, and feasible replication evidence.
- [ ] One reproducible final decision with blockers, limitations, deviations, and no hiring-outcome claim.

### Add Only After This Decision

- [ ] Dynamic JD-tailored résumé selection and rewriting — only if the decision supports a scoped expansion, with every claim traced to reviewed Contributions.
- [ ] Human résumé wording review, diff, layout, and export — after truthful selection/rewriting exists.
- [ ] Evidence-producing gap work and post-work reassessment — after gap judgments and graph usefulness are supported.
- [ ] More JDs or additional users — only to test a named generalization gap, not to rescue the preregistered three-JD result.

### Future Consideration

- [ ] Continuous LinkedIn/GitHub/portfolio synchronization and arbitrary document ingestion.
- [ ] Multi-user SaaS, authentication, billing, recruiter/employer workflows, or applicant ranking.
- [ ] Large skill-ontology ingestion, embeddings-first inference, graph database, or interactive graph explorer.
- [ ] Job application automation, job-board scraping, cover letters, generic interview prep, and application tracking.
- [ ] Claims about interview, offer, hiring, employment, or long-term career outcomes.

## Feature Prioritization Matrix

| Feature | User value | Implementation cost | Priority |
|---|---:|---:|---:|
| Source/cutoff manifest and coverage ledger | HIGH | MEDIUM | P1 |
| Item correction and user inventory seal | HIGH | HIGH | P1 |
| Canonical status-aware graph | HIGH | HIGH | P1 |
| Review-only mastery projection | HIGH | MEDIUM | P1 |
| Status-aware JD uncertainty | HIGH | HIGH | P1 |
| Exactly-three raw-JD intake and selection custody | HIGH | MEDIUM | P1 |
| Item-level JD correction and immutable acceptance | HIGH | HIGH | P1 |
| Sealed real-input evaluation runner | HIGH | HIGH | P1 |
| Human/blind review and decision finalizer | HIGH | HIGH | P1 |
| Full-career audit prioritization view | MEDIUM | MEDIUM | P1; needed to avoid user blockage |
| Dynamic résumé generation | HIGH downstream | HIGH | P2 after supported expansion |
| Gap Sprint and reassessment | HIGH downstream | HIGH | P2 after supported expansion |
| Graph visualization or production UI | LOW for validation | HIGH | P3 |

## Competitor and Precedent Analysis

External pages establish interface expectations, not efficacy. Vendor-reported interview or hiring outcomes were not used as evidence.

| Precedent | Publicly emphasized behavior | Useful expectation | v1.1 approach |
|---|---|---|---|
| Europass | Broad personal profile of experiences, projects, achievements, skills, and documents; user selects a subset for each CV | Maintain one broad career inventory and derive role-specific views later | Add explicit cutoff/completeness seal, Contribution granularity, review states, and mastery authority |
| LinkedIn Profile | User adds/edits/deletes Experiences and associates Skills with them | Item-level user control and contextual Skill association are table stakes | Preserve correction but do not let association establish mastery |
| Teal | Master résumé, duplicated role-specific versions, pasted-JD keyword/skill matching | Users expect a broad source and job-specific selection | Keep résumé generation deferred; evaluate a reviewed career graph rather than résumé wording |
| Huntr | Extracts JD keywords/responsibilities/qualifications and lets users accept, edit, or ignore AI suggestions with explanations | Fine-grained correction and explanation are expected in AI-assisted career tools | Review requirement items against exact source spans, then immutably accept the whole packet before scoring |
| Jobscan | Compares résumé text and JD text for hard/soft skill match | A simple, reproducible text baseline is familiar | Use only as the frozen weak baseline; never treat text overlap as capability |
| W3C PROV / Web Annotation | Models derivation, revision, attribution, primary source, and source segment selectors | Lineage and source anchoring should survive transformation | Use project-native hashes/versions/spans; do not add RDF infrastructure |
| NIST AI RMF / APA / OSF | Repeatable documented evaluation, human oversight, relevant conditions, preregistered decisions | Evaluation evidence and human authority must be fixed before conclusions | Execute the existing charter and retain negative outcomes, variance, and disagreement |

## Research Flags for Planning

- **Inventory reconciliation is HIGH complexity:** duplicate Experiences, overlapping projects/employment, sparse old records, and user-added missing items need explicit merge/split lineage. Plan dedicated fixtures before scaling data entry.
- **Status-aware JD semantics is HIGH complexity:** distinguish missing reviewed evidence from reviewed evidence of a lower capability. This likely requires phase-specific tests around `unsupported`, `uncertain`, `missing-capability`, and `missing-evidence`.
- **User time is a real blocker:** inventory seal, assessment reviews, selection/acceptance of three JDs, and blind/human evaluation are hard checkpoints. Plan resumable review packets and visible readiness criteria; do not hide them behind automation.
- **Exactly three means corpus custody, not just a count:** replacement after acceptance must invalidate dependent results and require a full rerun.
- **Decision rules must remain frozen:** if the current charter lacks a desired numeric threshold, record that limitation instead of adding a post-hoc rule after observing the three JDs.
- **“Full career” remains bounded:** the only defensible claim is all known items from declared sources as of the user-confirmed cutoff. The evaluation cannot establish universal career completeness or downstream hiring effectiveness.

## Sources

### Direct project evidence — HIGH confidence

- `.planning/PROJECT.md` — v1.1 goal, active target features, product boundary, and truthfulness constraints.
- `.planning/milestones/v1.0-REQUIREMENTS.md` — completed foundation versus deferred real-input evaluation.
- `validation/jd/evaluation-charter.json` — frozen three-attempt case inventory, baseline, blind-review, critical-fabrication, and limitation contract.
- `src/career_evidence_graph/domain/models.py` — existing assessment, review, JD source-span, accepted-packet, comparison, and gap semantics.
- `src/career_evidence_graph/audit/workflow.py` — existing one-question audit, attribution, unresolved/skip behavior, and immutable conclusion review.
- `src/career_evidence_graph/assessment.py` — existing review/admission authority, no-inflation aggregation, immutable versions, and policy calibration.
- `src/career_evidence_graph/jd.py` — existing private intake, exact-three readiness checks, reviewed-graph loader, source-bound comparison, graph immutability, and charter loader.

### Official and primary external cross-checks — MEDIUM confidence

- [Europass: complete a profile](https://europass.europa.eu/en/how-complete-my-europass-profile), [what Europass is](https://europass.europa.eu/en/what-europass), and [create a CV](https://europass.europa.eu/en/create-europass-cv) — broad editable profile followed by selective CV construction.
- [LinkedIn Help: manage the Experience section](https://www.linkedin.com/help/linkedin/answer/a593695) — item-level experience editing and Skill association.
- [Microsoft Research: Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/research/?p=564561) — efficient correction, scoped uncertainty, explanations, feedback, and visible consequences.
- [W3C PROV-O](https://www.w3.org/TR/prov-o/) — primary source, derivation, revision, attribution, association, delegation, and invalidation lineage.
- [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) — source quote/position selectors and source-state concerns.
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) and [Measure Playbook](https://airc.nist.gov/airmf-resources/playbook/measure/) — documented repeatable TEVV, human oversight, independent/domain review, and operationally relevant evaluation.
- [APA: Responsible Use of AI in Assessment](https://www.apa.org/science/programs/testing/responsible-ai-assessment) — validity, reliability, transparency, and human oversight in AI-assisted assessment.
- [OSF: Registrations and Preregistrations](https://help.osf.io/article/330-welcome-to-registrations) — time-stamped read-only plans and predeclared decision criteria.
- [Wei et al., Human Baselines in Model Evaluations](https://proceedings.mlr.press/v267/wei25s.html) — baseline design and reporting rigor.

### Current product pages — MEDIUM confidence for advertised features only

- [Teal Resume Builder](https://www.tealhq.com/tools/resume-builder) — master résumé, per-role versions, and JD matching.
- [Huntr Resume Tailor](https://api.huntr.co/product/resume-tailor) — requirement-oriented matching and per-suggestion accept/edit/ignore controls.
- [Jobscan tutorial](https://www.jobscan.co/jobscan-tutorial) — résumé/JD hard- and soft-skill text matching as a familiar baseline.

---
*Feature research for: v1.1 Full Career Graph and Real JD Validation*
*Researched: 2026-08-28*
