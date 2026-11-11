"""Bounded ordinary-resume Workable transport. No autofill or application operation.

Protocol evidence: Workable careers.6901cd820c44d775.js (SHA256
8d5032a52f953409af0afd95dd11b59095f20bedb669bb4dff32000bbf2cab0f) and
shared.applicationForm.20f17cd312ee6e3c.chunk.js (SHA256
982b5d16c0e8c2a12fb1c0721e7669f26de5fd462d43122517b88120283346a3),
reviewed statically 2026-10-17. This implements a narrow protocol, not copied JS.
Unsupported storage descriptors fail closed; static evidence is not live acceptance.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from .career_portal_data import PortalDataError
from .hosted_ats import control


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def job_shortcode(url: str) -> str | None:
    p = urlsplit(url)
    match = re.fullmatch(r"/[A-Za-z0-9_-]+/j/([A-Za-z0-9]+)/apply/", p.path)
    if p.scheme == "https" and p.netloc == "apply.workable.com" and not p.query and not p.fragment:
        return match[1] if match else None
    return None


STORAGE = "https://workable-application-form.s3.us-east-1.amazonaws.com"


def _storage(url: str):
    if not isinstance(url, str):
        raise ValueError("invalid storage URL")
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.netloc != urlsplit(STORAGE).netloc
        or p.fragment
        or any(c in url for c in "\\\r\n\t")
        or re.search(r"%(?![A-Fa-f0-9]{2})", url)
    ):
        raise ValueError("unsupported storage URL")
    return p


def _parts(request):
    content_type = request.headers.get("content-type", "")
    boundary = re.fullmatch(r"multipart/form-data; boundary=([-A-Za-z0-9_]{1,100})", content_type)
    raw = request.post_data_buffer
    if not boundary or not raw or len(raw) > 720000:
        return []
    marker = boundary[1].encode()
    if not raw.startswith(b"--" + marker + b"\r\n"):
        return []
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw
    )
    if (
        not message.is_multipart()
        or message.defects
        or message.preamble is not None
        or message.epilogue not in {None, "", "\r\n"}
    ):
        return []
    return list(message.iter_parts())


class ResumeUpload:
    def __init__(self, job: dict):
        self.job = job
        code = job_shortcode(job["job_url"])
        if not code:
            raise ValueError("unsupported Workable job")
        self.presign = f"https://apply.workable.com/api/v1/jobs/{code}/form/upload/resume?contentType=application%2Fpdf"
        self.active = None
        self.pending = {}
        self.sent = set()
        self.handle = None
        self.uploaded = False
        self.remote_sha256 = ""
        self.failed = False
        self.reading = False
        self.expires = 0.0

    def allows_public_read(self, request) -> bool:
        """Use exact job, bootstrap and reviewed static-source URLs for every resource."""
        if (
            request.method != "GET"
            or request.post_data_buffer is not None
            or request.redirected_from is not None
        ):
            return False
        if request.is_navigation_request():
            return request.resource_type == "document" and request.url == self.job["job_url"]
        account = urlsplit(self.job["job_url"]).path.split("/")[1]
        code = job_shortcode(self.job["job_url"])
        if request.resource_type in {"fetch", "xhr"}:
            return request.url in {
                f"https://apply.workable.com/api/v1/accounts/{account}?full=true",
                f"https://apply.workable.com/api/v2/accounts/{account}/jobs/{code}",
                f"https://apply.workable.com/api/v1/jobs/{code}/form",
            }
        # Static protocol evidence above identifies these exact source assets.
        # A resource type or a .js suffix cannot turn an API into a static grant.
        return request.resource_type == "script" and request.url in {
            "https://dcvxs6ggqztsa.cloudfront.net/candidate/releases/careers.6901cd820c44d775.js",
            "https://dcvxs6ggqztsa.cloudfront.net/candidate/releases/"
            "shared.applicationForm.20f17cd312ee6e3c.chunk.js",
        }

    def begin(self, question: dict, intent: dict, page):
        if self.active or page.url != self.job["job_url"]:
            raise ValueError("upload already attempted or page changed")
        field = control(page, question)
        if field.locator("xpath=ancestor::*[@data-ui='resume']").count() != 1:
            raise ValueError("ordinary resume control required")
        self.active = intent

    def sensitive(self, request) -> bool:
        p = urlsplit(request.url)
        return (
            request.method != "GET"
            or "/api/v1/jobs/" in p.path
            and re.search(r"/(?:form/upload|apply|autofill|attributes)(?:/|$)", p.path) is not None
            or self.handle is not None
            and request.url in {(STORAGE + "/"), self.handle["downloadUrl"]}
        )

    def allows(self, request) -> str | None:
        if not self.active or self.failed or request.resource_type not in {"fetch", "xhr"}:
            return None
        kind = None
        if request.method == "GET" and request.url == self.presign:
            if request.post_data_buffer is not None:
                return None
            kind = "workable_presign"
        elif request.method == "POST":
            self.settle("workable_presign")
            if not self.handle or time.time() >= self.expires or request.url != (STORAGE + "/"):
                return None
            fields = {"Content-Type": "application/pdf", **self.handle["uploadPostUrl"]["fields"]}
            parts = _parts(request)
            names = [p.get_param("name", header="content-disposition") for p in parts]
            if len(names) != len(set(names)) or set(names) != {*fields, "file"}:
                return None
            for name, part in zip(names, parts, strict=True):
                headers = [key.lower() for key, _ in part.raw_items()]
                params = part.get_params(header="content-disposition") or []
                expected_params = {"name", "filename"} if name == "file" else {"name"}
                if (
                    part.defects
                    or part.is_multipart()
                    or sorted(headers)
                    != (
                        ["content-disposition", "content-type"]
                        if name == "file"
                        else ["content-disposition"]
                    )
                    or part.get_content_disposition() != "form-data"
                    or len(params) != len(expected_params) + 1
                    or {key for key, _ in params[1:]} != expected_params
                    or name == "file"
                    and str(part["Content-Type"]) != "application/pdf"
                ):
                    return None
                raw = part.get_payload(decode=True)
                if name == "file":
                    if (
                        part.get_filename() != self.job["filename"]
                        or part.get_content_type() != "application/pdf"
                        or raw is None
                        or hashlib.sha256(raw).hexdigest() != self.job["file_sha256"]
                    ):
                        return None
                elif part.get_filename() is not None or raw != fields[name].encode():
                    return None
            kind = "workable_upload"
        elif (
            self.reading
            and self.handle
            and request.method == "GET"
            and request.url == self.handle["downloadUrl"]
            and request.post_data_buffer is None
        ):
            kind = "workable_readback"
        if kind is None or kind in self.sent:
            return None
        self.sent.add(kind)
        self.pending[request] = kind
        return kind

    def response(self, response, *, request=None):
        request = response.request if request is None else request
        kind = self.pending.get(request)
        if not kind:
            return
        if request.redirected_from is not None or response.status not in (
            {200} if kind != "workable_upload" else {200, 201, 204}
        ):
            self.failed = True
            raise ValueError("upload response unknown")
        raw = response.body()
        if self.pending.pop(request, None) is None:
            return
        if kind == "workable_presign":
            if (
                len(raw) > 64000
                or response.headers.get("content-type", "").split(";", 1)[0] != "application/json"
            ):
                raise ValueError("invalid signing response")
            self.handle = self.validate(json.loads(raw, object_pairs_hook=_unique))
        elif kind == "workable_upload":
            self.uploaded = True
        else:
            if (
                len(raw) > 600000
                or not raw.startswith(b"%PDF-")
                or hashlib.sha256(raw).hexdigest() != self.job["file_sha256"]
            ):
                raise ValueError("remote attachment mismatch")
            self.remote_sha256 = hashlib.sha256(raw).hexdigest()

    def settle(self, kind):
        for request, pending_kind in list(self.pending.items()):
            if pending_kind == kind:
                response = request.response()
                if response is not None:
                    self.response(response)

    def validate(self, data: dict) -> dict:
        if not isinstance(data, dict) or set(data) != {"uploadPostUrl", "downloadUrl"}:
            raise ValueError("unsupported signing descriptor")
        upload = data["uploadPostUrl"]
        if not isinstance(upload, dict) or set(upload) != {"url", "fields", "path"}:
            raise ValueError("unsupported upload descriptor")
        up, down = _storage(upload["url"]), _storage(data["downloadUrl"])
        fields = upload["fields"]
        required = {
            "utf8",
            "bucket",
            "key",
            "Policy",
            "X-Amz-Algorithm",
            "X-Amz-Credential",
            "X-Amz-Date",
            "X-Amz-Signature",
        }
        if (
            up.path not in {"", "/"}
            or up.query
            or not isinstance(fields, dict)
            or set(fields) != required
            or not all(isinstance(v, str) and len(v) <= 20000 for v in fields.values())
            or fields["utf8"] != ""
            or fields["bucket"] != "workable-application-form"
            or not re.fullmatch(
                r"tmp/ttl-1d/production/[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", fields["key"]
            )
            or fields["key"] != upload["path"]
            or unquote(down.path) != "/" + fields["key"]
            or fields["X-Amz-Algorithm"] != "AWS4-HMAC-SHA256"
            or not re.fullmatch(r"[a-fA-F0-9]{64}", fields["X-Amz-Signature"])
            or not re.fullmatch(
                r"[A-Z0-9]+/[0-9]{8}/us-east-1/s3/aws4_request", fields["X-Amz-Credential"]
            )
            or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", fields["X-Amz-Date"])
            or fields["X-Amz-Date"][:8] != fields["X-Amz-Credential"].split("/")[1]
        ):
            raise ValueError("unbound signed fields")
        query = _unique(parse_qsl(down.query, keep_blank_values=True, strict_parsing=True))
        expected_query = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Content-Sha256": "UNSIGNED-PAYLOAD",
            "X-Amz-Credential": fields["X-Amz-Credential"],
            "X-Amz-Date": fields["X-Amz-Date"],
            "X-Amz-SignedHeaders": "host",
            "x-amz-checksum-mode": "ENABLED",
            "x-id": "GetObject",
        }
        if (
            set(query) != {*expected_query, "X-Amz-Expires", "X-Amz-Signature"}
            or any(query[k] != v for k, v in expected_query.items())
            or not re.fullmatch(r"[a-fA-F0-9]{64}", query["X-Amz-Signature"])
            or not re.fullmatch(r"[0-9]{1,5}", query["X-Amz-Expires"])
            or not 1 <= int(query["X-Amz-Expires"]) <= 21600
        ):
            raise ValueError("unbound download signature")
        signed_at = (
            datetime.strptime(fields["X-Amz-Date"], "%Y%m%dT%H%M%SZ")
            .replace(tzinfo=UTC)
            .timestamp()
        )
        if signed_at > time.time() + 60 or signed_at + int(query["X-Amz-Expires"]) <= time.time():
            raise ValueError("download signature expired")
        policy = json.loads(
            base64.b64decode(fields["Policy"], validate=True), object_pairs_hook=_unique
        )
        if not isinstance(policy, dict) or set(policy) != {"expiration", "conditions"}:
            raise ValueError("invalid policy")
        expiration = datetime.fromisoformat(policy["expiration"].replace("Z", "+00:00"))
        if expiration.tzinfo is None or not 0 < expiration.timestamp() - time.time() <= 21600:
            raise ValueError("expired or unsupported policy")
        exact, bounds, prefixes, eq_key = {}, [], [], False
        if not isinstance(policy["conditions"], list) or len(policy["conditions"]) > 20:
            raise ValueError("invalid policy conditions")
        for condition in policy["conditions"]:
            if isinstance(condition, dict):
                pairs = condition.items()
            elif isinstance(condition, list) and len(condition) == 3:
                if condition[0] == "eq" and condition[1] == "$key":
                    eq_key = True
                    pairs = [("key", condition[2])]
                elif condition[0] == "starts-with" and condition[1:] in [
                    ["$utf8", ""],
                    ["$Content-Type", ""],
                ]:
                    prefixes.append(condition[1])
                    continue
                elif condition[0] == "content-length-range":
                    bounds.append(condition[1:])
                    continue
                else:
                    raise ValueError("broad or unknown policy condition")
            else:
                raise ValueError("invalid policy condition")
            for name, value in pairs:
                if not isinstance(value, str) or name in exact and exact[name] != value:
                    raise ValueError("conflicting policy condition")
                exact[name] = value
        expected = {k: v for k, v in fields.items() if k not in {"Policy", "X-Amz-Signature"}}
        size = Path(self.job["file_path"]).stat().st_size
        if (
            exact != expected
            or not eq_key
            or sorted(prefixes) != ["$Content-Type", "$utf8"]
            or len(bounds) != 1
            or not all(type(n) is int for n in bounds[0])
            or not 1 <= bounds[0][0] <= size <= 600000
            or not size <= bounds[0][1] <= 12000000
        ):
            raise ValueError("unbounded policy")
        self.expires = min(expiration.timestamp(), signed_at + int(query["X-Amz-Expires"]))
        return data

    def wait(self, page):
        deadline = time.monotonic() + 6
        while not self.uploaded and not self.failed and time.monotonic() < deadline:
            page.wait_for_timeout(25)
            self.settle("workable_upload")
        if not self.uploaded or self.failed:
            raise PortalDataError(
                "upload_result_unknown", "附件上传结果未确认，请核验保留的页面。", 409
            )
        page.locator('[data-ui="resume"] [data-action="view"]').wait_for(timeout=3000)

    def attachment(self, page):
        result = page.locator('[data-ui="resume"]').evaluate("""e => ({
            names:[...e.querySelectorAll('[data-id="filename"]')].filter(n=>n.getClientRects().length).map(n=>n.textContent.trim()),
            links:[...e.querySelectorAll('[data-action="view"]')]
              .filter(a=>a.getClientRects().length).map(a=>a.getAttribute('href'))})""")
        if (
            not self.handle
            or result["links"] != [self.handle["downloadUrl"]]
            or result["names"] != [self.job["filename"]]
        ):
            raise PortalDataError("upload_result_unknown", "当前表单附件链接未核验。", 409)

    def readback(self, page):
        self.attachment(page)
        self.reading = True
        try:
            page.evaluate(
                """async url => {
                const c=new AbortController(), timer=setTimeout(()=>c.abort(),4000);
                try { const r=await fetch(url,{credentials:'omit',redirect:'error',
                    signal:c.signal}); if(!r.ok)throw Error('attachment readback failed');
                    await r.arrayBuffer(); } finally {clearTimeout(timer);}
            }""",
                self.handle["downloadUrl"],
            )
            self.settle("workable_readback")
        finally:
            self.reading = False
        self.attachment(page)
        if self.failed or self.remote_sha256 != self.job["file_sha256"]:
            raise PortalDataError("upload_result_unknown", "远端附件字节未核验，请人工核验。", 409)
        return {
            "action": "workable_upload_verified",
            "remote_sha256": self.remote_sha256,
            "server_readback": True,
        }
