# Career Evidence Graph

This context defines the language used to distinguish career facts, their source material, and
their review state before capability assessment.

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
