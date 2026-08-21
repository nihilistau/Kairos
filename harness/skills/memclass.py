"""memclass — THE class vocabulary. One registry, everyone consumes, a gate pins the rest.
(INVARIANT-ROADMAP.md Tier 1.2; the recipe of INVARIANT-MEMORY.md at the vocabulary level.)

WHY THIS FILE EXISTS. Four class enumerations and three class->delivery maps grew in four
files (lifecycle.classify, okf_mem.MEM_CLASSES/CLASS_DEFAULT_DELIVERY,
recall.rs::classify_mem_class/class_default_delivery, self_model._CLASS_DELIVERY) — and
they had ALREADY drifted when this file was written: the 2026-07-12 incident fix
("a remembered thing is CONTEXT, not a command" — she recited an unrelated memory at
'what do you mean?' because fact-class delivery was an order) changed fact -> system IN
THE ENGINE ONLY. Both Python copies still said fact -> recite. An invariant fixed in one
of three copies is fixed in none; this registry adopts the fixed doctrine and the copies
are deleted in favour of imports. The engine cannot import Python, so G-MEMCLASS parses
recall.rs SOURCE and convicts drift the day it happens (the G-ONEDOOR derive-from-source
trick).

mem_class is a sigma coordinate (INVARIANT-MEMORY.md §1.1): this registry is the verdict
layer's own input vocabulary, which is why it gets the full discipline.

THE REGISTRY SEMANTICS, per class:
    delivery   the default delivery mode (per-entry fields may override)
    producers  which sites may EMIT this class (the producer/consumer closure,
               G-SECRET §4, held globally at the vocabulary level).
               "operator" = sanctioned hand-reclassification only.
    note       why it exists / what to know

Deliveries: the okf_mem vocabulary ("route:<t>" allowed by prefix). The DOCTRINE default
for anything remembered is the GENTLE one ("system" — a note she may use); "recite" is
reserved for classes that must be repeated verbatim; "attr-gate-strict" is the secret
discipline; "systemecho" is the authoritative override framing. NOTE the engine's unknown-
class fallback is `_ => "recite"` (recall.rs) — harsher than the doctrine — which is one
more reason no class may exist outside this registry.
"""

DELIVERIES = {"attr-gate-strict", "systemecho", "two-stage", "recite", "system", "pass"}
DECLINES = {"attribute-absent", "family-ambiguous", "low-margin", "zero-inference"}

REGISTRY = {
    # ── the harness writer's producible classes (lifecycle.classify) ──────────────────
    "fact": {
        "delivery": "system",       # THE 2026-07-12 FIX, now everywhere: context, not a command
        "producers": ["lifecycle.classify", "recall.rs.classify_mem_class"],
        "note": "the default class; nearly everything he tells her",
    },
    "preference": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "note": "likes/favourites; never-decay salience half-life",
    },
    "relationship": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "note": "people/pets in his life",
    },
    "identity": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "note": "who someone IS; the identity-firewall class",
    },
    "event": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "note": "dated/scheduled things; 3-day salience half-life. DISTINCT from "
                "episodic-event (MEM-OKF vocabulary) — merging the two names is a "
                "semantic decision deferred, on the record",
    },
    "private-secret": {
        "delivery": "attr-gate-strict",
        "producers": ["lifecycle.classify", "recall.rs.classify_mem_class", "operator"],
        "note": "the privacy discipline (G-SECRET); zero-inference decline on absent attr",
    },
    # ── MEM-OKF v2 policy vocabulary (concepts/episodes) ───────────────────────────────
    "counterfact": {
        "delivery": "systemecho",
        "producers": ["operator"],
        "note": "genuine authoritative override ('in this world the sky is green'). "
                "NO auto-producer BY DESIGN after the counterfact-default incident "
                "(99/131 rows carried it); the decider still branches on it — watched "
                "by G-SEM-TABLE's closure note and by G-MEMCLASS",
    },
    "same-template": {
        "delivery": "systemecho",   # two-stage REFUTED (G-MEMPOLICY-V3)
        "producers": ["operator"],
        "note": "MEM-OKF template-family policy class",
    },
    "persona": {
        "delivery": "system",
        "producers": ["recall.rs.classify_mem_class"],
        "note": "engine-legacy first-person class; the harness splits this signal into "
                "identity/preference instead",
    },
    "episodic-event": {
        "delivery": "system",       # the fix's doctrine (engine already says system)
        "producers": ["operator"],
        "note": "MEM-OKF episode class; see 'event' note re the un-merged twin names",
    },
    # ── self-model (PF-B1) ─────────────────────────────────────────────────────────────
    "self-fact": {
        "delivery": "recite",
        "producers": ["self_model.remember_self"],
        "note": "her own capabilities/identity as OKF concepts; recited faithfully "
                "on purpose — she does not paraphrase who she is",
    },
}

# ── derived views (the ONLY things consumers should touch) ─────────────────────────────
CLASSES = frozenset(REGISTRY)


def delivery_for(mem_class: str) -> str:
    """Default delivery, doctrine fallback GENTLE ('system'). The engine's compiled
    fallback for unknown classes is 'recite' — divergence by design impossible while
    every class lives in this registry (G-MEMCLASS holds that)."""
    row = REGISTRY.get(mem_class)
    return row["delivery"] if row else "system"


def delivery_map(classes=None) -> dict:
    """{class: delivery} projection, optionally restricted."""
    keys = classes if classes is not None else REGISTRY
    return {c: REGISTRY[c]["delivery"] for c in keys if c in REGISTRY}


def producers_of(mem_class: str) -> list:
    return list(REGISTRY.get(mem_class, {}).get("producers", []))


def produced_by(site: str) -> frozenset:
    return frozenset(c for c, r in REGISTRY.items() if site in r["producers"])
