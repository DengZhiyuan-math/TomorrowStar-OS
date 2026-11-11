from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_checkout_source_cli_inspects_snapshot_and_resumes_one_action_at_a_time(tmp_path: Path):
    workspace = tmp_path / "workspace"
    start = (
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--audit-id",
        "audit-cli",
    )
    started = run_cli(*start)
    assert started.returncode == 0, started.stderr
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / f"{audit_id}.json"
    assert snapshot_path.is_file()

    paused = run_cli("audit", "pause", "--workspace", str(workspace), "--audit-id", audit_id)
    assert paused.returncode == 0, paused.stderr
    resumed = run_cli("audit", "resume", "--workspace", str(workspace), "--audit-id", audit_id)
    assert resumed.returncode == 0, resumed.stderr
    inspected = run_cli("audit", "inspect", "--workspace", str(workspace), "--audit-id", audit_id)
    assert inspected.returncode == 0, inspected.stderr
    snapshot = json.loads(inspected.stdout)["snapshot"]
    assert snapshot["audit_id"] == audit_id
    assert snapshot["inspected_facts"]
    assert snapshot["questions"]
    assert snapshot["coverage"]


def test_audit_start_accepts_candidate_skill_context_as_unverified_reminder(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    links = tmp_path / "candidate-links.json"
    links.write_text(
        json.dumps(
            [
                {
                    "schema_version": "candidate-skill-link/v1",
                    "id": "candidate-skill-cli-testing",
                    "experience_candidate_id": "experience-candidate-cli",
                    "source_id": "source-cli-synthetic",
                    "capture_hash": "sha256:" + "a" * 64,
                    "source_locator": "resume.md#testing",
                    "candidate_text": "Testing",
                    "extraction_version": "synthetic-extractor/v1",
                }
            ]
        ),
        encoding="utf-8",
    )
    probe_plan = tmp_path / "probe-plan.json"
    probe_plan.write_text(
        json.dumps(
            {
                "schema_version": "audit-probe-plan/v1",
                "contribution_id": "contrib-stoa-authorization-boundary",
                "areas": [
                    {
                        "schema_version": "audit-probe-area/v1",
                        "area_id": "implementation",
                        "inspected_fact_ids": ["evid-stoa-build-week"],
                        "unverified_capability": "implementation boundary",
                        "demanding_prompt": "Which testing trade-off did you make?",
                        "intermediate_prompt": "Which test did you write?",
                        "simple_prompt": "Which test step did you complete?",
                        "immediately_higher_capability": "defending the test boundary",
                        "candidate_skill_link_ids": ["candidate-skill-cli-testing"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    started = run_cli(
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--experience-candidate-id",
        "experience-candidate-cli",
        "--candidate-skill-links",
        str(links),
        "--recorded-probe-plan",
        str(probe_plan),
    )

    assert started.returncode == 0, started.stderr
    snapshot = json.loads(started.stdout)["snapshot"]
    assert snapshot["schema_version"] == "audit-snapshot/v2"
    assert snapshot["questions"][0]["recall_reminder"] == (
        "Candidate skill reminder (unverified): Testing"
    )


def test_audit_start_rejects_non_array_candidate_skill_links_without_creating_an_audit(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    links = tmp_path / "candidate-links.json"
    links.write_text('{"PRIVATE_SOURCE_KEY": "PRIVATE_SOURCE_BODY"}', encoding="utf-8")

    started = run_cli(
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--experience-candidate-id",
        "experience-candidate-cli",
        "--candidate-skill-links",
        str(links),
    )

    assert started.returncode == 2
    assert json.loads(started.stderr) == {
        "valid": False,
        "error": "input_validation_error",
        "types": ["list_type"],
    }
    assert "PRIVATE_SOURCE" not in started.stdout + started.stderr
    assert not (workspace / "audits").exists()


def test_input_file_errors_do_not_expose_private_paths_or_bytes(tmp_path: Path) -> None:
    source = tmp_path / "PRIVATE_SOURCE_PATH.json"
    missing = run_cli("fixture", "validate", str(source))
    source.write_bytes(b"\xffPRIVATE_SOURCE_BODY")
    malformed = run_cli("fixture", "validate", str(source))

    for result in (missing, malformed):
        assert result.returncode == 2
        assert json.loads(result.stderr) == {"valid": False, "error": "input_read_error"}
        assert "PRIVATE_SOURCE" not in result.stdout + result.stderr


def test_invalid_action_and_corrupt_snapshot_return_stable_errors_without_writes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    started = run_cli(
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--audit-id",
        "audit-cli-invalid",
    )
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / f"{audit_id}.json"
    before = snapshot_path.read_bytes()

    invalid = run_cli("audit", "resume", "--workspace", str(workspace), "--audit-id", audit_id)
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)["error"] == "audit_workflow_error"
    assert snapshot_path.read_bytes() == before

    snapshot_path.write_text("{bad}", encoding="utf-8")
    corrupt = run_cli("audit", "pause", "--workspace", str(workspace), "--audit-id", audit_id)
    assert corrupt.returncode == 2
    assert json.loads(corrupt.stderr)["error"] == "audit_storage_error"
    assert snapshot_path.read_text(encoding="utf-8") == "{bad}"


def test_cli_skip_contribution_rejects_a_stale_question_target(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    started = run_cli(
        "audit",
        "start",
        "--workspace",
        str(workspace),
        "--fixture",
        str(FIXTURE),
        "--contribution-id",
        "contrib-stoa-authorization-boundary",
        "--audit-id",
        "audit-cli-stale-skip",
    )
    audit_id = json.loads(started.stdout)["audit_id"]
    snapshot_path = workspace / "audits" / f"{audit_id}.json"
    before = snapshot_path.read_bytes()

    rejected = run_cli(
        "audit",
        "skip-contribution",
        "--workspace",
        str(workspace),
        "--audit-id",
        audit_id,
        "--answer",
        "self rating: 6/10",
        "--question-id",
        "question-stale",
    )

    assert rejected.returncode == 2
    assert json.loads(rejected.stderr)["error"] == "audit_workflow_error"
    assert snapshot_path.read_bytes() == before
