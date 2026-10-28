"""Sync a selected private public presentation into an existing Astro checkout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from career_evidence_graph.public_site import export_public_site, load_public_site  # noqa: E402
from career_evidence_graph.workspace import open_private_workspace  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TomorrowStar public website projection")
    parser.add_argument("action", choices=("check", "export"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--website", type=Path)
    args = parser.parse_args(argv)
    try:
        workspace = open_private_workspace(args.workspace.expanduser())
        source = workspace / "reports/public-site/site-content.json"
        if args.action == "check":
            payload = load_public_site(source)
            print(json.dumps({"valid": True, "revision": payload["revision"]}))
            return 0
        if args.website is None:
            parser.error("export requires --website")
        website = args.website.expanduser()
        if website.is_symlink() or not (website / "astro.config.mjs").is_file():
            raise ValueError("public-site-website-invalid")
        website = website.resolve(strict=True)
        system = Path(__file__).resolve().parents[1]
        for root in (workspace, system):
            if website.is_relative_to(root) or root.is_relative_to(website):
                raise ValueError("public-site-workspaces-overlap")
        # Validate before creating any destination directory.
        load_public_site(source)
        destination = website / "src/content/generated/career.json"
        if any(parent.is_symlink() for parent in destination.parents):
            raise ValueError("public-site-destination-unsafe")
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(json.dumps(export_public_site(source, destination)))
        return 0
    except (OSError, ValueError):
        # Validation errors can contain private input values. Keep stdout/stderr content-free.
        print(
            "Public website sync failed. Check the selected source and folder boundaries.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
