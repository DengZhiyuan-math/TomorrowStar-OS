"""Recognize saved jobs without repeating the full application scan per row."""

from test_application_recommendations import recommendation_store as recommendation_store

from career_evidence_graph import application_recommendations as recommendations


def test_snapshot_recognizes_existing_jobs_with_one_call_scoped_identity_index(
    recommendation_store, monkeypatch
):
    store = recommendation_store
    urls = [f"https://www.linkedin.com/jobs/view/{10000 + index}" for index in range(10)]
    store.import_messages(
        [{"message_id": "ten-jobs", "body_text": "Ten recommendations.", "links": urls}],
        [{"message_id": "ten-jobs", "url": url} for url in urls],
    )
    expected = {}
    for index, url in enumerate(urls):
        record = store.applications.create_application(
            {
                "company": f"Saved {index}",
                "role_title": "Engineer",
                "status": "drafting",
                "url": url + "?trk=saved",
                "notes": "Keep the saved human wording.",
            }
        )
        expected[url] = record["id"]
    for index in range(10):
        store.applications.create_application(
            {"company": f"Other {index}", "role_title": "Engineer", "status": "drafting"}
        )
    before = {
        path: path.read_bytes()
        for folder in (store.root, store.applications.root)
        for path in folder.rglob("*")
        if path.is_file()
    }
    original = recommendations.recommendation_key
    calls = []

    def measured(url):
        calls.append(url)
        return original(url)

    monkeypatch.setattr(recommendations, "recommendation_key", measured)
    rows = store.snapshot()["recommendations"]

    assert {row["url"]: row["existing_application"]["id"] for row in rows} == expected
    assert len(calls) <= 100
    assert {path: path.read_bytes() for path in before} == before
