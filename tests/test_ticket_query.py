"""Exercise the read-only tracker query through its command-line interface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/query_tickets.py"


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def query(root: Path):
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--root", str(root), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, json.loads(result.stdout) if result.stdout else {}


def test_lists_readme_led_bold_tickets_and_excludes_nested_history(tmp_path):
    write(tmp_path, ".scratch/first/map.md", "# Map\n")
    write(
        tmp_path,
        ".scratch/first/issues/01-start.md",
        "# Start\nStatus: open\nAssignee: none\nBlocked by: none\n",
    )
    write(tmp_path, ".scratch/legacy/README.md", "# Legacy\n")
    write(
        tmp_path,
        ".scratch/legacy/issues/07-investigation.md",
        "# Investigate\n**Status:** open\n**Assignee:** root\n**Blocked by:** None.\n",
    )
    write(tmp_path, ".scratch/old/before/first/issues/01-copy.md", "Status: open\n")
    write(tmp_path, ".scratch/fixtures/issues/01-fixture.md", "Status: open\n")
    result, report = query(tmp_path)
    assert result.returncode == 0, result.stderr
    assert [item["path"] for item in report["tickets"]] == [
        ".scratch/first/issues/01-start.md",
        ".scratch/legacy/issues/07-investigation.md",
    ]
    assert report["scopes"]["all"]["total"] == 2
    assert report["scopes"]["map_directories"]["total"] == 1
    assert report["mechanical_frontier"] == [".scratch/first/issues/01-start.md"]


def test_unknown_owners_remain_unknown_and_body_cannot_supply_an_owner(tmp_path):
    write(
        tmp_path,
        ".scratch/map/issues/01-missing.md",
        "# Missing\nStatus: open\nBlocked by: none\n\n## History\nAssignee: none\n",
    )
    write(
        tmp_path,
        ".scratch/map/issues/02-empty.md",
        "# Empty\nStatus: open\nAssignee:\nBlocked by: none\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 0, result.stderr
    assert [item["assignee"] for item in report["tickets"]] == [None, None]
    assert report["mechanical_frontier"] == []
    assert {item["field"] for item in report["warnings"]} == {"Assignee"}


@pytest.mark.parametrize(
    ("metadata", "field"),
    [
        ("Status: open\nStatus: closed\nAssignee: none", "Status"),
        ("Assignee: none", "Status"),
        ("Status: running\nAssignee: none", "Status"),
        ("Status: open\nAssignee: none\nAssignee: root", "Assignee"),
    ],
)
def test_bad_metadata_reports_error_and_never_enters_frontier(tmp_path, metadata, field):
    write(tmp_path, ".scratch/map/issues/01-bad.md", f"# Bad\n{metadata}\nBlocked by: none\n")
    result, report = query(tmp_path)
    assert result.returncode == 2
    assert any(e["code"] == "invalid_metadata" and e["field"] == field for e in report["errors"])
    assert report["mechanical_frontier"] == []
    assert len(report["tickets"]) == 1


def test_cross_map_and_numeric_dependencies_keep_human_and_pause_gates_separate(tmp_path):
    write(
        tmp_path, ".scratch/a/issues/01-first.md", "# First\nStatus: resolved\nBlocked by: none\n"
    )
    write(tmp_path, ".scratch/a/issues/02-second.md", "# Second\nStatus: closed\nBlocked by: 无\n")
    write(
        tmp_path,
        ".scratch/a/issues/03-ready.md",
        "# Ready\nStatus: open\nAssignee: none\nBlocked by: 01, 02\nType: grilling\n",
    )
    write(
        tmp_path,
        ".scratch/single-job-application-flow-2026-10-16/issues/04-review.md",
        "# Review\nStatus: open\nAssignee: none\nInteraction: AFK with bounded HITL observations\n"
        "Blocked by: [First](../../a/issues/01-first.md)\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 0, result.stderr
    ready, paused = report["tickets"][2:]
    assert ready["direct_dependencies"] == [
        ".scratch/a/issues/01-first.md",
        ".scratch/a/issues/02-second.md",
    ]
    assert ready["mechanical_frontier"] and ready["requires_human"]
    assert paused["mechanical_frontier"] and paused["paused_route"] and paused["requires_human"]
    assert report["execution_authorized"] is False


def test_missing_dependency_declaration_is_unknown_not_a_free_start(tmp_path):
    write(tmp_path, ".scratch/a/issues/01-unknown.md", "# Unknown\nStatus: open\nAssignee: none\n")
    result, report = query(tmp_path)
    assert result.returncode == 0
    assert report["tickets"][0]["dependencies_known"] is False
    assert report["mechanical_frontier"] == []
    assert any(w["field"] == "Blocked by" for w in report["warnings"])


@pytest.mark.parametrize(
    ("blocked", "extra", "code"),
    [
        ("[Missing](99-missing.md)", {}, "missing_or_noncanonical_dependency"),
        (
            "[Outside](../../archive/before/issues/01-old.md)",
            {},
            "missing_or_noncanonical_dependency",
        ),
        ("02", {"02-a.md": "closed", "02-b.md": "closed"}, "ambiguous_or_missing_dependency"),
        ("some other task", {}, "invalid_dependency_declaration"),
        ("[Two](02-second.md)", {"02-second.md": "cycle"}, "dependency_cycle"),
        ("[Two](02-second.md)", {"02-second.md": "superseded"}, "active_dependency_on_superseded"),
    ],
)
def test_dependency_errors_fail_closed_without_omitting_tickets(tmp_path, blocked, extra, code):
    write(
        tmp_path,
        ".scratch/a/issues/01-first.md",
        f"# First\nStatus: open\nAssignee: none\nBlocked by: {blocked}\n",
    )
    for name, kind in extra.items():
        content = "# Other\nStatus: closed\nBlocked by: none\n"
        if kind == "cycle":
            content = "# Cycle\nStatus: closed\nBlocked by: [First](01-first.md)\n"
        if kind == "superseded":
            content += "Closure reason: superseded\n"
        write(tmp_path, f".scratch/a/issues/{name}", content)
    result, report = query(tmp_path)
    assert result.returncode == 2
    assert code in {error["code"] for error in report["errors"]}
    assert report["mechanical_frontier"] == []
    assert len(report["tickets"]) == 1 + len(extra)


def test_release_scopes_use_published_identities_and_current_ticket_statuses(tmp_path):
    for name, status in [
        ("01-original", "closed"),
        ("02-old", "closed"),
        ("03-baseline", "closed"),
        ("04-next", "open"),
    ]:
        suffix = "Closure reason: superseded\n" if name == "02-old" else ""
        write(
            tmp_path,
            f".scratch/a/issues/{name}.md",
            f"# {name}\nStatus: {status}\nAssignee: none\nBlocked by: none\n{suffix}",
        )
    publication = {
        "records": [{"canonical_path": ".scratch/a/issues/01-original.md", "status": "open"}],
        "superseded": [{"path": ".scratch/a/issues/02-old.md"}],
        "completed_evidence_preserved": [{"path": ".scratch/a/issues/03-baseline.md"}],
    }
    write(
        tmp_path,
        ".scratch/tomorrowstar-ticket-consolidation-2026-10-17/publication.json",
        json.dumps(publication),
    )
    result, report = query(tmp_path)
    assert result.returncode == 0
    original = report["scopes"]["original_published"]
    assert original["total"] == original["closed_or_resolved"] == 1
    assert original["unclosed"] == 0
    assert report["scopes"]["current_delivery"]["paths"] == [
        ".scratch/a/issues/01-original.md",
        ".scratch/a/issues/04-next.md",
    ]
    assert report["scopes"]["all"]["administrative_superseded"] == 1
    write(
        tmp_path,
        ".scratch/a/issues/05-future.md",
        "# Future\nStatus: open\nAssignee: none\nBlocked by: none\n",
    )
    _, later = query(tmp_path)
    assert later["scopes"]["current_delivery"]["total"] == 3
    assert later["scopes"]["original_published"]["total"] == 1


def test_query_repeats_without_writing_or_repairing_any_inputs(tmp_path):
    write(tmp_path, ".scratch/a/map.md", "# Map\n")
    write(
        tmp_path,
        ".scratch/a/issues/01-task.md",
        "# Task\nStatus: claimed\nAssignee: root\nBlocked by: none\n",
    )
    write(tmp_path, ".scratch/old/history/evidence.txt", "Original failure\n")
    before = {
        str(p.relative_to(tmp_path)): (
            p.read_bytes() if p.is_file() else None,
            p.stat().st_mtime_ns,
        )
        for p in tmp_path.rglob("*")
    }
    one, first = query(tmp_path)
    two, second = query(tmp_path)
    assert one.returncode == two.returncode == 0
    assert first == second
    assert before == {
        str(p.relative_to(tmp_path)): (
            p.read_bytes() if p.is_file() else None,
            p.stat().st_mtime_ns,
        )
        for p in tmp_path.rglob("*")
    }


@pytest.mark.parametrize("component", ["group", "issues", "ticket"])
def test_symbolic_links_cannot_import_outside_ticket_bodies(tmp_path, component):
    root = tmp_path / "checkout"
    write(root, ".scratch/a/issues/01-safe.md", "# Safe\nStatus: closed\nBlocked by: none\n")
    outside = tmp_path / "outside"
    secret = write(
        outside, "issues/02-secret.md", "# PRIVATE_SENTINEL\nStatus: closed\nBlocked by: none\n"
    )
    if component == "group":
        (root / ".scratch/leak").symlink_to(outside, target_is_directory=True)
    elif component == "issues":
        (root / ".scratch/leak").mkdir()
        (root / ".scratch/leak/issues").symlink_to(outside / "issues", target_is_directory=True)
    else:
        (root / ".scratch/a/issues/02-alias.md").symlink_to(secret)
    result, report = query(root)
    assert result.returncode == 2
    assert "unsafe_path" in {e["code"] for e in report["errors"]}
    assert "PRIVATE_SENTINEL" not in result.stdout + result.stderr


def test_malformed_publication_is_an_explicit_failure(tmp_path):
    write(
        tmp_path,
        ".scratch/a/issues/01-task.md",
        "# Task\nStatus: open\nAssignee: none\nBlocked by: none\n",
    )
    write(
        tmp_path,
        ".scratch/tomorrowstar-ticket-consolidation-2026-10-17/publication.json",
        "{broken",
    )
    result, report = query(tmp_path)
    assert result.returncode == 2
    assert report["scopes"]["original_published"]["available"] is False
    assert report["errors"][0]["code"] == "invalid_publication"
    assert report["mechanical_frontier"] == []


def test_legacy_owner_labels_are_preserved_verbatim(tmp_path):
    write(
        tmp_path,
        ".scratch/a/issues/01-owned.md",
        "# Owned\nStatus: open\nAssignee: Codex / root\nBlocked by: none\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 0
    assert report["tickets"][0]["assignee"] == "Codex / root"
    assert report["mechanical_frontier"] == []


@pytest.mark.parametrize("blocked", ["none, 02", "[One](01-done.md), 02"])
def test_partial_dependency_syntax_cannot_silently_drop_a_blocker(tmp_path, blocked):
    write(tmp_path, ".scratch/a/issues/01-done.md", "# Done\nStatus: closed\nBlocked by: none\n")
    write(
        tmp_path,
        ".scratch/a/issues/03-next.md",
        f"# Next\nStatus: open\nAssignee: none\nBlocked by: {blocked}\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 2
    assert report["mechanical_frontier"] == []
    assert "invalid_dependency_declaration" in {e["code"] for e in report["errors"]}


def test_empty_ticket_is_reported_and_text_output_explains_failure(tmp_path):
    write(tmp_path, ".scratch/a/issues/01-empty.md", "")
    result, report = query(tmp_path)
    assert result.returncode == 2
    assert report["tickets"][0]["status"] is None
    assert "invalid_metadata" in {e["code"] for e in report["errors"]}
    text = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert text.returncode == 2
    assert "invalid_metadata" in text.stdout
    assert "execution_authorized=false" in text.stdout


@pytest.mark.parametrize("blocked", ["none；02", "[Done](01-done.md)。02"])
def test_numbered_blocker_after_explanation_separator_is_not_dropped(tmp_path, blocked):
    write(tmp_path, ".scratch/a/issues/01-done.md", "# Done\nStatus: closed\nBlocked by: none\n")
    write(
        tmp_path,
        ".scratch/a/issues/03-next.md",
        f"# Next\nStatus: open\nAssignee: none\nBlocked by: {blocked}\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 2
    assert report["mechanical_frontier"] == []


def test_alternate_bold_key_cannot_hide_a_conflicting_owner(tmp_path):
    write(
        tmp_path,
        ".scratch/a/issues/01-conflict.md",
        "# Conflict\nStatus: open\nAssignee: none\n**Assignee**: root\nBlocked by: none\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 2
    assert report["tickets"][0]["assignee"] is None
    assert report["mechanical_frontier"] == []


@pytest.mark.parametrize("claim", ["unrecorded", "", "???"])
def test_explicit_unknown_claim_state_is_not_an_unclaimed_ticket(tmp_path, claim):
    write(
        tmp_path,
        ".scratch/a/issues/01-claim.md",
        f"# Claim\nStatus: open\nAssignee: none\nClaim state: {claim}\nBlocked by: none\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 0
    assert report["tickets"][0]["ownership_known"] is False
    assert report["mechanical_frontier"] == []
    assert any(w["field"] == "Claim state" for w in report["warnings"])


def test_issue_directory_navigation_is_not_counted_and_chinese_no_dependency_is_readable(tmp_path):
    for name in ("README.md", "map.md", "index.md"):
        write(tmp_path, f".scratch/a/issues/{name}", "# Navigation\n")
    write(
        tmp_path,
        ".scratch/a/issues/01-task.md",
        "# Task\n**Status**: open\n**Assignee**: none\n**Blocked by**: 无前置\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 0
    assert report["scopes"]["all"]["total"] == 1
    assert report["mechanical_frontier"] == [".scratch/a/issues/01-task.md"]


def test_existing_numbered_notes_have_explicit_nonblocking_dispositions(tmp_path):
    write(
        tmp_path,
        ".scratch/a/issues/08-installed.md",
        "# Installed\nStatus: closed\n"
        "Blocked by: 无；07及两份精确合成PDF测试授权门槛已满足。"
        "09实际用户体验接受单独保留。\n",
    )
    result, report = query(tmp_path)
    assert result.returncode == 0
    assert report["tickets"][0]["dependencies_known"] is True
    assert report["tickets"][0]["direct_dependencies"] == []
