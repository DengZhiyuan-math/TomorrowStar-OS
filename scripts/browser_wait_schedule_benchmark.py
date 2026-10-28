"""Pair only the old fixed pump and current busy/idle scheduling on owned synthetic CDP.

Reuse the baseline's complete 12-field production tick/pump cycle and oracle.
The control replaces only pump with the immutable pre-change method. Every
other production method is identical in both arms. No upload or Submit is run.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

from browser_performance_baseline import CHECKOUT, URL, Recorder, fixture, run_worker_case
from playwright.sync_api import sync_playwright

from career_evidence_graph import application_worker_browser as production
from career_evidence_graph.application_worker import WorkerService, start_run
from career_evidence_graph.career_portal_data import ApplicationStore


class CpuRecorder(Recorder):
    def run(self, stage, callback, **facts):
        before = time.process_time_ns()
        index = self.next_span + 1
        try:
            return super().run(stage, callback, **facts)
        finally:
            next(row for row in self.rows if row["span_id"] == index)["worker_cpu_ms"] = (
                time.process_time_ns() - before
            ) / 1_000_000


def load_control(path):
    spec = importlib.util.spec_from_file_location("career_evidence_graph.schedule_control", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ApplicationRunner.pump


def summary(values):
    return {
        "n": len(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
    }


def control_cases(browser, runner_class, output, variant):
    """Measure the idle public loop, explicit stop controls and owner maintenance."""
    temporary = tempfile.TemporaryDirectory(prefix="ts-schedule-control-", dir="/private/tmp")
    private = Path(temporary.name)
    apps = private / "applications"
    apps.mkdir(parents=True)
    service = WorkerService(ApplicationStore(apps), private / "runtime", live=True, generic=True)
    service.spawn = lambda: None
    context = browser.new_context(service_workers="block")
    context.route_web_socket("**/*", lambda route: route.close())
    start_run(service.store)
    maintained = []

    class Owner:
        def maintain(self, *, pump):
            maintained.append(time.monotonic())

    runner = runner_class(service.store, context, cua=Owner())
    # Retain Cua's owner-maintenance contract without invoking any real native driver.
    # New-page creation and field actions remain the actual DOM worker methods.
    runner.cua = None
    rows = []
    try:
        for mode in ("idle", "paused", "fault"):
            if mode == "paused":
                app = service.store.applications.create_application(
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
                                "application_id": app["id"],
                                "revision": app["revision"],
                                "country": "CHE",
                                "filename": "synthetic.pdf",
                                "file_base64": base64.b64encode(
                                    b"%PDF-1.4 Synthetic schedule only"
                                ).decode(),
                            }
                        ]
                    },
                )
                service.store.answers.put_answer(
                    {
                        "question": "Native country",
                        "value": "Canada",
                        "scope": {},
                        "state": "confirmed",
                        "source": "synthetic schedule",
                    }
                )

                def intercept(route):
                    class Route:
                        request = route.request

                        def continue_(self):
                            route.fulfill(status=200, content_type="text/html", body=fixture(10))

                        def abort(self, reason):
                            route.abort(reason)

                    runner._live_guard(Route())

                context.route("**/*", intercept)
                service.request("resume", {"controller": "synthetic-schedule"})
                runner.tick()
                fills_before = sum(
                    o.get("action") == "fill"
                    for o in service.store.load()["jobs"][0]["observations"]
                )
                assert fills_before == 1
                began = time.monotonic()
                service.request("pause", {"controller": "synthetic-schedule"})
                runner.pump()
                runner.tick()
                fills_after = sum(
                    o.get("action") == "fill"
                    for o in service.store.load()["jobs"][0]["observations"]
                )
                stop_response_ms = (time.monotonic() - began) * 1000
                paused = service.store.load()
                current = paused["jobs"][0]
                unknown_results = sum(
                    event.get("result") == "unknown" for event in service.store.measurements.read()
                )
                failure_count = sum(job["status"] == "needs_recheck" for job in paused["jobs"])
                assert fills_before == fills_after and paused["control"] == "paused"
                assert current["status"] == "filling" and current["intent"] is None
                assert not paused["worker_error"] and not unknown_results and not failure_count
                (private / "pause-state.json").write_text(json.dumps(paused, indent=2) + "\n")
                rows.append(
                    {
                        "variant": variant,
                        "mode": "pause_response",
                        "elapsed_ms": stop_response_ms,
                        "fills_before": fills_before,
                        "fills_after": fills_after,
                        "unknown_results": unknown_results,
                        "failure_count": failure_count,
                    }
                )
            elif mode == "fault":
                runner.event("synthetic_shared_fault")
            runner.cua = Owner()
            wall, cpu = time.monotonic(), time.process_time()
            loops = 0
            while time.monotonic() - wall < 1:
                runner.tick()
                runner.pump()
                loops += 1
            elapsed, used = time.monotonic() - wall, time.process_time() - cpu
            rows.append(
                {
                    "variant": variant,
                    "mode": mode,
                    "loops": loops,
                    "elapsed_ms": elapsed * 1000,
                    "python_worker_cpu_ms": used * 1000,
                    "python_worker_cpu_percent_of_one_core": used / elapsed * 100,
                    "owner_maintenance_calls": len(maintained),
                    "control": service.store.load()["control"],
                }
            )
            runner.cua = None
        assert all(row.get("loops", 0) <= 5 for row in rows)
        assert rows[2]["owner_maintenance_calls"] > rows[0]["owner_maintenance_calls"]
        assert service.store.load()["control"] == "paused"
    finally:
        context.close()
        shutil.copytree(private, output)
        temporary.cleanup()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--controls-only", action="store_true")
    args = parser.parse_args()
    if not args.cdp_url.startswith("http://127.0.0.1:") or not 5 <= args.pairs <= 20:
        parser.error("Use a separately owned loopback endpoint and 5–20 pairs")
    args.output.mkdir(parents=True, exist_ok=False)
    baseline = args.baseline_root / "src/career_evidence_graph/application_worker_browser.py"
    fixed_pump = load_control(baseline)
    candidate = production.ApplicationRunner

    class Control(candidate):
        pump = fixed_pump

    metadata = {
        "schema_version": "browser-wait-schedule-paired/v1",
        "controls_only": args.controls_only,
        "synthetic_only": True,
        "real_application_resumed": False,
        "python": sys.version,
        "platform": platform.platform(),
        "playwright": importlib.metadata.version("playwright"),
        "baseline_module_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
        "control_pump_source": inspect.getsource(fixed_pump),
        "candidate_pump_source": inspect.getsource(candidate.pump),
        "independent_oracle": (
            "baseline target DOM values, only GET requests, no pending intent, 12 verified fills"
        ),
        "cpu_scope": "Python worker process only; browser and Playwright Node CPU are not included",
        "boundary": (
            "Production tick then pump to fields_verified_before_upload; no upload or Submit"
        ),
        "source_hashes": {
            str(path.relative_to(CHECKOUT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                CHECKOUT / "scripts/browser_performance_baseline.py",
                *sorted((CHECKOUT / "src/career_evidence_graph").rglob("*.py")),
            ]
        },
    }
    recorder = CpuRecorder()
    cases, failures, idle = [], [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url)
            metadata["browser_version"] = browser.version
            for pair in range(1, 1 if args.controls_only else args.pairs + 1):
                arms = ("control", "candidate") if pair % 2 else ("candidate", "control")
                for position, variant in enumerate(arms, 1):
                    production.ApplicationRunner = Control if variant == "control" else candidate
                    first = len(recorder.rows)
                    try:
                        case = run_worker_case(
                            browser,
                            recorder,
                            args.output / f"pair-{pair}-{variant}",
                            pair,
                            main_loop_pump=True,
                        )
                    except Exception as error:
                        failures.append(
                            {
                                "pair": pair,
                                "variant": variant,
                                "error": str(error),
                                "type": type(error).__name__,
                            }
                        )
                        raise
                    finally:
                        for row in recorder.rows[first:]:
                            row.update(pair=pair, variant=variant, pair_position=position)
                    span = next(
                        row
                        for row in recorder.rows[first:]
                        if row["stage"] == "worker_verified_fields_cycle"
                    )
                    cases.append(
                        {
                            **case,
                            "pair": pair,
                            "variant": variant,
                            "position": position,
                            "elapsed_ms": span["elapsed_ms"],
                            "python_worker_cpu_ms": span["worker_cpu_ms"],
                        }
                    )
            production.ApplicationRunner = candidate
            for variant, runner_class in (("control", Control), ("candidate", candidate)):
                idle.extend(
                    control_cases(browser, runner_class, args.output / f"idle-{variant}", variant)
                )
            metadata["result"] = "passed"
    except Exception as error:
        metadata.update(result="error", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        production.ApplicationRunner = candidate
        metadata.update(cases=cases, failures=failures, idle=idle, spans=len(recorder.rows))
        metadata["source_unchanged_through_measurement"] = all(
            hashlib.sha256((CHECKOUT / path).read_bytes()).hexdigest() == fingerprint
            for path, fingerprint in metadata["source_hashes"].items()
        )
        if len(cases) == args.pairs * 2:
            a = [row["elapsed_ms"] for row in cases if row["variant"] == "control"]
            b = [row["elapsed_ms"] for row in cases if row["variant"] == "candidate"]
            deltas = [
                next(
                    r["elapsed_ms"]
                    for r in cases
                    if r["pair"] == pair and r["variant"] == "control"
                )
                - next(
                    r["elapsed_ms"]
                    for r in cases
                    if r["pair"] == pair and r["variant"] == "candidate"
                )
                for pair in range(1, args.pairs + 1)
            ]
            metadata["summary"] = {
                "control_ms": summary(a),
                "candidate_ms": summary(b),
                "paired_saving_ms": summary(deltas),
                "saving_exceeds_both_same_variant_ranges": min(deltas)
                > max(max(a) - min(a), max(b) - min(b)),
                "control_cpu_ms": summary(
                    [r["python_worker_cpu_ms"] for r in cases if r["variant"] == "control"]
                ),
                "candidate_cpu_ms": summary(
                    [r["python_worker_cpu_ms"] for r in cases if r["variant"] == "candidate"]
                ),
            }
        (args.output / "report.json").write_text(json.dumps(metadata, indent=2) + "\n")
        (args.output / "spans.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in recorder.rows)
        )
    print(json.dumps(metadata.get("summary", {}), indent=2))


if __name__ == "__main__":
    main()
