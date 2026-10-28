"""A resume review consumes one exact ready sibling letter through its existing review."""

import json
from copy import deepcopy

from test_cover_letter_content import ready
from test_j05_content_generation import delivery as delivery
from test_j05_content_generation import submit

from career_evidence_graph import application_experience_latex as generation
from career_evidence_graph.application_resume_content import content_revision


def test_resume_review_captures_ready_letter_and_records_the_same_revision(delivery, tmp_path):
    store, identifier, plan = delivery
    letter = ready(tmp_path / "letter")["content"]
    letter["application_id"] = "application-demo"
    letter["revision"] = content_revision(letter)
    provider_calls = []
    store.cover_letter_provider = lambda app, analysis: (
        provider_calls.append((app, analysis)) or letter
    )
    generation.configure_generation(store, identifier, writing_plan=plan)
    submit(delivery)
    candidate = generation.assemble_generation(store, identifier)
    context = generation.review_context(store, identifier)
    assert context["sibling_cover_letter"] == letter
    assert provider_calls == [("application-demo", None)]
    recorded = deepcopy(letter)
    letter["paragraphs"][0]["text"] = "Later independent human edit."
    letter["revision"] = content_revision(letter)
    reviewed = generation.review_generation(
        store,
        identifier,
        candidate_sha256=candidate["candidate_sha256"],
        reviewer_id="independent-reviewer",
        passed=True,
        issues=[],
        content_patch=None,
    )
    assert reviewed["review"]["sibling_cover_letter_revision"] == recorded["revision"]
    assert context["sibling_cover_letter"] == recorded
    assert len(provider_calls) == 1
    saved = json.loads((store.root / identifier / "experience-generation.json").read_text())
    assert saved["sibling_cover_letter"] == recorded
