"""Explicit pre-JSON LaTeX producer used only by saved-task compatibility tests."""

from career_evidence_graph.application_full_latex import generate_full_latex
from career_evidence_graph.application_resume import ApplicationResumeStore


class LegacyFullLatexFixtureStore(ApplicationResumeStore):
    """Keep the default CLI contract while replaying a historical LaTeX task."""

    def generate_for_task(self, identifier, revision, **options):
        from career_evidence_graph.application_information import (
            material_information_library,
            read_information_library,
        )

        options.pop("force_regenerate", None)
        options.pop("draft_only", None)
        # Preserve the caller's bound material facts. Only an undeclared legacy
        # library uses the explicit synthetic empty-library fallback.
        if "information_library" not in options:
            options["information_library"] = material_information_library(
                self.applications.get_application(identifier), read_information_library(None)
            )
        return generate_full_latex(self, identifier, revision, **options)
