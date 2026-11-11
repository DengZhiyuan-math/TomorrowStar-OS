"""Exact material pairs reuse passing sibling reviews or get one durable consistency check."""

from copy import deepcopy

import pytest
from test_cover_letter_content import inputs, result, writer
from test_json_resume_content import assignment, fragment

from career_evidence_graph.application_cover_letter import edit_cover_letter, generate_cover_letter
from career_evidence_graph.application_material_consistency import (
    check_material_consistency,
    read_material_consistency,
)
from career_evidence_graph.application_resume_content import assemble_content
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


@pytest.fixture
def pair(tmp_path):
    app, fixed, sources = inputs()
    analysis = fixed["analysis"]
    analysis["source_snapshot_revision"] = "source-snapshot-r1"
    analysis["job_brief"]["job"] = {key: value for key, value in app.items() if key != "id"}
    packet = {"status": "complete", "sources": {row["source_id"]: row for row in sources["items"]}}
    packet["revision"] = digest(packet)
    analysis["material_packet"] = packet
    letter = generate_cover_letter(
        tmp_path / "author", app, fixed, sources=sources, runner=writer([])
    )
    content = assemble_content(
        {
            "schema_version": "resume-plan/v1",
            "application_id": app["id"],
            "profile": {"name": "Synthetic Applicant", "contacts": []},
            "education": [],
            "assignments": [assignment()],
        },
        [fragment()],
    )
    resume = {
        "application_id": app["id"],
        "resume_content": content,
        "analysis_binding": {"analysis_id": analysis["id"]},
        "final_review": {"passed": True, "content_revision": content["revision"]},
    }
    return app, fixed, resume, letter


def check(tmp_path, pair, runner):
    return check_material_consistency(tmp_path / "pair", *pair, runner=runner)


def test_true_concurrent_reviews_get_one_narrow_check_and_exact_receipt(tmp_path, pair):
    calls = []

    def consistent(config, prompt, **kwargs):
        calls.append(prompt)
        assert "Check only factual contradictions" in prompt
        assert "is not by itself a contradiction" in prompt
        assert pair[2]["resume_content"]["revision"] in prompt
        assert pair[3]["content_revision"] in prompt
        return result({"consistent": True, "issues": []})

    checked = check(tmp_path, pair, consistent)
    assert checked["status"] == "passed" and checked["mode"] == "pair_review"
    assert checked["resume_content_revision"] == pair[2]["resume_content"]["revision"]
    assert checked["letter_content_revision"] == pair[3]["content_revision"]
    assert check(tmp_path, pair, consistent) == checked and len(calls) == 1


@pytest.mark.parametrize("side", ["resume", "letter"])
def test_exact_existing_sibling_review_avoids_an_extra_model_check(tmp_path, pair, side):
    _, _, resume, letter = pair
    if side == "resume":
        resume["final_review"]["sibling_cover_letter_revision"] = letter["content_revision"]
    else:
        letter["review_binding"]["sibling_resume_revision"] = resume["resume_content"]["revision"]
    checked = check(
        tmp_path, pair, lambda *_: pytest.fail("Passing sibling review already covers pair")
    )
    assert checked["status"] == "passed" and checked["mode"] == "existing_" + side + "_review"
    assert read_material_consistency(tmp_path / "pair", *pair) == checked


def test_stale_or_failed_sibling_review_does_not_cover_current_pair(tmp_path, pair):
    pair[2]["final_review"].update(
        passed=False, sibling_cover_letter_revision=pair[3]["content_revision"]
    )
    pair[3]["review_binding"]["sibling_resume_revision"] = "old-resume"
    calls = []
    checked = check(
        tmp_path,
        pair,
        lambda *_args, **_kwargs: calls.append(True) or result({"consistent": True, "issues": []}),
    )
    assert checked["mode"] == "pair_review" and calls == [True]


def test_concrete_contradiction_is_retained_without_rewriting_either_material(tmp_path, pair):
    before = deepcopy(pair)
    checked = check(
        tmp_path,
        pair,
        lambda *_args, **_kwargs: result(
            {
                "consistent": False,
                "issues": [
                    "resume experience-1 says team planning; "
                    "letter experience says completed sole ownership"
                ],
            }
        ),
    )
    assert checked["status"] == "conflict" and checked["issues"]
    assert pair == before
    assert read_material_consistency(tmp_path / "pair", *pair) == checked


def test_unknown_consistency_result_is_not_replayed_and_read_reconciliation_is_pure(tmp_path, pair):
    calls = []

    def lost(*_args, **_kwargs):
        calls.append(True)
        raise TimeoutError("Synthetic lost response")

    for _ in range(2):
        with pytest.raises(PortalDataError) as caught:
            check(tmp_path, pair, lost)
        assert caught.value.code == "material_consistency_needs_recheck"
    assert calls == [True]
    before = {path.name: path.read_bytes() for path in (tmp_path / "pair").iterdir()}
    with pytest.raises(PortalDataError):
        read_material_consistency(tmp_path / "pair", *pair)
    assert before == {path.name: path.read_bytes() for path in (tmp_path / "pair").iterdir()}


def test_local_completed_raw_result_reconciles_without_another_call_or_disk_write(tmp_path, pair):
    checked = check(
        tmp_path, pair, lambda *_args, **_kwargs: result({"consistent": True, "issues": []})
    )
    (tmp_path / "pair/consistency.json").unlink()
    before = {path.name: path.read_bytes() for path in (tmp_path / "pair").iterdir()}
    assert read_material_consistency(tmp_path / "pair", *pair) == checked
    assert before == {path.name: path.read_bytes() for path in (tmp_path / "pair").iterdir()}
    assert check(tmp_path, pair, lambda *_: pytest.fail("Reconcile raw result only")) == checked
    assert (tmp_path / "pair/consistency.json").exists()


@pytest.mark.parametrize("corruption", ["application", "analysis", "packet", "content"])
def test_changed_input_or_material_cannot_inherit_old_pair_receipt(tmp_path, pair, corruption):
    check(tmp_path, pair, lambda *_args, **_kwargs: result({"consistent": True, "issues": []}))
    if corruption == "application":
        pair[0]["job_description"] = "Different role."
    elif corruption == "analysis":
        pair[2]["analysis_binding"]["analysis_id"] = "other-analysis"
    elif corruption == "packet":
        pair[1]["analysis"]["material_packet"]["status"] = "reading"
    else:
        pair[3]["content"]["paragraphs"][0]["text"] = "Unversioned body mutation."
    with pytest.raises(PortalDataError) as caught:
        read_material_consistency(tmp_path / "pair", *pair)
    assert caught.value.code == "material_consistency_inputs_invalid"


def test_explicit_human_successor_is_compared_without_forging_or_reusing_ai_grounding(
    tmp_path, pair
):
    _, _, resume, letter = pair
    content = edit_cover_letter(
        letter["content"],
        "Explicit human body.",
        expected_revision=letter["content_revision"],
        edit_id="human-edit",
    )
    letter.update(content=content, content_revision=content["revision"], actor="user")
    letter["source_binding"]["manual_edit"] = True
    letter.pop("grounding")
    calls = []
    checked = check(
        tmp_path,
        pair,
        lambda *_args, **_kwargs: calls.append(True) or result({"consistent": True, "issues": []}),
    )
    assert checked["mode"] == "pair_review" and calls == [True]
    assert "grounding" not in letter
    assert letter["content"]["paragraphs"][0]["protected"] is True


def test_unknown_raw_schema_is_retained_instead_of_treated_as_a_known_pass(tmp_path, pair):
    with pytest.raises(PortalDataError) as caught:
        check(
            tmp_path,
            pair,
            lambda *_args, **_kwargs: result({"consistent": True, "issues": ["contradiction"]}),
        )
    assert caught.value.code == "material_consistency_needs_recheck"
    assert (tmp_path / "pair/review.json").exists()
    assert not (tmp_path / "pair/consistency.json").exists()
