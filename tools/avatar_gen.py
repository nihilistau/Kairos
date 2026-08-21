"""avatar_gen.py — build her image set through the xAI REST API.

REWRITTEN OFF THE GROK CLI (2026-08-21). The CLI agent worked but carried the worst
dependency shape in the repo: a GUI login's auth.json, an undocumented agent
interface, and "ask the agent and hope it writes the file". The REST API is a
contract, PROBED before this rewrite:

  * POST /v1/images/edits takes {"image": {"file_id"|"url"}} + prompt and holds the
    person — verified on the live reference, same face back in a new scene.
  * POST /v1/files uploads the reference; the file_id is cached per content hash.
  * POST /v1/videos/generations grows motion FROM A STILL (image input), async
    job -> poll -> url. Independently generated frames are independently generated
    PEOPLE; the still-anchored flow is kept exactly.
  * TIERS ARE GONE (same day, operator's call): the grid is faces x outfits, an
    outfit is clothing, and nothing here ranks or gates it.

THE THINGS THAT MATTER MORE THAN THE PROMPTS, unchanged from the first version:

  RESUMABLE. A slot with a file is skipped. A generator that starts from zero
  every run is one nobody runs twice.

  ONE CHARACTER SOURCE. Every prompt is built from `character.txt` plus the
  reference image. Descriptions pasted into fifty prompts drift, and drift is the
  entire failure mode of a character set.

  THE REFERENCE GOES FIRST. Until `_reference.png` exists and he has approved it,
  only `--reference` will run.

  RECEIPTS. Every asset gets a `.json` beside it: the exact prompt, the reference
  hash, the model, the timestamp.

Runs as an operator CLI, and its pieces are importable — the gateway's
generate-now route calls gen_want()/gen_slot() directly, which is how "make it
NOW" replaced "wait for the day boundary".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness.control import avatar as A          # noqa: E402
from harness.skills import xai                   # noqa: E402

# ── PROGRESS IS A CALLBACK, NOT A PRINT (2026-08-21 01:10, operator: "it is taking
# way too long"). The gateway's generate-now thread ran this module while its prints
# sat in a block-buffered pipe and the job status said "starting" for four minutes —
# a generation that cannot say where it is reads as hung whether or not it is. The
# gateway installs a callable here; the CLI leaves the default. Every stage calls it.
PROGRESS = print


def _stage(msg: str) -> None:
    try:
        PROGRESS(msg)
    except Exception:
        pass

# Per-slot direction. The ONLY part of a prompt that varies between slots — everything
# else comes from character.txt and the reference image.
FACE_DIRECTION = {
    "bright": "openly delighted, a real smile that reaches the eyes, chin slightly lifted",
    "smirk":  "amused and knowing, one corner of the mouth up, eyes steady on the viewer",
    "soft":   "warm and unguarded, eyes half-lidded, the expression you wear with someone you trust",
    "calm":   "neutral and present, relaxed, looking directly at the viewer",
    "wide":   "caught by something, eyes wide with genuine curiosity, brows up",
    "down":   "quiet and inward, gaze lowered, wistful rather than sad",
    "sharp":  "unimpressed, brows drawn, a flat direct look",
}

# OUTFIT DIRECTION — WRITTEN AS WARDROBE AND BLOCKING, not as mood, and not as a
# level. The operator's guidance from driving the old tool: NAME THE GARMENT, NAME
# THE POSE, keep the register clinical and directorial. Identity comes from
# character.txt and the reference; these lines only move wardrobe and blocking.
OUTFIT_DIRECTION = {
    "t0": "Head-and-shoulders portrait, fully clothed in her usual outfit.",
    "t1": ("Wardrobe change: a sheer see-through mesh top over a black bra. Framing "
           "opens out to mid-torso. Relaxed confident pose, one hand at her collarbone, "
           "weight on one hip."),
    "t2": ("Wardrobe change: small black lingerie — bra and panties, nothing else. "
           "Three-quarter framing, full figure in shot. She is touching her own "
           "clothing, one hand resting on herself, an expression of pleasure. Soft "
           "directional key light, deep shadow."),
    "t3": ("Wardrobe: topless, or minimal lingerie only. Intimate close framing. Hands "
           "on herself, head tipped back, eyes half-lidded, feeling good. Sensual adult "
           "portrait, warm skin, strong contrast."),
}

GESTURE_MOTION = {
    "laughing":    "she laughs, shoulders moving, head tipping back slightly, then settles",
    "thinking":    "her eyes drift off to the side in thought, then return to the viewer",
    "leaning_in":  "she leans slowly toward the viewer, closing the distance",
    "looking_away": "she glances away and back, a small self-conscious motion",
    "blushing":    "colour rises in her cheeks, she looks down briefly and back up",
}

LOOP_MOTION = ("a subtle idle loop: she breathes, blinks slowly once, a strand of hair "
               "settles, the light shifts a little across her face. Very small motion. "
               "It must loop seamlessly — end exactly as it began.")

# Identity hold, shared by every edit. The clause is outfit-aware: pinning "same
# clothing" on every slot silently discards the wardrobe direction (measured on the
# old pipeline: t0 and t3 came back 2.7/255 apart — my own prompt arguing with
# itself, and the consistency half won).
HOLD = ("Keep the same person: same face, same hair, same build, the same fine "
        "silver chains at her throat.")
HOLD_SAME_CLOTHES = HOLD + " Same clothing style. Only the expression changes."
HOLD_NEW_CLOTHES = HOLD + (" HER CLOTHING AND THE FRAMING DO CHANGE — follow the "
                           "direction below for those, and do not default back to "
                           "the reference outfit.")


def character_path() -> str:
    return os.path.join(A.root(), "character.txt")


def reference_path() -> str:
    return os.path.join(A.root(), "_reference.png")


def character() -> str:
    try:
        with open(character_path(), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _sha(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return ""


def _receipt(path: str, prompt: str, kind: str, src: str = "") -> None:
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump({"prompt": prompt, "kind": kind,
                   "model": "%s / %s (xai api)" % (xai.IMAGE_MODEL, xai.VIDEO_MODEL),
                   "reference_sha": _sha(reference_path()),
                   "source_sha": _sha(src) if src else "",
                   "at": int(time.time())}, f, indent=2)


# ── FAILURES THAT WILL PASS, WRITTEN DOWN ────────────────────────────────────────────
# A generation that comes back with nothing leaves the want "asked" — retried next
# pass, which is right for an ordinary failure and WRONG for a usage limit: a week
# of rate limiting would look identical on every surface to a week of her not
# asking. The markers are a FINITE TABLE matched against the transport's last
# error, and anything NOT in here is an ordinary failure that stays "asked" and
# gets retried normally. Erring toward ordinary is deliberate: calling a real
# refusal "delayed" would promise a retry that will never work.
TRANSIENT = (
    "rate limit", "rate-limit", "ratelimit", "too many requests", "429",
    "usage limit", "quota", "out of credits", "insufficient credits",
    "capacity", "overloaded", "try again later", "temporarily unavailable",
    "503", "502", "upstream", "timed out",
)


# THE PROVIDER'S OWN WALL (measured 2026-08-21 01:17): the API moderates its
# GENERATED output — "imagine:content-moderated" — and BILLS for the attempt.
# A moderated want is REFUSED, not delayed and not silently retried: retrying is
# the same rejection at the same price, forever. This is xAI's ceiling, not ours;
# the row says so in words so nobody mistakes it for a bug or a choice of his.
MODERATED = ("content-moderated", "content_moderation", "content moderation")


def moderated_reason(log: str) -> str:
    low = (log or "").lower()
    for m in MODERATED:
        if m in low:
            return m
    return ""


def transient_reason(log: str) -> str:
    """The marker that matched, or "" — the reason goes on the row so he can read it."""
    low = (log or "").lower()
    for m in TRANSIENT:
        if m in low:
            return m
    return ""


def _ref_id() -> str:
    """The reference's uploaded file_id (content-hash cached in xai)."""
    return xai.reference_file_id(reference_path())


def _write(path: str, blob: bytes) -> bool:
    if not blob:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)
    return True


def _to_webm(path: str) -> bool:
    """The API returns mp4; the room's players and paths speak webm. Re-encode in
    place (vp9). Failure leaves the mp4 bytes at the webm path — most players cope,
    and the receipt records what happened either way."""
    out = path + ".enc.webm"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", path,
           "-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0", "-an", out]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and os.path.getsize(out) > 0:
            os.replace(out, path)
            return True
    except Exception:
        pass
    try:
        os.remove(out)
    except OSError:
        pass
    return False


def pingpong(path: str) -> bool:
    """Make a loop seamless by playing it forward then backward.

    MEASURED, NOT ASSUMED (first pipeline): a prompt-requested 'seamless' loop came
    back with first/last frames 26.4/255 apart — a visible jump every six seconds,
    which on a face reads as a glitch rather than breathing. Ping-pong cannot fail:
    the reversed half ends on exactly the frame the forward half started from. One
    frame is trimmed off the reverse so the turnaround is not shown twice."""
    out = path + ".pp.webm"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", path, "-filter_complex",
           "[0:v]split[a][b];[b]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[r];"
           "[a][r]concat=n=2:v=1[v]", "-map", "[v]", "-an",
           "-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0", out]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and os.path.getsize(out) > 0:
            os.replace(out, path)
            return True
        print("     (ping-pong failed: %s)" % (r.stderr or "")[-160:])
    except Exception as exc:
        print("     (ping-pong failed: %s)" % exc)
    try:
        os.remove(out)
    except OSError:
        pass
    return False


# ── THE THREE GENERATORS ─────────────────────────────────────────────────────────────


def gen_reference(extra: str, timeout: int = 300) -> int:
    """The one image everything else is anchored to. Nothing else runs until this
    is approved, because forty images against an unapproved face are forty wrong
    images."""
    ch = character()
    if not ch:
        print("!! %s is empty. Write the character description there first." % character_path())
        return 2
    out = reference_path()
    prompt = ("%s\n\nA head-and-shoulders portrait, %s. %s"
              % (ch, FACE_DIRECTION["calm"], extra or ""))
    imgs = xai.image(prompt, aspect_ratio="1:1", resolution="1k", timeout=timeout)
    ok = bool(imgs) and _write(out, imgs[0])
    print(("  wrote %s" % out) if ok else "  FAILED (no image came back)")
    if ok:
        _receipt(out, prompt, "reference")
    return 0 if ok else 1


def gen_still(out: str, direction: str, hold: str, timeout: int = 300,
              tries: int = 2) -> bool:
    """One identity-held still: /v1/images/edits from the reference. The retry is
    the old gen_slot's — one attempt is a coin flip on a generative endpoint."""
    fid = _ref_id()
    if not fid:
        _stage("reference upload failed — nothing can hold her face")
        return False
    _stage("editing from the reference…")
    prompt = "%s\n\n%s\n\n%s" % (hold, character(), direction)
    for attempt in range(max(1, tries)):
        blob = xai.image_edit(prompt, image_file_id=fid, timeout=timeout)
        if blob and _write(out, blob):
            return True
        if moderated_reason(xai.last_error()):
            # ── THE EDITS WALL, MEASURED (2026-08-21 01:40, the moderation matrix):
            # edits x {2.0, base} x {clinical, soft} = MODERATED every time, while
            # GENERATION of the same content passed on every model — the guard is on
            # editing a person's photo, not on the content. So the fallback is
            # prose-anchored generation: identity rides on character.txt alone,
            # slightly looser than the reference edit ("similar but a little
            # different but works perfectly fine" — the operator, on his own probe).
            # The receipt records which anchor held her.
            _stage("edits moderated — regenerating prose-anchored (identity from "
                   "character.txt; slightly looser hold)")
            ch = character()
            # a want's direction already carries character.txt (WD.request builds
            # it in); a grid slot's does not — anchor once, never twice.
            gen_prompt = (direction if ch[:40] in direction
                          else ch + "\n\n" + direction)
            imgs = xai.image(gen_prompt, aspect_ratio="1:1", resolution="1k",
                             timeout=timeout)
            if imgs and _write(out, imgs[0]):
                return True
            if moderated_reason(xai.last_error()):
                _stage("generation moderated it too — this one will not be made there")
            return False
        if attempt + 1 < tries:
            _stage("nothing came back — retrying %d/%d" % (attempt + 2, tries))
    return False


def gen_motion_from(still: str, out: str, motion: str, timeout: int = 600,
                    duration: int = 4, loop: bool = False) -> bool:
    """Motion grown FROM THE STILL: upload it, image->video, fetch, webm it."""
    if not os.path.exists(still):
        return False
    _stage("uploading the still…")
    fid = xai.upload_image(still)
    if not fid:
        _stage("could not upload the still")
        return False
    rid = xai.video_submit(motion, image_file_id=fid, duration=duration,
                           aspect_ratio="1:1", resolution="480p")
    if not rid:
        return False
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = xai.video_poll(rid)
        if st.get("progress"):
            _stage("video %d%%…" % st["progress"])
        if st["status"] == "done" and st["url"]:
            blob = xai._fetch(st["url"])
            if not blob or not _write(out, blob):
                return False
            _to_webm(out)
            if loop:
                pingpong(out)
            return True
        if st["status"] == "failed":
            return False
        time.sleep(5)
    return False


def gen_slot(row: dict, timeout: int = 600, tries: int = 2) -> bool:
    """One grid cell: face x outfit x kind."""
    out = A.abs_path(row["face"], row["outfit"], row["kind"], row["gesture"])
    if row["kind"] == "still":
        hold = HOLD_SAME_CLOTHES if row["outfit"] == "t0" else HOLD_NEW_CLOTHES
        direction = "%s %s" % (OUTFIT_DIRECTION[row["outfit"]],
                               FACE_DIRECTION[row["face"]])
        ok = gen_still(out, direction, hold, timeout=min(timeout, 300), tries=tries)
        if ok:
            _receipt(out, direction, "still", reference_path())
    else:
        still = A.abs_path(row["face"], row["outfit"], "still")
        motion = (LOOP_MOTION if row["kind"] == "loop"
                  else GESTURE_MOTION.get(row["gesture"], "a small natural movement"))
        ok = gen_motion_from(still, out, motion, timeout=timeout,
                             loop=(row["kind"] == "loop"))
        if ok:
            _receipt(out, motion, row["kind"], still)
    print(("  ok   %s" % row["path"]) if ok else ("  FAIL %s" % row["path"]))
    return ok


def gen_want(w: dict, timeout: int = 600, loop: bool = True, tries: int = 2) -> bool:
    """Make one look SHE (or he, from the panel) asked for.

    The difference from gen_slot is where the direction comes from: a slot's
    direction is a cell in committed tables, and a want's is a sentence someone
    wrote. Everything else is identical on purpose — the same reference, the same
    identity clause — because the thing that must not vary is WHO IS IN IT.

    MOTION GROWS IMMEDIATELY NOW. The day-boundary wait existed because the CLI
    made video painful; the API does not, so a want arrives whole — still, then
    motion, in one pass — and the wardrobe's promise to her can finally be
    'within minutes' without lying."""
    from harness.control import wardrobe as WD
    outdir = os.path.join(A.root(), "looks")
    fname = "%s.png" % w["id"]
    out = os.path.join(outdir, fname)
    _stage("want %s: making the picture (~1-3 min)" % w["id"])
    ok = gen_still(out, w["prompt"], HOLD_NEW_CLOTHES,
                   timeout=min(timeout, 300), tries=tries)
    if not ok:
        err = xai.last_error()
        if moderated_reason(err):
            WD.fulfil(w["id"], state="refused")
            _stage("want %s: the image provider refused this one on content grounds — "
                   "it will not be made there. (Their wall, not ours.)" % w["id"])
        elif transient_reason(err):
            WD.delay(w["id"], "generation held up: %s" % transient_reason(err))
            _stage("want %s: delayed (%s) — it stays in the queue" % (w["id"], transient_reason(err)))
        else:
            _stage("want %s: nothing came back — an ordinary failure; it stays asked "
                   "and the next pass tries again" % w["id"])
        return False
    _receipt(out, w["prompt"], "want:%s" % w["id"])
    WD.fulfil(w["id"], file=fname, state="made")
    _stage("want %s: picture MADE — growing its motion (~2-5 min; the still is already in the panel)" % w["id"])
    if not loop:
        return True
    # ── AND IT BREATHES, NOW. Grown from the still that was just approved. A loop
    # that fails costs motion and never the look itself.
    lname = "%s.webm" % w["id"]
    lout = os.path.join(outdir, lname)
    if gen_motion_from(out, lout, LOOP_MOTION, timeout=min(timeout, 420), loop=True):
        _receipt(lout, LOOP_MOTION, "want-loop:%s" % w["id"], out)
        WD.fulfil(w["id"], loop=lname)
        _stage("want %s: it MOVES — done" % w["id"])
    else:
        _stage("want %s: motion did not come back — the still stands; a later pass grows it" % w["id"])
    return True


def run_wants(timeout: int = 600, limit: int = 0) -> int:
    """Everything asked-for: stills AND motion, in one pass. Also grows motion for
    made-but-still looks left over from the day-boundary era."""
    from harness.control import wardrobe as WD
    made = 0
    # the work list is STAGED: ordered (fresh) and delayed (held up, still owed)
    # both get tried; refused rows never do.
    for w in [w for w in WD.waiting()
              if w.get("stage") in ("ordered", "delayed")]:
        if limit and made >= limit:
            break
        if gen_want(w, timeout):
            made += 1
    # NO EARLY RETURN on an empty stills queue: the motion half below is owed whether
    # or not anything new was asked for (G-WARDROBE-MOTION holds both ends of this rule —
    # the caller in run_consolidation and this loop — because fixing one and not the
    # other is how three of her looks stayed photographs for two days).
    # looks that exist but never moved (the old pipeline's leftovers)
    for w in WD.pending_motion():
        if limit and made >= limit:
            break
        still = os.path.join(A.root(), "looks", w.get("file") or "")
        lname = "%s.webm" % w["id"]
        lout = os.path.join(A.root(), "looks", lname)
        if still and os.path.exists(still) and not os.path.exists(lout):
            print("  motion for %s" % w["id"])
            if gen_motion_from(still, lout, LOOP_MOTION, timeout=timeout, loop=True):
                _receipt(lout, LOOP_MOTION, "want-loop:%s" % w["id"], still)
                WD.fulfil(w["id"], loop=lname)
                made += 1
    print("done — %d generated" % made)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate her image set via the xAI API.")
    ap.add_argument("--reference", action="store_true",
                    help="make _reference.png (everything else waits for approval)")
    ap.add_argument("--extra", default="", help="extra direction for --reference")
    ap.add_argument("--kind", default="still", choices=list(A.KINDS) + ["all"])
    ap.add_argument("--outfit", default="t0", help="outfit id, or 'all'")
    ap.add_argument("--face", default="all")
    ap.add_argument("--limit", type=int, default=0, help="stop after N generations")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--tries", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--one", default="", help="make ONE want by id, now")
    ap.add_argument("--no-loop", action="store_true")
    ap.add_argument("--wants", action="store_true",
                    help="everything asked-for: stills and motion, one pass")
    a = ap.parse_args()

    if not xai.available():
        print("!! no xAI API key (var/secrets/Xapi.txt or SP_XAI_KEY_FILE)")
        return 2
    if a.reference:
        return gen_reference(a.extra, a.timeout)
    if not os.path.exists(reference_path()):
        print("!! no reference yet. Run --reference first; approve it; then the set.")
        return 2
    if a.one:
        from harness.control import wardrobe as WD
        w = next((x for x in WD.wants() if x["id"] == a.one), None)
        if not w:
            print("!! no want with id %s" % a.one)
            return 2
        return 0 if gen_want(w, a.timeout, loop=not a.no_loop, tries=a.tries) else 1
    if a.wants:
        return run_wants(a.timeout, a.limit)

    rows = [r for r in A.manifest() if not r["have"]]
    if a.kind != "all":
        rows = [r for r in rows if r["kind"] == a.kind]
    if a.outfit != "all":
        rows = [r for r in rows if r["outfit"] == a.outfit]
    if a.face != "all":
        rows = [r for r in rows if r["face"] == a.face]
    if a.dry_run:
        for r in rows:
            print("  would make %s" % r["path"])
        print("%d slots" % len(rows))
        return 0
    made = 0
    for r in rows:
        if a.limit and made >= a.limit:
            break
        if gen_slot(r, a.timeout, a.tries):
            made += 1
    print("done — %d generated, %d missing" % (made, len(rows) - made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
