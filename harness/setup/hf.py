"""Hugging Face model listings: files with their SHA-256 (LFS oid) and the licence card."""

from __future__ import annotations

import re
import urllib.parse

from harness.setup.net import CatalogueError, Net

_API = "https://huggingface.co/api/models/"
MAX_PAGES = 20
_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
_REPO = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")


def _repo(repo: str) -> str:
    if not isinstance(repo, str) or not _REPO.match(repo):
        raise CatalogueError("not a Hugging Face repository name")
    return repo


def files(repo: str, token: str | None = None, net: Net | None = None) -> list[dict]:
    """[{path, size, sha256}] for every file; sha256 is None for files outside LFS."""
    net = net or Net()
    url = f"{_API}{_repo(repo)}/tree/main?recursive=1"
    data: list = []
    for _ in range(MAX_PAGES):
        page, headers = net.get_json_page(url, token=token, what=repo)
        if not isinstance(page, list):
            raise CatalogueError("unexpected listing from Hugging Face")
        data.extend(page)
        m = _NEXT.search(headers.get("link", ""))
        if not m:
            break
        url = urllib.parse.urljoin(url, m.group(1))
    else:
        raise CatalogueError(f"{repo} lists too many files")
    out = []
    for e in data:
        if not isinstance(e, dict) or e.get("type") != "file" or not isinstance(e.get("path"), str):
            continue
        lfs = e.get("lfs") if isinstance(e.get("lfs"), dict) else {}
        oid = lfs.get("oid")
        try:
            size = int(lfs.get("size") or e.get("size") or 0)
        except (TypeError, ValueError):
            raise CatalogueError("unexpected file size from Hugging Face") from None
        out.append({
            "path": e["path"],
            "size": size,
            "sha256": oid.lower() if isinstance(oid, str) and re.fullmatch(r"[0-9a-fA-F]{64}", oid) else None,
        })
    return out


def card(repo: str, token: str | None = None, net: Net | None = None) -> dict:
    """{license, gated, license_link?, summary}; gated is False, "auto" or "manual"."""
    repo = _repo(repo)
    data = (net or Net()).get_json(f"{_API}{repo}", token=token, what=repo)
    if not isinstance(data, dict):
        raise CatalogueError("unexpected model info from Hugging Face")
    cd = data.get("cardData") if isinstance(data.get("cardData"), dict) else {}
    gated = data.get("gated")
    out = {
        "license": str(cd.get("license") or "unknown"),
        "gated": gated if gated in ("auto", "manual") else bool(gated),
    }
    link = cd.get("license_link")
    if isinstance(link, str) and link:
        out["license_link"] = (link if link.startswith("https://")
                               else f"https://huggingface.co/{repo}/blob/main/{link}")
    bits = [str(cd["pipeline_tag"])] if cd.get("pipeline_tag") else []
    base = cd.get("base_model")
    base = base[0] if isinstance(base, list) and base else base
    if isinstance(base, str):
        bits.append(f"based on {base}")
    out["summary"] = ", ".join(bits)
    return out
