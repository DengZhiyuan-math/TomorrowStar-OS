"""Reviewed Ashby draft transport for native generic controls. No Submit operation."""

from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from urllib.parse import urlsplit

from .application_automation import _job_identity
from .application_information import fact_for
from .career_portal_data import PortalDataError
from .hosted_ats import graphql_tokens, is_final_submission, multipart_parts

OPERATIONS = {
    "ApiJobPosting": ("query", {"jobPosting"}),
    "ApiOrganizationFromHostedJobsPageName": ("query", {"organizationFromHostedJobsPageName"}),
    "ApiSetFormValue": ("mutation", {"setFormValue"}),
    "ApiAutocompleteGeoLocation": ("query", {"result", "autocompleteGeoLocation"}),
    "ApiCreateFileUploadHandle": ("mutation", {"fileUploadHandle", "createFileUploadHandle"}),
    "ApiSetFormValueToFile": ("mutation", {"setFormValueToFile"}),
}


def supports(url: str) -> bool:
    """Select the existing adapter by posting identity, without operator grants."""
    try:
        _, normalized = _job_identity(url, allow_generic=True)
        p = urlsplit(normalized)
        return bool(
            p.hostname == "jobs.ashbyhq.com"
            and re.fullmatch(r"/[A-Za-z0-9_.-]+/[a-fA-F0-9-]{36}/application", p.path)
            and not p.query
            and not p.fragment
        )
    except PortalDataError:
        return False


def single_draft_operation(
    query: str, operation: str, variable_names: set[str], *, public=False, query_name=None
) -> bool:
    """Bind one understood root's arguments directly to the checked variables.

    This bounded syntax reader replaces exact query hashes, not a general GraphQL
    parser. Values and comments do not determine the operation's business purpose.
    """
    tokens = graphql_tokens(query)
    if tokens is None or operation not in OPERATIONS or not variable_names:
        return False
    kind, fields = OPERATIONS[operation]
    if tokens[:2] != [kind, query_name if public else operation]:
        return False
    index = 2

    def group(start: int, opening: str, closing: str) -> int:
        stack = []
        pairs = {"(": ")", "[": "]", "{": "}"}
        for position in range(start, len(tokens)):
            token = tokens[position]
            if token in pairs:
                stack.append(pairs[token])
            elif token in pairs.values():
                if not stack or stack.pop() != token:
                    return -1
                if not stack:
                    return position + 1 if tokens[start] == opening and token == closing else -1
        return -1

    def name(position):
        return position < len(tokens) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", tokens[position])

    # No defaults or unused variables: the JSON values checked below must be the
    # values executed by the root field, without an alternate literal/default.
    if tokens[index : index + 1] != ["("]:
        return False
    index += 1
    declared, required = set(), set()
    while tokens[index : index + 1] != [")"]:
        if (
            tokens[index : index + 1] != ["$"]
            or not name(index + 1)
            or tokens[index + 2 : index + 3] != [":"]
            or tokens[index + 1] in declared
        ):
            return False
        variable = tokens[index + 1]
        declared.add(variable)
        index += 3
        brackets = 0
        while tokens[index : index + 1] == ["["]:
            brackets += 1
            index += 1
        if not name(index):
            return False
        index += 1
        if tokens[index : index + 1] == ["!"]:
            index += 1
        for _ in range(brackets):
            if tokens[index : index + 1] != ["]"]:
                return False
            index += 1
            if tokens[index : index + 1] == ["!"]:
                index += 1
        if tokens[index - 1] == "!":
            required.add(variable)
    optional = {"searchContext"} if public and operation != "ApiJobPosting" else set()
    if (
        not required <= variable_names
        or not variable_names <= declared
        or not declared - variable_names <= optional
    ):
        return False
    index += 1
    if tokens[index : index + 1] != ["{"]:
        return False
    index += 1
    if name(index) and tokens[index + 1 : index + 2] == [":"]:
        index += 2
    if index >= len(tokens) or tokens[index] not in fields:
        return False
    index += 1
    if tokens[index : index + 1] != ["("]:
        return False
    index += 1
    arguments = set()
    while tokens[index : index + 1] != [")"]:
        if (
            not name(index)
            or tokens[index + 1 : index + 3] != [":", "$"]
            or tokens[index + 3 : index + 4] != [tokens[index]]
            or tokens[index] in arguments
        ):
            return False
        arguments.add(tokens[index])
        index += 4
    if arguments != declared:
        return False
    index += 1
    if tokens[index : index + 1] != ["{"]:
        return False
    index = group(index, "{", "}")
    if index < 0 or tokens[index : index + 1] != ["}"]:
        return False
    index += 1
    if not public:
        return index == len(tokens)
    # Public client documents append selection fragments. They cannot introduce
    # another operation or another root; writes keep the stricter existing path.
    fragments = set()
    while index < len(tokens):
        if (
            tokens[index] != "fragment"
            or not name(index + 1)
            or tokens[index + 1] in fragments
            or tokens[index + 2 : index + 3] != ["on"]
            or not name(index + 3)
            or tokens[index + 4 : index + 5] != ["{"]
        ):
            return False
        fragments.add(tokens[index + 1])
        index = group(index + 4, "{", "}")
        if index < 0:
            return False
    return all(
        tokens[i + 1] == "on" or tokens[i + 1] in fragments
        for i, token in enumerate(tokens[:-1])
        if token == "..."
    )


class DraftSession:
    def __init__(self, job: dict):
        self.job = job
        self.org, self.posting = urlsplit(job["job_url"]).path.split("/")[1:3]
        self.form = None
        self.fields = {}
        self.pending = {}
        self.active = None
        self.done = False
        self.suggestions = {}
        self.handle = None
        self.files = {}
        self.uploaded = False
        self.linked = False
        self.failed = False
        self.counts: dict[str, int] = {}
        self.sent: set[str] = set()
        self.public_request = None
        self.public_key = "jobPosting"

    def payload(self, request, *, public=False):
        if request.method != "POST" or request.resource_type not in {"fetch", "xhr"}:
            return None
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            return None
        raw = request.post_data_buffer
        if not raw or len(raw) > 128_000:
            return None
        try:
            p = json.loads(raw)
            if set(p) != {"operationName", "variables", "query"}:
                return None
            op = p["operationName"]
            if (
                not isinstance(op, str)
                or request.url != "https://jobs.ashbyhq.com/api/non-user-graphql?op=" + op
            ):
                return None
            if not isinstance(p["variables"], dict) or is_final_submission(request, self.job):
                return None
            if public:
                if getattr(request, "redirected_from", None) is not None:
                    return None
                for operation in ("ApiJobPosting", "ApiOrganizationFromHostedJobsPageName"):
                    if single_draft_operation(
                        p["query"], operation, set(p["variables"]), public=True, query_name=op
                    ):
                        tokens = graphql_tokens(p["query"])
                        # The bounded reader has excluded defaults and directives;
                        # the first selection starts with its sole root or alias.
                        key = tokens[tokens.index("{") + 1]
                        return operation, p["variables"], key
                return None
            if not single_draft_operation(p["query"], op, set(p["variables"])):
                return None
            return op, p["variables"]
        except (ValueError, TypeError, KeyError, AttributeError):
            return None

    def track_public(self, request):
        parsed = self.payload(request, public=True)
        if parsed is None:
            return False
        operation, variables, key = parsed
        if (operation, variables) == (
            "ApiJobPosting",
            {"organizationHostedJobsPageName": self.org, "jobPostingId": self.posting},
        ):
            self.pending[request] = ("initial", key)
            self.public_request = {"url": request.url, "body": request.post_data_buffer.decode()}
            self.public_key = key
            return True
        if (
            operation == "ApiOrganizationFromHostedJobsPageName"
            and variables.get("organizationHostedJobsPageName") == self.org
            and set(variables) <= {"organizationHostedJobsPageName", "searchContext"}
            and variables.get("searchContext") in (None, "JobPosting")
        ):
            self.pending[request] = ("organization", key)
            return True
        return False

    def refresh(self, page, action_results):
        """Recheck the observed posting query. It grants no write."""
        if not self.public_request:
            raise PortalDataError(
                "draft_result_unknown", "缺少已观察的只读草稿查询，请人工核验。", 409
            )
        data = page.evaluate(
            """async ({url, body}) => {
            const abort = new AbortController();
            const timer = setTimeout(() => abort.abort(), 4000);
            try {
                const response = await fetch(url, {method:'POST', body,
                    headers:{'Content-Type':'application/json'}, signal:abort.signal});
                if (!response.ok) throw new Error('readback failed');
                return await response.json();
            } finally { clearTimeout(timer); }
        }""",
            self.public_request,
        )
        if data.get("errors"):
            raise ValueError("draft readback failed")
        posting = data["data"][self.public_key]
        if posting["id"] != self.posting or posting["title"] != self.job["role_title"]:
            raise ValueError("posting changed")
        self._form(posting["applicationForm"])
        self.pending.clear()
        self.active, self.failed, self.done = None, False, False
        self.sent.clear()
        if not any(row["intent"]["action"] == "upload" for row in action_results.values()):
            return
        self.uploaded = self.linked = False
        self.files.clear()
        for row in action_results.values():
            intent = row["intent"]
            if intent["action"] != "upload" or row["conclusion"] != "current_matches":
                continue
            update = self.job.get("material_update") or {}
            current = update.get("new_attachment") or {}
            if (
                not intent.get("material_id")
                and update.get("status") in {"bound", "complete"}
                and current.get("attempt_id")
                and intent.get("attempt_id") != current["attempt_id"]
            ):
                if intent.get("material_update_id") == update.get("id"):
                    raise PortalDataError(
                        "draft_result_unknown", "新版简历的实际附件身份未核验。", 409
                    )
                # Earlier versions can have identical bytes. Their attempts remain
                # historical evidence, never proof of the current attachment.
                continue
            if (
                not intent.get("material_id")
                and intent.get("sha256") != self.job["file_sha256"]
                and any(
                    update.get("old_sha256") == intent.get("sha256")
                    and update.get("status") in {"bound", "complete"}
                    for update in [
                        self.job.get("material_update") or {},
                        *self.job.get("material_update_history", []),
                    ]
                )
            ):
                # A completed old resume remains in history; only the current
                # version can establish this field's present remote identity.
                continue
            path = intent.get("draft_path") or "resume"
            material = (
                next(
                    (
                        item
                        for item in self.job.get("materials", [])
                        if item.get("id") == intent.get("material_id")
                        and item.get("draft_path") == path
                    ),
                    None,
                )
                if intent.get("material_id")
                else {
                    "id": "resume",
                    "filename": self.job["filename"],
                    "sha256": self.job["file_sha256"],
                }
            )
            attachment = self.fields.get(path, {}).get("fieldValue")
            update = self.job.get("material_update") or {}
            if not intent.get("material_id") and update.get("status") in {"bound", "complete"}:
                old_id = (
                    update.get("page_receipt", {}).get("attachments", {}).get("remote") or {}
                ).get("attachment_id")
                current = update.get("new_attachment") or {}
                if isinstance(attachment, dict) and (
                    update.get("old_sha256") != self.job["file_sha256"]
                    and old_id
                    and attachment.get("id") == old_id
                    or current
                    and (
                        attachment.get("id") != current.get("attachment_id")
                        or intent.get("attempt_id") != current.get("attempt_id")
                    )
                ):
                    raise PortalDataError(
                        "draft_result_unknown", "新版简历的实际附件身份未核验。", 409
                    )
            if (
                material is None
                or intent.get("sha256") != material["sha256"]
                or not isinstance(attachment, dict)
                or not attachment.get("id")
                or attachment.get("filename") != material["filename"]
            ):
                raise PortalDataError(
                    "draft_result_unknown", "当前服务端附件未核验；不会重复上传。", 409
                )
            self.files[path] = {**material, "attachment_id": attachment["id"]}
            if material["id"] == "resume":
                self.uploaded = self.linked = True

    def _attachment_conflicts(self, path, attachment_id, sha256):
        return any(
            other_path != path
            and evidence.get("attachment_id") == attachment_id
            and evidence.get("sha256")
            and sha256
            and evidence["sha256"] != sha256
            for other_path, evidence in self.files.items()
        )

    def file_verified(self, question, material):
        path = question.get("draft_path")
        attachment = self.fields.get(path, {}).get("fieldValue")
        evidence = self.files.get(path, {})
        return bool(
            isinstance(attachment, dict)
            and attachment.get("id")
            and attachment.get("id") == evidence.get("attachment_id")
            and attachment.get("filename") == material["filename"]
            and evidence.get("filename") == material["filename"]
            and evidence.get("sha256") == material["sha256"]
            and evidence.get("id") == material["id"]
            and not self._attachment_conflicts(path, attachment["id"], material["sha256"])
        )

    def native_material_verified(self, intent, question, material):
        """Prove this active native attempt's own draft responses, never historical files."""
        if not all(isinstance(value, dict) for value in (intent, question, material)):
            return False
        active = self.active or {}
        proof = active.get("native_proof") or {}
        native = intent.get("native_material")
        if not isinstance(native, dict) or not isinstance(native.get("resolution"), dict):
            return False
        manifest = native["resolution"]
        remote_field = self.fields.get(question.get("draft_path"), {}).get("field", {})
        if (
            not proof
            or proof["failed"]
            or self.failed
            or not self.done
            or not isinstance(native, dict)
            or native.get("protocol") != "fixed-material/v1"
            or not {
                "request_id",
                "handoff_id",
                "call_id",
                "arguments_digest",
                "generation",
                "sequence",
                "assistance_ref_digest",
            }
            <= set(native)
            or not isinstance(intent.get("attempt_id"), str)
            or re.fullmatch(r"[a-f0-9]{32}", intent["attempt_id"]) is None
            or proof["intent"] != intent
            or active.get("intent") != intent
            or proof["question"]
            != {key: question.get(key) for key in ("id", "draft_path", "question", "type")}
            or intent.get("field_id") != question.get("id")
            or intent.get("draft_path") != question.get("draft_path")
            or active.get("path") != question.get("draft_path")
            or proof["form"]
            != ((self.form or {}).get("id"), (self.form or {}).get("sourceFormDefinitionId"))
            or proof["remote_field"]
            != {key: remote_field[key] for key in ("path", "title", "type") if key in remote_field}
            or material.get("id") != intent.get("material_id")
            or material.get("sha256") != intent.get("sha256")
            or manifest.get("sha256") != intent.get("sha256")
            or proof["material"] != {key: material.get(key) for key in ("id", "sha256", "filename")}
            or proof["material"]
            != {key: active.get("material", {}).get(key) for key in ("id", "sha256", "filename")}
        ):
            return False
        requests = list(proof["requests"].values())
        required = ["handle", "upload", "link"] if question["type"] == "file" else ["save"]
        if [record["kind"] for record in requests] != required or not all(
            record["verified"] for record in requests
        ):
            return False
        if question["type"] == "file":
            return bool(
                intent.get("action") == "upload"
                and manifest.get("kind") == "file"
                and manifest.get("size_bytes") == active["expected"]
                and material.get("filename") == intent.get("filename") == manifest.get("filename")
                and self.handle
                and self.uploaded
                and self.linked
                and self.files.get(active["path"], {}).get("handle") == self.handle["handle"]
                and self.file_verified(question, material)
            )
        expected = active.get("expected")
        return bool(
            intent.get("action") == "fill"
            and question["type"] in {"text", "textarea"}
            and manifest.get("kind") == "text"
            and isinstance(expected, str)
            and expected == intent.get("expected_value")
            and hashlib.sha256(expected.encode()).hexdigest() == manifest.get("sha256")
            and len(expected.encode()) == manifest.get("size_bytes")
            and self.saved(question, expected)
        )

    def begin(self, question: dict, expected, intent: dict, *, material=None):
        path = question.get("draft_path")
        entry = self.fields.get(path)
        if not entry or fact_for(entry["field"]["title"]) != fact_for(question["question"]):
            raise PortalDataError("draft_identity_changed", "草稿字段或表单身份已变更。", 409)
        self.active = {
            "path": path,
            "expected": expected,
            "intent": intent,
            "type": question["type"],
            "material": material
            or {
                "id": "resume",
                "filename": self.job["filename"],
                "sha256": self.job["file_sha256"],
            },
        }
        self.done = False
        self.sent.clear()
        if (intent.get("native_material") or {}).get("protocol") == "fixed-material/v1":
            self.active["native_proof"] = {
                "intent": deepcopy(intent),
                "question": {
                    key: question.get(key) for key in ("id", "draft_path", "question", "type")
                },
                "material": {
                    key: self.active["material"].get(key) for key in ("id", "sha256", "filename")
                },
                "form": (self.form["id"], self.form["sourceFormDefinitionId"]),
                "remote_field": {
                    key: deepcopy(entry["field"][key])
                    for key in ("path", "title", "type")
                    if key in entry["field"]
                },
                "requests": {},
                "failed": False,
            }
        if question["type"] == "file":
            self.handle, self.uploaded, self.linked = None, False, False

    def saved(self, question: dict, expected) -> bool:
        entry = self.fields.get(question.get("draft_path"), {})
        value = entry.get("fieldValue")
        if question["type"] == "combobox":
            actual = value.get("value") if isinstance(value, dict) else None
            return (
                isinstance(actual, dict)
                and actual.get("text") == expected
                and bool(actual.get("providerLocationId"))
            )
        return isinstance(value, dict) and value.get("value") == expected

    def option_value(self, question: dict, label: str):
        field = self.fields.get(question.get("draft_path"), {}).get("field", {})
        found = [
            option["value"]
            for option in field.get("selectableValues", [])
            if " ".join(option["label"].split()) == label
        ]
        if len(found) != 1:
            raise PortalDataError("ambiguous_option", "服务端选项不唯一，请核验。", 409)
        return found[0]

    def allows(self, request) -> bool:
        a = self.active
        if not a or not self.form:
            return False
        if a["type"] == "file" and not self.handle:
            self._settle("handle")
        if (
            a["type"] == "file"
            and self.handle
            and request.url == self.handle["url"]
            and request.method == "POST"
            and self.handle
            and not self.uploaded
        ):
            parts = multipart_parts(request)
            fields = {**self.handle["fields"], "Content-Type": "application/pdf"}
            names = [p.get_param("name", header="content-disposition") for p in parts]
            if len(names) != len(set(names)) or set(names) != {*fields, "file"}:
                return False
            for name, part in zip(names, parts, strict=True):
                raw = part.get_payload(decode=True)
                if name == "file":
                    if (
                        part.get_filename() != a["material"]["filename"]
                        or part.get_content_type() != "application/pdf"
                        or raw is None
                        or hashlib.sha256(raw).hexdigest() != a["material"]["sha256"]
                    ):
                        return False
                elif raw != fields[name].encode():
                    return False
            return self._permit(request, "upload", None)
        parsed = self.payload(request)
        if not parsed or parsed[1] is None:
            return False
        op, v = parsed
        if op == "ApiSetFormValueToFile" and a["type"] == "file" and not self.uploaded:
            self._settle("upload")
        base = {
            "organizationHostedJobsPageName": self.org,
            "formRenderIdentifier": self.form["id"],
            "formDefinitionIdentifier": self.form["sourceFormDefinitionId"],
            "path": a["path"],
        }
        expected = a["expected"]
        kind = None
        if (
            op == "ApiAutocompleteGeoLocation"
            and a["type"] == "combobox"
            and v == {"text": expected, "locationTypes": ["Country"]}
        ):
            kind = "lookup"
        elif op == "ApiSetFormValue" and a["type"] != "file":
            if a["type"] == "combobox":
                if expected not in self.suggestions:
                    self._settle("lookup")
                if expected not in self.suggestions:
                    return False
                expected = {"text": expected, "providerLocationId": self.suggestions[expected]}
            if v == {**base, "value": expected}:
                kind = "save"
        elif op == "ApiCreateFileUploadHandle" and a["type"] == "file" and not self.handle:
            if v == {
                "organizationHostedJobsPageName": self.org,
                "fileUploadContext": "NonUserFormEngine",
                "filename": a["material"]["filename"],
                "contentType": "application/pdf",
                "contentLength": expected,
            }:
                kind = "handle"
        elif (
            op == "ApiSetFormValueToFile"
            and a["type"] == "file"
            and self.uploaded
            and not self.linked
            and v == {**base, "fileHandle": self.handle["handle"]}
        ):
            kind = "link"
        return self._permit(request, kind, expected) if kind else False

    def _permit(self, request, kind, expected):
        proof = (self.active or {}).get("native_proof")
        if kind in self.sent:
            if proof is not None:
                proof["failed"] = True
            return False
        if proof is not None and proof["intent"] != self.active["intent"]:
            proof["failed"] = True
            return False
        self.sent.add(kind)
        self.pending[request] = (kind, expected)
        if proof is not None:
            proof["requests"][request] = {"kind": kind, "verified": False}
        return True

    def response(self, response):
        pending = self.pending.get(response.request)
        if pending is None:
            return
        proof = (self.active or {}).get("native_proof")
        record = (proof or {}).get("requests", {}).get(response.request)
        if (
            proof is not None
            and pending[0] in {"save", "handle", "upload", "link"}
            and (record is None or proof["intent"] != self.active["intent"])
        ):
            proof["failed"] = True
            raise ValueError("draft response belongs to another material attempt")
        try:
            self._response(response)
        except Exception:
            if proof is not None:
                proof["failed"] = True
            raise
        if record is not None and response.request not in self.pending:
            if (self.active or {}).get("native_proof") is not proof or proof[
                "intent"
            ] != self.active["intent"]:
                proof["failed"] = True
                raise ValueError("active material attempt changed during response")
            record["verified"] = True

    def _response(self, response):
        pending = self.pending.get(response.request)
        if pending is None:
            return
        kind, expected = pending
        if kind == "upload":
            self.pending.pop(response.request)
            if response.status != 204:
                raise ValueError("upload failed")
            self.uploaded = True
            self.counts[kind] = self.counts.get(kind, 0) + 1
            return
        data = response.json()
        # Body reads yield to browser events. A dependent request can finish this
        # same response first. Apply the response once.
        if self.pending.pop(response.request, None) is None:
            return
        if response.status != 200 or data.get("errors") or not isinstance(data.get("data"), dict):
            raise ValueError("draft request failed")
        data = data["data"]
        if kind == "initial":
            posting = data[expected or "jobPosting"]
            if posting["id"] != self.posting or posting["title"] != self.job["role_title"]:
                raise ValueError("posting changed")
            self._form(posting["applicationForm"])
        elif kind == "organization":
            organization = data[expected]
            if not organization["organizationId"] or organization["hostedJobsPageSlug"] != self.org:
                raise ValueError("organization changed")
        elif kind == "lookup":
            found = [s for s in data["result"]["suggestions"] if s["name"] == expected]
            if len(found) == 1 and found[0]["geoLocationPath"][-1]["type"] == "Country":
                self.suggestions[expected] = found[0]["geoLocationPath"][-1]["providerLocationId"]
        elif kind == "handle":
            h = data["fileUploadHandle"]
            if (
                not isinstance(h["handle"], str)
                or not h["handle"]
                or not isinstance(h["fields"], dict)
                or not h["fields"]
                or "file" in h["fields"]
                or "Content-Type" in h["fields"]
                or not all(
                    isinstance(k, str) and isinstance(v, str) for k, v in h["fields"].items()
                )
            ):
                raise ValueError("upload destination changed")
            _job_identity(h["url"], allow_generic=True)
            self.handle = h
        else:
            self._form(data["setFormValue" if kind == "save" else "setFormValueToFile"])
            field = self.fields[self.active["path"]]["fieldValue"]
            if kind == "save":
                if not field or field.get("value") != expected:
                    raise ValueError("draft value mismatch")
            else:
                if (
                    not field
                    or field.get("filename") != self.active["material"]["filename"]
                    or not field.get("id")
                    or self._attachment_conflicts(
                        self.active["path"], field["id"], self.active["material"]["sha256"]
                    )
                ):
                    raise ValueError("file link mismatch")
                self.linked = True
                self.files[self.active["path"]] = {
                    **self.active["material"],
                    "handle": self.handle["handle"],
                    "attachment_id": field["id"],
                }
            self.done = True
        self.counts[kind] = self.counts.get(kind, 0) + 1

    def _settle(self, kind):
        for request, (pending_kind, _) in list(self.pending.items()):
            if pending_kind == kind:
                response = request.response()
                if response is not None:
                    self.response(response)

    def verify(self, observed: dict, resolved: list, expected_for) -> dict:
        covered = {q.get("draft_path"): q for q in observed["fields"]}
        required = {
            path for path, e in self.fields.items() if e["isRequired"] and not e["isHidden"]
        }
        if not required.issubset(covered) or not self.uploaded or not self.linked:
            raise PortalDataError("draft_result_unverified", "服务端必填项或附件未核验。", 409)
        resume_paths = {
            path for path, question in covered.items() if question.get("resume") or path == "resume"
        }
        for path in required | resume_paths:
            question = covered[path]
            if question["type"] == "file":
                material = (
                    {
                        "id": "resume",
                        "filename": self.job["filename"],
                        "sha256": self.job["file_sha256"],
                    }
                    if path in resume_paths
                    else next(
                        (
                            row
                            for row in self.job.get("materials", [])
                            if row.get("draft_path") == path
                        ),
                        None,
                    )
                )
                valid = material is not None and self.file_verified(question, material)
            else:
                value = question.get("value")
                valid = (
                    (
                        isinstance(value, str)
                        and bool(value.strip())
                        or type(value) in {bool, int, float}
                    )
                    and question["valid"]
                    and self.saved(question, expected_for(question, value))
                )
            if not valid:
                raise PortalDataError("draft_result_unverified", "服务端必填项或附件未核验。", 409)
        for q, value, _ in resolved:
            if not self.saved(q, expected_for(q, value)):
                raise PortalDataError(
                    "draft_result_unverified", "页面显示与服务端答案不一致。", 409
                )
        return {
            "action": "draft_transport_verified",
            "required_field_count": len(required),
            "server_readback": True,
            "resume_sha256": self.job["file_sha256"],
            "response_counts": dict(self.counts),
        }

    def _form(self, form):
        if (
            form["errorMessages"]
            or form["formErrors"]
            or not form["id"]
            or not form["sourceFormDefinitionId"]
        ):
            raise ValueError("invalid form")
        if self.form and (form["id"], form["sourceFormDefinitionId"]) != (
            self.form["id"],
            self.form["sourceFormDefinitionId"],
        ):
            raise ValueError("form changed")
        fields = {e["field"]["path"]: e for s in form["sections"] for e in s["fieldEntries"]}
        if len(fields) != sum(len(s["fieldEntries"]) for s in form["sections"]):
            raise ValueError("duplicate field")
        self.form, self.fields = form, fields

    def wait(self, page):

        deadline = time.monotonic() + 12
        while not self.done and not self.failed and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        if self.failed:
            raise PortalDataError(
                "draft_result_unverified", "服务端未确认草稿或附件保存，请核验保留的页面。", 409
            )
        if not self.done:
            raise PortalDataError(
                "draft_result_unknown", "草稿保存或上传结果未确认，请核验保留的页面。", 409
            )
        self.active = None
