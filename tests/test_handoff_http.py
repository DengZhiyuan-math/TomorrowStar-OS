"""Synthetic loopback contracts for persistent single-job Codex handoff."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

import pytest
from test_career_portal_http import Portal

from career_evidence_graph.career_portal import create_server


@contextmanager
def handoff_portal(tmp_path: Path):
    applications = tmp_path / "applications"
    career = tmp_path / "career"
    applications.mkdir(exist_ok=True)
    career.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(career)], check=True)
    server = create_server(applications, career, handoff_root=tmp_path / "handoff")
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield Portal(server, applications, career)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_handoff_state_is_separate_from_experimental_worker(tmp_path):
    with handoff_portal(tmp_path) as portal:
        status, headers, raw = portal.request("GET", "/api/handoff/state")
        assert status == 200
        state = json.loads(raw)
        assert state["enabled"] is True
        assert state["execution_lane"] == "codex"
        assert state["tasks"] == []
        assert "no-store" in headers["Cache-Control"]
        status, _, raw = portal.request("GET", "/api/worker/state")
        assert status == 200
        assert json.loads(raw)["enabled"] is False


def test_execution_lanes_cannot_share_one_server(tmp_path):
    with pytest.raises(ValueError, match="separate"):
        create_server(
            tmp_path,
            tmp_path,
            worker_root=tmp_path / "automatic",
            handoff_root=tmp_path / "handoff",
        )


URL = "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc"
PDF = b"%PDF-1.4 Synthetic approved resume"
SHA = hashlib.sha256(PDF).hexdigest()


def post(portal, action, payload, *, headers=None):
    status, _, raw = portal.request(
        "POST",
        "/api/handoff/" + action,
        body=json.dumps(payload).encode(),
        headers=headers or portal.write_headers(),
    )
    return status, json.loads(raw)


def create_application(portal):
    status, _, raw = portal.request(
        "POST",
        "/api/applications",
        body=json.dumps(
            {
                "company": "Synthetic",
                "role_title": "Engineer",
                "url": URL,
                "application_strategy": "manual",
            }
        ).encode(),
        headers=portal.write_headers(),
    )
    assert status == 201, raw
    return json.loads(raw)["application"]


def prepare_payload(app):
    return {
        "application_id": app["id"],
        "revision": app["revision"],
        "country": "CHE",
        "filename": "approved.pdf",
        "file_base64": base64.b64encode(PDF).decode(),
        "acknowledge": True,
    }


def test_http_lifecycle_is_revision_bound_and_human_submission_is_explicit(tmp_path):
    with handoff_portal(tmp_path) as portal:
        app = create_application(portal)
        status, state = post(portal, "prepare", prepare_payload(app))
        assert status == 200, state
        task = state["active_task"]
        old_revision = task["revision"]
        status, state = post(
            portal,
            "claim",
            {"task_id": task["id"], "task_revision": task["revision"], "owner": "synthetic-codex"},
        )
        assert status == 200, state
        token = state["claim_token"]
        task = state["active_task"]
        status, conflict = post(
            portal,
            "claim",
            {"task_id": task["id"], "task_revision": old_revision, "owner": "second-executor"},
        )
        assert status == 409, conflict
        status, _, raw = portal.request("GET", "/api/handoff/state")
        assert status == 200
        assert token.encode() not in raw
        payload = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "claim_token": token,
            "result": "ready",
            "page_url": URL,
            "source": "Synthetic page and screenshot",
            "fields": [{"question": "Full name", "value": "Synthetic Person"}],
            "attachment": {"filename": "approved.pdf", "sha256": SHA},
            "missing": [],
        }
        status, state = post(portal, "readback", payload)
        assert status == 200, state
        task = state["active_task"]
        assert task["status"] == "ready_for_review"
        assert portal.state()["applications"][0]["status"] == "drafting"
        status, error = post(
            portal,
            "submitted",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "acknowledge": True,
                "source": "Attempt before review",
            },
        )
        assert status == 409, error
        for action, expected in [
            ("review", "reviewed"),
            ("submitted", "submitted"),
            ("receipt", "confirmed"),
        ]:
            status, state = post(
                portal,
                action,
                {
                    "task_id": task["id"],
                    "task_revision": task["revision"],
                    "acknowledge": True,
                    "source": "Synthetic human observation",
                    **({"locator": "Synthetic receipt-42"} if action == "receipt" else {}),
                },
            )
            assert status == 200, state
            task = next(item for item in state["tasks"] if item["id"] == task["id"])
            assert task["status"] == expected
        assert portal.state()["applications"][0]["status"] == "confirmation_received"
    with handoff_portal(tmp_path) as portal:
        status, _, raw = portal.request("GET", "/api/handoff/state")
        assert status == 200
        assert json.loads(raw)["tasks"][0]["status"] == "confirmed"
        assert token.encode() not in raw


@pytest.mark.parametrize(
    "action",
    [
        "prepare",
        "claim",
        "readback",
        "review",
        "submitted",
        "receipt",
        "resolve",
        "release",
        "retry-sync",
        "answer",
    ],
)
def test_all_handoff_writes_require_same_origin_csrf(tmp_path, action):
    with handoff_portal(tmp_path) as portal:
        for headers in (
            {"Content-Type": "application/json"},
            {**portal.write_headers(), "Origin": "https://untrusted.example"},
            {**portal.write_headers(), "X-CSRF-Token": "wrong"},
        ):
            status, _, raw = portal.request(
                "POST", "/api/handoff/" + action, body=b"{}", headers=headers
            )
            assert status == 403, raw
        status, _, raw = portal.request(
            "GET", "/api/handoff/state", headers={"Host": "untrusted.example"}
        )
        assert status == 403
        status, _, raw = portal.request(
            "POST",
            "/api/handoff/" + action,
            body=b"{}",
            headers={**portal.write_headers(), "Content-Length": "1048577"},
        )
        assert status == 413, raw


def needs_input_task(portal):
    app = create_application(portal)
    status, state = post(portal, "prepare", prepare_payload(app))
    assert status == 200, state
    task = state["active_task"]
    status, state = post(
        portal,
        "claim",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "owner": "synthetic-answer-codex",
        },
    )
    assert status == 200, state
    task, token = state["active_task"], state["claim_token"]
    status, state = post(
        portal,
        "readback",
        {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "claim_token": token,
            "result": "needs_input",
            "page_url": URL,
            "source": "Synthetic original partial readback",
            "fields": [{"question": "Full name", "value": "Synthetic Person"}],
            "attachment": {"filename": "approved.pdf", "sha256": SHA},
            "missing": ["Notice period"],
        },
    )
    assert status == 200, state
    return app, state["active_task"], token


def test_task_bound_answer_pauses_for_recheck_and_preserves_partial_readback(tmp_path):
    with handoff_portal(tmp_path) as portal:
        app, task, token = needs_input_task(portal)
        original = task["readbacks"]
        payload = {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "question": "Notice period",
            "value": "One month",
            "scope": {"application_id": app["id"]},
            "acknowledge": True,
        }
        status, state = post(portal, "answer", payload)
        assert status == 200, state
        task = state["active_task"]
        assert task["status"] == "needs_recheck"
        assert task["reason"] == "answer_changed"
        assert task["readbacks"] == original
        assert any(event["action"] == "human_answer_changed" for event in task["events"])
        saved = next(answer for answer in state["library"] if answer["value"] == "One month")
        assert saved["scope"] == {"application_id": app["id"]}
        assert saved["state"] == "confirmed"
        status, stale = post(portal, "answer", {**payload, "value": "Stale replacement"})
        assert status == 409, stale
        status, state = post(
            portal,
            "resolve",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "revision": app["revision"],
                "acknowledge": True,
                "source": "Synthetic human checked original page",
                "conclusion": "current_matches",
            },
        )
        assert status == 200, state
        task = state["active_task"]
        assert task["status"] == "claimed"
        assert task["readbacks"] == original
        assert any(answer["value"] == "One month" for answer in task["answers"])
        assert portal.state()["applications"][0]["status"] == "drafting"
        status, state = post(
            portal,
            "readback",
            {
                "task_id": task["id"],
                "task_revision": task["revision"],
                "claim_token": token,
                "result": "ready",
                "page_url": URL,
                "source": "Synthetic complete second readback",
                "fields": [
                    {"question": "Full name", "value": "Synthetic Person"},
                    {"question": "Notice period", "value": "One month"},
                ],
                "attachment": {"filename": "approved.pdf", "sha256": SHA},
                "missing": [],
            },
        )
        assert status == 200, state
        assert state["active_task"]["status"] == "ready_for_review"
        assert state["active_task"]["readbacks"][0] == original[0]
        assert len(state["active_task"]["readbacks"]) == 2
