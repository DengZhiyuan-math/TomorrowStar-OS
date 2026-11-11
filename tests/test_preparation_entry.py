"""Preparation uses retained local stages without constructing a filling runtime."""

import json

import pytest
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal

from career_evidence_graph.application_flow import ApplicationFlowService
from career_evidence_graph.career_portal import create_server
from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError


@pytest.fixture(autouse=True)
def synthetic_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex-home"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def post(instance, action, payload):
    status, _, raw = instance.request(
        "POST",
        "/api/flow/" + action,
        body=json.dumps(payload).encode(),
        headers=instance.write_headers(),
    )
    return status, json.loads(raw)


def snapshot(instance):
    status, _, raw = instance.request("GET", "/api/flow/state")
    assert status == 200, raw
    return json.loads(raw)


def test_preparation_entry_persists_without_touching_filling_roots(portal, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "career_evidence_graph.application_runtime.WorkerService",
        lambda *_args, **_kwargs: pytest.fail("Preparation constructed a filling worker"),
    )
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic Employer",
            "role_title": "Python Engineer",
            "job_description": "Build reliable Python systems.",
        }
    )
    worker = tmp_path / "preserved-worker"
    worker.mkdir()
    (worker / "run.json").write_bytes(b"paused owner and unknown action")
    root = tmp_path / "material-preparation"
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=root,
        worker_root=worker,
        preparation_only=True,
    ) as active:
        state = snapshot(active)
        assert state["mode"] == "preparation"
        assert state["capabilities"]["worker"] is False
        assert active.server.worker_service is None
        status, task = post(
            active,
            "create",
            {
                "application_id": job["id"],
                "application_revision": job["revision"],
            },
        )
        assert status == 200, task
        assert task["worker_ref"] is None
        assert snapshot(active)["active_task"]["id"] == task["id"]
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=root,
        preparation_only=True,
    ) as reopened:
        assert snapshot(reopened)["active_task"] == task
    assert list(worker.iterdir()) == [worker / "run.json"]
    assert (worker / "run.json").read_bytes() == b"paused owner and unknown action"


def test_preparation_reports_unverified_connections_and_missing_dependencies(
    portal,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TOMORROWSTAR_CODEX_EXECUTABLE", str(tmp_path / "missing-codex"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "unused-codex-home"))
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        checks = snapshot(active)["preparation"]["checks"]
        assert set(checks) == {"gmail", "model", "sources", "pdf", "policy", "draft"}
        assert checks["gmail"]["status"] == "unavailable"
        assert checks["model"]["status"] == "unavailable"
        assert checks["sources"]["status"] == "unavailable"
        assert checks["policy"]["status"] == "available"
        assert "preparation-policy/v1.0" in checks["policy"]["message"]
        assert checks["draft"]["status"] == "not_created"
        assert all(row["message"] for row in checks.values())
        assert snapshot(active)["tasks"] == []


def test_preparation_keeps_valid_profile_when_a_document_exceeds_read_limit(portal, tmp_path):
    from test_preparation_candidate_chain import prepare_career

    prepare_career(portal)
    reports = portal.career / "reports"
    reports.mkdir()
    archive = reports / "synthetic-oversized-history.json"
    archive.write_bytes(b"x" * 2_000_001)
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        state = snapshot(active)
        sources = state["preparation"]["checks"]["sources"]
        assert sources["status"] == "needs_input"
        assert "超过读取大小限制" in sources["message"]
        assert "补齐个人资料" not in sources["message"]
        assert state["tasks"] == []
        assert state["capabilities"]["worker"] is False
    assert archive.stat().st_size == 2_000_001


@pytest.mark.parametrize(
    ("profile_state", "reason"),
    [
        ("missing", "未找到结构化个人资料"),
        ("invalid", "结构化个人资料格式无效"),
        ("unreadable", "结构化个人资料暂不可读"),
    ],
)
def test_preparation_names_the_actual_profile_problem(portal, tmp_path, profile_state, reason):
    from test_preparation_candidate_chain import prepare_career

    prepare_career(portal)
    profile = portal.career / "sources/profile.json"
    if profile_state == "missing":
        profile.unlink()
    elif profile_state == "invalid":
        profile.write_text('{"name": 1, "private": "synthetic-private-sentinel"}')
    else:
        profile.write_bytes(b"x" * 2_000_001)
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        state = snapshot(active)
        sources = state["preparation"]["checks"]["sources"]
        assert sources["status"] == "needs_input"
        assert reason in sources["message"]
        assert "synthetic-private-sentinel" not in sources["message"]
        assert state["tasks"] == []


@pytest.mark.parametrize(
    ("profile_state", "has_items", "status", "reason"),
    [
        ("valid", False, "unavailable", "尚无可用于材料准备的经历条目"),
        ("missing", False, "unavailable", "未找到结构化个人资料"),
        ("invalid", False, "unavailable", "结构化个人资料格式无效"),
        ("valid", True, "available", "内容归属仍以来源审核为准"),
    ],
)
def test_preparation_separates_profile_from_available_experience_items(
    portal, tmp_path, profile_state, has_items, status, reason
):
    from test_preparation_candidate_chain import prepare_career

    contribution = prepare_career(portal)
    if not has_items:
        contribution.unlink()
    profile = portal.career / "sources/profile.json"
    if profile_state == "missing":
        profile.unlink()
    elif profile_state == "invalid":
        profile.write_text('{"name": 1}')
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        sources = snapshot(active)["preparation"]["checks"]["sources"]
        assert sources["status"] == status
        assert reason in sources["message"]
        if profile_state == "valid":
            assert "补充个人资料" not in sources["message"]
            assert "添加个人资料" not in sources["message"]


def test_preparation_preserves_each_document_read_problem_without_exposing_content(
    portal, tmp_path
):
    from test_preparation_candidate_chain import prepare_career

    prepare_career(portal)
    reports = portal.career / "reports"
    reports.mkdir()
    (reports / "synthetic-private-format-sentinel.md").write_bytes(b"\xffprivate-content")
    (reports / "synthetic-private-large-sentinel.json").write_bytes(b"x" * 2_000_001)
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        sources = snapshot(active)["preparation"]["checks"]["sources"]
        assert sources["status"] == "needs_input"
        assert "超过读取大小限制" in sources["message"]
        assert "UTF-8" in sources["message"]
        assert "sentinel" not in sources["message"]
        assert "private-content" not in sources["message"]
        assert str(portal.career) not in sources["message"]


@pytest.mark.parametrize("changed", ["login", "codex_config", "policy"])
def test_preparation_connection_and_policy_changes_require_explicit_input_update(
    portal,
    tmp_path,
    monkeypatch,
    changed,
):
    from career_evidence_graph import application_preparation

    codex_home = tmp_path / "synthetic-codex"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Use Python.",
        }
    )
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        status, task = post(
            active,
            "create",
            {
                "application_id": job["id"],
                "application_revision": job["revision"],
            },
        )
        assert status == 200
        if changed == "policy":
            monkeypatch.setattr(application_preparation, "PREPARATION_POLICY_VERSION", "revised")
        else:
            name = "auth.json" if changed == "login" else "config.toml"
            (codex_home / name).write_text("synthetic changed identity")
        assert snapshot(active)["preparation"]["checks"]["draft"]["status"] == "stale"
        assert (
            post(
                active,
                "start",
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "stage": "analysis",
                },
            )[1]["error"]
            == "flow_inputs_stale"
        )
        status, updated = post(
            active,
            "update-inputs",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "application_revision": job["revision"],
            },
        )
        assert status == 200 and updated["inputs"] != task["inputs"]
        assert updated["analysis_id"] is None and updated["resume_id"] is None
        assert snapshot(active)["preparation"]["checks"]["draft"]["status"] == "not_created"


def test_preparation_rejects_filling_even_when_called_directly(portal, tmp_path):
    job = ApplicationStore(portal.applications).create_application(
        {
            "company": "Synthetic",
            "role_title": "Engineer",
            "job_description": "Use Python.",
        }
    )
    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "preparation",
        preparation_only=True,
    ) as active:
        _, task = post(
            active,
            "create",
            {
                "application_id": job["id"],
                "application_revision": job["revision"],
            },
        )
        for action, fields in [
            ("prepare-worker", {"country": "Switzerland", "send_confirmed": True}),
            ("worker-action", {"operation": "resume", "payload": {}}),
        ]:
            status, error = post(
                active,
                action,
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    **fields,
                },
            )
            assert status == 409 and error["error"] == "flow_preparation_only"
        assert snapshot(active)["active_task"] == task


@pytest.mark.parametrize("original_preparation", [True, False])
def test_preparation_cannot_recover_or_adopt_the_other_runtime_mode(
    portal,
    tmp_path,
    original_preparation,
):
    applications = ApplicationStore(portal.applications)
    root = tmp_path / "original-flow"
    original = ApplicationFlowService(applications, root, preparation_only=original_preparation)
    original.close()
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(PortalDataError) as error:
        create_server(
            portal.applications,
            portal.career,
            flow_root=root,
            preparation_only=not original_preparation,
        )
    assert error.value.code == "flow_mode_mismatch"
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
