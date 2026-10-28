"""Preparation measurements retain real work and never confer action authority."""

import json

import pytest

from career_evidence_graph.application_resume import ApplicationResumeStore
from career_evidence_graph.career_portal_data import ApplicationStore, CareerCatalog


def test_retired_html_preparation_cannot_record_successful_work_or_cache_hits(tmp_path):
    apps = tmp_path / "apps"
    apps.mkdir()
    career = tmp_path / "career"
    profile = career / "reports/public-site/site-content.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        json.dumps(
            {"schema_version": "public-site-source/v1", "profile": {"name": "Synthetic Person"}}
        )
    )
    applications = ApplicationStore(apps)
    app = applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "status": "drafting",
            "url": "https://careers.example.test/jobs/42",
        }
    )
    calls = []

    def tailor(draft, *args):
        calls.append(True)
        return draft | {"generation": "codex"}

    store = ApplicationResumeStore(
        applications,
        CareerCatalog(career),
        tmp_path / "resumes",
        tailorer=tailor,
        exporter=lambda html, pdf: pdf.write_bytes(b"%PDF-synthetic"),
    )
    from career_evidence_graph.career_portal_data import PortalDataError

    for _ in range(2):
        with pytest.raises(PortalDataError) as error:
            store.generate(app["id"], app["revision"])
        assert error.value.code == "resume_html_retired"
        assert error.value.status == 410
    assert not calls
    assert store.measurements.read() == []
    assert not list(store.root.rglob("resume.html"))
    assert not list(store.root.rglob("resume.pdf"))


def test_rejected_prepare_is_retained_without_changing_business_state(tmp_path, monkeypatch):
    import pytest

    from career_evidence_graph.application_worker import WorkerService
    from career_evidence_graph.career_portal_data import PortalDataError

    apps = tmp_path / "apps"
    apps.mkdir()
    service = WorkerService(ApplicationStore(apps), tmp_path / "worker")
    monkeypatch.setattr(service, "spawn", lambda: None)
    app = service.store.applications.create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "status": "drafting",
            "url": "https://jobs.lever.co/synthetic/00000000-0000-0000-0000-000000000001",
        }
    )
    with pytest.raises(PortalDataError):
        service.request("prepare", {"jobs": [{"application_id": app["id"], "revision": "stale"}]})
    assert service.store.load()["jobs"] == []
    events = service.store.measurements.read()
    assert len([e for e in events if e["kind"] == "episode_start"]) == 1
    assert any(e["kind"] == "stage_end" and e["result"] == "failed" for e in events)


def test_nested_stages_do_not_double_count_and_unknown_cost_stays_unknown(tmp_path, monkeypatch):
    import career_evidence_graph.worker_measurement as module
    from career_evidence_graph.worker_measurement import MeasurementLog

    now = [0]
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: now[0])
    log = MeasurementLog(tmp_path)
    episode = log.begin("synthetic-job")
    with log.stage("resume_prepare", episode_id=episode):
        now[0] = 1_000_000
        with log.stage("source_read"):
            now[0] = 3_000_000
        log.usage("")
        now[0] = 5_000_000
    log.event(
        "state",
        episode_id=episode,
        category="terminal",
        status="ready_for_review",
        pending_sync=False,
        intent_pending=False,
    )
    report = log.summary()
    row = report["episodes"][0]
    assert report["incomplete"] is False
    assert row["measurement_complete"] is True
    assert row["wall_ms"] == 5.0
    assert row["time_ms"]["auto"] == 5.0
    assert row["fee"] is None
    assert row["usage"] is None
    assert row["outcome"] == "ready"


def test_measurement_file_failure_does_not_change_preparation(tmp_path):
    from career_evidence_graph.worker_measurement import MeasurementLog

    root = tmp_path / "metrics"
    root.mkdir()
    target = tmp_path / "untouched"
    target.write_text("unchanged")
    (root / "measurements.jsonl").symlink_to(target)
    log = MeasurementLog(root)
    with log.stage("source_read"):
        result = "business result"
    assert result == "business result"
    assert target.read_text() == "unchanged"
    assert log.incomplete is True
    assert (root / ".measurement-incomplete").exists()


def test_wait_pause_and_cancel_remain_in_the_observed_timeline(tmp_path, monkeypatch):
    import career_evidence_graph.worker_measurement as module
    from career_evidence_graph.worker_measurement import MeasurementLog

    now = [0]
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: now[0])
    log = MeasurementLog(tmp_path)
    episode = log.begin("synthetic")
    with log.stage("form_step", episode_id=episode):
        now[0] = 2_000_000
    log.event("state", episode_id=episode, category="user_wait", status="needs_input")
    now[0] = 4_000_000
    log.event("state", episode_id=episode, category="pause", status="needs_input")
    now[0] = 6_000_000
    log.event("state", episode_id=episode, category="terminal", status="cancelled")
    row = log.summary()["episodes"][0]
    assert row["time_ms"] == {
        "auto": 2.0,
        "user_wait": 2.0,
        "pause": 2.0,
        "queue": 0.0,
        "outage": 0.0,
        "unobserved": 0.0,
    }
    assert row["outcome"] == "cancelled"
    assert row["human_active_ms"] is None


def test_corrupt_measurement_row_retains_known_started_processes(tmp_path):
    from career_evidence_graph.worker_measurement import MeasurementLog

    log = MeasurementLog(tmp_path)
    log.begin("synthetic-started")
    with log.path.open("a") as stream:
        stream.write("broken measurement row\n")
    report = log.summary()
    assert len(report["episodes"]) == 1
    assert report["incomplete"] is True
    assert report["episodes"][0]["measurement_complete"] is False
    assert "broken measurement row" in log.path.read_text()


def test_orphan_episode_marks_summary_incomplete_without_inventing_a_process(tmp_path):
    from career_evidence_graph.worker_measurement import MeasurementLog

    log = MeasurementLog(tmp_path)
    episode = log.begin("synthetic-started")
    log.event("state", episode_id="missing-start", category="terminal", status="ready_for_review")
    original = log.path.read_bytes()

    report = MeasurementLog(tmp_path).summary()

    assert report["incomplete"] is True
    assert [row["episode_id"] for row in report["episodes"]] == [episode]
    assert log.path.read_bytes() == original


@pytest.mark.parametrize("shared", [False, True])
def test_orphan_stage_end_marks_summary_incomplete_without_inventing_a_start(tmp_path, shared):
    from career_evidence_graph.worker_measurement import MeasurementLog

    log = MeasurementLog(tmp_path)
    episode = log.begin("synthetic-started")
    log.event(
        "stage_end",
        episode_id=None if shared else episode,
        stage="runtime_start" if shared else "fill",
        span_id="missing-start",
        result="passed",
        elapsed_ms=100,
    )
    original = log.path.read_bytes()

    report = MeasurementLog(tmp_path).summary()

    assert report["incomplete"] is True
    row = report["episodes"][0]
    if not shared:
        assert row["measurement_complete"] is False
    assert row["stages"] == []
    assert row["time_ms"]["auto"] == 0
    assert log.path.read_bytes() == original


@pytest.mark.parametrize("mismatch", ["episode_id", "clock_id", "stage"])
def test_stage_end_requires_the_same_episode_clock_and_stage(tmp_path, monkeypatch, mismatch):
    import career_evidence_graph.worker_measurement as module
    from career_evidence_graph.worker_measurement import MeasurementLog

    log = MeasurementLog(tmp_path)
    first = log.begin("first-synthetic-application")
    second = log.begin("second-synthetic-application")
    fields = {"episode_id": first, "stage": "fill"}
    log.event("stage_start", span_id="same-span", **fields)
    if mismatch == "clock_id":
        monkeypatch.setattr(module, "_CLOCK", "another-clock")
    else:
        fields[mismatch] = {"episode_id": second, "stage": "upload"}[mismatch]
    log.event("stage_end", span_id="same-span", elapsed_ms=100, result="passed", **fields)
    original = log.path.read_bytes()

    report = MeasurementLog(tmp_path).summary()

    assert report["incomplete"] is True
    row = next(row for row in report["episodes"] if row["episode_id"] == first)
    assert row["measurement_complete"] is False
    assert row["stages"] == []
    assert row["time_ms"]["auto"] == 0
    assert log.path.read_bytes() == original


@pytest.mark.parametrize("shared", [False, True])
def test_open_stage_is_incomplete_only_until_its_matching_end_arrives(tmp_path, shared):
    from career_evidence_graph.worker_measurement import MeasurementLog

    log = MeasurementLog(tmp_path)
    episode = log.begin("synthetic-started")

    with log.stage("runtime_start" if shared else "fill", episode_id=None if shared else episode):
        report = log.summary()
        assert report["incomplete"] is True
        if not shared:
            assert report["episodes"][0]["measurement_complete"] is False

    report = log.summary()
    assert report["incomplete"] is False
    assert report["episodes"][0]["measurement_complete"] is True


@pytest.mark.parametrize(
    "changes",
    [
        None,
        {"kind": []},
        {"kind": ""},
        {"kind": "state", "episode_id": []},
        {"kind": "state", "category": {}},
        {"monotonic_ns": []},
        {"monotonic_ns": True},
        {"clock_id": {}},
        {"kind": "stage_start", "span_id": []},
        {"kind": "stage_end", "stage": "fill", "span_id": "span", "result": "passed"},
        {
            "kind": "stage_end",
            "stage": "fill",
            "span_id": "span",
            "result": "passed",
            "elapsed_ms": "broken",
        },
        {"kind": "action_start", "attempt_id": []},
        {"kind": "cache"},
        {"kind": "intervention_request", "request_group": []},
        {"kind": "model_usage", "usage": []},
        {"kind": "model_usage", "usage": {"input_tokens": "37"}},
        {"kind": "state", "affected_jobs": [{}]},
    ],
)
def test_invalid_json_record_cannot_block_worker_reload_or_summary(tmp_path, monkeypatch, changes):
    from test_application_worker import job

    from career_evidence_graph.application_worker import WorkerService, WorkerStore

    apps = tmp_path / "apps"
    apps.mkdir()
    service = WorkerService(
        ApplicationStore(apps), tmp_path / "worker", fixture_origin="http://127.0.0.1:9999"
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    service.request("prepare", {"jobs": [job(service)]})
    checkpoint = service.store.load()
    valid = service.store.measurements.read()
    bad = dict(valid[0])
    if changes is None:
        bad.pop("kind")
    else:
        bad.update(changes)
    path = service.store.measurements.path
    first, rest = path.read_bytes().split(b"\n", 1)
    original = first + b"\n" + json.dumps(bad).encode() + b"\n" + rest
    path.write_bytes(original)

    reopened = WorkerStore(service.store.applications, service.store.root)

    assert reopened.load() == checkpoint
    assert reopened.measurements.read() == valid
    report = reopened.measurements.summary()
    assert report["incomplete"] is True
    assert len(report["episodes"]) == 1
    assert report["episodes"][0]["measurement_complete"] is False
    assert path.read_bytes() == original
    reopened.save(checkpoint)
    assert reopened.load() == checkpoint


@pytest.mark.parametrize("bad", [b'{"partial":"\xe4\xb8', b"\xff"])
@pytest.mark.parametrize("position", ["tail", "middle"])
def test_invalid_utf8_line_preserves_valid_episodes_and_checkpoint(
    tmp_path, monkeypatch, bad, position
):
    from test_application_worker import job

    from career_evidence_graph.application_worker import WorkerService, WorkerStore

    apps = tmp_path / "apps"
    apps.mkdir()
    service = WorkerService(
        ApplicationStore(apps), tmp_path / "worker", fixture_origin="http://127.0.0.1:9999"
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    service.request("prepare", {"jobs": [job(service)]})
    checkpoint = service.store.load()
    valid = service.store.measurements.read()
    path = service.store.measurements.path
    raw = path.read_bytes()
    first, rest = raw.split(b"\n", 1)
    original = raw + bad if position == "tail" else first + b"\n" + bad + b"\n" + rest
    path.write_bytes(original)

    reopened = WorkerStore(service.store.applications, service.store.root)

    assert reopened.load() == checkpoint
    assert reopened.measurements.read() == valid
    report = reopened.measurements.summary()
    assert report["incomplete"] is True
    assert len(report["episodes"]) == 1
    assert report["episodes"][0]["measurement_complete"] is False
    assert path.read_bytes() == original


@pytest.mark.parametrize("bad_tail", [b"\xe4\xb8", b'{"partial":'])
def test_new_episode_does_not_join_a_damaged_unterminated_tail(tmp_path, bad_tail):
    from career_evidence_graph.worker_measurement import MeasurementLog

    log = MeasurementLog(tmp_path)
    first = log.begin("first-synthetic-application")
    original = log.path.read_bytes() + bad_tail
    log.path.write_bytes(original)
    reopened = MeasurementLog(tmp_path)

    second = reopened.begin("second-synthetic-application")

    assert {row["episode_id"] for row in reopened.summary()["episodes"]} == {first, second}
    assert reopened.incomplete
    assert log.path.read_bytes().startswith(original + b"\n")


def test_invalid_measurement_link_cannot_stop_business_checkpoint(tmp_path, monkeypatch):
    from test_application_worker import job

    from career_evidence_graph.application_worker import WorkerService

    apps = tmp_path / "apps"
    apps.mkdir()
    service = WorkerService(
        ApplicationStore(apps), tmp_path / "worker", fixture_origin="http://127.0.0.1:9999"
    )
    monkeypatch.setattr(service, "spawn", lambda: None)
    service.request("prepare", {"jobs": [job(service)]})
    state = service.store.load()
    state["jobs"][0]["measurement_id"] = ["invalid observational link"]
    service.store.save(state)
    assert service.store.stop_reason() == ""
    assert service.store.load()["jobs"][0]["measurement_id"] == ["invalid observational link"]
    assert service.store.measurements.incomplete is True


def test_initial_start_wait_and_shared_startup_are_not_explicit_batch_pause(tmp_path, monkeypatch):
    import career_evidence_graph.worker_measurement as module
    from career_evidence_graph.worker_measurement import MeasurementLog

    now = [0]
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: now[0])
    log = MeasurementLog(tmp_path)
    episode = log.begin("synthetic")
    log.track(
        {
            "control": "paused",
            "batch_id": "synthetic-batch",
            "jobs": [
                {"measurement_id": episode, "application_id": "synthetic", "status": "queued"}
            ],
        }
    )
    now[0] = 1_000_000
    with log.stage("runtime_start", batch_id="synthetic-batch"):
        now[0] = 3_000_000
    now[0] = 4_000_000
    log.event("observation_end", episode_id=episode)
    report = log.summary()
    row = report["episodes"][0]
    assert report["incomplete"] is False
    assert row["measurement_complete"] is True
    assert row["time_ms"]["pause"] == 0.0
    assert row["time_ms"]["queue"] == 2.0
    assert row["time_ms"]["user_wait"] == 2.0
    assert row["time_ms"]["auto"] == 0.0


def test_unknown_rpc_and_blocked_later_call_have_different_dispatch_counts(tmp_path):
    import sys

    import pytest

    from career_evidence_graph.career_portal_data import PortalDataError
    from career_evidence_graph.cua_driver import CuaMcpClient
    from career_evidence_graph.worker_measurement import MeasurementLog

    child = tmp_path / "synthetic-mcp.py"
    child.write_text("""import json,sys
for line in sys.stdin:
    r=json.loads(line)
    if 'id' not in r: continue
    if r['method']=='tools/call': sys.exit(0)
    names=['browser_prepare','get_browser_state','browser_click','list_windows','end_session','check_permissions']
    result={'tools':[{'name':n} for n in names]} if r['method']=='tools/list' else {}
    print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
""")
    log = MeasurementLog(tmp_path)
    episode = log.begin("synthetic")
    with log.stage("form_step", episode_id=episode):
        client = CuaMcpClient([sys.executable, str(child)], None, timeout=1)
        try:
            for _ in range(2):
                with pytest.raises(PortalDataError):
                    client.call("browser_click", {})
        finally:
            client.close()
    row = log.summary()["episodes"][0]
    assert row["cua_calls"] == 2
    assert row["cua_dispatch"] == {"acknowledged": 0, "unknown": 1, "not_sent": 1}
