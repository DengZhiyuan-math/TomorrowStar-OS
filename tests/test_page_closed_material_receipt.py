"""A page-closed receipt switches materials without checking the closed page."""


def test_a_page_closed_receipt_counts_only_while_the_page_is_closed():
    from career_evidence_graph.application_bound_materials import page_closed_receipt

    receipt = {"page_closed": True, "run_id": "r", "page_id": "p"}
    assert page_closed_receipt(receipt, {"page_open": False})
    assert not page_closed_receipt(receipt, {"page_open": True})
    assert not page_closed_receipt({"run_id": "r"}, {"page_open": False})
