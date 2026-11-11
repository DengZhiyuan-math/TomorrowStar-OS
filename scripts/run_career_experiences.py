"""Organize career bodies and their derived directory in an explicit private library."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(argv=None):
    from career_evidence_graph.application_career_library import CareerLibrary
    from career_evidence_graph.career_portal_data import PortalDataError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "action",
        choices=(
            "sync",
            "directory",
            "read",
            "save",
            "preview-import",
            "import",
            "upgrade-facts",
            "education",
            "save-education",
        ),
    )
    parser.add_argument("--candidate-id", action="append", default=[])
    parser.add_argument("--request", type=Path, help="Private JSON containing save arguments.")
    args = parser.parse_args(argv)
    library = CareerLibrary(args.manifest)
    try:
        if args.action == "directory":
            result = library.index()
        elif args.action == "sync":
            result = library.sync_experiences(args.candidate_id or None)
        elif args.action == "upgrade-facts":
            result = library.upgrade_experience_facts(args.candidate_id or None)
        elif args.action == "education":
            result = library.education()
        elif args.action == "save-education":
            if args.request is None:
                parser.error("save-education requires --request")
            result = library.save_education(**json.loads(args.request.read_text(encoding="utf-8")))
        else:
            if len(args.candidate_id) != 1:
                parser.error("read/save/import require exactly one --candidate-id")
            if args.action in {"save", "preview-import", "import"}:
                if args.request is None:
                    parser.error("save/import require --request")
                request = json.loads(args.request.read_text(encoding="utf-8"))
                if args.action == "save":
                    result = library.save_experience(args.candidate_id[0], **request)
                elif args.action == "preview-import":
                    result = library.preview_experience_import(args.candidate_id[0], request)
                else:
                    result = library.import_experience(args.candidate_id[0], request)
            else:
                result = library.read_experience(args.candidate_id[0])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        code = error.code if isinstance(error, PortalDataError) else "invalid-experience-request"
        # Paths and source content belong only in successful private data output.
        print(json.dumps({"error": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
