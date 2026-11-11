"""Read or explicitly adopt application records in a selected tracker directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(argv=None):
    from career_evidence_graph.career_portal_data import ApplicationStore, PortalDataError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("action", choices=("list", "read", "preview-import", "import"))
    parser.add_argument("--id")
    parser.add_argument("--expected-revision")
    args = parser.parse_args(argv)
    if args.action != "list" and not args.id:
        parser.error("read/import require --id")
    if args.action in {"preview-import", "import"} and not args.expected_revision:
        parser.error("import requires --expected-revision from a current read")
    try:
        store = ApplicationStore(args.root)
        if args.action == "list":
            result = store.list_applications()
        elif args.action == "read":
            result = store.get_application(args.id)
        else:
            action = (
                store.preview_application_import
                if args.action == "preview-import"
                else store.import_application
            )
            result = action(args.id, expected_revision=args.expected_revision)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        code = error.code if isinstance(error, PortalDataError) else "invalid-application-request"
        print(json.dumps({"error": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
