"""Ported from the Illustrated Primer's setup centre (primer/setup/net.py, 2026-11-26), allowlist
trimmed to the hosts Kairos downloads from.

HTTPS GET for the Setup catalogues and downloader: allowlist, redirect and address policy.

The first request must go to an allowlisted host. Every hop must be https and must not be an
IP literal or resolve to a private, loopback, link-local or reserved address. The Hugging Face
token travels only to huggingface.co (and subdomains) and is dropped on any other host.
The transport and resolver are injectable so tests never touch the network.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

ALLOWED_HOSTS = (
    "huggingface.co",
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "codeload.github.com",
)
TOKEN_HOST = "huggingface.co"
MAX_REDIRECTS = 5
MAX_BODY = 32 * 1024 * 1024
TIMEOUT = 30.0
USER_AGENT = "kairos-setup"   # a named agent: Cloudflare 403s Python-urllib (G-BACKEND-SEAM §11)


class CatalogueError(Exception):
    """A catalogue or download request that cannot proceed; `reason` is a short sentence."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str = ""
    redirects: list[str] = field(default_factory=list)


def host_matches(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def _embedded_v4(a: ipaddress.IPv6Address):
    out = []
    if a.ipv4_mapped:
        out.append(a.ipv4_mapped)
    if a.sixtofour:
        out.append(a.sixtofour)
    top = a.packed[:12]
    if top == bytes(12) or top == bytes.fromhex("0064ff9b" + "00" * 8):
        out.append(ipaddress.IPv4Address(a.packed[12:]))
    return out


def check_url(url: str, first: bool, resolve=socket.getaddrinfo) -> str:
    """Return the host if `url` may be fetched, else raise CatalogueError."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        raise CatalogueError("the address is not a valid URL") from None
    if parts.scheme != "https":
        raise CatalogueError("only https addresses are allowed")
    if not host:
        raise CatalogueError("the address has no host")
    if first and not any(host_matches(host, d) for d in ALLOWED_HOSTS):
        raise CatalogueError(f"{host} is not an allowed download host")
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        pass
    else:
        raise CatalogueError("addresses given as IP numbers are not allowed")
    try:
        infos = resolve(host, None)
        addrs = [ipaddress.ip_address(str(i[4][0]).split("%", 1)[0]) for i in infos]
    except (OSError, ValueError, IndexError, TypeError):
        raise CatalogueError(f"cannot resolve {host}") from None
    if not addrs:
        raise CatalogueError(f"cannot resolve {host}")
    for a in list(addrs):
        if isinstance(a, ipaddress.IPv6Address):
            addrs.extend(_embedded_v4(a))
    # Known limit: this lookup and the connect urllib makes are separate resolutions, so a DNS
    # rebind between them could slip through (the same rule Primer's web reader applies).
    if not all(a.is_global for a in addrs):
        raise CatalogueError(f"{host} is not a public address")
    return host


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def urllib_transport(url: str, headers: dict[str, str], max_bytes: int = MAX_BODY, opener=None):
    """One request, no redirect following: returns (status, headers, body)."""
    opener = opener or urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = opener.open(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as exc:
        resp = exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise CatalogueError(f"network error: {getattr(exc, 'reason', exc) or type(exc).__name__}") from None
    try:
        body = resp.read(max_bytes + 1)
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        status = resp.status if hasattr(resp, "status") else resp.code
    except OSError as exc:
        raise CatalogueError(f"network error: {exc}") from None
    finally:
        resp.close()
    if len(body) > max_bytes:
        raise CatalogueError("the response is too large")
    return status, hdrs, body


def urllib_stream_transport(url: str, headers: dict[str, str], opener=None, timeout: float = 60.0):
    """One request, no redirect following: returns (status, headers, readable stream). Caller closes."""
    opener = opener or urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        resp = exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise CatalogueError(f"network error: {getattr(exc, 'reason', exc) or type(exc).__name__}") from None
    status = resp.status if hasattr(resp, "status") else resp.code
    return status, {k.lower(): v for k, v in resp.headers.items()}, resp


@dataclass
class StreamResponse:
    status: int
    headers: dict[str, str]
    stream: object
    url: str = ""


class Net:
    """Policy-enforcing GET. `transport(url, headers) -> (status, headers, body)` is injectable;
    `stream_transport(url, headers) -> (status, headers, stream)` serves `open_stream`."""

    def __init__(self, transport=None, resolve=None, stream_transport=None) -> None:
        self._transport = transport or urllib_transport
        self._stream_transport = stream_transport or urllib_stream_transport
        self._resolve = resolve or socket.getaddrinfo

    def _walk(self, url: str, base_headers: dict[str, str], token: str | None, send, discard=None):
        """Follow redirects, re-checking the URL policy and the token rule on every hop.
        Returns (status, headers, payload, final_url, hops)."""
        seen: list[str] = []
        for hop in range(MAX_REDIRECTS + 1):
            host = check_url(url, first=(hop == 0), resolve=self._resolve)
            headers = {"User-Agent": USER_AGENT, **base_headers}
            if token and host_matches(host, TOKEN_HOST):
                headers["Authorization"] = f"Bearer {token}"
            status, hdrs, payload = send(url, headers)
            if status in (301, 302, 303, 307, 308):
                if discard:
                    discard(payload)
                loc = hdrs.get("location")
                if not loc:
                    raise CatalogueError("a redirect had no destination")
                seen.append(url)
                url = urllib.parse.urljoin(url, loc)
                continue
            return status, hdrs, payload, url, seen
        raise CatalogueError("too many redirects")

    def get(self, url: str, *, token: str | None = None, accept: str | None = None) -> Response:
        base = {"Accept": accept} if accept else {}
        status, hdrs, body, final, seen = self._walk(url, base, token, self._transport)
        return Response(status, hdrs, body, final, seen)

    def open_stream(self, url: str, *, token: str | None = None, headers: dict[str, str] | None = None) -> StreamResponse:
        """Like `get` but returns an open stream (caller closes it); same policy on every hop."""

        def close(stream):
            try:
                stream.close()
            except Exception as _swx:
                import logging
                from harness.loud import swallowed as _swallowed
                _swallowed(logging.getLogger(__name__), "open_stream.close", _swx, lane="setup")

        status, hdrs, stream, final, _ = self._walk(
            url, dict(headers or {}), token, self._stream_transport, discard=close
        )
        return StreamResponse(status, hdrs, stream, final)

    def get_json_page(self, url: str, *, token: str | None = None, what: str | None = None):
        """(parsed JSON, response headers). `what` names the thing asked for, for error text."""
        resp = self.get(url, token=token, accept="application/json")
        host = (urllib.parse.urlsplit(resp.url).hostname or "the server").lower()
        label = f"{host}: {what} " if what else f"{host}: "
        if resp.status in (401, 403):
            if host_matches(host, TOKEN_HOST):
                if token:
                    raise CatalogueError("Hugging Face refused the token (or the licence is not accepted)")
                raise CatalogueError("a Hugging Face token is needed for this repository")
            raise CatalogueError(f"{host} refused the request (rate limited?)")
        if resp.status == 404:
            raise CatalogueError(f"{label}not found" if what else f"{host}: not found")
        if resp.status >= 400:
            raise CatalogueError(f"{host} answered {resp.status}")
        try:
            return json.loads(resp.body.decode("utf-8")), resp.headers
        except (ValueError, UnicodeDecodeError):
            raise CatalogueError(f"{host} sent something that is not JSON") from None

    def get_json(self, url: str, *, token: str | None = None, what: str | None = None):
        return self.get_json_page(url, token=token, what=what)[0]
