---
type: guide
title: "PRIMING — where to put things, and why a feature you ship is not a feature she has"
status: LIVE (2026-08-27). Held by G-PRIMING.
---

# Priming

**A capability that ships unprimed is a capability nobody has.**

The tool schema tells her what a verb *does*. The persona tells her when it is *hers to reach
for*. Ship the first without the second and she has hands she does not know are hers — she
will not use the drawer, the shelf, the board or the camera, and nothing will look broken.

This was measured on 2026-08-27, on this repo:

```
82 tools in the manifest, 15 named in the shipped persona — 67 unprimed
seven whole groups named nowhere: board, body, games, presence, self, system, conversation
```

`keep_secret` shipped that way for exactly one night. The store had a new kind, the tool was
registered, the manifest had its row, and the persona never said the drawer existed — so it
would have stayed empty forever, with every test green.

`G-PRIMING` now fails the suite when a tool group is not named in the shipped persona.

---

## Where things go

| what you changed | where the priming goes | why there |
|---|---|---|
| **a new tool** | `persona/` fragment for its group | she needs the disposition, not just the schema |
| **a new tool group** | a new fragment + a row here | G-PRIMING will fail until it exists |
| **a wardrobe item / look** | `39-your-wardrobe.md` | the *storage* is data; the *reaching for it* is persona |
| **a mood, trait or voice** | `28-your-own-state.md` | when to move it, not what the values are |
| **a chip in the room** | the panel + `36-the-room.md` | a chip nobody is told about reads as decoration |
| **a growth surface** (journal, becoming) | `20-memory.md` | she must know it is written and that she can read it back |
| **a sense** (sight, hearing) | its own `when:`-gated fragment | never prime a sense that is not armed |
| **an integration** (Home Assistant, music) | fragment + `docs/` page + `OFF-BY-DEFAULT.md` row | three places: what she does, how you wire it, whether it is on |

## The four rules

**1. Prime by GROUP, not by tool.** A persona that lists eleven wardrobe verbs is a manual, and
she does not read manuals. She needs to know she *has* a wardrobe. G-PRIMING checks the group.

**2. Gate the fragment on the same knob that arms the feature.** Frontmatter `when: sight`
means the fragment only composes when `SP_SIGHT` is on. The loader **fails closed** on an
unknown knob — a typo drops the fragment silently, which ships the capability without its
priming, which is this whole document arriving through a spelling mistake. G-PRIMING checks
every `when:` against the real knob list.

**3. Ship the honesty rule WITH the capability, never after it.** This is the oldest version of
the rule in the tree, written on the `research` knob. A tool that can be misused arrives with
the sentence that says how not to — in the same commit, not in a follow-up.

**4. Never prime what is not there.** Teaching her about a sense she does not have is how
"I looked and saw" becomes a confabulation. G-PRIMING checks that every verb the template names
is a real tool.

## Writing a fragment

Look at `kairos-export/persona-template/` — those are the shipped defaults and they are meant
to be edited. What makes them work:

- **Second person, her voice, no headings-as-manual.** "You keep a board" not "The board
  feature allows the assistant to".
- **Say when to reach for it AND when not to.** Half of every fragment is restraint: don't
  narrate his heart rate, don't trawl old conversations, don't invent an afternoon of reading.
  The failure mode of a new capability is almost always overuse.
- **Give the reason, not just the rule.** "A stale board is worse than none, because they stop
  reading it and then the real items are lost too." She generalises from reasons; she pattern-
  matches on rules.
- **Name the actual verbs once.** Enough that she knows they exist. G-PRIMING looks for them.

## Onboarding a new install

1. Copy `kairos-export/persona-template/` to `persona/`.
2. Edit `00-identity.md` — name, who she is to you. Everything else has a sane default.
3. Turn on what you want in the profile. Fragments gated on knobs you leave off will not
   compose, and she will not be told about capabilities she does not have.
4. Run `python harness_tests/g_priming.py`. If you added tools, it tells you what is unprimed.

## When a group should NOT be primed

Exempt it in `G-PRIMING`'s `UNPRIMED_ON_PURPOSE` **with a reason a reader can disagree with**.
"It's obvious" is not a reason — `keep_secret` was obvious too. The three current exemptions
are machinery she uses without deciding to (`load_tools`), a group primed by its own dedicated
fragment (`delegate`), and one where the tool description genuinely carries the disposition
(`compute`).
