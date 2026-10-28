"""Hand source-bound experience fragments to TomorrowStar without running a model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(argv=None):
    from career_evidence_graph import application_experience_latex as generation
    from career_evidence_graph.application_career_library import CareerLibrary
    from career_evidence_graph.application_resume import (
        ApplicationResumeStore,
        career_source_snapshot,
    )
    from career_evidence_graph.career_portal_data import (
        ApplicationStore,
        CareerCatalog,
        PortalDataError,
    )
    from career_evidence_graph.workspace import open_private_workspace

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--applications", type=Path, required=True)
    parser.add_argument("--career-workspace", type=Path, required=True)
    parser.add_argument("--career-library-manifest", type=Path)
    parser.add_argument("--resume-root", type=Path, required=True)
    parser.add_argument(
        "action",
        choices=(
            "prepare",
            "status",
            "context",
            "writer",
            "configure",
            "read",
            "fragment",
            "assemble",
            "review",
            "review-context",
            "adopt",
        ),
    )
    parser.add_argument("--generation-id")
    parser.add_argument(
        "--request", type=Path, help="UTF-8 JSON arguments for the selected operation"
    )
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.request.read_text(encoding="utf-8")) if args.request else {}
        if not isinstance(request, dict):
            raise ValueError("The request must be a JSON object.")
        store = ApplicationResumeStore(
            ApplicationStore(args.applications),
            CareerCatalog(
                open_private_workspace(
                    args.career_workspace, public_root=Path(__file__).resolve().parents[1]
                )
            ),
            args.resume_root,
            career_library=CareerLibrary(args.career_library_manifest)
            if args.career_library_manifest is not None
            else None,
        )
        with store.applications.write_lock():
            if args.action == "prepare":
                # An explicitly delivered snapshot is already fixed upstream input.
                if "source_snapshot" not in request:
                    request["source_snapshot"] = career_source_snapshot(
                        store.catalog, career_library=store.career_library
                    )
                result = generation.prepare_generation(store, **request)
            else:
                if not args.generation_id:
                    parser.error("This operation requires --generation-id.")
                operation = {
                    "status": generation.generation_state,
                    "context": generation.generation_context,
                    "writer": generation.writer_context,
                    "configure": generation.configure_generation,
                    "read": generation.read_source,
                    "fragment": generation.submit_fragment,
                    "assemble": generation.assemble_generation,
                    "review": generation.review_generation,
                    "review-context": generation.review_context,
                    "adopt": generation.adopt_generation,
                }[args.action]
                result = operation(store, args.generation_id, **request)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except PortalDataError as error:
        print(
            json.dumps({"error": error.code, "message": error.message}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, TypeError) as error:
        print(
            json.dumps({"error": "invalid_request", "message": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
