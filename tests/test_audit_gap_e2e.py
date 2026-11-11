from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_career_evidence.py"
FIXTURE = ROOT / "validation/fixtures/stoa/v1/known-good.json"
MANIFEST = FIXTURE.with_name("source-manifest.json")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _probe_plan(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "audit-probe-plan/v1",
                "contribution_id": "contrib-stoa-authorization-boundary",
                "areas": [
                    {
                        "schema_version": "audit-probe-area/v1",
                        "area_id": "implementation",
                        "inspected_fact_ids": ["evid-stoa-backend-audit"],
                        "unverified_capability": "authorization-boundary implementation",
                        "demanding_prompt": (
                            "How did you defend the authorization boundary under failure?"
                        ),
                        "intermediate_prompt": (
                            "Which authorization boundary did you implement and check?"
                        ),
                        "simple_prompt": (
                            "Which authorization implementation step did you complete?"
                        ),
                        "immediately_higher_capability": (
                            "independently defending authorization failures"
                        ),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _decisions(path: Path, question_id: str, answer: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "schema_version": "audit-boundary-decision/v1",
                        "question_id": question_id,
                        "answer": answer,
                        "outcome": "established",
                        "rationale": "Recorded offline decision establishes the boundary.",
                        "strongest_capability": (
                            "implementing and verifying the authorization boundary"
                        ),
                        "next_higher_not_established": (
                            "independently defending authorization failures"
                        ),
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _start(workspace: Path, audit_id: str, plan: Path) -> dict[str, object]:
    return _json(
        _run(
            "audit",
            "start",
            "--workspace",
            str(workspace),
            "--fixture",
            str(FIXTURE),
            "--manifest",
            str(MANIFEST),
            "--contribution-id",
            "contrib-stoa-authorization-boundary",
            "--audit-id",
            audit_id,
            "--recorded-probe-plan",
            str(plan),
        )
    )


def _action(workspace: Path, audit_id: str, action: str, *args: str) -> dict[str, object]:
    return _json(
        _run("audit", action, "--workspace", str(workspace), "--audit-id", audit_id, *args)
    )


def test_offline_checkout_source_journeys_cover_aud_requirements(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    plan = _probe_plan(tmp_path / "probe-plan.json")
    inspection = _json(
        _run(
            "audit",
            "inspect",
            "--fixture",
            str(FIXTURE),
            "--manifest",
            str(MANIFEST),
            "--contribution-id",
            "contrib-stoa-authorization-boundary",
        )
    )
    assert inspection["facts"] and inspection["limitations"]

    started = _start(workspace, "audit-e2e", plan)
    audit_id = str(started["audit_id"])
    question_id = str(started["question"]["id"])
    answer = "I chose the authorization boundary and verified its failure behavior."
    decisions = _decisions(tmp_path / "decisions.json", question_id, answer)

    _action(workspace, audit_id, "pause")
    resumed = _action(workspace, audit_id, "resume")
    assert resumed["snapshot"]["questions"][-1]["id"] == question_id
    established = _action(
        workspace,
        audit_id,
        "answer",
        "--answer",
        answer,
        "--recorded-decisions",
        str(decisions),
    )
    assert established["snapshot"]["questions"][-1]["turn"] == "ownership"
    ownership = _action(
        workspace, audit_id, "answer", "--answer", "I owned the final design decision."
    )
    assert ownership["snapshot"]["questions"][-1]["turn"] == "assistance"
    reviewing = _action(workspace, audit_id, "answer", "--answer", "No outside assistance.")
    conclusion = reviewing["snapshot"]["conclusion"]
    assert conclusion["entries"][0]["verification"] == "audit-verified"
    original = conclusion["original_proposal"]

    edited = _action(
        workspace,
        audit_id,
        "review-entry",
        "--entry-id",
        "entry-implementation",
        "--decision",
        "edit",
        "--correction",
        "Clarified independently owned boundary decision.",
        "--reason",
        "Make the boundary precise.",
        "--reviewer",
        "reviewer",
    )
    assert edited["snapshot"]["conclusion"]["original_proposal"] == original
    confirmed_entry = _action(
        workspace,
        audit_id,
        "review-entry",
        "--entry-id",
        "entry-implementation",
        "--decision",
        "confirm",
        "--reason",
        "Confirmed after correction.",
        "--reviewer",
        "reviewer",
    )
    completed = _action(
        workspace,
        audit_id,
        "review-conclusion",
        "--decision",
        "confirm",
        "--reason",
        "The reviewed conclusion is ready.",
        "--reviewer",
        "reviewer",
    )
    assert completed["snapshot"]["status"] == "completed"
    reopened = _json(
        _run("audit", "inspect", "--workspace", str(workspace), "--audit-id", audit_id)
    )
    assert reopened["snapshot"]["conclusion_reviews"] == completed["snapshot"]["conclusion_reviews"]
    assert confirmed_entry["snapshot"]["conclusion"]["original_proposal"] == original

    signalled = _start(workspace, "audit-signal", plan)
    signalled_id = str(signalled["audit_id"])
    ownership_turn = _action(
        workspace, signalled_id, "answer", "--answer", "The team did that part, not me."
    )
    assert ownership_turn["snapshot"]["questions"][-1]["turn"] == "ownership"
    assistance_turn = _action(
        workspace, signalled_id, "answer", "--answer", "The team owned the work."
    )
    resumed_ladder = _action(
        workspace, signalled_id, "answer", "--answer", "No outside assistance."
    )
    assert assistance_turn["snapshot"]["questions"][-1]["turn"] == "assistance"
    assert resumed_ladder["snapshot"]["questions"][-1]["turn"] == "capability"
    assert resumed_ladder["snapshot"]["coverage"][0]["strongest_capability"] is None

    skipped = _start(workspace, "audit-skip", plan)
    skipped_id = str(skipped["audit_id"])
    rated = "自评 7/10 — 我选择跳过访谈"
    skip_conclusion = _action(workspace, skipped_id, "skip-contribution", "--answer", rated)
    entry = skip_conclusion["snapshot"]["conclusion"]["entries"][0]
    assert entry["self_rating"] == rated
    assert entry["verification"] == "self-assessed-unverified"
    rejected = _action(
        workspace,
        skipped_id,
        "review-conclusion",
        "--decision",
        "reject",
        "--reason",
        "The self-assessment is not an audited conclusion.",
        "--reviewer",
        "reviewer",
    )
    assert rejected["snapshot"]["status"] == "rejected"
