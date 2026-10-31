"""The worker keeps logins between runs, and a closed page's request never stops it."""

from playwright.sync_api import Error

from career_evidence_graph.application_worker_browser import _abort
from career_evidence_graph.cua_driver import LOGIN_STATE, load_login_state, save_login_state


def test_login_state_round_trips_and_ignores_a_damaged_file(tmp_path):
    assert load_login_state(tmp_path) is None

    class Context:
        def cookies(self):
            return [{"name": "session", "value": "x"}]

    save_login_state(tmp_path, Context())
    assert load_login_state(tmp_path)["cookies"][0]["name"] == "session"
    (tmp_path / LOGIN_STATE).write_text("{")
    assert load_login_state(tmp_path) is None


def test_abort_of_a_closed_page_request_is_not_an_error():
    class Route:
        def abort(self, code):
            raise Error("Target page, context or browser has been closed")

    _abort(Route())


def test_an_overrun_idle_wait_is_not_a_lost_browser(monkeypatch):
    from career_evidence_graph import application_worker_browser as worker

    def overrun(*_args):
        raise Error("owned_browser_read_timeout")

    monkeypatch.setattr(worker, "pump_events", overrun)
    runner = worker.ApplicationRunner.__new__(worker.ApplicationRunner)
    runner.shared_fault, runner.work_progressed, runner.context, events = False, False, None, []
    runner.event = events.append
    runner.pump()
    assert events == []


def test_worker_adopts_a_login_saved_by_the_sign_in_window(tmp_path):
    from career_evidence_graph.cua_driver import sync_login_state

    class Context:
        def __init__(self):
            self.jar = [{"name": "guest", "value": "1"}]

        def add_cookies(self, cookies):
            self.jar += cookies

        def cookies(self):
            return list(self.jar)

    context = Context()
    seen = sync_login_state(tmp_path, context, None)
    signed_in = {"cookies": [{"name": "session", "value": "x"}], "origins": []}
    (tmp_path / LOGIN_STATE).write_text(__import__("json").dumps(signed_in))
    sync_login_state(tmp_path, context, seen - 1)
    names = {c["name"] for c in load_login_state(tmp_path)["cookies"]}
    assert names == {"guest", "session"}
