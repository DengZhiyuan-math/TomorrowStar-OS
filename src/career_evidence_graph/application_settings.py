"""The settings the App's 设置 page reads and saves (2026-11-16, user request).

Each setting stays in the file that already holds it, so the code that reads it is
unchanged: the fill executor in the fill root, target companies and score thresholds
in the flow root, and the mail and automatic-flow options in the App's portal.json,
which the native App reads when it opens.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._vendor import job_apply_store as helper
from .career_portal_data import PortalDataError

SCORE_THRESHOLDS = "score-thresholds.json"
TARGET_COMPANIES = "target-companies.json"
FILL_EXECUTOR = "fill-executor.json"
# Below skip_below a job is skipped; from manual_from on it is prepared for manual review.
DEFAULT_THRESHOLDS = {"skip_below": 15, "manual_from": 75}
# portal.json keys this page may change; the App applies them when it reopens.
PORTAL_KEYS = (
    "application_processed_label",
    "automatic_takeover",
    "match_second_opinion_claude_config",
)


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _thresholds(value):
    if not isinstance(value, dict):
        return None
    skip, manual = value.get("skip_below"), value.get("manual_from")
    if not all(type(number) is int for number in (skip, manual)) or not 0 <= skip < manual <= 100:
        return None
    return {"skip_below": skip, "manual_from": manual}


def score_thresholds(flow_root):
    """The saved score lines, or the defaults when none are saved or they are invalid."""
    saved = _read(Path(flow_root) / SCORE_THRESHOLDS) if flow_root else None
    return _thresholds(saved) or dict(DEFAULT_THRESHOLDS)


def _companies(value):
    if not isinstance(value, list) or len(value) > 200:
        return None
    names = []
    for name in value:
        if not isinstance(name, str) or len(name.strip()) > 120:
            return None
        if name.strip() and name.strip().casefold() not in {item.casefold() for item in names}:
            names.append(name.strip())
    return names


class Settings:
    def __init__(self, *, flow_root=None, fill_root=None, portal_config=None):
        self.flow_root = Path(flow_root) if flow_root else None
        self.fill_root = Path(fill_root) if fill_root else None
        self.portal_config = Path(portal_config) if portal_config else None

    def _portal(self):
        return _read(self.portal_config) if self.portal_config else None

    def snapshot(self):
        portal = self._portal()
        executor = _read(self.fill_root / FILL_EXECUTOR) if self.fill_root else None
        companies = _read(self.flow_root / TARGET_COMPANIES) if self.flow_root else None
        return {
            "schema_version": "app-settings/v1",
            "fill_executor": {
                "available": self.fill_root is not None,
                "value": "claude" if (executor or {}).get("executor") == "claude" else "codex",
            },
            "score_thresholds": {
                "available": self.flow_root is not None,
                "value": score_thresholds(self.flow_root),
                "default": dict(DEFAULT_THRESHOLDS),
            },
            "target_companies": {
                "available": self.flow_root is not None,
                "value": _companies((companies or {}).get("companies")) or [],
            },
            "mail_and_flow": {
                "available": portal is not None,
                "value": {
                    "application_processed_label": (portal or {}).get(
                        "application_processed_label"
                    )
                    or "",
                    "automatic_takeover": (portal or {}).get("automatic_takeover") is not False,
                    "match_second_opinion_claude_config": (portal or {}).get(
                        "match_second_opinion_claude_config"
                    )
                    or "",
                },
            },
        }

    def save(self, payload):
        """Save the sections present in ``payload``; returns the new snapshot."""
        sections = {"fill_executor", "score_thresholds", "target_companies", "mail_and_flow"}
        if not isinstance(payload, dict) or not payload or not set(payload) <= sections:
            raise PortalDataError("settings_invalid", "设置内容无效，请刷新后重试。", 400)
        current = self.snapshot()
        for key in payload:
            if not current[key]["available"]:
                raise PortalDataError("settings_unavailable", "此项设置在当前环境不可用。", 409)
        writes = []
        if "fill_executor" in payload:
            if payload["fill_executor"] not in {"codex", "claude"}:
                raise PortalDataError("settings_invalid", "请选择 Codex 或 Claude。", 400)
            writes.append(
                (self.fill_root / FILL_EXECUTOR, {"executor": payload["fill_executor"]})
            )
        if "score_thresholds" in payload:
            thresholds = _thresholds(payload["score_thresholds"])
            if thresholds is None:
                raise PortalDataError(
                    "settings_invalid", "门槛须为 0–100 的整数，且跳过线低于手动线。", 400
                )
            writes.append((self.flow_root / SCORE_THRESHOLDS, thresholds))
        if "target_companies" in payload:
            companies = _companies(payload["target_companies"])
            if companies is None:
                raise PortalDataError("settings_invalid", "公司名称过长或数量过多。", 400)
            writes.append((self.flow_root / TARGET_COMPANIES, {"companies": companies}))
        if "mail_and_flow" in payload:
            value = payload["mail_and_flow"]
            if (
                not isinstance(value, dict)
                or set(value) != set(PORTAL_KEYS)
                or not isinstance(value["application_processed_label"], str)
                or len(value["application_processed_label"]) > 200
                or not isinstance(value["automatic_takeover"], bool)
                or not isinstance(value["match_second_opinion_claude_config"], str)
                or len(value["match_second_opinion_claude_config"]) > 1000
            ):
                raise PortalDataError("settings_invalid", "邮件与自动流程设置无效。", 400)
            portal = dict(self._portal())
            portal["automatic_takeover"] = value["automatic_takeover"]
            for key in ("application_processed_label", "match_second_opinion_claude_config"):
                # An empty field removes the option, as before it was set.
                if value[key].strip():
                    portal[key] = value[key].strip()
                else:
                    portal.pop(key, None)
            writes.append((self.portal_config, portal))
        for path, value in writes:
            helper.atomic_write_json(path, value)
        return self.snapshot() | {"restart_required": "mail_and_flow" in payload}
