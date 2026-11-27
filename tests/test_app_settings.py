"""The 设置 page saves each setting into the file its reader already uses."""

import json

import pytest

from career_evidence_graph.application_computer_use import preferred_executor
from career_evidence_graph.application_match_scoring import score_tier
from career_evidence_graph.application_settings import Settings, score_thresholds
from career_evidence_graph.career_portal_data import PortalDataError


@pytest.fixture
def settings(tmp_path):
    for name in ("flow", "fill"):
        (tmp_path / name).mkdir()
    portal = tmp_path / "portal.json"
    portal.write_text(
        json.dumps(
            {
                "applications": "/synthetic/applications",
                "career_workspace": "/synthetic/career",
                "takeover_executor": "codex",
                "automatic_takeover": True,
                "match_second_opinion_claude_config": "~/.claude-synthetic",
            }
        )
    )
    return Settings(flow_root=tmp_path / "flow", fill_root=tmp_path / "fill", portal_config=portal)


def test_defaults_read_from_the_existing_files(settings):
    snapshot = settings.snapshot()
    assert snapshot["fill_executor"]["value"] == "codex"
    assert snapshot["score_thresholds"]["value"] == {"skip_below": 15, "manual_from": 75}
    assert snapshot["target_companies"]["value"] == []
    assert snapshot["mail_and_flow"]["value"] == {
        "application_processed_label": "",
        "automatic_takeover": True,
        "match_second_opinion_claude_config": "~/.claude-synthetic",
    }


def test_each_section_is_saved_where_its_reader_looks(settings, tmp_path):
    result = settings.save(
        {
            "fill_executor": "claude",
            "score_thresholds": {"skip_below": 30, "manual_from": 80},
            "target_companies": [" Mistral ", "mistral", "", "Synthetic AG"],
        }
    )
    assert result["restart_required"] is False
    assert preferred_executor(tmp_path / "fill") == "claude"
    assert score_thresholds(tmp_path / "flow") == {"skip_below": 30, "manual_from": 80}
    saved = json.loads((tmp_path / "flow/target-companies.json").read_text())
    assert saved == {"companies": ["Mistral", "Synthetic AG"]}
    lines = score_thresholds(tmp_path / "flow")
    assert score_tier({"upper": 25}, thresholds=lines) == "skip"
    assert score_tier({"upper": 50}, thresholds=lines) == "auto"
    assert score_tier({"upper": 80}, thresholds=lines) == "manual"


def test_mail_and_flow_keep_other_portal_keys_and_ask_for_a_restart(settings, tmp_path):
    result = settings.save(
        {
            "mail_and_flow": {
                "application_processed_label": " Jobs/Done ",
                "automatic_takeover": False,
                "match_second_opinion_claude_config": "",
            }
        }
    )
    assert result["restart_required"] is True
    portal = json.loads((tmp_path / "portal.json").read_text())
    assert portal["applications"] == "/synthetic/applications"
    assert portal["takeover_executor"] == "codex"
    assert portal["application_processed_label"] == "Jobs/Done"
    assert portal["automatic_takeover"] is False
    assert "match_second_opinion_claude_config" not in portal


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"unknown": 1},
        {"fill_executor": "other"},
        {"score_thresholds": {"skip_below": 80, "manual_from": 70}},
        {"score_thresholds": {"skip_below": 10, "manual_from": 101}},
        {"target_companies": "Mistral"},
    ],
)
def test_invalid_settings_change_nothing(settings, tmp_path, payload):
    with pytest.raises(PortalDataError):
        settings.save(payload)
    assert not (tmp_path / "flow/score-thresholds.json").exists()
    assert not (tmp_path / "fill/fill-executor.json").exists()


def test_a_section_without_its_file_is_unavailable(tmp_path):
    settings = Settings()
    assert not settings.snapshot()["mail_and_flow"]["available"]
    with pytest.raises(PortalDataError):
        settings.save({"fill_executor": "claude"})


def test_without_saved_lines_the_tiers_are_unchanged():
    assert score_tier({"upper": 14.9}) == "skip"
    assert score_tier({"upper": 15}) == "auto"
    assert score_tier({"upper": 75}) == "manual"
    assert score_tier({"upper": 50}, needs_review=True) == "approve"


def test_a_model_disagreement_asks_only_when_the_tiers_differ():
    from career_evidence_graph.application_match_scoring import score_tier

    def models(first, second):
        return {"needs_review": True, "primary": {"upper": first}, "second": {"upper": second}}

    assert score_tier({"upper": 50}, models=models(40, 60)) == "auto"
    assert score_tier({"upper": 72}, models=models(65, 80)) == "approve"
