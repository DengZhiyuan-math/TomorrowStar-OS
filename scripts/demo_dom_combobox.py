"""Demonstrate DOM-first readonly selection through a synthetic durable worker.

Supply a newly owned loopback CDP endpoint. Chrome startup and native Cua latency
are outside this measurement. No native Cua client, real ATS, model, upload or
Submit is used. Each case stops after independently verified fields, before upload.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import statistics
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHECKOUT / "src"))

from browser_performance_baseline import Recorder  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from career_evidence_graph import hosted_ats  # noqa: E402
from career_evidence_graph.application_worker import WorkerService, start_run  # noqa: E402
from career_evidence_graph.application_worker_browser import ApplicationRunner  # noqa: E402
from career_evidence_graph.career_portal_data import ApplicationStore  # noqa: E402

URL = "https://careers.example.test/jobs/dom-readonly"
HTML = """<!doctype html><title>Synthetic Careers</title><h1>Engineer</h1><form>
<label>Full name *<input required></label>
<label>Email *<input type='email' required></label>
<label>Application country *<input role='combobox' readonly required
  aria-controls='countries' aria-expanded='false'></label>
<div role='listbox' id='countries' hidden></div>
<label>Resume *<input type='file' name='resume' required></label>
<button type='submit'>Submit</button></form><script>
window.domActions=[];
const combo=document.querySelector('[role=combobox]');
const list=document.getElementById('countries');
combo.onclick=()=>{
  window.domActions.push('open');combo.ariaExpanded='true';list.hidden=false;
  setTimeout(()=>{
    list.innerHTML="<div role='option'>Switzerland</div>"+
      "<div role='option' style='display:none'>Switzerland</div>";
    list.querySelector('[role=option]').onclick=()=>{
      window.domActions.push('choose');combo.value='Switzerland';
      combo.ariaExpanded='false';list.hidden=true;
    };
  },80);
};
document.querySelector('form').onsubmit=e=>{e.preventDefault();throw Error('No Submit');};
</script>"""


class NoNativeMutation:
    """A refusal probe, not a simulated Cua timing implementation."""

    click_route = "dom_event"

    def __init__(self):
        self.fill_calls = 0

    def new_page(self, context, *, keep_visible=False):
        return context.new_page()

    def fill(self, *args, **kwargs):
        self.fill_calls += 1
        raise AssertionError("Supported DOM dropdown must not invoke native filling")


def run_case(browser, recorder, destination, index):
    recorder.case = {"repeat": index, "phase": "warmup" if index == 0 else "measured"}
    with tempfile.TemporaryDirectory(prefix="ts-dom-dropdown-case-", dir="/private/tmp") as tmp:
        root = Path(tmp)
        applications = root / "applications"
        applications.mkdir()
        service = WorkerService(
            ApplicationStore(applications), root / "worker", live=True, generic=True
        )
        service.spawn = lambda: None
        application = service.store.applications.create_application(
            {
                "company": "Synthetic",
                "role_title": "Engineer",
                "status": "drafting",
                "url": URL,
                "application_strategy": "batch",
            }
        )
        service.request(
            "prepare",
            {
                "jobs": [
                    {
                        "application_id": application["id"],
                        "revision": application["revision"],
                        "country": "CHE",
                        "filename": "synthetic.pdf",
                        "file_base64": base64.b64encode(b"%PDF-1.4 Synthetic only").decode(),
                    }
                ]
            },
        )
        expected = {
            "Full name": "Synthetic Person",
            "Email": "synthetic@example.invalid",
            "Application country": "Switzerland",
        }
        for question, value in expected.items():
            service.store.answers.put_answer(
                {"question": question, "value": value, "scope": {}, "state": "confirmed"}
            )
        context = browser.new_context(service_workers="block", offline=True)
        context.set_default_timeout(5000)
        start_run(service.store)
        service.request("resume", {"controller": "synthetic-dom-demo"})
        probe = NoNativeMutation()
        runner = ApplicationRunner(service.store, context, cua=probe)
        counts, sent, blocked = Counter(), [], []

        def intercept(route):
            class SyntheticRoute:
                request = route.request

                def continue_(self):
                    sent.append({"url": self.request.url, "method": self.request.method})
                    if self.request.url == URL and self.request.method == "GET":
                        route.fulfill(status=200, content_type="text/html", body=HTML)
                    else:
                        route.abort()

                def abort(self, reason):
                    blocked.append({"url": self.request.url, "method": self.request.method})
                    route.abort(reason)

            runner._live_guard(SyntheticRoute())

        context.route("**/*", intercept)
        for owner, name in (
            (runner, "observe"),
            (runner, "authorize"),
            (runner, "persist"),
            (service.store, "resolve"),
        ):
            original = getattr(owner, name)

            def traced(*args, _original=original, _name=name, **kwargs):
                counts[_name] += 1
                return recorder.run(_name, lambda: _original(*args, **kwargs))

            setattr(owner, name, traced)

        current, ticks = None, 0

        def cycle():
            nonlocal current, ticks
            for index in range(1, 8):
                ticks = index
                recorder.run("worker_iteration", lambda: (runner.tick(), runner.pump()))
                current = service.store.load()["jobs"][0]
                fills = [o for o in current["observations"] if o.get("verified")]
                if len(fills) == 3:
                    return
                if current["status"] not in {"queued", "filling"}:
                    raise AssertionError((current["status"], current["reason"]))
            raise AssertionError("Worker failed to verify three synthetic fields")

        try:
            recorder.run("complete_synthetic_fields_entry", cycle)
            page = runner.pages[application["id"]]
            observed = recorder.run(
                "independent_final_readback", lambda: hosted_ats.observe(page, current)
            )
            values = {field["question"]: field["value"] for field in observed["fields"]}
            assert all(values[question] == value for question, value in expected.items())
            assert current["intent"] is None
            assert not any(o.get("action") == "upload" for o in current["observations"])
            dropdown = next(
                o
                for o in current["observations"]
                if o.get("intent", {}).get("fact") == "question:application country"
            )
            assert dropdown["executor"] == "playwright" and dropdown["input_route"] == "dom"
            assert dropdown["intent"]["answer_ref"]["revision"]
            actions = page.evaluate("window.domActions")
            assert actions == ["open", "choose"] and probe.fill_calls == 0
            assert all(request["method"] == "GET" for request in sent)
            return {
                **recorder.case,
                "outcome": "fields_verified_before_upload",
                "worker_ticks": ticks,
                "worker_calls": dict(counts),
                "dom_actions": actions,
                "native_fill_calls": probe.fill_calls,
                "readback_verified": True,
                "intent_bound": True,
                "sent_synthetic_requests": sent,
                "blocked_requests": blocked,
            }
        finally:
            service.request("pause", {"controller": "synthetic-dom-demo"})
            context.close()
            destination.mkdir()
            (destination / "worker-state.json").write_bytes(service.store.path.read_bytes())
            if service.store.measurements.path.exists():
                (destination / "measurements.jsonl").write_bytes(
                    service.store.measurements.path.read_bytes()
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if not args.cdp_url.startswith("http://127.0.0.1:") or not 5 <= args.repetitions <= 20:
        parser.error("Require a newly owned loopback CDP endpoint and 5–20 repetitions")
    args.output.mkdir(parents=True, exist_ok=False)
    recorder = Recorder()
    report = {
        "schema_version": "dom-readonly-combobox-demo/v1",
        "utc": datetime.now(UTC).isoformat(),
        "synthetic_only": True,
        "real_applications_resumed": False,
        "native_cua_latency_measured": False,
        "boundary": (
            "Actual DOM worker with a native mutation refusal probe; no simulated native timing"
        ),
        "outcome_boundary": (
            "Complete prepare/resume/field entry, paused before upload and final review"
        ),
        "timing_boundary": "Inclusive stages; startup and independent final readback are separate",
        "playwright": importlib.metadata.version("playwright"),
        "source_hashes": {
            str(path.relative_to(CHECKOUT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                CHECKOUT / "src/career_evidence_graph/application_worker_browser.py",
                CHECKOUT / "src/career_evidence_graph/hosted_ats.py",
                CHECKOUT / "src/career_evidence_graph/application_worker.py",
                CHECKOUT / "scripts/browser_performance_baseline.py",
            ]
        },
        "cases": [],
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url)
            report["browser_version"] = browser.version
            for index in range(args.repetitions + 1):
                report["cases"].append(
                    run_case(browser, recorder, args.output / f"case-{index}", index)
                )
        report["result"] = "ok"
    except Exception as error:
        report.update(result="error", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report["source_hashes_after"] = {
            name: hashlib.sha256((CHECKOUT / name).read_bytes()).hexdigest()
            for name in report["source_hashes"]
        }
        report["source_unchanged"] = report["source_hashes_after"] == report["source_hashes"]
        if not report["source_unchanged"]:
            report["result"] = "source_changed"
        measured = [
            row["elapsed_ms"]
            for row in recorder.rows
            if row["phase"] == "measured"
            and row["stage"] == "complete_synthetic_fields_entry"
            and row["result"] == "ok"
        ]
        report["entry_elapsed_ms"] = {
            "n": len(measured),
            "median": statistics.median(measured) if measured else None,
            "min": min(measured, default=None),
            "max": max(measured, default=None),
        }
        (args.output / "demo.json").write_text(json.dumps(report, indent=2) + "\n")
        (args.output / "stages.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in recorder.rows)
        )
        print(
            json.dumps(
                {
                    "result": report["result"],
                    "output": str(args.output),
                    "timing": report["entry_elapsed_ms"],
                }
            )
        )
    if report["result"] != "ok":
        raise RuntimeError("Demo evidence is incomplete or the measured source changed")


if __name__ == "__main__":
    main()
