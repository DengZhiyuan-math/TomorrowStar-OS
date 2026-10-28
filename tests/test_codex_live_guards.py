"""MC-10 live-test guards, checked offline against the controlled app-server peer."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from codex_live_guards import (
    InboundTap,
    OutboundTap,
    assert_isolated_codex_home,
    c0_passed,
    codex_home_names,
    frame_violations,
    mark_passed,
    prepare_case_dir,
)
from test_application_codex_assist import config, server

from career_evidence_graph.application_codex_assist import PROTOCOL_VERSION, CodexAdapter


def peer_methods(executable):
    rows = [json.loads(line) for line in executable.with_suffix(".jsonl").read_text().splitlines()]
    return [row["method"] for row in rows if "method" in row]


@pytest.mark.parametrize("entry", ["AGENTS.md", "skills", "memories", "rules", ".agents"])
@pytest.mark.parametrize("inside", [".", ".codex"])
def test_isolated_home_refuses_user_context_entries_by_name(tmp_path, entry, inside):
    home = tmp_path / "codex-home"
    (home / ".codex").mkdir(parents=True)
    target = home / inside / entry
    if entry == "skills":
        (target / "user-skill").mkdir(parents=True)  # a skill beside the bundled .system
    elif entry.endswith(".md"):
        target.write_text("synthetic")
    else:
        target.mkdir()
    with pytest.raises(AssertionError, match=entry):
        assert_isolated_codex_home(home)


def test_isolated_home_allows_only_the_bundled_system_skills_and_lists_names(tmp_path):
    home = tmp_path / "codex-home"
    (home / ".codex" / "skills" / ".system" / "bundled").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("{}")  # presence only; never read
    assert assert_isolated_codex_home(home) == home.resolve()
    assert codex_home_names(home) == {
        "home": [".codex"],
        ".codex": ["auth.json", "skills"],
        ".codex/skills": [".system"],
    }


def test_isolated_home_accepts_a_clean_directory_and_refuses_the_user_home(tmp_path):
    home = tmp_path / "codex-home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("{}")  # presence only; never read
    assert assert_isolated_codex_home(home) == home.resolve()
    with pytest.raises(AssertionError, match="user home"):
        assert_isolated_codex_home(Path.home())
    with pytest.raises(AssertionError, match="absolute"):
        assert_isolated_codex_home(Path("relative-home"))


def test_frame_violations_flag_user_paths_private_roots_and_real_domains(tmp_path):
    temp = "/Users/synthetic/tmp-root"
    private = "/Volumes/synthetic/private-workspace"
    text = json.dumps(
        {
            "inside": temp + "/peer/runtime",
            "outside": "/Users/synthetic/.local/bin/python3.13",
            "private": private + "/applications/x.json",
            "mail": "https://www.linkedin.com/jobs/view/10001",
            "other_job": "https://jobs.lever.co/other-company/1",
            "job": "https://jobs.lever.co/synthetic-1/00000000-0000-0000-0000-000000000001/apply",
            "fact": "synthetic@example.invalid",
            "reserved": "https://exfil.example/collect and https://a.test/",
            "loopback": "http://127.0.0.1:8123/application",
            "not_hosts": "Google Chrome.app features.hooks handoff.json synthetic.pdf",
        }
    )
    assert frame_violations(text, temp_root=temp, private_roots=[private]) == [
        "user_path:/Users/synthetic/.local/bin/python3.13",
        "private_root:" + private,
        "domain:jobs.lever.co/other-company",
        "domain:www.linkedin.com",
    ]
    clean = json.dumps({"cwd": temp, "job": "https://jobs.lever.co/synthetic-1/x"})
    assert frame_violations(clean, temp_root=temp, private_roots=[private]) == []


def test_outbound_tap_records_clean_frames_from_the_controlled_peer(tmp_path):
    executable = server(tmp_path)
    adapter = CodexAdapter(config(tmp_path, executable))
    evidence = tmp_path / "outbound.jsonl"
    tap = OutboundTap(adapter, evidence, temp_root=tmp_path, private_roots=[])
    inbound = InboundTap(adapter, tmp_path / "inbound.jsonl")
    try:
        run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
        assert run.status == "ready"
    finally:
        adapter.close()
    written = [json.loads(line) for line in evidence.read_text().splitlines()]
    assert [row["frame"]["method"] for row in written] == [
        "initialize",
        "initialized",
        "config/read",
        "thread/start",
    ]
    assert tap.violations == [] and tap.blocked == []
    assert tap.counts == {"initialize": 1, "initialized": 1, "config/read": 1, "thread/start": 1}
    assert [row["method"] for row in tap.responses] == ["initialize", "config/read", "thread/start"]
    assert peer_methods(executable) == [row["frame"]["method"] for row in written]
    received = [json.loads(line) for line in (tmp_path / "inbound.jsonl").read_text().splitlines()]
    assert [row["id"] for row in received] == [1, 2, 3] == [row["id"] for row in inbound.messages]
    assert received[0]["result_keys"] == ["codexHome", "platformFamily", "platformOs", "userAgent"]


def test_outbound_tap_blocks_a_private_frame_before_it_reaches_the_peer(tmp_path):
    executable = server(tmp_path)
    adapter = CodexAdapter(config(tmp_path, executable))
    runtime = tmp_path / "runtime"  # thread/start carries cwd=runtime
    tap = OutboundTap(adapter, tmp_path / "outbound.jsonl", temp_root=None, private_roots=[runtime])
    try:
        run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    finally:
        adapter.close()
    assert run.status == "unknown" and run.error_code == "transport_failed"
    assert run.model_turn_allowed is False
    assert [row["method"] for row in tap.blocked] == ["config/read"]
    assert tap.violations == ["private_root:" + str(runtime.resolve())]
    assert "config/read" not in peer_methods(executable)
    rows = [json.loads(line) for line in (tmp_path / "outbound.jsonl").read_text().splitlines()]
    assert [row.get("blocked") for row in rows] == [None, None, True]
    assert "frame" not in rows[-1]


def test_outbound_tap_limits_sessions_and_turns(tmp_path):
    executable = server(tmp_path)
    adapter = CodexAdapter(config(tmp_path, executable))
    tap = OutboundTap(
        adapter,
        tmp_path / "outbound.jsonl",
        temp_root=tmp_path,
        private_roots=[],
        limits={"thread/start": 0},
    )
    try:
        run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    finally:
        adapter.close()
    assert run.status == "unknown" and run.thread_id is None
    assert [row["method"] for row in tap.blocked] == ["thread/start"]
    assert tap.blocked[0]["reasons"] == ["limit:thread/start"]
    assert tap.violations == []
    assert "thread/start" not in peer_methods(executable)


def test_tap_rows_carry_monotonic_time_and_request_latency(tmp_path):
    executable = server(tmp_path)
    adapter = CodexAdapter(config(tmp_path, executable))
    tap = OutboundTap(adapter, tmp_path / "out.jsonl", temp_root=tmp_path, private_roots=[])
    inbound = InboundTap(adapter, tmp_path / "in.jsonl")
    try:
        adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    finally:
        adapter.close()
    for path in ("out.jsonl", "in.jsonl"):
        rows = [json.loads(line) for line in (tmp_path / path).read_text().splitlines()]
        assert rows and all(isinstance(row["t"], float) for row in rows)
    assert all(isinstance(row["t"], float) for row in inbound.messages)
    assert [row["method"] for row in tap.responses] == ["initialize", "config/read", "thread/start"]
    assert all(0 <= row["latency"] < 15 for row in tap.responses)


def test_inbound_tap_keeps_json_rpc_error_bodies_and_failed_requests(tmp_path):
    executable = server(tmp_path, "rejected")
    adapter = CodexAdapter(config(tmp_path, executable))
    tap = OutboundTap(adapter, tmp_path / "out.jsonl", temp_root=tmp_path, private_roots=[])
    inbound = InboundTap(adapter, tmp_path / "in.jsonl")
    try:
        run = adapter.start({"assistance_id": "assist-1"}, request_id="start-1")
    finally:
        adapter.close()
    assert run.error_code == "request_rejected"
    assert inbound.messages[0]["error"] == {"code": -32000, "message": "secret sentinel"}
    assert tap.failures[0]["method"] == "initialize"
    assert "request_rejected" in tap.failures[0]["error"]
    assert isinstance(tap.failures[0]["latency"], float)


def test_turn_frames_refuse_checkout_and_user_name_tokens(tmp_path):
    tap = OutboundTap(
        SimpleNamespace(_send=None, _request=None),
        tmp_path / "out.jsonl",
        temp_root=tmp_path,
        private_roots=[],
        turn_tokens=["/Volumes/Work/checkout", "synthuser"],
    )
    tap.check({"method": "thread/start", "params": {"command": "/Volumes/Work/checkout/driver"}})
    with pytest.raises(OSError, match="turn_token"):
        tap.check(
            {
                "method": "turn/start",
                "params": {"text": "/Volumes/Work/checkout/x and /Volumes/home/synthuser/y"},
            }
        )
    assert tap.violations == ["turn_token:/Volumes/Work/checkout", "turn_token:synthuser"]


def fake_codex(tmp_path, version):
    path = tmp_path / "fake-codex"
    path.write_text(f"#!/bin/sh\necho 'codex-cli {version}'\n")
    path.chmod(0o700)
    return path


def test_case_dir_checks_version_first_and_reruns_only_before_any_turn(tmp_path):
    root, home = tmp_path / "evidence", tmp_path / "home"
    home.mkdir()
    with pytest.raises(AssertionError, match="version"):
        prepare_case_dir(root, "C1", fake_codex(tmp_path, "0.1"), home)
    assert not (root / "C1").exists()
    executable = fake_codex(tmp_path, PROTOCOL_VERSION)
    first, info = prepare_case_dir(root, "C1", executable, home)
    assert first == root / "C1" and first.is_dir() and info["prior"] == []
    assert info["version"] == "codex-cli " + PROTOCOL_VERSION and len(info["sha256"]) == 64
    (first / "outbound.jsonl").write_text(
        json.dumps({"blocked": True, "method": "turn/start", "reasons": ["limit:turn/start"]})
        + "\n"
    )
    again, info = prepare_case_dir(root, "C1", executable, home)
    assert again == first and info["prior"] == ["C1.prior-1"]
    assert (root / "C1.prior-1" / "outbound.jsonl").is_file()
    (again / "outbound.jsonl").write_text(
        json.dumps({"method": "turn/start", "frame": {"method": "turn/start"}}) + "\n"
    )
    with pytest.raises(AssertionError, match="turn/start"):
        prepare_case_dir(root, "C1", executable, home)


def test_later_cases_require_the_c0_pass_marker(tmp_path):
    assert c0_passed(tmp_path) is False
    (tmp_path / "C0").mkdir()
    mark_passed(tmp_path / "C0")
    assert c0_passed(tmp_path) is True
