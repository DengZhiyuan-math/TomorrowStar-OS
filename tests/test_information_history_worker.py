"""Real worker edits retain prior information records."""

import json

from test_application_worker import service as service

from career_evidence_graph.application_information import read_information_history
from career_evidence_graph.application_worker import digest


def test_worker_contact_correction_and_withdrawal_keep_history(service):
    first = service.store.answers.put_answer(
        {"question": "Email", "scope": {}, "state": "confirmed", "value": "old@example.invalid"}
    )
    service.request(
        "library",
        {
            "key": first["key"],
            "revision": digest(first),
            "value": "current@example.invalid",
        },
    )
    current = service.store.answers.get_answer(first["key"])
    service.request(
        "library",
        {
            "key": first["key"],
            "revision": digest(current),
            "withdraw": True,
        },
    )
    history = read_information_history(service.store.answers.root, key=first["key"])
    assert [event["source"] for event in history] == ["answer-correction", "answer-withdrawal"]
    assert all(event["status"] == "applied" for event in history)
    retained = json.loads((service.store.answers.root / history[0]["backup"]).read_bytes())
    assert retained["answers"][first["key"]]["value"] == "old@example.invalid"
    withdrawn = service.store.answers.get_answer(first["key"])
    assert withdrawn["value"] is None
    assert withdrawn["state"] == "missing"
