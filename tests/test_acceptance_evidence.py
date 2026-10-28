"""Synthetic durable acceptance evidence survives owned work cleanup."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def evidence(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "acceptance_evidence", ROOT / "scripts/preserve_acceptance_evidence.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    monkeypatch.setattr(result, "TEMP_ROOTS", ())
    return result


def inputs(tmp_path, evidence):
    source = tmp_path / "source"
    source.mkdir()
    for name, content in {
        ".python-version": "3.13.14\n",
        "pyproject.toml": '[project]\nrequires-python = ">=3.13,<3.14"\n',
        "uv.lock": "version = 1\n",
        "_career_evidence_build.py": "# synthetic\n",
        "src/career_evidence_graph/__init__.py": "# synthetic loaded source\n",
    }.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    candidate = tmp_path / "candidate"
    manifest = evidence.freeze.create(source, candidate)
    app = tmp_path / "original-app"
    app.mkdir()
    (app / "binary").write_bytes(b"synthetic original app")
    config = tmp_path / "config.json"
    config.write_text('{"synthetic": true}\n')
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "source_revision": "synthetic-uncommitted",
                "loaded_sources": [manifest["files"][0]],
                "excluded_changes": [{"path": "private", "reason": "outside candidate scope"}],
                "historical_baseline": "unknown",
                "untracked_inputs": ["src/career_evidence_graph/__init__.py"],
                "source_observations": [],
            }
        )
    )
    return candidate, app, config, context


def test_baseline_preserves_candidate_app_config_before_execution(tmp_path, evidence):
    args = inputs(tmp_path, evidence)
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    evidence.begin(*args, output, work_parent)
    assert evidence.verify(output) == {
        "baseline_verified": True,
        "run_receipt_verified": False,
        "run_verified": False,
        "cleanup_verified": False,
    }
    assert (output / "baseline/original-app/binary").read_bytes() == b"synthetic original app"
    assert (output / "baseline/config.json").read_bytes() == b'{"synthetic": true}\n'
    assert all(
        path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
        for path in [output, *output.rglob("*")]
    )


def test_observed_process_receipts_survive_owned_cleanup_and_reopen(tmp_path, evidence):
    args = inputs(tmp_path, evidence)
    source_file = args[0] / "payload/src/career_evidence_graph/__init__.py"
    # Re-freeze after adding a real executable synthetic entry point.
    source = tmp_path / "source"
    (source / "src/career_evidence_graph/__init__.py").write_text(
        "from pathlib import Path\nPath('result.pdf').write_bytes(b'%PDF-synthetic')\n"
        "print('synthetic process observed')\n"
    )
    import shutil

    shutil.rmtree(args[0])
    manifest = evidence.freeze.create(source, args[0])
    context = json.loads(args[3].read_text())
    context["loaded_sources"] = [
        item
        for item in manifest["files"]
        if item["path"] == source_file.relative_to(args[0] / "payload").as_posix()
    ]
    args[3].write_text(json.dumps(context))
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    record = evidence.begin(*args, output, work_parent)
    assert evidence.run(output)["observed_returncode"] == 0
    assert (output / "run/stdout.bin").read_bytes() == b"synthetic process observed\n"
    evidence.cleanup(output)
    evidence.cleanup(output)
    assert not Path(record["work"]).exists()
    shutil.rmtree(tmp_path / "source")
    shutil.rmtree(args[0])
    assert evidence.verify(output) == {
        "baseline_verified": True,
        "run_receipt_verified": True,
        "run_verified": True,
        "cleanup_verified": True,
    }
    assert (output / "run/artifacts/result.pdf").read_bytes() == b"%PDF-synthetic"


@pytest.mark.parametrize("damage", ["missing", "corrupt", "permission", "symlink", "extra"])
def test_damaged_private_baseline_never_verifies_or_cleans(tmp_path, evidence, damage):
    args = inputs(tmp_path, evidence)
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    record = evidence.begin(*args, output, work_parent)
    target = output / "baseline/config.json"
    if damage == "missing":
        target.unlink()
    elif damage == "corrupt":
        target.write_bytes(b"changed")
    elif damage == "permission":
        target.chmod(0o644)
    elif damage == "symlink":
        target.unlink()
        target.symlink_to(args[2])
    else:
        (output / "unexpected").write_text("unlisted evidence")
        (output / "unexpected").chmod(0o600)
    with pytest.raises((ValueError, OSError)):
        evidence.verify(output)
    with pytest.raises((ValueError, OSError)):
        evidence.cleanup(output)
    assert Path(record["work"]).is_dir()


@pytest.mark.parametrize(
    "damage", ["loaded-source", "missing-app", "symlink", "containment", "temporary"]
)
def test_unsafe_or_ambiguous_source_stops_before_run(tmp_path, evidence, damage, monkeypatch):
    args = list(inputs(tmp_path, evidence))
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    if damage == "loaded-source":
        context = json.loads(args[3].read_text())
        context["loaded_sources"][0]["sha256"] = "0" * 64
        args[3].write_text(json.dumps(context))
    elif damage == "missing-app":
        (args[1] / "binary").unlink()
    elif damage == "symlink":
        target = args[1] / "binary"
        target.unlink()
        target.symlink_to(args[2])
    elif damage == "containment":
        output = args[0] / "durable"
    else:
        monkeypatch.setattr(evidence, "TEMP_ROOTS", (tmp_path,))
    with pytest.raises((ValueError, OSError)):
        evidence.begin(*args, output, work_parent)
    assert list(work_parent.iterdir()) == []


def test_original_permissions_are_retained_as_facts_not_inherited(tmp_path, evidence):
    args = inputs(tmp_path, evidence)
    args[2].chmod(0o644)
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    record = evidence.begin(*args, output, work_parent)
    assert record["source_modes"]["config.json"]["."] == "0644"
    assert (output / "baseline/config.json").stat().st_mode & 0o777 == 0o600


def test_timeout_keeps_raw_receipts_but_refuses_cleanup(tmp_path, evidence):
    args = inputs(tmp_path, evidence)
    source = tmp_path / "source"
    (source / "src/career_evidence_graph/__init__.py").write_text(
        'import time\nprint("entered", flush=True)\ntime.sleep(10)\n'
    )
    import shutil

    shutil.rmtree(args[0])
    manifest = evidence.freeze.create(source, args[0])
    context = json.loads(args[3].read_text())
    context["loaded_sources"] = [
        item for item in manifest["files"] if item["path"].endswith("__init__.py")
    ]
    args[3].write_text(json.dumps(context))
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    baseline = evidence.begin(*args, output, work_parent)
    receipt = evidence.run(output, timeout=0.1)
    assert evidence.verify(output)["run_verified"] is False
    assert evidence.verify(output)["run_receipt_verified"] is True
    assert receipt["timed_out"] is True
    assert receipt["observed_returncode"] != 0
    assert (output / "run/stdout.bin").read_bytes() == b"entered\n"
    with pytest.raises(ValueError, match="successful"):
        evidence.cleanup(output)
    assert Path(baseline["work"]).exists()


def test_copy_failure_leaves_failed_evidence_and_never_creates_work(
    tmp_path, evidence, monkeypatch
):
    args = inputs(tmp_path, evidence)
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    original = evidence._write

    def denied(path, content):
        if path.name == "binary":
            raise PermissionError("synthetic denied copy")
        return original(path, content)

    monkeypatch.setattr(evidence, "_write", denied)
    with pytest.raises(PermissionError):
        evidence.begin(*args, output, work_parent)
    assert output.is_dir()
    assert list(work_parent.iterdir()) == []
    with pytest.raises((OSError, ValueError)):
        evidence.verify(output)


@pytest.mark.parametrize("mutation", ["token", "work", "owner", "extra-work"])
def test_cleanup_rejects_changed_ownership_and_changed_work(tmp_path, evidence, mutation):
    args = inputs(tmp_path, evidence)
    context = json.loads(args[3].read_text())
    context["loaded_sources"] = [
        item
        for item in evidence.freeze.verify(args[0])["files"]
        if item["path"].endswith("__init__.py")
    ]
    args[3].write_text(json.dumps(context))
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    baseline = evidence.begin(*args, output, work_parent)
    evidence.run(output)
    work = Path(baseline["work"])
    if mutation in {"token", "work"}:
        baseline[mutation] = ".." if mutation == "token" else str(tmp_path / "unrelated")
        (output / "baseline.json").write_text(json.dumps(baseline))
    elif mutation == "owner":
        (work / ".acceptance-owner").write_text("different owner")
    else:
        (work / "new-work").write_text("not retained")
    with pytest.raises((OSError, ValueError)):
        evidence.cleanup(output)
    assert work.exists()


def test_work_cannot_be_created_inside_original_app(tmp_path, evidence):
    args = inputs(tmp_path, evidence)
    before = list(args[1].rglob("*"))
    with pytest.raises(ValueError, match="Work"):
        evidence.begin(*args, tmp_path / "durable", args[1])
    assert list(args[1].rglob("*")) == before


def test_changing_original_during_copy_never_seals_mixed_baseline(tmp_path, evidence, monkeypatch):
    args = inputs(tmp_path, evidence)
    output = tmp_path / "durable"
    work_parent = tmp_path / "workspaces"
    work_parent.mkdir()
    original = evidence._copy

    def changing(source, target):
        original(source, target)
        if source == args[1]:
            (source / "binary").write_bytes(b"changed during snapshot")

    monkeypatch.setattr(evidence, "_copy", changing)
    with pytest.raises(ValueError, match="changed"):
        evidence.begin(*args, output, work_parent)
    assert not (output / "baseline.json").exists()
    assert list(work_parent.iterdir()) == []
