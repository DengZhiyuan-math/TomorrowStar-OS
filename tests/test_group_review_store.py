"""Immutable grouped review candidates retain original facts and technical receipts."""

import hashlib
import json
from pathlib import Path

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate
from test_standalone_prism_review import FakePrism

from career_evidence_graph.career_portal_data import PortalDataError


def test_group_review_prepares_a_separate_editable_project_without_compile_or_model(full_latex):
    store, _, _, _, calls, base, _, inputs = full_latex
    generated = generate(full_latex)
    original = Path(generated["source_checkpoint"]["project_root"])
    before = {p: p.read_bytes() for p in original.rglob("*") if p.is_file()}
    base_before = {p: p.read_bytes() for p in base.rglob("*") if p.is_file()}
    result = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    assert result["id"] != generated["id"]
    assert result["origin"] == "generated_latex"
    assert result["factual_review"] == "pending"
    assert result["group_preview"] is None
    assert result["group_session"]["root_draft_id"] == generated["id"]
    assert result["source_checkpoint"]["project_root"] != str(original)
    assert "TomorrowStar group" in result["latex_source"]
    assert len(result["review_groups"]) == 7
    assert all(len(group["review_fingerprint"]) == 64 for group in result["review_groups"])
    assert result["verified_unchanged_group_ids"] == []
    assert before == {p: p.read_bytes() for p in before}
    assert base_before == {p: p.read_bytes() for p in base_before}
    assert len(calls) == 1
    assert not list(store.root.rglob("*.pdf"))
    assert store.draft(result["id"])["group_session"] == result["group_session"]


def test_generated_group_project_under_git_parent_retains_policy_and_review_receipt(full_latex):
    store, _, _, _, calls, _, _, inputs = full_latex
    generated = generate(full_latex)
    (store.root / ".git").mkdir()
    prepared = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    assert prepared["source_checkpoint"]["source_policy"] == "generated-latex-project/v1"
    store.group_prism_client = FakePrism()
    state = store.group_review_state(prepared["id"])
    captured = store.capture_group_review(
        prepared["id"],
        prepared["draft_sha256"],
        task_inputs=inputs,
        expected_source_revision=state["live_source_revision"],
    )
    reviewed = captured["draft"]
    assert reviewed["source_checkpoint"]["source_policy"] == "generated-latex-project/v1"
    assert store.draft(reviewed["id"])["group_preview"] == reviewed["group_preview"]
    assert store.group_prism_client.calls == ["compile"]
    assert len(calls) == 1


def test_capture_binds_saved_source_and_pdf_without_export_or_factual_approval(full_latex):
    store, _, _, _, calls, _, _, inputs = full_latex
    generated = generate(full_latex)
    prepared = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    store.group_prism_client = FakePrism()
    state = store.group_review_state(prepared["id"])
    assert state["status"] == "empty"
    captured = store.capture_group_review(
        prepared["id"],
        prepared["draft_sha256"],
        task_inputs=inputs,
        expected_source_revision=state["live_source_revision"],
    )
    draft = captured["draft"]
    assert draft["id"] != prepared["id"]
    assert draft["factual_review"] == "pending"
    assert (
        draft["group_preview"]["source_revision"] == draft["source_checkpoint"]["source_revision"]
    )
    assert draft["group_preview"]["preview_url"].startswith(
        "/api/flow/group-previews/" + draft["id"]
    )
    assert store.group_preview_pdf(draft["id"], draft["group_preview"]["id"]).startswith(b"%PDF-")
    assert captured["verified_unchanged_group_ids"] == [g["id"] for g in draft["review_groups"]]
    assert store.group_prism_client.calls == ["compile"]
    assert len(calls) == 1
    again = store.capture_group_review(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        expected_source_revision=draft["source_checkpoint"]["source_revision"],
    )
    assert again["draft"]["id"] == draft["id"]
    assert store.group_prism_client.calls == ["compile"]


def _prepared(data):
    store, *_, inputs = data
    generated = generate(data)
    return store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )


def test_edit_omission_restoration_and_new_group_keep_separate_versions(full_latex):
    store, *_, inputs = full_latex
    prepared = _prepared(full_latex)
    group = prepared["review_groups"][2]
    old_project = Path(prepared["group_session"]["project_root"]) / "main.tex"
    before = old_project.read_bytes()

    def edit(draft, **payload):
        return store.edit_group_review(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            payload={
                "group_id": group["id"],
                "title": group["title"],
                "latex": group["rewritten"],
                "source_ids": [s["source_id"] for s in group["sources"]],
                **payload,
            },
        )

    changed = edit(
        prepared, latex=group["rewritten"].replace("Analyzed strategy;", "Analyzed strategy and")
    )
    assert group["id"] not in changed["verified_unchanged_group_ids"]
    assert len(changed["verified_unchanged_group_ids"]) == 6
    assert old_project.read_bytes() == before
    assert changed["group_session"]["id"] != prepared["group_session"]["id"]
    omitted = edit(changed, disposition="omit")
    assert group["id"] not in {g["id"] for g in omitted["review_groups"]}
    assert omitted["omitted_groups"][0]["original"] == group["original"]
    restored = edit(omitted, disposition="include")
    assert group["id"] in {g["id"] for g in restored["review_groups"]}
    assert group["id"] not in restored["verified_unchanged_group_ids"]
    new = store.edit_group_review(
        restored["id"],
        restored["draft_sha256"],
        task_inputs=inputs,
        payload={
            "title": "Strategy",
            "latex": "Analyzed strategy.\n",
            "source_ids": [group["sources"][0]["source_id"]],
            "disposition": "include",
        },
    )
    assert len(new["review_groups"]) == 8
    assert new["review_groups"][-1]["original"] == group["sources"][0]["text"]
    assert new["factual_review"] == "pending"


def test_unverified_source_never_enters_new_body(full_latex):
    store, *_, inputs = full_latex
    prepared = _prepared(full_latex)
    group = prepared["review_groups"][2]
    result = store.edit_group_review(
        prepared["id"],
        prepared["draft_sha256"],
        task_inputs=inputs,
        payload={
            "group_id": group["id"],
            "title": group["title"],
            "latex": "Built 999 services.",
            "source_ids": [s["source_id"] for s in group["sources"]],
            "disposition": "include",
        },
    )
    assert result["verification_queue"][0]["rewritten"] == "Built 999 services."
    assert "999" not in result["latex_source"]
    assert store.draft(prepared["id"])["latex_source"] == prepared["latex_source"]


@pytest.mark.parametrize(
    "mutation", ["original", "source", "attribution", "missing", "duplicate", "root", "context"]
)
def test_group_readback_revalidates_canonical_provenance_even_with_rehashed_metadata(
    full_latex, mutation
):
    store, *_, _inputs = full_latex
    prepared = _prepared(full_latex)
    path = store.root / prepared["id"] / "draft.json"
    draft = json.loads(path.read_bytes())
    group = draft["review_groups"][2]
    if mutation == "original":
        group["original"] = "False original"
    elif mutation == "source":
        group["sources"][0]["text"] = "Unsupported source override"
    elif mutation == "attribution":
        group["attribution"] = ["Team"]
    elif mutation == "missing":
        draft["review_groups"].pop()
    elif mutation == "duplicate":
        draft["omitted_groups"].append(group)
    elif mutation == "root":
        draft["group_session"]["root_draft_id"] = draft["id"]
    else:
        draft["group_context_revision"] = "f" * 64
    raw = json.dumps(draft).encode()
    path.write_bytes(raw)
    (path.parent / "draft-integrity.json").write_text(
        json.dumps(
            {"schemaVersion": 1, "id": draft["id"], "sha256": hashlib.sha256(raw).hexdigest()}
        )
    )
    with pytest.raises(PortalDataError):
        store.draft(draft["id"])


def test_source_reassignment_changes_review_scope_and_preserves_original(full_latex):
    store, *_, inputs = full_latex
    draft = _prepared(full_latex)
    group, other = draft["review_groups"][2:4]
    changed = store.edit_group_review(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        payload={
            "group_id": group["id"],
            "title": group["title"],
            "latex": "Analyzed strategy.",
            "source_ids": [other["sources"][0]["source_id"]],
            "disposition": "include",
        },
    )
    current = next(g for g in changed["review_groups"] if g["id"] == group["id"])
    assert current["original"] == group["original"]
    assert current["sources"] == other["sources"]
    assert current["attribution"] == other["attribution"]
    assert group["id"] not in changed["verified_unchanged_group_ids"]


def test_queue_resolution_uses_existing_eligible_sources(full_latex):
    store, _, _, _, _, _, output, inputs = full_latex
    output["groups"][6]["source_ids"] = []
    draft = _prepared(full_latex)
    group = draft["verification_queue"][0]
    source = next(s for s in draft["available_review_sources"] if s["title"] == "Project 6")
    resolved = store.edit_group_review(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        payload={
            "group_id": group["id"],
            "title": group["title"],
            "latex": group["rewritten"],
            "source_ids": [source["source_id"]],
            "disposition": "include",
        },
    )
    assert not resolved["verification_queue"]
    assert resolved["review_groups"][-1]["id"] == group["id"]
    assert group["id"] not in resolved["verified_unchanged_group_ids"]
