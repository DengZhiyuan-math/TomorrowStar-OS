from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"
PYTEST_LAUNCHER = ROOT / "scripts" / "run_pytest.py"


def test_explicit_checkout_launcher_resolves_the_repository_src_package() -> None:
    """The project-local launcher selects this checkout without a global import hook."""
    cli = subprocess.run(
        [sys.executable, str(LAUNCHER), "implementation-path"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert cli.returncode == 0, cli.stderr
    assert (
        Path(json.loads(cli.stdout)["package_path"]).resolve()
        == (ROOT / "src" / "career_evidence_graph" / "cli.py").resolve()
    )


def test_explicit_checkout_pytest_launcher_imports_the_source_package() -> None:
    """The locked test gate must select checkout code without ``PYTHONPATH``."""
    completed = subprocess.run(
        [
            sys.executable,
            str(PYTEST_LAUNCHER),
            "-q",
            "tests/test_domain_models.py",
            "-k",
            "models_reject_unknown_fields",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_built_wheel_is_self_contained_outside_the_checkout(tmp_path: Path) -> None:
    """A fresh-cache offline build must install without a checkout import hook."""
    distribution_dir = tmp_path / "dist"
    virtualenv = tmp_path / "wheel-venv"
    external_cwd = tmp_path / "external"
    fresh_cache = tmp_path / "fresh-uv-cache"
    distribution_dir.mkdir()
    external_cwd.mkdir()
    fresh_cache.mkdir()
    offline_environment = os.environ | {"UV_CACHE_DIR": str(fresh_cache), "UV_OFFLINE": "1"}

    built = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "--out-dir", str(distribution_dir)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=offline_environment,
    )
    assert built.returncode == 0, built.stderr
    wheel = next(distribution_dir.glob("career_evidence_graph-*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        wheel_members = archive.namelist()
        assert "sitecustomize.py" not in wheel_members
        assert not any(name.endswith(".pth") for name in wheel_members)
        assert str(ROOT.resolve()).encode("utf-8") not in b"".join(
            archive.read(name) for name in wheel_members
        )
        record_name = next(name for name in wheel_members if name.endswith(".dist-info/RECORD"))
        record_rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
        record = {row[0]: row[1:] for row in record_rows}
        for name in wheel_members:
            if name == record_name:
                assert record[name] == ["", ""]
                continue
            digest = base64.urlsafe_b64encode(hashlib.sha256(archive.read(name)).digest())
            expected_hash = f"sha256={digest.rstrip(b'=').decode('ascii')}"
            assert record[name] == [expected_hash, str(len(archive.read(name)))]
    package_modules = [
        name
        for name in wheel_members
        if name.startswith("career_evidence_graph/") and name.endswith(".py")
    ]
    assert package_modules
    assert all(name in record and record[name][0] for name in package_modules)

    created = subprocess.run(
        ["uv", "venv", "--offline", "--python", sys.executable, str(virtualenv)],
        cwd=external_cwd,
        check=False,
        capture_output=True,
        text=True,
        env=offline_environment,
    )
    assert created.returncode == 0, created.stderr
    wheel_python = virtualenv / "bin" / "python"
    installed = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--python",
            str(wheel_python),
            "--no-deps",
            str(wheel),
        ],
        cwd=external_cwd,
        check=False,
        capture_output=True,
        text=True,
        env=offline_environment,
    )
    assert installed.returncode == 0, installed.stderr

    imported = subprocess.run(
        [
            str(wheel_python),
            "-c",
            (
                "import json; from importlib.metadata import distribution; "
                "import career_evidence_graph; "
                "dist = distribution('career-evidence-graph'); "
                "print(json.dumps({'package_path': career_evidence_graph.__file__, "
                "'cli_path': str(dist.locate_file('career_evidence_graph/cli.py')), "
                "'entry_points': [entry.value for entry in dist.entry_points "
                "if entry.group == 'console_scripts' and entry.name == 'career-evidence']}))"
            ),
        ],
        cwd=external_cwd,
        check=False,
        capture_output=True,
        text=True,
    )

    assert imported.returncode == 0, imported.stderr
    installed_paths = json.loads(imported.stdout)
    assert virtualenv.resolve() in Path(installed_paths["package_path"]).resolve().parents
    assert virtualenv.resolve() in Path(installed_paths["cli_path"]).resolve().parents
    assert installed_paths["entry_points"] == ["career_evidence_graph.cli:main"]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_source(
    *args: str, pythonpath_prefix: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the package CLI from the source tree, not a stale wheel install."""
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    source_paths = [source_root]
    if pythonpath_prefix is not None:
        source_paths.insert(0, str(pythonpath_prefix))
    environment = os.environ | {"PYTHONPATH": os.pathsep.join(source_paths)}
    return subprocess.run(
        [sys.executable, "-m", "career_evidence_graph.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_offline_cli_crosses_real_storage_and_replay_boundaries(tmp_path, charter_path):
    inputs = tmp_path / "inputs"
    workspace = tmp_path / "workspace"
    inputs.mkdir()
    raw_response = inputs / "raw.json"
    proposal = inputs / "proposal.json"
    expected = inputs / "expected.json"
    lineage = inputs / "lineage.json"
    result = {
        "trace_kind": "synthetic-plumbing-only",
        "functional_chain_connected": True,
    }
    _write_json(raw_response, {"provider_called": False, "result": result})
    _write_json(proposal, {"proposed": result})
    _write_json(expected, result)
    _write_json(
        lineage,
        {
            "fixture": {"kind": "synthetic-plumbing-only"},
            "artifacts": [],
            "prompt": {"version": "none"},
            "model": {"provider": "none"},
            "configuration": {"network": False},
            "policy": {"charter": "1.0.0"},
            "reviewer": {"kind": "test-confirmed"},
        },
    )

    validated = _run("validate-charter", str(charter_path))
    assert validated.returncode == 0, validated.stderr

    created = _run(
        "run",
        "create",
        "--workspace",
        str(workspace),
        "--charter",
        str(charter_path),
        "--run-id",
        "tracer-001",
        "--raw-response",
        str(raw_response),
        "--proposal",
        str(proposal),
        "--confirmed-result",
        str(expected),
        "--lineage",
        str(lineage),
    )
    assert created.returncode == 0, created.stderr
    assert (workspace / "formal-runs" / "tracer-001" / "manifest.json").is_file()

    verified = _run("run", "verify", "--workspace", str(workspace), "--run-id", "tracer-001")
    assert verified.returncode == 0, verified.stderr

    replayed = _run("replay", "--workspace", str(workspace), "--run-id", "tracer-001")
    assert replayed.returncode == 0, replayed.stderr
    assert json.loads(replayed.stdout)["matched"] is True


def test_duplicate_run_is_rejected_without_overwrite(tmp_path, charter_path):
    value_path = tmp_path / "value.json"
    _write_json(value_path, {"result": {"ok": True}})
    expected_path = tmp_path / "expected.json"
    _write_json(expected_path, {"ok": True})
    lineage_path = tmp_path / "lineage.json"
    _write_json(
        lineage_path,
        {
            "fixture": {},
            "artifacts": [],
            "prompt": {},
            "model": {},
            "configuration": {},
            "policy": {},
            "reviewer": {},
        },
    )
    base = (
        "run",
        "create",
        "--workspace",
        str(tmp_path / "workspace"),
        "--charter",
        str(charter_path),
        "--run-id",
        "same-run",
        "--raw-response",
        str(value_path),
        "--proposal",
        str(expected_path),
        "--confirmed-result",
        str(expected_path),
        "--lineage",
        str(lineage_path),
    )
    assert _run(*base).returncode == 0
    manifest_path = tmp_path / "workspace/formal-runs/same-run/manifest.json"
    original = manifest_path.read_bytes()

    duplicate = _run(*base)

    assert duplicate.returncode == 2
    assert manifest_path.read_bytes() == original


def test_cli_verifies_machine_and_human_provenance_registry():
    verified = _run(
        "provenance",
        "verify",
        "validation/provenance/registry.json",
        "--readme",
        "references/README.md",
        "--project-root",
        ".",
    )

    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout) == {"record_count": 4, "valid": True}


def _domain_fixture(*, contribution_id: str = "contribution.delivery") -> dict[str, object]:
    """Return a synthetic, non-calibrated record for the Phase 2 CLI tracer."""
    return {
        "schema_version": "career-evidence-fixture/v1",
        "fixture_notice": "Synthetic contract exercise; not calibrated mastery.",
        "experiences": [
            {
                "id": "experience.synthetic",
                "experience_type": "project",
                "title": "Synthetic validation tracer",
                "contribution_ids": ["contribution.delivery"],
            }
        ],
        "contributions": [
            {
                "id": "contribution.delivery",
                "experience_id": "experience.synthetic",
                "summary": "A synthetic auditable outcome.",
                "claim_ids": ["claim.delivery"],
            }
        ],
        "claims": [
            {
                "id": "claim.delivery",
                "contribution_id": "contribution.delivery",
                "statement": "A synthetic claim with explicit limits.",
                "responsibility": "user",
                "assistance": "none",
                "confirmation_status": "confirmed",
                "completion_status": "delivered",
                "limitations": ["Synthetic fixture only."],
            }
        ],
        "evidence": [
            {
                "id": "evidence.synthetic",
                "kind": "acceptance_record",
                "proof_limit": "recorded_delivery",
                "repository": "synthetic/repository",
                "pinned_commit": "a" * 40,
                "tracked_path": "docs/acceptance.md",
                "section_locator": "# synthetic-result",
                "content_hash": "sha256:" + "b" * 64,
            }
        ],
        "claim_evidence_links": [
            {
                "claim_id": "claim.delivery",
                "evidence_id": "evidence.synthetic",
                "section_locator": "# synthetic-result",
            }
        ],
        "skills": [{"id": "skill.validation", "name": "Validation"}],
        "assessments": [
            {
                "id": "assessment.validation",
                "skill_id": "skill.validation",
                "contribution_id": contribution_id,
                "lineage": {"source_kind": "contribution", "contribution_id": contribution_id},
                "demonstrated_mastery": 0,
                "skill_centrality": 100,
                "evidence_confidence": 37,
                "context": "Synthetic contract fixture.",
                "duration": {"state": "not_verified"},
                "basis_claim_ids": ["claim.delivery"],
                "assessment_status": "partial",
            }
        ],
        "user_skill_views": [
            {
                "skill_id": "skill.validation",
                "assessment_ids": ["assessment.validation"],
                "fixture_notice": "Non-calibrated test view.",
            }
        ],
    }


def test_domain_fixture_validate_tracer_is_offline_and_deterministic(tmp_path):
    fixture_path = Path(__file__).parent / "fixtures" / "domain_fixture.json"

    result = _run_source("fixture", "validate", str(fixture_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["experience_count"] == 1
    assert payload["contribution_count"] == 1
    assert payload["assessment_count"] == 1
    assert payload["user_skill_count"] == 1
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", payload["fixture_hash"])


def test_domain_fixture_rejects_missing_assessment_contribution(tmp_path):
    fixture_path = tmp_path / "invalid-fixture.json"
    _write_json(fixture_path, _domain_fixture(contribution_id="contribution.missing"))

    result = _run_source("fixture", "validate", str(fixture_path))

    assert result.returncode == 2
    assert json.loads(result.stderr) == {
        "valid": False,
        "violations": [
            {
                "code": "assessment.contribution_missing",
                "path": "assessments.assessment.validation.contribution_id",
            }
        ],
    }


def test_domain_fixture_tracer_cannot_reach_network_subprocess_or_live_adapter(tmp_path):
    fixture_path = tmp_path / "fixture.json"
    _write_json(fixture_path, _domain_fixture())
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()
    (guard_dir / "sitecustomize.py").write_text(
        """
import importlib.abc
import socket
import subprocess
import sys

def blocked(*args, **kwargs):
    raise AssertionError('offline tracer reached a forbidden side effect')

class BlockCodexAdapter(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'career_evidence_graph.codex_cli':
            raise AssertionError('offline tracer imported the Codex adapter')
        return None

socket.create_connection = blocked
subprocess.run = blocked
sys.meta_path.insert(0, BlockCodexAdapter())
""".strip(),
        encoding="utf-8",
    )

    result = _run_source("fixture", "validate", str(fixture_path), pythonpath_prefix=guard_dir)

    assert result.returncode == 0, result.stderr
