"""Conversation memory + capabilities -- the tiered short/mid/long store.

Built ON the existing MEM-OKF content-addressed store (tools/okf_mem.py): every
object is sha256-addressed, with three disclosure tiers -- LUT (index) -> sum/ (the
gist) -> full/ (the complete context). The model gets the gist by default and digs
into the full transcript only when it needs to.

The tiers, mapped to the operator's design:
  SHORT  the live conversation (carried in `messages`, passed in each turn).
  MID    durable FACTS extracted from the conversation -> the recall registry
         (harness.skills.memory.remember) so they survive window-scroll.
  LONG   the whole conversation stored COMPLETE (full/) AND SUMMARIZED (sum/),
         linked by one sha256 address -- recall the gist, dig deeper on demand.

Plus a CAPABILITIES corpus: "how do I use myself" facts the model can recall, and
an init primer that points the system at what it can do.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import textwrap
import types
from typing import List, Optional

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "..", "tools")))
import okf_mem as ok  # noqa: E402

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_HARNESS_ROOT = os.path.abspath(os.path.join(_THIS, "..", ".."))
CONV_ROOT = os.environ.get("SP_CONV_OKF_ROOT", os.path.join(_HARNESS_ROOT, "memory-okf-conv"))
CAPS_ROOT = os.environ.get("SP_CAPS_OKF_ROOT", os.path.join(_HARNESS_ROOT, "memory-okf-caps"))


# ──── transcript / model helpers ───────────────────────────────────────────
# ── WHAT A ONE-SHOT PROMPT MAY COST (2026-08-30) ──────────────────────────────────────
# This function fed EVERY message at FULL length into a one-shot prompt, and the day
# transcript grows all day. Measured this morning, three wedges in a row: the day's
# ~20,000 tokens became `need` in v1_oneshot, which opens a SCRATCH cache — and a scratch
# runs ring-off, so every layer gets the full Pmax instead of the 2048-slot SWA ring the
# resident session uses. That makes a long scratch ~4x more expensive PER POSITION than
# the conversation it is summarising: 4.30 GB, on top of 7.5 GB resident, on a 12.3 GB
# card. Past ~95% WDDM pages over PCIe, the forward crawls for hours holding the device
# lock, and every turn of hers queues behind it — the chip stuck on "warming" all morning.
#
# `narrative.py` has bounded exactly this since it was written (`_MAX_TURNS = 40`, each
# turn cut to 200 chars) because it feeds the same kind of call. AGENTS.md §0: the rule
# was enforced on one of the two paths that mint a one-shot from a transcript, and
# therefore on neither. It is enforced here now, in the thing they both call.
#
# The numbers are chosen against the ENGINE's ceiling, not by feel: v1_oneshot refuses a
# scratch over SP_ONESHOT_PMAX_MAX (6144 positions). 40 turns x 300 chars is ~12k
# characters — under 5k tokens even at the pessimistic ~2.5 chars/token that code and
# unusual text produce — so a capped transcript can never trip the refusal. `narrative.py`
# has run on 40 x 200 for the same job since it was written; this is slightly more
# generous, and still an order of magnitude below what wedged the box.
_MAX_TURNS = 40          # the tail of the conversation a one-shot may read
_MAX_TURN_CHARS = 300    # per turn, so one pasted wall of text cannot fill the window


def _transcript(messages: List[dict]) -> str:
    lines = []
    kept = [m for m in (messages or []) if m.get("role") != "system"][-_MAX_TURNS:]
    for m in kept:
        who = "User" if m.get("role") == "user" else "AI"
        body = (m.get("content", "") or "")
        if len(body) > _MAX_TURN_CHARS:
            body = body[:_MAX_TURN_CHARS] + " …"
        lines.append(f"{who}: {body}")
    return "\n".join(lines).strip()


def _keys_from(text: str, fallback: str = "conversation") -> str:
    words = ["".join(c for c in w if c.isalnum()) for w in text.lower().split()]
    seen, keys = set(), []
    for w in words:
        if len(w) >= 4 and w not in seen:
            seen.add(w)
            keys.append(w)
        if len(keys) >= 8:
            break
    return ",".join(keys) or fallback


def _chat(prompt: str, client=None, max_tokens: int = 160) -> str:
    """ONE-SHOT. Summarising a conversation is a question with an answer; nothing continues it.

    Through chat() this landed in the ONE RESIDENT KV SLOT — the one holding his live
    conversation — and evicted it, so his very next turn re-prefilled from token 0. A
    summariser that costs the thing it is summarising is not a summariser.
    """
    # ── THE SIDECAR CONSOLIDATOR (2026-08-20) — built, gated, DARK by default. ──
    # Extraction/summarization is squarely the small model's job, and every fact
    # this file mints is stamped `inferred` regardless of who paraphrased it. But
    # consolidation writes into HER memory, so the offload stays dark until its
    # outputs have been read side by side against the model's on a real day
    # (OFF-BY-DEFAULT §11 carries the arming condition). Fail-open as always: a
    # dark or empty sidecar falls through to the model one-shot below.
    if os.environ.get("SP_AUX_CONSOLIDATE", "0") == "1" and client is None:
        try:
            from harness.sidecar import client as _aux
            if _aux.available():
                out = _aux.chat([{"role": "user", "content": prompt}],
                                max_tokens=max_tokens)
                if out:
                    return out
        except Exception as _swx:
            _swallowed(_swlog, "_chat", _swx, lane="skills")
    from harness.inference.client import get_client
    client = client or get_client()
    if hasattr(client, "oneshot"):
        return (client.oneshot([{"role": "user", "content": prompt}],
                               max_tokens=max_tokens, temperature=0.0) or "").strip()
    # test doubles / older clients keep the old path
    from harness.inference.inference_config import InferenceConfig
    cfg = InferenceConfig(temperature=0.0, max_tokens=max_tokens, auto_recall=False)
    return client.chat(messages=[{"role": "user", "content": prompt}], config=cfg).text.strip()


def _cmd_add_fields() -> set:
    """Every `a.<attr>` that `okf_mem.cmd_add` reads, parsed from its source.

    Read rather than restated so this cannot drift again (see the note in _okf_add). Falls
    back to a known-good superset if the source moves — a missing field must degrade to
    None, never to an AttributeError inside a night job nobody is watching."""
    try:
        import ast
        import inspect
        src = inspect.getsource(ok.cmd_add)
        tree = ast.parse(textwrap.dedent(src))
        return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == "a"}
    except Exception as _swx:
        _swallowed(_swlog, "_cmd_add_fields", _swx, lane="skills")
        return {"root", "full_file", "blob_ref", "addr", "kind", "keys", "summary", "title",
                "detail", "detail_file", "status", "gate", "commit", "repro", "mem_class",
                "delivery", "authority", "retrieval_key", "decline_when",
                "decline_message", "confidence"}


def _okf_add(root: str, addr: str, keys: str, summary: str, full_body: str, detail: str, kind: str = "agent") -> str:
    tf = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    tf.write(full_body)
    tf.close()
    # ── THE ARGPARSE NAMESPACE THAT WENT STALE (2026-07-30) ──────────────────────────
    # `ok.cmd_add` is a CLI handler: it reads its arguments off an argparse Namespace,
    # where every declared flag exists (as None if unset). This hand-built stand-in listed
    # the fourteen fields cmd_add read AT THE TIME, and when the MEM-OKF v2 policy block
    # landed (mem_class / delivery / authority / retrieval_key / decline_*) cmd_add grew
    # SEVEN more reads that nothing here supplied. Result:
    #     AttributeError: 'types.SimpleNamespace' object has no attribute 'mem_class'
    # — and it went unnoticed for weeks because `store_conversation`'s only caller was
    # `consolidate_current`, whose only caller was `run_agency_scheduler`, which nothing
    # called. The dead path was also broken; wiring the day boundary is what found it.
    #
    # Derive the field list FROM cmd_add rather than restating it, so the next flag
    # cmd_add grows defaults to None here instead of raising. A hand-maintained mirror of
    # someone else's signature is the two-copies bug with an argparse hat on.
    _fields = _cmd_add_fields()
    ns = types.SimpleNamespace(**{f: None for f in _fields})
    ns.root, ns.full_file, ns.blob_ref, ns.addr, ns.kind = root, tf.name, None, addr, kind
    ns.keys, ns.summary, ns.title = keys, summary[:200], None
    ns.detail, ns.detail_file = detail, None
    ns.status, ns.gate, ns.commit, ns.repro = "ACTIVE", "none", None, None
    try:
        ok.cmd_add(ns)
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass
    return addr


# ──── LONG-term: store / recall / dig a whole conversation ─────────────────
def summarize_conversation(messages: List[dict], client=None) -> str:
    """Distil a conversation into a 2-3 sentence factual gist (the summary tier)."""
    t = _transcript(messages)
    if not t:
        return ""
    prompt = ("Summarize this conversation in 2-3 sentences. Capture the key FACTS the user "
              "stated and the topics discussed. Be factual and concise; do not invent.\n\n"
              f"{t}\n\nSummary:")
    return _chat(prompt, client=client, max_tokens=140)


def store_conversation(messages: List[dict], summary: Optional[str] = None, client=None) -> Optional[str]:
    """Store a conversation COMPLETE (full/) and SUMMARIZED (sum/), linked by one sha256 addr."""
    t = _transcript(messages)
    if not t:
        return None
    # OFF THE RECORD HOLDS THE LONG STORE TOO (2026-08-28, external review): this writes
    # the COMPLETE transcript under memory-okf-conv — the largest single leak an anon
    # evening could have, and the only conversation-shaped one. Same guard as every door.
    try:
        from harness.control import anon as _anon
        if _anon.holds("conversation.store"):
            return None
    except Exception as _swx:
        _swallowed(_swlog, "store_conversation", _swx, lane="skills")
    if summary is None:
        summary = summarize_conversation(messages, client=client) or t[:160]
    addr = ok.addr_of(t)
    keys = _keys_from(summary)
    _okf_add(CONV_ROOT, addr, keys, summary, full_body=t, detail=summary, kind="agent")
    return addr


def recall_conversations(query: str) -> str:
    """Search past conversations and return the GIST (summary) of each match. Default disclosure."""
    if not os.path.exists(os.path.join(CONV_ROOT, ok.LUT_NAME)):
        return "(no past conversations stored)"
    q = query.lower()
    hits = [r for r in ok.lut_rows(CONV_ROOT) if q in r[2].lower() or q in r[3].lower()]
    if not hits:
        return f"(no past conversation matches '{query}')"
    return "\n".join(f"[{r[0]}] {r[3]}" for r in hits)


def read_conversation(addr: str) -> str:
    """DIG DEEPER: return the FULL transcript of a stored conversation by its address."""
    p = os.path.join(CONV_ROOT, ok.FULL_DIR, addr + ".md")
    if not os.path.exists(p):
        return f"(no stored conversation '{addr}')"
    _, body = ok.parse_fm(ok.read(p))
    return body.strip()


# ──── MID-term: extract durable facts -> the recall registry ───────────────
def extract_facts(messages: List[dict], client=None) -> List[str]:
    """Pull the durable FACTS the user stated out of a conversation (one per line)."""
    t = _transcript(messages)
    if not t:
        return []
    # ── BY HIS NAME, NOT "THE USER" (2026-08-28, his ask: "her memories are of Sam,
    # not of the user"). The prompt said "the user", so the model wrote rows that begin
    # "The user ..." — 24 of the 25 such rows in the live store carried src=consolidator,
    # this pass. A memory of a person is written in that person's name; "the user" is a
    # role, and a companion who files her person under a role is keeping records, not
    # knowing someone. The name comes from PersonModel.who — the one authority the export
    # already rewrites for the blank slate, so a fresh clone's companion writes its own
    # operator's name and never his.
    from harness.model.person import PersonModel as _PM
    _who = _PM.who or "the user"
    # "still be true next week" — the store had "Sam needs to pee", "Sam's eyes are
    # wide" filed as durable FACTS (class fact, year-long half-life) by this pass. A
    # moment is not a memory; the admission door catches some of these, but the cheapest
    # place to not-store a thing is to not-extract it.
    prompt = ("Conversation:\n" + t + "\n\n"
              "Write the facts %s (the human) stated about themselves above, each as one "
              "short sentence on its own line, naming them as %s — never as 'the user'. "
              "Only facts that will still be true next week; never momentary states "
              "(what they need, feel or look like right now). "
              "Output only the facts, nothing else.\n\nFacts %s stated:"
              % (_who, _who, _who))
    r = _chat(prompt, client=client, max_tokens=160)
    facts = []
    # Echo guard: a genuine user fact never contains these meta words (the model sometimes
    # parrots the instruction back instead of extracting).
    meta = ("conversation", "extract", "instruction", "do not", "durable",
            "one per line", "own line", "the facts the user", "output only",
            "naming them as", "the human")
    for ln in r.splitlines():
        s = ln.strip().lstrip("-*0123456789.) ").strip()
        sl = s.lower()
        if not (6 <= len(s) <= 160):
            continue
        if "none" in sl[:6] or any(b in sl for b in meta):
            continue
        # BELT UNDER THE PROMPT: a model that writes "The user ..." anyway is corrected at
        # the seam, so the instruction failing quietly cannot re-grow the pile of role-rows
        # this change exists to end. Leading position only — a sentence ABOUT users stays.
        s = re.sub(r"^[Tt]he user\b", _who, s)
        facts.append(s)
    return facts


def consolidate_conversation(messages: List[dict], client=None) -> dict:
    """The extraction pass (short -> mid + long): extract facts into the registry AND store the
    whole conversation (full + summary). Returns {facts, conversation_addr}."""
    from harness.skills.memory import remember
    facts = extract_facts(messages, client=client)
    stored = []
    for f in facts:
        r = remember(f, source="consolidator")   # MEM-OKF v2 §M1: provenance = the extraction pass
        stored.append((f, r))
    addr = store_conversation(messages, client=client)
    return {"facts": stored, "conversation_addr": addr}


# ──── CAPABILITIES corpus + init primer ────────────────────────────────────
CAPABILITIES = [
    ("identity", "What you are",
     "You are Kairos, an experimental AI running locally on a single RTX 2060 with a real, auditable working memory."),
    ("memory-remember", "Store a fact",
     "State a fact and it is captured to long-term memory automatically; or call the remember tool. Facts survive across turns and restarts."),
    ("memory-recall", "Recall facts",
     "Relevant stored facts are recalled automatically; or call list_memories to see your whole memory."),
    ("memory-forget", "Forget / update a memory",
     "Say 'forget X' or call the forget tool. When you learn a fact that supersedes or contradicts an old one, the DECIDE pass updates or merges it for you."),
    ("tools-python", "Run code",
     "To run code, emit <tool name=\"run_python\">{\"code\": \"print(2+2)\"}</tool> and use the result. Pass code as a JSON string."),
    ("tools-calc", "Compute",
     "To compute an expression, emit <tool name=\"calculate\">{\"expression\": \"47*89\"}</tool>."),
    ("conversation-recall", "Remember past conversations",
     "Past conversations are stored summarized and complete. Call recall_conversations(query) for the gist of relevant past chats, then read_conversation(addr) to dig into the full transcript."),
    ("agency", "Maintain your own memory",
     "Between turns you review your memory and curate it: forgetting redundant facts and consolidating related ones, so your memory stays consistent."),
    # PK2 §P2 self-knowledge refresh — the organism can now state its new abilities.
    ("provenance", "Know where a memory came from",
     "Every fact you store carries its source and time. Call provenance(fact) to answer 'where/when did I learn that?' — the MEM-OKF v2 provenance lane."),
    ("coding", "Edit and test code",
     "You can read, write, and precisely EDIT files (edit_file: exact find/replace), search the workspace, run shell commands, and run pytest (run_tests) — a real coding loop, sandboxed to the workspace."),
    ("tasks", "Work multi-step tasks on your own",
     "You can take a goal and work it across many steps (plan, act, observe, verify) under a step + time budget, saving progress so a task resumes after a restart. Operator-posted tasks you advance between chats."),
    ("hygiene", "Keep your own memory tidy",
     "You can verify your fact registry (verify_registry) for duplicates/malformed rows and compact it (compact_registry) — hygiene, not forgetting."),
]


def seed_capabilities() -> List[str]:
    """Write the capabilities corpus into the MEM-OKF caps store (recallable 'how do I use myself')."""
    addrs = []
    for key, summary, detail in CAPABILITIES:
        body = f"# {summary}\n\n{detail}\n"
        addr = ok.addr_of(body)
        _okf_add(CAPS_ROOT, addr, keys=key, summary=summary, full_body=body, detail=detail, kind="agent")
        addrs.append(addr)
    return addrs


def recall_capability(query: str) -> str:
    """Look up how to use a capability (gist)."""
    if not os.path.exists(os.path.join(CAPS_ROOT, ok.LUT_NAME)):
        return "(capabilities not seeded)"
    q = query.lower()
    hits = [r for r in ok.lut_rows(CAPS_ROOT) if q in r[2].lower() or q in r[3].lower()]
    if not hits:
        return f"(no capability matches '{query}')"
    return "\n".join(f"- {r[3]}" for r in hits)


def init_primer() -> str:
    """The on-init priming text: a compact 'how to use yourself' the system loads at start."""
    lines = ["You are Kairos. You can use yourself as follows:"]
    for _key, summary, detail in CAPABILITIES:
        lines.append(f"- {summary}: {detail}")
    return "\n".join(lines)


# Tools the model can call (alongside harness.skills.memory.MEMORY_TOOLS).
CONVERSATION_TOOLS = [recall_conversations, read_conversation]
