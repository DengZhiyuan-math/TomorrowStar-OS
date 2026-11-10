"""Bounded preparation batches share the single-job flow's snapshot and runner."""

import re
import time
from copy import deepcopy
from uuid import uuid4

from .career_portal_data import PortalDataError
from .validation.hashing import record_digest as digest


class MaterialBatch:
    """Coordinate explicit local material work without application authority."""

    def __init__(self, flow):
        self.flow = flow

    def seal(self, state):
        batch = state.get("preparation_batch")
        if batch:
            batch["revision"] = digest({k: v for k, v in batch.items() if k != "revision"})

    def validate(self, state):
        batches = state.get("preparation_batch_history", [])
        try:
            if not isinstance(batches, list):
                raise ValueError("invalid-history")
            for batch in [state.get("preparation_batch"), *batches]:
                if batch is None:
                    continue
                if not isinstance(batch, dict) or any(
                    not isinstance(batch.get(key), str) or re.fullmatch(pattern, batch[key]) is None
                    for key, pattern in (
                        ("id", r"[a-f0-9]{32}"),
                        ("request_id", r"[a-f0-9]{32}"),
                        ("request_hash", r"[a-f0-9]{64}"),
                        ("revision", r"[a-f0-9]{64}"),
                    )
                ):
                    raise ValueError("invalid-identity")
                if (
                    batch["revision"] != digest({k: v for k, v in batch.items() if k != "revision"})
                    or batch["control"] not in {"paused", "running", "cancelled", "needs_recheck"}
                    or type(batch["epoch"]) is not int
                    or batch["epoch"] < 0
                    or batch["policy_version"] != "preparation-policy/v1.0"
                    or not isinstance(batch["reason"], str)
                    or not isinstance(batch["events"], list)
                    or not all(isinstance(event, dict) for event in batch["events"])
                    or not isinstance(batch["items"], list)
                    or not 1 <= len(batch["items"]) <= 100
                ):
                    raise ValueError("invalid-batch")
                identifiers = set()
                selections = set()
                for row in batch["items"]:
                    if (
                        not isinstance(row, dict)
                        or re.fullmatch(r"[a-f0-9]{24}", row["item_id"]) is None
                        or row["item_id"] in identifiers
                        or row["kind"] not in {"application", "recommendation"}
                        or not isinstance(row["id"], str)
                        or not row["id"]
                        or (row["kind"], row["id"]) in selections
                        or not isinstance(row["revision"], str)
                        or not row["revision"]
                        or row["status"]
                        not in {
                            "pending",
                            "active",
                            "needs_input",
                            "deferred",
                            "stale",
                            "needs_recheck",
                            "waiting_draft_review",
                            "waiting_pdf_review",
                            "waiting_application_record",
                            "cancelled",
                        }
                        or not isinstance(row["reason"], str)
                        or row["task_input_epoch"] is not None
                        and (
                            type(row["task_input_epoch"]) is not int or row["task_input_epoch"] < 0
                        )
                        or row["task_id"] is not None
                        and re.fullmatch(r"[a-f0-9]{32}", row["task_id"]) is None
                    ):
                        raise ValueError("invalid-item")
                    identifiers.add(row["item_id"])
                    selections.add((row["kind"], row["id"]))
                active = next(
                    (r for r in batch["items"] if r["item_id"] == batch["active_item_id"]), None
                )
                if (batch["active_item_id"] is not None and active is None) or (
                    batch["active_task_id"] is not None
                    and (active is None or active["task_id"] != batch["active_task_id"])
                ):
                    raise ValueError("invalid-current-item")
                if "retained_material" in batch or batch.get("kind") == "accepted_material_reuse":
                    task = next(
                        (row for row in state["tasks"] if row["id"] == batch["active_task_id"]),
                        None,
                    )
                    acceptance = (task or {}).get("material_acceptance")
                    requests = batch.get("adoption_requests")
                    if (
                        not task
                        or not acceptance
                        or batch.get("kind") != "accepted_material_reuse"
                        or batch["control"] != "paused"
                        or len(batch["items"]) != 1
                        or active["status"] != "waiting_application_record"
                        or active["task_id"] != task["id"]
                        or active.get("material_acceptance_revision") != acceptance["revision"]
                        or active.get("resume_id") != acceptance["resume_id"]
                        or active.get("pdf_sha256") != acceptance["pdf_sha256"]
                        or batch["retained_material"]
                        != {
                            "task_id": task["id"],
                            "material_acceptance_revision": acceptance["revision"],
                            "resume_id": acceptance["resume_id"],
                            "pdf_sha256": acceptance["pdf_sha256"],
                            "source_sha256": acceptance["source_sha256"],
                        }
                        or not isinstance(requests, list)
                        or not 1 <= len(requests) <= 100
                        or any(
                            not isinstance(row, dict)
                            or set(row) != {"request_id", "request_hash"}
                            or any(
                                not isinstance(row[key], str)
                                or re.fullmatch(pattern, row[key]) is None
                                for key, pattern in (
                                    ("request_id", r"[a-f0-9]{32}"),
                                    ("request_hash", r"[a-f0-9]{64}"),
                                )
                            )
                            for row in requests
                        )
                        or len({row["request_id"] for row in requests}) != len(requests)
                        or {
                            "request_id": batch["request_id"],
                            "request_hash": batch["request_hash"],
                        }
                        not in requests
                    ):
                        raise ValueError("invalid-retained-material-batch")
        except (KeyError, TypeError, ValueError) as error:
            raise PortalDataError(
                "flow_batch_invalid", "材料批次记录不能核验，请保留原件。", 409
            ) from error

    def recover(self, state):
        batch = state.get("preparation_batch")
        if batch and batch["control"] == "running":
            batch.update(control="paused", reason="flow_restarted", epoch=batch["epoch"] + 1)
            return True
        return False

    def snapshot(self, state):
        return deepcopy(state.get("preparation_batch"))

    def request(self, action, payload):
        if not self.flow.preparation_only:
            raise PortalDataError("invalid_flow_batch_request", "材料批次请求无效。")
        if action == "batch-adopt-accepted-material":
            return self._adopt_accepted_material(payload)
        if action != "batch-create":
            return self._operation(action, payload)
        if not isinstance(payload, dict) or set(payload) != {"request_id", "items"}:
            raise PortalDataError("invalid_flow_batch_request", "材料批次字段无效。")
        if (
            not isinstance(payload["request_id"], str)
            or re.fullmatch(r"[a-f0-9]{32}", payload["request_id"]) is None
            or not isinstance(payload["items"], list)
            or not 1 <= len(payload["items"]) <= 100
            or any(
                not isinstance(row, dict)
                or set(row) != {"kind", "id", "revision"}
                or not isinstance(row["kind"], str)
                or row["kind"] not in {"application", "recommendation"}
                or any(not isinstance(row[k], str) or not row[k] for k in ("id", "revision"))
                for row in payload["items"]
            )
        ):
            raise PortalDataError("invalid_flow_batch_request", "请明确选择1至100个岗位。")
        with self.flow.applications.write_lock():
            self.flow._writable()
            state = self.flow._load()
            current = state.get("preparation_batch")
            request_hash = digest(payload)
            replay = next(
                (
                    b
                    for b in [current, *state.get("preparation_batch_history", [])]
                    if b and b["request_id"] == payload["request_id"]
                ),
                None,
            )
            if replay:
                if replay["request_hash"] != request_hash:
                    raise PortalDataError("conflict", "同一次批次选择已变化，请核验原记录。", 409)
                return deepcopy(replay)
            if current and current["control"] != "cancelled":
                raise PortalDataError("flow_batch_exists", "请先处理或取消现有材料批次。", 409)
            if (current and any(r["status"] == "needs_recheck" for r in current["items"])) or any(
                t.get("export_recoveries")
                or t["status"] == "needs_recheck"
                or t.get("worker_ref")
                or any(
                    s["status"] in {"queued", "running", "needs_recheck"}
                    for s in t["stages"].values()
                )
                for t in state["tasks"]
            ):
                raise PortalDataError(
                    "flow_batch_existing_work", "请先暂停并核验已有任务结果。", 409
                )
            candidates = self.flow.callbacks.get("batch_candidates")
            available = (
                candidates()
                if candidates
                else {
                    "applications": self.flow.applications.list_applications(),
                    "recommendations": [],
                }
            )
            items, seen = [], set()
            for selected in payload["items"]:
                key = selected["kind"], selected["id"]
                if key in seen:
                    original = next(r for r in items if (r["kind"], r["id"]) == key)
                    if original["revision"] != selected["revision"]:
                        raise PortalDataError("conflict", "重复岗位包含冲突版本，请重新读取。", 409)
                    continue
                seen.add(key)
                known = next(
                    (r for r in available[selected["kind"] + "s"] if r["id"] == selected["id"]),
                    None,
                )
                if known is None or known.get("revision") != selected["revision"]:
                    raise PortalDataError("conflict", "岗位选择已变化，请重新读取。", 409)
                items.append(
                    dict(selected)
                    | {
                        "item_id": digest(key)[:24],
                        "application_id": selected["id"]
                        if selected["kind"] == "application"
                        else None,
                        "company": known.get("company", ""),
                        "role_title": known.get("role_title", ""),
                        "status": "pending",
                        "reason": "selected",
                        "task_id": None,
                        "task_input_epoch": None,
                    }
                )
            explanations = {
                row["application_id"]: row for row in self.flow._explanations(state)["explanations"]
            }
            for item in items:
                explanation = explanations.get(item["application_id"])
                score = (explanation or {}).get("score")
                item["match_score"] = (
                    score["lower"] if explanation and explanation["fresh"] and score else None
                )
            manual = {
                identifier: index for index, identifier in enumerate(state.get("manual_order", []))
            }
            if manual:
                items.sort(key=lambda row: manual.get(row["application_id"], len(manual)))
            else:
                items.sort(
                    key=lambda row: (
                        -row["match_score"] if row["match_score"] is not None else float("inf")
                    )
                )
            if current:
                state.setdefault("preparation_batch_history", []).append(deepcopy(current))
            state["preparation_batch"] = {
                "id": uuid4().hex,
                "policy_version": "preparation-policy/v1.0",
                "order_mode": "manual" if manual else "match",
                "request_id": payload["request_id"],
                "request_hash": request_hash,
                "control": "paused",
                "reason": "user_selection",
                "epoch": 0,
                "active_item_id": None,
                "active_task_id": None,
                "items": items,
                "events": [],
            }
            self.seal(state)
            self.flow._save(state)
            return self.snapshot(state)

    def _adopt_accepted_material(self, payload):
        if (
            not isinstance(payload, dict)
            or set(payload) != {"request_id", "task_id", "task_revision"}
            or any(
                not isinstance(payload[key], str) or re.fullmatch(pattern, payload[key]) is None
                for key, pattern in (
                    ("request_id", r"[a-f0-9]{32}"),
                    ("task_id", r"[a-f0-9]{32}"),
                    ("task_revision", r"[a-f0-9]{64}"),
                )
            )
        ):
            raise PortalDataError("invalid_flow_batch_request", "既有材料批次字段无效。")
        with self.flow.applications.write_lock():
            state, task = self.flow._checked(payload["task_id"], payload["task_revision"])
            self.flow._retained_material_current(task)
            acceptance = task.get("material_acceptance")
            if (
                not acceptance
                or not task["materials_confirmed"]
                or task["status"] != "materials_ready"
            ):
                raise PortalDataError(
                    "flow_batch_material_acceptance_required",
                    "请先保存此版本已有的真人材料决定。",
                    409,
                )
            binding = {
                "task_id": task["id"],
                "material_acceptance_revision": acceptance["revision"],
                "resume_id": task["resume_id"],
                "pdf_sha256": task["resume_sha256"],
                "source_sha256": acceptance["source_sha256"],
            }
            request = {"request_id": payload["request_id"], "request_hash": digest(payload)}
            current = state.get("preparation_batch")
            for batch in [current, *state.get("preparation_batch_history", [])]:
                if not batch:
                    continue
                known = next(
                    (
                        row
                        for row in [
                            {
                                "request_id": batch["request_id"],
                                "request_hash": batch["request_hash"],
                            },
                            *batch.get("adoption_requests", []),
                        ]
                        if row["request_id"] == request["request_id"]
                    ),
                    None,
                )
                if known:
                    if known != request or batch.get("retained_material") != binding:
                        raise PortalDataError("conflict", "同一次材料复用请求已绑定其他版本。", 409)
                    return deepcopy(batch)
            if current and current.get("retained_material") == binding:
                aliases = current.setdefault("adoption_requests", [])
                if len(aliases) >= 100:
                    raise PortalDataError(
                        "flow_batch_exists", "既有材料复用请求已达记录上限。", 409
                    )
                aliases.append(request)
                self._save(state)
                return self.snapshot(state)
            if current and current["control"] != "cancelled":
                raise PortalDataError("flow_batch_exists", "请保留并处理现有材料批次。", 409)
            if current:
                state.setdefault("preparation_batch_history", []).append(deepcopy(current))
            application = self.flow.applications.get_application(task["application_id"])
            item_id = digest(("application", task["application_id"]))[:24]
            state["preparation_batch"] = {
                "id": uuid4().hex,
                "kind": "accepted_material_reuse",
                "policy_version": "preparation-policy/v1.0",
                "order_mode": "retained",
                "request_id": request["request_id"],
                "request_hash": request["request_hash"],
                "control": "paused",
                "reason": "waiting_application_record",
                "epoch": 0,
                "active_item_id": item_id,
                "active_task_id": task["id"],
                "retained_material": binding,
                "adoption_requests": [request],
                "items": [
                    {
                        "item_id": item_id,
                        "kind": "application",
                        "id": task["application_id"],
                        "revision": task["application_revision"],
                        "application_id": task["application_id"],
                        "company": application.get("company", ""),
                        "role_title": application.get("role_title", ""),
                        "status": "waiting_application_record",
                        "reason": "waiting_application_record",
                        "task_id": task["id"],
                        "task_input_epoch": task.get("input_epoch", 0),
                        "task_inputs": deepcopy(task["inputs"]),
                        "match_score": None,
                        "resume_id": task["resume_id"],
                        "pdf_sha256": task["resume_sha256"],
                        "material_acceptance_revision": acceptance["revision"],
                    }
                ],
                "events": [{"action": "adopt_accepted_material", "at": time.time()}],
            }
            self._save(state)
            return self.snapshot(state)

    @staticmethod
    def _unknown_tasks(state):
        return any(
            task.get("export_recoveries")
            or task["status"] == "needs_recheck"
            or any(stage["status"] == "needs_recheck" for stage in task["stages"].values())
            for task in state["tasks"]
        )

    @staticmethod
    def _export_reconciled(item, task):
        binding = item.get("unknown_export")
        proof = task.get("export_recheck") or {}
        stage = task["stages"].get("export", {})
        expected = {
            "attempt_id": stage.get("attempt_id"),
            "draft_id": task.get("draft_id"),
            "draft_sha256": task.get("draft_sha256"),
            "input_epoch": task.get("input_epoch", 0),
        }
        return (
            bool(binding)
            and binding == expected
            and all(proof.get(key) == value for key, value in expected.items())
            and proof.get("status") == stage.get("status")
            and stage.get("status") in {"complete", "failed"}
        )

    def _checked(self, payload):
        self.flow._writable()
        state = self.flow._load()
        batch = state.get("preparation_batch")
        if not batch or payload["batch_id"] != batch["id"]:
            raise PortalDataError("flow_batch_not_found", "找不到此材料批次。", 404)
        if payload["batch_revision"] != batch["revision"]:
            raise PortalDataError("conflict", "材料批次已变化，请重新读取。", 409)
        return state, batch

    def _enqueue(self, batch):
        if batch["control"] == "running":
            self.flow._queue.put((batch["id"], "batch", batch["epoch"]))

    def _save(self, state):
        self.seal(state)
        self.flow._save(state)

    def _operation(self, action, payload):
        fields = {
            "batch-control": {"batch_id", "batch_revision", "operation"},
            "batch-retry": {"batch_id", "batch_revision", "item_id"},
            "batch-reorder": {"batch_id", "batch_revision", "item_id", "direction"},
        }
        if (
            action not in fields
            or not isinstance(payload, dict)
            or set(payload) != fields[action]
            or any(not isinstance(v, str) or not v for v in payload.values())
        ):
            raise PortalDataError("invalid_flow_batch_request", "材料批次字段无效。")
        with self.flow.applications.write_lock():
            state, batch = self._checked(payload)
            if action == "batch-control":
                operation = payload["operation"]
                if operation not in {"pause", "resume", "cancel"}:
                    raise PortalDataError("invalid_flow_batch_request", "材料批次操作无效。")
                if batch.get("kind") == "accepted_material_reuse":
                    if operation == "pause":
                        return self.snapshot(state)
                    raise PortalDataError(
                        "flow_batch_application_record_required",
                        "既有材料已保存；真实申请继续暂停。",
                        409,
                    )
                if self._unknown_tasks(state):
                    raise PortalDataError(
                        "flow_batch_recheck_required", "结果未明，请先核验已有回执。", 409
                    )
                if batch["control"] == "cancelled":
                    raise PortalDataError("flow_batch_cancelled", "此批次已取消，请保留记录。", 409)
                if any(row["status"] == "needs_recheck" for row in batch["items"]):
                    if operation == "resume":
                        self._resolve_rechecks(state, batch)
                    elif operation == "pause":
                        return self.snapshot(state)
                    else:
                        raise PortalDataError(
                            "flow_batch_recheck_required", "结果未明，请先核验。", 409
                        )
                if operation == "resume" and any(
                    row["status"] == "waiting_application_record" for row in batch["items"]
                ):
                    raise PortalDataError(
                        "flow_batch_application_record_required",
                        "材料已完成；真实申请暂停，等待申请记录。",
                        409,
                    )
                target = {"resume": "running", "pause": "paused", "cancel": "cancelled"}[operation]
                if batch["control"] == target:
                    return self.snapshot(state)
                batch.update(control=target, reason="user_" + operation, epoch=batch["epoch"] + 1)
                batch["events"].append({"action": operation, "at": time.time()})
                self._save(state)
                if operation == "cancel":
                    task = next(
                        (t for t in state["tasks"] if t["id"] == batch["active_task_id"]), None
                    )
                    if task and task["status"] != "cancelled":
                        self.flow.cancel(task["id"], task["revision"])
                        state = self.flow._load()
                        batch = state["preparation_batch"]
                    for row in batch["items"]:
                        if row["status"] in {
                            "pending",
                            "active",
                            "waiting_draft_review",
                            "waiting_pdf_review",
                        }:
                            row.update(status="cancelled", reason="user_cancel")
                    batch.update(active_item_id=None, active_task_id=None)
                    self._save(state)
                elif operation == "resume":
                    task = next(
                        (t for t in state["tasks"] if t["id"] == batch["active_task_id"]), None
                    )
                    if task:
                        for stage, value in task["stages"].items():
                            if value["status"] == "queued":
                                self.flow._queue.put((task["id"], stage, value["attempt_id"]))
                self._enqueue(batch)
                return self.snapshot(state)
            if batch["control"] == "cancelled":
                raise PortalDataError("flow_batch_cancelled", "此批次已取消。", 409)
            if self._unknown_tasks(state) or any(
                row["status"] == "needs_recheck" for row in batch["items"]
            ):
                raise PortalDataError("flow_batch_recheck_required", "结果未明，请先核验。", 409)
            item = next((r for r in batch["items"] if r["item_id"] == payload["item_id"]), None)
            if item is None:
                raise PortalDataError("flow_batch_item_missing", "找不到所选批次岗位。", 404)
            if action == "batch-reorder":
                if payload["direction"] not in {"up", "down"} or item["status"] != "pending":
                    raise PortalDataError("flow_batch_reorder_invalid", "只能调整未开始岗位。", 409)
                pending = [r for r in batch["items"] if r["status"] == "pending"]
                position = pending.index(item)
                target = position + (-1 if payload["direction"] == "up" else 1)
                if 0 <= target < len(pending):
                    left, right = batch["items"].index(item), batch["items"].index(pending[target])
                    batch["items"][left], batch["items"][right] = (
                        batch["items"][right],
                        batch["items"][left],
                    )
                    batch["order_mode"] = "manual"
                    batch["events"].append(
                        {
                            "action": "reorder",
                            "item_id": item["item_id"],
                            "direction": payload["direction"],
                            "at": time.time(),
                        }
                    )
            else:
                if item["status"] not in {"deferred", "needs_input", "stale"}:
                    raise PortalDataError(
                        "flow_batch_retry_invalid", "仅能手动重试已知待处理岗位。", 409
                    )
                candidates = self.flow.callbacks.get("batch_candidates")
                available = (
                    candidates()
                    if candidates
                    else {
                        "applications": self.flow.applications.list_applications(),
                        "recommendations": [],
                    }
                )
                candidate = next(
                    (r for r in available[item["kind"] + "s"] if r["id"] == item["id"]), None
                )
                if candidate is None:
                    raise PortalDataError("flow_batch_item_missing", "岗位来源暂不可读。", 409)
                task = next(
                    (row for row in state["tasks"] if row["id"] == item.get("task_id")), None
                )
                if task and task["application_id"] != item.get("application_id", item["id"]):
                    raise PortalDataError(
                        "flow_batch_task_mismatch", "批次岗位与任务绑定不符，请保留原记录。", 409
                    )
                reuse_synced = (
                    candidate["revision"] == item["revision"]
                    and task is not None
                    and task["status"] in {"draft", "stale"}
                    and task["stages"]["analysis"]["status"] == "pending"
                    and not task.get("worker_ref")
                    and not any(
                        row["status"] in {"queued", "running", "needs_recheck"}
                        for row in task["stages"].values()
                    )
                )
                if reuse_synced:
                    # Explicit retry repairs legacy synced/stale state, never a read or restart.
                    self.flow._group_guard_change(task)
                    self.flow._fresh(task, stage="analysis")
                    task["status"] = "draft"
                item.setdefault("binding_history", []).append(
                    {
                        k: deepcopy(item.get(k))
                        for k in (
                            "revision",
                            "task_id",
                            "task_input_epoch",
                            "task_inputs",
                            "status",
                            "reason",
                        )
                    }
                )
                item["force_new"] = (
                    item["status"] == "stale" or candidate["revision"] != item["revision"]
                ) and not reuse_synced
                item.update(
                    revision=candidate["revision"],
                    status="pending",
                    reason="user_retry",
                    retry=True,
                )
                batch["events"].append(
                    {"action": "retry", "item_id": item["item_id"], "at": time.time()}
                )
            self._save(state)
            self._enqueue(batch)
            return self.snapshot(state)

    def _resolve_rechecks(self, state, batch):
        candidates = self.flow.callbacks.get("batch_candidates")
        available = candidates() if candidates else {}
        for item in batch["items"]:
            if item["status"] != "needs_recheck":
                continue
            task = next((t for t in state["tasks"] if t["id"] == item["task_id"]), None)
            if task is not None and self._export_reconciled(item, task):
                self.after_task(state, task)
                continue
            candidate = next(
                (
                    r
                    for r in available.get("recommendations", [])
                    if item["kind"] == "recommendation" and r["id"] == item["id"]
                ),
                None,
            )
            if (
                candidate
                and (item.get("unknown_source") or {}).get("acquisition_checkpoint")
                == "needs_recheck"
                and candidate.get("acquisition_checkpoint") in {"complete", "failed"}
                and candidate.get("selection_status") != "needs_recheck"
            ):
                item.setdefault("binding_history", []).append(deepcopy(item["unknown_source"]))
                complete = candidate["acquisition_checkpoint"] == "complete"
                item.update(
                    revision=candidate["revision"],
                    status="pending" if complete else "deferred",
                    reason="source_verified" if complete else "source_required",
                )
                batch.update(active_item_id=None, active_task_id=None)
                continue
            if (
                candidate
                and candidate.get("selection_status") == "saved"
                and candidate.get("existing_application")
                and candidate.get("acquisition_checkpoint") != "needs_recheck"
            ):
                item.update(
                    revision=candidate["revision"],
                    status="pending",
                    reason="saved_selection_verified",
                )
                batch.update(active_item_id=None, active_task_id=None)
                continue
            raise PortalDataError(
                "flow_batch_recheck_required", "结果未明，请先核验已有回执。", 409
            )
        batch.update(control="paused", reason="result_verified", epoch=batch["epoch"] + 1)

    def guard_start(self, state, task, stage):
        batch = state.get("preparation_batch")
        if not batch and (
            stage in {"resume", "export"}
            and task["stages"].get("export", {}).get("status") == "needs_recheck"
            # An explicit letter or letter PDF retry redoes only that unknown stage.
            or stage in {"letter", "letter_export"}
            and task["stages"].get(stage, {}).get("status") == "needs_recheck"
        ):
            return
        if (
            self._unknown_tasks(state)
            or batch
            and any(r["status"] == "needs_recheck" for r in batch["items"])
        ):
            raise PortalDataError("flow_batch_recheck_required", "结果未明，请先核验。", 409)
        if not batch or batch["control"] == "cancelled":
            return
        if batch["control"] != "running" or batch["active_task_id"] != task["id"]:
            raise PortalDataError("flow_batch_paused", "请在当前材料批次中继续该岗位。", 409)
        item = next(row for row in batch["items"] if row["item_id"] == batch["active_item_id"])
        if item["status"] == "waiting_application_record":
            raise PortalDataError(
                "flow_batch_application_record_required", "材料已完成；等待申请记录。", 409
            )

    def guard_admission(self, state, task):
        batch = state.get("preparation_batch")
        if (
            self._unknown_tasks(state)
            or batch
            and any(r["status"] == "needs_recheck" for r in batch["items"])
        ):
            return False
        return (
            not batch
            or batch["control"] == "cancelled"
            or (batch["control"] == "running" and batch["active_task_id"] == task["id"])
        )

    def _dispose(self, batch, item, status, reason):
        # Recovery can observe the same bound endpoint more than once.
        target = {"needs_recheck": "needs_recheck", "waiting_application_record": "paused"}.get(
            status
        )
        if (
            target is not None
            and item["status"] == status
            and item["reason"] == reason
            and batch["control"] == target
            and batch["reason"] == reason
        ):
            return
        item.update(status=status, reason=reason)
        if status == "needs_recheck":
            batch.update(control="needs_recheck", reason=reason, epoch=batch["epoch"] + 1)
        elif status in {"deferred", "needs_input", "stale", "cancelled"}:
            batch.update(active_item_id=None, active_task_id=None)
        elif status == "waiting_application_record" and batch["control"] != "cancelled":
            batch.update(control="paused", reason=reason, epoch=batch["epoch"] + 1)
        batch["events"].append(
            {"action": status, "item_id": item["item_id"], "reason": reason, "at": time.time()}
        )

    def after_task(self, state, task):
        batch = state.get("preparation_batch")
        if not batch or batch["active_task_id"] != task["id"]:
            return
        item = next(row for row in batch["items"] if row["item_id"] == batch["active_item_id"])
        if batch["control"] == "cancelled":
            return
        old = deepcopy(item)
        status = task["status"]
        if item["status"] == "needs_recheck" and status != "needs_recheck":
            if not self._export_reconciled(item, task):
                batch.update(control="needs_recheck", reason="flow_result_needs_recheck")
                return
            item.setdefault("export_recheck_history", []).append(
                {"binding": item.pop("unknown_export"), "proof": deepcopy(task["export_recheck"])}
            )
            batch.update(control="paused", reason="result_verified", epoch=batch["epoch"] + 1)
        if item["task_input_epoch"] != task.get("input_epoch", 0):
            self._dispose(batch, item, "stale", "flow_inputs_changed")
        elif status == "needs_recheck":
            export = task["stages"].get("export", {})
            if export.get("status") == "needs_recheck":
                item.setdefault(
                    "unknown_export",
                    {
                        "attempt_id": export.get("attempt_id"),
                        "draft_id": task.get("draft_id"),
                        "draft_sha256": task.get("draft_sha256"),
                        "input_epoch": task.get("input_epoch", 0),
                    },
                )
            self._dispose(batch, item, "needs_recheck", "flow_result_needs_recheck")
        elif status in {"failed", "export_failed", "cancelled", "stale"}:
            reason = next(
                (row["error_code"] for row in task["stages"].values() if row.get("error_code")),
                "flow_" + status,
            )
            self._dispose(
                batch,
                item,
                "stale"
                if status == "stale"
                else "cancelled"
                if status == "cancelled"
                else "deferred",
                reason,
            )
        elif status == "draft_ready":
            review = task.get("draft_review") or {}
            reviewed = all(
                review.get(key) == value
                for key, value in {
                    "status": "reviewed",
                    "actor": "user",
                    "draft_id": task.get("draft_id"),
                    "draft_sha256": task.get("draft_sha256"),
                    "analysis_id": task.get("analysis_id"),
                    "input_revision": digest(task["inputs"]),
                }.items()
            )
            if task.get("origin") == "generated_latex":
                try:
                    self.flow._reviewed_groups(task)
                except PortalDataError:
                    reviewed = False
                else:
                    reviewed = True
            item.update(
                status="active" if reviewed else "waiting_draft_review",
                reason="draft_reviewed" if reviewed else "draft_review_required",
            )
        elif status == "resume_ready":
            item.update(status="waiting_pdf_review", reason="pdf_review_required")
        elif status == "materials_ready":
            self._dispose(batch, item, "waiting_application_record", "waiting_application_record")
        else:
            item.update(status="active", reason=status)
        if old != item:
            self._enqueue(batch)

    def _failed(self, state, batch, item, error):
        code = getattr(error, "code", "flow_batch_needs_recheck")
        if code in {"intake_busy", "intake_unavailable", "flow_runtime_busy"}:
            item.update(status="pending", reason=code)
            batch.update(
                control="paused",
                reason=code,
                active_item_id=None,
                active_task_id=None,
                epoch=batch["epoch"] + 1,
            )
            self._save(state)
            return
        unknown = not isinstance(error, PortalDataError) or any(
            marker in code for marker in ("needs_recheck", "unknown", "uncertain", "pending")
        )
        if unknown and item["kind"] == "recommendation":
            candidates = self.flow.callbacks.get("batch_candidates")
            if candidates:
                try:
                    candidate = next(
                        (
                            r
                            for r in candidates().get("recommendations", [])
                            if r["id"] == item["id"]
                        ),
                        {},
                    )
                    item["unknown_source"] = {
                        k: candidate.get(k)
                        for k in ("acquisition_checkpoint", "selection_status", "revision")
                    }
                except (OSError, ValueError, TypeError, KeyError):
                    pass
        disposition = (
            "needs_recheck" if unknown else "stale" if code == "flow_inputs_stale" else "deferred"
        )
        self._dispose(batch, item, disposition, code)
        self._save(state)
        self._enqueue(batch)

    def advance(self, batch_id, epoch):
        """Admit at most one local stage, only from the existing serial runner."""
        with self.flow.applications.write_lock():
            state = self.flow._load()
            batch = state.get("preparation_batch")
            if not batch or (batch["id"], batch["epoch"], batch["control"]) != (
                batch_id,
                epoch,
                "running",
            ):
                return
            if batch.get("kind") == "accepted_material_reuse":
                return
            if self._unknown_tasks(state):
                batch.update(control="needs_recheck", reason="flow_result_needs_recheck")
                self._save(state)
                return
            item = next(
                (r for r in batch["items"] if r["item_id"] == batch["active_item_id"]), None
            )
            if item is None:
                item = next((r for r in batch["items"] if r["status"] == "pending"), None)
                if item is None:
                    batch.update(control="paused", reason="no_processable_items")
                    self._save(state)
                    return
                batch["active_item_id"] = item["item_id"]
                item.update(status="active", reason="selecting")
                self._save(state)
                try:
                    select = self.flow.callbacks.get("batch_select")
                    application = (
                        select(deepcopy(item))
                        if select
                        else (
                            self.flow.applications.get_application(item["id"])
                            if item["kind"] == "application"
                            else None
                        )
                    )
                    if (
                        application
                        and item["kind"] == "application"
                        and application.get("revision") != item["revision"]
                    ):
                        raise PortalDataError(
                            "conflict", "岗位记录已变化，请明确重试当前版本。", 409
                        )
                    if not application or not application.get("job_description", "").strip():
                        raise PortalDataError("source_required", "请先取得完整岗位来源。", 409)
                    if application.get("status", "drafting") != "drafting":
                        raise PortalDataError(
                            "application_already_in_progress",
                            "原岗位记录已有申请进度，请先核验。",
                            409,
                        )
                    task = self.flow.create(
                        application["id"],
                        application["revision"],
                        force_new=item.pop("force_new", False),
                    )
                except (PortalDataError, OSError, ValueError, TypeError, KeyError) as error:
                    state = self.flow._load()
                    self._failed(
                        state,
                        state["preparation_batch"],
                        next(
                            r
                            for r in state["preparation_batch"]["items"]
                            if r["item_id"] == item["item_id"]
                        ),
                        error,
                    )
                    return
                state = self.flow._load()
                batch = state["preparation_batch"]
                item = next(r for r in batch["items"] if r["item_id"] == batch["active_item_id"])
                item.update(
                    application_id=application["id"],
                    task_id=task["id"],
                    task_input_epoch=task.get("input_epoch", 0),
                    task_inputs=deepcopy(task["inputs"]),
                )
                batch["active_task_id"] = task["id"]
                self._save(state)
            else:
                task = next((t for t in state["tasks"] if t["id"] == item["task_id"]), None)
                if task is None:
                    self._failed(
                        state,
                        batch,
                        item,
                        PortalDataError("flow_batch_task_missing", "岗位任务缺失。", 409),
                    )
                    return
            retrying = item.get("retry") and task["status"] in {"failed", "export_failed"}
            if not retrying:
                self.after_task(state, task)
            self._save(state)
            if batch["active_task_id"] != task["id"] or batch["control"] != "running":
                return
            try:
                self.flow._fresh(task)
                if retrying:
                    stage = next(
                        name
                        for name, value in task["stages"].items()
                        if value["status"] == "failed"
                    )
                elif task["status"] == "draft":
                    stage = "analysis"
                elif task["status"] == "analysis_ready":
                    from .application_draft import resume_language_policy
                    from .application_explanations import qualification_for

                    application = self.flow.applications.get_application(task["application_id"])
                    library = (
                        self.flow.information_provider() if self.flow.information_provider else None
                    )
                    qualification = qualification_for(task, application, library)
                    if qualification["status"] not in {"supported", "not_specified"}:
                        self._dispose(batch, item, "needs_input", "flow_qualification_required")
                        self._save(state)
                        self._enqueue(batch)
                        return
                    if (
                        resume_language_policy(application["job_description"])["status"]
                        == "needs_input"
                    ):
                        self._dispose(batch, item, "needs_input", "flow_resume_language_required")
                        self._save(state)
                        self._enqueue(batch)
                        return
                    stage = "resume"
                elif task["status"] == "draft_ready" and item["status"] == "active":
                    # Résumé, then letter, then export, as in Flow.prepare.
                    stage = (
                        "letter"
                        if self.flow.letter_due(task)
                        else "letter_export"
                        if self.flow.letter_export_due(task)
                        else "export"
                    )
                else:
                    return
                self.flow.start(task["id"], task["revision"], stage, retry=bool(retrying))
            except (PortalDataError, OSError, ValueError) as error:
                state = self.flow._load()
                batch = state["preparation_batch"]
                item = next(r for r in batch["items"] if r["item_id"] == batch["active_item_id"])
                self._failed(state, batch, item, error)


def batch_candidates(applications, intake):
    """Applications and recommendations a preparation batch may select from."""
    source = intake.snapshot() if intake else {}
    return {
        "applications": applications.list_applications(),
        "recommendations": source.get("recommendations", []),
        "intake_status": source.get("status", "unavailable"),
    }


def select_batch_item(applications, intake, item):
    """Resolve one batch item to its current drafting application with a complete JD."""
    if item["kind"] == "application":
        application = applications.get_application(item["id"])
        if application["revision"] != item["revision"]:
            raise PortalDataError("conflict", "岗位记录已变化，请明确重试当前版本。", 409)
    else:
        if intake is None:
            raise PortalDataError("intake_unavailable", "推荐记录暂不可用。", 409)
        source = intake.snapshot()
        if source["status"] == "running":
            raise PortalDataError("intake_busy", "推荐读取尚在进行，请稍后明确继续。", 409)
        row = next((r for r in source["recommendations"] if r["id"] == item["id"]), None)
        if row is None or row["revision"] != item["revision"]:
            raise PortalDataError("conflict", "岗位来源已变化，请核验当前版本。", 409)
        if row.get("acquisition_checkpoint") == "needs_recheck" or (
            row.get("selection_status") == "needs_recheck"
        ):
            raise PortalDataError(
                "recommendation_needs_recheck", "先核验本岗已有来源或保存回执。", 409
            )
        selected = intake.select(item["id"], item["revision"])
        application = selected["application"]
        if any(
            application.get(key, "").strip() != row.get(key, "").strip()
            for key in ("company", "role_title", "location", "job_description")
        ):
            raise PortalDataError(
                "flow_batch_jd_conflict", "已有岗位记录与推荐原文不同，请先核验。", 409
            )
    if not application.get("job_description", "").strip():
        raise PortalDataError("recommendation_jd_incomplete", "请先取得完整 JD。", 409)
    if application["status"] != "drafting":
        raise PortalDataError(
            "flow_batch_existing_application", "已有申请结果，请先核验原记录。", 409
        )
    return application
