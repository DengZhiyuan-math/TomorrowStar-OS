"""MC-18/MC-19 dependency ratchet: no new mutual imports or private access.

The baseline records the current state of ``src/career_evidence_graph``. New items
fail; removed items also fail so the baseline is tightened in the same change.
Function-local imports are scanned but are not errors by themselves. MC-19 adds a
per-file count, across src and tests/, of private attribute uses on the Flow,
Pipeline and Resume store receivers; any increase or unrecorded decrease fails.
"""

import ast
import json
from pathlib import Path

PACKAGE = "career_evidence_graph"
SOURCE_ROOT = Path(__file__).parents[1] / "src"
BASELINE = Path(__file__).parent / "fixtures" / "dependency-ratchet-v1.json"
REPO_ROOT = Path(__file__).parents[1]
COUNTED_ROOTS = (SOURCE_ROOT / PACKAGE, Path(__file__).parent)
PRIVATE_RECEIVERS = {
    "flow",
    "self.flow",
    "pipeline",
    "store",
    "ApplicationFlowService",
    "ApplicationResumeStore",
}


def module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def load_sources(root: Path = SOURCE_ROOT) -> dict[str, tuple[str, bool]]:
    """Return {module: (source, is_package)} for every package module."""
    return {
        module_name(path, root): (path.read_text(encoding="utf-8"), path.name == "__init__.py")
        for path in sorted((root / PACKAGE).rglob("*.py"))
    }


def import_edges(sources: dict[str, tuple[str, bool]]) -> tuple[set, set]:
    """Return intra-package (importer, imported) edges and private (importer, source, name)."""
    edges, private = set(), set()
    for importer, (source, is_package) in sources.items():
        package = importer if is_package else importer.rpartition(".")[0]
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                targets = [(alias.name, None) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    anchor = package.split(".")[: len(package.split(".")) - node.level + 1]
                    base = ".".join([*anchor, *([base] if base else [])])
                targets = [(base, alias.name) for alias in node.names]
            else:
                continue
            for base, name in targets:
                if base != PACKAGE and not base.startswith(PACKAGE + "."):
                    continue
                submodule = f"{base}.{name}" if name else None
                target = submodule if submodule in sources else base
                if target != importer:
                    edges.add((importer, target))
                is_private = name and name.startswith("_") and not name.endswith("__")
                if is_private and base != importer:
                    private.add((importer, base, name))
    return edges, private


def ratchet_items(sources: dict[str, tuple[str, bool]]) -> dict[str, set[str]]:
    edges, private = import_edges(sources)
    mutual = {f"{a} <-> {b}" for a, b in edges if a < b and (b, a) in edges}
    private_imports = {f"{importer} imports {source}.{name}" for importer, source, name in private}
    return {"mutual_import_pairs": mutual, "private_cross_module_imports": private_imports}


def ratchet_failures(current: dict[str, set[str]], baseline: dict[str, list[str]]) -> list[str]:
    failures = []
    for kind, items in current.items():
        recorded = set(baseline[kind])
        failures += [f"new {kind}: {item}" for item in sorted(items - recorded)]
        failures += [
            f"resolved {kind}: {item} -- remove it from {BASELINE.name} (update the baseline)"
            for item in sorted(recorded - items)
        ]
    return failures


def private_attribute_uses(source: str) -> int:
    """Count ``receiver._name`` reads/writes for the recorded receivers (dunders excluded)."""
    return sum(
        isinstance(node, ast.Attribute)
        and node.attr.startswith("_")
        and not node.attr.endswith("__")
        and ast.unparse(node.value) in PRIVATE_RECEIVERS
        for node in ast.walk(ast.parse(source))
    )


def private_attribute_counts(paths=None) -> dict[str, int]:
    """Return {repository-relative path: count} for files with at least one use."""
    if paths is None:
        paths = sorted(path for root in COUNTED_ROOTS for path in root.rglob("*.py"))
    counts = {}
    for path in paths:
        count = private_attribute_uses(path.read_text(encoding="utf-8"))
        if count:
            counts[path.relative_to(REPO_ROOT).as_posix()] = count
    return counts


def private_use_failures(current: dict[str, int], baseline: dict[str, int]) -> list[str]:
    failures = []
    for path in sorted(set(current) | set(baseline)):
        now, recorded = current.get(path, 0), baseline.get(path, 0)
        if now > recorded:
            failures.append(f"new private_attribute_uses: {path} {recorded} -> {now}")
        elif now < recorded:
            failures.append(
                f"resolved private_attribute_uses: {path} {recorded} -> {now}"
                f" -- record it in {BASELINE.name} (update the baseline)"
            )
    return failures


def test_dependency_ratchet_matches_baseline():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures = ratchet_failures(ratchet_items(load_sources()), baseline)
    assert not failures, "\n".join(failures)


def _synthetic(**modules: str) -> dict[str, tuple[str, bool]]:
    sources = {PACKAGE: ("", True), f"{PACKAGE}.sub": ("", True)}
    for name, source in modules.items():
        dotted = f"{PACKAGE}.{name.replace('__', '.')}"
        sources[dotted] = (source, False)
    return sources


def test_detector_reports_new_cycle_and_private_import_by_name():
    sources = _synthetic(
        a="from .b import public\n",
        b="def f():\n    from career_evidence_graph import a\n",
        c="from career_evidence_graph.sub.d import _helper, __all__\n",
        sub__d="from ..a import _private\nfrom . import e\n",
        sub__e="import career_evidence_graph.sub.d\n",
    )
    items = ratchet_items(sources)
    assert items == {
        "mutual_import_pairs": {
            "career_evidence_graph.a <-> career_evidence_graph.b",
            "career_evidence_graph.sub.d <-> career_evidence_graph.sub.e",
        },
        "private_cross_module_imports": {
            "career_evidence_graph.c imports career_evidence_graph.sub.d._helper",
            "career_evidence_graph.sub.d imports career_evidence_graph.a._private",
        },
    }
    empty = {"mutual_import_pairs": [], "private_cross_module_imports": []}
    failures = ratchet_failures(items, empty)
    assert (
        "new mutual_import_pairs: career_evidence_graph.a <-> career_evidence_graph.b" in failures
    )
    assert (
        "new private_cross_module_imports: "
        "career_evidence_graph.c imports career_evidence_graph.sub.d._helper"
    ) in failures


def test_detector_asks_to_update_baseline_when_an_item_is_removed():
    stale = {
        "mutual_import_pairs": ["career_evidence_graph.x <-> career_evidence_graph.y"],
        "private_cross_module_imports": [],
    }
    failures = ratchet_failures(ratchet_items(_synthetic(x="import os\n")), stale)
    assert failures == [
        "resolved mutual_import_pairs: career_evidence_graph.x <-> career_evidence_graph.y"
        f" -- remove it from {BASELINE.name} (update the baseline)"
    ]


def test_real_snapshot_injection_fails_with_specific_names():
    sources = load_sources()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    source, is_package = sources[f"{PACKAGE}.jd"]
    sources[f"{PACKAGE}.jd"] = (source + "\nfrom .cli import _not_public\n", is_package)
    source, is_package = sources[f"{PACKAGE}.cli"]
    sources[f"{PACKAGE}.cli"] = (source + "\ndef _late():\n    from . import jd\n", is_package)
    failures = ratchet_failures(ratchet_items(sources), baseline)
    assert (
        "new mutual_import_pairs: career_evidence_graph.cli <-> career_evidence_graph.jd"
        in failures
    )
    assert (
        "new private_cross_module_imports: "
        "career_evidence_graph.jd imports career_evidence_graph.cli._not_public"
    ) in failures


def test_private_attribute_uses_match_baseline():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    failures = private_use_failures(private_attribute_counts(), baseline["private_attribute_uses"])
    assert not failures, "\n".join(failures)


def test_private_attribute_counter_reports_receivers_and_both_directions(tmp_path):
    source = (
        "flow._load()\nself.flow._queue.put(1)\npipeline._tick()\nstore._read(x)\n"
        "ApplicationFlowService._x\nApplicationResumeStore._y = 1\n"
        "flow.__class__\nflow.public()\nself._own\nservice._load()\nworker.store._z\n"
    )
    assert private_attribute_uses(source) == 6
    path = tmp_path / "sample.py"
    path.write_text(source)
    assert private_attribute_uses(path.read_text()) == 6
    assert private_use_failures({"a.py": 3}, {"a.py": 2}) == [
        "new private_attribute_uses: a.py 2 -> 3"
    ]
    assert private_use_failures({}, {"a.py": 1}) == [
        f"resolved private_attribute_uses: a.py 1 -> 0 -- record it in {BASELINE.name}"
        " (update the baseline)"
    ]
    assert private_use_failures({"a.py": 2}, {"a.py": 2}) == []
