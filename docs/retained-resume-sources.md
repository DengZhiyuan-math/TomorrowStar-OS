# Retained résumé source reuse

## Current product requirement — 2026-10-20

The [single-job flow](single-job-flow.md) defines product behavior; the
[development plan](development-plan.md) tracks the implementation changes.
Existing usable material is reused automatically. Changed facts update only the
affected content, using the user's edited version as the base. Model configuration
changes do not invalidate usable analysis or material. System checks establish
which source and PDF are being used; each version needs no separate human acceptance.

Career facts come from the career library. Explicit user additions and corrections
are saved there with their source and history. Application information and reusable
answers remain in the information library. A bad retained capture or reference
marks only the affected material; other sources and the job analysis remain usable.
An important unresolved conflict pauses the current job. It does not trigger a
whole-library approval or silent processing of the next job.

## Existing manifest implementation and remaining differences

The following describes the current `retained-resume-sources/v1` mechanism.
Its human-acceptance capture chain and whole-snapshot invalidation are existing
implementation restrictions, not requirements to carry into the simplified flow.
This documentation change does not migrate captures or change runtime behavior.

Material preparation can reuse an existing human decision through an explicit
`sources/retained-resume-sources.json` manifest in the selected private career
workspace. An accepted directory name, profile text or inventory membership
does not grant this authority.

The manifest uses `retained-resume-sources/v1`. Its `captures` object contains
`task`, `source`, `pdf` and `approval`, each with a workspace-relative `path` and
`sha256`. Captures must remain in a hidden workspace directory so the catalog
does not send raw task or approval history as model document context.
The loader rejects redirects, changed captures, duplicate fields and invalid
bindings. It reuses the retained material acceptance validator and checks the
actual source and PDF against the original human content-and-layout decision.
It reads existing bytes; it does not compile or renew an export acceptance.

Each `groups` entry contains:

| Field | Meaning |
| --- | --- |
| `title` | Documentary label |
| `start_line`, `end_line` | Inclusive full-source line interval |
| `source_kind` | `accepted_resume` or `education` |
| `context_source_ids` | Existing registered contribution sources whose responsibility and boundaries remain attached |
| `education_profile_locator` | Specific `profile.education[index]`, or null for work |
| `education_profile_sha256` | Digest of that unchanged structured record, or null for work |

An operator must first compare the actual existing records and accepted source
to establish the initial correspondence. A digest detects later changes; it
does not prove the initial mapping. The bounded education parser supports one
ordinary `\entry{institution}{period}` per mapped credential. It checks degree
level, institution identity under conservative normalization, ongoing/awarded
state, period and explicit expected completion date, including status in detail.
Unknown formats and actual conflicts stop reuse. Full academic subject and
program-name equivalence still require the initial documentary comparison;
the parser does not perform semantic credential evaluation. Unchanged recorded
facts do not require another applicant interview.

Education reuse requires the same complete base source, exact original bytes,
and the actual education interval. Multiple excerpts must be consecutive and
belong to the same source and receipt. Education cannot support a work claim or
be copied to a different interval to avoid review. Editors cannot alter the
fixed credential. Extra narrative detail need not occur verbatim in an already
accepted shorter rendering; the complete structured record remains preserved.

Work sources retain the previously accepted wording and cited responsibility
boundaries, including collaboration, coding assistance and design-only limits.
No source is relabeled `User` merely to make a draft eligible. Profile editorial
statements and inventory identity remain separate from contribution evidence
and assessed capability.

`input.json` and `source-snapshot.json` retain full local provenance. The model's
`model-input.json` references exact numbered base lines instead of duplicating
accepted excerpts, carries responsibility and boundary metadata, and compacts
JSON document whitespace without removing values. Configuration manifest and
raw acceptance captures are excluded from model document context. The existing
full-generation request-size guard still applies without truncation. Analysis
uses the same bounded 128,000-byte budget and retains its explicit coverage
report. Exact decimal literals and whitespace inside strings remain unchanged.

The existing loader binds analysis to a whole source snapshot and the generated
preparation path still waits for group review and specific PDF acceptance. These
are differences from the current product requirement above. Historical analysis,
original material decisions and capture bytes remain intact; they do not require
new user approvals merely because a different job or configuration is being used.
