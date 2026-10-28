"""Information aliases and scopes are usable without loading an executor."""

import subprocess
import sys
from pathlib import Path

import pytest

from career_evidence_graph import application_information as information
from career_evidence_graph import application_worker as legacy_worker


def test_information_import_does_not_load_application_worker():
    source = Path(__file__).resolve().parents[1] / "src"
    program = (
        f"import sys; sys.path.insert(0, {str(source)!r}); "
        "import career_evidence_graph.application_information; "
        "assert 'career_evidence_graph.application_worker' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", program], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("EMAIL ADDRESS:", "email"),
        ("English proficiency CEFR", "language_english_cefr"),
        ("French proficiency CEFR", "language_french_cefr"),
        ("Current Academic Degree", "academic_degree"),
        ("Do you require visa sponsorship now or in the future?", "sponsorship_now_future"),
        ("Do you require visa sponsorship now?", "question:do you require visa sponsorship now"),
    ],
)
def test_reviewed_aliases_keep_their_existing_meaning(question, expected):
    assert information.fact_for(question) == expected
    assert legacy_worker.fact_for(question) == expected


def test_information_owns_scope_checks_and_worker_keeps_direct_compatibility_exports():
    context = {"company": "Synthetic", "country": "CHE", "application_id": "synthetic-job"}
    assert information.scope_matches({}, context)
    assert information.scope_matches({"country": "CHE"}, context)
    assert not information.scope_matches({"country": "GBR"}, context)
    assert not information.scope_matches({"other": "CHE"}, context)
    assert {"CHE", "USA", "GBR", "DEU", "FRA", "CAN", "OTHER"} == information.COUNTRIES
    assert legacy_worker.fact_for is information.fact_for
    assert legacy_worker.scope_matches is information.scope_matches
    assert legacy_worker.COUNTRIES is information.COUNTRIES
