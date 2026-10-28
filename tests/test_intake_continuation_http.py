"""Loopback continuation endpoints preserve CSRF and server-owned cursor identity."""

import json

import pytest
from test_application_intake import message, page, ready
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal

from career_evidence_graph.application_intake import ApplicationIntakeService


@pytest.fixture(autouse=True)
def synthetic_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "synthetic-codex"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_http_continue_rejects_forged_cursor_and_preserves_scope_and_auth(portal, tmp_path):
    calls = []

    def reader(directory, **options):
        calls.append(options)
        return {
            "status": "readable",
            "emails": [message()],
            "provenance": {
                "next_page_token": "private-cursor" if len(calls) == 1 else "",
            },
        }

    def factory(applications, root):
        return ApplicationIntakeService(applications, root, reader=reader, fetcher=page)

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        preparation_only=True,
        flow_intake_factory=factory,
    ) as active:

        def post(action, body, auth=True):
            status, _, raw = active.request(
                "POST",
                "/api/recommendations/" + action,
                body=json.dumps(body).encode(),
                headers=active.write_headers() if auth else {},
            )
            return status, json.loads(raw)

        assert post("refresh", {}, False)[0] == 403
        assert post("refresh", {"after": "2026-10-01", "before": "2026-10-08"})[0] == 200
        state = ready(active.server.application_intake_service)
        assert state["status"] == "partial" and "private-cursor" not in json.dumps(state)
        assert post("continue", {"revision": state["revision"], "cursor": "forged"})[0] == 400
        assert post("continue", {"revision": "stale"})[0] == 409
        assert (
            post(
                "continue",
                {"revision": state["revision"], "after": "2026-10-01", "before": "2026-10-09"},
            )[0]
            == 409
        )
        assert len(calls) == 1
        assert post("continue", {"revision": state["revision"]})[0] == 200
        result = ready(active.server.application_intake_service)
        assert result["status"] == "complete" and len(calls) == 2
        row = result["recommendations"][0]
        assert (
            post("acquire", {"id": row["id"], "revision": row["revision"], "retry": "yes"})[0]
            == 400
        )
        assert post("reconcile-source", {"id": []})[0] == 400
