"""Strict contracts and offline validation primitives."""

from .acceptance import evaluate_functional_acceptance
from .models import FormalRunManifest, ProvenanceRegistry, ReplayResult, ValidationCharter

__all__ = [
    "FormalRunManifest",
    "ProvenanceRegistry",
    "ReplayResult",
    "ValidationCharter",
    "evaluate_functional_acceptance",
]
