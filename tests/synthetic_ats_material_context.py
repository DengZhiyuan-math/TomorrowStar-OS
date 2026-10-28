"""Trusted delivery for ATS-only fixtures; does not validate real Flow lineage."""

from copy import deepcopy

from career_evidence_graph.application_worker import digest


def supply_synthetic_material_context(service, monkeypatch):
    """Complete the explicit SingleBinding double without bypassing material logic."""
    jobs = service.store.load()["jobs"]
    assert len(jobs) == 1
    job = jobs[0]
    scope = (job["application_id"], job["job_url"], job["file_sha256"])
    application = service.store.applications.get_application(job["application_id"])
    sources = {"items": [], "revision": digest({"items": []})}

    def delivered(applications, _flow_root, current):
        assert applications is service.store.applications
        assert current.get("workflow") == "single"
        assert (current["application_id"], current["job_url"], current["file_sha256"]) == scope
        # These forms request no generated supplement. An absent cover-letter
        # branch is intentional; it is not a successful generation receipt.
        return {"application": deepcopy(application), "sources": deepcopy(sources)}

    monkeypatch.setattr(service.store, "single_material_source_provider", delivered)
