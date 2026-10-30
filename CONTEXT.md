# Career Evidence Graph

This context defines the language used to distinguish career facts, their source material, and
their review state before capability assessment. Application behavior follows
[APP-01–18](docs/single-job-flow.md); research review terminology does not create
extra application approvals or a second source of career facts.

## Language

**Source Universe Revision**:
An immutable declaration of the career-information sources and category coverage in scope at one
career-fact cutoff.
_Avoid_: Source list, repo list

**Source**:
A stable logical origin of career information, whether available, unavailable, documentary, or
self-reported. A Source is about career history; it is not itself an Experience.
_Avoid_: Evidence, Experience, file

**Capture**:
One immutable acquired version of a Source, with its own acquisition time and content identity.
_Avoid_: Current file, Source

**Experience Candidate**:
A source-grounded proposal that one real-world undertaking, engagement, or period of activity
belongs in the career inventory. It has not yet been accepted by the user.
_Avoid_: Experience, repository, resume entry

**Candidate Skill Link**:
A source-grounded, versioned suggestion that one specific Experience Candidate may warrant
examination for a Skill. It retains source/capture identity, a locator, candidate wording, and
extraction version, but establishes no canonical Skill, responsibility, confidence, mastery, or
assessment. The same candidate wording may be linked independently to multiple Experience
Candidates. A later Contribution-Skill assessment need not have a Candidate Skill Link; the link
is discovery and audit context, never a scoring prerequisite.
_Avoid_: Skill score, Experience capability, global source skill

**Candidate Skill Prompt Context**:
An optional, user-visible reminder of Candidate Skill Link wording and source context used while
auditing the linked Experience Candidate. It helps recall and is not an assertion that the user
has the Skill; inability to recall a source's wording or project detail is not itself a negative
capability conclusion.
_Avoid_: Leading evidence, memory test, assessment basis

**Experience**:
One user-accepted real-world undertaking, engagement, or period of career-relevant activity. It
may be described by multiple Sources and later decomposed into Contributions.
_Avoid_: Project repository, source document, job title

**Disposition**:
The explicit review outcome assigned to a Source or Experience Candidate so that no known item is
silently omitted.
_Avoid_: Classification, score

**Inventory Revision**:
An immutable set of Experience Candidates, Source dispositions, review decisions, and coverage
state bound to one Source Universe Revision.
_Avoid_: Current inventory, resume

**Accepted Inventory Revision**:
An Inventory Revision whose exact identity the user has explicitly accepted after every known
Source and Experience Candidate received a Disposition.
_Avoid_: Latest inventory, complete resume

**Unresolved Experience**:
An Experience Candidate deliberately retained because its identity or facts remain uncertain. It
prevents omission but cannot enter downstream Contribution or Skill assessment.
_Avoid_: Weak Experience, rejected Experience

**Contribution**:
The minimum auditable fact unit inside an Experience, describing one bounded outcome or piece of
work whose responsibility, assistance, evidence, and capability implications can be reviewed.
_Avoid_: Experience, task list, repository activity

**Question Layer**:
The purpose of a question in the ordered project interview: project overview,
project depth, or transfer. It is separate from question difficulty.
_Avoid_: Mastery band, difficulty level

**Question Difficulty**:
The demanding, intermediate, or simple level within a depth or transfer probe.
It adjusts the capability prompt; it is not a mastery score or a question layer.
_Avoid_: Skill score, interview stage

**Project Interview Plan**:
A preparation artifact containing one overview question and separate depth and
transfer plans for the same selected Contributions. Questions declare evaluation
criteria before answers. Binding to supplied context does not admit inventory or
establish question quality, capability, or mastery.
_Avoid_: Accepted assessment, complete interview record

**Context Request**:
A request for a source label, artifact, or prior context needed to understand the
active question. Preserve it separately from capability answers. It does not
consume a question, lower difficulty, or establish inability.
_Avoid_: Incorrect answer, skip, negative capability evidence

**Transfer Evidence**:
An answer that demonstrates reasoning about adapting an inspected mechanism to a
similar problem under an explicit changed condition. It can support a bounded Skill
judgment after review. It does not assert completed implementation, deployment, or
repeated responsibility across real contexts.
_Avoid_: New real-world Contribution, project result

## Application workflow language

**Current contract — 2026-10-20:** The definitions below follow
[the application specification](docs/single-job-flow.md). The system handles one
job at a time. Important missing facts, conflicts or unknown results wait on that
job; only recommendation ingestion continues. Optional preparation/research modes
are separate from the default continuous application flow.

**Career History Library (职业经历库)**:
The authority for career, education, project, Contribution, responsibility and
result facts and their retained source material. Explicit user additions or
corrections are recorded directly with source and history. Ambiguous project
ownership or important factual ambiguity requires clarification. Saving a fact
does not award a Skill score or seal a research corpus.
_Avoid_: Application answer cache, generated résumé as fact authority

**Career Fact (职业事实)**:
A reusable statement about an actual career activity, identity, responsibility,
method or result, with its applicable time, status and source context; a question,
discussion turn or hypothetical answer is not itself a Career Fact.
_Avoid_: Conversation entry, source paragraph, assessment conclusion

**Experience Context Item (经历背景资料)**:
A sourced description that belongs to one Experience but is not the user's own
work, such as a website, repository or other person's statement. It can explain
an Experience to the matching model; it never counts as the user's activity.
_Avoid_: third-party Career Fact, user responsibility

**Education Record (学历记录)**:
The single structured authority for each degree: field, institution, dates and
whether it is awarded or in progress. Application answers, qualification checks
and résumé education are derived from it, never kept as separate copies.
_Avoid_: degree answer, profile education copy, template-only education

**Matching View (匹配视图)**:
The one model-facing projection of the Career History Library, grouped by
Experience with the Education Record, Career Facts and Experience Context Items
kept apart. It omits receipts and audit notes and is rebuilt only when the library
changes; stored records stay the authority for every check.
_Avoid_: per-job source dump, audit record

**Experience Main Content (经历主要内容)**:
The consolidated current account of one Experience, retaining distinct career
facts and their responsibility boundaries without repeating the discussions,
source copies or maintenance history used to prepare it.
_Avoid_: Conversation archive, résumé selection, concatenated source material

**Experience Workstream (经历工作方向)**:
A coherent area of actual work belonging to one stable Experience, such as backend
development, frontend development or organizational management. Several Workstreams
may reference the same Experience-owned fact or source without duplicating it.
_Avoid_: Separate Experience by default, repository boundary, conversation topic

**Career Preparation Material (职业整理依据)**:
Questions, answers, discussions and documents used to establish or correct career
facts; retaining this material preserves traceability without making each item
an independent career fact or a default job-matching input.
_Avoid_: Experience Main Content, Career Fact, assessed capability

**Skill Retrieval Term (技能检索词)**:
A skill or technology term grounded in saved career facts or an explicit user
statement, with its experience and responsibility context; it helps find relevant
content without establishing a mastery score or independent personal responsibility.
_Avoid_: Assessed Skill, repository keyword as personal capability

**Recommendation Ingestion (推荐收录)**:
Durable storage of original email content, recommendation entries and links.
Completion permits the dedicated label and archive operation. It does not require
full JD retrieval or mean any recommended job was applied to.
_Avoid_: Mail marked read, full JD acquisition, submission

**Application Queue (申请队列)**:
A persistent ordered set of deduplicated recommended jobs and their progress.
It accepts new recommendations while job execution is running or waiting.
Only one job advances at a time. A user skip preserves that job for a later return.
_Avoid_: Finite approved batch, concurrent applications, inbox unread list

**Job Recommendation (岗位推荐)**:
A mail- or page-sourced lead to a possible job opportunity. Its presence does not establish
that the original JD is complete, the opening is current, or the user is qualified.
_Avoid_: Confirmed opportunity, complete JD, eligible application

**Material Preparation Batch (材料准备批次)**:
An optional explicitly selected set for the alternate material-preparation mode.
Its historical finite-batch review and stop rules do not define the continuous
application product. Materials can also be generated directly within one job.
_Avoid_: Default application queue, submitted campaign, common résumé

**Sequential Application Cycle (逐岗申请闭环)**:
Handling one job through JD analysis, matching, tailored materials, filling,
manual final Submit and observed outcome before advancing to the next job.
An important blockage waits on the current job. A user skip preserves progress
and permits the next job; known low-match, duplicate or unavailable jobs retain
their skip reason. An unknown submission result pauses for verification.
_Avoid_: Generating all résumés first, concurrent jobs, treating skip as submitted

**Material Preparation Priority (材料准备优先级)**:
An explainable recommendation about which job's materials to prepare first, informed by relevant
career material and applicable preferences. It is separate from qualification and a hiring outcome.
_Avoid_: Skill mastery, hiring probability, confirmed eligibility

**Job Qualification Status (岗位资格状态)**:
A comparison of explicit job conditions with applicable applicant facts, retaining support,
conflicts and unresolved conditions separately. Unstated conditions are not confirmed eligibility.
_Avoid_: Match score, preparation priority, employer acceptance

**Qualification Information Pending (资格待补充)**:
A qualification comparison with missing or conflicting applicant facts after
consulting the applicable career and information libraries. Uncertainty remains
visible while useful analysis and materials may proceed. It blocks execution only
when the next required operation needs an important unresolved fact; then the
current job waits rather than processing other jobs.
_Avoid_: Automatic résumé refusal, confirmed ineligibility, deferred group of questions

**Single-Job Application Task (单岗位申请任务)**:
A persistent record linking one job's JD and actually relevant inputs to analysis,
materials, manual edits, worker progress and observed outcome. It does not need
an explicit material-confirmation object. A checkpoint is distinguished from the
current page; a read does not repeat an external action.
_Avoid_: Browser session, submitted application, canonical Skill assessment

**Job Match Analysis (岗位匹配分析)**:
A source-bound comparison of one JD's requirements with the available career evidence,
including supported, partial, gap and unknown judgments and their limits.
It does not confirm personal mastery or establish a reusable application answer.
_Avoid_: Grill-Me assessment, verified qualification, permission to infer an answer

**Job Match Score (岗位匹配分)**:
A score calculated under an identified match policy for one JD and one career-source revision.
Unknown evidence and unmet hard conditions remain explicit alongside the score.
It is separate from Skill mastery, evidence confidence and an employer's hiring decision.
_Avoid_: Skill score, hiring probability, confirmed eligibility

**Job Similarity (岗位相似度)**:
The similarity between the actual work and requirements described by two JDs. It identifies
historical jobs whose associated résumés warrant a reuse check; different titles or industries
can describe similar work, while a shared title alone does not establish similarity or confirm
that a résumé can be reused. It is an internal judgment used to accelerate résumé preparation,
not a user-facing score or rating. The résumé reuse process is internal and adds no dedicated
status, explanation or candidate-selection interface to normal résumé preparation.
_Avoid_: Job Match Score, title similarity, résumé similarity, confirmed résumé reuse

**JD Work Profile (JD工作内容画像)**:
A reusable, source-bound description of the actual work and requirements in one JD version,
used to find similar historical jobs across titles and industries. It is distinct from the
user's job-match assessment and does not establish résumé suitability or personal capability.
_Avoid_: User Skill profile, job title category, original JD, résumé approval

**Resume Reuse Candidate (简历复用候选)**:
A résumé version eligible for consideration when preparing material for another job; eligibility
does not establish suitability for the new JD or permission to send. An accepted, reviewed version
may qualify even if it was never submitted.
_Avoid_: Approved new-job résumé, submitted résumé, sending permission

**Resume Rewrite Reference (简历改写参考)**:
An existing résumé or draft used to inform wording and selection for a new version; an unreviewed
draft may serve this role without becoming an accepted résumé or confirmed facts. The resulting
new version receives automatic fact and layout checks for ordinary applications; high-value jobs invite focused user adjustment under APP-06. No routine new-version acceptance is required.
_Avoid_: Accepted résumé, inherited material acceptance, confirmed career facts

**Local Resume Revision (简历局部修改)**:
A change to an otherwise suitable résumé's ordering, supported emphasis, or a single project
addition or replacement while the remaining selection and structure stay suitable. The result
is a distinct new version, with unaffected content and the original version retained.
_Avoid_: Whole-résumé rewrite, unchanged accepted PDF, new career facts

**Resume Regeneration (简历重新生成)**:
Preparation of a new résumé version when the principal experiences must be reselected and the
overall emphasis reorganized for the target JD, using supported career facts and retaining prior versions.
_Avoid_: Cosmetic rewording, single-project revision, invented experience

**Resume Generation (简历生成)**:
Preparation of job-specific résumé material by selecting, arranging and expressing currently
available career facts, including explicit user additions retained with source and history.
Generation may reuse those facts directly without an independent approval stage;
it cannot invent experience, responsibility or results.
_Avoid_: Experience discovery, career-fact interview, new factual evidence

**Resume Base Document (简历底稿)**:
An existing full résumé used as the starting point for a job-specific draft; its presence does not confirm every claim it contains.
The base remains distinct from each job-specific version.
_Avoid_: Confirmed facts, reviewed job résumé, approved application attachment

**Resume Verification Queue (简历待核对清单)**:
Retained résumé statements whose verifiable source or responsibility attribution remains unresolved.
They stay outside the new résumé body until verified for inclusion, while their original records remain available.
_Avoid_: Rejected experience, evidence of inability, confirmed résumé content

**JD Narrative Emphasis (岗位表述侧重)**:
The prioritization and framing of supported experience statements for a specific JD.
It may change emphasis, ordering, detail and inclusion for one job version, with omitted experiences and reasons retained for restoration; facts and responsibility attribution remain unchanged.
_Avoid_: New capability evidence, invented achievements, responsibility reassignment

**Experience Review Group (经历审核组)**:
An optional material-review view showing original and proposed wording, sources
and responsibility for one experience. It supports focused editing or separate
research review. Ordinary automatic applications do not require confirmation of
every group or renewed approval of unchanged content.
_Avoid_: Mandatory application gate, sending permission

**Tailored Resume Draft (专用简历草稿)**:
A versioned job-specific selection and rewrite of attributable career material,
with sources and retained history. The system checks ordinary drafts and PDFs
automatically; high-value jobs invite focused user adjustment after the draft.
The draft does not establish Skill mastery or final application submission.
_Avoid_: New career truth, submitted résumé, mandatory draft approval

**Cover Letter (求职信)**:
A job-specific letter that opens with a concrete application motivation and uses one or two
relevant Experiences to demonstrate technical strengths and suitability for the role.
_Avoid_: Résumé summary, generic motivation answer, evidence of Skill mastery

**Cover Letter Body (求职信正文)**:
The application-specific narrative between the fixed salutation and sign-off. The same wording
serves text and file delivery; contact details, salutation, sign-off and signature remain separate.
_Avoid_: Complete LaTeX document, second career-fact source, PDF-only content

**Application Material Requirement (申请材料要求)**:
A job- or form-specific instruction identifying a material and its required or optional delivery.
An unverified requirement remains distinct from confirmed absence of a delivery requirement.
_Avoid_: Material generation status, blank required flag, JD silence as proof of absence

**Motivation Answer (动机问答)**:
An answer to a particular employer question about interest or suitability, with that question's
scope and limits. It does not automatically substitute for a separately requested Cover Letter.
_Avoid_: Cover Letter, reusable personal fact

**Submitted Application (已提交申请)**:
An application whose final user-operated submission has an attributable explicit
success result observed on the site, in a confirmation message or another clear
source. A user answer can resolve an uncertain result; routine submission does
not need a separate user assertion. Filled fields or draft-save evidence do not
establish this state.
_Avoid_: Application readiness, draft saved, hiring outcome

**Application Receipt (申请接收回执)**:
An attributable confirmation that the final application was received. The system
can capture it automatically after manual Submit. It need not be typed into a
separate form by the user and does not establish a hiring outcome.
_Avoid_: Visible filled form, draft-save evidence, offer

**Application Control Interface (申请控制界面)**:
The TomorrowStar interface where the user selects applications, assigns résumés,
controls batch execution, and reviews progress.
_Avoid_: Employer application form, application receipt

**Application Review Page (申请复核页面)**:
A live employer form filled for one selected application, which the user can inspect
before final submission. Its presence does not establish employer receipt.
_Avoid_: Application receipt, permanently saved draft

**Application Batch (申请批次)**:
A user-selected set of existing application records to prepare together.
Each record keeps its own job identity and outcome; a batch does not imply submission.
_Avoid_: New application record, submitted campaign

**Application Batch Pause (申请批次暂停)**:
A deliberate stop of new automatic steps in an Application Batch while retaining its
identity and progress for continuation. It is separate from cancellation and submission.
_Avoid_: Cancelled batch, saved browser form

**Application Resume Selection (岗位简历选择)**:
The version used for one application, selected by the system or adjusted by the
user. Effective results are reused. Changed inputs update only affected parts;
user-edited materials remain the base. The system evaluates applicability and
merges updates, asking only about important conflicts.
_Avoid_: Filename alone, automatic replacement of manual edits, blanket reconfirmation

**Application Run Progress (申请执行进度)**:
The state of preparing and filling one selected application, including waits for input
or review. It is separate from submission and receipt outcomes.
_Avoid_: Application submitted, employer receipt

**Application Input Wait (申请补充等待)**:
A wait on the current job because an important required fact or clarification is
unresolved. No other job advances during this wait. New emails may be ingested.
An answer is saved once and reused within its applicable scope. The user can
choose to skip without resolving the current question.
_Avoid_: Continue other jobs, aggregate a round of questions, application failure

**Application Input Item (申请补充项)**:
A question or clarification that awaits user input, with its conditions and affected applications.
Several applications share one item only when the question and applicable conditions are equivalent.
_Avoid_: Job task, universal question

**Application Readiness (申请就绪)**:
The condition that an application's required inputs and continuation checks are satisfied.
Readiness alone does not resume a paused Application Batch or establish submission.
_Avoid_: Running task, application submitted

**Application Cancellation (申请任务取消)**:
The user's stop of further automatic work on selected applications while retaining prior progress
and outcomes. It does not withdraw data or an application already sent to an employer.
_Avoid_: Application withdrawal, deleted history

**Application Answer Library (申请答案库 / 通用信息库 / 信息库)**:
Application facts, reusable answers and miscellaneous information with source,
time and applicability. Career facts remain authoritative in the Career History
Library. A user answer is saved without another confirmation; the system judges
reuse scope. Routine generated non-factual narrative does not become an asserted
career fact or a Skill score.
_Avoid_: Second career fact authority, career Skill graph

**Confirmed Application Answer (已确认申请答案)**:
An answer supplied or corrected by the user, retained with source and relevant
conditions. It is reused when applicable without reconfirmation. The system may
also compose routine narrative from known facts; it must not invent personal facts.
_Avoid_: Fabricated factual claim, requirement for all generated prose to be approved

**Answer Scope (答案适用范围)**:
The conditions under which a Confirmed Application Answer is valid, such as a country,
employer, role, or time condition. Similar wording alone does not establish the same scope.
_Avoid_: Universal answer, question text

**Default Answer Scope (默认答案范围)**:
The system's initial judgment of the conditions in which an answer applies,
based on question meaning, country, employer, role and time where relevant.
The user can correct it. Only important genuine ambiguity needs clarification.
_Avoid_: Mandatory scope-approval step, universal permission

**Application Question Equivalence (申请问题等价)**:
Two application questions ask for the same applicant fact within the same Answer Scope,
with compatible time, conditions, and answer-option meanings. Different wording can be equivalent;
text similarity alone does not establish equivalence.
_Avoid_: Similar question, inferred answer

**Application Question Mapping (申请问题映射)**:
The system's semantic interpretation of a site's question and options against
available facts in both libraries. Exact text or a predeclared field-key list is
not required. Mapping does not invent or expand a personal fact.
_Avoid_: New applicant fact, exact-label-only reuse

**Single-Application Answer (仅本次答案)**:
A Confirmed Application Answer that the user limits to one application and excludes
from the reusable Application Answer Library.
_Avoid_: Remembered answer, deleted external submission

**Unknown Application Question (未知申请问题)**:
A question not yet resolved from available facts and context. The system first
judges meaning, applicability and importance. Low-impact narrative can be drafted
autonomously. An important required unknown factual answer stops the current job;
the user's answer is saved to the appropriate library, unless explicitly limited
to this job, and the remaining steps continue without another confirmation.
_Avoid_: Every unfamiliar question requires a user answer, permission to invent facts

**Application Checkpoint (申请执行检查点)**:
A retained record of one application's progress, input references and observed outcomes.
It can remain after its employer page or execution process no longer exists.
_Avoid_: Live page, employer-saved draft

**Application Runtime Observation (申请运行观察)**:
A time-bound observation of the current application execution or employer page.
It is separate from a retained Application Checkpoint and does not establish submission.
_Avoid_: Historical page presence, application receipt

**Application Preparation Measurement (申请准备测量)**:
An observational record of one request to prepare a selected application, including
its automatic work, queueing, user waits, pauses, interruptions and unobserved time.
Continuation remains part of the same preparation. Changed inputs can start a linked new preparation.
It grants no action permission and cannot establish an answer or capability.
_Avoid_: Action authorization, CPU time, application submission

**Complete Preparation Outcome (完整准备结果)**:
A measured outcome where the selected application is ready for manual review at its
agreed support level, its current inputs and page are verifiable, and record synchronization
is complete. Earlier page readiness and pending synchronization remain separate outcomes.
It does not establish final submission or employer receipt.
_Avoid_: Filled field alone, submitted application, employer acceptance

**Application Intervention (申请人工介入)**:
A request for or observed user action to resolve one unplanned preparation blockage.
One shared answer can resolve a single request affecting several applications.
Required routine review is recorded separately. Waiting duration does not establish active effort.
_Avoid_: Every click, routine final review, user waiting time as working time

**Application Draft Save Evidence (申请草稿保存证据)**:
Evidence that an identified employer form accepted particular fields or an attachment as a draft.
It does not establish final application submission or employer receipt of that application.
_Avoid_: Visible field value alone, final submission confirmation

**Application Form Capability (申请表单能力)**:
A specific behavior an application form supports, such as answering a field, revealing a required
question, saving a draft or accepting an attachment. Evidence is bounded to the observed form behavior.
_Avoid_: Platform-wide support, support for every company form

**Application Recovery (申请恢复)**:
Re-establishing the conditions for safe application preparation after an interruption,
using retained progress and freshly verified application facts and outcomes.
It does not imply preservation of the original employer page or automatic continuation of a paused Application Batch.
_Avoid_: Browser restart, preserved original page, application submission

**Automatic Takeover (自动接管)**:
Handing the current job's original application page to the configured Takeover Executor when the
fill script cannot continue, at most once per Continue and never including final Submit. When the
takeover is unavailable, the job waits with the stated reason instead of retrying or switching executor.
_Avoid_: Retry, fallback to another executor, background autofill

**Takeover Executor (接管执行者)**:
The one AI agent the user selects to perform Automatic Takeover, running with a dedicated, isolated
configuration and sign-in rather than the user's personal agent context.
_Avoid_: Fallback chain, personal Codex or Claude session
