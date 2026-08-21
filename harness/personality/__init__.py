"""harness.personality — the self-modifiable personality framework (CONTRACT-PERSONALITY).

PF-B1 (this module's first brick): fact OWNERSHIP. A fact carries an owner axis ORTHOGONAL to its
mem_class — `self` (about the agent: "I can read and write memories") vs `user` (about the
operator: "the user prefers tea"). Self-facts form the agent's SELF-MODEL; user-facts are the
operator's. Stored as OKF concepts (so they compose with the engine store-merge + the DF curator),
retrievable/renderable distinctly, and — later bricks — self-modifiable via tags/decorators and
curatable by NIGHTSHIFT.
"""
from harness.personality.self_model import (
    SelfModelStore, remember_self, remember_user, render_self_model,
)

__all__ = ["SelfModelStore", "remember_self", "remember_user", "render_self_model"]
