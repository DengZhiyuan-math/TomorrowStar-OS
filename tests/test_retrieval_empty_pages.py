"""Program-owned empty-page receipts avoid calls without hiding unknown outcomes."""

import json
from pathlib import Path

import pytest
from test_requirement_retrieval import REQUIREMENTS, model_runner
from test_requirement_retrieval import inputs as inputs

from career_evidence_graph import application_retrieval as retrieval
from career_evidence_graph.career_portal_data import PortalDataError


def run_plan(app, snapshot, directory, calls, **kwargs):
    return retrieval.plan_retrieval(
        app,
        snapshot,
        directory,
        runner=model_runner(lambda _: {"requirements": REQUIREMENTS, "selections": []}, calls),
        requirements=REQUIREMENTS,
        # A re-check with fixed requirements still pages the whole index; an unknown
        # follow-up pages only unread entries (2026-11-08), so it has no empty page.
        selected_candidate_ids=["ordinary"],
        **kwargs,
    )


def test_empty_fixed_page_skips_model_and_retains_full_coverage(inputs, tmp_path, monkeypatch):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    calls = []
    plan = run_plan(app, snapshot, tmp_path / "old", calls)
    assert [context["page"] for context in calls] == [2]
    first = Path(plan["directory"]) / "page-0001"
    receipt = json.loads((first / "skipped.json").read_text())
    assert receipt["reason"] == "no_unread_candidates"
    assert receipt["model_called"] is False
    assert not (first / "result.json").exists()
    assert not (first / "attempt.json").exists()
    assert plan["coverage"]["visited_candidate_ids"] == ["ordinary", "unfamiliar"]
    assert plan["coverage"]["page_count"] == 2
    before = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}
    calls.clear()
    run_plan(app, snapshot, tmp_path / "replay", calls, resume_from=Path(plan["directory"]))
    assert calls == []
    assert before == {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "damage",
    [
        "context",
        "prompt",
        "schema",
        "receipt",
        "unknown",
        "malformed",
        "missing_context",
        "contradictory_result",
    ],
)
def test_empty_page_cannot_hide_changed_receipts_or_an_unknown_call(
    inputs, tmp_path, monkeypatch, damage
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    plan = run_plan(app, snapshot, tmp_path / "old", [])
    first = Path(plan["directory"]) / "page-0001"
    if damage == "unknown":
        (first / "skipped.json").unlink()
        (first / "attempt.json").write_text('{"status":"in_flight"}')
    elif damage == "malformed":
        (first / "skipped.json").write_text("{")
    elif damage == "missing_context":
        (first / "context.json").unlink()
    elif damage == "contradictory_result":
        (first / "result.json").write_text("{}")
    else:
        name = "skipped.json" if damage == "receipt" else damage + ".json"
        (first / name).write_text("{}")
    calls = []
    with pytest.raises(PortalDataError):
        run_plan(app, snapshot, tmp_path / "rejected", calls, resume_from=Path(plan["directory"]))
    assert calls == []


def test_initial_requirement_extraction_still_calls_model_on_an_empty_candidate_page(
    inputs, tmp_path, monkeypatch
):
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    calls = []
    plan = retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "initial",
        runner=model_runner(lambda _: {"requirements": REQUIREMENTS, "selections": []}, calls),
        selected_candidate_ids=["ordinary", "unfamiliar"],
    )
    assert [context["page"] for context in calls] == [1]
    assert calls[0]["requirements"] is None
    assert plan["requirements"] == REQUIREMENTS
    assert plan["coverage"]["visited_candidate_ids"] == ["ordinary", "unfamiliar"]


def test_an_unknown_follow_up_pages_only_unread_entries(inputs, tmp_path, monkeypatch):
    """2026-11-08: finnova re-sent all 75 entries in every follow-up round."""
    app, snapshot = inputs
    monkeypatch.setattr(retrieval, "MAX_PAGE_BYTES", 180)
    calls = []
    plan = retrieval.plan_retrieval(
        app,
        snapshot,
        tmp_path / "followup",
        runner=model_runner(lambda _: {"requirements": REQUIREMENTS, "selections": []}, calls),
        requirements=REQUIREMENTS,
        unknown_requirements=[0],
        selected_candidate_ids=["ordinary"],
    )
    assert [[row["candidate_id"] for row in context["records"]] for context in calls] == [
        ["unfamiliar"]
    ]
    assert plan["coverage"]["visited_candidate_ids"] == ["unfamiliar"]
    assert plan["coverage"]["total_records"] == 2
