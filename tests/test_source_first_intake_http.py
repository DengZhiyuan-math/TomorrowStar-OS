"""Source-only intake HTTP contracts use synthetic sources and authentication."""

import json

from test_application_intake import ready
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal
from test_source_first_intake import TEXT, fields

from career_evidence_graph.application_intake import ApplicationIntakeService


def test_source_only_http_accepts_paste_and_rejects_manual_fact_payload(portal, tmp_path):
    def factory(applications, root):
        return ApplicationIntakeService(applications, root, extractor=fields)

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        preparation_only=True,
        flow_intake_factory=factory,
    ) as active:
        body = {"text": TEXT, "request_id": "e" * 32}
        assert (
            active.request("POST", "/api/intake/ingest", body=json.dumps(body).encode())[0] == 403
        )
        status, _, raw = active.request(
            "POST",
            "/api/intake/ingest",
            body=json.dumps(body).encode(),
            headers=active.write_headers(),
        )
        assert status == 200, raw
        done = ready(active.server.application_intake_service)
        assert done["job"]["status"] == "saved"
        status, _, raw = active.request("GET", "/api/intake/state")
        assert status == 200
        assert json.loads(raw)["job"]["application_id"] == done["job"]["application_id"]
        status, _, _ = active.request(
            "POST",
            "/api/intake/ingest",
            body=json.dumps(body | {"company": "Manual"}).encode(),
            headers=active.write_headers(),
        )
        assert status == 400
