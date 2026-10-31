"""A contact-only change rebinds the fixed-template résumé without a template update."""

from career_evidence_graph.application_resume import ApplicationResumeStore


def test_only_a_contact_change_skips_the_template_update():
    old = {"information_library_revision": "old", "jd_revision": "same"}
    assert ApplicationResumeStore._only_contacts_changed(
        old, old | {"information_library_revision": "new"}
    )
    assert not ApplicationResumeStore._only_contacts_changed(
        old, {"information_library_revision": "new", "jd_revision": "other"}
    )
    assert not ApplicationResumeStore._only_contacts_changed(old, old | {"jd_revision": "other"})


def test_a_page_closed_receipt_counts_only_while_the_page_is_closed():
    from career_evidence_graph.application_bound_materials import page_closed_receipt

    receipt = {"page_closed": True, "run_id": "r", "page_id": "p"}
    assert page_closed_receipt(receipt, {"page_open": False})
    assert not page_closed_receipt(receipt, {"page_open": True})
    assert not page_closed_receipt({"run_id": "r"}, {"page_open": False})
