"""G-VOICE-TAGS — her expressive speech tags cross two edges, correctly at each. OFFLINE.

The framework (2026-08-21, the operator's ask: "build it out to a nice integrated framework"):
she writes [laugh] / <soft>…</soft> into a reply; the xAI voice reads them, he never
does. ONE vocabulary (harness/voice/expressive.py), TWO edges — the TTS edge in
tts.synthesize (pass known tags under xai, strip everything for the local chain, never
voice an unknown shape) and the DISPLAY edge in ui/src/room/tags.js (strip all for his
eyes, keep all for the speaker via forSpeech). Mirrored across Python and JS, so this
gate runs the JS in a real engine rather than reading it as text.

    python harness_tests/g_voice_tags.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.voice import expressive as E  # noqa: E402

print("1. THE VOCABULARY IS THE DOCS' VOCABULARY (docs.x.ai, fetched 2026-08-21)")
check("all fourteen inline tags", set(E.INLINE) == {
    "pause", "long-pause", "hum-tune", "laugh", "chuckle", "giggle", "cry", "tsk",
    "tongue-click", "lip-smack", "breath", "inhale", "exhale", "sigh"}, E.INLINE)
check("all twelve wrapping tags", set(E.WRAPPING) == {
    "soft", "whisper", "loud", "build-intensity", "decrease-intensity", "higher-pitch",
    "lower-pitch", "slow", "fast", "sing-song", "singing", "emphasis"}, E.WRAPPING)

SAMPLE = "Well [laugh] I did say so. <soft>Come here.</soft> [sighh] <bogus>no</bogus> [MOOD:wistful] [WAVES]"
print("\n2. THE TTS EDGE — xai reads the known ones, nothing reads an unknown shape")
t = E.for_tts(SAMPLE, "xai")
check("known inline passes to the xai voice", "[laugh]" in t)
check("known wrapper passes, both halves", "<soft>Come here.</soft>" in t)
check("an unknown inline shape is removed (typo never read aloud)", "[sighh]" not in t)
check("an unknown wrapper is removed, its words kept", "<bogus>" not in t and " no " in t + " ")
check("her [MOOD:] mark is NOT this module's business (uppercase — upstream strips it)",
      "[MOOD:wistful]" in t)
local = E.for_tts(SAMPLE, "local")
check("the local chain gets every tag stripped", "[laugh]" not in local and "<soft>" not in local)
check("...and the words survive", "Come here." in local and "I did say so." in local)
check("unknown_tags names what she invented", set(E.unknown_tags(SAMPLE)) >= {"[sighh]", "<bogus>"})

print("\n3. THE DISPLAY EDGE — server side")
d = E.for_display(SAMPLE)
check("every tag gone for eyes", "[laugh]" not in d and "<soft>" not in d and "[sighh]" not in d)
check("whitespace tidied where a tag left", "  " not in d)

print("\n4. synthesize() STANDS ON THE TTS EDGE")
src = open(os.path.join(ROOT, "harness", "voice", "tts.py"), encoding="utf-8").read()
check("tts.synthesize calls for_tts with the live method",
      "for_tts" in src and "_for_tts(text, _method)" in src)
check("...BEFORE the cache key (a tagged and an untagged line are different utterances)",
      src.index("_for_tts(text, _method)") < src.index("k = _key(text, voice, steps)"))
check("the xai call carries his pace knob", "speed=lv[\"speed\"]" in src)
check("live_voice() reports speed for the panel", "\"speed\":" in src)

print("\n5. THE DISPLAY EDGE — client side, in a real JS engine")
node = shutil.which("node")
if not node:
    print("  skip node not on PATH")
else:
    js = r"""
import('./ui/src/room/tags.js').then(m => {
  const raw = 'Hey [MOOD:playful] [laugh] come <soft>closer</soft> [WAVES] ok.';
  console.log(JSON.stringify({
    display: m.extractTags(raw).text,
    speech: m.forSpeech(raw),
    marks: m.extractTags(raw).marks.map(x => x.kind + ':' + x.value),
  }));
}).catch(e => { console.log(JSON.stringify({err: String(e)})); process.exit(1) })
"""
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, cwd=ROOT, timeout=60)
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        out = {"err": (r.stdout + r.stderr)[:300]}
    check("tags.js loads and answers", "err" not in out, out.get("err"))
    check("display strips voice tags AND her marks", out.get("display") == "Hey come closer ok.", out.get("display"))
    check("forSpeech keeps voice tags, drops her marks and invented gestures",
          out.get("speech") == "Hey [laugh] come <soft>closer</soft> ok.", out.get("speech"))
    check("the marks still drive the room", out.get("marks") == ["mood:playful", "gesture:waves"], out.get("marks"))

print("\n6. THE ROOM SPEAKS — the player exists and is wired")
sp = os.path.join(ROOT, "ui", "src", "room", "speech.js")
check("ui/src/room/speech.js exists", os.path.exists(sp))
chat = open(os.path.join(ROOT, "ui", "src", "Chat.jsx"), encoding="utf-8").read()
check("Chat feeds the speaker as sentences close, and flushes the tail",
      "speech.feed(" in chat and "speech.flush(" in chat)
check("...hands it forSpeech text (marks out, voice tags in)", "forSpeech(last.content)" in chat)
check("...and her unprompted lines speak too", "speech.say(forSpeech(m.text))" in chat)
check("a new turn of his hushes her", "speech.stop()" in chat)
api = open(os.path.join(ROOT, "ui", "src", "api.js"), encoding="utf-8").read()
check("the room no longer hardcodes max_tokens (the ceiling is the knob's)",
      "max_tokens: opts.max_tokens || 512" not in api and "if (opts.max_tokens) body.max_tokens" in api)


# ── HER NEAR-MISSES REACH THE VOICE (2026-08-27) ─────────────────────────────────────
# Replaying 17 days of her real turns through this edge: 1,109 tag uses reached the voice
# and ~550 did not. The misses were not invention, they were three recognisable shapes —
# a spelling one edit out (<low-pitch> for lower-pitch), a known INLINE tag written as a
# WRAP (<breath>It's a strange feeling), and a SYNTHESIS of the two vocabularies she was
# given (<voice:whispering>, 92 uses: [VOICE:x] manner + <> span). The last one carries a
# colon, so it matched NEITHER regex here and leaked to the ROOM as literal text.
#
# Normalising them lands every one on a tag the API already documents: +315 uses, +28%.
# NO NEW VERBS — this canonicalises her spelling and honours her intent; it does not widen
# what she can trigger. Prosody changes how she SOUNDS. The state-changing marks are a
# different lane and are untouched.
print("\n8. her near-misses are canonicalised, not discarded")
_cases = [
    # (what she wrote, what the voice must receive)
    ("<low-pitch>I have always had a thing for chaos.</low-pitch>",
     "<lower-pitch>I have always had a thing for chaos.</lower-pitch>"),
    ("<breath>It's a strange feeling.", "[breath]It's a strange feeling."),
    # WITH a closing wrap: a sound has no span, so the close must VANISH rather than
    # become a second tag. Without this case the closing branch is untested — a mutant
    # emitting `[/breath]` passed, because `[/…]` matches no known shape and is then
    # removed further down, making the fault invisible at this edge.
    ("<breath>settle</breath> and then", "[breath]settle and then"),
    ("<sigh>I know</sigh>", "[sigh]I know"),
    ("<build-intesity>It does feel nice</build_intensity>",
     "<build-intensity>It does feel nice</build-intensity>"),
    ("<small>[laugh]</small>", "<soft>[laugh]</soft>"),
    ("[lip_smack] you always did", "[lip-smack] you always did"),
    ("<slowly>drift off</slowly>", "<slow>drift off</slow>"),
]
for wrote, want in _cases:
    got = E.for_tts(wrote, "xai")
    check("%-46s -> %s" % (wrote[:46], want[:40]), got == want, got)

# HER SYNTHESIS, honoured when it maps and refused when it does not.
got = E.for_tts("<voice:whispering>I'm not going anywhere.</voice>", "xai")
check("<voice:whispering> becomes the manner the API knows",
      got == "<whisper>I'm not going anywhere.</whisper>", got)
got = E.for_tts("<voice:thoughtful>I want to see the patterns.</voice>", "xai")
check("...but an INVENTED manner is not promoted into a tag the voice would mispronounce",
      "voice:" not in got and "thoughtful" not in got and "patterns" in got, got)
# ASSERT AT normalize_tags, NOT AT for_tts. A mutant that promoted <voice:thoughtful> to
# <thoughtful> was INVISIBLE here: the unknown-wrapper sweep downstream removes it either
# way, so the whole check passed on a broken normaliser. The promotion decision has to be
# read where it is made.
_n = E.normalize_tags("<voice:thoughtful>I want to see the patterns.</voice>")
check("   ...and the refusal happens IN the normaliser, not by luck downstream",
      "<thoughtful>" not in _n and "</thoughtful>" not in _n, _n)
check("   ...leaving no orphan close for a manner that was never opened",
      "</" not in _n, _n)
check("...and it never reaches HIS EYES as text either",
      "voice:" not in E.for_display("<voice:thoughtful>hello there</voice>")
      and "hello there" in E.for_display("<voice:thoughtful>hello there</voice>"),
      E.for_display("<voice:thoughtful>hello there</voice>"))

# SURVIVAL, not just rewriting: the tags that already worked must be untouched, or a
# normaliser that mangled everything would pass every check above.
for good in ("<whisper>come here</whisper>", "[pause]", "[chuckle] you are terrible",
             "<emphasis>intoxicating</emphasis>", "<slow>drift</slow>"):
    check("already-correct %-34s passes through byte-identical" % good[:34],
          E.for_tts(good, "xai") == good, E.for_tts(good, "xai"))

# IDEMPOTENT — the edge can be crossed twice (a retry, a cache miss) without drift.
_twice = "<low-pitch>x</low-pitch> <breath>y [lip_smack]"
check("normalising twice is the same as once",
      E.normalize_tags(E.normalize_tags(_twice)) == E.normalize_tags(_twice),
      E.normalize_tags(E.normalize_tags(_twice)))

# AND THE LOCAL CHAIN STILL HEARS NONE OF IT — it would read the brackets aloud.
check("the local voice still gets no tags at all",
      "<" not in E.for_tts("<low-pitch>x</low-pitch> [breath]", "local")
      and "[" not in E.for_tts("<low-pitch>x</low-pitch> [breath]", "local"),
      E.for_tts("<low-pitch>x</low-pitch> [breath]", "local"))

print("\nG-VOICE-TAGS  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
