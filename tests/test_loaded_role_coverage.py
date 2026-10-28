"""MC-15/MC-20: package modules a process can load are measured by its loaded role.

The subprocess probes cover what startup and the status reads load. The static scan
requires each role to contain every package module its modules import, module-level or
function-local, so a lazily imported module cannot run outside the role's startup identity.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"

# Loaded but deliberately outside a role; each entry states why its code cannot change
# what the measured controller or worker does for an application.
EXEMPT = {
    "loaded_code": "the normalizer measures itself into every role revision",
    "_vendor": "package marker only; _vendor.job_apply_store is measured",
    "validation": "package marker of the research harness; validation.hashing is measured",
    "validation.acceptance": "research acceptance records; no application path calls them",
    # Not normalizable in v1 (frozen Pydantic models carry generated __hash__ closures).
    # Role modules import CodexCLIConfig/CodexCLIResult/StrictModel from it; their field
    # and config policy is measured as model_policy records of each importing role module.
    "validation.models": "Codex CLI and strict model contracts; measured as importer model_policy",
    "validation.replay": "research replay harness; no application path calls it",
    "audit": "research Grill-Me audit package; read only for research pages",
    "audit.decision": "research Grill-Me audit decisions; read only for research pages",
    "audit.models": "research Grill-Me audit contracts; read only for research pages",
    "audit.store": "research Grill-Me audit store; read only for research pages",
    "audit.workflow": "research Grill-Me audit workflow; read only for research pages",
    "domain": "research domain package marker",
    "domain.fixtures": "research STOA fixture loader; no application path calls it",
    "domain.invariants": "research domain invariants for the audit harness",
    "domain.models": "research domain contracts for the audit harness",
    "application_worker_fixtures": "synthetic ATS pages served only by fixture test runs",
    "application_preparation_fixtures": "synthetic Gmail/JD captures; macos/server.py loads it "
    "only for the isolated synthetic preparation journey",
    # Open point: python-loaded-code/v1 cannot normalize frozen Pydantic __hash__ closures.
    # application_resume imports Profile/PublicSiteSource at module level, so their policy
    # is measured there; the unmeasured functions (load_public_site,
    # export_public_site) serve only GET /api/public-site and the public export, not
    # application writing, matching or filling.
    "public_site": "public profile contracts; models measured via importers, functions unmeasured",
}

CONTROLLER_PROBE = r"""
import json, subprocess, sys, threading
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from career_evidence_graph.career_portal import create_server

root = Path(sys.argv[2])
options = {"preparation_only": True} if sys.argv[3] == "preparation" else {
    "worker_root": root / "worker"
}
(root / "applications").mkdir()
(root / "career").mkdir()
subprocess.run(["git", "init", "--quiet", str(root / "career")], check=True)
server = create_server(
    root / "applications", root / "career", flow_root=root / "flow",
    write_admission_policy="development", **options,
)
try:
    flow = server.application_flow_service
    job = flow.applications.create_application(
        {"company": "Synthetic", "role_title": "Engineer", "job_description": "Build."}
    )
    task = flow.create(job["id"], job["revision"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for path in ("/api/state", "/api/flow/state", "/api/flow/" + task["id"], "/api/pipeline/state"):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request("GET", path)
        connection.getresponse().read()
        connection.close()
    server.shutdown()
finally:
    server.server_close()
print(json.dumps(sorted(name for name in sys.modules if name.startswith("career_evidence_graph."))))
"""

WORKER_PROBE = r"""
import json, sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from career_evidence_graph import application_worker_browser as browser

def stop_before_browser():
    raise browser.Error("bounded_startup_probe")

root = Path(sys.argv[2])
(root / "applications").mkdir()
browser.sync_playwright = stop_before_browser
browser.main([
    "--applications", str(root / "applications"),
    "--runtime", str(root / "runtime"),
    "--fixture-origin", "http://127.0.0.1:9999",
])
print(json.dumps(sorted(name for name in sys.modules if name.startswith("career_evidence_graph."))))
"""


def _loaded(probe, tmp_path, *arguments):
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(SOURCE), str(tmp_path), *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    names = json.loads(result.stdout.splitlines()[-1])
    return {name.removeprefix("career_evidence_graph.") for name in names}


def _roles():
    from career_evidence_graph.loaded_code import _PREPARATION_MODULES, _RUNTIME_MODULES

    return set(_PREPARATION_MODULES), {key: set(value) for key, value in _RUNTIME_MODULES.items()}


def test_controller_modules_are_in_the_controller_role_or_exempt(tmp_path):
    preparation, roles = _roles()
    assert preparation <= roles["controller"]
    for mode in ("application", "preparation"):
        root = tmp_path / mode
        root.mkdir()
        loaded = _loaded(CONTROLLER_PROBE, root, mode)
        assert {"application_flow_view", "application_existing_handoff"} <= loaded
        assert sorted(loaded - roles["controller"] - set(EXEMPT)) == [], mode


def test_worker_process_modules_are_in_the_worker_role_or_exempt(tmp_path):
    _, roles = _roles()
    loaded = _loaded(WORKER_PROBE, tmp_path)
    assert "career_portal" not in loaded
    assert sorted(loaded - roles["worker"] - set(EXEMPT)) == []
    # MC-20: startup preloads the whole role before recording the worker identity.
    assert sorted(roles["worker"] - loaded) == []


def test_exemptions_stay_reasoned_and_outside_every_role():
    preparation, roles = _roles()
    measured = preparation.union(*roles.values())
    assert not measured & set(EXEMPT)
    assert all(isinstance(reason, str) and len(reason) > 20 for reason in EXEMPT.values())
    package = SOURCE / "career_evidence_graph"
    for name in measured | set(EXEMPT):
        path = package.joinpath(*name.split("."))
        assert path.with_suffix(".py").is_file() or (path / "__init__.py").is_file(), name


def test_role_revisions_are_measurable_with_the_added_modules():
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from career_evidence_graph.loaded_code import measure_packaged_roles, "
        "loaded_preparation_revision; "
        "r = measure_packaged_roles(); p = loaded_preparation_revision(); "
        "print(r['controller'], r['worker'], p)"
    )
    output = subprocess.check_output(
        [sys.executable, "-I", "-B", "-c", code, str(SOURCE)], text=True, timeout=60
    ).split()
    assert output[0].startswith("python-loaded-code/v1:controller:")
    assert output[1].startswith("python-loaded-code/v1:worker:")
    assert len(output[2]) == 64


def _package_imports(name):
    """Package modules named by any import statement in ``name``, including function-local ones."""
    package = SOURCE / "career_evidence_graph"

    def exists(dotted):
        path = package.joinpath(*dotted.split("."))
        return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()

    path = package.joinpath(*name.split("."))
    is_package = not path.with_suffix(".py").is_file()
    source = path / "__init__.py" if is_package else path.with_suffix(".py")
    base = name.split(".") if is_package else name.split(".")[:-1]
    found = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level:
            parts = base[: len(base) - node.level + 1] + (node.module or "").split(".")
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "career_evidence_graph."
        ):
            parts = node.module.split(".")[1:]
        elif isinstance(node, ast.Import):
            parts = []
            for alias in node.names:
                if alias.name.startswith("career_evidence_graph."):
                    found.add(alias.name.removeprefix("career_evidence_graph."))
            continue
        else:
            continue
        parts = [part for part in parts if part]
        targets = [parts] + [parts + [alias.name] for alias in node.names]
        for target in targets:
            found.update(
                ".".join(target[:end])
                for end in range(1, len(target) + 1)
                if exists(".".join(target[:end]))
            )
    return found


def _reachable(modules):
    seen, pending = set(), list(modules)
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            pending.extend(_package_imports(name) - seen)
    return seen


def test_the_scan_sees_function_local_write_path_imports():
    # Lazy imports on application write paths that the startup probe never executes.
    assert {"resume_template", "chrome_registration"} <= _package_imports("application_resume")
    assert "application_experience_content" in _package_imports("application_experience_latex")
    assert "application_content_reconcile" in _package_imports("application_resume_versions")
    assert "application_material_packet" in _package_imports("application_matching_pipeline")
    assert "application_form_state" in _package_imports("application_worker")


def test_statically_reachable_modules_are_in_their_role_or_exempt():
    _, roles = _roles()
    for role in ("controller", "worker"):
        # MC-20: each role is closed under its package imports, module-level and
        # function-local. Which lazy paths a process will actually run is not decided here
        # (calls through other objects defeat a call-graph walk), so the worker role also
        # covers controller-side paths such as application_flow -> application_preparation.
        assert sorted(_reachable(roles[role]) - roles[role] - set(EXEMPT)) == [], role
