"""Pinned local signing identity shared by the builder and main-App updater."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

BUNDLE_ID = "dev.tomorrowstar.desktop"


class SigningPolicy(NamedTuple):
    identity_sha1: str
    designated_requirement: str
    installed_app: Path


def normalize_identity(identity: str) -> str:
    if not isinstance(identity, str) or re.fullmatch(r"[0-9A-Fa-f]{40}", identity) is None:
        raise ValueError("Choose the exact 40-character code-signing certificate SHA-1.")
    return identity.upper()


def designated_requirement(identity: str) -> str:
    return f'identifier "{BUNDLE_ID}" and certificate leaf = H"{normalize_identity(identity)}"'


def load_policy(
    config: Path | None = None,
    identity_override: str | None = None,
    allow_ad_hoc_synthetic: bool = False,
) -> SigningPolicy:
    main = Path.home() / "Applications/TomorrowStar.app"
    if allow_ad_hoc_synthetic:
        if identity_override is not None:
            raise ValueError("Synthetic ad-hoc signing cannot override the stable identity.")
        return SigningPolicy("-", "", main)
    config = config or Path.home() / "Library/Application Support/TomorrowStar/signing.json"
    try:
        if config.is_symlink() or config.resolve() != config.absolute():
            raise ValueError("The stable signing configuration cannot use a symlink or path alias.")
        value = json.loads(config.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("A validated stable signing configuration is required.") from error
    if not isinstance(value, dict) or set(value) != {
        "identity_sha1",
        "designated_requirement",
        "installed_app",
    }:
        raise ValueError("The stable signing configuration has invalid fields.")
    identity = normalize_identity(value["identity_sha1"])
    requirement = designated_requirement(identity)
    if value["designated_requirement"] != requirement or value["installed_app"] != str(main):
        raise ValueError("The stable signing configuration does not bind the fixed main App.")
    if identity_override is not None and normalize_identity(identity_override) != identity:
        raise ValueError("The requested signing identity differs from the pinned identity.")
    return SigningPolicy(identity, requirement, main)


def validate_identity(policy: SigningPolicy) -> None:
    if policy.identity_sha1 == "-":
        return
    result = subprocess.run(
        ["/usr/bin/security", "find-identity", "-v", "-p", "codesigning"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    identities = re.findall(r"^\s*\d+\) ([0-9A-Fa-f]{40}) ", result.stdout, re.MULTILINE)
    if policy.identity_sha1 not in {value.upper() for value in identities}:
        raise ValueError("The pinned code-signing identity is unavailable; no fallback is allowed.")


def sign_code(path: Path, policy: SigningPolicy, *, app: bool = False) -> None:
    command = ["/usr/bin/codesign", "--force", "--sign", policy.identity_sha1]
    if app and policy.identity_sha1 != "-":
        command.extend(["--requirements", "=designated => " + policy.designated_requirement])
    subprocess.run([*command, str(path)], check=True, capture_output=True, timeout=60)


def verify_app(app: Path, policy: SigningPolicy) -> None:
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    if policy.identity_sha1 == "-":
        return
    subprocess.run(
        [
            "/usr/bin/codesign",
            "--verify",
            "--strict",
            "-R",
            "=" + policy.designated_requirement,
            str(app),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    result = subprocess.run(
        ["/usr/bin/codesign", "-d", "-r-", str(app)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    actual = [
        line.removeprefix("designated => ").strip()
        for line in lines
        if line.startswith("designated => ")
    ]
    # csreq/codesign pretty-print certificate hashes in lowercase. Admit only
    # this closed requirement grammar and normalize the hash, never identifiers
    # or extra predicates. A different certificate or broader requirement fails.
    match = re.fullmatch(
        r'identifier "dev\.tomorrowstar\.desktop" and certificate leaf = H"([0-9A-Fa-f]{40})"',
        actual[0] if len(actual) == 1 else "",
    )
    if match is None or designated_requirement(match[1]) != policy.designated_requirement:
        raise ValueError("The App designated requirement differs from the pinned requirement.")
