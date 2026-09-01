# Resume and Personal-Website Seed Interfaces

Status: resolved research note

## Question

Which readable local artifacts should seed the initial career backbone, what structure do they
expose, where do they overlap, and why can neither be treated as a complete or authoritative
inventory?

The Phase 8 destination is an accepted, source-reconciled inventory, not a resume-derived claim
set ([map](../map.md), [Phase 8 context](../../../.planning/phases/08-full-career-inventory-review-and-seal/08-CONTEXT.md)).
This note therefore uses "authoritative interface" narrowly: the preferred readable input for
capturing what the presentation artifact currently says. It does **not** mean authoritative user
truth.

## Primary local inputs inspected

To preserve the public/private boundary, the exact private locators, labels, content, item counts,
and content identities are omitted from this note. The inspected inputs are referenced by generic
interface labels:

- **Private interface R — resume source family.** Human-readable LaTeX sources for several
  role-oriented resume variants, plus generated PDFs and build by-products.
- **Private interface W — website content source.** JavaScript content modules consumed by a
  static-site renderer, plus route and component files that present those modules.
- **Private interface L — resume claim ledger.** A structured JSON review aid stored beside the
  resume sources.

Only the first-party local source files were used. No external link, rendered public page, search
result, or third-party description was treated as a source.

## Interface decision

### Resume

Use the **LaTeX source family as a union of discovery clues**. Do not select one tailored version
as the canonical career history. The source variants expose recurring sections for profile,
education, professional or internship activity, selected project/research activity, mathematical
research, teaching/technical communication, and funding. Within those sections the useful seed
fields are display title, organization or context, free-text period, short description or bullets,
and occasional links.

The generated PDFs are presentation derivatives of the readable LaTeX and should not be parsed
when the source is available. Auxiliary compiler files are not career sources.

Private interface L can be captured as a **separate clue source**, but not used as the Experience
authority. It exposes a stable claim identifier, source-fact text, candidate wording, source
pointers, verification state, allowed-use hints, interview-detail hints, a boundary, risk notes,
and a verification date. Several of those fields cross the Phase 8 boundary into responsibility,
claim wording, or downstream use. Phase 8 may use only identity and reconciliation clues from this
interface; it must not inherit responsibility, verification, capability, or resume-admission
judgments.

### Personal website

Use the **JavaScript content modules as the readable website seed interface**. The route and
component files are renderers, not independent career sources. The content modules expose these
review-relevant shapes:

- education: degree, institution, period, detail;
- employment or internship: role, organization, period, detail, points;
- side projects: title, description, link, tags;
- research: name, links, points;
- thesis work: name, context, period, supervisor, points;
- teaching and seminars: role, period, link, points;
- schools or related activity: title, date, link;
- specialized project cards: title, type, summary, links, and labelled narrative sections with
  text or bullets.

Identity/contact fields, interests, display highlights, skill lists, tags, credentials, and visual
copy are presentation data. They are not Experience candidates by default. Links may identify
other declared Sources, but linked repositories, papers, and reports must still be reconciled
through the Phase 7 registry rather than silently imported.

## Overlap and reconciliation behavior

The resume family and website modules repeat much of the same education, professional activity,
research, teaching, and project material. They often vary in selection, ordering, title wording,
date precision, and the amount of narrative detail. Specialized resume variants also collapse or
omit items to fit a target role, while the website expands some items into category pages.

Treat repetition as a **merge proposal**, not corroboration and not a second Experience. A proposed
candidate should retain links to every source occurrence. Matching may use normalized title,
organization/context, date overlap, and linked-source identity as deterministic clues. Any
conflict or uncertain match remains separate or unresolved for user review, consistent with the
Phase 8 no-auto-merge decision
([Phase 8 context](../../../.planning/phases/08-full-career-inventory-review-and-seal/08-CONTEXT.md)).

## Limits

Neither interface is complete or authoritative because:

- both are curated presentation artifacts and intentionally omit material;
- resume variants are target-specific and may select, compress, or reword the same activity;
- website categories are navigation structures, not a career ontology;
- periods are mostly free text, date precision varies, and some items omit organization, context,
  or dates;
- entries have no common stable Experience identifier or retained cross-source lineage;
- descriptions may mix identity facts with goals, result claims, responsibility wording, metrics,
  skill labels, or resume-oriented framing;
- the inspected local artifacts include working-tree material, so extraction must bind to an exact
  private capture rather than assume a public or committed version;
- an external link is only a pointer to another Source and cannot fill gaps in the captured item;
- repeated wording cannot establish independence, responsibility, delivery, mastery, confidence,
  or completeness.

These limits implement the established rule that a resume can provide discovery clues but cannot
establish inventory completeness, responsibility, mastery, or confidence
([Phase 7 context](../../../.planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md)).
They also avoid materializing the final `Experience` contract prematurely: the current final model
requires Contribution lineage, which Phase 8 deliberately does not create
([domain model](../../../src/career_evidence_graph/domain/models.py)).

## Recommended extraction contract

For each source occurrence, extract only a proposal containing:

- source reference and source-local locator;
- source-facing title;
- proposed inventory category;
- organization or context when explicitly present;
- start/end text exactly as present, plus separately parsed dates only when unambiguous;
- a short source-grounded identity description;
- explicitly present links to other declared Sources;
- uncertainty and conflict notes;
- a presentation-role marker such as resume variant, website summary, or website detail page.

Exclude skills, tags, responsibility levels, assistance, mastery, confidence, JD relevance,
interview hints, and optimized candidate wording. Preserve raw wording in the private capture, but
keep it out of public logs and artifacts as required by the private-source boundary
([requirements](../../../.planning/REQUIREMENTS.md)).

## Conclusion

The initial backbone should be proposed from the union of the readable LaTeX resume sources and
the website's JavaScript content modules. PDFs, renderers, compiler by-products, skill/tag fields,
and the claim ledger's downstream judgments are not inventory authorities. The union is still only
a high-signal first pass; completeness comes from reconciling it against every Source in the Phase
7 registry and obtaining explicit user dispositions for all candidates.
