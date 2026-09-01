# Derive Reviewable Repository-to-Experience Clustering Signals

## Question

Which deterministic, reviewable repository metadata and first-party project signals can propose
that several repositories or local copies belong to one real-world Experience, distinguish forks,
tutorials, experiments, and abandoned work, and leave ambiguous merges unresolved?

## Conclusion

Use a two-layer resolver, not a similarity score:

1. **Repository identity resolution** decides whether two Sources are views or copies of the same
   repository. It may auto-link only when a stable repository identity or a canonical remote
   resolution matches exactly.
2. **Experience clustering** proposes whether distinct repositories describe the same real-world
   undertaking. It always remains reviewable and must have at least one explicit first-party
   relationship signal. Similar names, technologies, timestamps, or shared Git ancestry are never
   enough to auto-merge Experiences.

This distinction is necessary because forks and templates intentionally share history, while a
single product can intentionally span repositories with unrelated histories. The output should be
an evidence-bearing proposal with a disposition, not a probability and not a capability claim.

## Research basis

The available private source captures expose two complementary shapes:

- remote-repository provenance includes canonical repository naming, URL, fork/archive flags,
  default-branch commit and tree identities, lifecycle timestamps, visibility, and primary
  language;
- authorized local-project provenance includes the configured project identity, Git root, branch,
  HEAD, origin, and an inventory of tracked and non-ignored project files.

An authenticated, read-only GitHub metadata pass confirmed that the live API can additionally
provide stable repository IDs, fork parent, description, homepage, topics, template state, and
archive state. GitHub documents that `parent` and `source` are returned for forks, and that the
repository response includes template, topic, archive, URL, and lifecycle fields
([GitHub REST: Get a repository](https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#get-a-repository)).
GitHub also recommends persisting its opaque global node ID as the cross-API reference for an
object ([GitHub: Using global node IDs](https://docs.github.com/en/graphql/guides/using-global-node-ids)).
Repository README content can be acquired at a named ref through the official contents endpoint
([GitHub REST: Get a repository README](https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28#get-a-repository-readme)).

The private corpus also contains first-party root documentation and project manifests that state
relationships and lifecycle intent more precisely than repository names do. No private values or
findings from that inspection are reproduced here.

Any metadata used by the inventory proposer must be bound to an immutable acquisition record.
Live API fields that are absent from the Phase 7 capture cannot silently become cutoff-time facts;
they require a new timestamped capture or must be labelled as current enrichment pending review.

## Signal ladder

The resolver should retain every original Source and record which signal fired. “Automatic” below
means an automatic Source-to-repository link, never automatic user acceptance of an Experience.

| Priority | Deterministic signal | Meaning | Permitted action |
|---|---|---|---|
| A1 | Same stable host repository ID | Same hosted repository object even when its address differs | Auto-link Sources to one repository identity; preserve both Source lineages |
| A2 | A local `origin` resolves through the host API to the same stable repository ID | Local checkout or worktree of that hosted repository | Auto-link local and remote Sources; retain local branch, HEAD, and dirty-state provenance separately |
| A3 | Exact canonical remote URL after host resolution | Same current remote repository | Auto-link when stable ID lookup is unavailable; retain the unresolved-ID limitation |
| B1 | Exact commit or root-tree identity | Content snapshots overlap exactly at that revision | Propose `snapshot-copy`; do not auto-link because a fork or template may share the object |
| B2 | Verified common Git ancestor | Histories are related | Propose `shared-history`; never infer same repository or Experience from this alone |
| C1 | Host-declared fork parent/source | Repository belongs to an upstream fork network | Mark fork lineage and prevent history-based auto-merge |
| C2 | Host-declared template repository | Repository was generated from a template | Mark template lineage and prevent tree/history similarity from implying one Experience |
| D1 | First-party documentation explicitly links sibling repositories as components of one named undertaking | Distinct repositories intentionally belong to one product/research system | Create an Experience merge proposal for user review |
| D2 | A checked-in workspace, submodule, deployment, or package manifest explicitly references another repository/component | Machine-readable first-party relationship | Create an Experience merge proposal; describe the relationship type |
| D3 | Distinct repositories declare the same canonical product identifier, deployment domain, API contract, or documentation hub | Strong cross-repository product relation | Create a merge proposal only when the identifier is explicit and stable |
| E1 | Matching normalized title tokens, component suffixes, descriptions, topics, organization, or overlapping dates | Candidate similarity | Rank items together for review; never merge automatically |
| E2 | Matching language, framework, directory shape, file names, creation/push proximity, or inactivity | Weak similarity | Display only as supporting context; never determine identity or disposition |

Git provides the exact primitives needed for the history signals: `rev-parse --verify` resolves and
validates commit objects ([git-rev-parse](https://git-scm.com/docs/git-rev-parse)), and
`merge-base` finds common ancestors or checks ancestry
([git-merge-base](https://git-scm.com/docs/git-merge-base)). A checked-in `.gitmodules` file
explicitly records submodule paths and URLs, so it is a stronger relationship statement than a
name resemblance ([gitmodules](https://git-scm.com/docs/gitmodules)).

GitHub keeps redirects for renamed repository web and Git operations, while recommending that
local remotes be updated. Therefore, resolve remotes through the host rather than treating the raw
URL string as permanent identity
([GitHub: Renaming a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)).

## Classification rules

These rules propose review dispositions; none establishes responsibility, Contribution, Skill, or
mastery.

### Local copy, backup, mirror, or quarantine

- Exact stable repository identity: attach as another Source to the same repository identity.
- Exact content/history without a resolvable remote: propose `snapshot-copy` and leave the merge
  unresolved until the user confirms its role.
- First-party text explicitly saying backup, mirror, quarantine, export, or public/private copy:
  propose `source-copy`, not a separate Experience.
- A different branch, uncommitted state, or later local work does not create a new Experience by
  itself; preserve those facts as Source provenance.

### Fork

- Prefer host-declared `fork`, `parent`, and `source` over name or history heuristics.
- A fork is a repository relationship, not an Experience. Propose `background-only` unless another
  source explicitly ties it to a career undertaking that deserves an Experience candidate.
- Divergence, commits, pull requests, or repository ownership cannot establish the user's role or
  capability in Phase 8.

### Tutorial, course, exercise, or study repository

- Require explicit first-party wording in the repository description, README, syllabus/course
  metadata, or root project manifest.
- Propose either an `education` Experience candidate or `background-only`; never silently promote
  it to a project Experience.
- Several repositories may support one educational period only when a course/program identifier
  or another explicit source connects them. Shared subject matter is insufficient.

### Experiment, prototype, proof of concept, or research artifact

- Use explicit lifecycle/purpose wording from first-party documentation or checked-in manifests.
- Propose `research`, `project`, or `background-only` according to the stated undertaking, while
  retaining an uncertainty field if the category is unclear.
- Small size, notebooks, missing deployment configuration, or short activity windows do not prove
  “experiment” or lack of career relevance.

### Archived, abandoned, deprecated, or superseded work

- A host archive flag is deterministic evidence that the repository is read-only and presented as
  no longer actively maintained, but it is not evidence that the underlying Experience is invalid
  or unimportant ([GitHub: Archiving repositories](https://docs.github.com/en/repositories/archiving-a-github-repository/archiving-repositories)).
- “Abandoned,” “deprecated,” and “superseded” require explicit first-party wording or an explicit
  replacement link. Otherwise use neutral `inactive-or-unclear` wording.
- Last-push age, sparse commits, missing releases, or a deleted deployment cannot independently
  justify exclusion.

### Ambiguous project relation

Leave the proposal unresolved when any of these applies:

- similar names but no explicit cross-reference;
- shared Git history with fork/template status unknown;
- a local project has no resolvable remote and only weak content resemblance;
- sources disagree on title, organization/context, dates, or whether two components were one
  undertaking;
- one repository appears to contain several distinct undertakings or several career periods;
- a portfolio, notes vault, or source collection mentions multiple projects but is not itself the
  undertaking.

## Deterministic proposal procedure

1. **Bind inputs.** Read only Sources in the chosen Source Universe Revision. Store the capture
   identity and acquisition time for every inspected field or document.
2. **Normalize remotes for lookup.** Parse supported HTTPS/SSH remote forms, remove only transport
   syntax and an optional `.git` suffix, and ask the repository host for canonical identity.
   Preserve the original remote string privately.
3. **Resolve same-repository edges.** Apply A1-A3. Store `same_repository` with the exact signal
   code. Never discard duplicate Source records.
4. **Mark lineage guards.** Apply C1-C2 before commit/tree comparisons so forks and templates are
   not mistaken for copies of the user's own undertaking.
5. **Add history hints.** Apply B1-B2 only when required objects are available locally or in the
   captured source. Record `snapshot-copy` or `shared-history`; do not upgrade them silently.
6. **Extract explicit relationships.** Inspect description, homepage, topics, README, root project
   manifests, workspace/submodule files, deployment configuration, and linked portfolio/resume
   entries. Each proposal stores a private source locator and a short reason code.
7. **Propose Experience clusters.** A distinct-repository cluster requires at least one D-class
   signal. E-class signals may order the review packet but cannot create the cluster alone.
8. **Apply classification proposals.** Add fork/tutorial/experiment/archive/copy lifecycle tags and
   a proposed Source disposition. These are review aids, not accepted facts.
9. **Surface conflicts.** Any contradictory high-priority signals produce `unresolved`, never a
   tie-breaking numeric score.
10. **Present for review.** Show the proposed Experience, attached Sources, signal codes, private
    source locators, conflicts, proposed disposition, and explicit alternatives: confirm, edit,
    split, merge, exclude with reason, background-only, or unresolved.

## Required private records

For each relation proposal, retain privately:

- left and right Source IDs;
- capture identities and observation times;
- relation type and signal code;
- normalized host identity when available;
- source field or document locator supporting the relation;
- conflict flags and why automation stopped;
- proposed action and final user decision;
- the inventory revision that consumed the decision.

Readable values, external paths, repository labels, private URLs, source-derived totals, content
identities, and extracted snippets must never appear in public logs, tests, planning artifacts, or
error messages.

## Synthetic acceptance cases

Implementation can validate the policy without private fixtures:

1. Two remote syntaxes resolve to one stable repository ID: auto-link Sources, keep both lineages.
2. Two repositories share an exact commit but one is a fork: record shared history, do not merge
   Experiences.
3. Two component repositories explicitly name and link the same product: create a merge proposal,
   not an accepted merge.
4. Two repositories have similar names and timestamps only: keep separate and mark relation
   unresolved or weakly suggested.
5. A README explicitly identifies course exercises: propose education/background-only review.
6. A README explicitly identifies a prototype: propose a lifecycle tag without inferring skill.
7. A repository is archived with no replacement statement: retain it for inventory review and do
   not call it abandoned.
8. A local source has no remote but matches a captured tree: propose snapshot-copy and require user
   confirmation.
9. A source collection mentions several undertakings: split candidates while dispositioning the
   collection Source once for every derived link.

## Decision

Adopt the two-layer deterministic resolver and the A-E signal ladder. Permit automatic linking
only for exact repository identity (A-class). Require human review for every cross-repository
Experience cluster, every lifecycle/category proposal, and every ambiguity. Treat repository
activity strictly as discovery context; it cannot produce responsibility or capability claims.
