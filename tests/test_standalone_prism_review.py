"""Standalone review receipts do not require a job or approval."""

import json
from pathlib import Path

import pytest

from career_evidence_graph.career_portal_data import PortalDataError


class FakePrism:
    def __init__(self):
        self.calls = []

    def open(self, binding):
        self.calls.append("open")
        return "http://127.0.0.1:52073/"

    def compile(self, binding):
        self.calls.append("compile")
        return {
            "source_revision": binding["source_revision"],
            "pdf": (
                Path(__file__).parent / "fixtures/pdf-export/current-template.pdf"
            ).read_bytes(),
            "build": {"main": binding["main"], "exit": 0, "pdf_updated": True},
        }


def make_store(tmp_path, client=None):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    project = tmp_path / "latex"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    config = tmp_path / "resume-review.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    return PrismReviewStore(tmp_path / "receipts", config, client or FakePrism()), project


def test_capture_latest_saved_source_into_immutable_review_without_job_or_approval(tmp_path):
    store, project = make_store(tmp_path)
    empty = store.state()
    assert empty["status"] == "empty"
    assert not store.root.exists()
    captured = store.capture(empty["live_source_revision"])
    version = captured["latest"]
    assert captured["status"] == "ready"
    assert captured["source_changed"] is False
    assert version["review_status"] == "pending_human_review"
    assert version["page_count"] >= 1
    assert store.source(version["id"]) == (project / "main.tex").read_bytes()
    assert store.pdf(version["id"]).startswith(b"%PDF-")
    assert not list(tmp_path.rglob("*.md"))


def test_reads_and_editor_do_not_create_receipts_or_modify_sources(tmp_path):
    client = FakePrism()
    store, project = make_store(tmp_path, client)
    before = {path: path.read_bytes() for path in project.iterdir()}
    assert store.editor() == "http://127.0.0.1:52073/"
    assert store.state()["latest"] is None
    assert not store.root.exists()
    assert client.calls == ["open"]
    assert {path: path.read_bytes() for path in project.iterdir()} == before


def test_new_saved_source_keeps_old_receipt_and_stale_expected_revision_never_compiles(tmp_path):
    client = FakePrism()
    store, project = make_store(tmp_path, client)
    first = store.capture(store.state()["live_source_revision"])["latest"]
    (project / "main.tex").write_text("Changed synthetic source")
    changed = store.state()
    assert changed["status"] == "source_changed"
    assert changed["latest"] == first
    with pytest.raises(PortalDataError, match="源已变化"):
        store.capture(first["source_revision"])
    assert client.calls == ["compile"]
    assert store.source(first["id"]) == b"Synthetic source"
    second = store.capture(changed["live_source_revision"])
    assert len(second["versions"]) == 2
    assert second["latest"]["id"] != first["id"]
    assert store.source(first["id"]) == b"Synthetic source"


@pytest.mark.parametrize(
    "mutation", ["changed", "edit-undo", "mismatched-revision", "mismatched-build"]
)
def test_changed_or_mismatched_compile_cannot_replace_latest(tmp_path, mutation):
    store, project = make_store(tmp_path)
    first = store.capture(store.state()["live_source_revision"])["latest"]
    original = (project / "main.tex").read_bytes()

    class DamagedPrism(FakePrism):
        def compile(self, binding):
            result = super().compile(binding)
            if mutation in {"changed", "edit-undo"}:
                (project / "main.tex").write_text("changed during build")
                if mutation == "edit-undo":
                    (project / "main.tex").write_bytes(original)
            elif mutation == "mismatched-revision":
                result["source_revision"] = "0" * 64
            else:
                result["build"]["main"] = "other.tex"
            return result

    store.client = DamagedPrism()
    with pytest.raises(PortalDataError):
        store.capture(store.state()["live_source_revision"])
    assert store.state()["status"] == "needs_recheck"
    assert store.state()["latest"] == first


def test_unknown_request_is_persisted_before_compile_and_survives_restart(tmp_path):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    class UncertainPrism(FakePrism):
        def compile(self, binding):
            self.calls.append("compile")
            attempts = list(store.root.glob("*/intent.json"))
            assert len(attempts) == 1
            assert attempts[0].read_bytes()
            raise TimeoutError("private source path must not escape")

    client = UncertainPrism()
    store, _ = make_store(tmp_path, client)
    expected = store.state()["live_source_revision"]
    with pytest.raises(PortalDataError) as failure:
        store.capture(expected)
    assert "private" not in str(failure.value)
    restarted = PrismReviewStore(store.root, store.config_path, client)
    assert restarted.state()["status"] == "needs_recheck"
    with pytest.raises(PortalDataError):
        restarted.capture(expected)
    with pytest.raises(PortalDataError):
        restarted.reconcile()
    assert client.calls == ["compile"]


def test_explicit_reconcile_reads_complete_receipt_without_rebuilding(tmp_path):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    client = FakePrism()
    store, _ = make_store(tmp_path, client)
    first = store.capture(store.state()["live_source_revision"])
    restarted = PrismReviewStore(store.root, store.config_path, client)
    assert restarted.reconcile(first["latest"]["id"]) == first
    assert client.calls == ["compile"]


@pytest.mark.parametrize(
    "artifact", ["resume.tex", "latex-sources.json", "resume.pdf", "build.json"]
)
def test_tampered_archive_source_pdf_or_build_is_not_reviewable(tmp_path, artifact):
    store, _ = make_store(tmp_path)
    identifier = store.capture(store.state()["live_source_revision"])["latest"]["id"]
    (store.root / identifier / artifact).write_bytes(b"tampered")
    assert store.state()["status"] == "needs_recheck"
    with pytest.raises(PortalDataError):
        store.source(identifier)
    with pytest.raises(PortalDataError):
        store.pdf(identifier)


def test_source_unavailable_preserves_historical_review(tmp_path):
    store, project = make_store(tmp_path)
    first = store.capture(store.state()["live_source_revision"])["latest"]
    (project / "main.tex").unlink()
    state = store.state()
    assert state["status"] == "source_unavailable"
    assert state["latest"] == first
    assert store.pdf(first["id"]).startswith(b"%PDF-")


@pytest.mark.parametrize("damage", ["config-link", "project-link", "duplicate-key", "fifo"])
def test_config_redirect_or_duplicate_fields_cannot_compile(tmp_path, damage):
    import os

    client = FakePrism()
    store, project = make_store(tmp_path, client)
    if damage == "config-link":
        target = tmp_path / "real-config.json"
        store.config_path.rename(target)
        store.config_path.symlink_to(target)
    elif damage == "project-link":
        alias = tmp_path / "alias"
        alias.symlink_to(project)
        store.config_path.write_text(json.dumps({"project_root": str(alias), "main": "main.tex"}))
    elif damage == "duplicate-key":
        store.config_path.write_text('{"project_root":"x","main":"main.tex","main":"other.tex"}')
    else:
        store.config_path.unlink()
        os.mkfifo(store.config_path)
    assert store.state()["status"] == "source_unavailable"
    with pytest.raises(PortalDataError):
        store.capture("0" * 64)
    assert client.calls == []


def test_unsafe_version_identifier_cannot_read_outside_receipts(tmp_path):
    store, _ = make_store(tmp_path)
    with pytest.raises(PortalDataError):
        store.pdf("../outside")
    with pytest.raises(PortalDataError):
        store.source("/private/tmp/outside")


def test_known_failed_compile_allows_only_a_new_explicit_capture(tmp_path):
    class FailedPrism(FakePrism):
        def compile(self, binding):
            self.calls.append("compile")
            raise PortalDataError("resume_export_failed", "严格编译失败。", 503)

    store, _ = make_store(tmp_path, FailedPrism())
    revision = store.state()["live_source_revision"]
    with pytest.raises(PortalDataError):
        store.capture(revision)
    assert store.state()["status"] == "empty"
    assert store.client.calls == ["compile"]
    store.client = FakePrism()
    assert store.capture(revision)["status"] == "ready"


def test_unrelated_corrupt_receipt_preserves_last_valid_version(tmp_path):
    store, _ = make_store(tmp_path)
    first = store.capture(store.state()["live_source_revision"])["latest"]
    (store.root / "invalid-attempt").mkdir()
    state = store.state()
    assert state["status"] == "needs_recheck"
    assert state["latest"] == first


def test_receipt_reads_do_not_write_or_recompile(tmp_path):
    store, _ = make_store(tmp_path)
    first = store.capture(store.state()["live_source_revision"])["latest"]
    before = {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    store.state()
    store.reconcile(first["id"])
    store.source(first["id"])
    store.pdf(first["id"])
    store.editor()
    assert before == {path: path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
    assert store.client.calls == ["compile", "open"]


def test_completed_receipt_survives_lost_response_and_reconcile_never_repeats_build(
    tmp_path, monkeypatch
):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    store, _ = make_store(tmp_path)
    expected = store.state()["live_source_revision"]

    def lost_response():
        raise OSError("synthetic response interrupted")

    monkeypatch.setattr(store, "state", lost_response)
    with pytest.raises(PortalDataError):
        store.capture(expected)
    restarted = PrismReviewStore(store.root, store.config_path, store.client)
    assert restarted.reconcile()["status"] == "ready"
    assert store.client.calls == ["compile"]


def test_parallel_capture_is_rejected_before_a_second_attempt(tmp_path):
    import fcntl

    store, _ = make_store(tmp_path)
    revision = store.state()["live_source_revision"]
    store.root.mkdir()
    with (store.root / ".capture.lock").open("wb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(PortalDataError) as failure:
            store.capture(revision)
        assert failure.value.code == "prism_review_busy"
    assert store.client.calls == []
    assert not list(store.root.glob("*/intent.json"))


def test_native_inspector_counts_compressed_pdf_and_revalidates_immutable_reads(tmp_path):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    compressed_pdf = b"%PDF-1.5\nSynthetic compressed object stream, no raw Page marker\n%%EOF"

    class CompressedPrism(FakePrism):
        def compile(self, binding):
            result = super().compile(binding)
            result["pdf"] = compressed_pdf
            return result

    seen = []

    def inspector(raw):
        seen.append(raw)
        assert raw == compressed_pdf
        return 4

    store, _ = make_store(tmp_path, CompressedPrism())
    store = PrismReviewStore(store.root, store.config_path, store.client, pdf_inspector=inspector)
    version = store.capture(store.state()["live_source_revision"])["latest"]
    assert version["page_count"] == 4
    restarted = PrismReviewStore(
        store.root, store.config_path, store.client, pdf_inspector=inspector
    )
    assert restarted.state()["latest"] == version
    assert restarted.pdf(version["id"]) == compressed_pdf
    assert len(seen) >= 4
    assert store.client.calls == ["compile"]


def test_known_pdf_validation_failure_preserves_result_and_allows_only_explicit_retry(tmp_path):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    observed = []
    store, _ = make_store(tmp_path)

    def rejecting_inspector(raw):
        attempts = list(store.root.glob("*/resume.pdf"))
        assert len(attempts) == 1 and attempts[0].read_bytes() == raw
        assert (attempts[0].parent / "build.json").is_file()
        observed.append(raw)
        raise PortalDataError("resume_pdf_invalid", "PDF 不能核验。", 409)

    store = PrismReviewStore(
        store.root, store.config_path, store.client, pdf_inspector=rejecting_inspector
    )
    revision = store.state()["live_source_revision"]
    with pytest.raises(PortalDataError) as failure:
        store.capture(revision)
    assert failure.value.code == "resume_pdf_invalid"
    assert len(observed) == 1
    retained = list(store.root.glob("*/resume.pdf"))
    assert len(retained) == 1
    restarted = PrismReviewStore(store.root, store.config_path, store.client)
    assert restarted.state()["status"] == "empty"
    assert store.client.calls == ["compile"]
    assert restarted.capture(revision)["status"] == "ready"
    assert retained[0].read_bytes() == observed[0]
    assert store.client.calls == ["compile", "compile"]


def test_interrupted_pdf_inspection_remains_unknown_and_does_not_allow_retry(tmp_path):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    store, _ = make_store(tmp_path)

    def interrupted_inspector(_raw):
        raise RuntimeError("synthetic private helper interruption")

    store = PrismReviewStore(
        store.root, store.config_path, store.client, pdf_inspector=interrupted_inspector
    )
    revision = store.state()["live_source_revision"]
    with pytest.raises(PortalDataError) as failure:
        store.capture(revision)
    assert failure.value.code == "prism_review_needs_recheck"
    assert "private" not in str(failure.value)
    assert store.state()["status"] == "needs_recheck"
    assert len(list(store.root.glob("*/resume.pdf"))) == 1
    assert not list(store.root.glob("*/failed.json"))
    restarted = PrismReviewStore(store.root, store.config_path, store.client)
    with pytest.raises(PortalDataError):
        restarted.capture(revision)
    assert store.client.calls == ["compile"]


@pytest.mark.parametrize("pages", [0, -1, True, 4.0, "4", None])
def test_inspector_requires_a_positive_integer_page_count(tmp_path, pages):
    from career_evidence_graph.application_prism_review import PrismReviewStore

    store, _ = make_store(tmp_path)
    store = PrismReviewStore(
        store.root, store.config_path, store.client, pdf_inspector=lambda _raw: pages
    )
    with pytest.raises(PortalDataError) as failure:
        store.capture(store.state()["live_source_revision"])
    assert failure.value.code == "resume_pdf_invalid"
    assert store.state()["status"] == "empty"
    assert len(list(store.root.glob("*/resume.pdf"))) == 1
