"""A factual group review and an exact PDF binding remain distinct decisions."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_application_resume import task_resume as task_resume
from test_full_latex_generation import full_latex as full_latex
from test_full_latex_generation import generate
from test_standalone_prism_review import FakePrism

from career_evidence_graph.application_input_binding import configuration_revision
from career_evidence_graph.application_worker import digest
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def reviewed_latex(full_latex):
    store, *_, inputs = full_latex
    generated = generate(full_latex)
    draft = store.prepare_group_review(
        generated["id"], generated["draft_sha256"], task_inputs=inputs
    )
    store.group_prism_client = FakePrism()
    draft = store.capture_group_review(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        expected_source_revision=store.group_review_state(draft["id"])["live_source_revision"],
    )["draft"]
    receipts = [
        {
            "id": uuid4().hex,
            "group_id": group["id"],
            "review_fingerprint": group["review_fingerprint"],
            "draft_id": draft["id"],
            "draft_sha256": draft["draft_sha256"],
            "input_revision": digest(inputs),
            "source_revision": draft["source_checkpoint"]["source_revision"],
            "preview_id": draft["group_preview"]["id"],
            "verified_by": "user",
            "at": 1.0,
        }
        for group in draft["review_groups"]
    ]
    return store, draft, inputs, receipts


def test_formal_binding_reuses_exact_strict_preview_and_preserves_pending_material_approval(
    reviewed_latex,
):
    store, draft, inputs, receipts = reviewed_latex
    preview = store.group_preview_pdf(draft["id"], draft["group_preview"]["id"])
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        export_id=uuid4().hex,
        prism=draft["source_checkpoint"],
        group_reviews=receipts,
    )
    assert result["kind"] == "pdf"
    assert result["origin"] == "generated_latex"
    assert result["factual_review"] == "pending"
    assert result["group_review"]["preview_id"] == draft["group_preview"]["id"]
    assert result["group_review"]["receipts"] == receipts
    assert store.pdf(result["id"]) == preview
    assert store.read_export(result["id"]) == result
    assert store.group_prism_client.calls == ["compile"]
    assert "materials_confirmed" not in result
    assert store.draft(draft["id"])["factual_review"] == "pending"


def test_explicit_transport_configuration_is_used_without_real_prism(reviewed_latex, monkeypatch):
    from career_evidence_graph.application_prism import PrismClient

    store, draft, inputs, receipts = reviewed_latex
    store.prism_client = SimpleNamespace(
        configuration=lambda: {"kind": "synthetic-fixed-pdf", "synthetic": True}
    )

    def unexpected(*_args, **_kwargs):
        pytest.fail("Explicit transport must not fall back to real Prism")

    monkeypatch.setattr(PrismClient, "__init__", unexpected)
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        export_id=uuid4().hex,
        prism=draft["source_checkpoint"],
        group_reviews=receipts,
    )
    assert result["export_configuration_revision"] == configuration_revision(
        {"kind": "synthetic-fixed-pdf", "synthetic": True}
    )
    assert store.group_prism_client.calls == ["compile"]
    assert "materials_confirmed" not in result


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "source", "input", "actor", "preview", "fingerprint"]
)
def test_invalid_group_confirmation_never_creates_a_formal_attempt(reviewed_latex, mutation):
    store, draft, inputs, receipts = reviewed_latex
    receipts = deepcopy(receipts)
    if mutation == "missing":
        receipts.pop()
    elif mutation == "duplicate":
        receipts[-1] = receipts[0]
    else:
        key = {
            "source": "source_revision",
            "input": "input_revision",
            "actor": "verified_by",
            "preview": "preview_id",
            "fingerprint": "review_fingerprint",
        }[mutation]
        receipts[0][key] = "wrong-version"
    identifier = uuid4().hex
    with pytest.raises(PortalDataError):
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id=identifier,
            prism=draft["source_checkpoint"],
            group_reviews=receipts,
        )
    assert not (store.root / identifier).exists()
    assert store.group_prism_client.calls == ["compile"]


def test_historical_pdf_readback_and_reconcile_do_not_recompile_or_require_live_source(
    reviewed_latex,
):
    store, draft, inputs, receipts = reviewed_latex
    identifier = uuid4().hex
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        export_id=identifier,
        prism=draft["source_checkpoint"],
        group_reviews=receipts,
    )
    (Path(draft["group_session"]["project_root"]) / "main.tex").write_text("Later source edits")
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    assert store.read_export(identifier) == result
    assert (
        store.reconcile_export(
            identifier,
            draft_id=draft["id"],
            draft_sha256=draft["draft_sha256"],
            task_inputs=inputs,
            group_reviews=receipts,
        )
        == result
    )
    assert before == {p: p.read_bytes() for p in before}
    assert store.group_prism_client.calls == ["compile"]


def test_changed_pdf_rehashed_in_export_cannot_replace_original_strict_preview(reviewed_latex):
    store, draft, inputs, receipts = reviewed_latex
    result = store.export_for_draft(
        draft["id"],
        draft["draft_sha256"],
        task_inputs=inputs,
        export_id=uuid4().hex,
        prism=draft["source_checkpoint"],
        group_reviews=receipts,
    )
    folder = store.root / result["id"]
    raw = (folder / "resume.pdf").read_bytes() + b"\n% Changed export bytes\n"
    (folder / "resume.pdf").write_bytes(raw)
    manifest = json.loads((folder / "export.json").read_bytes())
    manifest["pdf_sha256"] = hashlib.sha256(raw).hexdigest()
    (folder / "export.json").write_text(json.dumps(manifest))
    with pytest.raises(PortalDataError):
        store.read_export(result["id"])
    assert store.group_prism_client.calls == ["compile"]


@pytest.mark.parametrize("undo", [False, True])
def test_source_change_while_binding_cannot_adopt_preview_as_current_pdf(reviewed_latex, undo):
    store, draft, inputs, receipts = reviewed_latex
    identifier = uuid4().hex
    main = Path(draft["group_session"]["project_root"]) / "main.tex"
    original = main.read_bytes()
    changed = []

    def inspect(raw):
        if (store.root / identifier / "resume.pdf").exists() and not changed:
            changed.append(True)
            main.write_bytes(original + b"\n% Edited during PDF binding\n")
            if undo:
                main.write_bytes(original)
        return 1

    store.pdf_inspector = inspect
    with pytest.raises(PortalDataError):
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id=identifier,
            prism=draft["source_checkpoint"],
            group_reviews=receipts,
        )
    assert changed
    assert store.group_prism_client.calls == ["compile"]
