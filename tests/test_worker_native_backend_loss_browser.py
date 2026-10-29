"""MC-10 C5 rehearsal: the controlled app-server is killed mid-turn (zero model calls).

Same native chain as MC-09 (real Pipeline, Worker, runner, reviewed native candidate,
real CodexAdapter; only the app-server is ``native_return_peer.py``). While its native
``browser_type`` is in flight on the busy Country handler, the peer's whole process
group, including the native driver it spawned, is SIGKILLed. The assertions are the
live C5 ones from ``test_worker_native_live_model_browser.py``. The outbound tap also
checks the real model-facing delivery against the live turn guard.
"""

import json
import os
from pathlib import Path

import pytest
from codex_live_guards import OutboundTap
from test_synthetic_takeover_chain_browser import job
from test_worker_native_chain_browser import (  # noqa: F401 - fixture import
    SLOW_COUNTRY,
    case,
    first_stop,
    native_chain,
)
from test_worker_native_live_model_browser import (
    REPO,
    assert_backend_loss,
    kill_backend_group,
    settle,
)

pytestmark = [
    pytest.mark.worker_browser,
    pytest.mark.skipif(
        os.environ.get("TS_CUA_NATIVE_TEST") != "1", reason="Explicit native Cua opt-in"
    ),
]


@pytest.mark.parametrize("native_chain", [case("chain_tool_unknown", SLOW_COUNTRY)], indirect=True)
def test_killed_controlled_app_server_is_unknown_and_refuses_the_next_dispatch(
    native_chain,  # noqa: F811 - the imported fixture
    tmp_path,
):
    ns = native_chain
    ns.processes, ns.case = [], {}
    tap = OutboundTap(
        ns.adapter,
        tmp_path / "outbound.jsonl",
        temp_root=tmp_path,
        private_roots=[REPO / ".career-evidence"],
        turn_tokens=[REPO, Path.home().name],
    )
    first_stop(ns)
    assert tap.counts.get("turn/start") == 1 and tap.violations == [], tap.blocked
    settle(
        ns,
        lambda: any(row["text"].startswith("native-input-handler-start:") for row in ns.console),
    )
    killed = kill_backend_group(ns)
    try:
        assert_backend_loss(ns, killed)
        assert tap.counts.get("initialize") == 1 and tap.blocked == []
    finally:
        current = job(ns)
        evidence = {
            "case": ns.case,
            "status": current["status"],
            "reason": current.get("reason"),
            "assistance": current.get("assistance"),
            "requests": ns.requests,
            "writes": ns.writes,
            "outbound_counts": tap.counts,
            "outbound_failures": tap.failures,
        }
        (tmp_path / "backend-loss.json").write_text(json.dumps(evidence, indent=2, default=str))
