// Run by g_marks_leak. Evaluates ui/src/room/tags.js's OWN `_loose` builder and proves
// every regex it yields actually CONSTRUCTS in a JS engine.
//
// WHY THIS EXISTS. On 2026-08-06 the mirror was widened to absorb `[MOOD_shift:...]` and
// the new suffix was written `[_\- ]`. That is correct in Python. In a JS *string* `\-`
// is not an escape, so the regex engine received `[_- ]` — a RANGE from `_` (0x5F) to
// space (0x20), out of order — and `new RegExp` threw AT MODULE LOAD. Not a broken chip:
// the whole bundle failed to evaluate and the room rendered nothing at all.
//
// Every other check in the suite reads the file as text. Text cannot tell you that a
// pattern compiles, and a pattern that does not compile is a blank screen.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
// `_loose` in ui/src/room/tags.js; `TAG_LOOSE` in console/index.html — the THIRD copy,
// which drifted for two weeks precisely because nothing constructed it (2026-08-19).
const m = src.match(/const (?:_loose|TAG_LOOSE) = \(w\) => (.+)/);
if (!m) {
  console.log("NO_LOOSE");
  process.exit(2);
}
const _loose = new Function("w", "return " + m[1].replace(/;\s*$/, ""));

// The spellings the mirror has to keep catching, so a fix that makes it merely COMPILE
// but stop matching is caught here too.
const PROBES = {
  MOOD: ["[MOOD:tender]", "[MOOD_shift:playful]", "[MOODing:wistful]", "[MOOD-wistful]"],
  VOICE: ["[VOICING:soft, warm]", "[VO_ICE:flirty]"],
  TRAIT: ["[TRAITS:+naughty]", "[TRAIT:+flirty]"],
  WEAR: ["[WEAR:the grey jumper]"],
  SHOW: ["[SHOW:a moment]"],
};

const lines = [];
for (const w of Object.keys(PROBES)) {
  const body = _loose(w);
  let re;
  try {
    re = new RegExp("\\[\\s*(?:" + body + ")\\s*[:\\-]([^\\]]+)\\]", "i");
  } catch (e) {
    lines.push(w + " THROWS " + e.message);
    continue;
  }
  const probes = PROBES[w];
  const hit = probes.filter((p) => re.test(p)).length;
  lines.push(w + " OK " + hit + "/" + probes.length);
}
console.log(lines.join("\n"));
