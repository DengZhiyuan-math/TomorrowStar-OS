"""Public-host checks without DNS lookups or network requests."""

from __future__ import annotations

from ipaddress import ip_address
from socket import inet_aton
from urllib.parse import unquote


def is_public_host(host: str) -> bool:
    """Recognize local names and legacy numeric IPv4 spellings used by browsers."""
    try:
        host = unquote(host).encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        return False
    if "." not in host or host.endswith((".local", ".localhost", ".internal")):
        return False
    try:
        address = ip_address(host)
    except ValueError:
        try:
            # inet_aton parses shortened, octal and hexadecimal IPv4 without resolving DNS.
            address = ip_address(inet_aton(host))
        except OSError:
            return True
    return address.is_global
