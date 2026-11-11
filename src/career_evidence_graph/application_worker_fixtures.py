"""Isolated loopback Lever and Greenhouse forms; never an employer endpoint."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import shlex
import sys
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from types import SimpleNamespace
from urllib.parse import urlencode

from ._vendor.job_apply_store import atomic_write_json, read_json_object
from .application_automation import _job_identity
from .ats_forms import FORMS

SOURCE_INTAKE_JD = (
    "Company: Synthetic Employer\nTitle: Software Engineer\nRequirements: Python\nunit tests"
)

_FIXTURE_PYTHON = """import json
import sys
from pathlib import Path

if sys.argv[1:] == ["--version"]:
    print("codex-cli synthetic-flow-fixture/1 new_model_calls=0 "
          f"isolated={sys.flags.isolated} bytecode_writes={int(not sys.dont_write_bytecode)}")
    raise SystemExit(0)

try:
    args = sys.argv[1:]
    if not args or args[0] != "exec" or "--json" not in args:
        raise ValueError("Only version and structured analysis/resume exec are supported.")
    schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
    prompt = sys.stdin.read() if args[-1] == "-" else args[-1]
    data = json.loads(prompt.rsplit("\\n", 1)[-1])
    properties = set(schema.get("properties", {}))
    limitation = (
        "SYNTHETIC fixture; new_model_calls=0. Literal source replay only; "
        "no semantic JD or hard-condition interpretation and no real capability assessment."
    )
    if properties == {"excerpts"}:
        start, end = data["range"]["start"], data["range"]["end"]
        fields = data.get("field_ranges") or [{"start": start, "end": end}]
        field = next(row for row in fields if row["start"] < end and start < row["end"])
        first = max(start, field["start"])
        last = min(end, field["end"], first + 160)
        quote = data["text"][first - start:last - start]
        output = {"excerpts": [{"source_id": data["source"]["source_id"],
            "quote": quote, "start": first, "end": last,
            "requirement_indexes": list(range(len(data["requirements"])))}]
            if quote.strip() else []}
    elif properties == {"business_object", "role_understanding", "groups"}:
        job = data
        lines = list(dict.fromkeys(line.strip() for line in job["job_description"].splitlines()
                                   if line.strip()))
        output = {
            "business_object": "Unspecified in literal synthetic fixture",
            "role_understanding": {
                "business_objective": "Unknown: fixture does not interpret business goals.",
                "work_outputs": ["Unassessed: synthetic literal replay only."],
                "methods_role": "Unassessed: literal term matching is not business understanding.",
            },
            "groups": [{
                "label": line, "jd_quote": line, "operator": "all",
                "importance": "required", "hard_condition": False, "weight": 1,
                "weight_reason": "Equal synthetic literal groups; no semantic business weighting.",
                "requirements": [{"text": line, "jd_quote": line}],
            } for line in lines],
        }
    elif properties == {"role_understanding", "requirements", "selected_source_ids",
                      "selection_rationale", "extracted_fields", "limitations"}:
        # A trusted view omits the admission flags the program has already applied.
        eligible = [
            source for source in data["sources"]
            if source.get("available", True) and source.get("match_eligible", True)
            and source.get("resume_eligible") and source.get("rewrite_allowed", True)
            and source.get("attribution") == "User"
        ]
        requirements, selected, seen = [], [], set()
        fixed = data.get("match_requirements")
        requirement_schema = schema["properties"]["requirements"].get("items", {})
        if "$ref" in requirement_schema:
            name = requirement_schema["$ref"].rsplit("/", 1)[-1]
            requirement_schema = schema.get("$defs", {}).get(name, {})
        scopes = requirement_schema.get("properties", {}).get("claim_scope", {}).get("enum", [])
        supported_scope = "personal_completed"
        if scopes and supported_scope not in scopes:
            supported_scope = "documentary" if "documentary" in scopes else "unknown"
        for original in fixed if fixed is not None else data["job"]["job_description"].splitlines():
            text = original["text"] if isinstance(original, dict) else original.strip()
            if not text or text.casefold() in seen:
                continue
            if len(text) > 2000:
                raise ValueError("Synthetic JD lines must contain at most 2000 characters.")
            seen.add(text.casefold())
            source = next(
                (row for row in eligible if text.casefold() in row["text"].casefold()), None
            )
            references = [source["source_id"]] if source else []
            quote = (
                next((line for line in source["text"].splitlines() if line.strip()), "")
                if source else ""
            )
            requirements.append({
                "text": text,
                "importance": original["importance"] if isinstance(original, dict) else "required",
                "hard_condition": (original["hard_condition"]
                                   if isinstance(original, dict) else False),
                "judgment": "supported" if source else "unknown",
                "source_ids": references,
                "citations": [{"source_id": source["source_id"], "quote": quote[:4000]}]
                if source else [],
                "claim_scope": supported_scope if source else "unknown",
                "explanation": "Synthetic literal term appears in the attributed source."
                if source else "Synthetic fixture has no literal personal-source support.",
            })
            if schema.get("title") == "_ControlledOutput":
                requirements[-1]["inference"] = {
                    "requirement_id": original["scoring_framework"]["requirement_id"],
                    "type": "direct",
                    "relation": "supports" if source else "unresolved",
                    "basis": "Synthetic literal replay only; no semantic assessment.",
                    "expression_scope": "Use only the cited recorded work and responsibility."
                    if source else "",
                    "calculation": None,
                }
            for reference in references:
                if reference not in selected:
                    selected.append(reference)
        fields = {
            key: data["job"].get(key) or None for key in ("company", "role_title", "location")
        }
        fields["uncertain_fields"] = [key for key, value in fields.items() if value is None]
        role_understanding = {
            "business_objective": "Unknown: fixture does not interpret business goals.",
            "work_outputs": ["Unassessed: synthetic literal replay only."],
            "methods_role": "Unassessed: literal term matching is not business understanding.",
        }
        if data.get("job_brief"):
            role_understanding = data["job_brief"]["role_understanding"]
        rationale = [
            {"source_id": source_id,
             "business_relevance": "Unassessed: fixture preserves literal source selection only.",
             "evidence_role": "transferable"}
            for source_id in selected
        ]
        output = {"role_understanding": role_understanding,
                  "requirements": requirements, "selected_source_ids": selected,
                  "selection_rationale": rationale,
                  "extracted_fields": fields, "limitations": [limitation]}
    elif properties == {"company", "role_title", "location", "deadline", "salary",
                        "employment_type", "posted_date", "is_full_jd"}:
        allowed_source = (
            "Company: Synthetic Employer\\nTitle: Software Engineer\\n"
            "Requirements: Python\\nunit tests"
        )
        fixed_url = "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"
        if data not in {allowed_source, allowed_source + "\\n" + fixed_url}:
            raise ValueError("JD intake accepts only the declared fixed synthetic source.")
        output = {
            "company": "Synthetic Employer", "role_title": "Software Engineer",
            "location": "", "deadline": "", "salary": "", "employment_type": "",
            "posted_date": "", "is_full_jd": True,
        }
    elif properties == {"items", "limitations"}:
        items = []
        for source in data["sources"][:4]:
            if not source["text"].strip() or len(source["text"]) > 1800:
                raise ValueError("Synthetic resume replay requires a bounded original source.")
            items.append({"source_index": source["source_index"], "text": source["text"]})
        output = {"items": items, "limitations": [limitation]}
    elif properties == {"groups", "limitations"}:
        numbered = data["body_lines"]
        if not isinstance(numbered, list) or not numbered or any(
            not isinstance(row, dict) or set(row) != {"line_number", "text"}
            or type(row["line_number"]) is not int or row["line_number"] != number
            or not isinstance(row["text"], str)
            for number, row in enumerate(numbered, 1)
        ):
            raise ValueError("Synthetic full LaTeX replay requires original body lines.")
        lines = [row["text"] for row in numbered]
        starts = [0]
        for index, line in enumerate(lines):
            if index and line.startswith("\\\\section*{"):
                starts.append(index)
        groups = []
        sources = data["confirmation_context"] + data["sources"]
        for start, end in zip(starts, starts[1:] + [len(lines)]):
            block = lines[start:end]
            heading = block[0].strip()
            section = heading.startswith("\\\\section*{") and heading.endswith("}")
            visible = [line.strip() for line in block[1:] if line.strip()] if section else [
                line.strip() for line in block if line.strip()
            ]
            source = None
            for candidate in sources:
                if not candidate.get("resume_eligible") or not visible:
                    continue
                if candidate.get("source_kind") == "identity" and not section:
                    values = json.loads(candidate["text"]).values()
                    supported = all(line in values for line in visible)
                elif candidate.get("attribution") == "User" and section:
                    supported = all(line in candidate["text"] for line in visible)
                else:
                    supported = False
                if supported:
                    source = candidate
                    break
            groups.append({
                "title": heading[len("\\\\section*{"):-1] if section else "Identity",
                "start_line": start + 1,
                "end_line": end,
                "source_ids": [source["source_id"]] if source else [],
                "latex": "".join(block),
                "disposition": "include" if source else "verify",
                "reason": "Synthetic literal source replay; human review remains required."
                if source else "No literal attributed source; preserve for verification.",
            })
        output = {"groups": groups, "limitations": [limitation]}
    else:
        raise ValueError("Unsupported schema; Gmail and other tool transports are disabled.")
except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
    print("Synthetic fixture rejected input: " + str(error), file=sys.stderr)
    raise SystemExit(2)

print(json.dumps({"type": "synthetic_fixture", "synthetic": True, "new_model_calls": 0}))
print(json.dumps({"type": "structured_result", "result": output}))
"""


def synthetic_cli_text() -> str:
    """Render the fixed literal replay through this process's actual Python interpreter."""
    return (
        "#!/bin/sh\nexec "
        + shlex.quote(sys.executable)
        + " -I -B -c "
        + shlex.quote(_FIXTURE_PYTHON)
        + ' "$@"\n'
    )


BROWSER_FIXTURE_URL = "https://careers.example.test/jobs/browser-synthetic"
BROWSER_UPLOAD_URL = "https://apply.workable.com/synthetic-employer/j/SYNTHETIC1/apply/"
BROWSER_ASHBY_URL = (
    "https://jobs.ashbyhq.com/synthetic/00000000-0000-0000-0000-000000000001/application"
)
_ASHBY_PUBLIC_QUERIES = {
    "ApiJobPosting": (
        "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
        " jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName,"
        " jobPostingId: $jobPostingId) { ...PostingParts } }"
        " fragment PostingParts on JobPosting { id title applicationForm { id } }"
    ),
    "ApiOrganizationFromHostedJobsPageName": (
        "query ApiOrganizationFromHostedJobsPageName($organizationHostedJobsPageName: String!,"
        " $searchContext: OrganizationSearchContext) { organization:"
        " organizationFromHostedJobsPageName(organizationHostedJobsPageName:"
        " $organizationHostedJobsPageName, searchContext: $searchContext)"
        " { ...OrganizationParts } }"
        " fragment OrganizationParts on Organization { organizationId name hostedJobsPageSlug }"
    ),
}


def browser_fixture_job_url(scenario: str) -> str:
    """Select a source-owned job; callers cannot supply an external URL."""
    if scenario == "ashby-bootstrap":
        return BROWSER_ASHBY_URL
    if scenario == "integration-upload":
        return BROWSER_UPLOAD_URL
    if scenario not in {"dom", "manual", "unknown", "integration"}:
        raise ValueError("synthetic-browser-scenario")
    return BROWSER_FIXTURE_URL


def browser_fixture_configuration(root: Path) -> dict:
    """Accept only the canonical, isolated inputs for the fixed browser diagnostic."""
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("synthetic-browser-root")
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("synthetic-browser-link")
    for name in ("applications", "career", "home", "tmp", "runtime"):
        path = root / name
        if path.is_symlink() or not path.is_dir():
            raise ValueError("synthetic-browser-directory")
    for name in ("single-job-flow", "single-job-worker"):
        path = root / "runtime" / name
        if path.is_symlink() or path.exists() and not path.is_dir():
            raise ValueError("synthetic-browser-runtime")

    def read(name):
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError("synthetic-browser-file")
        if path.stat().st_size > 16_384:
            raise ValueError("synthetic-browser-metadata")
        return json.loads(path.read_text())

    marker, config, fixture = (
        read(name) for name in ("synthetic-flow.json", "portal.json", "browser-fixture.json")
    )
    expected = {
        "applications": str(root / "applications"),
        "career_workspace": str(root / "career"),
    }
    executable = root / "codex-fixture"
    if (
        executable.is_symlink()
        or not executable.is_file()
        or not os.access(executable, os.X_OK)
        or executable.stat().st_nlink != 1
    ):
        raise ValueError("synthetic-browser-cli")
    if (
        not isinstance(marker, dict)
        or set(marker) != {"schemaVersion", "purpose", "codex_sha256"}
        or type(marker["schemaVersion"]) is not int
        or marker["schemaVersion"] != 1
        or marker["purpose"] != "browser-synthetic"
        or marker["codex_sha256"] != hashlib.sha256(executable.read_bytes()).hexdigest()
        or executable.read_bytes() != synthetic_cli_text().encode()
        or config != expected
    ):
        raise ValueError("synthetic-browser-contract")
    if (
        not isinstance(fixture, dict)
        or set(fixture) != {"schemaVersion", "scenario"}
        or type(fixture["schemaVersion"]) is not int
        or fixture["schemaVersion"] != 1
        or not isinstance(fixture["scenario"], str)
        or fixture["scenario"]
        not in {"dom", "manual", "unknown", "integration", "integration-upload", "ashby-bootstrap"}
    ):
        raise ValueError("synthetic-browser-scenario")
    return {**expected, "scenario": fixture["scenario"]}


def browser_fixture_markup(scenario: str) -> str:
    """Source-owned fixtures only. No caller URL, HTML, or executable content is accepted."""
    if scenario == "ashby-bootstrap":
        return (
            """<!doctype html><html lang='en'><meta charset='utf-8'>
<title>Software Engineer @ Synthetic Employer</title><h1>Software Engineer</h1>
<p>Synthetic public bootstrap. No employer receives this data.</p><main></main><script>
const queries="""
            + json.dumps(_ASHBY_PUBLIC_QUERIES)
            + """;
async function read(op,variables) {
 return (await fetch('/api/non-user-graphql?op='+op,{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({operationName:op,query:queries[op],variables})})).json();
}
Promise.all([
 read('ApiJobPosting',{organizationHostedJobsPageName:'synthetic',
  jobPostingId:'00000000-0000-0000-0000-000000000001'}),
 read('ApiOrganizationFromHostedJobsPageName',{organizationHostedJobsPageName:'synthetic',
  searchContext:'JobPosting'})
]).then(()=>document.querySelector('main').innerHTML=`<form>
 <label data-field-path='unknown'>Unrecorded required answer
  <input name='unknown' required></label>
 <label data-field-path='resume'>Resume<input name='resume' type='file' required></label>
 <button type='submit'>Submit Application</button></form>`);
window.finalActions=0;document.addEventListener('submit',e=>{
 e.preventDefault();window.finalActions++;
});
</script></html>"""
        )
    if scenario == "integration-upload":
        markup = browser_fixture_markup("integration")
        return markup.replace(
            "<label>Resume *<input type='file' name='resume' required></label>",
            '<div data-ui="resume"><label>Resume *'
            '<input type="file" name="resume" required></label>'
            '<span data-id="filename"></span></div>',
        ).replace(
            "</script></html>",
            """
document.querySelector('input[type=file]').onchange=async e=>{
 const file=e.target.files[0]; if(!file)return;
 try {
 const signing=await fetch('/api/v1/jobs/SYNTHETIC1/form/upload/resume?'
   +'contentType=application%2Fpdf');
 if(!signing.ok)throw Error('signing failed');
 const handle=await signing.json(),data=new FormData();data.append('Content-Type',file.type);
 for(const [key,value] of Object.entries(handle.uploadPostUrl.fields))data.append(key,value);
 data.append('file',file);
 const uploaded=await fetch(handle.uploadPostUrl.url,{method:'POST',body:data});
 if(!uploaded.ok)throw Error('upload failed');await uploaded.text();
 document.querySelector('[data-id=filename]').textContent=file.name;
 const link=document.createElement('a');link.dataset.action='view';
 link.href=handle.downloadUrl;link.textContent='View synthetic attachment';
 document.querySelector('[data-ui=resume]').append(link);
 }catch(error){window.syntheticUploadError=error.name;}
};
</script></html>""",
        )
    if scenario not in {"dom", "manual", "unknown", "integration"}:
        raise ValueError("synthetic-browser-scenario")
    country = (
        "<input type='color' required>"
        if scenario == "manual"
        else "<input role='combobox' readonly required "
        "aria-controls='countries' aria-expanded='false'>"
    )
    assignment = "combo.value='Switzerland';" if scenario in {"dom", "integration"} else ""
    integration = (
        """<fieldset><legend>Available for synthetic onsite work? *</legend>
<label><input type='radio' name='onsite' value='yes' required>Yes</label>
<label><input type='radio' name='onsite' value='no' required checked>No</label></fieldset>
<label>Synthetic policy acknowledgement *
<input type='checkbox' name='policy' value='acknowledged' required></label>
<label>Synthetic start date *<input type='date' name='start_date' required></label>
<label>Keep existing preference<input type='checkbox' name='keep_preference' checked></label>
"""
        if scenario == "integration"
        else ""
    )
    email_value = " value='wrong-address'" if scenario == "integration" else ""
    return (
        """<!doctype html><html lang='en'><meta charset='utf-8'>
<title>Synthetic Employer Careers</title><style>
body{font:16px system-ui;max-width:650px;margin:40px auto;padding:20px}
label{display:block;margin:16px 0}input{font:inherit;padding:8px;display:block}
[role=option]{padding:10px;border:1px solid #ccc;cursor:pointer}
</style><h1>Software Engineer</h1>
<p>Synthetic browser acceptance. No employer receives this data.</p>
<form><label>Full name *<input name='person' required></label>
<label>Email *<input name='email' type='email' required"""
        + email_value
        + """></label>
<label>Application country *"""
        + country
        + """</label>
<div role='listbox' id='countries' hidden></div>
"""
        + integration
        + """<label>Manual acceptance checkpoint *<input name='checkpoint' required></label>
<label>Untouched note<input name='untouched' value='Preserve this value'></label>
<label>Resume *<input type='file' name='resume' required></label>
<button type='submit'>Submit</button></form><script>
window.syntheticBrowserActions=[];window.syntheticSubmitAttempts=0;
const combo=document.querySelector('[role=combobox]'),list=document.getElementById('countries');
if(combo) combo.onclick=()=>{
 window.syntheticBrowserActions.push('open');combo.ariaExpanded='true';list.hidden=false;
 setTimeout(()=>{list.innerHTML="<div role='option'>Switzerland</div>";
 list.querySelector('[role=option]').onclick=()=>{
 window.syntheticBrowserActions.push('choose');"""
        + assignment
        + """
 combo.ariaExpanded='false';list.hidden=true;};},80);};
document.querySelector('form').onsubmit=e=>{e.preventDefault();window.syntheticSubmitAttempts++;};
</script></html>"""
    )


def isolate_browser_fixture(context) -> None:
    """Block transport before creating any fixture page or runner."""
    context.route("**/*", lambda route: route.abort("blockedbyclient"))
    context.route_web_socket("**/*", lambda socket: socket.on_message(lambda _message: None))


def create_browser_upload_receiver(root: Path) -> tuple[ThreadingHTTPServer, str]:
    """One local receiver for the fixed synthetic ordinary-resume protocol."""
    if browser_fixture_configuration(root)["scenario"] != "integration-upload":
        raise ValueError("synthetic-browser-upload-scenario")
    from .workable_uploads import STORAGE

    directory = root / "runtime/browser-upload-receiver"
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink():
        raise ValueError("synthetic-browser-upload-link")
    event_path = directory / "events.json"
    events = (
        read_json_object(event_path, "upload events")
        if event_path.exists()
        else {
            "presigns": 0,
            "uploads": [],
            "readbacks": 0,
            "submissions": 0,
        }
    )
    token = secrets.token_hex(32)
    lock = Lock()
    key = "tmp/ttl-1d/production/00000000-0000-0000-0000-000000000001"
    date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    credential = "SYNTHETIC/" + date[:8] + "/us-east-1/s3/aws4_request"
    fields = {
        "utf8": "",
        "bucket": "workable-application-form",
        "key": key,
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": credential,
        "X-Amz-Date": date,
        "X-Amz-Signature": "a" * 64,
    }
    signed_policy = {
        "expiration": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        "conditions": [
            ["starts-with", "$utf8", ""],
            ["eq", "$key", key],
            ["content-length-range", 1, 12000000],
            ["starts-with", "$Content-Type", ""],
            *[{name: value} for name, value in fields.items() if name != "X-Amz-Signature"],
        ],
    }
    fields["Policy"] = base64.b64encode(json.dumps(signed_policy).encode()).decode()
    download = (
        STORAGE
        + "/"
        + key
        + "?"
        + urlencode(
            {
                "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                "X-Amz-Content-Sha256": "UNSIGNED-PAYLOAD",
                "X-Amz-Credential": credential,
                "X-Amz-Date": date,
                "X-Amz-Expires": "600",
                "X-Amz-Signature": "b" * 64,
                "X-Amz-SignedHeaders": "host",
                "x-amz-checksum-mode": "ENABLED",
                "x-id": "GetObject",
            }
        )
    )
    descriptor = {
        "uploadPostUrl": {"url": STORAGE, "fields": fields, "path": key},
        "downloadUrl": download,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, status, body=b"", mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "https://apply.workable.com")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def handle_request(self):
            if self.headers.get("X-Synthetic-Receiver") != token:
                self.send(403)
                return
            if self.command == "GET" and self.path == "/document":
                self.send(
                    200,
                    browser_fixture_markup("integration-upload").encode(),
                    "text/html; charset=utf-8",
                )
            elif self.command == "GET" and self.path == "/presign":
                events["presigns"] += 1
                atomic_write_json(event_path, events)
                self.send(200, json.dumps(descriptor).encode())
            elif self.command == "POST" and self.path == "/upload":
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 720000 or events["uploads"]:
                    self.send(409)
                    return
                raw = self.rfile.read(size)
                message = BytesParser(policy=policy.default).parsebytes(
                    (
                        "Content-Type: "
                        + self.headers.get("Content-Type", "")
                        + "\r\nMIME-Version: 1.0\r\n\r\n"
                    ).encode()
                    + raw
                )
                files = [
                    part.get_payload(decode=True)
                    for part in message.iter_parts()
                    if part.get_param("name", header="content-disposition") == "file"
                ]
                if len(files) != 1 or not files[0] or not files[0].startswith(b"%PDF-"):
                    self.send(400)
                    return
                with (directory / "object.pdf").open("xb") as output:
                    os.fchmod(output.fileno(), 0o600)
                    output.write(files[0])
                events["uploads"].append(
                    {
                        "sha256": hashlib.sha256(files[0]).hexdigest(),
                        "size": len(files[0]),
                    }
                )
                atomic_write_json(event_path, events)
                self.send(204)
            elif self.command == "GET" and self.path == "/object" and events["uploads"]:
                events["readbacks"] += 1
                atomic_write_json(event_path, events)
                self.send(200, (directory / "object.pdf").read_bytes(), "application/pdf")
            else:
                self.send(404)

        def guarded_request(self):
            with lock:
                self.handle_request()

        do_GET = do_POST = guarded_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.synthetic_descriptor = descriptor
    Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True).start()
    atomic_write_json(event_path, events)
    return server, token


def install_browser_fixture(context, runner, root: Path) -> None:
    """Retain the production guard and map only the fixed synthetic transports."""
    config = browser_fixture_configuration(root)
    markup = browser_fixture_markup(config["scenario"])
    runner.synthetic_browser = True
    receiver = None
    job_url = browser_fixture_job_url(config["scenario"])
    public_responses = {}
    if config["scenario"] == "ashby-bootstrap":
        public_responses = {
            "ApiJobPosting": {
                "jobPosting": {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "title": "Software Engineer",
                    "applicationForm": {
                        "id": "synthetic-render",
                        "sourceFormDefinitionId": "synthetic-definition",
                        "errorMessages": [],
                        "formErrors": [],
                        "sections": [
                            {
                                "fieldEntries": [
                                    {
                                        "field": {
                                            "path": "unknown",
                                            "title": "Unrecorded required answer",
                                        },
                                        "fieldValue": None,
                                        "isRequired": True,
                                        "isHidden": False,
                                    },
                                    {
                                        "field": {"path": "resume", "title": "Resume"},
                                        "fieldValue": None,
                                        "isRequired": True,
                                        "isHidden": False,
                                    },
                                ]
                            }
                        ],
                    },
                }
            },
            "ApiOrganizationFromHostedJobsPageName": {
                "organization": {
                    "organizationId": "synthetic-org",
                    "name": "Synthetic Employer",
                    "hostedJobsPageSlug": "synthetic",
                }
            },
        }
    if config["scenario"] == "integration-upload":
        receiver, token = create_browser_upload_receiver(root)
        job_url = BROWSER_UPLOAD_URL

        def close_receiver(*_args):
            receiver.shutdown()
            receiver.server_close()

        context.on("close", close_receiver)

    def intercept(route):
        document = SimpleNamespace(status=200, dispose=lambda: None)
        public = None

        class SyntheticRoute:
            request = route.request

            def continue_(self):
                if self.request.method == "GET" and self.request.url == job_url:
                    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=markup)
                else:
                    route.abort("blockedbyclient")

            def abort(self, reason):
                route.abort(reason)

            def fetch(self, **options):
                nonlocal public
                from .workable_uploads import STORAGE

                if (
                    receiver is None
                    and self.request.method == "GET"
                    and self.request.url == job_url
                    and options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                ):
                    return document
                if (
                    public_responses
                    and self.request.method == "POST"
                    and options == {"max_redirects": 0, "max_retries": 0, "timeout": 10000}
                ):
                    operation = self.request.post_data_json.get("operationName")
                    if (
                        operation in public_responses
                        and self.request.url
                        == "https://jobs.ashbyhq.com/api/non-user-graphql?op=" + operation
                    ):
                        public = SimpleNamespace(
                            status=200,
                            dispose=lambda: None,
                            data={"data": public_responses[operation]},
                        )
                        return public
                endpoints = {
                    ("GET", BROWSER_UPLOAD_URL): "/document",
                    (
                        "GET",
                        "https://apply.workable.com/api/v1/jobs/SYNTHETIC1/form/upload/resume?"
                        "contentType=application%2Fpdf",
                    ): "/presign",
                    ("POST", STORAGE + "/"): "/upload",
                }
                if receiver is not None:
                    endpoints[("GET", receiver.synthetic_descriptor["downloadUrl"])] = "/object"
                target = endpoints.get((self.request.method, self.request.url))
                if (
                    receiver is None
                    or target is None
                    or options
                    != {
                        "max_redirects": 0,
                        "max_retries": 0,
                        "timeout": 10000,
                    }
                ):
                    raise ValueError("synthetic-browser-upload-target")
                return route.fetch(
                    url=f"http://127.0.0.1:{receiver.server_port}" + target,
                    headers={**self.request.headers, "X-Synthetic-Receiver": token},
                    **options,
                )

            def fulfill(self, **response):
                if response.get("response") is document:
                    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=markup)
                elif public is not None and response.get("response") is public:
                    route.fulfill(status=200, json=public.data)
                else:
                    route.fulfill(**response)

        runner._live_guard(SyntheticRoute())

    context.route("**/*", intercept)
    context.route_web_socket("**/*", lambda socket: socket.on_message(lambda _message: None))


def page_markup(app: dict, index: int, platform: str, controls: dict) -> str:
    form = FORMS[platform]
    identifier = app["id"]
    question = (
        "Will you now or in the future require visa sponsorship?"
        if index % 2 == 0
        else "Do you require visa sponsorship now or in the future?"
    )
    question = controls.get("sponsorship_question", question)
    row_class = "application-question" if platform == "lever" else "field"
    label_class = "application-label" if platform == "lever" else ""

    def field(key: str, label: str, content: str) -> str:
        return (
            f'<div class="{row_class}"><label class="{label_class}" for="{key}">'
            f"{html.escape(label)} *</label>{content}</div>"
        )

    def text(key: str, label: str, kind: str = "text") -> str:
        return field(key, label, f'<input id="{key}" name="{key}" type="{kind}" required>')

    def select(key: str, label: str) -> str:
        # Greenhouse uses non-label values. The executor must select and read the label.
        yes, no = ("1", "0") if platform == "greenhouse" else ("Yes", "No")
        return field(
            key,
            label,
            f'<select id="{key}" name="{key}" required>'
            f'<option value="">Choose…</option><option value="{yes}">Yes</option>'
            f'<option value="{no}">No</option></select>',
        )

    fields = (
        text("name", "Full name")
        if platform == "lever"
        else text("first_name", "First Name") + text("last_name", "Last Name")
    )
    fields += text("email", "Email address", "email")
    fields += select("sponsorship" if platform == "lever" else "question_1001", question)
    if platform == "greenhouse":
        fields += select("question_1002", "Are you currently authorized to work in this country?")
    fields += field(
        "resume", "Resume", '<input id="resume" name="resume" type="file" accept=".pdf" required>'
    )
    if controls.get("extra_attachment"):
        fields += field("cover_letter", "Cover Letter", '<input id="cover_letter" type="file">')
    if controls.get("unsupported_control"):
        fields += field(
            "custom", "Unverified control", '<input id="custom" type="checkbox" required>'
        )
    form_attributes = 'class="application-form"' if platform == "lever" else 'id="application_form"'
    upload_id = form.upload_status.removeprefix("#")
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Synthetic {platform.title()} · {html.escape(app["company"])}</title>
<style>body{{font:16px system-ui;max-width:700px;margin:40px auto;padding:20px}}
.application-question,.field{{margin:24px 0}}label{{display:block;margin-bottom:8px}}
input,select,button{{font:inherit;padding:10px}}input{{width:80%}}
small{{display:block;color:#576557}}.banner{{background:#fff4cf;padding:15px}}</style>
<main data-company="{html.escape(app["company"], quote=True)}"
 data-role="{html.escape(app["role_title"], quote=True)}"
 data-job-url="{html.escape(_job_identity(app["url"])[1], quote=True)}">
<p class="banner">Synthetic local acceptance page. No employer receives this application.</p>
<h1>{html.escape(app["role_title"])}</h1><h2>{html.escape(app["company"])}</h2>
<form {form_attributes} action="{form.submit_path(identifier)}" method="post">
{fields}<small id="{upload_id}" data-state="empty">No resume selected</small>
<button type="submit">Submit application</button>
</form></main><script>
document.querySelector('#resume').addEventListener('change', async (event) => {{
 const file = event.target.files[0], status = document.querySelector('#{upload_id}');
 if (!file) return;
 status.dataset.state = 'uploading';
 try {{
 const response = await fetch('{form.upload_path(identifier)}', {{
 method:'POST', body:await file.arrayBuffer(),
 headers:{{'Content-Type':'application/pdf','X-Filename':encodeURIComponent(file.name)}}
 }});
 const result = await response.json(); if (!response.ok) throw new Error('Upload failed');
 if (result.new_required) {{
   const row = document.createElement('div'); row.className = '{row_class}';
   const label = document.createElement('label'); label.className = '{label_class}';
   label.htmlFor = 'notice_period'; label.textContent = 'Notice period in days *';
   const input = document.createElement('input'); input.id = 'notice_period';
   input.required = true; row.append(label, input); status.before(row);
 }}
 if (result.identity_changed)
   document.querySelector('main').dataset.company = 'Changed fixture company';
 status.dataset.state = 'complete'; status.dataset.sha256 = result.sha256;
 status.dataset.name = file.name; status.textContent = file.name + ' · uploaded';
 }} catch {{ status.dataset.state = 'error'; status.textContent = 'Upload failed'; }}
}});
</script></html>'''


def create_fixture_server(applications: list[dict], root: Path) -> ThreadingHTTPServer:
    records = {app["id"]: app for app in applications}
    platforms = {key: _job_identity(app["url"])[0] for key, app in records.items()}
    event_path = root / "fixture-events.json"
    events = (
        read_json_object(event_path, "fixture events")
        if event_path.exists()
        else {"uploads": [], "submissions": [], "blocked_requests": []}
    )
    configuration = root / "fixture-server.json"
    port = (
        read_json_object(configuration, "fixture server")["port"] if configuration.exists() else 0
    )
    lock = Lock()
    # Test-only fixture controls. This dictionary is not exposed through the portal API.
    overrides: dict[str, dict] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def send(self, status: int, raw: bytes, mime: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            identifier = self.path.rsplit("/", 1)[-1]
            if identifier not in records or self.path != FORMS[platforms[identifier]].page_path(
                identifier
            ):
                self.send(404, b"Not found", "text/plain")
                return
            markup = page_markup(
                records[identifier],
                list(records).index(identifier),
                platforms[identifier],
                overrides.get(identifier, {}),
            )
            self.send(200, markup.encode(), "text/html; charset=utf-8")

        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 1_000_000:
                self.send(413, b"{}", "application/json")
                return
            raw = self.rfile.read(size)
            identifier = self.path.rsplit("/", 1)[-1]
            if identifier not in records:
                self.send(404, b"{}", "application/json")
                return
            form, controls = FORMS[platforms[identifier]], overrides.get(identifier, {})
            if self.path == form.upload_path(identifier):
                entry = {"id": identifier, "sha256": hashlib.sha256(raw).hexdigest(), "size": size}
                with lock:
                    events["uploads"].append(entry)
                    atomic_write_json(event_path, events)
                response = dict(entry)
                if controls.get("wrong_upload_digest"):
                    response["sha256"] = "0" * 64
                response["new_required"] = bool(controls.get("new_required_after_upload"))
                response["identity_changed"] = bool(controls.get("identity_changed_after_upload"))
                self.send(
                    503 if controls.get("upload_error") else 200,
                    json.dumps(response).encode(),
                    "application/json",
                )
            elif self.path == form.submit_path(identifier):
                with lock:
                    events["submissions"].append({"id": identifier, "source": "human"})
                    atomic_write_json(event_path, events)
                self.send(200, b"Synthetic human submission received", "text/plain")
            else:
                self.send(404, b"{}", "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.fixture_events = events
    server.fixture_overrides = overrides
    Thread(target=server.serve_forever, daemon=True).start()
    atomic_write_json(event_path, events)
    atomic_write_json(configuration, {"port": server.server_port})
    return server
