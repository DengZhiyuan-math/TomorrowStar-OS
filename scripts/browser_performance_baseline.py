"""Measure existing browser primitives on isolated synthetic forms, never a real ATS.

The optional Cua protocol adapter is deliberately simulated: its DOM scan/click
times are not native Cua RPC, AX, transport, or computer-use latency measurements.
An externally owned, fresh Chrome CDP endpoint is required; this script never
launches Chrome, reads its existing pages, or attaches a personal profile.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import platform
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHECKOUT / "src"))

from career_evidence_graph import hosted_ats  # noqa: E402
from career_evidence_graph.cua_driver import CuaDriver  # noqa: E402

URL = "https://careers.example.test/jobs/42"
JOB = {"platform": "generic", "job_url": URL, "company": "Synthetic", "role_title": "Engineer"}


def fixture(size: int) -> str:
    fields = "".join(
        f"<label for='text-{i}'>Synthetic field {i} *</label>"
        f"<input id='text-{i}' required value='initial-{i}'>"
        for i in range(size)
    )
    return (
        "<!doctype html><title>Synthetic Careers</title><h1>Engineer</h1><form>"
        "<label>Email *<input type='email' required value='synthetic@example.invalid'></label>"
        "<label>Resume *<input type='file' name='resume' required></label>"
        "<label for='native-country'>Native country *</label>"
        "<select id='native-country' required><option value=''>Choose</option>"
        "<option>Canada</option></select>"
        "<label>Application country *<input role='combobox' aria-expanded='false' "
        "required></label><div role='listbox' hidden>"
        "<div role='option'>Switzerland</div></div>" + fields + "</form><script>"
        "const combo=document.querySelector('[role=combobox]');"
        "const list=document.querySelector('[role=listbox]');"
        "combo.onclick=()=>{combo.ariaExpanded='true';list.hidden=false};"
        "document.querySelector('[role=option]').onclick=()=>{"
        "combo.value='Switzerland';combo.ariaExpanded='false';list.hidden=true};"
        "document.querySelector('form').onsubmit=e=>e.preventDefault();</script>"
    )


class Recorder:
    def __init__(self):
        self.rows = []
        self.case = {}
        self.stack = []
        self.next_span = 0

    def run(self, stage, callback, **facts):
        started = time.perf_counter_ns()
        self.next_span += 1
        row = {
            **self.case,
            "stage": stage,
            "span_id": self.next_span,
            "parent_span": self.stack[-1] if self.stack else None,
            **facts,
        }
        self.stack.append(self.next_span)
        try:
            result = callback()
        except Exception as error:
            row.update(result="error", error_type=type(error).__name__, error=str(error)[:500])
            raise
        else:
            row["result"] = "ok"
            return result
        finally:
            row["elapsed_ms"] = (time.perf_counter_ns() - started) / 1_000_000
            self.rows.append(row)
            self.stack.pop()


class CountedPage:
    """Count only direct production Page.evaluate calls; no claim about CDP frames."""

    def __init__(self, page, recorder):
        self.page, self.recorder = page, recorder
        self.evaluate_calls = 0

    def __getattr__(self, name):
        return getattr(self.page, name)

    def evaluate(self, *args):
        self.evaluate_calls += 1
        return self.recorder.run("page_evaluate", lambda: self.page.evaluate(*args))


class SimulatedCuaClient:
    """Structural CuaDriver protocol double, executing only this synthetic DOM."""

    def __init__(self, page, recorder):
        self.page, self.recorder = page, recorder
        self.calls = Counter()

    def call(self, name, arguments, **_):
        self.calls[name] += 1
        return self.recorder.run("simulated_rpc_" + name, lambda: self._call(name, arguments))

    def _call(self, name, arguments):
        if name == "list_windows":
            return {"windows": [{"pid": 42, "window_id": 7}]}
        if name == "get_browser_state" and "snapshot_format" not in arguments:
            return {
                "binding_quality": "exact",
                "endpoint_access_class": "driver_owned",
                "mutation_allowed": True,
                "target_id": "synthetic-target",
                "tabs": [{"url": self.page.url, "tab_id": "synthetic-tab"}],
            }
        if name == "get_browser_state":
            refs = self.page.evaluate("""() => [...document.querySelectorAll(
              'input,textarea,select,[role]')].filter(e=>e.getClientRects().length &&
              getComputedStyle(e).visibility!=='hidden').map((e,i)=>{
                e.dataset.syntheticRef='ref-'+i;
                return {ref:'ref-'+i, role:e.getAttribute('role') || e.tagName.toLowerCase(),
                  name:(e.labels?.[0]?.textContent || e.textContent || '').replace(/[*]/g,'')
                    .trim().replace(/\\s+/g,' '),frame:'main',actions:['click']};
              })""")
            return {
                "page": {"url": self.page.url},
                "target_id": "synthetic-target",
                "tab_id": "synthetic-tab",
                "snapshot": {"complete": True},
                "refs": refs,
            }
        if name == "browser_click":
            self.page.locator(f'[data-synthetic-ref="{arguments["ref"]}"]').click()
            return {"ok": True}
        raise ValueError("Unsupported synthetic protocol operation")


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        if row.get("phase") == "measured" and row["result"] == "ok":
            key = (row.get("size"), row.get("file_bytes"), row["stage"])
            groups[key].append(row["elapsed_ms"])
    return [
        {
            "size": size,
            "file_bytes": file_bytes,
            "stage": stage,
            "n": len(values),
            "median_ms": statistics.median(values),
            "min_ms": min(values),
            "max_ms": max(values),
        }
        for (size, file_bytes, stage), values in groups.items()
    ]


def run_case(context, recorder, size, file_bytes, repeat, phase):
    recorder.case = {"size": size, "file_bytes": file_bytes, "repeat": repeat, "phase": phase}
    page = recorder.run("new_page", context.new_page)
    counted = CountedPage(page, recorder)
    blocked_requests = []

    def route(request_route):
        request = request_route.request
        if request.url == URL and request.method == "GET":
            request_route.fulfill(status=200, content_type="text/html", body=fixture(size))
        else:
            blocked_requests.append({"url": request.url, "method": request.method})
            request_route.abort()

    page.route("**/*", route)
    page.route_web_socket("**/*", lambda socket: socket.close())
    try:
        recorder.run("synthetic_navigation", lambda: page.goto(URL, wait_until="load"))
        if file_bytes:
            recorder.run(
                "synthetic_file_setup",
                lambda: page.locator("input[type=file]").set_input_files(
                    {
                        "name": "synthetic.pdf",
                        "mimeType": "application/pdf",
                        "buffer": b"%PDF-1.4\n" + b"x" * (file_bytes - 9),
                    }
                ),
            )

        observation = recorder.run("observe_initial", lambda: hosted_ats.observe(counted, JOB))
        assert len(observation["fields"]) == size + 4
        by_question = {field["question"]: field for field in observation["fields"]}
        for kind, question, value in (
            ("text", "Synthetic field 0", "Synthetic updated"),
            ("select", "Native country", "Canada"),
            ("combobox", "Application country", "Switzerland"),
        ):
            recorder.run(
                "dom_fill_" + kind,
                lambda q=question, v=value: hosted_ats.fill(counted, by_question[q], v),
            )
            observed = recorder.run(
                "observe_after_" + kind, lambda: hosted_ats.observe(counted, JOB)
            )
            assert (
                next(f["value"] for f in observed["fields"] if f["question"] == question) == value
            )

        page.locator("input[role=combobox]").evaluate("e=>{e.value='';e.ariaExpanded='false'}")
        client = SimulatedCuaClient(page, recorder)
        driver = CuaDriver(client, 42, click_route="dom_event", driver_owned=True, window_id=7)
        recorder.run(
            "cua_driver_fill_simulated_transport",
            lambda: driver.fill(
                counted,
                by_question["Application country"],
                "Switzerland",
                check=lambda: None,
                pump=lambda: None,
            ),
        )
        observed = recorder.run(
            "observe_after_simulated_cua", lambda: hosted_ats.observe(counted, JOB)
        )
        assert (
            next(f["value"] for f in observed["fields"] if f["question"] == "Application country")
            == "Switzerland"
        )
        editable_calls = dict(client.calls)
        page.locator("input[role=combobox]").evaluate(
            "e=>{e.value='';e.ariaExpanded='false';e.readOnly=true}"
        )
        client.calls.clear()
        recorder.run(
            "cua_driver_readonly_fill_simulated_transport",
            lambda: driver.fill(
                counted,
                by_question["Application country"],
                "Switzerland",
                check=lambda: None,
                pump=lambda: None,
            ),
        )
        observed = recorder.run(
            "observe_after_simulated_readonly_cua", lambda: hosted_ats.observe(counted, JOB)
        )
        assert (
            next(f["value"] for f in observed["fields"] if f["question"] == "Application country")
            == "Switzerland"
        )
        file = next(field for field in observed["fields"] if field["type"] == "file")
        expected = (
            hashlib.sha256(b"%PDF-1.4\n" + b"x" * (file_bytes - 9)).hexdigest()
            if file_bytes
            else ""
        )
        assert file["file_sha256"] == expected
        return {
            **recorder.case,
            "evaluate_calls": counted.evaluate_calls,
            "simulated_rpc_calls": dict(client.calls),
            "simulated_editable_rpc_calls": editable_calls,
            "blocked_requests": blocked_requests,
            "readback_verified": True,
            "file_sha256_verified": True,
        }
    finally:
        recorder.run("page_close", page.close)


def run_worker_case(browser, recorder, destination, repeat, size=10, *, main_loop_pump=False):
    """Run real durable worker ticks, stopping after verified fields before upload."""
    from career_evidence_graph.application_worker import WorkerService, start_run
    from career_evidence_graph.application_worker_browser import ApplicationRunner
    from career_evidence_graph.career_portal_data import ApplicationStore

    recorder.case = {"size": size, "file_bytes": 0, "repeat": repeat, "phase": "measured"}
    with tempfile.TemporaryDirectory(prefix="ts-browser-baseline-") as temporary:
        root = Path(temporary)
        apps = root / "applications"
        apps.mkdir()
        service = WorkerService(ApplicationStore(apps), root / "worker", live=True, generic=True)
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
                        "file_base64": base64.b64encode(
                            b"%PDF-1.4 Synthetic baseline only"
                        ).decode(),
                    }
                ]
            },
        )
        answers = [
            ("Email", "synthetic@example.invalid"),
            ("Native country", "Canada"),
            ("Application country", "Switzerland"),
        ]
        answers.extend(
            (f"Synthetic field {index}", f"Updated synthetic {index}") for index in range(size)
        )
        for question, value in answers:
            service.store.answers.put_answer(
                {
                    "question": question,
                    "value": value,
                    "scope": {},
                    "state": "confirmed",
                    "source": "synthetic baseline",
                }
            )
        context = browser.new_context(service_workers="block")
        context.set_default_timeout(5000)
        sent, blocked = [], []
        start_run(service.store)
        service.request("resume", {"controller": "synthetic-baseline"})
        runner = ApplicationRunner(service.store, context)

        def intercept(route):
            class SyntheticRoute:
                request = route.request

                def continue_(self):
                    sent.append({"method": self.request.method, "url": self.request.url})
                    if self.request.url == URL and self.request.method == "GET":
                        route.fulfill(status=200, content_type="text/html", body=fixture(size))
                    else:
                        route.abort()

                def abort(self, reason):
                    blocked.append({"method": self.request.method, "url": self.request.url})
                    route.abort(reason)

            runner._live_guard(SyntheticRoute())

        context.route("**/*", intercept)
        # Timed wrappers delegate to the bound production methods without changing results.
        for owner, name, stage in (
            (runner, "observe", "worker_observe"),
            (runner, "authorize", "worker_authorize"),
            (runner, "persist", "worker_persist"),
            (service.store, "resolve", "worker_resolve"),
        ):
            original = getattr(owner, name)

            def traced(*args, _original=original, _stage=stage, **kwargs):
                return recorder.run(_stage, lambda: _original(*args, **kwargs))

            setattr(owner, name, traced)

        expected_fills = size + 2
        current = None
        ticks = 0

        def iteration():
            recorder.run("worker_tick", runner.tick)
            if main_loop_pump:
                recorder.run("worker_main_loop_pump", runner.pump)

        def cycle():
            nonlocal current, ticks
            for index in range(1, expected_fills + 4):
                ticks = index
                recorder.run("worker_iteration", iteration)
                state = service.store.load()
                current = state["jobs"][0]
                verified = [
                    row
                    for row in current["observations"]
                    if row.get("action") == "fill" and row.get("verified")
                ]
                if len(verified) == expected_fills:
                    return
                if current["status"] not in {"queued", "filling"}:
                    raise AssertionError(
                        f"Synthetic worker stopped: {current['status']} {current.get('reason')}"
                    )
            raise AssertionError("Synthetic worker did not verify expected fields")

        try:
            recorder.run("worker_verified_fields_cycle", cycle)
            assert current["intent"] is None
            assert all(row["method"] == "GET" for row in sent)
            page = runner.pages[application["id"]]
            fields = hosted_ats.observe(page, current)["fields"]
            values = {field["question"]: field["value"] for field in fields}
            assert all(values[question] == value for question, value in answers)
            if main_loop_pump:
                recorder.run("worker_idle_pump", runner.pump)
            return {
                **recorder.case,
                "worker_ticks": ticks,
                "verified_fills": expected_fills,
                "outcome": "fields_verified_before_upload",
                "worker_status": current["status"],
                "main_loop_pump": main_loop_pump,
                "ready_for_review_measured": False,
                "sent_synthetic_requests": sent,
                "blocked_requests": blocked,
            }
        finally:
            service.request("pause", {"controller": "synthetic-baseline"})
            context.close()
            destination.mkdir(parents=True, exist_ok=False)
            if service.store.measurements.path.exists():
                (destination / "measurements.jsonl").write_bytes(
                    service.store.measurements.path.read_bytes()
                )
            (destination / "measurement-summary.json").write_text(
                json.dumps(service.store.measurements.summary(), indent=2) + "\n"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 50, 200])
    parser.add_argument("--file-mib", type=float, nargs="+", default=[0.25, 5])
    parser.add_argument("--runner-cases", type=int, default=5)
    parser.add_argument("--runner-only", action="store_true")
    parser.add_argument("--main-loop-pump", action="store_true")
    args = parser.parse_args()
    if not args.cdp_url.startswith("http://127.0.0.1:"):
        parser.error("Use only a root-owned isolated loopback CDP endpoint")
    if args.repetitions < 5 or any(size < 1 or size > 500 for size in args.sizes):
        parser.error("Require >=5 repetitions and form sizes between 1 and 500")
    if any(size <= 0 or size > 20 for size in args.file_mib):
        parser.error("File sizes must be positive and <=20 MiB")
    if args.runner_cases != 0 and not 5 <= args.runner_cases <= 20:
        parser.error("Use 0 or 5–20 real worker cases")
    args.output.mkdir(parents=True, exist_ok=False)
    recorder, cases = Recorder(), []
    metadata = {
        "schema_version": "browser-performance-baseline/v1",
        "utc": datetime.now(UTC).isoformat(),
        "synthetic_only": True,
        "real_application_resumed": False,
        "python": sys.version,
        "platform": platform.platform(),
        "playwright": importlib.metadata.version("playwright"),
        "repetitions": args.repetitions,
        "sizes": args.sizes,
        "file_mib": args.file_mib,
        "runner_cases": args.runner_cases,
        "runner_only": args.runner_only,
        "main_loop_pump": args.main_loop_pump,
        "worker_variant": "production_tick_then_pump" if args.main_loop_pump else "tick_only",
        "boundary": (
            "CDP real browser; actual DOM worker; no Cua protocol simulation executed"
            if args.runner_only
            else "CDP real browser; simulated Cua protocol, not native RPC latency"
        ),
        "startup_boundary": "Fresh context measured; Chrome cold launch measured separately",
        "timing_boundary": "Inclusive spans: do not add a parent to its nested children",
        "routing_boundary": (
            "Editable combobox is a primitive comparison, not ApplicationRunner routing. "
            "Readonly combobox measures production CuaDriver protocol structure separately. "
            "No ready_for_review or full worker journey outcome is measured."
        ),
        "source_hashes": {
            str(path.relative_to(CHECKOUT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                CHECKOUT / "src/career_evidence_graph/hosted_ats.py",
                CHECKOUT / "src/career_evidence_graph/cua_driver.py",
                CHECKOUT / "src/career_evidence_graph/application_worker_browser.py",
                CHECKOUT / "src/career_evidence_graph/application_worker.py",
                CHECKOUT / "src/career_evidence_graph/worker_measurement.py",
            ]
        },
    }
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = recorder.run(
                "cdp_connect", lambda: playwright.chromium.connect_over_cdp(args.cdp_url)
            )
            metadata["browser_version"] = browser.version
            context = recorder.run(
                "isolated_context_create",
                lambda: browser.new_context(
                    service_workers="block", viewport={"width": 1280, "height": 900}
                ),
            )
            context.set_default_timeout(5000)
            try:
                attachments = [0, *[int(value * 1024 * 1024) for value in args.file_mib]]
                if not args.runner_only:
                    for size in args.sizes:
                        for file_bytes in attachments:
                            cases.append(run_case(context, recorder, size, file_bytes, 0, "warmup"))
                            for repeat in range(1, args.repetitions + 1):
                                cases.append(
                                    run_case(
                                        context, recorder, size, file_bytes, repeat, "measured"
                                    )
                                )
                for repeat in range(1, args.runner_cases + 1):
                    cases.append(
                        run_worker_case(
                            browser,
                            recorder,
                            args.output / f"worker-{repeat}",
                            repeat,
                            main_loop_pump=args.main_loop_pump,
                        )
                    )
            finally:
                recorder.case = {}
                recorder.run("isolated_context_close", context.close)
    except Exception as error:
        metadata.update(result="error", error_type=type(error).__name__, error=str(error))
        raise
    else:
        metadata["result"] = "ok"
    finally:
        result = {
            **metadata,
            "cases": cases,
            "stages": recorder.rows,
            "summary": summarize(recorder.rows),
        }
        (args.output / "baseline.json").write_text(json.dumps(result, indent=2) + "\n")
        (args.output / "stages.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in recorder.rows)
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "result": metadata.get("result"),
                    "cases": len(cases),
                    "stage_records": len(recorder.rows),
                }
            )
        )


if __name__ == "__main__":
    main()
