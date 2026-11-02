"""Owner maintenance: a terminal loss is logged once and stops; a transient one retries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from career_evidence_graph.career_portal_data import PortalDataError
from career_evidence_graph.cua_driver import OWNER_READ_RETRIES, CuaDriver


class Client:
    def __init__(self):
        self.failed = False
        self.exit_code = None
        self.process = SimpleNamespace(poll=lambda: self.exit_code)


def driver(client, keep_owner):
    return CuaDriver(client, 42, window_id=7, driver_owned=True, keep_owner=keep_owner)


@pytest.mark.parametrize("terminal", ["exited", "failed"])
def test_terminal_owner_loss_is_logged_once_and_stops_maintenance(capsys, terminal):
    """574 identical errors in the real log came from an exited driver re-read each tick."""
    client, reads = Client(), []

    def keep_owner(*, pump):
        reads.append(1)
        raise PortalDataError("cua_handoff_unknown", "control connection lost", 409)

    cua = driver(client, keep_owner)
    if terminal == "exited":
        client.exit_code = 1
    else:
        client.failed = True
    for _ in range(50):
        cua.maintain(pump=lambda: None)
    assert reads == []
    assert cua.owner_lost == ("cua_driver_exited" if terminal == "exited" else "cua_client_failed")
    assert capsys.readouterr().out.count("cua_owner_lost") == 1


def test_a_read_that_fails_the_client_is_terminal_at_once(capsys):
    client = Client()

    def keep_owner(*, pump):
        client.failed = True
        raise PortalDataError("cua_result_unknown", "lost reply", 409)

    cua = driver(client, keep_owner)
    cua.maintain(pump=lambda: None)
    cua.maintain(pump=lambda: None)
    assert cua.owner_lost == "cua_client_failed"
    assert capsys.readouterr().out.count("cua_owner_lost") == 1


def test_transient_owner_read_failures_retry_then_become_terminal(capsys):
    client, outcomes = Client(), []

    def keep_owner(*, pump):
        if outcomes.pop(0):
            raise PortalDataError("cua_refused", "busy", 409)

    cua = driver(client, keep_owner)
    # A recovered read resets the count.
    outcomes.extend([True, True, False])
    for _ in range(2):
        with pytest.raises(PortalDataError):
            cua.maintain(pump=lambda: None)
    cua.maintain(pump=lambda: None)
    assert cua.owner_lost is None
    outcomes.extend([True] * OWNER_READ_RETRIES)
    for _ in range(OWNER_READ_RETRIES - 1):
        with pytest.raises(PortalDataError):
            cua.maintain(pump=lambda: None)
    cua.maintain(pump=lambda: None)
    assert cua.owner_lost == "cua_refused"
    cua.maintain(pump=lambda: None)
    assert outcomes == []
    assert capsys.readouterr().out.count("cua_owner_lost") == 1
