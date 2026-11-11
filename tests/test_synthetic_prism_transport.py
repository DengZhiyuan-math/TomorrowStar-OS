"""Fixed PDF transport preserves real strict receipts without any Prism service."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph.application_prism import PrismClient
from career_evidence_graph.application_prism_review import PrismReviewStore
from career_evidence_graph.career_portal_data import PortalDataError


def synthetic_project(tmp_path):
    root = tmp_path / "synthetic"
    script = Path(__file__).parents[1] / "scripts/create_synthetic_flow.py"
    subprocess.run(
        [sys.executable, "-I", "-B", str(script), "--preparation", str(root)],
        check=True,
        capture_output=True,
    )
    project = root / "runtime/material-preparation/resumes/project"
    project.mkdir(parents=True)
    (project / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nSynthetic fixture\n\\end{document}\n"
    )
    return root, project


def test_fixed_transport_uses_strict_receipts_and_explicitly_refuses_real_editor(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_preparation_fixtures import SyntheticPrismClient
    from career_evidence_graph.application_prism import source_snapshot

    def unexpected(*_args, **_kwargs):
        pytest.fail("Synthetic preparation must not construct a real Prism client")

    monkeypatch.setattr(PrismClient, "__init__", unexpected)
    root, project = synthetic_project(tmp_path)
    client = SyntheticPrismClient(root)
    assert client.configuration()["synthetic"] is True
    assert client.configuration()["real_compilation"] is False
    store = PrismReviewStore(
        root / "runtime/strict-receipts",
        client=client,
        binding_provider=lambda: source_snapshot(project, "main.tex"),
    )
    binding = store.binding()
    with pytest.raises(PortalDataError) as editor:
        client.open(binding)
    assert editor.value.code == "synthetic_prism_editor_disabled"
    captured = store.capture(binding["source_revision"])
    version = captured["latest"]
    assert captured["status"] == "ready"
    assert version["review_status"] == "pending_human_review"
    assert store.pdf(version["id"]) == (root / "synthetic-preview.pdf").read_bytes()
    assert store.source(version["id"]) == (project / "main.tex").read_bytes()
    assert store.build(version["id"])["synthetic"] is True
    assert store.build(version["id"])["real_compilation"] is False
    assert not list(root.rglob("worker-state.json"))


@pytest.mark.parametrize("damage", ["hardlink", "symlink", "changed", "missing"])
def test_unverifiable_fixed_pdf_fails_without_fallback(tmp_path, monkeypatch, damage):
    from career_evidence_graph.application_preparation_fixtures import SyntheticPrismClient
    from career_evidence_graph.application_prism import source_snapshot

    def unexpected(*_args, **_kwargs):
        pytest.fail("Unverifiable synthetic inputs cannot fall back to Prism")

    monkeypatch.setattr(PrismClient, "__init__", unexpected)
    root, project = synthetic_project(tmp_path)
    pdf = root / "synthetic-preview.pdf"
    retained = tmp_path / "retained-fixture.pdf"
    retained.write_bytes(pdf.read_bytes())
    original = retained.read_bytes()
    pdf.unlink()
    if damage == "hardlink":
        os.link(retained, pdf)
    elif damage == "symlink":
        pdf.symlink_to(retained)
    elif damage == "changed":
        pdf.write_bytes(original + b"changed")
    client = SyntheticPrismClient(root)
    with pytest.raises(PortalDataError) as failed:
        client.compile(source_snapshot(project, "main.tex"))
    assert failed.value.code == "resume_export_failed"
    assert retained.read_bytes() == original


def test_foreign_project_is_rejected_before_reading_its_source(tmp_path, monkeypatch):
    from career_evidence_graph import application_prism
    from career_evidence_graph.application_preparation_fixtures import SyntheticPrismClient

    root, _ = synthetic_project(tmp_path)

    def unexpected(*_args, **_kwargs):
        pytest.fail("A foreign project must be rejected before its source is read")

    monkeypatch.setattr(application_prism, "source_snapshot", unexpected)
    client = SyntheticPrismClient(root)
    binding = {"project_root": str(tmp_path / "foreign"), "main": "main.tex"}
    for operation in (client.open, client.compile):
        with pytest.raises(PortalDataError) as failed:
            operation(binding)
        assert failed.value.code == "synthetic_prism_source_invalid"


def test_uncertain_fixed_transport_survives_reopen_without_replay(tmp_path, monkeypatch):
    from career_evidence_graph.application_preparation_fixtures import SyntheticPrismClient
    from career_evidence_graph.application_prism import source_snapshot

    root, project = synthetic_project(tmp_path)
    client = SyntheticPrismClient(root)
    compile_fixture = client.compile
    calls = []

    def uncertain(binding):
        calls.append("compile")
        compile_fixture(binding)
        raise TimeoutError("Synthetic result was lost")

    monkeypatch.setattr(client, "compile", uncertain)
    store = PrismReviewStore(
        root / "runtime/uncertain-receipts",
        client=client,
        binding_provider=lambda: source_snapshot(project, "main.tex"),
    )
    with pytest.raises(PortalDataError):
        store.capture(store.binding()["source_revision"])
    pending = store.state()
    assert pending["status"] == "needs_recheck" and pending["pending_attempt_id"]
    retained = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    reopened = PrismReviewStore(store.root, client=client, binding_provider=store.binding_provider)
    assert reopened.state() == pending
    for operation in (
        lambda: reopened.capture(store.binding()["source_revision"]),
        reopened.reconcile,
    ):
        with pytest.raises(PortalDataError):
            operation()
    assert calls == ["compile"]
    assert reopened.state()["pending_attempt_id"] == pending["pending_attempt_id"]
    assert {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()} == retained
