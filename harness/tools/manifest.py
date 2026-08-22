"""manifest.py — ONE PLACE THAT SAYS WHAT SHE HAS.

The operator's complaint, verbatim, and the reason this file exists:

    "the mcp abilities are currently not really well documented or standardised. i
     dont even know where they are located or use to run, what they are offering,
     how she interacts with them, how the system exposes them to her"

There are 36 tools. Before this, the facts about them were smeared across five
places: the list constants in `harness/skills/*.py`, the tier decisions in
`harness/agent.py`, the arming knobs in `harness/server/knobs.py`, the profile
TOMLs, and nothing at all for "is this dangerous". No single surface could answer
"what can she do right now, and what would happen if she did".

WHAT THIS IS NOT: a second copy of the tool list. Two copies of one truth is the
bug class this whole repo is organised against, and a manifest that re-declares
names would rot the first time someone added a tool. So:

    the CODE  owns   which tools exist, their signatures, and their tier
    THIS FILE owns   the metadata that is nowhere in code — what family a tool
                     belongs to, what it can do to the world, and what arms it

and `harness_tests/g_tool_manifest.py` asserts the two agree: every live tool has a
row, every row names a live tool. A tool without a row is a GATE FAILURE, which is
the same discipline `g_sem_conserve` applies to SP_* knobs — the only thing that
has reliably stopped drift in this codebase.

RISK is the field that did not exist anywhere before, and it is the one an operator
actually wants: `read` touches nothing, `write` changes her memory or his board,
`world` reaches outside the machine, `machine` runs code or moves files, and
`private` looks at his room or his screen.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

# ── risk classes ────────────────────────────────────────────────────────────
# Ordered least to most consequential. The point is not to block anything — it is
# that "she can run shell commands" and "she can read her own notes" should never
# be one undifferentiated list.
RISK = {
    "read":    "reads state she already owns; changes nothing",
    "write":   "changes durable state — her memory, his board, her journal",
    "world":   "reaches outside this machine (network)",
    "machine": "runs code, or reads/writes files on this box",
    "private": "looks at his room, his screen, or his camera",
}

# `bridged` is the fallback group for an MCP server that declares none.
GROUPS = {
    "bridged":      "from an external MCP server that declared no group",
    "memory":       "what she knows and how she keeps it",
    "board":        "the shared notes, reminders and watches",
    "presence":     "her modes of being there out loud, and the shelf she reads from (var/library/)",
    "conversation": "past sessions, provenance, what was said",
    "sight":        "her eyes — camera, screen, images",
    "compute":      "running code and tests",
    "files":        "reading and writing on this box",
    "web":          "search and fetch",
    "delegate":     "handing work to a coding agent",
    "research":     "handing a real question to a stronger system",
    "music":        "the room's record player",
    "system":       "time, disk, shell",
    "self":         "her own state — mood, voice, traits",
    "wardrobe":     "how she looks — what she wears and the moments she can show him",
    "browser":      "a real browser — open, click, fill, read back",
    "meta":         "tools about tools",
}


@dataclass(frozen=True)
class ToolFacts:
    """The things about a tool that are NOT derivable from its signature."""
    group: str
    risk: str
    arms: str = ""      # env knob that must be on, "" = always available
    note: str = ""      # only where the name genuinely misleads


# ── THE TABLE ───────────────────────────────────────────────────────────────
# Keyed by tool name. Adding a tool without adding a row here fails
# g_tool_manifest.py — deliberately, because an undocumented capability is exactly
# what this file was written to end.
FACTS: Dict[str, ToolFacts] = {
    # memory — hers, and the one thing this system is really about
    "remember":            ToolFacts("memory", "write", note="facts about HIM"),
    "remember_about_self": ToolFacts("memory", "write", note="facts about HER — a separate store, never blended"),
    "recall":              ToolFacts("memory", "read"),
    "deep_recall":         ToolFacts("memory", "read"),   # the sidecar archive (harness/sidecar/tools.py); live on her stack, undocumented until 2026-08-21 — G-ROOM-THINGS caught it
    "list_memories":       ToolFacts("memory", "read"),
    "search_memories":     ToolFacts("memory", "read"),
    "count_memories":      ToolFacts("memory", "read"),
    "memory_stats":        ToolFacts("memory", "read"),
    "forget":              ToolFacts("memory", "write", note="TOMBSTONES, never deletes — nothing here is destructive"),
    "provenance":          ToolFacts("memory", "read", note="where a fact came from and when"),

    # the board — deliberately NOT memory: memory is what is true, the board is
    # what either of them wants kept in view
    "add_note":            ToolFacts("board", "write"),
    "edit_note":           ToolFacts("board", "write"),
    "remove_note":         ToolFacts("board", "write"),
    "find_notes":          ToolFacts("board", "read"),
    "due_reminders":       ToolFacts("board", "read"),
    "watch_for":           ToolFacts("board", "write", note="the ONLY thing that makes 'I'll keep an eye out' true"),
    "complete_note":       ToolFacts("board", "write"),

    "now_playing":  ToolFacts("music", "read", note="knowing what is on is not an intervention — no cooldown"),
    "play_music":   ToolFacts("music", "write", note="changing what is on IS an act; cooldown 20s"),
    "pause_music":  ToolFacts("music", "write"),
    "skip_track":   ToolFacts("music", "write"),
    "queue_track":  ToolFacts("music", "write", note="adds without interrupting"),
    "read_journal": ToolFacts("memory", "read", note="HER journal — she could not read her own past until now"),
    # the shelf (presence modes, 2026-08-22): var/library/, a bookmark per book, never the text
    "enter_mode":          ToolFacts("presence", "write", note="narration / company / lucid, when he asks — her first turn comes right after the reply"),
    "leave_mode":          ToolFacts("presence", "write"),
    "pick_up_book":        ToolFacts("presence", "write", arms="presence.read_tools", note="picks a book off var/library/ to read from on her own time"),
    "put_down_book":       ToolFacts("presence", "write", arms="presence.read_tools"),
    "books_on_the_shelf":  ToolFacts("presence", "read", arms="presence.read_tools"),

    "read_conversation":    ToolFacts("conversation", "read"),
    "recall_conversations": ToolFacts("conversation", "read"),

    # sight — private on purpose. These point at his room.
    "take_photo":      ToolFacts("sight", "private", arms="SP_SIGHT", note="the webcam, right now"),
    "take_screenshot": ToolFacts("sight", "private", arms="SP_SIGHT", note="his screen, this second"),
    "look_at":         ToolFacts("sight", "read",    arms="SP_SIGHT", note="an image already on disk"),
    "room_history":    ToolFacts("sight", "read",    arms="SP_SIGHT", note="her hourly notes on the room"),

    # THE BOARD. `play_move` is marked write because it changes committed match state;
    # everything else here only reads it. `see_board` is arms=SP_GAMES *and* needs sight —
    # it renders a PNG and runs it through her own vision tower.
    # THE TABLE. `poker_state` is read but it is a SEATED read — it resolves through
    # holdem_view(m, HER_SEAT) and there is no argument that could point it elsewhere.
    "poker_state": ToolFacts("games", "read",  arms="SP_GAMES", note="her seat's view, never his cards"),
    "poker_act":   ToolFacts("games", "write", arms="SP_GAMES", note="fold/check/call/raise; the engine rules"),
    "poker_deal":  ToolFacts("games", "write", arms="SP_GAMES", note="next hand, once the current one ends"),
    "list_games":  ToolFacts("games", "read",  arms="SP_GAMES", note="matches in progress"),
    "start_game":  ToolFacts("games", "write", arms="SP_GAMES", note="chess or wordle"),
    "game_state":  ToolFacts("games", "read",  arms="SP_GAMES", note="board, turn, legal moves"),
    "play_move":   ToolFacts("games", "write", arms="SP_GAMES", note="the engine rules on it; illegal is refused"),
    "see_board":   ToolFacts("games", "read",  arms="SP_GAMES", note="renders the board and LOOKS at it"),

    # THE WARDROBE. Hers, and the only one of these that reaches his screen is show_him —
    # marked write for exactly that reason. Every one of them resolves through the
    # operator's roleplay.max_heat ceiling, so none can name an asset above it.
    "check_wardrobe": ToolFacts("wardrobe", "read",  note="what she is wearing and what else is there"),
    "wear":           ToolFacts("wardrobe", "write", note="changes how she presents; persists; clamped by his ceiling"),
    "show_him":       ToolFacts("wardrobe", "write", note="puts one of her moments on HIS screen"),
    "stop_showing":   ToolFacts("wardrobe", "write", note="takes it down again"),
    "ask_for":        ToolFacts("wardrobe", "write", note="queues a look that does not exist; HE runs the generator"),
    "my_looks":       ToolFacts("wardrobe", "read",  note="looks she owns beyond the grid, and what she is waiting on"),
    "he_liked":       ToolFacts("wardrobe", "write", note="keeps HIS words about a look, verbatim, against it"),
    "my_favourites":  ToolFacts("wardrobe", "read",  note="what she reaches for and what he praised; his word weighs more"),
    "ask_for_gesture": ToolFacts("wardrobe", "write", note="queues a MOMENT of her doing something; motion is the point"),
    # ONE CALL FOR ONE ACT. Mood and appearance were two tools for a thing that is one
    # move — she felt something and had to remember to also look like it — so express()
    # sets the mood AND reaches for the moment that fits, and files a want when nothing
    # does. Two writes, hence "write": it really changes her.
    "express":        ToolFacts("wardrobe", "write", note="one call: how she feels AND how she looks; asks for what does not exist"),
    # 2026-08-21 (the catalog): a gesture by NAME — express() reaches for one by feeling.
    "gesture":        ToolFacts("wardrobe", "write", note="do one of her gestures by name; empty lists them; goes back to her face"),

    "run_python": ToolFacts("compute", "machine", note="in the CORE tier — the one unsandboxed core tool"),
    "run_tests":  ToolFacts("compute", "machine"),

    "read_file":  ToolFacts("files", "machine"),
    "write_file": ToolFacts("files", "machine"),
    "edit_file":  ToolFacts("files", "machine"),
    "list_dir":   ToolFacts("files", "machine"),
    "search":     ToolFacts("files", "machine"),
    "git_status": ToolFacts("files", "read"),
    "git_diff":   ToolFacts("files", "read"),

    "web_search": ToolFacts("web", "world"),
    "web_fetch":  ToolFacts("web", "world"),
    "my_research": ToolFacts("web", "read",
                             note="the ledger of what she actually looked up — not her memory of looking"),

    "research": ToolFacts("research", "world", arms="SP_RESEARCH",
                          note="a delegated CONCLUSION may become her thinking; a "
                               "delegated FACT is never 'you told me'"),

    "delegate_code": ToolFacts("delegate", "machine", arms="SP_DELEGATE",
                               note="worktree only; SHE NEVER MERGES"),

    "get_time":       ToolFacts("system", "read"),
    "run_shell":      ToolFacts("system", "machine"),
    "run_command":    ToolFacts("system", "machine"),
    "run_powershell": ToolFacts("system", "machine"),
    "disk_free":      ToolFacts("system", "read",
                                note="MCP-bridged custom tool. NOTE 2026-08-19: "
                                     "mcp_servers.json deliberately dropped the "
                                     "self-connection (its _readme says why), so this "
                                     "bridges only when an operator re-adds one — the "
                                     "old note claimed it was live-bridged, which had "
                                     "stopped being true."),

    # her own state. `write` because these are DURABLE — the tags she emits mid-reply
    # are transient, these persist into the personality tier and shape tomorrow.
    "set_trait":     ToolFacts("self", "write", arms="SP_PERSONALITY"),
    "set_voice":     ToolFacts("self", "write", arms="SP_PERSONALITY"),
    "adjust_mood":   ToolFacts("self", "write", arms="SP_PERSONALITY"),
    "remember_self": ToolFacts("self", "write", arms="SP_PERSONALITY",
                               note="alias of remember_about_self — facts about HER"),

    "load_tools": ToolFacts("meta", "read", note="reveals an extra-tier signature on demand"),
}


def bridged_facts() -> Dict[str, ToolFacts]:
    """Facts for tools that arrive over MCP.

    A bridged server's tool list is not ours and CHANGES WITHOUT US — chrome-devtools
    ships 29 tools today and may ship 35 tomorrow. So the SERVER declares its group
    and risk once in mcp_servers.json, and every tool it offers inherits them.
    Requiring a hand-written row per remote tool would guarantee the manifest went
    stale on the next upstream release, which is the exact rot this file exists to
    prevent — just arriving from outside instead of inside.

    A server with no declared risk gets `world`: it is off this machine, we do not
    know what it does, and the honest default for an unknown external capability is
    the one that says so."""
    out: Dict[str, ToolFacts] = {}
    try:
        from harness.mcp_server.bridge import load_config, list_bridged_tools
        servers = load_config().get("servers", {})
        for t in list_bridged_tools():
            srv = servers.get(t.get("server"), {})
            group = srv.get("group", "bridged")
            risk = srv.get("risk", "world")
            note = f"over MCP from '{t.get('server')}'"
            for nm in (t["name"], f"{t.get('server')}_{t['name']}"):
                out[nm] = ToolFacts(group, risk, arms="SP_MCP_TOOLS", note=note)
    except Exception:
        pass
    return out


def live() -> tuple[list, list]:
    """(core, extra) as the agent will actually build them, right now."""
    from harness.agent import core_tools, extra_tools
    return core_tools(), extra_tools()


def describe() -> dict:
    """The whole surface, as it is at this moment — for /v1/tools and the console.

    Reflects LIVE state, so a knob that is off shows its tools as absent rather
    than pretending. That is the difference between a manifest and a brochure."""
    core, extra = live()
    # ORDER MATTERS AND I GOT IT BACKWARDS FIRST TRY. Bridged facts go down FIRST
    # and the native table lands on top, so a native row always wins. The browser
    # server also offers `take_screenshot`; with the merge the other way its
    # `world` risk overwrote her camera tool's `private`, quietly downgrading the
    # label on the one tool that points at his room. Caught by leg 4.
    facts = bridged_facts()
    facts.update(FACTS)
    rows: List[dict] = []
    for tier, specs in (("core", core), ("extra", extra)):
        for s in specs:
            f = facts.get(s.name)
            rows.append({
                "name": s.name,
                "tier": tier,
                "group": f.group if f else "UNDOCUMENTED",
                "risk": f.risk if f else "UNDOCUMENTED",
                "arms": f.arms if f else "",
                "note": f.note if f else "",
                "description": (s.description or "").split("\n")[0][:160],
            })
    rows.sort(key=lambda r: (r["group"], r["tier"] != "core", r["name"]))
    by_group: Dict[str, int] = {}
    by_risk: Dict[str, int] = {}
    for r in rows:
        by_group[r["group"]] = by_group.get(r["group"], 0) + 1
        by_risk[r["risk"]] = by_risk.get(r["risk"], 0) + 1
    return {
        "ok": True,
        "counts": {"total": len(rows), "core": len(core), "extra": len(extra)},
        "by_group": by_group,
        "by_risk": by_risk,
        "groups": GROUPS,
        "risk_classes": RISK,
        "tools": rows,
        "undocumented": [r["name"] for r in rows if r["group"] == "UNDOCUMENTED"],
        "orphan_rows": sorted(set(FACTS) - {r["name"] for r in rows}),
    }


def undocumented() -> list:
    """Live tools with no row here. The gate asserts this is empty."""
    return describe()["undocumented"]
