# Synthetic JSON resume contracts

All names, institutions, facts and locators in this directory are synthetic.
They do not represent a private library, a real writer call, or accepted materials.

All generated resumes are in English. Source library materials may use other
languages; their original language is not restricted by this contract. The demo
and its output target an English resume, including literal `%`, `#`, and `_` text.

`single-experience.json` contains a program-owned `plan` and a fixed synthetic
writer response in `fragments`. Run `assemble_content(**fixture)` to obtain
`resume-content/v1` JSON. The plan supplies fixed profile, education and assigned
experience metadata. The writer supplies only referenced content items. The
education status is `in_progress`; dates do not imply an awarded degree.

The assignment binds `experience_id` to the snapshot's canonical `candidate_id`
and `assignment_revision`. Sources have stable IDs and locators. Facts carry
source references, responsibility, actual/planned status and scope. This contract
does not assign research capability scores. `title` is a fixed display title;
it is not an unstructured experience body. The separate optional `role` preserves
the fixed role alongside a project title. Optional organization/role/dates/location may be absent; a personal project does
not need an organization to be used.

`invalid-fragments.json` contains complete writer responses to reject against the
main fixture's assignment. Cases cover wrong experience/candidate/revision,
unknown references, duplicate item IDs, empty completion, mutually exclusive
completion/missing-material results, and forbidden presentation fields.

`semantic-review-cases.json` contains structurally valid overclaims. The expected
semantic review result is `reject`: planned work became completed work, or team
participation became leadership. Passing JSON validation is expected for these
cases. Schema validation cannot establish the truth of prose. No semantic model
review has run for this fixture.

All model and dictionary inputs are revalidated. `validate_content` also binds a
normalized content hash to `revision`. A caller must obtain patch permissions
independently of the model output:

```python
revised = apply_content_patch(
    content,
    {
        "schema_version": "resume-content-patch/v1",
        "base_revision": content["revision"],
        "changes": [
            {
                "item_id": "item-demo-1",
                "field": "text",
                "expected": old_text,
                "value": reviewed_text,
            }
        ],
    },
    allowed_targets=[{"item_id": "item-demo-1", "fields": ["text"]}],
)
```

Only `text` and `links` are patchable. Fixed profile, education, experience
metadata, provenance and references cannot be rewritten by a review patch.
`allowed_targets` is a trusted program argument, not a field accepted in model
JSON. Stale revisions, old-value mismatches and human/protected targets fail.

The separate trusted `retained` argument to `assemble_content` accepts
`resume-retained/v1`, `application_id`, and `items` containing `experience_id`
and a protected human `item` with an `edit_source`. Human wording, including
whitespace, is preserved; references need not be invented. An existing item ID
is replaced in place, or a new human item is appended to that experience.
Global writer output cannot declare itself human. Retained global content,
human deletions/reordering, existing TeX/Prism edits, library corrections and
migration remain for J05/J06. Existing data and manual files are not read or
rewritten by these pure functions.

## Export schema from the actual models

The installed library is Pydantic v2. `v1` denotes the JSON contract version.
Do not hand-maintain a second schema. From the checkout root, export a standalone
schema for the desired model with `model_json_schema()`, or export all contracts
with the existing Pydantic `TypeAdapter`:

```bash
PYTHONPATH=src UV_CACHE_DIR=/private/tmp/tomorrowstar-j01-j02-uv-cache \
uv run --locked --offline --no-sync python -B - <<'PY'
import json
from pydantic import TypeAdapter
from career_evidence_graph.application_resume_content import (
    ContentPatch, ExperienceFacts, ExperienceFragment, NeedsMaterialFragment,
    ResumeContent, ResumePlan, RetainedContent, WritingAssignment,
)
# Individual model: print(json.dumps(ResumeContent.model_json_schema(), indent=2))
contracts = TypeAdapter(
    ExperienceFacts | WritingAssignment | ExperienceFragment | NeedsMaterialFragment
    | ResumePlan | ResumeContent | ContentPatch | RetainedContent
)
print(json.dumps(contracts.json_schema(), ensure_ascii=False, indent=2))
PY
```

Schema exports describe field types and allowed structure. Identity binding,
reference membership and patch permissions additionally require the public
validation functions, which receive the actual fixed assignment or trusted scope.
