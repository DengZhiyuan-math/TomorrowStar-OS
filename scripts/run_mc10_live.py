"""Run exactly one authorized MC-10 case, or check its prerequisites without a turn."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from codex_live_guards import assert_isolated_codex_home, codex_home_names  # noqa: E402

from career_evidence_graph.application_codex_assist import PROTOCOL_VERSION  # noqa: E402

LIVE_FILE = "tests/test_worker_native_live_model_browser.py"
CASES = {
    "C0": LIVE_FILE + "::test_c0_handshake_effective_config_and_four_tool_catalog_without_turn[C0]",
    "C1": LIVE_FILE + "::test_c1_adversarial_page_has_only_recorded_native_effects[C1]",
    "C2": LIVE_FILE
    + "::test_c2_covered_combobox_on_the_original_page_from_structured_information[C2]",
    "C3": LIVE_FILE + "::test_c3_pause_interrupts_the_active_model_turn[C3]",
    "C4": LIVE_FILE + "::test_c4_pause_drains_the_in_flight_native_page_action[C4]",
    "C5": LIVE_FILE + "::test_c5_killed_app_server_is_unknown_and_refuses_the_next_dispatch[C5]",
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def junit_passed(path, node):
    if not path.is_file():
        return False
    report = ET.parse(path).getroot()
    cases = list(report.iter("testcase"))
    return (
        len(cases) == 1
        and cases[0].get("name") == node.split("::", 1)[1]
        and cases[0].get("classname", "").split(".")[-1] == Path(LIVE_FILE).stem
        and not any(list(report.iter(kind)) for kind in ("failure", "error", "skipped"))
    )


def source_manifest(repo):
    """Hash checkout inputs; runtime caches and local evidence are not source."""
    files = set()
    for directory in ("src", "tests", "macos", "scripts", "assets"):
        files.update(
            path
            for path in (repo / directory).rglob("*")
            if path.is_file()
            and not {"__pycache__", ".pytest_cache", ".ruff_cache"}.intersection(path.parts)
        )
    files.update(
        repo / name
        for name in (".python-version", "pyproject.toml", "uv.lock", "_career_evidence_build.py")
        if (repo / name).is_file()
    )
    return {
        path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }


def run(case, *, check_only=False, environment=None, repo=ROOT, execute=None):
    environment = dict(os.environ if environment is None else environment)
    execute = subprocess.run if execute is None else execute
    repo = Path(repo).resolve()
    if case not in CASES:
        raise ValueError("Select exactly one case C0-C5")
    for key in ("TS_CUA_NATIVE_TEST", "CAREER_EVIDENCE_ENABLE_LIVE_MODEL"):
        if environment.get(key) != "1":
            raise ValueError(f"{key}=1 is required")
    paths = {}
    for key in (
        "TOMORROWSTAR_CODEX_EXECUTABLE",
        "TS_CUA_DRIVER_BINARY",
        "TS_MC10_CODEX_HOME",
        "TS_MC10_EVIDENCE_DIR",
    ):
        value = environment.get(key)
        if not value or not Path(value).is_absolute():
            raise ValueError(f"{key} must be an explicit absolute path")
        paths[key] = Path(value)
    cli, driver = paths["TOMORROWSTAR_CODEX_EXECUTABLE"], paths["TS_CUA_DRIVER_BINARY"]
    if any(not p.is_file() or p.is_symlink() or not os.access(p, os.X_OK) for p in (cli, driver)):
        raise ValueError("Codex and native driver must be executable regular files")
    home = assert_isolated_codex_home(paths["TS_MC10_CODEX_HOME"])
    version = execute(
        [str(cli), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"},
        check=False,
    )
    if version.returncode or version.stdout.strip() != "codex-cli " + PROTOCOL_VERSION:
        raise ValueError("Codex version does not match the accepted protocol pin")
    source = source_manifest(repo)
    identity = {
        "source_sha256": hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest(),
        "codex_version": version.stdout.strip(),
        "codex_sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(driver.read_bytes()).hexdigest(),
        "codex_home": str(home),
    }
    root = paths["TS_MC10_EVIDENCE_DIR"]
    if case != "C0":
        try:
            c0 = json.loads((root / "C0/result.json").read_text())
        except (OSError, ValueError) as exception:
            raise ValueError("C1-C5 require a passed C0 from this runner") from exception
        if (
            not (root / "C0/PASSED").is_file()
            or not isinstance(c0, dict)
            or c0.get("status") != "passed"
        ):
            raise ValueError("C1-C5 require a passed C0 from this runner")
        if c0.get("identity") != identity:
            raise ValueError("C0 identity differs from the current source, CLI, driver or home")
    result = {
        "status": "ready",
        "case": case,
        "identity": identity,
        "source": source,
        "codex_home_names_before": codex_home_names(home),
    }
    stage, evidence = root / (".runner-" + case), root / case
    if stage.exists() or evidence.exists():
        raise ValueError(f"{case} already has evidence; refusing a repeat")
    runtime_base = Path(tempfile.gettempdir()).resolve()
    if runtime_base.is_relative_to(repo) or repo.is_relative_to(runtime_base):
        raise ValueError("MC-10 temporary workspace must be outside the checkout and its ancestors")
    if check_only:
        return result
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage.mkdir(mode=0o700)  # exclusive reservation; a partial run remains reserved
    write_json(stage / "source-frozen.json", source)
    runtime = tempfile.mkdtemp(prefix=f"tomorrowstar-mc10-{case.lower()}-", dir=runtime_base)
    environment.pop("PYTEST_ADDOPTS", None)
    command = [
        sys.executable,
        "-B",
        str(repo / "scripts/run_pytest.py"),
        "-q",
        "-rs",
        "-m",
        "live_model and worker_browser",
        "--junitxml=" + str(stage / "junit.xml"),
        "--basetemp=" + runtime,
        CASES[case],
    ]
    result.update(command=command, basetemp=runtime, started_at=time.time())
    error = None
    code = None
    try:
        with (stage / "pytest.log").open("w") as log:
            code = execute(
                command,
                cwd=repo,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
    except BaseException as exception:
        error = f"{type(exception).__name__}: {exception}"
    after, home_after, binaries_unchanged, postflight_error = None, None, False, None
    try:
        after = source_manifest(repo)
        binaries_unchanged = (
            hashlib.sha256(cli.read_bytes()).hexdigest() == identity["codex_sha256"]
            and hashlib.sha256(driver.read_bytes()).hexdigest() == identity["driver_sha256"]
        )
        assert_isolated_codex_home(home)
        home_after = codex_home_names(home)
    except (OSError, AssertionError) as exception:
        postflight_error = str(exception)
    result.update(
        finished_at=time.time(),
        returncode=code,
        error=error,
        source_unchanged=after == source,
        binaries_unchanged=binaries_unchanged,
        codex_home_names_after=home_after,
        postflight_error=postflight_error,
    )
    write_json(stage / "source-after.json", after)
    try:
        recorded = json.loads((evidence / "case.json").read_text())
        passed = (
            code == 0
            and error is None
            and postflight_error is None
            and result["source_unchanged"]
            and result["binaries_unchanged"]
            and isinstance(recorded, dict)
            and recorded.get("case") == case
            and (evidence / "outbound.jsonl").is_file()
            and (evidence / "inbound.jsonl").is_file()
            and junit_passed(stage / "junit.xml", CASES[case])
            and (case != "C0" or (evidence / "PASSED").is_file())
        )
    except (OSError, ValueError, ET.ParseError) as exception:
        passed = False
        result["evidence_error"] = str(exception)
    result["status"] = "passed" if passed else "failed"
    if case == "C0" and not passed:
        (evidence / "PASSED").unlink(missing_ok=True)
    write_json(stage / "result.json", result)
    evidence.mkdir(exist_ok=True, mode=0o700)
    for name in (
        "pytest.log",
        "junit.xml",
        "result.json",
        "source-frozen.json",
        "source-after.json",
    ):
        if (stage / name).is_file():
            shutil.copyfile(stage / name, evidence / name)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check paths, version and frozen-input identity; start no app-server or browser",
    )
    options = parser.parse_args(argv)
    try:
        result = run(options.case, check_only=options.check_only)
    except (OSError, ValueError, AssertionError, subprocess.TimeoutExpired) as exception:
        print(f"MC-10 refused: {exception}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {key: result[key] for key in ("case", "status", "identity")}
            | {"source_files": len(result["source"])},
            indent=2,
        )
    )
    return 0 if result["status"] in {"ready", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
