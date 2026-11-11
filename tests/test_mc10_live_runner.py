"""MC-10's live runner is checked offline; no real app-server is started here."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from career_evidence_graph.application_codex_assist import PROTOCOL_VERSION


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/run_mc10_live.py"
    spec = importlib.util.spec_from_file_location("run_mc10_live", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_live_gates_refuses_before_any_process_or_evidence(runner, tmp_path):
    calls = []
    with pytest.raises(ValueError, match="TS_CUA_NATIVE_TEST"):
        runner.run("C0", environment={}, repo=tmp_path, execute=lambda *a, **k: calls.append(a))
    assert calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def configured(tmp_path, runner, monkeypatch):
    repo = tmp_path / "checkout"
    (repo / "src").mkdir(parents=True)
    (repo / "src/example.py").write_text("synthetic source\n")
    cli, driver, home = tmp_path / "codex", tmp_path / "driver", tmp_path / "isolated-home"
    cli.write_bytes(b"synthetic-cli")
    driver.write_bytes(b"synthetic-driver")
    cli.chmod(0o700)
    driver.chmod(0o700)
    home.mkdir()
    external_temp = tmp_path / "external-temp"
    external_temp.mkdir()
    monkeypatch.setattr(runner.tempfile, "tempdir", str(external_temp))
    environment = {
        "TS_CUA_NATIVE_TEST": "1",
        "CAREER_EVIDENCE_ENABLE_LIVE_MODEL": "1",
        "TOMORROWSTAR_CODEX_EXECUTABLE": str(cli),
        "TS_CUA_DRIVER_BINARY": str(driver),
        "TS_MC10_CODEX_HOME": str(home),
        "TS_MC10_EVIDENCE_DIR": str(tmp_path / "evidence"),
    }
    calls = []

    def execute(argv, **kwargs):
        calls.append(argv)
        assert argv == [str(cli), "--version"], "check-only must not dispatch pytest or app-server"
        return subprocess.CompletedProcess(argv, 0, stdout="codex-cli " + PROTOCOL_VERSION)

    return SimpleNamespace(
        repo=repo, cli=cli, driver=driver, home=home, env=environment, calls=calls, execute=execute
    )


def test_check_only_records_identity_without_consuming_a_case(runner, configured):
    ns = configured
    result = runner.run("C0", check_only=True, environment=ns.env, repo=ns.repo, execute=ns.execute)
    assert result["status"] == "ready"
    assert result["identity"]["codex_version"] == "codex-cli " + PROTOCOL_VERSION
    assert set(result["source"]) == {"src/example.py"}
    assert len(result["identity"]["source_sha256"]) == 64
    assert len(ns.calls) == 1
    assert not Path(ns.env["TS_MC10_EVIDENCE_DIR"]).exists()


def live_peer(ns, runner, *, case="C0", skipped=False, change_source=False):
    """Stand in for the process boundary, writing a normal one-case pytest result."""
    version = ns.execute

    def execute(argv, **kwargs):
        if argv[-1] == "--version":
            return version(argv, **kwargs)
        ns.calls.append(argv)
        assert argv.count(runner.CASES[case]) == 1
        assert "-m" in argv and argv[argv.index("-m") + 1] == "live_model and worker_browser"
        assert "timeout" not in kwargs
        assert "PYTEST_ADDOPTS" not in kwargs["env"]
        temp = Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--basetemp=")))
        assert not temp.is_relative_to(ns.repo)
        junit = Path(next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--junitxml=")))
        name = runner.CASES[case].split("::")[1]
        status = '<skipped message="precondition lost"/>' if skipped else ""
        junit.write_text(
            "<testsuites><testsuite><testcase "
            'classname="tests.test_worker_native_live_model_browser" '
            f'name="{name}">{status}</testcase></testsuite></testsuites>'
        )
        evidence = Path(ns.env["TS_MC10_EVIDENCE_DIR"]) / case
        evidence.mkdir()
        (evidence / "case.json").write_text(json.dumps({"case": case}))
        (evidence / "outbound.jsonl").write_text("")
        (evidence / "inbound.jsonl").write_text("")
        (evidence / "PASSED").write_text("{}")
        kwargs["stdout"].write("synthetic pytest log\n")
        if change_source:
            (ns.repo / "src/example.py").write_text("changed during run\n")
        return subprocess.CompletedProcess(argv, 0)

    return execute


def test_one_case_archives_junit_and_log_then_refuses_an_accidental_repeat(runner, configured):
    ns = configured
    ns.env["PYTEST_ADDOPTS"] = "--unintended-extra-test"
    result = runner.run("C0", environment=ns.env, repo=ns.repo, execute=live_peer(ns, runner))
    assert result["status"] == "passed"
    evidence = Path(ns.env["TS_MC10_EVIDENCE_DIR"]) / "C0"
    assert (evidence / "pytest.log").read_text() == "synthetic pytest log\n"
    assert (evidence / "junit.xml").is_file()
    assert json.loads((evidence / "result.json").read_text())["status"] == "passed"
    assert json.loads((evidence / "source-frozen.json").read_text()) == result["source"]
    assert len(ns.calls) == 2  # one --version and exactly one pytest process
    with pytest.raises(ValueError, match="already"):
        runner.run("C0", environment=ns.env, repo=ns.repo, execute=live_peer(ns, runner))
    assert len([argv for argv in ns.calls if "--version" not in argv]) == 1


@pytest.mark.parametrize("failure", ["skip", "source drift"])
def test_skips_and_source_drift_cannot_publish_a_passed_c0(runner, configured, failure):
    ns = configured
    result = runner.run(
        "C0",
        environment=ns.env,
        repo=ns.repo,
        execute=live_peer(
            ns, runner, skipped=failure == "skip", change_source=failure == "source drift"
        ),
    )
    assert result["status"] == "failed"
    evidence = Path(ns.env["TS_MC10_EVIDENCE_DIR"]) / "C0"
    assert (evidence / "junit.xml").is_file()
    assert not (evidence / "PASSED").exists()


@pytest.mark.parametrize("changed", ["missing", "source", "driver", "codex", "home"])
def test_later_cases_require_a_passed_c0_for_the_same_inputs(runner, configured, changed):
    ns = configured
    if changed != "missing":
        runner.run("C0", environment=ns.env, repo=ns.repo, execute=live_peer(ns, runner))
        if changed == "source":
            (ns.repo / "src/example.py").write_text("successor source\n")
        elif changed in {"driver", "codex"}:
            Path(
                ns.env[
                    "TS_CUA_DRIVER_BINARY"
                    if changed == "driver"
                    else "TOMORROWSTAR_CODEX_EXECUTABLE"
                ]
            ).write_bytes(b"successor binary")
        else:
            successor = ns.home.parent / "successor-home"
            successor.mkdir()
            ns.env["TS_MC10_CODEX_HOME"] = str(successor)
    with pytest.raises(ValueError, match="passed C0|identity"):
        runner.run("C1", check_only=True, environment=ns.env, repo=ns.repo, execute=ns.execute)
    assert not (Path(ns.env["TS_MC10_EVIDENCE_DIR"]) / "C1").exists()


def test_later_case_runs_once_after_the_matching_c0(runner, configured):
    ns = configured
    runner.run("C0", environment=ns.env, repo=ns.repo, execute=live_peer(ns, runner))
    result = runner.run(
        "C1", environment=ns.env, repo=ns.repo, execute=live_peer(ns, runner, case="C1")
    )
    assert result["status"] == "passed"
    assert [argv[-1] for argv in ns.calls if "--version" not in argv] == [
        runner.CASES["C0"],
        runner.CASES["C1"],
    ]


@pytest.mark.parametrize("version", ["codex-cli 0.1", "codex-cli 0.166.0-alpha.4", "unknown"])
def test_cli_below_the_protocol_floor_refuses_before_claiming_any_case(runner, configured, version):
    ns = configured

    def old_version(argv, **kwargs):
        assert argv == [str(ns.cli), "--version"]
        return subprocess.CompletedProcess(argv, 0, stdout=version)

    with pytest.raises(ValueError, match="protocol minimum"):
        runner.run("C0", environment=ns.env, repo=ns.repo, execute=old_version)
    assert not Path(ns.env["TS_MC10_EVIDENCE_DIR"]).exists()


def test_lost_binary_after_a_case_keeps_a_failed_result_and_prevents_replay(runner, configured):
    ns = configured
    peer = live_peer(ns, runner)

    def execute(argv, **kwargs):
        completed = peer(argv, **kwargs)
        if "--version" not in argv:
            ns.driver.unlink()
        return completed

    result = runner.run("C0", environment=ns.env, repo=ns.repo, execute=execute)
    assert result["status"] == "failed"
    assert result["postflight_error"]
    evidence = Path(ns.env["TS_MC10_EVIDENCE_DIR"]) / "C0"
    assert (evidence / "result.json").is_file()
    assert (evidence / "junit.xml").is_file()
    assert not (evidence / "PASSED").exists()


@pytest.mark.parametrize("location", ["checkout", "ancestor"])
def test_unsafe_temp_base_refuses_before_dispatch_or_case_reservation(
    runner, configured, monkeypatch, location
):
    ns = configured
    temp_base = ns.repo if location == "checkout" else ns.repo.parent
    monkeypatch.setattr(runner.tempfile, "tempdir", str(temp_base))
    with pytest.raises(ValueError, match="temporary workspace"):
        runner.run("C0", environment=ns.env, repo=ns.repo, execute=ns.execute)
    assert not Path(ns.env["TS_MC10_EVIDENCE_DIR"]).exists()
    assert all(argv[-1] == "--version" for argv in ns.calls)
