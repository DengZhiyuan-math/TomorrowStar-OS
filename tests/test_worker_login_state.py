"""The worker keeps logins between runs, and a closed page's request never stops it."""

from playwright.sync_api import Error

from career_evidence_graph.application_worker_browser import _abort
from career_evidence_graph.cua_driver import LOGIN_STATE, load_login_state, save_login_state


def test_login_state_round_trips_and_ignores_a_damaged_file(tmp_path):
    assert load_login_state(tmp_path) is None

    class Context:
        def storage_state(self):
            return {"cookies": [{"name": "session", "value": "x"}], "origins": []}

    save_login_state(tmp_path, Context())
    assert load_login_state(tmp_path)["cookies"][0]["name"] == "session"
    (tmp_path / LOGIN_STATE).write_text("{")
    assert load_login_state(tmp_path) is None


def test_abort_of_a_closed_page_request_is_not_an_error():
    class Route:
        def abort(self, code):
            raise Error("Target page, context or browser has been closed")

    _abort(Route())
