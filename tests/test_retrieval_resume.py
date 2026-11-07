"""Discovery resumes saved page results and waits on unknown provider outcomes."""

import json
from pathlib import Path

import pytest
from test_matching_stage_recovery import terminal_model_failure
from test_requirement_retrieval import (
    REQUIREMENTS,
    model_runner,
    relevant,
)
from test_requirement_retrieval import (
    inputs as inputs,
)

from career_evidence_graph import application_retrieval as retrieval
from career_evidence_graph.application_retrieval import plan_retrieval
from career_evidence_graph.career_portal_data import PortalDataError


def test_completed_retrieval_replays_locally_with_a_predictable_new_invocation(inputs, tmp_path):
    app, snapshot = inputs
    calls = []
    old = plan_retrieval(
        app,
        snapshot,
        tmp_path / "old",
        runner=model_runner(relevant, calls),
        requirements=REQUIREMENTS,
    )
    old_dir = Path(old["directory"])
    before = {path.relative_to(old_dir): path.read_bytes() for path in old_dir.rglob("*.json")}
    dispatched = []
    new = plan_retrieval(
        app,
        snapshot,
        tmp_path / "new",
        runner=model_runner(relevant, calls),
        requirements=REQUIREMENTS,
        invocation_id="a" * 32,
        resume_from=old_dir,
        on_dispatch=lambda: dispatched.append(True),
    )
    assert new == old | {"directory": str(tmp_path / "new" / ("a" * 32))}
    assert len(calls) == 1
    assert dispatched == []
    assert {
        path.relative_to(old_dir): path.read_bytes() for path in old_dir.rglob("*.json")
    } == before


def test_known_failed_page_retries_once_without_repeating_successful_pages(
    inputs, tmp_path, monkeypatch
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    calls = []
    run = model_runner(relevant, calls)

    def fail_second(config, prompt, **kwargs):
        if config.workspace.name == "page-0002":
            raise terminal_model_failure("Synthetic confirmed terminal CLI failure")
        return run(config, prompt, **kwargs)

    with pytest.raises(PortalDataError):
        plan_retrieval(app, snapshot, tmp_path / "old", runner=fail_second, invocation_id="b" * 32)
    dispatched = []
    result = plan_retrieval(
        app,
        snapshot,
        tmp_path / "new",
        runner=run,
        resume_from=tmp_path / "old" / ("b" * 32),
        on_dispatch=lambda: dispatched.append(True),
    )
    assert result["selected_candidate_ids"] == ["unfamiliar"]
    assert [call["page"] for call in calls] == [1, 2]
    assert dispatched == [True]


def test_interrupted_page_is_not_redispatched_after_prior_pages_are_replayed(
    inputs, tmp_path, monkeypatch
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    calls = []
    run = model_runner(relevant, calls)

    def interrupt_second(config, prompt, **kwargs):
        if config.workspace.name == "page-0002":
            raise KeyboardInterrupt
        return run(config, prompt, **kwargs)

    with pytest.raises(KeyboardInterrupt):
        plan_retrieval(
            app, snapshot, tmp_path / "old", runner=interrupt_second, invocation_id="b" * 32
        )
    dispatched = []
    with pytest.raises(PortalDataError) as error:
        plan_retrieval(
            app,
            snapshot,
            tmp_path / "new",
            runner=run,
            resume_from=tmp_path / "old" / ("b" * 32),
            on_dispatch=lambda: dispatched.append(True),
        )
    assert error.value.code == "match_result_needs_recheck"
    assert len(calls) == 1
    assert dispatched == []


@pytest.mark.parametrize("artifact", ["prompt.json", "schema.json", "hash", "plan.json"])
def test_saved_retrieval_with_changed_call_evidence_is_rejected_without_dispatch(
    inputs, tmp_path, artifact
):
    app, snapshot = inputs
    calls = []
    run = model_runner(relevant, calls)
    old = plan_retrieval(app, snapshot, tmp_path / "old", runner=run)
    old_dir = Path(old["directory"])
    page = old_dir / "page-0001"
    if artifact == "hash":
        path = page / "result.json"
        saved = json.loads(path.read_text())
        saved["output_schema_hash"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(saved))
    elif artifact == "plan.json":
        saved = json.loads((old_dir / artifact).read_text())
        saved["selected_candidate_ids"] = []
        (old_dir / artifact).write_text(json.dumps(saved))
    else:
        (page / artifact).write_text("{}")
    with pytest.raises(PortalDataError) as error:
        plan_retrieval(app, snapshot, tmp_path / "new", runner=run, resume_from=old_dir)
    assert error.value.code == "retrieval_invalid"
    assert len(calls) == 1


@pytest.mark.parametrize("invalid", ["schema", "semantic"])
def test_known_invalid_page_can_be_replaced_without_replaying_forever(inputs, tmp_path, invalid):
    app, snapshot = inputs
    calls = []
    old_dir = tmp_path / "old" / ("d" * 32)
    bad = (
        {}
        if invalid == "schema"
        else {
            "requirements": REQUIREMENTS,
            "selections": [
                {
                    "candidate_id": "not-in-directory",
                    "requirement_indexes": [0],
                    "rationale": "Read",
                }
            ],
        }
    )
    with pytest.raises(PortalDataError):
        plan_retrieval(
            app,
            snapshot,
            tmp_path / "old",
            runner=model_runner(lambda _: bad, calls),
            invocation_id="d" * 32,
        )
    before = {path.relative_to(old_dir): path.read_bytes() for path in old_dir.rglob("*.json")}
    dispatched = []
    result = plan_retrieval(
        app,
        snapshot,
        tmp_path / "new",
        runner=model_runner(relevant, calls),
        resume_from=old_dir,
        on_dispatch=lambda: dispatched.append(True),
    )
    assert result["selected_candidate_ids"] == ["unfamiliar"]
    assert len(calls) == 2
    assert dispatched == [True]
    assert (old_dir / "page-0001/validation-failure.json").is_file()
    assert {
        path.relative_to(old_dir): path.read_bytes() for path in old_dir.rglob("*.json")
    } == before


@pytest.mark.parametrize("invalid", ["schema", "semantic"])
def test_invalid_raw_page_without_marker_is_checked_before_a_later_retry(inputs, tmp_path, invalid):
    app, snapshot = inputs
    calls = []
    old_dir = tmp_path / "old" / ("d" * 32)
    bad = (
        {}
        if invalid == "schema"
        else {
            "requirements": REQUIREMENTS,
            "selections": [
                {
                    "candidate_id": "not-in-directory",
                    "requirement_indexes": [0],
                    "rationale": "Read",
                }
            ],
        }
    )
    with pytest.raises(PortalDataError):
        plan_retrieval(
            app,
            snapshot,
            tmp_path / "old",
            runner=model_runner(lambda _: bad, calls),
            invocation_id="d" * 32,
        )
    (old_dir / "page-0001/validation-failure.json").unlink()
    before = {path.relative_to(old_dir): path.read_bytes() for path in old_dir.rglob("*.json")}
    checked = tmp_path / "checked" / ("e" * 32)
    dispatched = []
    with pytest.raises(PortalDataError) as error:
        plan_retrieval(
            app,
            snapshot,
            checked.parent,
            invocation_id=checked.name,
            runner=model_runner(relevant, calls),
            resume_from=old_dir,
            on_dispatch=lambda: dispatched.append(True),
        )
    assert error.value.code == "retrieval_invalid"
    assert dispatched == []
    assert (checked / "page-0001/validation-failure.json").is_file()
    assert (checked / "page-0001/result.json").read_bytes() == before[Path("page-0001/result.json")]
    assert {
        path.relative_to(old_dir): path.read_bytes() for path in old_dir.rglob("*.json")
    } == before
    result = plan_retrieval(
        app,
        snapshot,
        tmp_path / "retry",
        runner=model_runner(relevant, calls),
        resume_from=checked,
        on_dispatch=lambda: dispatched.append(True),
    )
    assert result["selected_candidate_ids"] == ["unfamiliar"]
    assert dispatched == [True]
    assert len(calls) == 2


@pytest.mark.parametrize("damaged", ["validation-failure.json", "result.json"])
def test_invalid_page_marker_cannot_authorize_retry_of_damaged_receipts(inputs, tmp_path, damaged):
    app, snapshot = inputs
    calls = []
    old_dir = tmp_path / "old" / ("d" * 32)
    with pytest.raises(PortalDataError):
        plan_retrieval(
            app,
            snapshot,
            old_dir.parent,
            runner=model_runner(lambda _: {}, calls),
            invocation_id=old_dir.name,
        )
    (old_dir / "page-0001" / damaged).write_text("{}")
    with pytest.raises(PortalDataError) as error:
        plan_retrieval(
            app,
            snapshot,
            tmp_path / "new",
            runner=model_runner(relevant, calls),
            resume_from=old_dir,
        )
    assert error.value.code == "retrieval_invalid"
    assert len(calls) == 1


def test_a_call_refused_before_writing_anything_is_not_resumed(inputs, tmp_path, monkeypatch):
    # A retrieval_too_large refusal left an empty folder; each retry then failed to
    # read its record (Overstory, 2026-11-07).
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_FACT_BYTES", 1)
    with pytest.raises(PortalDataError) as error:
        plan_retrieval(
            app,
            snapshot,
            tmp_path / "old",
            runner=model_runner(relevant, []),
            invocation_id="b" * 32,
        )
    assert error.value.code == "retrieval_too_large"
    monkeypatch.undo()
    calls = []
    result = plan_retrieval(
        app,
        snapshot,
        tmp_path / "new",
        runner=model_runner(relevant, calls),
        resume_from=tmp_path / "old" / ("b" * 32),
    )
    assert calls and result["selected_candidate_ids"]
