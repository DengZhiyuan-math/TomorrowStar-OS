from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "career_evidence_graph.cli", *args],
        check=False,
        capture_output=True,
        text=True,
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
    fixture_path = tmp_path / "fixture.json"
    _write_json(fixture_path, _domain_fixture())

    result = _run("fixture", "validate", str(fixture_path))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "assessment_count": 1,
        "contribution_count": 1,
        "experience_count": 1,
        "fixture_hash": "sha256:PLACEHOLDER",
        "user_skill_count": 1,
        "valid": True,
    }


def test_domain_fixture_rejects_missing_assessment_contribution(tmp_path):
    fixture_path = tmp_path / "invalid-fixture.json"
    _write_json(fixture_path, _domain_fixture(contribution_id="contribution.missing"))

    result = _run("fixture", "validate", str(fixture_path))

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
