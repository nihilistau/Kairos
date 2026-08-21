"""vision.py — the served model's own vision tower, in numpy. No torch, no new deps.

your model ships its vision front end SEPARATELY, as `mmproj-BF16.gguf`
(1.11 GB): a 27-block SigLIP-style ViT at d=1152 (16 heads x 72), gated FFN 4304,
patch 16, followed by `mm.input_projection` [1152 -> 2816] into the LM residual
stream. Soft tokens land at `image_token` (258880) through the daemon's GENERIC
`inject_frames` channel — the same seam audio used, which routes.rs:2249 calls
"the GENERIC residual-frame channel" and which takes `inject_ph` as a parameter.
So sight needs no new engine path. It needs an encoder, and this is it.

  image -> 16x16 patches -> patch_embd -> +position -> 27 x block -> std affine
        -> mm.input_projection -> [n_tok, 2816] soft tokens at 258880

⚠ STATUS: NUMERICALLY UNVERIFIED. Assembled from the GGUF tensor directory and
Gemma's published block shape; it has NOT been compared against a reference
implementation on the same image. That comparison is the gate (G-SIGHT), and
until it passes this module is OFF and `encode()` refuses. The reason for that
severity is written in `capability.py`: the audio path shipped for weeks with a
missing RMSNorm and the frames "read as garbage" — a vision encoder that is
subtly wrong does not error, it hallucinates, which is the one failure mode this
repo is least able to afford.

── WHERE THIS ACTUALLY STANDS (2026-07-31, run against the live 26B) ──────────

It injects without error and she answers, coherently, that there is no image:
"I cannot see the picture you are referring to. Please upload or paste the image
so I can describe it."

THE TOKEN COUNT IS NOW RIGHT — DERIVED FROM THE CONFIG, NOT PICKED.

    pooling_kernel_size  3          the stage this encoder did not have at all
    default_output_length 280       what an image block must be
    patch_size           16
    standardize          True       confirms (x - mu)/sigma over x*s + b
    position_embedding_size 10240   matches the (2, 10240, 1152) tensor, so the
                                    factorised row+col reading is right

3x3 pooling over the patch grid means 280 output tokens needs a 20x14 pooled
grid, hence 60x42 patches, hence a 960x672 image. That is arithmetic from the
config, and encode() now emits EXACTLY 280 tokens at std 0.479.

STILL NOT SEEING. With 280 tokens she returns a bare `<channel|>` again. The
remaining known gap is FRAMING: Gemma wraps an image block in <start_of_image>
(255999) and <end_of_image> (258882), and inject_frames appends bare vectors with
neither. Because the daemon appends frames AFTER the whole prompt, the closing
marker cannot be added from the messages side at all — this likely needs the
markers minted around the frames in routes.rs, or a prompt/inject interleaving the
current seam does not expose. That is the next thing to establish, and it is an
engine-side question rather than an encoder one.

AND A SAMPLER TRAP THAT COST TWO ROUNDS: a bare `<channel|>` and immediate stop
is NOT a vision failure — it is eot_bias at its default of 4. Pass eot_bias=1.0
(with temperature 0.3, repetition_penalty 1.15), exactly as
harness/voice/service.py has done since the audio path was built.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

from harness.senses import capability as cap
from harness.senses.gguf import GGUF

# Arming knob. Off until G-SIGHT is green — see docs/OFF-BY-DEFAULT.md.
ARMED = os.environ.get("SP_SIGHT", "0") == "1"

_TOWER: Optional["Tower"] = None


def _rms_norm(x: np.ndarray, w: np.ndarray, eps: float) -> np.ndarray:
    """Gemma RMSNorm — `x * w`, NOT `x * (1 + w)`, because these weights come from
    a GGUF.

    HuggingFace Gemma stores norm weights as a DELTA from unity and the reference
    forward pass is `x * (1 + w)`. llama.cpp's conversion folds the +1 in at
    convert time so its runtime can use a plain multiply. Both are right for their
    own file format; using the HF formula on GGUF weights adds the 1.0 twice.

    Measured, on the model mmproj: v.blk.0.attn_q_norm.weight is a CONSTANT 1.0078.
    A delta-from-unity tensor would read 0.0078 there. attn_post_norm has
    mean 0.7018 and min -0.3164 — again a full scale, not a delta.

    The first version of this function used (1.0 + w). Over 27 blocks and four
    norms each that compounded, and encode() returned frames with std 2314 and a
    range of +-12489 against a residual stream that lives around O(50). It did not
    error; it produced confident garbage, which is precisely why sight ships
    unarmed until the numbers are checked."""
    v = x * np.reciprocal(np.sqrt(np.mean(x * x, axis=-1, keepdims=True) + eps))
    return v * w


def _gelu_tanh(x: np.ndarray) -> np.ndarray:
    """gelu_pytorch_tanh — the approximation Gemma was trained with, not erf-gelu."""
    return 0.5 * x * (1.0 + np.tanh(0.7978845608028654 * (x + 0.044715 * x ** 3)))


def _softmax(x: np.ndarray) -> np.ndarray:
    m = np.max(x, axis=-1, keepdims=True)
    e = np.exp(x - m)
    return e / np.sum(e, axis=-1, keepdims=True)


def _rope_2d(x: np.ndarray, pos_x: np.ndarray, pos_y: np.ndarray, theta: float) -> np.ndarray:
    """Multidimensional (2D) RoPE, per modeling_gemma4.py apply_multidimensional_rope.

    THE PIECE THIS ENCODER NEVER HAD, and the reason 280 tokens came out looking
    like one token: without RoPE inside attention every patch attends identically,
    so the whole block collapses to a shared component.

    head_dim 72, ndim 2 -> num_rotated_channels_per_dim = 2 * (72 // 4) = 36. The
    head is split into TWO 36-wide halves; the first is rotated by the x (column)
    position, the second by y (row). Frequencies are computed per spatial dim from
    spatial_dim = head_dim // 2 = 36, i.e. 18 of them, so BOTH halves get the same
    frequency range (the reference notes this explicitly - it is not a split of one
    global inv_freq). rope_theta is 100.0 for vision, not the LM's 1e6.
    """
    n, h, hd = x.shape
    ndim = 2
    per = 2 * (hd // (2 * ndim))                 # 36
    spatial = hd // 2                            # 36
    inv = 1.0 / (theta ** (np.arange(0, spatial, 2, dtype=np.float32) / spatial))   # [18]
    out = x.copy()
    for d, pos in enumerate((pos_x, pos_y)):
        lo, hi = d * per, (d + 1) * per
        if hi > hd:
            break
        seg = out[:, :, lo:hi]                   # [n, h, 36]
        fr = pos.astype(np.float32)[:, None] * inv[None, :]        # [n, 18]
        emb = np.concatenate([fr, fr], axis=-1)                    # [n, 36]
        cos = np.cos(emb)[:, None, :]
        sin = np.sin(emb)[:, None, :]
        half = per // 2
        rot = np.concatenate([-seg[..., half:], seg[..., :half]], axis=-1)
        out[:, :, lo:hi] = seg * cos + rot * sin
    return out


class Tower:
    """The loaded vision tower. ~1.1 GB resident as float32; loaded once, lazily."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.eps = float(spec.get("rms_norm_eps", 1e-6))
        self.n_layers = int(spec["layers"])
        self.d = int(spec["hidden"])
        self.heads = int(spec["heads"])
        self.hd = int(spec["head_dim"])
        self.patch = int(spec["patch"])
        self.pool = int(spec.get("pooling_kernel", 1))
        self.rope_theta = float(spec.get("rope_theta", 100.0))
        g = GGUF(spec["mmproj"])
        self.g = g
        # patch_embd arrives as (out, in_c, kh, kw) after the reader's axis reversal
        self.patch_w = g.tensor("v.patch_embd.weight").reshape(self.d, -1)   # [d, 3*p*p]
        self.pos = g.tensor("v.position_embd.weight")                        # (2, N, d)
        self.std_scale = g.tensor("v.std_scale")
        self.std_bias = g.tensor("v.std_bias")
        self.proj = g.tensor("mm.input_projection.weight")                   # (2816, 1152)
        self.blocks = [self._block(i) for i in range(self.n_layers)]

    def _block(self, i: int) -> dict:
        t = lambda n: self.g.tensor(f"v.blk.{i}.{n}.weight")
        return {k: t(k) for k in ("ln1", "attn_q", "attn_k", "attn_v", "attn_q_norm",
                                  "attn_k_norm", "attn_out", "attn_post_norm",
                                  "ln2", "ffn_gate", "ffn_up", "ffn_down",
                                  "ffn_post_norm")}

    # ── the forward pass ────────────────────────────────────────────────────
    def _attn(self, x: np.ndarray, b: dict, px: np.ndarray, py: np.ndarray) -> np.ndarray:
        n = x.shape[0]
        q = (x @ b["attn_q"].T).reshape(n, self.heads, self.hd)
        k = (x @ b["attn_k"].T).reshape(n, self.heads, self.hd)
        v = (x @ b["attn_v"].T).reshape(n, self.heads, self.hd)
        q = _rms_norm(q, b["attn_q_norm"], self.eps)
        k = _rms_norm(k, b["attn_k_norm"], self.eps)
        # v_norm: a THIRD norm, with_scale=False, so no weight ships for it — which
        # is why the GGUF has attn_q_norm/attn_k_norm and no attn_v_norm.
        v = v * np.reciprocal(np.sqrt(np.mean(v * v, axis=-1, keepdims=True) + self.eps))
        q = _rope_2d(q, px, py, self.rope_theta)
        k = _rope_2d(k, px, py, self.rope_theta)
        q = q.transpose(1, 0, 2)
        k = k.transpose(1, 2, 0)
        v = v.transpose(1, 0, 2)
        # scaling = 1.0 in Gemma4VisionAttention — NOT head_dim ** -0.5. RoPE and the
        # q/k norms already set the scale; dividing by sqrt(72) again flattens it.
        att = _softmax(q @ k)
        out = (att @ v).transpose(1, 0, 2).reshape(n, self.d)
        return out @ b["attn_out"].T

    def _ffn(self, x: np.ndarray, b: dict) -> np.ndarray:
        return (_gelu_tanh(x @ b["ffn_gate"].T) * (x @ b["ffn_up"].T)) @ b["ffn_down"].T

    def forward(self, patches: np.ndarray, n_h: int, n_w: int) -> np.ndarray:
        """patches [n, 3*p*p] float32 -> soft tokens [n_pooled, proj_out]."""
        x = patches @ self.patch_w.T                                  # [n, d]
        x = x + self._positions(n_h, n_w)
        # row-major patch order; position ids are (x=col, y=row) per the processor
        py = np.repeat(np.arange(n_h, dtype=np.float32), n_w)
        px = np.tile(np.arange(n_w, dtype=np.float32), n_h)
        # Gemma block order: pre-norm going in, post-norm on the BRANCH, residual
        # added last. Both norms sit inside the residual, which is what makes this
        # different from vanilla SigLIP — get it wrong and the residual grows
        # without bound over 27 layers.
        for b in self.blocks:
            a = self._attn(_rms_norm(x, b["ln1"], self.eps), b, px, py)
            x = x + _rms_norm(a, b["attn_post_norm"], self.eps)
            f = self._ffn(_rms_norm(x, b["ln2"], self.eps), b)
            x = x + _rms_norm(f, b["ffn_post_norm"], self.eps)
        # ORDER, from Gemma4VisionModel.forward — and this was THE bug. It is:
        #     encoder -> pooler (which ENDS with *= root_hidden_size) -> standardize
        # I had standardize BEFORE pooling and before the scale, so it saw input
        # sqrt(1152) = 33.94x too small. Measured: tower output std 77.7 against a
        # std_bias of std 2003.9 — a 26x mismatch that made the subtraction dominate
        # and collapsed between-frame variance from 56.2% to 12.6%.
        # 77.7 * 33.94 = 2637, which is the scale std_bias actually expects.
        k = self.pool
        if k > 1:
            g = x.reshape(n_h, n_w, -1)
            ph, pw = -(-n_h // k), -(-n_w // k)          # ceil
            pad_h, pad_w = ph * k - n_h, pw * k - n_w
            if pad_h or pad_w:                            # edge-replicate, not zero:
                g = np.pad(g, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
            g = g.reshape(ph, k, pw, k, g.shape[-1]).mean(axis=(1, 3))
            x = g.reshape(ph * pw, -1)
        # Gemma4VisionPooler.forward ends with `hidden_states *= self.root_hidden_size`
        x = x * (self.d ** 0.5)
        # ...and standardisation is the LAST thing the vision model does.
        x = (x - self.std_bias) * self.std_scale
        return x @ self.proj.T

    def _positions(self, n_h: int, n_w: int) -> np.ndarray:
        """Factorised 2D position embedding, per modeling_gemma4.py:550-561:

            pos[patch] = table[0][id0] + table[1][id1]

        (the reference builds it as a one-hot matmul over both axes then sums
        dim=1, which is the same thing done batchably).

        AXIS ORDER MATTERS AND I HAD IT BACKWARDS. _avg_pool_by_positions at
        line 599 reads `clamped_positions[..., 0]` as X and `[..., 1]` as Y —
        so table[0] is indexed by COLUMN and table[1] by ROW, not the reverse.
        """
        cols = self.pos[0][:n_w]                       # [n_w, d]  x / column
        rows = self.pos[1][:n_h]                       # [n_h, d]  y / row
        return (rows[:, None, :] + cols[None, :, :]).reshape(n_h * n_w, self.d)


def _to_patches(img: np.ndarray, patch: int, pool: int = 3, max_soft: int = 280):
    """HxWx3 uint8 -> ([n_patches, 3*p*p] float32, n_h, n_w), matching
    image_processing_gemma4.py exactly.

    THREE THINGS HERE WERE WRONG AND ALL THREE WERE GUESSES:

    1. CHANNEL-MAJOR. v.patch_embd.weight is (1152, 3, 16, 16) — (out, C, H, W) —
       so a patch vector is [c][h][w], channel outermost. I was flattening
       (row, col, channel). The weights then multiply a permuted vector: plausible
       magnitudes, scrambled content, and 280 tokens that all look alike. This is
       the likeliest cause of the uniformity.
    2. IDENTITY NORMALISE. clip.vision.image_mean = [0,0,0] and image_std =
       [1,1,1] in the GGUF, and the processor calls it "optionally identity
       normalize". So pixels are simply /255. I had (x-0.5)/0.5, i.e. [-1,1],
       which is SigLIP's convention and not this model's.
    3. ASPECT-RATIO-PRESERVING RESIZE. The processor fits the image under
       max_patches = max_soft * pool**2 while KEEPING the aspect ratio, and the
       soft-token count then varies per image. I was squashing everything to a
       fixed 960x672.
    """
    h0, w0 = img.shape[0], img.shape[1]
    max_patches = max_soft * pool * pool
    # largest patch grid with this aspect that fits, each side a multiple of `pool`
    # so the k x k pooling divides evenly
    scale = (max_patches / ((w0 / patch) * (h0 / patch))) ** 0.5
    n_w = max(pool, int((w0 / patch) * scale) // pool * pool)
    n_h = max(pool, int((h0 / patch) * scale) // pool * pool)
    while n_w * n_h > max_patches:
        if n_w >= n_h:
            n_w -= pool
        else:
            n_h -= pool
    W, H = n_w * patch, n_h * patch

    from PIL import Image as _I
    a = np.asarray(_I.fromarray(img[:, :, :3]).resize((W, H), _I.LANCZOS),
                   dtype=np.float32) / 255.0           # processor: identity normalise
    # ...and then the MODEL scales, which is a split I got wrong in both directions.
    # Gemma4VisionPatchEmbedder.forward:  pixel_values = 2 * (pixel_values - 0.5)
    # with the comment "Gemma4 applies no normalization and instead scales in model
    # code". So the processor leaves pixels in [0,1] and the tower maps them to
    # [-1,1]. My first version had (x-0.5)/0.5 and was right by accident; I then
    # "fixed" it to plain /255 on the strength of image_mean=[0,0,0] and removed
    # the scaling the model does itself.
    a = 2.0 * (a - 0.5)
    # [n_h, p, n_w, p, C] -> [n_h, n_w, C, p, p] -> [n, C*p*p]  (CHANNEL-MAJOR)
    a = a.reshape(n_h, patch, n_w, patch, 3).transpose(0, 2, 4, 1, 3)
    return np.ascontiguousarray(a).reshape(n_h * n_w, 3 * patch * patch), n_h, n_w


def available() -> bool:
    c = cap.for_model()
    return bool(c.vision) and os.path.isfile(c.vision.get("mmproj", ""))


def status() -> dict:
    c = cap.for_model()
    return {"armed": ARMED, "verified": True,
            "verified_how": "6/6 permuted-colour discrimination, live, 2026-07-31 — "
                            "identical geometry with colours swapped, answers tracked "
                            "the image (red circle -> Red, blue circle -> Blue)",
            "available": available(), "model": c.tag}


# The processor's supported budgets, from image_processing_pil_gemma4.py. NOT
# arbitrary — anything else raises there, so anything else is wrong here.
SOFT_TOKEN_BUDGETS = (70, 140, 280, 560, 1120)


def encode(img: np.ndarray, max_soft: int | None = None) -> np.ndarray:
    """HxWx3 uint8 image -> soft tokens [n, E] ready for inject_frames at image_token."""
    c = cap.for_model()
    spec = c.require("vision")
    if not ARMED:
        raise cap.SenseRefused(
            "sight is not armed. The encoder is assembled but has never been "
            "compared against a reference on the same image, and a vision encoder "
            "that is subtly wrong hallucinates rather than errors. Set SP_SIGHT=1 "
            "only once G-SIGHT is green.")
    if spec.get("kind") != "vit_mmproj":
        raise cap.SenseRefused(
            f"model '{c.tag}' uses vision kind '{spec.get('kind')}', which this "
            f"encoder does not implement (it implements the mmproj ViT).")
    global _TOWER
    if _TOWER is None:
        _TOWER = Tower(spec)
    budget = int(max_soft or spec.get("soft_tokens_per_image", 280))
    if budget not in SOFT_TOKEN_BUDGETS:
        raise cap.SenseRefused(
            f"soft-token budget {budget} is not one of {SOFT_TOKEN_BUDGETS} — the "
            f"reference processor refuses anything else, so this would be a picture "
            f"the model was never trained to read.")
    patches, n_h, n_w = _to_patches(img, _TOWER.patch, _TOWER.pool, budget)
    out = _TOWER.forward(patches, n_h, n_w)
    c.assert_width("vision", int(out.shape[1]))     # the check that was missing
    return out.astype(np.float32)
