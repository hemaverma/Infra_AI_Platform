"""DNS resolution utilities for infrastructure tests."""

import ipaddress
import socket
from typing import Optional

import dns.resolver


def resolve_hostname(hostname: str, timeout: float = 10.0) -> Optional[str]:
    """Resolve a hostname to an IP address.

    Returns the first resolved IP or None if resolution fails.
    """
    try:
        answers = dns.resolver.resolve(hostname, "A", lifetime=timeout)
        return str(answers[0]) if answers else None
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
            dns.resolver.NoNameservers, dns.exception.Timeout):
        return None


def resolve_cname(hostname: str, timeout: float = 10.0) -> Optional[str]:
    """Resolve a CNAME record for a hostname.

    Returns the CNAME target or None.
    """
    try:
        answers = dns.resolver.resolve(hostname, "CNAME", lifetime=timeout)
        return str(answers[0].target) if answers else None
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
            dns.resolver.NoNameservers, dns.exception.Timeout):
        return None


def is_private_ip(ip: str) -> bool:
    """Check if an IP address is in a private range (RFC 1918 or link-local)."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private
    except ValueError:
        return False


def check_port_open(host: str, port: int, timeout: float = 5.0) -> bool:
    """Check if a TCP port is reachable on the given host."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
