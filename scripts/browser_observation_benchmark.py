"""Measure one document-local File digest candidate, retaining all production DOM reads.

This is an isolated benchmark candidate, never a production cache. The baseline
complete tick/pump loop and independent target-value oracle run unchanged.
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
import time
from pathlib import Path

import browser_performance_baseline as baseline
from browser_wait_schedule_benchmark import CpuRecorder
from playwright.sync_api import sync_playwright

from career_evidence_graph import application_worker, hosted_ats

DIGEST = """const sha=file ? Array.from(new Uint8Array(await crypto.subtle.digest(
     'SHA-256',await file.arrayBuffer())),b=>b.toString(16).padStart(2,'0')).join('') : '';"""
CACHED = "const sha=file ? await fileDigest(file) : '';"
assert hosted_ats.INSPECT_HOSTED.count(DIGEST) == 1
CANDIDATE = """() => {
 const hashes = new WeakMap();
 const stats = {hits:0,misses:0};
 const fileDigest = async file => {
   if (hashes.has(file)) { stats.hits++; return hashes.get(file); }
   stats.misses++;
   const hash = Array.from(new Uint8Array(await crypto.subtle.digest(
     'SHA-256', await file.arrayBuffer())), b=>b.toString(16).padStart(2,'0')).join('');
   hashes.set(file, hash);
   return hash;
 };
 return {inspect:INSPECT, stats};
}""".replace("INSPECT", hosted_ats.INSPECT_HOSTED.replace(DIGEST, CACHED))


class DigestCandidate:
    """Keep handles private to this owner/context/page and invalidate on document events."""

    def __init__(self, context):
        self.context = context
        self.handles = {}
        self.stale = set()
        self.registered = set()
        self.reads = 0

    def inspect(self, page, generic):
        if page.context is not self.context:
            raise ValueError("Candidate owner/context mismatch")
        if page not in self.registered:
            self.registered.add(page)
            page.on(
                "framenavigated",
                lambda frame: self.stale.add(page) if frame is page.main_frame else None,
            )
            page.on("close", lambda *_: self.stale.add(page))
            page.on("crash", lambda *_: self.stale.add(page))
        if page in self.stale:
            if old := self.handles.pop(page, None):
                old.dispose()
            self.stale.discard(page)
        if page not in self.handles:
            self.handles[page] = page.evaluate_handle(CANDIDATE)
        self.reads += 1
        return self.handles[page].evaluate("(entry, generic) => entry.inspect(generic)", generic)

    def statistics(self):
        return [handle.evaluate("entry => entry.stats") for handle in self.handles.values()]

    def close(self):
        for handle in self.handles.values():
            handle.dispose()
        self.handles.clear()


class ObservedPage:
    def __init__(self, page, candidate):
        self.page, self.candidate = page, candidate

    def __getattr__(self, name):
        return getattr(self.page, name)

    def evaluate(self, expression, argument):
        assert expression == hosted_ats.INSPECT_HOSTED
        return self.candidate.inspect(self.page, argument)


class MeasuredBrowser:
    def __init__(self, browser):
        self.browser = browser
        self.observers = {}
        self.stats = []
        self.file_oracles = []
        self.expected_file = b""

    def new_context(self, **kwargs):
        context = self.browser.new_context(**kwargs)
        observer = DigestCandidate(context)
        self.observers[context] = observer
        parent = self

        class Context:
            def __getattr__(self, name):
                return getattr(context, name)

            def close(self):
                for page in context.pages:
                    actual = page.locator("input[type=file]").evaluate(
                        """async e => {const file=e.files[0];
                        return file ? {size:file.size, sha:Array.from(new Uint8Array(
                          await crypto.subtle.digest('SHA-256', await file.arrayBuffer())),
                          b=>b.toString(16).padStart(2,'0')).join('')} : {size:0,sha:''};}"""
                    )
                    assert actual == {
                        "size": len(parent.expected_file),
                        "sha": hashlib.sha256(parent.expected_file).hexdigest()
                        if parent.expected_file
                        else "",
                    }
                    parent.file_oracles.append(actual)
                parent.stats.extend(observer.statistics())
                observer.close()
                context.close()
                parent.observers.pop(context)

        return Context()


def synthetic_pdf(file_bytes):
    prefix = b"%PDF-1.4 Synthetic observation only\n"
    return prefix + b"0" * max(0, file_bytes - len(prefix))


def summary(values):
    return {
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
    }


def validate_lifecycle(browser, fixture):
    """Read-only candidate checks on new synthetic pages; no worker actions are replayed."""
    context = browser.new_context(service_workers="block")
    context.set_default_timeout(5000)
    context.route("**/*", lambda route: route.fulfill(status=200, body=fixture(10)))
    context.route_web_socket("**/*", lambda route: route.close())
    other = browser.new_context(service_workers="block")
    candidate = DigestCandidate(context)
    try:
        page = context.new_page()
        page.goto(baseline.URL, wait_until="domcontentloaded")

        def select_file(value):
            page.evaluate(
                """value => {const transfer=new DataTransfer();transfer.items.add(
                  new File([value], 'same-name.pdf', {type:'application/pdf',lastModified:42}));
                  document.querySelector('input[type=file]').files=transfer.files;}""",
                value,
            )

        select_file("abc")
        first = candidate.inspect(page, True)
        repeated = candidate.inspect(page, True)
        first_file = next(f for f in first["fields"] if f["type"] == "file")
        assert first_file["file_sha256"] == hashlib.sha256(b"abc").hexdigest()
        assert first == repeated
        assert candidate.statistics() == [{"hits": 1, "misses": 1}]
        select_file("def")
        replaced = candidate.inspect(page, True)
        replaced_file = next(f for f in replaced["fields"] if f["type"] == "file")
        assert replaced_file["filename"] == first_file["filename"]
        assert replaced_file["file_sha256"] == hashlib.sha256(b"def").hexdigest()
        page.evaluate(
            """() => {const old=document.querySelector('input[type=email]');
             const fresh=old.cloneNode();fresh.value='changed@example.invalid';
             old.replaceWith(fresh);
             document.querySelector('select option:last-child').textContent='Austria';}"""
        )
        dynamic = candidate.inspect(page, True)
        assert next(f for f in dynamic["fields"] if f["type"] == "email")["value"] == (
            "changed@example.invalid"
        )
        assert next(f for f in dynamic["fields"] if f["type"] == "select")["options"] == ["Austria"]
        page.reload(wait_until="domcontentloaded")
        reloaded = candidate.inspect(page, True)
        assert page.url == baseline.URL
        assert next(f for f in reloaded["fields"] if f["type"] == "file")["file_sha256"] == ""
        assert candidate.statistics() == [{"hits": 0, "misses": 0}]
        sibling = context.new_page()
        sibling.goto(baseline.URL, wait_until="domcontentloaded")
        candidate.inspect(sibling, True)
        assert candidate.statistics() == [{"hits": 0, "misses": 0}, {"hits": 0, "misses": 0}]
        unrelated = other.new_page()
        try:
            candidate.inspect(unrelated, True)
        except ValueError as error:
            assert str(error) == "Candidate owner/context mismatch"
        else:
            raise AssertionError("A different owner/context was accepted")
        return {
            "same_file_hit": True,
            "replacement_same_name_size_mtime_miss": True,
            "control_replacement_and_option_changes_fresh": True,
            "same_url_new_document_invalidates": True,
            "different_owner_context_rejected": True,
            "different_page_fresh_cache": True,
            "scope": "main-frame handle per owner/context/page; no control reference cache",
        }
    finally:
        candidate.close()
        context.close()
        other.close()


def pressure_observations(browser, fixture, pairs):
    """5 MiB is outside the 700 KB résumé gate: observe-only stress, never worker input."""
    rows = []
    expected_sha = hashlib.sha256(bytes(5 * 1024 * 1024)).hexdigest()
    for pair in range(1, pairs + 1):
        arms = ("control", "candidate") if pair % 2 else ("candidate", "control")
        for position, variant in enumerate(arms, 1):
            context = browser.new_context(service_workers="block")
            context.set_default_timeout(5000)
            context.route("**/*", lambda route: route.fulfill(status=200, body=fixture(10)))
            context.route_web_socket("**/*", lambda route: route.close())
            candidate = DigestCandidate(context)
            try:
                page = context.new_page()
                page.goto(baseline.URL, wait_until="domcontentloaded")
                page.evaluate(
                    """size => {const transfer=new DataTransfer();transfer.items.add(
                      new File([new Uint8Array(size)], 'stress-only.pdf'));
                      document.querySelector('input[type=file]').files=transfer.files;}""",
                    5 * 1024 * 1024,
                )
                expected = hosted_ats.observe(page, baseline.JOB)
                assert (
                    next(f for f in expected["fields"] if f["type"] == "file")["file_sha256"]
                    == expected_sha
                )
                observed = ObservedPage(page, candidate) if variant == "candidate" else page
                wall, cpu = time.perf_counter(), time.process_time()
                for _ in range(36):
                    assert hosted_ats.observe(observed, baseline.JOB) == expected
                elapsed, used = time.perf_counter() - wall, time.process_time() - cpu
                rows.append(
                    {
                        "pair": pair,
                        "variant": variant,
                        "position": position,
                        "file_mib": 5,
                        "stress_only": True,
                        "full_worker_cycle": False,
                        "observations": 36,
                        "elapsed_ms": elapsed * 1000,
                        "python_cpu_ms": used * 1000,
                        "digest_stats": candidate.statistics(),
                    }
                )
            finally:
                candidate.close()
                context.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--file-mib", type=float, nargs="+", default=[0, 0.25])
    args = parser.parse_args()
    if not args.cdp_url.startswith("http://127.0.0.1:") or not 5 <= args.pairs <= 20:
        parser.error("Use an explicitly owned loopback CDP endpoint and at least five pairs")
    if any(size not in {0, 0.25} for size in args.file_mib):
        parser.error(
            "Worker inputs accept 0/0.25 MiB; 5 MiB runs separately as observe-only stress"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    original_service = application_worker.WorkerService
    original_fixture, original_observe = baseline.fixture, hosted_ats.observe
    recorder = CpuRecorder()
    cases = []
    metadata = {
        "schema_version": "browser-observation-paired/v1",
        "synthetic_only": True,
        "real_application_resumed": False,
        "candidate": "document-local File-object SHA WeakMap",
        "production_changed": False,
        "python": sys.version,
        "platform": platform.platform(),
        "playwright": importlib.metadata.version("playwright"),
        "source_hashes": {
            str(p.relative_to(baseline.CHECKOUT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                baseline.CHECKOUT / "scripts/browser_performance_baseline.py",
                baseline.CHECKOUT / "scripts/browser_wait_schedule_benchmark.py",
                *sorted((baseline.CHECKOUT / "src/career_evidence_graph").rglob("*.py")),
            ]
        },
        "candidate_js_sha256": hashlib.sha256(CANDIDATE.encode()).hexdigest(),
        "boundary": (
            "tick/pump to 12 verified fields before upload; all scans and authorization retained"
        ),
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url)
            metadata["browser_version"] = browser.version
            measured = MeasuredBrowser(browser)
            for mib in args.file_mib:
                payload = synthetic_pdf(int(mib * 1024 * 1024))
                encoded = base64.b64encode(payload).decode()

                class Service(original_service):
                    def request(self, operation, body, _encoded=encoded):
                        if operation == "prepare":
                            body = {
                                **body,
                                "jobs": [{**j, "file_base64": _encoded} for j in body["jobs"]],
                            }
                        return super().request(operation, body)

                application_worker.WorkerService = Service

                def fixture(size, _mib=mib, _encoded=encoded):
                    html = original_fixture(size)
                    if _mib:
                        html += (
                            "<script>const bytes=Uint8Array.from(atob("
                            + json.dumps(_encoded)
                            + "),c=>c.charCodeAt(0));"
                        )
                        html += (
                            "const transfer=new DataTransfer();transfer.items.add(new File([bytes],"
                            " 'synthetic.pdf', {type:'application/pdf'}));"
                            "document.querySelector('input[type=file]').files=transfer.files;</script>"
                        )
                    return html

                baseline.fixture = fixture
                for pair in range(1, args.pairs + 1):
                    arms = ("control", "candidate") if pair % 2 else ("candidate", "control")
                    for position, variant in enumerate(arms, 1):

                        def observe(page, job, _variant=variant):
                            if _variant == "candidate":
                                observer = measured.observers[page.context]
                                return original_observe(ObservedPage(page, observer), job)
                            return original_observe(page, job)

                        hosted_ats.observe = observe
                        measured.expected_file = payload if mib else b""
                        first, stats_start = len(recorder.rows), len(measured.stats)
                        case = baseline.run_worker_case(
                            measured,
                            recorder,
                            args.output / f"file-{mib}-pair-{pair}-{variant}",
                            pair,
                            main_loop_pump=True,
                        )
                        spans = recorder.rows[first:]
                        for row in spans:
                            row.update(file_mib=mib, pair=pair, variant=variant, position=position)
                        cycle = next(
                            x for x in spans if x["stage"] == "worker_verified_fields_cycle"
                        )
                        observations = [x for x in spans if x["stage"] == "worker_observe"]
                        cases.append(
                            {
                                **case,
                                "file_mib": mib,
                                "pair": pair,
                                "variant": variant,
                                "position": position,
                                "elapsed_ms": cycle["elapsed_ms"],
                                "python_cpu_ms": cycle["worker_cpu_ms"],
                                "observe_count": len(observations),
                                "observe_total_ms": sum(x["elapsed_ms"] for x in observations),
                                "digest_stats": measured.stats[stats_start:],
                                "file_oracle": measured.file_oracles[-1],
                            }
                        )
            metadata["lifecycle"] = validate_lifecycle(browser, original_fixture)
            hosted_ats.observe = original_observe
            metadata["pressure_observe_only"] = pressure_observations(
                browser, original_fixture, args.pairs
            )
            metadata["result"] = "passed"
    except Exception as error:
        metadata.update(result="error", error=str(error), error_type=type(error).__name__)
        raise
    finally:
        application_worker.WorkerService = original_service
        baseline.fixture, hosted_ats.observe = original_fixture, original_observe
        metadata["cases"] = cases
        metadata["source_unchanged"] = all(
            hashlib.sha256((baseline.CHECKOUT / p).read_bytes()).hexdigest() == h
            for p, h in metadata["source_hashes"].items()
        )
        comparisons = []
        for mib in args.file_mib:
            a = [x for x in cases if x["file_mib"] == mib and x["variant"] == "control"]
            b = [x for x in cases if x["file_mib"] == mib and x["variant"] == "candidate"]
            if len(a) == len(b) == args.pairs:
                differences = [
                    next(x["elapsed_ms"] for x in a if x["pair"] == i)
                    - next(x["elapsed_ms"] for x in b if x["pair"] == i)
                    for i in range(1, args.pairs + 1)
                ]
                control, candidate = (
                    summary([x["elapsed_ms"] for x in a]),
                    summary([x["elapsed_ms"] for x in b]),
                )
                comparisons.append(
                    {
                        "file_mib": mib,
                        "stress_only": mib == 5,
                        "control_ms": control,
                        "candidate_ms": candidate,
                        "paired_saving_ms": summary(differences),
                        "min_saving_exceeds_same_version_ranges": min(differences)
                        > max(control["range"], candidate["range"]),
                        "control_observe_ms": summary([x["observe_total_ms"] for x in a]),
                        "candidate_observe_ms": summary([x["observe_total_ms"] for x in b]),
                    }
                )
        metadata["comparisons"] = comparisons
        (args.output / "report.json").write_text(json.dumps(metadata, indent=2) + "\n")
        (args.output / "spans.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in recorder.rows)
        )
    print(json.dumps(comparisons, indent=2))


if __name__ == "__main__":
    main()
