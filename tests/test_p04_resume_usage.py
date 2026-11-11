"""Resume coverage counts adopted content sources, not offered candidates."""

from career_evidence_graph.application_resume import ApplicationResumeStore


def test_generated_latex_usage_excludes_omitted_and_unused_sources():
    draft = dict.fromkeys(
        (
            "factual_review",
            "source_checkpoint",
            "base_checkpoint",
            "latex_source",
            "verification_queue",
            "analysis_binding",
            "information_library_revision",
        )
    )
    draft.update(
        origin="generated_latex",
        generation_sources=[{"source_id": key} for key in ("used", "omitted", "unused")],
        selected_source_ids=["used", "omitted", "unused"],
        review_groups=[
            {"sources": [{"source_id": "used"}]},
            {"sources": [{"source_id": "used"}, {"source_id": "also-used"}]},
        ],
        omitted_groups=[{"sources": [{"source_id": "omitted"}]}],
    )
    result = ApplicationResumeStore._source_review(draft)
    assert result["used_source_ids"] == ["used", "also-used"]
    assert result["available_review_sources"] == draft["generation_sources"]
