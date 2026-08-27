import json
from pathlib import Path

from career_evidence_graph.audit.workflow import canonical_assistance, parse_assistance


def test_legacy_codex_assisted_reads_and_new_write_is_canonical():
    path = Path("validation/fixtures/stoa/v1/known-good.json")
    raw = path.read_bytes()
    parsed = json.loads(raw)
    assert parse_assistance("codex_assisted") == "coding-agent-assisted"
    assert canonical_assistance("codex_assisted") == "coding-agent-assisted"
    assert path.read_bytes() == raw
    assert any(c["assistance"] == "codex_assisted" for c in parsed["fixture"]["claims"])


def test_new_assistance_is_provider_neutral():
    assert canonical_assistance("codex_assisted") == "coding-agent-assisted"
    assert canonical_assistance("third_party") == "third-party-assisted"
    assert canonical_assistance("none") == "none"
