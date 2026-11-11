# Choose the Experience Candidate and Inventory Revision Contract

Type: grilling
Status: resolved
Blocked by: 01, 02, 03

## Question

What is the smallest domain contract that can represent Experience Candidates, multiple Source
links, merge and split proposals, uncertainty, every required Disposition, immutable Inventory
Revisions, and downstream admission blocks without creating placeholder Contributions or a second
source authority?

## Comments

Resolved in
[Experience Candidate and Inventory Revision Contract](../research/04-experience-candidate-contract.md).

Use one immutable proposal graph rather than a provisional `Experience`. An
`ExperienceCandidate` retains one or more exact Source links and identity facts only. One
SourceDisposition covers every Source, and one CandidateDisposition covers every candidate.
Edits, merges, and splits are represented as acyclic candidate-replacement edges; generated
candidates receive their own dispositions, so no item disappears inside an operation.

The canonical `InventoryRevision` binds the exact Phase 7 source snapshot, candidates, Source
dispositions, candidate dispositions, and parent revision. Coverage is a deterministic view over
that revision, not a second ledger. An `AcceptedInventoryRevision` is a small hash-bound seal that
also cites the passing Phase 7 verification and the user's explicit checkpoint acceptance.

Only a confirmed candidate in an accepted revision may enter Phase 9 as an audit input. Phase 8
never constructs the existing contribution-linked `Experience`, and no Phase 8 object can enter
Skill, mastery, JD, or resume admission directly. A user-added candidate must still link to a
declared self-report Source; if the bound Source Universe lacks one, the item remains unresolved
until the Phase 7 source authority produces a successor revision.
