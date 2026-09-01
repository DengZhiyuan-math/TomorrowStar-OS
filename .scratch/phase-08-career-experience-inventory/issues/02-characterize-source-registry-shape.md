# Characterize the Private Source Registry for Inventory Consumption

Type: research
Status: resolved
Blocked by: none

## Question

What exact schema, capture metadata, category coverage, availability states, and safe access seams
does the Phase 7 private Source Universe Revision expose to Phase 8, and which fields are usable
for candidate inventory without interpreting Source presence as career truth or capability?

## Comments

## Answer

Phase 8 must consume the existing registry through one new read-only, integrity-checking seam in
`workspace.py`. The snapshot may drive coverage, discovery, and lineage only; availability,
capture metadata, repository metadata, and repeated descriptions cannot establish an Experience
fact or capability. See
[Characterize the Private Source Registry for Inventory Consumption](../research/02-source-registry-shape.md).
