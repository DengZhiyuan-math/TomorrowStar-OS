"""Production intake wiring uses synthetic mail through authenticated HTTP."""

import json
from functools import partial

import pytest
from test_application_intake import message, ready
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal

from career_evidence_graph import application_intake


def request(active, path, payload=None):
    status, _, raw = active.request(
        "GET" if payload is None else "POST",
        path,
        body=None if payload is None else json.dumps(payload).encode(),
        headers={} if payload is None else active.write_headers(),
    )
    assert status == 200, raw
    return json.loads(raw)


@pytest.mark.parametrize("label", [None, "  Synthetic Jobs / 已处理  ", "INBOX", 42, ""])
def test_configured_label_is_local_and_reopening_preserves_mail_receipts(
    portal, tmp_path, monkeypatch, label
):
    reads, calls, fetches = [], [], []
    external = {"labeled": False, "archived": False}
    invalid = label is not None and label != "  Synthetic Jobs / 已处理  "

    def reader(*args, **kwargs):
        reads.append(kwargs)
        return {
            "status": "readable",
            "emails": [message()],
            "provenance": {"mailbox_identity": "a" * 64, "account_identity_status": "verified"},
        }

    def mailbox(directory, *, operation, label_name, expected_mailbox_identity, **kwargs):
        assert label_name == label
        assert expected_mailbox_identity == "a" * 64
        # All original mail and candidate links must be durable before a mailbox call.
        saved = active.server.application_intake_service.snapshot()["recommendations"]
        assert saved[0]["source_messages"][0]["message_id"] == "mail-one"
        calls.append(operation)
        if operation == "label":
            external["labeled"] = True
        if operation == "archive":
            external["archived"] = True
            raise TimeoutError("Synthetic archive response lost")
        return {"status": "complete", **external}

    monkeypatch.setattr(
        application_intake,
        "ApplicationIntakeService",
        partial(
            application_intake.ApplicationIntakeService,
            reader=reader,
            mailbox=mailbox,
            fetcher=lambda url: fetches.append(url),
        ),
    )
    options = {"flow_root": tmp_path / "flow", "application_processed_label": label}
    with _running_portal(portal.applications, portal.career, **options) as active:
        state = request(active, "/api/recommendations/state")
        assert state["enabled"] is True
        assert state["progress"].get("mail_processing_error", "") == (
            "gmail_processing_invalid" if invalid else ""
        )
        assert active.state()["connections"]["applications"] is True
        request(active, "/api/recommendations/refresh", {"capture_only": True})
        captured = ready(active.server.application_intake_service)
        assert captured["progress"]["mail_captured"] == 1
        assert captured["progress"]["mail_labeled"] == int(label is not None and not invalid)
        assert captured["progress"]["mail_archived"] == 0
        assert len(captured["recommendations"]) == 1
        assert not fetches
        assert active.server.application_flow_service.snapshot()["tasks"] == []
    before = list(calls)
    with _running_portal(portal.applications, portal.career, **options) as active:
        reopened = request(active, "/api/recommendations/state")
        assert reopened["recommendations"] == captured["recommendations"]
        assert reopened["progress"]["mail_captured"] == 1
        assert calls == before and len(reads) == 1
        if label is not None and not invalid:
            assert reopened["progress"]["mail_needs_recheck"] == 1
            request(active, "/api/recommendations/continue", {"revision": reopened["revision"]})
            reconciled = ready(active.server.application_intake_service)
            assert reconciled["progress"]["mail_archived"] == 1
            assert reconciled["progress"]["mail_needs_recheck"] == 0
            assert calls == ["inspect", "label", "inspect", "archive", "inspect"]
        else:
            assert calls == []
            assert not reopened["progress"]["mail_label_configured"]
        assert not fetches
        assert active.server.application_flow_service.snapshot()["tasks"] == []
