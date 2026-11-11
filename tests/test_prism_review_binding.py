"""Job-scoped receipt bindings preserve standalone read and compile limits."""

import pytest
from test_standalone_prism_review import FakePrism

from career_evidence_graph.application_prism import source_snapshot, validate_archive
from career_evidence_graph.application_prism_review import PrismReviewStore
from career_evidence_graph.career_portal_data import PortalDataError


def make_bound_store(tmp_path, client=None):
    project = tmp_path / "job-version"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic job version")

    def provider():
        return source_snapshot(project, "main.tex")

    return (
        PrismReviewStore(
            tmp_path / "receipts", client=client or FakePrism(), binding_provider=provider
        ),
        project,
        provider,
    )


def test_provider_reads_create_no_config_or_receipt_and_capture_returns_verified_archive(tmp_path):
    store, project, provider = make_bound_store(tmp_path)
    before = sorted(tmp_path.rglob("*"))
    assert store.binding() == provider()
    assert store.state()["status"] == "empty"
    assert sorted(tmp_path.rglob("*")) == before
    captured = store.capture(provider()["source_revision"])
    identifier = captured["latest"]["id"]
    version = store.version(identifier)
    assert version["binding"] == provider()
    assert version["review_status"] == "pending_human_review"
    assert validate_archive(store.archive(identifier), version["binding"]) == store.source(
        identifier
    )
    assert store.source(identifier) == (project / "main.tex").read_bytes()
    assert not list(tmp_path.rglob("*config*"))


def test_live_provider_detects_edits_without_changing_immutable_archive(tmp_path):
    store, project, provider = make_bound_store(tmp_path)
    identifier = store.capture(provider()["source_revision"])["latest"]["id"]
    original = store.archive(identifier)
    original_binding = store.version(identifier)["binding"]
    (project / "main.tex").write_text("Edited synthetic source")
    assert store.state()["status"] == "source_changed"
    assert store.binding() != original_binding
    assert store.version(identifier)["binding"] == original_binding
    assert store.archive(identifier) == original


@pytest.mark.parametrize("damage", ["extra", "stale", "missing", "relative", "main"])
def test_provider_cannot_supply_unvalidated_or_stale_snapshot(tmp_path, damage):
    store, project, provider = make_bound_store(tmp_path)
    binding = provider()
    if damage == "extra":
        binding["untrusted"] = True
    elif damage == "stale":
        (project / "main.tex").write_text("New source")
    elif damage == "missing":
        del binding["files"]
    elif damage == "relative":
        binding["project_root"] = "relative"
    else:
        binding["main"] = "../main.tex"
    store.binding_provider = lambda: binding
    with pytest.raises(PortalDataError):
        store.binding()
    assert not store.root.exists()
    assert store.client.calls == []


def test_changed_provider_project_during_compile_retains_unknown_without_replay(tmp_path):
    current = [None]

    class SwitchingPrism(FakePrism):
        def compile(self, binding):
            result = super().compile(binding)
            current[0] = alternate
            return result

    client = SwitchingPrism()
    store, project, _provider = make_bound_store(tmp_path, client)
    alternate = tmp_path / "other-job"
    alternate.mkdir()
    (alternate / "main.tex").write_text("Synthetic job version")
    current[0] = project

    def provider():
        return source_snapshot(current[0], "main.tex")

    store.binding_provider = provider
    with pytest.raises(PortalDataError):
        store.capture(store.binding()["source_revision"])
    reopened = PrismReviewStore(store.root, client=client, binding_provider=provider)
    assert reopened.state()["status"] == "needs_recheck"
    with pytest.raises(PortalDataError):
        reopened.capture(reopened.binding()["source_revision"])
    assert client.calls == ["compile"]


def test_unknown_compile_survives_reopen_with_provider(tmp_path):
    class UncertainPrism(FakePrism):
        def compile(self, binding):
            self.calls.append("compile")
            raise TimeoutError("unknown result")

    client = UncertainPrism()
    store, _project, provider = make_bound_store(tmp_path, client)
    with pytest.raises(PortalDataError):
        store.capture(store.binding()["source_revision"])
    reopened = PrismReviewStore(store.root, client=client, binding_provider=provider)
    assert reopened.state()["status"] == "needs_recheck"
    with pytest.raises(PortalDataError):
        reopened.capture(reopened.binding()["source_revision"])
    with pytest.raises(PortalDataError):
        reopened.reconcile()
    assert client.calls == ["compile"]


@pytest.mark.parametrize("method", ["version", "archive"])
def test_new_receipt_readers_reject_tampered_archive(tmp_path, method):
    store, _project, provider = make_bound_store(tmp_path)
    identifier = store.capture(provider()["source_revision"])["latest"]["id"]
    (store.root / identifier / "latex-sources.json").write_bytes(b"{}")
    with pytest.raises(PortalDataError):
        getattr(store, method)(identifier)
