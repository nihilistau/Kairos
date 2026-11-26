"""GitHub releases: the newest release carrying a matching asset that has a published SHA-256."""

from __future__ import annotations

import re

from harness.setup.net import CatalogueError, Net

_REPO = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")
_SHA = re.compile(r"sha256:([0-9a-fA-F]{64})")


def releases(repo: str, *, net: Net | None = None) -> list[dict]:
    """The repo's 30 most recent releases (drafts left out), newest first: one API request."""
    if not isinstance(repo, str) or not _REPO.match(repo):
        raise CatalogueError("not a GitHub repository name")
    listing = (net or Net()).get_json(f"https://api.github.com/repos/{repo}/releases?per_page=30", what=repo)
    if not isinstance(listing, list):
        raise CatalogueError("unexpected releases listing from GitHub")
    return [r for r in listing if isinstance(r, dict) and not r.get("draft")]


def latest_asset(repo: str, pattern: str, *, prefer_tag_prefix: str | None = None,
                 net: Net | None = None, listing: list[dict] | None = None) -> dict:
    """{tag, name, size, url, sha256}. Searches recent releases newest first, since the very
    latest one may lack the platform's asset. Assets without a digest are skipped. `listing`
    (from releases()) saves the request."""
    if not isinstance(repo, str) or not _REPO.match(repo):
        raise CatalogueError("not a GitHub repository name")
    try:
        rx = re.compile(pattern)
    except re.error:
        raise CatalogueError("bad asset pattern") from None
    releases_ = listing if listing is not None else releases(repo, net=net)
    order = releases_
    if prefer_tag_prefix:
        pref = [r for r in releases_ if str(r.get("tag_name", "")).startswith(prefer_tag_prefix)]
        order = pref + [r for r in releases_ if r not in pref]
    for rel in order:
        for a in rel.get("assets") or []:
            name = a.get("name")
            m = _SHA.fullmatch(str(a.get("digest") or ""))
            if not isinstance(name, str) or not rx.search(name) or not m:
                continue
            url = a.get("browser_download_url")
            if not isinstance(url, str):
                continue
            try:
                size = int(a.get("size") or 0)
            except (TypeError, ValueError):
                raise CatalogueError("unexpected asset size from GitHub") from None
            return {"tag": str(rel.get("tag_name", "")), "name": name, "size": size,
                    "url": url, "sha256": m.group(1).lower()}
    raise CatalogueError("no recent release has a matching file with a published SHA-256")
