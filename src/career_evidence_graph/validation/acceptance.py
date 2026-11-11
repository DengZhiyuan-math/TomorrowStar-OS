"""Deterministic blocker evaluation for the functional charter."""

from __future__ import annotations

from collections.abc import Iterable

from .models import CriticalNegativeCase, FunctionalAcceptanceEvaluation


def evaluate_functional_acceptance(
    cases: Iterable[CriticalNegativeCase],
    *,
    strengths_observed: Iterable[str] = (),
) -> FunctionalAcceptanceEvaluation:
    """Block on every triggered critical case without averaging strengths."""
    blocking_classes = sorted({case.blocker_class for case in cases if case.triggered})
    return FunctionalAcceptanceEvaluation(
        schema_version="functional-acceptance-evaluation/v1",
        decision="block" if blocking_classes else "pass",
        blocking_classes=blocking_classes,
        strengths_observed=list(strengths_observed),
    )
