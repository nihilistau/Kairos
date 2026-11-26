"""THE SETUP CENTRE (2026-11-26, design §4): everything a fresh install needs, found, fetched,
checked and configured. The network, catalogue, download and extraction modules are ported
from the Illustrated Primer's setup centre (primer/setup/) — same allowlist-first, hash-checked,
resumable, approve-before-running rules; `kits.json`, `installer.py` and `profile_writer.py`
are Kairos's own. Gate: G-SETUP.
"""
from harness.setup.net import CatalogueError  # noqa: F401
