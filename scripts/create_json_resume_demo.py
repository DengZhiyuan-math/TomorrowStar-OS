"""Create a synthetic JSON resume slice in a new directory; never open the App."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHECKOUT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New synthetic output directory")
    args = parser.parse_args()
    destination = args.destination.expanduser()
    if destination.exists() or destination.is_symlink():
        parser.error("Destination already exists; choose a new directory.")

    from career_evidence_graph.application_resume_content import assemble_content
    from career_evidence_graph.application_resume_render import render_resume

    sample = json.loads(
        (CHECKOUT / "tests/fixtures/json_resume/single-experience.json").read_text(encoding="utf-8")
    )
    content = assemble_content(**sample)
    rendered = render_resume(content)
    metadata = asdict(rendered)
    metadata.pop("tex")
    input_json = json.dumps(sample, ensure_ascii=False, indent=2) + "\n"
    metadata.update(
        input_sha256=hashlib.sha256(input_json.encode("utf-8")).hexdigest(),
        tex_sha256=hashlib.sha256(rendered.tex.encode("utf-8")).hexdigest(),
    )
    files = {
        "input.json": input_json,
        "resume.json": json.dumps(content, ensure_ascii=False, indent=2) + "\n",
        "render.json": json.dumps(
            {
                "schema_version": "resume-render-manifest/v1",
                "synthetic": True,
                "operation": "render_only",
                **metadata,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
    try:
        destination.mkdir(mode=0o700)
        for name, value in files.items():
            with (destination / name).open("x", encoding="utf-8") as output:
                output.write(value)
        with (destination / "main.tex").open("x", encoding="utf-8") as output:
            output.write(rendered.tex)
    except FileExistsError:
        parser.error("Destination already exists; choose a new directory.")
    except OSError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
