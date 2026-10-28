"""A known strict snapshot is a new technical export, never an unknown-call repair."""

import hashlib
import json
from pathlib import Path

import pytest
from test_application_flow import application as application
from test_standalone_prism_review import FakePrism

from career_evidence_graph.application_prism import source_snapshot
from career_evidence_graph.application_prism_review import PrismReviewStore
from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.career_portal_data import CareerCatalog, PortalDataError


@pytest.fixture
def adoption(application, tmp_path):
    applications, job = application
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic reviewed source")
    binding = source_snapshot(project, "main.tex")
    client = FakePrism()
    reviews = PrismReviewStore(
        tmp_path / "reviews",
        client=client,
        binding_provider=lambda: source_snapshot(project, "main.tex"),
    )
    version = reviews.capture(binding["source_revision"])["latest"]
    career = tmp_path / "career"
    career.mkdir()
    store = ApplicationResumeStore(
        applications, CareerCatalog(career), tmp_path / "resumes", prism_client=client
    )
    inputs = {"fixture": "first"}
    draft = store.import_latex_for_task(
        job["id"], job["revision"], task_inputs=inputs, prism=binding
    )
    client.configuration = lambda: {"fixture": "strict"}

    def unknown(_binding):
        client.calls.append("unknown_compile")
        raise TimeoutError("Prism idle exited")

    client.compile = unknown
    with pytest.raises(PortalDataError):
        store.export_for_draft(
            draft["id"],
            draft["draft_sha256"],
            task_inputs=inputs,
            export_id="a" * 32,
            prism=binding | {"draft_id": draft["id"], "draft_sha256": draft["draft_sha256"]},
        )
    arguments = dict(
        task_inputs=inputs,
        export_id="b" * 32,
        review_store=reviews,
        review_version_id=version["id"],
        prior_export_id="a" * 32,
        expected_pdf_sha256=version["pdf_sha256"],
    )
    return store, reviews, client, draft, arguments


def test_known_snapshot_creates_distinct_export_without_replaying_unknown_compile(adoption):
    store, reviews, client, draft, arguments = adoption
    prior = {path: path.read_bytes() for path in (store.root / ("a" * 32)).iterdir()}
    result = store.adopt_review_snapshot(draft["id"], draft["draft_sha256"], **arguments)
    assert result["origin"] == "existing_latex"
    assert result["factual_review"] == "pending"
    assert result["operation_kind"] == "reuse_completed_review"
    assert result["review_snapshot_reuse"]["kind"] == "known_snapshot_reuse"
    assert result["pdf_sha256"] == arguments["expected_pdf_sha256"]
    assert (store.root / ("b" * 32) / "resume.pdf").read_bytes() == reviews.pdf(
        arguments["review_version_id"]
    )
    assert store.read_export("b" * 32) == result
    assert all(path.read_bytes() == raw for path, raw in prior.items())
    assert not (store.root / ("a" * 32) / "export.json").exists()
    assert client.calls == ["compile", "unknown_compile"]


def test_snapshot_build_bytes_are_copied_exactly_without_rewriting_compile_evidence(adoption):
    store, reviews, _client, draft, arguments = adoption
    directory = reviews.root / arguments["review_version_id"]
    raw = (directory / "build.json").read_bytes() + b"\n"
    (directory / "build.json").write_bytes(raw)
    receipt = json.loads((directory / "version.json").read_bytes())
    receipt["build_sha256"] = hashlib.sha256(raw).hexdigest()
    (directory / "version.json").write_text(json.dumps(receipt))
    assert (
        reviews.version(arguments["review_version_id"])["pdf_sha256"]
        == arguments["expected_pdf_sha256"]
    )
    store.adopt_review_snapshot(draft["id"], draft["draft_sha256"], **arguments)
    assert (store.root / ("b" * 32) / "prism-build.json").read_bytes() == raw


def test_reuse_export_cannot_be_downgraded_to_an_ordinary_compile(adoption):
    store, reviews, _client, draft, arguments = adoption
    store.adopt_review_snapshot(draft["id"], draft["draft_sha256"], **arguments)
    for name in ("export-intent.json", "export.json"):
        path = store.root / ("b" * 32) / name
        document = json.loads(path.read_bytes())
        document.pop("operation_kind")
        document.pop("review_snapshot_reuse")
        path.write_text(json.dumps(document))
    (reviews.root / arguments["review_version_id"] / "resume.tex").write_text("Tampered")
    with pytest.raises(PortalDataError):
        store.read_export("b" * 32)


@pytest.mark.parametrize(
    "damage",
    [
        "pdf",
        "archive",
        "source",
        "build",
        "version",
        "prior_intent",
        "prior_archive",
        "draft",
        "live_source",
        "reuse_receipt",
        "new_pdf",
        "new_build",
        "operation",
        "inputs",
        "job",
    ],
)
def test_reuse_reads_fail_closed_when_any_evidence_or_current_binding_changes(adoption, damage):
    store, reviews, client, draft, arguments = adoption
    store.adopt_review_snapshot(draft["id"], draft["draft_sha256"], **arguments)
    review_directory = reviews.root / arguments["review_version_id"]
    export_directory = store.root / ("b" * 32)
    files = {
        "pdf": review_directory / "resume.pdf",
        "archive": review_directory / "latex-sources.json",
        "source": review_directory / "resume.tex",
        "build": review_directory / "build.json",
        "version": review_directory / "version.json",
        "prior_intent": store.root / ("a" * 32) / "export-intent.json",
        "prior_archive": store.root / ("a" * 32) / "latex-sources.json",
        "draft": store.root / draft["id"] / "draft.json",
        "live_source": Path(draft["source_checkpoint"]["project_root"]) / "main.tex",
        "reuse_receipt": export_directory / "snapshot-reuse.json",
        "new_pdf": export_directory / "resume.pdf",
        "new_build": export_directory / "prism-build.json",
    }
    if damage in files:
        path = files[damage]
        path.write_bytes(path.read_bytes() + b"\n")
    elif damage in {"operation", "inputs"}:
        for name in ("export-intent.json", "export.json"):
            path = export_directory / name
            data = json.loads(path.read_bytes())
            if damage == "operation":
                data["operation_kind"] = "compile"
            else:
                data["task_inputs"] = {"fixture": "second"}
            path.write_text(json.dumps(data))
    else:
        current = store.applications.get_application(draft["application_id"])
        store.applications.update_application(
            draft["application_id"], {"job_description": "Changed JD"}, current["revision"]
        )
    with pytest.raises(PortalDataError) as error:
        store.read_export("b" * 32)
    assert error.value.code == "resume_export_needs_recheck"
    assert client.calls == ["compile", "unknown_compile"]


@pytest.mark.parametrize(
    "damage",
    ["pdf", "same_id", "inputs", "complete_prior", "other_project", "bad_version", "bad_export_id"],
)
def test_invalid_adoption_creates_no_export_directory_and_preserves_prior(
    adoption, damage, tmp_path
):
    store, reviews, client, draft, arguments = adoption
    prior_directory = store.root / ("a" * 32)
    if damage == "pdf":
        arguments["expected_pdf_sha256"] = "0" * 64
    elif damage == "same_id":
        arguments["export_id"] = "a" * 32
    elif damage == "inputs":
        arguments["task_inputs"] = {"fixture": "second"}
    elif damage == "complete_prior":
        (prior_directory / "export.json").write_text("{}")
    elif damage == "other_project":
        other = tmp_path / "other-project"
        other.mkdir()
        (other / "main.tex").write_bytes(reviews.source(arguments["review_version_id"]))
        alternate = PrismReviewStore(
            tmp_path / "other-reviews",
            client=FakePrism(),
            binding_provider=lambda: source_snapshot(other, "main.tex"),
        )
        version = alternate.capture(alternate.binding()["source_revision"])["latest"]
        assert (
            version["source_sha256"]
            == reviews.version(arguments["review_version_id"])["source_sha256"]
        )
        arguments.update(review_store=alternate, review_version_id=version["id"])
    elif damage == "bad_version":
        arguments["review_version_id"] = "../elsewhere"
    else:
        arguments["export_id"] = "../elsewhere"
    before = {path: path.read_bytes() for path in prior_directory.iterdir()}
    with pytest.raises(PortalDataError):
        store.adopt_review_snapshot(draft["id"], draft["draft_sha256"], **arguments)
    assert not (store.root / ("b" * 32)).exists()
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert client.calls == ["compile", "unknown_compile"]
