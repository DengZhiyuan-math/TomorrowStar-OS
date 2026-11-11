"""Read the local Markdown tracker without changing tickets or application state."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

EXCLUDED = {"before", "history", "baseline", "candidate", "payload", "tests", "fixtures"}


FIELDS = {
    "Status",
    "Assignee",
    "Triage",
    "Interaction",
    "Type",
    "Claim state",
    "Blocked by",
    "Closure reason",
}
CLOSED = {"closed", "resolved"}


def metadata(text: str, path: str, errors: list, warnings: list) -> dict:
    header = re.split(r"^#{2,}\s", text, maxsplit=1, flags=re.M)[0]
    fields = {}
    for key, value in re.findall(
        r"^(?:\*\*)?([\w ]+?)(?:\*\*)?:[ \t]*(?:\*\*)?[ \t]*([^\n]*)$", header, re.M
    ):
        if key not in FIELDS:
            continue
        if key in fields:
            errors.append({"path": path, "code": "invalid_metadata", "field": key})
            fields[key] = None
        else:
            fields[key] = value.strip() or None
    if fields.get("Status") not in CLOSED | {"open", "claimed"}:
        errors.append({"path": path, "code": "invalid_metadata", "field": "Status"})
    owner = fields.get("Assignee")
    if owner in {None, "unknown", "unrecorded"}:
        fields["Assignee"] = None
        warnings.append({"path": path, "code": "unknown_metadata", "field": "Assignee"})
    return fields


def valid_explanation(text: str) -> bool:
    # Historical notes can explicitly separate satisfied gates and independent review.
    for clause in re.split(r"[。；;]", text):
        if re.search(r"[\[\]()]", clause):
            return False
        if re.search(r"\d", clause) and not re.fullmatch(
            r"[ \t]*\d{2}[^\d]*(?:门槛已满足|单独保留)[ \t]*", clause
        ):
            return False
    return True


def dependencies(ticket: dict, rows: dict, root: Path, errors: list, warnings: list) -> list:
    name = ticket["path"]
    raw = ticket["blocked_by"]
    if raw is None:
        warnings.append({"path": name, "code": "unknown_metadata", "field": "Blocked by"})
        ticket["dependencies_known"] = False
        return []
    targets = re.findall(r"\[[^]\n]+\]\(([^)\n]+)\)", raw)
    resolved = []
    if targets:
        residue = re.sub(r"\[[^]\n]+\]\(([^)\n]+)\)", "", raw)
        prefix, _, explanation = residue.partition("。")
        if not re.fullmatch(r"[ \t,，、;；.]*", prefix) or not valid_explanation(explanation):
            errors.append({"path": name, "code": "invalid_dependency_declaration"})
            ticket["dependencies_known"] = False
        for target in targets:
            path = (root / name).parent.joinpath(target.split("#", 1)[0]).resolve()
            resolved.append(path.relative_to(root).as_posix() if path.is_relative_to(root) else "")
    elif re.fullmatch(
        r"(?:none|无(?:前置(?:依赖)?|依赖)?)(?:[ \t]*\([^()\d\[\]]*\))?[.]?",
        re.split(r"[；;。]", raw, maxsplit=1)[0],
        re.I,
    ):
        note = re.split(r"[；;。]", raw, maxsplit=1)
        if len(note) > 1 and not valid_explanation(note[1]):
            errors.append({"path": name, "code": "invalid_dependency_declaration"})
            ticket["dependencies_known"] = False
        return []
    elif re.fullmatch(r"\d+(?:[ ,，、]+\d+)*", raw):
        for number in re.findall(r"\d+", raw):
            choices = [
                n
                for n in rows
                if Path(n).parent == Path(name).parent and Path(n).name.startswith(number + "-")
            ]
            if len(choices) != 1:
                errors.append(
                    {"path": name, "code": "ambiguous_or_missing_dependency", "target": number}
                )
                ticket["dependencies_known"] = False
            else:
                resolved.append(choices[0])
    else:
        errors.append({"path": name, "code": "invalid_dependency_declaration"})
        ticket["dependencies_known"] = False
    for target in resolved:
        if target not in rows:
            errors.append(
                {"path": name, "code": "missing_or_noncanonical_dependency", "target": target}
            )
            ticket["dependencies_known"] = False
    return sorted(set(target for target in resolved if target in rows))


PUBLICATION = Path(".scratch/tomorrowstar-ticket-consolidation-2026-10-17/publication.json")


def counts(tickets: list) -> dict:
    return {
        "total": len(tickets),
        "closed_or_resolved": sum(t["status"] in CLOSED for t in tickets),
        "unclosed": sum(t["status"] not in CLOSED for t in tickets),
        "administrative_superseded": sum(t["closure_reason"] == "superseded" for t in tickets),
        "status_counts": dict(Counter(t["status"] or "unknown" for t in tickets)),
    }


def release_scopes(rows: dict, root: Path, errors: list) -> dict:
    scopes = {
        "all": counts(list(rows.values())),
        "map_directories": counts(
            [t for n, t in rows.items() if (root / n).parent.parent.joinpath("map.md").is_file()]
        ),
    }
    unavailable = {"available": False, "reason": "publication_missing"}
    scopes.update(original_published=unavailable, current_delivery=unavailable)
    path = root / PUBLICATION
    if any(p.is_symlink() for p in (path, path.parent, path.parent.parent)):
        errors.append({"path": PUBLICATION.as_posix(), "code": "invalid_publication"})
        scopes.update(
            original_published={"available": False, "reason": "unsafe_publication"},
            current_delivery={"available": False, "reason": "unsafe_publication"},
        )
        return scopes
    if not path.exists():
        return scopes
    try:
        data = json.loads(path.read_text())
        groups = []
        for key, field in [
            ("records", "canonical_path"),
            ("superseded", "path"),
            ("completed_evidence_preserved", "path"),
        ]:
            items = data[key]
            if not isinstance(items, list):
                raise ValueError
            names = [item[field] for item in items]
            if any(not isinstance(n, str) or n not in rows for n in names):
                raise ValueError
            if len(set(names)) != len(names):
                raise ValueError
            groups.append(set(names))
        original, administrative, preserved = groups
        if not original or original & (administrative | preserved) or administrative & preserved:
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        errors.append({"path": PUBLICATION.as_posix(), "code": "invalid_publication"})
        scopes.update(
            original_published={"available": False, "reason": "invalid_publication"},
            current_delivery={"available": False, "reason": "invalid_publication"},
        )
        return scopes
    directories = {Path(n).parent for n in original}
    current = {n for n in rows if Path(n).parent in directories} - administrative - preserved
    for key, names in [("original_published", original), ("current_delivery", current)]:
        scopes[key] = {
            "available": True,
            **counts([rows[n] for n in sorted(names)]),
            "paths": sorted(names),
        }
    return scopes


def ticket_paths(root: Path, errors: list) -> list[Path]:
    scratch = root / ".scratch"
    if scratch.is_symlink() or not scratch.is_dir():
        errors.append({"path": ".scratch", "code": "tracker_unavailable"})
        return []
    paths = []
    for group in sorted(scratch.iterdir()):
        if group.name in EXCLUDED:
            continue
        if group.is_symlink():
            errors.append({"path": group.relative_to(root).as_posix(), "code": "unsafe_path"})
            continue
        if not group.is_dir():
            continue
        issues = group / "issues"
        if issues.is_symlink():
            errors.append({"path": issues.relative_to(root).as_posix(), "code": "unsafe_path"})
            continue
        if not issues.is_dir():
            continue
        for path in sorted(issues.glob("*.md")):
            if path.name.lower() in {"readme.md", "map.md", "index.md"}:
                continue
            if path.is_symlink() or not path.is_file():
                errors.append({"path": path.relative_to(root).as_posix(), "code": "unsafe_path"})
            else:
                paths.append(path)
    return paths


def query(root: Path) -> dict:
    tickets = []
    errors = []
    warnings = []
    for path in ticket_paths(root, errors):
        name = path.relative_to(root).as_posix()
        try:
            text = path.read_text()
        except (OSError, UnicodeError):
            errors.append({"path": name, "code": "unreadable_ticket"})
            text = "# Unreadable ticket\n"
        fields = metadata(text, name, errors, warnings)
        interaction = fields.get("Interaction")
        claim_unknown = "Claim state" in fields
        if claim_unknown:
            warnings.append({"path": name, "code": "unknown_metadata", "field": "Claim state"})
        tickets.append(
            {
                "path": name,
                "title": text.splitlines()[0].lstrip("# ") if text.splitlines() else "",
                "status": fields.get("Status"),
                "assignee": fields.get("Assignee"),
                "triage": fields.get("Triage"),
                "interaction": interaction,
                "type": fields.get("Type"),
                "claim_state": fields.get("Claim state"),
                "ownership_known": fields.get("Assignee") is not None and not claim_unknown,
                "closure_reason": fields.get("Closure reason"),
                "blocked_by": fields.get("Blocked by"),
                "dependencies_known": True,
                "requires_human": "HITL" in (interaction or "")
                or fields.get("Type") == "grilling"
                or fields.get("Triage") == "needs-info",
                "paused_route": path.parent.parent.name == "single-job-application-flow-2026-10-16",
            }
        )
    rows = {t["path"]: t for t in tickets}
    for t in tickets:
        t["direct_dependencies"] = dependencies(t, rows, root, errors, warnings)
        t["mechanical_frontier"] = (
            not any(e["path"] == t["path"] for e in errors)
            and t["status"] == "open"
            and t["assignee"] == "none"
            and t["ownership_known"]
            and t["dependencies_known"]
            and all(
                rows[d]["status"] in CLOSED and rows[d]["closure_reason"] != "superseded"
                for d in t["direct_dependencies"]
            )
        )
    for t in tickets:
        if t["status"] not in CLOSED:
            for d in t["direct_dependencies"]:
                if rows[d]["closure_reason"] == "superseded":
                    errors.append(
                        {"path": t["path"], "code": "active_dependency_on_superseded", "target": d}
                    )
    try:
        TopologicalSorter({t["path"]: t["direct_dependencies"] for t in tickets}).prepare()
    except CycleError as exc:
        errors.append({"path": exc.args[1][0], "code": "dependency_cycle", "cycle": exc.args[1]})
    scopes = release_scopes(rows, root, errors)
    if errors:
        for t in tickets:
            t["mechanical_frontier"] = False
    return {
        "tickets": tickets,
        "scopes": scopes,
        "mechanical_frontier": [t["path"] for t in tickets if t["mechanical_frontier"]],
        "execution_authorized": False,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="Print the full JSON report")
    args = parser.parse_args()
    report = query(args.root.resolve())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for name, scope in report["scopes"].items():
            print(
                name
                + ": "
                + json.dumps({k: v for k, v in scope.items() if k != "paths"}, ensure_ascii=False)
            )
        print("execution_authorized=false; mechanical frontier does not grant execution permission")
        for t in report["tickets"]:
            if t["status"] not in CLOSED:
                print(
                    json.dumps(
                        {
                            k: t[k]
                            for k in (
                                "path",
                                "status",
                                "assignee",
                                "claim_state",
                                "ownership_known",
                                "triage",
                                "interaction",
                                "type",
                                "dependencies_known",
                                "direct_dependencies",
                                "mechanical_frontier",
                                "requires_human",
                                "paused_route",
                            )
                        },
                        ensure_ascii=False,
                    )
                )
        for kind in ("errors", "warnings"):
            for diagnostic in report[kind]:
                print(kind + ": " + json.dumps(diagnostic, ensure_ascii=False))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
