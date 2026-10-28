"""Preserve an explicit private synthetic acceptance baseline and owned work receipts.

This does not certify installed App identity, historical runs or human acceptance.
All detailed manifests and raw subprocess output stay in the private destination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import freeze_preparation_candidate as freeze

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOTS = (Path(tempfile.gettempdir()).resolve(), Path("/private/tmp"), Path("/tmp"))


def _write(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        os.chmod(path, 0o600)
        handle.write(content)
    if freeze._read(path) != content or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("Copy bytes or permissions failed verification.")


def _entries(root: Path) -> list[dict]:
    freeze._safe_path(root)
    if not root.is_dir():
        raise ValueError("Expected an accessible directory.")
    entries = []
    for path in sorted(root.rglob("*")):
        freeze._safe_path(path)
        if path.is_dir():
            entries.append({"path": path.relative_to(root).as_posix(), "directory": True})
            continue
        content = freeze._read(path)
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    return entries


def _snapshot(source: Path) -> list[dict]:
    if source.is_dir():
        return _entries(source)
    content = freeze._read(source)
    return [{"path": ".", "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}]


def _copy(source: Path, destination: Path) -> None:
    freeze._safe_path(source)
    if source.is_dir():
        destination.mkdir(mode=0o700)
        for path in sorted(source.iterdir()):
            _copy(path, destination / path.name)
    else:
        _write(destination, freeze._read(source))


def _load(path: Path) -> dict:
    value = json.loads(freeze._read(path), object_pairs_hook=freeze._object)
    if not isinstance(value, dict):
        raise ValueError("Expected an evidence object.")
    return value


def _permissions(root: Path) -> None:
    for path in (root, *root.rglob("*")):
        freeze._safe_path(path)
        if stat.S_IMODE(path.stat().st_mode) != (0o700 if path.is_dir() else 0o600):
            raise ValueError("Private evidence permission drift; preserve and investigate.")


def _context(candidate: Path, context: dict) -> None:
    manifest = freeze.verify(candidate)
    if set(context) != {
        "source_revision",
        "loaded_sources",
        "excluded_changes",
        "historical_baseline",
        "untracked_inputs",
        "source_observations",
    }:
        raise ValueError("Source context is incomplete.")
    if not isinstance(context["source_revision"], str) or not context["source_revision"]:
        raise ValueError("Source revision is missing.")
    loaded = context["loaded_sources"]
    if not isinstance(loaded, list) or not loaded:
        raise ValueError("Actual loaded source is ambiguous.")
    if any(item not in manifest["files"] for item in loaded):
        raise ValueError("Actual loaded source does not match the candidate inventory.")
    untracked = context["untracked_inputs"]
    if (
        not isinstance(untracked, list)
        or any(not isinstance(path, str) for path in untracked)
        or not set(untracked).issubset({item["path"] for item in manifest["files"]})
    ):
        raise ValueError("Untracked candidate inputs must name retained manifest entries.")
    observations = context["source_observations"]
    if not isinstance(observations, list) or any(
        not isinstance(item, dict)
        or set(item) != {"argv", "stdout", "stderr", "returncode"}
        or not isinstance(item["argv"], list)
        or not item["argv"]
        or any(not isinstance(arg, str) for arg in item["argv"])
        or not isinstance(item["stdout"], str)
        or not isinstance(item["stderr"], str)
        or type(item["returncode"]) is not int
        for item in observations
    ):
        raise ValueError("Source observations need raw command and result records.")
    if context["historical_baseline"] != "unknown":
        raise ValueError("A new baseline cannot retrospectively certify historical runs.")
    excluded = context["excluded_changes"]
    if not isinstance(excluded, list) or any(
        not isinstance(item, dict)
        or set(item) != {"path", "reason"}
        or any(not isinstance(value, str) or not value for value in item.values())
        for item in excluded
    ):
        raise ValueError("Excluded changes need explicit reasons.")


def begin(
    candidate: Path,
    original_app: Path,
    config: Path,
    context: Path,
    output: Path,
    work_parent: Path,
) -> dict:
    """Copy a baseline before creating an isolated work directory; never overwrite."""
    output = freeze._safe_path(output)
    inputs = [freeze._safe_path(path) for path in (candidate, original_app, config, context)]
    work_parent = freeze._safe_path(work_parent)
    if any(work_parent.is_relative_to(root) for root in (ROOT, *inputs)):
        raise ValueError("Work parent must be outside protected input trees.")
    if any(
        output.is_relative_to(root) or root.is_relative_to(output)
        for root in (ROOT, *inputs, work_parent)
    ):
        raise ValueError("Evidence must be separate from source and work trees.")
    if any(output.is_relative_to(root) for root in TEMP_ROOTS):
        raise ValueError("Evidence destination must be persistent, outside temporary roots.")
    _context(candidate, _load(context))
    if not original_app.is_dir() or not _entries(original_app):
        raise ValueError("Original App baseline is missing.")
    freeze._read(config)
    snapshots = [_snapshot(path) for path in inputs]
    output.mkdir(mode=0o700)
    baseline = output / "baseline"
    baseline.mkdir(mode=0o700)
    # Failed partial copies intentionally remain evidence; retry at a fresh destination.
    source_modes = {}
    for source, name in zip(
        inputs, ("candidate", "original-app", "config.json", "context.json"), strict=True
    ):
        source_modes[name] = (
            {
                path.relative_to(source).as_posix(): f"{stat.S_IMODE(path.stat().st_mode):04o}"
                for path in (source, *source.rglob("*"))
            }
            if source.is_dir()
            else {".": f"{stat.S_IMODE(source.stat().st_mode):04o}"}
        )
        _copy(source, baseline / name)
    for source, name, snapshot in zip(
        inputs, ("candidate", "original-app", "config.json", "context.json"), snapshots, strict=True
    ):
        if _snapshot(source) != snapshot or _snapshot(baseline / name) != snapshot:
            raise ValueError("Original source changed while copying the baseline.")
    _context(baseline / "candidate", _load(baseline / "context.json"))
    token = uuid.uuid4().hex
    work = work_parent / ("acceptance-work-" + token)
    record = {
        "format": "durable-acceptance/v1",
        "files": _entries(baseline),
        "work": str(work),
        "token": token,
        "source_modes": source_modes,
        "rollback": {"app": "original-app", "config": "config.json"},
    }
    _write(output / "baseline.json", freeze._json(record))
    verify(output)
    work.mkdir(mode=0o700)
    _write(work / ".acceptance-owner", token.encode())
    return record


def verify(output: Path) -> dict:
    """Reopen retained bytes without original sources or work directory."""
    output = freeze._safe_path(output)
    _permissions(output)
    expected = {"baseline", "baseline.json"}
    if (output / "run.json").exists():
        expected.update({"command.json", "run", "run.json"})
    if (output / "cleanup.json").exists():
        expected.add("cleanup.json")
    if {path.name for path in output.iterdir()} != expected:
        raise ValueError("Evidence contains an unsealed or unexpected stage.")
    baseline = _load(output / "baseline.json")
    if set(baseline) != {"format", "files", "work", "token", "rollback", "source_modes"} or (
        baseline["format"] != "durable-acceptance/v1"
        or baseline["rollback"] != {"app": "original-app", "config": "config.json"}
        or _entries(output / "baseline") != baseline["files"]
    ):
        raise ValueError("Baseline bytes or rollback references changed.")
    if (
        not isinstance(baseline["token"], str)
        or not re.fullmatch("[0-9a-f]{32}", baseline["token"])
        or not isinstance(baseline["work"], str)
        or not Path(baseline["work"]).is_absolute()
        or ".." in Path(baseline["work"]).parts
        or Path(baseline["work"]).name != "acceptance-work-" + baseline["token"]
        or Path(baseline["work"]).is_relative_to(output)
        or output.is_relative_to(Path(baseline["work"]))
    ):
        raise ValueError("Malformed work ownership binding.")
    _context(output / "baseline/candidate", _load(output / "baseline/context.json"))
    result = {
        "baseline_verified": True,
        "run_receipt_verified": False,
        "run_verified": False,
        "cleanup_verified": False,
    }
    if (output / "run.json").exists():
        receipt = _load(output / "run.json")
        requested = _load(output / "command.json")
        if (
            receipt
            != {
                "baseline_sha256": hashlib.sha256(
                    freeze._read(output / "baseline.json")
                ).hexdigest(),
                "observed_returncode": receipt.get("observed_returncode"),
                "timed_out": receipt.get("timed_out"),
                "descendants_detected": receipt.get("descendants_detected"),
                "process_group": receipt.get("process_group"),
                "files": _entries(output / "run"),
            }
            or type(receipt["observed_returncode"]) is not int
            or type(receipt["timed_out"]) is not bool
            or type(receipt["descendants_detected"]) is not bool
            or type(receipt["process_group"]) is not int
            or receipt["process_group"] <= 0
            or requested != _command(output, baseline)
        ):
            raise ValueError("Observed run receipt or version relation changed.")
        result["run_receipt_verified"] = True
        result["run_verified"] = (
            receipt["observed_returncode"] == 0
            and not receipt["timed_out"]
            and not receipt["descendants_detected"]
        )
    if (output / "cleanup.json").exists():
        if (
            not result["run_verified"]
            or _load(output / "cleanup.json")
            != {"token": baseline["token"], "observed_absent": True}
            or Path(baseline["work"]).exists()
            or Path(baseline["work"]).is_symlink()
        ):
            raise ValueError("Cleanup cannot be independently verified.")
        result["cleanup_verified"] = True
    return result


def _command(output: Path, baseline: dict) -> dict:
    context = _load(output / "baseline/context.json")
    loaded = context["loaded_sources"]
    if len(loaded) != 1 or not loaded[0]["path"].endswith(".py"):
        raise ValueError("Synthetic execution requires one unambiguous Python entrypoint.")
    entrypoint = output / "baseline/candidate/payload" / loaded[0]["path"]
    runner = (
        "import resource,runpy,sys; "
        "resource.setrlimit(resource.RLIMIT_FSIZE, (4194304,4194304)); "
        "runpy.run_path(sys.argv[1], run_name='__main__')"
    )
    return {
        "argv": [sys.executable, "-I", "-B", "-c", runner, str(entrypoint)],
        "cwd": baseline["work"],
        "phase": "requested-synthetic-child",
    }


def _owned_work(output: Path, baseline: dict) -> Path:
    work = freeze._safe_path(Path(baseline["work"]))
    if (
        work.name != "acceptance-work-" + baseline["token"]
        or work.is_relative_to(output)
        or output.is_relative_to(work)
        or freeze._read(work / ".acceptance-owner") != baseline["token"].encode()
    ):
        raise ValueError("Work ownership is missing or ambiguous.")
    return work


def run(output: Path, timeout: float = 30) -> dict:
    """Execute the retained synthetic Python entrypoint and retain raw observations."""
    output = freeze._safe_path(output)
    verify(output)
    baseline = _load(output / "baseline.json")
    work = _owned_work(output, baseline)
    command = _command(output, baseline)
    _write(output / "command.json", freeze._json(command))
    if not 0 < timeout <= 60:
        raise ValueError("Synthetic subprocess timeout must be bounded to one minute.")
    retained = output / "run"
    retained.mkdir(mode=0o700)
    _write(retained / "stdout.bin", b"")
    _write(retained / "stderr.bin", b"")
    with (
        (retained / "stdout.bin").open("ab") as stdout,
        (retained / "stderr.bin").open("ab") as stderr,
    ):
        observed = subprocess.Popen(
            command["argv"],
            cwd=work,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            env={"PATH": os.defpath, "TMPDIR": str(work)},
        )
        timed_out = False
        try:
            observed.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(observed.pid, signal.SIGKILL)
            observed.wait(timeout=5)
        descendants = _group_exists(observed.pid)
        if descendants:
            os.killpg(observed.pid, signal.SIGKILL)
    artifacts = retained / "artifacts"
    artifacts.mkdir(mode=0o700)
    for path in sorted(work.iterdir()):
        if path.name != ".acceptance-owner":
            _copy(path, artifacts / path.name)
    receipt = {
        "baseline_sha256": hashlib.sha256(freeze._read(output / "baseline.json")).hexdigest(),
        "observed_returncode": observed.returncode,
        "timed_out": timed_out,
        "descendants_detected": descendants,
        "process_group": observed.pid,
        "files": _entries(retained),
    }
    _write(output / "run.json", freeze._json(receipt))
    verify(output)
    return receipt


def cleanup(output: Path) -> dict:
    """Remove only the exact owned, exited work copy after verifying retained bytes."""
    result = verify(output)
    if result["cleanup_verified"]:
        return result
    receipt = _load(output / "run.json") if result["run_verified"] else {}
    if (
        not result["run_verified"]
        or receipt["observed_returncode"] != 0
        or receipt["timed_out"]
        or receipt["descendants_detected"]
        or _group_exists(receipt["process_group"])
    ):
        raise ValueError("Cleanup requires an observed successful process exit.")
    baseline = _load(output / "baseline.json")
    work = _owned_work(output, baseline)
    actual = [item for item in _entries(work) if item["path"] != ".acceptance-owner"]
    if actual != _entries(output / "run/artifacts"):
        raise ValueError("Work bytes changed after retention; cleanup stopped.")
    shutil.rmtree(work)
    _write(
        output / "cleanup.json", freeze._json({"token": baseline["token"], "observed_absent": True})
    )
    return verify(output)


def _group_exists(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("begin", "run", "verify", "cleanup"))
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--original-app", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--work-parent", type=Path)
    args = parser.parse_args()
    try:
        if args.operation == "begin":
            if any(
                item is None
                for item in (
                    args.candidate,
                    args.original_app,
                    args.config,
                    args.context,
                    args.work_parent,
                )
            ):
                parser.error(
                    "begin requires candidate, original-app, config, context and work-parent"
                )
            begin(
                args.candidate,
                args.original_app,
                args.config,
                args.context,
                args.evidence,
                args.work_parent,
            )
        elif args.operation == "run":
            receipt = run(args.evidence)
            if (
                receipt["observed_returncode"] != 0
                or receipt["timed_out"]
                or receipt["descendants_detected"]
            ):
                print(json.dumps({"verified": False}))
                return 1
        elif args.operation == "cleanup":
            cleanup(args.evidence)
        result = verify(args.evidence)
        print(json.dumps(result, sort_keys=True))
        if result["run_receipt_verified"] and not result["run_verified"]:
            return 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        # No raw exception text: OS errors can contain private paths.
        print(json.dumps({"verified": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
