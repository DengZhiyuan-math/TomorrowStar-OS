"""Mail capture is available through the authenticated existing intake endpoint."""

import json

from test_application_intake import message, ready
from test_career_portal_http import _running_portal
from test_career_portal_http import portal as portal

from career_evidence_graph.application_intake import ApplicationIntakeService
from career_evidence_graph.career_portal_data import ApplicationStore


def test_http_capture_saves_links_without_fetching_jds(portal, tmp_path):
    reads, fetches = [], []

    def reader(directory, **options):
        reads.append(options["page_token"])
        return {
            "status": "readable",
            "emails": [
                message(
                    f"mail-{len(reads)}",
                    links=[f"https://www.linkedin.com/jobs/view/{12345 + len(reads)}"],
                )
            ],
            "provenance": {"next_page_token": "next-page" if len(reads) == 1 else ""},
        }

    def factory(applications, root):
        return ApplicationIntakeService(
            applications, root, reader=reader, fetcher=lambda url: fetches.append(url)
        )

    with _running_portal(
        portal.applications,
        portal.career,
        flow_root=tmp_path / "flow",
        preparation_only=True,
        flow_intake_factory=factory,
    ) as active:
        payload = json.dumps({"capture_only": True, "max_results": 1}).encode()
        assert active.request("POST", "/api/recommendations/refresh", body=payload)[0] == 403
        status, _, raw = active.request(
            "POST",
            "/api/recommendations/refresh",
            body=payload,
            headers=active.write_headers(),
        )
        assert status == 200, raw
        state = ready(active.server.application_intake_service)
        assert state["status"] == "complete"
        assert reads == [None, "next-page"]
        assert len(state["recommendations"]) == 2
        assert fetches == []
        assert ApplicationStore(portal.applications).list_applications() == []
        status, _, _ = active.request(
            "POST",
            "/api/recommendations/refresh",
            body=json.dumps({"capture_only": "yes"}).encode(),
            headers=active.write_headers(),
        )
        assert status == 400
