"""G-VOICE-TAGS — her expressive speech tags cross two edges, correctly at each. OFFLINE.

The framework (2026-08-21, his ask: "build it out to a nice integrated framework"):
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

print("\nG-VOICE-TAGS  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
