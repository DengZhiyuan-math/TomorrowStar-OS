"""One explicit byte-budget policy shared by reading, matching and quote recovery.

This module reads only the supplied environment (or the process environment). It
has no model, material-store, reader or matcher dependency.
"""

from __future__ import annotations

import os
import re

from .career_portal_data import PortalDataError

MAX_MATCH_CONTEXT_BYTES = 128_000
MAX_MATERIAL_CONTEXT_BYTES = 60_000


def context_limits(environment=None) -> dict:
    """Return validated match/material limits from one run's environment.

    Missing values use the retained defaults. An implicit material limit adapts
    below a smaller match limit; an explicitly incompatible pair fails closed.
    Consumers configure runs through this Interface, not copied module constants.
    """
    environment = dict(os.environ) if environment is None else environment
    values = {}
    for name, variable, default in (
        ("match_context_bytes", "TOMORROWSTAR_MATCH_CONTEXT_BYTES", MAX_MATCH_CONTEXT_BYTES),
        (
            "material_context_bytes",
            "TOMORROWSTAR_MATERIAL_CONTEXT_BYTES",
            MAX_MATERIAL_CONTEXT_BYTES,
        ),
    ):
        raw = environment.get(variable, str(default))
        if (
            not isinstance(raw, str)
            or re.fullmatch(r"[0-9]+", raw) is None
            or len(raw.lstrip("0")) > 7
        ):
            raise PortalDataError(
                "match_context_limits_invalid",
                "分析上下文字节预算必须是正整数且不得超过 1 MiB。",
                409,
            )
        values[name] = int(raw.lstrip("0") or "0")
    if "TOMORROWSTAR_MATERIAL_CONTEXT_BYTES" not in environment:
        values["material_context_bytes"] = min(
            values["material_context_bytes"], values["match_context_bytes"] - 1
        )
    if not (0 < values["material_context_bytes"] < values["match_context_bytes"] <= 1_048_576):
        raise PortalDataError(
            "match_context_limits_invalid",
            "资料预算必须小于完整分析预算；完整分析预算不得超过 1 MiB。",
            409,
        )
    return values
