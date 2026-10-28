"""Export continues the adopted analysis qualification, without live reassessment."""

from copy import deepcopy

import pytest
from test_application_flow import application as application
from test_application_flow import wait_for
from test_job_explanations import requirement
from test_pdf_export_flow import export_request, review
from test_pdf_export_flow import reviewed_draft as reviewed_draft

from career_evidence_graph.career_portal_data import PortalDataError


def fixed_delivery(service, task, *, judgment="supported", contract=None, status="adopted"):
    with service.applications.write_lock():
        state = service._load()
        current = service._task(state, task["id"])
        analysis = next(row["result"] for row in current["artifacts"] if row["stage"] == "analysis")
        analysis.update(
            application_id=current["application_id"],
            job_brief={},
            material_packet={},
            inference_result={},
            requirements=[requirement("Fluent English", judgment=judgment, hard=True)],
        )
        if contract is not None:
            handoff = {
                "id": "saved-generation",
                "application_id": current["application_id"],
                "analysis_binding": {"analysis_id": current["analysis_id"]},
                "generation_contract": contract,
                "fixed_inputs_revision": "fixed-inputs",
                "status": status,
            }
            current["experience_handoff"] = deepcopy(handoff)
            service.callbacks["experience_generation"] = lambda _: deepcopy(handoff)
        service._save(state)
        return deepcopy(current)


@pytest.mark.parametrize("contract", [None, "fixed-writing/v1", "content-writing/v1"])
def test_export_reuses_fixed_supported_qualification_without_information_reads(
    reviewed_draft, monkeypatch, contract
):
    service, task, calls = reviewed_draft
    task = fixed_delivery(service, review(service, task), contract=contract)
    information_reads = []
    explanations = []
    original_information = service.information_provider
    service.information_provider = lambda: information_reads.append("live") or {}

    def live_qualification(*args):
        explanations.append("live")
        return {"qualification": {"status": "needs_input"}}

    with monkeypatch.context() as patch:
        patch.setattr(service, "_explanation", live_qualification)
        export_request(service, task)
        assert information_reads == explanations == []
    service.information_provider = original_information
    result = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    assert result["analysis_id"] == task["analysis_id"]
    assert result["draft_sha256"] == task["draft_sha256"]
    assert calls == ["generate", "export"]


@pytest.mark.parametrize("contract", [None, "fixed-writing/v1", "content-writing/v1"])
@pytest.mark.parametrize("judgment", ["unknown", "gap"])
def test_export_keeps_fixed_unknown_or_conflicting_qualification_block(
    reviewed_draft, monkeypatch, contract, judgment
):
    service, task, calls = reviewed_draft
    task = fixed_delivery(service, review(service, task), judgment=judgment, contract=contract)
    monkeypatch.setattr(
        service, "_explanation", lambda *args: {"qualification": {"status": "supported"}}
    )
    before = (service.root / "flow.json").read_bytes()
    with pytest.raises(PortalDataError) as caught:
        export_request(service, task)
    assert caught.value.code == "flow_qualification_required"
    assert (service.root / "flow.json").read_bytes() == before
    assert calls == ["generate"]


@pytest.mark.parametrize("contract", ["fixed-writing/v1", "content-writing/v1"])
def test_export_requires_the_fixed_handoff_to_be_adopted(reviewed_draft, contract):
    service, task, calls = reviewed_draft
    task = fixed_delivery(service, review(service, task), contract=contract, status="writing")
    with pytest.raises(PortalDataError) as caught:
        export_request(service, task)
    assert caught.value.code == "flow_generation_not_adopted"
    assert calls == ["generate"]


@pytest.mark.parametrize("contract", [None, "fixed-writing/v1", "content-writing/v1"])
def test_fixed_reviewed_export_does_not_retrieve_live_inputs_again(reviewed_draft, contract):
    service, task, calls = reviewed_draft
    task = fixed_delivery(service, review(service, task), contract=contract)
    original_provider = service.input_provider
    service.input_provider = lambda _: pytest.fail("Fixed export must reuse its delivered inputs")
    export_request(service, task)
    service.input_provider = original_provider
    result = wait_for(service, task["id"], lambda row: row["status"] == "materials_ready")
    assert result["draft_sha256"] == task["draft_sha256"]
    assert calls == ["generate", "export"]
