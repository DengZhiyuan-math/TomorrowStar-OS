"""Public Worker PDF recovery consumes exact original results with offline clients."""

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_worker import service as service
from test_cover_letter_delivery import field, revised_body
from test_cover_letter_delivery import modern as modern
from test_supplemental_material_module import materials
from test_supplemental_material_module import prepared as prepared

from career_evidence_graph import application_cover_letter as letter
from career_evidence_graph import application_prism
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


class OriginalBuild:
    """One compile completes remotely but loses its response to the caller."""

    def __init__(self):
        self.compiles = 0
        self.reads = 0
        self.binding = None
        self.raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
        self.change = lambda result: None

    def compile(self, binding):
        self.compiles += 1
        self.binding = deepcopy(binding)
        raise TimeoutError("Synthetic completed build response lost")

    def read_compiled(self, binding):
        self.reads += 1
        assert binding == self.binding
        result = {
            "binding": deepcopy(binding),
            "pdf": self.raw,
            "build": {
                "source_revision": binding["source_revision"],
                "pdf_sha256": hashlib.sha256(self.raw).hexdigest(),
                "status": "complete",
                "exit": 0,
            },
        }
        self.change(result)
        return result


@pytest.fixture
def lost_build(modern, monkeypatch):
    ready, fixed = modern
    worker, job, batch = ready
    revised_body(fixed)
    before_body = deepcopy(fixed["cover_letter"])
    client = OriginalBuild()
    worker.store.cover_letter_client = client
    monkeypatch.setattr(
        application_prism,
        "PrismClient",
        lambda *a, **kw: pytest.fail("Offline Worker must use the explicit readback client"),
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume_versions.TectonicCompiler",
        lambda *a, **kw: pytest.fail("Offline Worker must use the explicit readback client"),
    )
    worker.store.cover_letter_exporter = lambda directory, content, template: (
        letter.export_cover_letter_pdf(
            directory, content, template, client=client, pdf_inspector=lambda raw: 1
        )
    )
    # One real entry changes from an unsupported file type to a PDF destination.
    assert not materials(ready).prepare(
        job, batch, {"fields": [field(kind="file", required=True, accept="image/*")]}
    )
    assert client.compiles == 0
    assert fixed["cover_letter"] == before_body
    with pytest.raises(PortalDataError) as caught:
        materials(ready).prepare(
            job, batch, {"fields": [field(kind="file", required=True, accept=".pdf")]}
        )
    assert caught.value.code == "letter_export_needs_recheck"
    assert client.compiles == 1
    state = worker.store.load()
    state.update(control="paused", current_job_id=job["application_id"])
    state["jobs"][0]["status"] = "needs_recheck"
    original = deepcopy(state["jobs"][0]["materials"][0])
    worker.store.save(state)
    worker.store.check_single = lambda *a, **kw: True
    worker.store.cover_letter_pdf_inspector = lambda raw: 1
    worker.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("Repeated compile")
    payload = {
        "application_id": job["application_id"],
        "material_id": original["id"],
        "expected_material_revision": digest(original),
        "request_id": "e" * 32,
    }
    return worker, fixed, client, original, payload


def test_worker_recovers_exact_completed_lost_response_and_keeps_human_body(lost_build):
    worker, fixed, client, original, payload = lost_build
    before_body = deepcopy(fixed["cover_letter"])
    worker.request("recheck-cover-letter-file", payload)
    worker.request("recheck-cover-letter-file", payload)
    job = worker.store.load()["jobs"][0]
    recovered = job["materials"][0]
    assert recovered["id"] == original["id"] and recovered["status"] == "ready"
    assert recovered["letter_content"] == original["letter_content"]
    assert recovered["content_revision"] == original["content_revision"]
    assert recovered["letter_content"]["paragraphs"][0]["origin"] == "human"
    assert Path(recovered["file_path"]).read_bytes() == client.raw
    assert job["material_file_rechecks"][0]["previous_material"] == original
    assert len(job["material_file_rechecks"]) == 1
    assert fixed["cover_letter"] == before_body
    assert client.compiles == client.reads == 1


@pytest.mark.parametrize(
    "corruption,code,reads",
    [
        ("incomplete", "letter_export_needs_recheck", 1),
        ("unreadable", "letter_export_needs_recheck", 1),
        ("unavailable", "letter_export_needs_recheck", 1),
        ("project", "letter_export_needs_recheck", 1),
        ("main", "letter_export_needs_recheck", 1),
        ("files", "letter_export_needs_recheck", 1),
        ("build_revision", "letter_export_needs_recheck", 1),
        ("pdf_hash", "letter_export_needs_recheck", 1),
        ("pdf_format", "letter_export_needs_recheck", 1),
        ("pages", "letter_export_needs_recheck", 1),
        ("unverified_pages", "letter_export_needs_recheck", 1),
        ("body", "material_recheck_changed", 0),
        ("template", "letter_export_needs_recheck", 0),
        ("source", "letter_export_needs_recheck", 0),
        ("source_during_read", "letter_export_needs_recheck", 1),
        ("fact", "material_input_changed", 1),
    ],
)
def test_worker_does_not_adopt_unverified_original_pdf(lost_build, corruption, code, reads):
    worker, fixed, client, original, payload = lost_build
    path = worker.store.root / "materials" / original["id"] / "project" / "main.tex"

    def corrupt(result):
        if corruption == "incomplete":
            result["build"]["status"] = "running"
        elif corruption == "unreadable":
            raise OSError("Synthetic original result unreadable")
        elif corruption == "unavailable":
            raise PortalDataError("prism_unavailable", "Synthetic unavailable result", 409)
        elif corruption == "project":
            result["binding"]["project_root"] += "-other"
        elif corruption == "main":
            result["binding"]["main"] = "other.tex"
        elif corruption == "files":
            result["binding"]["files"] = []
        elif corruption == "build_revision":
            result["build"]["source_revision"] = "wrong"
        elif corruption == "pdf_hash":
            result["build"]["pdf_sha256"] = "wrong"
        elif corruption == "pdf_format":
            result["pdf"] = b"not a PDF"
            result["build"]["pdf_sha256"] = hashlib.sha256(result["pdf"]).hexdigest()
        elif corruption == "source_during_read":
            path.write_text(path.read_text() + "% Human edit during read\n")

    client.change = corrupt
    if corruption == "body":
        fixed["cover_letter"]["result"]["content_revision"] = "new-body"
    elif corruption == "template":
        template = worker.store.cover_letter_template
        template.write_text(template.read_text().replace("Dear Hiring Team", "Dear Changed Team"))
    elif corruption == "source":
        path.write_text(path.read_text() + "% Human edit\n")
    elif corruption == "pdf_format":
        worker.store.cover_letter_pdf_inspector = None
    elif corruption in {"pages", "unverified_pages"}:
        worker.store.cover_letter_pdf_inspector = lambda raw: 2 if corruption == "pages" else None
    elif corruption == "fact":
        fixed["sources"]["items"][0]["text"] = "Changed source fact"
    state_before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as caught:
        worker.request("recheck-cover-letter-file", payload)
    assert caught.value.code == code
    assert worker.store.path.read_bytes() == state_before
    assert worker.store.load()["jobs"][0]["materials"] == [original]
    assert client.compiles == 1 and client.reads == reads


@pytest.mark.parametrize("guard", ["running", "other_current", "intent", "manual_edit"])
def test_worker_readback_preserves_existing_operation_admission(lost_build, guard):
    worker, fixed, client, original, payload = lost_build
    state = worker.store.load()
    if guard == "running":
        state["control"] = "running"
    elif guard == "other_current":
        other = deepcopy(state["jobs"][0])
        other["application_id"] = "f" * 32
        state["jobs"].append(other)
        state["current_job_id"] = other["application_id"]
    elif guard == "intent":
        state["jobs"][0]["intent"] = {"id": "unknown-web-action", "action": "upload"}
    else:
        state["jobs"][0]["material_edit"] = {"status": "needs_recheck"}
    worker.store.save(state)
    with pytest.raises(PortalDataError) as caught:
        worker.request("recheck-cover-letter-file", payload)
    assert caught.value.code == "material_recheck_pause_required"
    assert client.compiles == 1 and client.reads == 0
    assert worker.store.load()["jobs"][0]["materials"] == [original]


def test_worker_accepts_real_client_dependency_policy_for_identical_compiled_files(lost_build):
    worker, fixed, client, original, payload = lost_build

    def actual_dependencies(result):
        actual = application_prism.dependency_snapshot(
            Path(result["binding"]["project_root"]),
            result["binding"]["main"],
            result["binding"]["files"],
        )
        result["binding"] = actual
        result["build"]["source_revision"] = actual["source_revision"]

    client.change = actual_dependencies
    worker.request("recheck-cover-letter-file", payload)
    assert worker.store.load()["jobs"][0]["materials"][0]["status"] == "ready"
    assert client.compiles == client.reads == 1


def test_worker_recheck_request_id_cannot_be_rebound_after_adoption(lost_build):
    worker, fixed, client, original, payload = lost_build
    worker.request("recheck-cover-letter-file", payload)
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as caught:
        worker.request("recheck-cover-letter-file", payload | {"material_id": "f" * 32})
    assert caught.value.code == "material_recheck_changed"
    assert worker.store.path.read_bytes() == before
    assert client.compiles == client.reads == 1


@pytest.mark.parametrize(
    "redirect",
    [
        "letter.pdf",
        "build.json",
        "export.json",
        "directory",
        "materials",
        "dangling_pdf",
        "during_read",
    ],
)
def test_worker_readback_preserves_redirected_outputs(lost_build, tmp_path, redirect):
    worker, fixed, client, original, payload = lost_build
    directory = worker.store.root / "materials" / original["id"]
    sentinel = tmp_path / "human-document.txt"
    sentinel.write_bytes(b"preserve human document")

    def redirect_file():
        (directory / "letter.pdf").symlink_to(sentinel)

    if redirect == "during_read":
        client.change = lambda result: redirect_file()
    elif redirect in {"directory", "materials"}:
        path = directory if redirect == "directory" else directory.parent
        target = tmp_path / "preserved-material-directory"
        path.rename(target)
        path.symlink_to(target, target_is_directory=True)
    elif redirect == "dangling_pdf":
        sentinel.unlink()
        redirect_file()
    else:
        (directory / redirect).symlink_to(sentinel)
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        worker.request("recheck-cover-letter-file", payload)
    assert worker.store.path.read_bytes() == before
    assert worker.store.load()["jobs"][0]["materials"] == [original]
    if redirect == "dangling_pdf":
        assert not sentinel.exists()
    else:
        assert sentinel.read_bytes() == b"preserve human document"
    assert client.compiles == 1
    assert client.reads == int(redirect == "during_read")


@pytest.mark.parametrize("partial", ["complete_bad_pdf", "pdf_only", "build_only", "export_only"])
def test_worker_readback_preserves_conflicting_local_evidence(lost_build, partial):
    import json

    worker, fixed, client, original, payload = lost_build
    directory = worker.store.root / "materials" / original["id"]
    if partial in {"complete_bad_pdf", "pdf_only"}:
        (directory / "letter.pdf").write_bytes(b"human modified PDF content")
    if partial == "complete_bad_pdf":
        (directory / "build.json").write_text(
            json.dumps(
                {
                    "source_revision": client.binding["source_revision"],
                    "pdf_sha256": hashlib.sha256(client.raw).hexdigest(),
                    "build": {"exit": 0},
                }
            )
        )
    elif partial == "build_only":
        (directory / "build.json").write_text("human incomplete receipt")
    elif partial == "export_only":
        (directory / "export.json").write_text("human incomplete receipt")
    before_files = {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        worker.request("recheck-cover-letter-file", payload)
    assert worker.store.path.read_bytes() == before
    assert before_files == {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }
    assert client.compiles == 1


@pytest.mark.parametrize("present", ["pdf", "build"])
def test_worker_recovers_missing_output_without_rewriting_matching_partial_evidence(
    lost_build, present
):
    import json

    worker, fixed, client, original, payload = lost_build
    directory = worker.store.root / "materials" / original["id"]
    if present == "pdf":
        path = directory / "letter.pdf"
        path.write_bytes(client.raw)
    else:
        path = directory / "build.json"
        path.write_text(
            json.dumps(
                {
                    "source_revision": client.binding["source_revision"],
                    "pdf_sha256": hashlib.sha256(client.raw).hexdigest(),
                    "build": {"exit": 0},
                }
            )
        )
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    worker.request("recheck-cover-letter-file", payload)
    assert worker.store.load()["jobs"][0]["materials"][0]["status"] == "ready"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert client.compiles == client.reads == 1


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("page_limit", [64_000, 70_000])
def test_original_page_size_limit_survives_local_and_remote_recheck(
    modern, monkeypatch, local, page_limit
):
    import json

    ready, fixed = modern
    worker, job, batch = ready
    revised_body(fixed)
    body = deepcopy(fixed["cover_letter"])
    client = OriginalBuild()
    worker.store.cover_letter_client = client
    monkeypatch.setattr(
        application_prism, "PrismClient", lambda *a, **kw: pytest.fail("No real Prism")
    )
    monkeypatch.setattr(
        "career_evidence_graph.application_resume_versions.TectonicCompiler",
        lambda *a, **kw: pytest.fail("No real Prism"),
    )
    seen = []
    export = letter.export_cover_letter_pdf

    def observe_export(*args, **kwargs):
        seen.append(kwargs["max_bytes"])
        return export(*args, **kwargs)

    monkeypatch.setattr(letter, "export_cover_letter_pdf", observe_export)
    question = field(kind="file", required=True, accept=".pdf", max_bytes=page_limit)
    with pytest.raises(PortalDataError) as caught:
        materials(ready).prepare(job, batch, {"fields": [question]})
    assert caught.value.code == "letter_export_needs_recheck"
    assert seen == [page_limit] and len(client.raw) > page_limit
    state = worker.store.load()
    state.update(control="paused", current_job_id=job["application_id"])
    state["jobs"][0]["status"] = "needs_recheck"
    original = deepcopy(state["jobs"][0]["materials"][0])
    worker.store.save(state)
    worker.store.check_single = lambda *a, **kw: True
    worker.store.cover_letter_pdf_inspector = lambda raw: 1
    directory = worker.store.root / "materials" / original["id"]
    if local:
        (directory / "letter.pdf").write_bytes(client.raw)
        (directory / "build.json").write_text(
            json.dumps(
                {
                    "source_revision": client.binding["source_revision"],
                    "pdf_sha256": hashlib.sha256(client.raw).hexdigest(),
                    "build": {"exit": 0},
                }
            )
        )
    before = worker.store.path.read_bytes()
    files_before = {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }
    with pytest.raises(PortalDataError) as rejected:
        worker.request(
            "recheck-cover-letter-file",
            {
                "application_id": job["application_id"],
                "material_id": original["id"],
                "expected_material_revision": digest(original),
                "request_id": "8" * 32,
            },
        )
    assert rejected.value.code == "letter_export_needs_recheck"
    assert original["max_bytes"] == page_limit
    assert worker.store.path.read_bytes() == before
    assert worker.store.load()["jobs"][0]["materials"] == [original]
    assert files_before == {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }
    assert fixed["cover_letter"] == body
    assert client.compiles == 1 and client.reads == int(not local)


@pytest.mark.parametrize("legacy", [False, True])
def test_retained_current_page_limit_cannot_be_broadened_during_recheck(lost_build, legacy):
    worker, fixed, client, original, payload = lost_build
    state = worker.store.load()
    current = state["jobs"][0]
    current["form_state"] = {
        "snapshot": {
            "fields": [
                field(kind="file", required=True, accept=".pdf", max_bytes=len(client.raw) - 1)
            ]
        }
    }
    if legacy:
        current["materials"][0].pop("max_bytes", None)
    original = deepcopy(current["materials"][0])
    payload["expected_material_revision"] = digest(original)
    worker.store.save(state)
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as rejected:
        worker.request("recheck-cover-letter-file", payload)
    assert rejected.value.code == "letter_export_needs_recheck"
    assert worker.store.path.read_bytes() == before
    assert client.compiles == client.reads == 1


def test_legacy_unknown_file_without_page_limit_keeps_existing_default(lost_build):
    worker, fixed, client, original, payload = lost_build
    state = worker.store.load()
    state["jobs"][0]["materials"][0].pop("max_bytes", None)
    original = deepcopy(state["jobs"][0]["materials"][0])
    payload["expected_material_revision"] = digest(original)
    worker.store.save(state)
    worker.request("recheck-cover-letter-file", payload)
    assert worker.store.load()["jobs"][0]["materials"][0]["status"] == "ready"
    assert client.compiles == client.reads == 1


def test_recheck_does_not_guess_a_malformed_original_limit(lost_build):
    worker, fixed, client, original, payload = lost_build
    state = worker.store.load()
    state["jobs"][0]["materials"][0]["max_bytes"] = "700000"
    original = deepcopy(state["jobs"][0]["materials"][0])
    payload["expected_material_revision"] = digest(original)
    worker.store.save(state)
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as rejected:
        worker.request("recheck-cover-letter-file", payload)
    assert rejected.value.code == "cover_letter_file_limit_invalid"
    assert worker.store.path.read_bytes() == before
    assert client.compiles == 1 and client.reads == 0


def test_worker_readback_falls_back_to_the_resume_pdf_inspector(lost_build):
    """2026-11-03: no letter inspector was injected, so a valid PDF 1.5 hit the regex."""
    worker, _fixed, _client, original, payload = lost_build
    del worker.store.cover_letter_pdf_inspector
    pages = []
    worker.store.pdf_inspector = lambda raw: pages.append(raw) or 1
    worker.request("recheck-cover-letter-file", payload)
    recovered = worker.store.load()["jobs"][0]["materials"][0]
    assert recovered["id"] == original["id"] and recovered["status"] == "ready"
    assert pages
