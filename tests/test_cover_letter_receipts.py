"""Native invocation bindings and lost PDF publications recover without execution."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_cover_letter_content import TEMPLATE, Compiler, inputs, native, output, phase, ready
from test_material_consistency import pair as pair

from career_evidence_graph import application_cover_letter as letters
from career_evidence_graph.application_material_consistency import (
    check_material_consistency,
    read_material_consistency,
)
from career_evidence_graph.career_portal_data import PortalDataError


def native_letter(config, prompt, **kwargs):
    value = (
        {"supported": True, "reason": "Exact source scope."}
        if phase(prompt) == "review-schema.json"
        else output()
    )
    return native(config, prompt, value)


@pytest.mark.parametrize("phase", ["writer", "review"])
@pytest.mark.parametrize("corruption", ["prompt_hash", "output_schema_hash", "raw_stdout_jsonl"])
def test_letter_read_rejects_mismatched_native_invocation(tmp_path, phase, corruption):
    app, fixed, sources = inputs()
    directory = tmp_path / "author"
    letters.generate_cover_letter(directory, app, fixed, sources=sources, runner=native_letter)
    path = directory / ("generation.json" if phase == "writer" else "review.json")
    recorded = json.loads(path.read_text())
    recorded[corruption] = "different native invocation"
    path.write_text(json.dumps(recorded))
    before = {file.name: file.read_bytes() for file in directory.iterdir() if file.is_file()}
    with pytest.raises(PortalDataError) as error:
        letters.read_cover_letter_result(directory, app, fixed, sources=sources)
    assert error.value.code == "letter_generation_needs_recheck"
    assert before == {
        file.name: file.read_bytes() for file in directory.iterdir() if file.is_file()
    }


def test_initial_letter_does_not_adopt_unbound_native_writer(tmp_path):
    def wrong(config, prompt, **kwargs):
        return native(config, "An unrelated prompt", output())

    with pytest.raises(PortalDataError) as error:
        letters.generate_cover_letter(
            tmp_path / "author", *inputs()[:2], sources=inputs()[2], runner=wrong
        )
    assert error.value.code == "letter_generation_needs_recheck"
    assert not (tmp_path / "author/material.json").exists()


def test_pair_recovery_rejects_swapped_native_review(tmp_path, pair):
    directory = tmp_path / "pair"
    check_material_consistency(
        directory,
        *pair,
        runner=lambda config, prompt, **kwargs: native(
            config, prompt, {"consistent": True, "issues": []}
        ),
    )
    path = directory / "review.json"
    recorded = json.loads(path.read_text())
    recorded["prompt_hash"] = "0" * 64
    path.write_text(json.dumps(recorded))
    with pytest.raises(PortalDataError) as error:
        read_material_consistency(directory, *pair)
    assert error.value.code == "material_consistency_needs_recheck"


def test_cancel_after_writer_preserves_body_and_never_starts_reviewer(tmp_path):
    calls = []
    allowed = True

    def writer(config, prompt, **kwargs):
        nonlocal allowed
        calls.append(phase(prompt))
        allowed = False
        return native_letter(config, prompt)

    directory = tmp_path / "author"
    with pytest.raises(PortalDataError) as error:
        letters.generate_cover_letter(
            directory, *inputs()[:2], sources=inputs()[2], runner=writer, admit_call=lambda: allowed
        )
    assert error.value.code == "letter_generation_failed"
    assert calls == ["schema.json"]
    assert (directory / "draft.json").is_file()
    assert json.loads((directory / "failure.json").read_text())["stage"] == "cancelled"


def test_local_pdf_read_recovers_lost_publication_without_writes_or_compile(tmp_path, monkeypatch):
    content = ready(tmp_path)["content"]
    directory = tmp_path / "pdf"
    compiler = Compiler()
    original = letters.helper.atomic_write_json

    def lose_publication(path, value):
        if path.name == "export.json":
            raise OSError("synthetic lost publication")
        return original(path, value)

    monkeypatch.setattr(letters.helper, "atomic_write_json", lose_publication)
    with pytest.raises(PortalDataError):
        letters.export_cover_letter_pdf(
            directory, content, TEMPLATE, client=compiler, pdf_inspector=lambda _: 1
        )
    before = {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }
    recovered = letters.read_cover_letter_pdf(
        directory, content, TEMPLATE, pdf_inspector=lambda _: 1
    )
    assert recovered["content_revision"] == content["revision"]
    assert compiler.calls == 1 and not (directory / "export.json").exists()
    assert before == {
        str(path.relative_to(directory)): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }
    build = json.loads((directory / "build.json").read_text())
    assert build["pdf_sha256"] == recovered["sha256"]


def test_pdf_reconciliation_reads_existing_prism_output_and_never_builds_again(tmp_path):
    from pathlib import Path

    content = ready(tmp_path)["content"]
    directory = tmp_path / "pdf"
    compiler = Compiler(unknown=True)
    with pytest.raises(PortalDataError):
        letters.export_cover_letter_pdf(directory, content, TEMPLATE, client=compiler)

    class Readback:
        calls = 0

        def read_compiled(self, binding):
            self.calls += 1
            raw = (Path(__file__).parent / "fixtures/pdf-export/current-template.pdf").read_bytes()
            return {
                "binding": deepcopy(binding),
                "pdf": raw,
                "build": {
                    "status": "complete",
                    "exit": 0,
                    "source_revision": binding["source_revision"],
                    "pdf_sha256": hashlib.sha256(raw).hexdigest(),
                },
            }

    client = Readback()
    recovered = letters.reconcile_cover_letter_pdf(
        directory, content, TEMPLATE, client=client, pdf_inspector=lambda _: 1
    )
    assert client.calls == 1 and compiler.calls == 1
    assert recovered["page_count"] == 1
    assert (
        letters.read_cover_letter_pdf(directory, content, TEMPLATE, pdf_inspector=lambda _: 1)
        == recovered
    )
