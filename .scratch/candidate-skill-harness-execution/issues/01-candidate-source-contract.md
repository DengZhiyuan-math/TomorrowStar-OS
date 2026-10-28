# Define the Candidate-Source Contract

Type: grilling
Status: resolved

## Question

What minimum, versioned harness contract represents an external source's
candidate Skills and source links while making it impossible for that record
to serve as a mastery, responsibility, or Contribution-Skill assessment input?

## Answer

Use a versioned **Candidate Skill Link** scoped to exactly one Experience
Candidate. It retains the source/capture identity, source locator, candidate
wording, and extraction version only. It deliberately has no canonical
`skill_id`, responsibility, evidence confidence, mastery, or assessment field.
The same candidate wording may appear in independent links for multiple
Experience Candidates; this is not a shared global capability conclusion.

The existing candidate-only private source registry and derived-mapping
lineage remain the reusable source/capture foundation. A later harness
contract must consume that identity rather than introduce a second source
store. Only a completed Grill-Me audit can map a candidate link to an audited
Contribution and then permit existing Contribution-Skill proposal logic.
