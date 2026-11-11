"""JSON materials and record persistence do not require the browser executor."""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_json_rendering_works_with_the_execution_module_unavailable():
    script = r"""
import importlib.abc, json, sys
from pathlib import Path
class NoExecutor(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "career_evidence_graph.application_worker":
            raise ImportError("The executor is unavailable to this pure material step")
sys.meta_path.insert(0, NoExecutor())
from career_evidence_graph.application_resume_content import assemble_content
from career_evidence_graph.application_resume_render import render_resume
sample = json.loads(Path("tests/fixtures/json_resume/single-experience.json").read_text())
rendered = render_resume(assemble_content(**sample))
assert rendered.tex.startswith("\\documentclass")
assert "career_evidence_graph.application_worker" not in sys.modules
"""
    env = dict(os.environ, PYTHONPATH=str(Path("src").absolute()))
    result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode()


def test_record_identity_keeps_historical_json_bytes_and_rejects_nonfinite_values():
    from career_evidence_graph.validation.hashing import record_digest

    assert (
        record_digest({"z": "café", "a": [1, True]})
        == hashlib.sha256('{"a": [1, true], "z": "café"}'.encode()).hexdigest()
    )
    with pytest.raises(ValueError):
        record_digest({"value": float("nan")})


def test_private_record_directory_excludes_the_checkout_and_symlinks(tmp_path):
    from career_evidence_graph.application_storage import private_root

    assert private_root(tmp_path / "records") == tmp_path / "records"
    with pytest.raises(ValueError):
        private_root(Path.cwd() / "private-records")
    link = tmp_path / "alias"
    link.symlink_to(tmp_path / "records", target_is_directory=True)
    with pytest.raises(ValueError):
        private_root(link)
