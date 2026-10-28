"""Original v1 producer artifacts survive newer renderer and text-boundary rules."""

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from test_application_worker import service as service
from test_cover_letter_content import Compiler
from test_cover_letter_delivery import TEMPLATE, field
from test_cover_letter_delivery import modern as modern
from test_cover_letter_edit import editable as editable
from test_cover_letter_worker_readback import OriginalBuild
from test_supplemental_material_module import materials
from test_supplemental_material_module import prepared as prepared

from career_evidence_graph import application_cover_letter as letters
from career_evidence_graph import application_material_edit as editing
from career_evidence_graph import application_prism
from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.validation.hashing import record_digest as digest


@pytest.fixture(scope="module")
def original_v1():
    name = "career_evidence_graph._test_original_letter_v1"
    path = Path(__file__).parent / "fixtures/cover-letter-v1-producer.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert module.RENDERER_REVISION == "cover-letter-renderer/v1"
    return module


@pytest.fixture(autouse=True)
def no_real_compiler(monkeypatch):
    monkeypatch.setattr(
        application_prism,
        "PrismClient",
        lambda *a, **kw: pytest.fail("Legacy compatibility must use an explicit fake client"),
    )


def file_snapshot(directory):
    return {
        str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_real_v1_completed_local_receipt_reads_without_writes(modern, original_v1, tmp_path):
    _, fixed = modern
    content = fixed["cover_letter"]["result"]["content"]
    compiler = Compiler()
    directory = tmp_path / "original-v1"
    original = original_v1.export_cover_letter_pdf(
        directory, content, TEMPLATE, client=compiler, pdf_inspector=lambda _: 1
    )
    assert (
        original_v1.read_cover_letter_pdf(directory, content, TEMPLATE, pdf_inspector=lambda _: 1)
        == original
    )
    assert (
        original_v1.render_cover_letter(content, TEMPLATE)["tex"]
        == letters.render_cover_letter(content, TEMPLATE)["tex"]
    )
    before = file_snapshot(directory)
    assert (
        letters.read_cover_letter_pdf(directory, content, TEMPLATE, pdf_inspector=lambda _: 1)
        == original
    )
    assert file_snapshot(directory) == before
    assert compiler.calls == 1


@pytest.fixture
def old_pending(modern, original_v1):
    prepared, fixed = modern
    worker, job, batch = prepared
    client = OriginalBuild()
    worker.store.cover_letter_client = client
    worker.store.cover_letter_exporter = lambda directory, content, template: (
        original_v1.export_cover_letter_pdf(
            directory, content, template, client=client, pdf_inspector=lambda _: 1
        )
    )
    with pytest.raises(PortalDataError) as unknown:
        materials(prepared).prepare(
            job, batch, {"fields": [field(kind="file", required=True, accept=".pdf")]}
        )
    assert unknown.value.code == "letter_export_needs_recheck"
    state = worker.store.load()
    state.update(control="paused", current_job_id=job["application_id"])
    state["jobs"][0]["status"] = "needs_recheck"
    old = deepcopy(state["jobs"][0]["materials"][0])
    worker.store.save(state)
    worker.store.check_single = lambda *a, **kw: True
    worker.store.cover_letter_pdf_inspector = lambda _: 1
    worker.store.cover_letter_exporter = lambda *a, **kw: pytest.fail("No repeated compilation")
    directory = worker.store.root / "materials" / old["id"]
    intent = json.loads((directory / "export-intent.json").read_text())
    assert intent["renderer_revision"] == original_v1.RENDERER_REVISION
    assert (directory / "project/main.tex").read_text() == letters.render_cover_letter(
        old["letter_content"], TEMPLATE
    )["tex"]
    payload = {
        "application_id": job["application_id"],
        "material_id": old["id"],
        "expected_material_revision": digest(old),
        "request_id": "9" * 32,
    }
    return worker, fixed, client, old, directory, payload


def test_public_worker_reads_original_v1_pending_attempt_without_replay(old_pending):
    worker, fixed, client, old, directory, payload = old_pending
    source = (directory / "project/main.tex").read_bytes()
    body = deepcopy(fixed["cover_letter"])
    worker.request("recheck-cover-letter-file", payload)
    worker.request("recheck-cover-letter-file", payload)
    job = worker.store.load()["jobs"][0]
    recovered = job["materials"][0]
    assert recovered["id"] == old["id"] and recovered["status"] == "ready"
    assert recovered["renderer_revision"] == "cover-letter-renderer/v1"
    assert recovered["letter_content"] == old["letter_content"]
    assert recovered["content_revision"] == old["content_revision"]
    assert job["material_file_rechecks"][0]["previous_material"] == old
    assert len(job["material_file_rechecks"]) == 1
    assert (directory / "project/main.tex").read_bytes() == source
    assert fixed["cover_letter"] == body
    assert client.compiles == client.reads == 1


@pytest.mark.parametrize("damage", ["body", "template", "source", "unknown_renderer"])
def test_legacy_version_compatibility_does_not_ignore_original_bindings(old_pending, damage):
    worker, fixed, client, old, directory, payload = old_pending
    if damage == "body":
        fixed["cover_letter"]["result"]["content_revision"] = "different-body"
    elif damage == "template":
        path = worker.store.cover_letter_template
        path.write_text(path.read_text().replace("Dear Hiring Team", "Dear Changed Team"))
    elif damage == "source":
        path = directory / "project/main.tex"
        path.write_bytes(path.read_bytes() + b"% changed source\n")
    else:
        path = directory / "export-intent.json"
        intent = json.loads(path.read_text())
        intent["renderer_revision"] = "unknown-renderer"
        path.write_text(json.dumps(intent))
    before = worker.store.path.read_bytes()
    files = file_snapshot(directory)
    with pytest.raises(PortalDataError):
        worker.request("recheck-cover-letter-file", payload)
    assert worker.store.path.read_bytes() == before
    assert file_snapshot(directory) == files
    assert client.compiles == 1 and client.reads == 0


@pytest.mark.parametrize("damage", ["pdf_hash", "pages", "source_during_read"])
def test_legacy_readback_keeps_pdf_and_live_source_validation(old_pending, damage):
    worker, _, client, old, directory, payload = old_pending
    if damage == "pdf_hash":
        client.change = lambda result: result["build"].update(pdf_sha256="wrong")
    elif damage == "pages":
        worker.store.cover_letter_pdf_inspector = lambda _: 2
    else:

        def change_source(result):
            path = directory / "project/main.tex"
            path.write_bytes(path.read_bytes() + b"% changed during original read\n")

        client.change = change_source
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError):
        worker.request("recheck-cover-letter-file", payload)
    assert worker.store.path.read_bytes() == before
    assert worker.store.load()["jobs"][0]["materials"] == [old]
    assert client.compiles == client.reads == 1


@pytest.fixture
def old_editable(editable, original_v1):
    flow, worker, old, payload, state = editable
    template = TEMPLATE.replace(
        "Sincerely,\\\\\nSynthetic Applicant",
        "Thank you for your consideration.\n\nSincerely,\\\\\nSynthetic Applicant",
    )
    worker.store.cover_letter_template.write_text(template)
    produced = original_v1.render_cover_letter(old["letter_content"], template)
    current = letters.render_cover_letter(old["letter_content"], template)
    assert produced["tex"] == current["tex"]
    assert produced["text_suffix"] != current["text_suffix"]
    old.update(
        text=produced["text"],
        text_sha256=hashlib.sha256(produced["text"].encode()).hexdigest(),
        template_revision=produced["template_revision"],
        text_prefix=produced["text_prefix"],
        text_suffix=produced["text_suffix"],
    )
    saved = worker.store.load()
    saved["jobs"][0]["materials"][0] = deepcopy(old)
    worker.store.save(saved)
    payload.update(
        expected_text_sha256=old["text_sha256"],
        text=old["text"].replace("Built Python services", "Helped build Python services"),
    )
    return flow, worker, old, payload, state


def test_body_only_edit_of_real_v1_text_preserves_its_fixed_boundaries(old_editable):
    flow, worker, old, payload, state = old_editable
    assert editing.edit_material(flow, worker, None, payload)["status"] == "complete"
    job = worker.store.load()["jobs"][0]
    saved = job["materials"][0]
    assert saved["text"] == payload["text"]
    assert saved["text_prefix"] == old["text_prefix"]
    assert saved["text_suffix"] == old["text_suffix"]
    assert job["material_history"][-1] == old
    assert saved["letter_content"]["paragraphs"][0]["protected"] is True
    assert (
        state["tasks"][0]["cover_letter"]["content_history"][-1]["content_revision"]
        == old["content_revision"]
    )


@pytest.mark.parametrize("damage", ["greeting", "closing", "stored_bounds", "template"])
def test_legacy_body_mapping_rejects_fixed_or_unverifiable_changes(old_editable, damage):
    flow, worker, old, payload, _ = old_editable
    if damage == "greeting":
        payload["text"] = payload["text"].replace("Dear Hiring Team", "Dear Other Team")
    elif damage == "closing":
        payload["text"] = payload["text"].replace("Thank you", "Thanks")
    elif damage == "template":
        path = worker.store.cover_letter_template
        path.write_text(path.read_text().replace("Synthetic Applicant", "Different Applicant"))
    else:
        current = worker.store.load()
        current["jobs"][0]["materials"][0].update(text_prefix="", text_suffix="")
        worker.store.save(current)
        old = deepcopy(current["jobs"][0]["materials"][0])
    before = worker.store.path.read_bytes()
    with pytest.raises(PortalDataError) as blocked:
        editing.edit_material(flow, worker, None, payload)
    assert blocked.value.code == "letter_fixed_text_changed"
    assert worker.store.path.read_bytes() == before
    assert worker.store.load()["jobs"][0]["materials"][0] == old


def test_original_v1_pending_control_reads_exact_result(old_pending, original_v1):
    _, _, client, old, directory, _ = old_pending
    recovered = original_v1.reconcile_cover_letter_pdf(
        directory, old["letter_content"], TEMPLATE, client=client, pdf_inspector=lambda _: 1
    )
    assert recovered["renderer_revision"] == original_v1.RENDERER_REVISION
    assert Path(recovered["file_path"]).read_bytes() == client.raw
    assert client.compiles == client.reads == 1


def test_original_v1_mapping_control_accepts_same_body_edit(old_editable, original_v1, monkeypatch):
    flow, worker, _, payload, _ = old_editable
    monkeypatch.setattr(letters, "render_cover_letter", original_v1.render_cover_letter)
    assert editing.edit_material(flow, worker, None, payload)["status"] == "complete"
    assert worker.store.load()["jobs"][0]["materials"][0]["text"] == payload["text"]


def test_original_v1_ready_pdf_retains_public_reuse(modern, original_v1):
    prepared, _ = modern
    worker, job, batch = prepared
    compiler = Compiler()
    worker.store.cover_letter_exporter = lambda directory, content, template: (
        original_v1.export_cover_letter_pdf(
            directory, content, template, client=compiler, pdf_inspector=lambda _: 1
        )
    )
    question = field(kind="file", required=True, accept=".pdf")
    assert materials(prepared).prepare(job, batch, {"fields": [question]})
    saved = worker.store.load()["jobs"][0]
    assert (
        worker.store.field_material(question, saved)["renderer_revision"]
        == original_v1.RENDERER_REVISION
    )
    assert materials((worker, saved, batch)).prepare(saved, batch, {"fields": [question]})
    assert compiler.calls == 1


@pytest.mark.parametrize("intent", [[], None, "invalid", 3])
def test_malformed_legacy_intent_still_waits_without_reads(old_pending, intent):
    worker, _, client, old, directory, payload = old_pending
    path = directory / "export-intent.json"
    path.write_text(json.dumps(intent))
    before = worker.store.path.read_bytes()
    files = file_snapshot(directory)
    with pytest.raises(PortalDataError) as caught:
        worker.request("recheck-cover-letter-file", payload)
    assert caught.value.code == "letter_export_needs_recheck"
    assert worker.store.path.read_bytes() == before
    assert file_snapshot(directory) == files
    assert client.compiles == 1 and client.reads == 0


def test_known_v1_receipt_still_honors_caller_size_limit(modern, original_v1, tmp_path):
    _, fixed = modern
    content = fixed["cover_letter"]["result"]["content"]
    compiler = Compiler()
    directory = tmp_path / "original-v1-limit"
    original_v1.export_cover_letter_pdf(
        directory, content, TEMPLATE, client=compiler, pdf_inspector=lambda _: 1
    )
    before = file_snapshot(directory)
    with pytest.raises(PortalDataError) as caught:
        letters.read_cover_letter_pdf(
            directory, content, TEMPLATE, max_bytes=10, pdf_inspector=lambda _: 1
        )
    assert caught.value.code == "letter_export_needs_recheck"
    assert file_snapshot(directory) == before
    assert compiler.calls == 1
