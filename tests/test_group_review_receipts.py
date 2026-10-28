"""Actual grouped résumé stores retain bounded, same-source technical receipts."""

from pathlib import Path

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate
from test_standalone_prism_review import FakePrism

from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def grouped(full_latex):
    store, _, _, _, calls, _, _, inputs = full_latex
    generated = generate(full_latex)
    store.group_prism_client = FakePrism()
    draft = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    main = Path(draft["group_session"]["project_root"]) / "main.tex"
    return store, draft, main, inputs, calls


def capture(grouped, draft=None, **kwargs):
    store, prepared, _, inputs, _ = grouped
    draft = draft or prepared
    return store.capture_group_review(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        expected_source_revision=store.group_review_state(draft["id"])["live_source_revision"],
        **kwargs,
    )


def block(group):
    return (
        f"% TomorrowStar group {group['id']} begin\n"
        + group["rewritten"]
        + f"\n% TomorrowStar group {group['id']} end\n"
    )


def fingerprints(draft):
    return {g["id"]: g["review_fingerprint"] for g in draft["review_groups"]}


def test_stale_expected_source_fails_before_compile_and_preserves_original(grouped):
    store, draft, main, inputs, calls = grouped
    old = store.group_review_state(draft["id"])["live_source_revision"]
    main.write_text(main.read_text().replace("strategy; built", "strategy and built"))
    with pytest.raises(PortalDataError) as error:
        store.capture_group_review(
            draft["id"], draft["draft_sha256"], task_inputs=inputs, expected_source_revision=old
        )
    assert error.value.code == "prism_source_changed"
    assert store.group_prism_client.calls == []
    assert store.draft(draft["id"])["latex_source"] == draft["latex_source"]
    assert len(calls) == 1


def test_unknown_attempt_survives_reads_and_blocks_capture_edit_and_recompile(grouped):
    store, draft, _, inputs, _ = grouped

    class UncertainPrism(FakePrism):
        def compile(self, binding):
            self.calls.append("compile")
            raise TimeoutError("synthetic unknown compiler outcome")

    client = UncertainPrism()
    store.group_prism_client = client
    with pytest.raises(PortalDataError):
        capture(grouped)
    first = store.group_review_state(draft["id"])
    assert first["status"] == "needs_recheck"
    assert first["pending_attempt_id"]
    assert list(store.root.rglob("intent.json"))
    with pytest.raises(PortalDataError):
        capture(grouped)
    with pytest.raises(PortalDataError):
        capture(grouped, reconcile=True)
    with pytest.raises(PortalDataError) as error:
        store.edit_group_review(draft["id"], draft["draft_sha256"], task_inputs=inputs, payload={})
    assert error.value.code == "prism_review_needs_recheck"
    assert (
        store.group_review_state(draft["id"])["pending_attempt_id"] == first["pending_attempt_id"]
    )
    assert client.calls == ["compile"]


@pytest.mark.parametrize("undo", [False, True])
def test_source_mutated_during_compile_is_never_adopted(grouped, undo):
    store, draft, main, _, _ = grouped
    original = main.read_bytes()

    class ChangingPrism(FakePrism):
        def compile(self, binding):
            result = super().compile(binding)
            main.write_bytes(original.replace(b"strategy; built", b"strategy and built"))
            if undo:
                main.write_bytes(original)
            return result

    client = ChangingPrism()
    store.group_prism_client = client
    with pytest.raises(PortalDataError):
        capture(grouped)
    assert store.group_review_state(draft["id"])["status"] == "needs_recheck"
    assert store.draft(draft["id"])["latex_source"] == draft["latex_source"]
    with pytest.raises(PortalDataError):
        capture(grouped, reconcile=True)
    assert client.calls == ["compile"]


@pytest.mark.parametrize("damage", ["unknown", "unpaired", "outside"])
def test_unmapped_editor_source_retains_technical_preview_without_draft(grouped, damage):
    store, draft, main, _, _ = grouped
    text = main.read_text()
    identifier = draft["review_groups"][1]["id"]
    if damage == "unknown":
        text = text.replace(identifier, "f" * 64)
    elif damage == "unpaired":
        text = text.replace(f"% TomorrowStar group {identifier} end\n", "")
    else:
        text = text.replace("\\end{document}", "Unmapped prose\n\\end{document}")
    main.write_text(text)
    result = capture(grouped)
    assert result["status"] == "mapping_required" and result["draft"] is None
    preview = result["preview"]
    assert preview["latex_source"] == text
    assert preview["review_status"] == "pending_human_review"
    assert store.group_preview_pdf(draft["id"], preview["id"]).startswith(b"%PDF-")
    assert store.draft(draft["id"])["latex_source"] == draft["latex_source"]
    assert store.group_prism_client.calls == ["compile"]
    assert capture(grouped)["status"] == "mapping_required"
    assert store.group_prism_client.calls == ["compile"]


def test_manual_rewrite_changes_only_affected_group_fingerprint(grouped):
    store, draft, main, _, calls = grouped
    first = capture(grouped)["draft"]
    original = fingerprints(first)
    changed = first["review_groups"][1]
    text = main.read_text().replace(
        "Analyzed strategy; built 1 Python services.", "Built 1 Python services; analyzed strategy."
    )
    main.write_text(text)
    result = capture(grouped, first)
    revised = result["draft"]
    assert revised["latex_source"] == text
    assert fingerprints(revised)[changed["id"]] != original[changed["id"]]
    unchanged = set(original) - {changed["id"]}
    assert set(result["verified_unchanged_group_ids"]) == unchanged
    assert all(fingerprints(revised)[key] == original[key] for key in unchanged)
    assert store.draft(first["id"])["latex_source"] == first["latex_source"]
    assert revised["factual_review"] == "pending"
    assert store.group_prism_client.calls == ["compile", "compile"] and len(calls) == 1


def test_completed_receipt_reconcile_reads_same_draft_and_pdf_without_compile(grouped):
    store, _, _, _, _ = grouped
    first = capture(grouped)
    draft = first["draft"]
    original_pdf = store.group_preview_pdf(draft["id"], first["preview"]["id"])
    reconciled = capture(grouped, draft, reconcile=True)
    assert reconciled["status"] == "ready"
    assert reconciled["draft"]["id"] == draft["id"]
    assert reconciled["draft"]["draft_sha256"] == draft["draft_sha256"]
    assert reconciled["preview"]["id"] == first["preview"]["id"]
    assert store.group_preview_pdf(draft["id"], first["preview"]["id"]) == original_pdf
    assert store.group_prism_client.calls == ["compile"]


@pytest.mark.parametrize("change", ["delete", "reorder", "swap-content"])
def test_body_group_operations_preserve_only_verified_mapping(grouped, change):
    store, _, main, _, _ = grouped
    first = capture(grouped)["draft"]
    one, two = first["review_groups"][1:3]
    text = main.read_text()
    if change == "delete":
        text = text.replace(block(one), "")
    elif change == "reorder":
        text = text.replace(block(one) + block(two), block(two) + block(one))
    else:
        text = text.replace(one["rewritten"], "SWAP-CONTENT")
        text = text.replace(two["rewritten"], one["rewritten"])
        text = text.replace("SWAP-CONTENT", two["rewritten"])
    main.write_text(text)
    result = capture(grouped, first)
    if change == "swap-content":
        assert result["status"] == "mapping_required" and result["draft"] is None
        return
    revised = result["draft"]
    expected = set(fingerprints(first)) - ({one["id"]} if change == "delete" else set())
    assert set(result["verified_unchanged_group_ids"]) == expected
    assert all(fingerprints(revised)[key] == fingerprints(first)[key] for key in expected)
    if change == "delete":
        assert one["id"] not in {g["id"] for g in revised["review_groups"]}
        assert any(g["id"] == one["id"] for g in revised["omitted_groups"])
    else:
        assert [g["id"] for g in revised["review_groups"]][1:3] == [two["id"], one["id"]]
    assert store.draft(first["id"])["latex_source"] == first["latex_source"]


@pytest.mark.parametrize("change", ["preamble", "ancillary", "unsafe-body"])
def test_layout_or_read_surface_changes_are_rejected_before_compile(grouped, change):
    store, draft, main, _, _ = grouped
    if change == "preamble":
        main.write_text(
            main.read_text().replace("\\begin{document}", "% Different layout\n\\begin{document}")
        )
    elif change == "ancillary":
        (main.parent / "style-note.txt").write_text("Changed auxiliary source")
    else:
        main.write_text(
            main.read_text().replace("\\end{document}", "\\input{secret}\n\\end{document}")
        )
    with pytest.raises(PortalDataError):
        capture(grouped)
    assert store.group_prism_client.calls == []
    assert not list(store.root.rglob("intent.json"))
    assert store.draft(draft["id"])["latex_source"] == draft["latex_source"]
