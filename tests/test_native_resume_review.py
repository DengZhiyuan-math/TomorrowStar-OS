"""The fixed native helper connects an existing review without a job workflow."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_application_prism import compiling_editor

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "macos/resume_review.py"


def run_helper(*args, env=None, script=HELPER):
    return subprocess.run(
        [sys.executable, "-I", "-B", str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


def test_unconfigured_helper_returns_one_safe_json_error_without_creating_state(tmp_path):
    config = tmp_path / "not configured.json"
    result = run_helper("--config", config)
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "code": "resume_review_not_configured",
        "message": "请先配置专用 LaTeX 简历审阅项目。",
    }
    assert len(result.stdout.splitlines()) == 1 and result.stderr == ""
    assert str(tmp_path) not in result.stdout
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("relocated", [False, True])
@pytest.mark.parametrize("use_default", [False, True])
def test_helper_opens_existing_synthetic_source_without_build_or_state_writes(
    tmp_path, monkeypatch, relocated, use_default
):
    project = tmp_path / "latex"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic standalone source")
    config = tmp_path / "resume-review.json"
    if use_default:
        home = tmp_path / "synthetic home"
        monkeypatch.setenv("HOME", str(home))
        config = home / "Library/Application Support/TomorrowStar/resume-review.json"
        config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    script = HELPER
    if relocated:
        resources = tmp_path / "App With Spaces/Contents/Resources"
        resources.mkdir(parents=True)
        shutil.copy2(HELPER, resources / "resume_review.py")
        shutil.copytree(
            ROOT / "src/career_evidence_graph",
            resources / "system/src/career_evidence_graph",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        script = resources / "resume_review.py"
    preserved = {path: path.read_bytes() for path in [config, project / "main.tex"]}
    with compiling_editor(project, monkeypatch) as requests:
        arguments = [] if use_default else ["--config", config]
        result = run_helper(*arguments, env=dict(os.environ), script=script)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "ready",
        "url": os.environ["TOMORROWSTAR_PRISM_URL"] + "/",
        "title": "LaTeX 简历编辑与预览",
    }
    assert len(result.stdout.splitlines()) == 1 and result.stderr == ""
    assert str(project) not in result.stdout and "Synthetic standalone source" not in result.stdout
    assert requests == [("GET", "/api/ping"), ("GET", "/api/tree")]
    assert all(path.read_bytes() == raw for path, raw in preserved.items())
    assert list(project.iterdir()) == [project / "main.tex"]


@pytest.mark.parametrize(
    "damage",
    [
        "symlink",
        "parent-link",
        "directory",
        "fifo",
        "oversized",
        "extra",
        "missing-field",
        "duplicate",
        "invalid-json",
    ],
)
def test_bad_config_fails_with_safe_json_without_contacting_any_service(tmp_path, damage):
    config = tmp_path / "secret-review.json"
    config.write_text(json.dumps({"project_root": "/private/secret-source", "main": "main.tex"}))
    if damage == "symlink":
        alias = tmp_path / "alias.json"
        alias.symlink_to(config)
        config = alias
    elif damage == "parent-link":
        parent = tmp_path / "directory"
        parent.mkdir()
        moved = parent / config.name
        config.rename(moved)
        alias = tmp_path / "parent-alias"
        alias.symlink_to(parent, target_is_directory=True)
        config = alias / config.name
    elif damage == "directory":
        config.unlink()
        config.mkdir()
    elif damage == "fifo":
        config.unlink()
        os.mkfifo(config)
    elif damage == "oversized":
        config.write_bytes(b"x" * 16_385)
    elif damage == "extra":
        config.write_text(
            '{"project_root":"/private/secret-source","main":"main.tex","token":"secret"}'
        )
    elif damage == "missing-field":
        config.write_text('{"project_root":"/private/secret-source"}')
    elif damage == "duplicate":
        config.write_text('{"project_root":"secret","project_root":"other","main":"main.tex"}')
    else:
        config.write_text("secret source body is not JSON")
    result = run_helper(
        "--config",
        config,
        env=dict(os.environ) | {"TOMORROWSTAR_PRISM_URL": "http://external.example.test:1"},
    )
    assert result.returncode == 2 and result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["status"] == "error" and payload["code"] == "resume_review_config_invalid"
    assert str(tmp_path) not in result.stdout and "secret" not in result.stdout


def test_invalid_arguments_are_not_echoed_and_never_create_private_default_state():
    result = run_helper("--not-supported", "/private/secret-token")
    assert result.returncode == 2 and result.stderr == ""
    assert json.loads(result.stdout)["code"] == "resume_review_request_invalid"
    assert "secret" not in result.stdout


def test_unavailable_prism_returns_no_private_locators_or_traceback(tmp_path):
    project = tmp_path / "secret source"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic private source body")
    config = tmp_path / "secret-config.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    result = run_helper(
        "--config", config, env=dict(os.environ) | {"TOMORROWSTAR_PRISM_URL": "http://127.0.0.1:1"}
    )
    assert result.returncode == 2 and result.stderr == ""
    assert json.loads(result.stdout)["code"] == "resume_review_unavailable"
    assert str(project) not in result.stdout and "private source body" not in result.stdout


def test_relocated_helper_does_not_fall_back_to_an_ambient_engine(tmp_path):
    resources = tmp_path / "Incomplete App/Contents/Resources"
    resources.mkdir(parents=True)
    shutil.copy2(HELPER, resources / "resume_review.py")
    project = tmp_path / "latex"
    project.mkdir()
    (project / "main.tex").write_text("Synthetic source")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"project_root": str(project), "main": "main.tex"}))
    # A site-level import must not replace missing bundled application code.
    (resources.parent / "src/career_evidence_graph").mkdir(parents=True)
    (resources.parent / "src/career_evidence_graph/__init__.py").write_text("")
    (resources.parent / "src/career_evidence_graph/application_prism.py").write_text(
        'class PrismClient:\n def open(self, binding): return "http://127.0.0.1:1234/"\n'
        "def source_snapshot(root, main): return {}\n"
    )
    result = run_helper("--config", config, script=resources / "resume_review.py")
    assert result.returncode == 2 and result.stderr == ""
    assert json.loads(result.stdout)["code"] == "resume_review_unavailable"
