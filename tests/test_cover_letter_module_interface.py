"""Material owners resolve their own attempts; callers supply fixed deliveries."""

from copy import deepcopy

import pytest
from test_cover_letter_content import inputs, writer
from test_material_consistency import pair as pair

from career_evidence_graph import application_cover_letter as letters
from career_evidence_graph import application_material_consistency as consistency
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


def letter_task():
    application, fixed, sources = inputs()
    fixed["analysis"]["job_brief"]["job"] = {
        key: value for key, value in application.items() if key != "id"
    }
    task = {
        "application_id": application["id"],
        "stages": {
            "letter": {
                "status": "running",
                "attempt_id": "c" * 32,
                "fixed_inputs_revision": letters.letter_inputs_revision(fixed),
            }
        },
    }
    return task, fixed, sources


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def consistency_task(pair):
    app, fixed, resume, letter = pair
    resume.update(id="active-resume", content_revision=resume["resume_content"]["revision"])
    pair_binding = {
        "resume_content_revision": resume["content_revision"],
        "letter_content_revision": letter["content_revision"],
    }
    letter.setdefault("id", "letter")
    return {
        "application_id": app["id"],
        "analysis_id": fixed["analysis"]["id"],
        "draft_id": resume["id"],
        "artifacts": [
            {"stage": "resume", "adopted": True, "result": resume},
            {"stage": "letter", "adopted": True, "result": letter},
        ],
        "stages": {"letter": {"status": "complete"}},
        "letter_id": letter["id"],
        "material_consistency": pair_binding | {"pair_revision": digest(pair_binding)},
    }


def test_letter_owner_prepares_and_reads_one_exact_attempt_without_pdf_or_replay(tmp_path):
    task, fixed, sources = letter_task()
    calls = []
    reads = []

    def read_sources(analysis):
        reads.append(analysis["id"])
        return {"selected": deepcopy(sources)}

    module = letters.CoverLetterModule(tmp_path / "letters", read_sources, runner=writer(calls))
    prepared = module.prepare(task, fixed)
    assert prepared["attempt_id"] == "c" * 32
    assert prepared["content"]["paragraphs"][1]["text"] == "Built Python services with the team."
    assert len(calls) == 2
    before = tree(tmp_path)
    assert module.read(task, fixed) == prepared
    assert module.prepare(task, fixed) == prepared
    assert tree(tmp_path) == before and len(calls) == 2
    assert reads == [fixed["analysis"]["id"]] * 3
    assert not list(tmp_path.rglob("*.pdf"))


def test_consistency_owner_uses_active_resume_instead_of_last_adopted_history(tmp_path, pair):
    _, fixed, resume, letter = pair
    task = consistency_task(pair)
    resume["final_review"]["sibling_cover_letter_revision"] = letter["content_revision"]
    stale = deepcopy(resume)
    stale.update(id="historical-resume", content_revision="old-content")
    stale["resume_content"]["experiences"][0]["items"][0]["text"] = "An older assertion."
    task["artifacts"].append({"stage": "resume", "adopted": True, "result": stale})
    module = consistency.MaterialConsistencyModule(
        tmp_path / "checks", runner=lambda *_: pytest.fail("Existing exact review covers pair")
    )
    before = deepcopy(task)
    checked = module.check(task, fixed)
    assert checked["mode"] == "existing_resume_review"
    assert checked["resume_content_revision"] == resume["content_revision"]
    files = tree(tmp_path)
    assert module.read(task, fixed) == checked
    assert tree(tmp_path) == files and task == before


@pytest.mark.parametrize("change", ["attempt", "retry", "fixed_inputs"])
def test_letter_owner_rejects_changed_attempt_before_directory_or_source_read(tmp_path, change):
    task, fixed, _ = letter_task()
    if change == "attempt":
        task["stages"]["letter"]["attempt_id"] = "../other"
    elif change == "retry":
        task["stages"]["letter"]["retry_from_attempt_id"] = "../other"
    else:
        task["stages"]["letter"]["fixed_inputs_revision"] = "old-inputs"
    root = tmp_path / "letters"
    module = letters.CoverLetterModule(
        root,
        lambda *_: pytest.fail("Invalid attempt cannot read a source delivery"),
        runner=lambda *_: pytest.fail("Invalid attempt cannot call an author"),
    )
    with pytest.raises(PortalDataError):
        module.prepare(task, fixed)
    assert not root.exists()


@pytest.mark.parametrize(
    "change", ["active_id", "pair_revision", "reserved_content", "outer_content"]
)
def test_consistency_owner_rejects_wrong_pair_without_call_or_directory(tmp_path, pair, change):
    task = consistency_task(pair)
    if change == "active_id":
        task["draft_id"] = "not-the-active-resume"
    elif change == "pair_revision":
        task["material_consistency"]["pair_revision"] = "old-pair"
    elif change == "reserved_content":
        expected = task["material_consistency"]
        expected["resume_content_revision"] = "another-resume-version"
        expected["pair_revision"] = digest(
            {key: value for key, value in expected.items() if key != "pair_revision"}
        )
    else:
        task["artifacts"][0]["result"]["content_revision"] = "another-resume-version"
    root = tmp_path / "checks"
    module = consistency.MaterialConsistencyModule(
        root, runner=lambda *_: pytest.fail("A different pair cannot call the checker")
    )
    before = deepcopy(task)
    for operation in (module.read, module.check):
        with pytest.raises(PortalDataError) as caught:
            operation(task, pair[1])
        assert caught.value.code == "material_consistency_inputs_invalid"
    assert not root.exists() and task == before


def test_letter_owner_read_of_unknown_attempt_is_pure_and_prepare_does_not_replay(tmp_path):
    task, fixed, sources = letter_task()
    calls = []

    def lost(*_args, **_kwargs):
        calls.append("writer")
        raise TimeoutError("Synthetic lost author response")

    root = tmp_path / "letters"
    module = letters.CoverLetterModule(root, lambda _: {"selected": sources}, runner=lost)
    with pytest.raises(PortalDataError) as missing:
        module.read(task, fixed)
    assert missing.value.code == "letter_generation_needs_recheck"
    assert not root.exists() and calls == []
    with pytest.raises(PortalDataError):
        module.prepare(task, fixed)
    before = tree(tmp_path)
    for operation in (module.read, module.prepare):
        with pytest.raises(PortalDataError) as caught:
            operation(task, fixed)
        assert caught.value.code == "letter_generation_needs_recheck"
    assert calls == ["writer"] and tree(tmp_path) == before
