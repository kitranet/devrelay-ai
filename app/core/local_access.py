"""Trust-boundary checks for loopback-only local workflow routes."""

from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import Request

from app.core.errors import LocalReviewLoopbackError


def require_loopback(request: Request) -> None:
    client = request.client
    host = request.url.hostname
    try:
        client_is_loopback = client is not None and ip_address(client.host).is_loopback
    except ValueError:
        client_is_loopback = False
    host_is_loopback = bool(host and host.lower() == "localhost")
    if host and not host_is_loopback:
        try:
            host_is_loopback = ip_address(host).is_loopback
        except ValueError:
            host_is_loopback = False
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    browser_source_is_loopback = True
    if origin:
        browser_source_is_loopback = _url_is_loopback(origin)
    elif referer:
        browser_source_is_loopback = _url_is_loopback(referer)
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if fetch_site == "cross-site":
        browser_source_is_loopback = False
    if not client_is_loopback or not host_is_loopback or not browser_source_is_loopback:
        raise LocalReviewLoopbackError()


def _url_is_loopback(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return False
        if host.lower() == "localhost":
            return True
        return ip_address(host).is_loopback
    except ValueError:
        return False
