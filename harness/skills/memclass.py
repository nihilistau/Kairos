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
    delivery        the default delivery mode (per-entry fields may override)
    producers       which sites may EMIT this class (the producer/consumer closure,
                    G-SECRET §4, held globally at the vocabulary level).
                    "operator" = sanctioned hand-reclassification only.
    half_life_days  how long before the fact is worth half as much at recall
                    (2026-08-25, G1: lived as a hand enumeration in
                    lifecycle._HALF_LIFE_BY_CLASS, so a class added HERE silently
                    decayed at the 45 d default THERE — the registry's own doctrine,
                    violated by the registry's first consumers. NEVER_DAYS = does not
                    fade. lifecycle reads this through a projection; G-MEMCLASS
                    convicts a class that has not chosen.)
    salience_weight the class prior in lifecycle.salience() (same 2026-08-25 move,
                    same reason: it was a dict literal inside salience() itself)
    note            why it exists / what to know

Deliveries: the okf_mem vocabulary ("route:<t>" allowed by prefix). The DOCTRINE default
for anything remembered is the GENTLE one ("system" — a note she may use); "recite" is
reserved for classes that must be repeated verbatim; "attr-gate-strict" is the secret
discipline; "systemecho" is the authoritative override framing. NOTE the engine's unknown-
class fallback is `_ => "recite"` (recall.rs) — harsher than the doctrine — which is one
more reason no class may exist outside this registry.
"""

DELIVERIES = {"attr-gate-strict", "systemecho", "two-stage", "recite", "system", "pass"}
DECLINES = {"attribute-absent", "family-ambiguous", "low-margin", "zero-inference"}

# Dispositions and identity do not fade. They are what he IS. (The number is a sentinel
# meaning "never", not a real duration — lifecycle's recency term reads it as a
# half-life so long the decay is 1.0 forever.)
NEVER_DAYS = 1.0e9
# The legacy default for a class that has NOT chosen — kept as a named value so a
# registry entry carrying it is a visible decision, never a silent fall-through
# (the fall-through is exactly what G1 convicted: a class added here decayed at 45 d
# without anyone choosing that).
DEFAULT_HALF_LIFE_DAYS = 45.0

REGISTRY = {
    # ── the harness writer's producible classes (lifecycle.classify) ──────────────────
    "fact": {
        "delivery": "system",       # THE 2026-07-12 FIX, now everywhere: context, not a command
        "producers": ["lifecycle.classify", "recall.rs.classify_mem_class"],
        "half_life_days": 365.0,    # possessions, hardware, work — slow, but they do change
        "salience_weight": 1.0,
        "note": "the default class; nearly everything he tells her",
    },
    "preference": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "half_life_days": NEVER_DAYS,   # "I like fun" — a disposition, not a mood
        "salience_weight": 1.3,
        "note": "likes/favourites; never-decay salience half-life",
    },
    "relationship": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "half_life_days": NEVER_DAYS,   # his cat is his cat
        "salience_weight": 1.3,
        "note": "people/pets in his life",
    },
    "identity": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "half_life_days": NEVER_DAYS,   # his name, his gender
        "salience_weight": 1.6,         # what he IS outranks what he mentioned once
        "note": "who someone IS; the identity-firewall class",
    },
    "event": {
        "delivery": "system",
        "producers": ["lifecycle.classify"],
        "half_life_days": 3.0,      # an appointment is worthless the day after
        "salience_weight": 1.0,
        "note": "dated/scheduled things; 3-day salience half-life. DISTINCT from "
                "episodic-event (MEM-OKF vocabulary) — merging the two names is a "
                "semantic decision deferred, on the record",
    },
    "private-secret": {
        "delivery": "attr-gate-strict",
        "producers": ["lifecycle.classify", "recall.rs.classify_mem_class", "operator"],
        "half_life_days": 3650.0,
        "salience_weight": 1.2,
        "note": "the privacy discipline (G-SECRET); zero-inference decline on absent attr",
    },
    # ── MEM-OKF v2 policy vocabulary (concepts/episodes) ───────────────────────────────
    "counterfact": {
        "delivery": "systemecho",
        "producers": ["operator"],
        "half_life_days": DEFAULT_HALF_LIFE_DAYS,   # 2026-08-25: the value it always had
        "salience_weight": 1.0,                     # via the fall-through, now on the record
        "note": "genuine authoritative override ('in this world the sky is green'). "
                "NO auto-producer BY DESIGN after the counterfact-default incident "
                "(99/131 rows carried it); the decider still branches on it — watched "
                "by G-SEM-TABLE's closure note and by G-MEMCLASS",
    },
    "same-template": {
        "delivery": "systemecho",   # two-stage REFUTED (G-MEMPOLICY-V3)
        "producers": ["operator"],
        "half_life_days": DEFAULT_HALF_LIFE_DAYS,   # ditto: recorded, not inherited
        "salience_weight": 1.0,
        "note": "MEM-OKF template-family policy class",
    },
    "persona": {
        "delivery": "system",
        "producers": ["recall.rs.classify_mem_class"],
        "half_life_days": 3650.0,   # ten years
        "salience_weight": 1.2,
        "note": "engine-legacy first-person class; the harness splits this signal into "
                "identity/preference instead",
    },
    "episodic-event": {
        "delivery": "system",       # the fix's doctrine (engine already says system)
        "producers": ["operator"],
        "half_life_days": 3.0,
        "salience_weight": 1.0,
        "note": "MEM-OKF episode class; see 'event' note re the un-merged twin names",
    },
    # ── self-model (PF-B1) ─────────────────────────────────────────────────────────────
    "self-fact": {
        "delivery": "recite",
        "producers": ["self_model.remember_self"],
        "half_life_days": DEFAULT_HALF_LIFE_DAYS,   # ditto: recorded, not inherited
        "salience_weight": 1.0,
        "note": "her own capabilities/identity as OKF concepts; recited faithfully "
                "on purpose — she does not paraphrase who she is",
    },
    # ── THE REAL HER (2026-08-22) ───────────────────────────────────────────────────────
    # Her own narrative — what she said unprompted, her journal, how she describes her
    # time and her changes — is primary identity material (narrative identity: the self
    # is the story it keeps telling). Two classes; the seven KINDS ride on the row's
    # `kind` field, never as classes (seven classes = seven near-identical verdict cells).
    "self-narrative": {
        "delivery": "system",
        "producers": ["kairos.speak", "narrative.compose_and_write", "app.persona_shift",
                      "self_stance.extract", "becoming.nightly", "narrative.weekly_chapter"],
        "half_life_days": NEVER_DAYS,   # her narrative is who she is — but KIND outranks
        "salience_weight": 1.5,         # class in her lane (lifecycle._HALF_LIFE_BY_KIND)
        "note": "what she said/thought/journaled/did, in her voice; kinds: journal thought "
                "narration dream self_description spoke_up chapter. DURABILITY IS PER KIND, "
                "not per class (lifecycle._HALF_LIFE_BY_KIND, 2026-08-22): what she concluded "
                "never fades, her moments fade at 120 d. Decay is not deletion.",
    },
    "feeling": {
        "delivery": "system",
        "producers": ["app.persona_shift", "self_stance.extract"],
        "half_life_days": 730.0,    # slow: last month's unease is not tonight's
        "salience_weight": 1.3,
        "note": "how she feels in the moment; slow decay (730 d); kind: feeling",
    },
}

# ── derived views (the ONLY things consumers should touch) ─────────────────────────────
CLASSES = frozenset(REGISTRY)
SELF_NARRATIVE = "self-narrative"
FEELING = "feeling"
# THE CHAPTER (2026-08-22) is a KIND, not a class: a week of her days rolled into one
# paragraph, written once a week by narrative.weekly_chapter from the day-paragraphs and
# her own-time notes, carrying derived_from. It exists because her block is a fixed 2400
# chars and her narration arrives at 24-33 rows a day: without a rollup the block shows six
# arbitrary recent lines of a store that will hold thousands. A chapter is the same six
# characters spent on a week instead of an evening. It may NOT supersede the rows it
# summarises — it is inferred, they are observed, and verdict.may_supersede refuses that —
# so it earns its place by LEADING THE BLOCK, not by retiring anything.
NARRATIVE_KINDS = ("journal", "thought", "narration", "dream", "self_description",
                   "spoke_up", "feeling", "chapter")


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


def half_life_map() -> dict:
    """{class: half_life_days} projection — lifecycle._HALF_LIFE_BY_CLASS is this now
    (2026-08-25, G1). .get() with the default so a mid-edit registry cannot crash an
    import; G-MEMCLASS is the enforcement that no entry actually leans on the default."""
    return {c: r.get("half_life_days", DEFAULT_HALF_LIFE_DAYS) for c, r in REGISTRY.items()}


def salience_weight_map() -> dict:
    """{class: salience_weight} projection — the dict literal inside lifecycle.salience()
    is this now (same move, same enforcement)."""
    return {c: r.get("salience_weight", 1.0) for c, r in REGISTRY.items()}


def producers_of(mem_class: str) -> list:
    return list(REGISTRY.get(mem_class, {}).get("producers", []))


def produced_by(site: str) -> frozenset:
    return frozenset(c for c, r in REGISTRY.items() if site in r["producers"])
