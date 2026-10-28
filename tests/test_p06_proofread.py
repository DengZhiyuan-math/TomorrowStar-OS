"""The human's TeX is authoritative; proofreading only supplies bounded text patches."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_proofread import (
    apply_text_patches,
    proofread,
    validate_record,
)


def document(text):
    return "\\documentclass{article}\n\\begin{document}\n" + text + "\n\\end{document}\n"


def patch(source, before, after, kind="spelling"):
    start = source.index(before)
    return dict(
        start=start,
        end=start + len(before),
        before=before,
        after=after,
        kind=kind,
        reason="Clear local text correction.",
    )


@pytest.mark.parametrize(
    ("before", "after", "kind"),
    [
        ("teh", "the", "spelling"),
        ("has", "have", "grammar"),
        ("the the", "the", "duplicate_word"),
        ("hello", "Hello", "capitalization"),
        ("Hello,", "Hello.", "punctuation"),
    ],
)
def test_local_clear_text_patch(before, after, kind):
    source = document(before)
    assert apply_text_patches(source, [patch(source, before, after, kind)]) == document(after)


@pytest.mark.parametrize(
    ("text", "before", "after", "kind"),
    [
        ("Built 20 projects", "20", "30", "spelling"),
        ("Built a project", "Built a project", "Led global strategy", "grammar"),
        ("Hello\nworld", "Hello\nworld", "Hello world", "punctuation"),
        (r"\\textbf{teh}", r"\\textbf", r"\\emph", "spelling"),
        ("% teh\nText", "teh", "the", "spelling"),
        ("$teh$", "teh", "the", "spelling"),
        (r"\(teh\)", "teh", "the", "spelling"),
        (r"\url{teh}", "teh", "the", "spelling"),
        (r"\label{teh}", "teh", "the", "spelling"),
        (r"\cite{teh}", "teh", "the", "spelling"),
        (r"\custom{teh}", "teh", "the", "spelling"),
        (r"\begin{verbatim}teh\end{verbatim}", "teh", "the", "spelling"),
        ("Acme", "Acme", "Acne", "spelling"),
        ("Product", "Product", "product", "capitalization"),
        ("Count 1,000", ",", ".", "punctuation"),
        ("Acme", "cme", "cne", "spelling"),
        ("$teh", "teh", "the", "spelling"),
        (r"\(teh", "teh", "the", "spelling"),
        (r"\\% teh", "teh", "the", "spelling"),
        ("the\tthe", "the\tthe", "the", "duplicate_word"),
        (r"\begin{equation}teh", "teh", "the", "spelling"),
        ("othe the", "the the", "the", "duplicate_word"),
        ("Visit https://example.test", ".", "", "punctuation"),
        ("Contact person@example.test", ".", "", "punctuation"),
        ("Visit example.test/about", ".", "", "punctuation"),
        (r"\begin{alignat}teh\end{alignat}", "teh", "the", "spelling"),
        (r"\begin{multline}teh\end{multline}", "teh", "the", "spelling"),
        (r"\begin{flalign*}teh\end{flalign*}", "teh", "the", "spelling"),
        (r"\begin{eqnarray}teh\end{eqnarray}", "teh", "the", "spelling"),
        (r"\begin{alignat}teh", "teh", "the", "spelling"),
        (r"\verb|teh", "teh", "the", "spelling"),
        (r"\verb*|teh", "teh", "the", "spelling"),
    ],
)
def test_unsafe_or_nonprose_patch_is_rejected(text, before, after, kind):
    source = document(text)
    with pytest.raises(ValueError):
        apply_text_patches(source, [patch(source, before, after, kind)])


def test_text_formatting_argument_is_corrected_without_command_change():
    source = document(r"\textbf{teh}")
    assert apply_text_patches(source, [patch(source, "teh", "the")]) == document(r"\textbf{the}")


def test_preamble_and_overlap_and_inexact_offsets_are_rejected():
    source = document("teh")
    p = patch(source, "teh", "the")
    for patches in ([p, p], [dict(p, start=p["start"] - 1)], [patch(source, "article", "articl")]):
        with pytest.raises(ValueError):
            apply_text_patches(source, patches)


def test_proofread_single_call_has_only_current_human_text_and_records_patches(tmp_path):
    source = document("teh")
    calls = []
    p = patch(source, "teh", "the")

    def runner(config, prompt, **options):
        calls.append((config, prompt, options))
        return SimpleNamespace(structured_result={"patches": [p], "notices": []})

    store = SimpleNamespace(model_runner=runner)
    record = proofread(store, tmp_path, source)
    assert record["status"] == "complete"
    assert record["latex_source"] == document("the")
    assert len(calls) == 1
    assert calls[0][0].workspace == tmp_path
    prompt = calls[0][1]
    for invariant in ("Do not", "proper names", "facts", "layout", "JD", "notices"):
        assert invariant in prompt
    schema = json.loads((tmp_path / "proofread-schema.json").read_text())
    assert schema["additionalProperties"] is False
    assert "latex_source" not in schema["properties"]
    assert validate_record(source, record) == document("the")
    assert (tmp_path / "proofread-input.json").exists()
    assert json.loads((tmp_path / "proofread-result.json").read_text()) == record
    assert proofread(store, tmp_path, source) == record
    assert len(calls) == 1


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"patches": [], "notices": [], "latex_source": "rewrite"},
        {"patches": [{"before": "teh"}], "notices": []},
    ],
)
def test_invalid_response_preserves_human_text_and_never_retries(tmp_path, result):
    calls = []

    def runner(*args, **kwargs):
        calls.append(True)
        if result is None:
            raise RuntimeError("private failure text")
        return SimpleNamespace(structured_result=result)

    source = document("teh")
    record = proofread(SimpleNamespace(model_runner=runner), tmp_path, source)
    assert len(calls) == 1
    assert record["status"] == "unavailable"
    assert record["latex_source"] == source
    assert record["patches"] == [] and record["notices"]
    assert "private failure text" not in json.dumps(record)
    assert validate_record(source, record) == source


def test_notices_keep_ambiguous_proper_names_unchanged(tmp_path):
    source = document("Acme")

    def runner(*a, **k):
        return SimpleNamespace(
            structured_result={"patches": [], "notices": ["Acme may be a proper name; preserved."]}
        )

    record = proofread(SimpleNamespace(model_runner=runner), tmp_path, source)
    assert record["status"] == "complete" and record["latex_source"] == source
    assert record["notices"]


def test_saved_record_hash_and_rebuilt_source_must_match(tmp_path):
    source = document("teh")

    def runner(*a, **k):
        return SimpleNamespace(
            structured_result={"patches": [patch(source, "teh", "the")], "notices": []}
        )

    record = proofread(SimpleNamespace(model_runner=runner), tmp_path, source)
    for altered in (
        dict(record, latex_source=source),
        dict(record, after_sha256="0" * 64),
        dict(record, before_sha256=hashlib.sha256(b"wrong").hexdigest()),
    ):
        with pytest.raises(ValueError):
            validate_record(source, altered)


def test_malformed_human_tex_and_empty_patches_preserve_original(tmp_path):
    source = "Human has not finished the TeX preamble yet."

    def runner(*a, **k):
        return SimpleNamespace(structured_result={"patches": [], "notices": []})

    record = proofread(SimpleNamespace(model_runner=runner), tmp_path, source)
    assert record["latex_source"] == source
    assert validate_record(source, record) == source


def test_interrupted_attempt_never_invokes_model_again(tmp_path):
    (tmp_path / "proofread-attempt.json").write_text("{}")
    store = SimpleNamespace(model_runner=lambda *a, **k: pytest.fail("No automatic retry"))
    record = proofread(store, tmp_path, document("teh"))
    assert record["status"] == "unavailable"
    assert record["latex_source"] == document("teh")


def test_one_unsafe_patch_rejects_entire_model_set_and_preserves_original(tmp_path):
    source = document("teh project count 20")

    def runner(*a, **k):
        return SimpleNamespace(
            structured_result={
                "patches": [patch(source, "teh", "the"), patch(source, "20", "30")],
                "notices": [],
            }
        )

    record = proofread(SimpleNamespace(model_runner=runner), tmp_path, source)
    assert record["status"] == "unavailable"
    assert record["latex_source"] == source and record["patches"] == []


def test_symlink_output_directory_is_rejected_without_write(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "linked"
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        proofread(SimpleNamespace(), target, document("teh"))
    assert list(outside.iterdir()) == []
