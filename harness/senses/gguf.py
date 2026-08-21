"""gguf.py — a minimal, read-only GGUF reader. numpy only, no new dependencies.

Enough to pull the vision tower out of `mmproj-*.gguf` and nothing more: header,
KV metadata, tensor directory, and lazy per-tensor reads for the unquantised
types (F32/F16/BF16). Quantised blocks are NOT decoded — mmproj ships BF16/F16,
and a half-implemented dequantiser that silently returns wrong numbers is exactly
the failure mode `capability.py` exists to prevent. Unsupported type => raise.

GGUF tensor shapes are stored fastest-axis-first (ne[0] is the innermost). numpy
wants the opposite, so `tensor()` reverses them — a [1152, 4304] ffn_up in the
file is a (4304, 1152) array here, which is the shape you multiply by.
"""
from __future__ import annotations

import struct
from typing import Any

import numpy as np

# GGUF metadata value types
(_U8, _I8, _U16, _I16, _U32, _I32, _F32, _BOOL, _STR, _ARR, _U64, _I64, _F64) = range(13)
_FIX = {_U8: ("<B", 1), _I8: ("<b", 1), _U16: ("<H", 2), _I16: ("<h", 2),
        _U32: ("<I", 4), _I32: ("<i", 4), _F32: ("<f", 4), _BOOL: ("<?", 1),
        _U64: ("<Q", 8), _I64: ("<q", 8), _F64: ("<d", 8)}

# ggml tensor types we will decode. Anything else raises rather than guesses.
GGML_F32, GGML_F16, GGML_BF16 = 0, 1, 30
_ITEMSIZE = {GGML_F32: 4, GGML_F16: 2, GGML_BF16: 2}


class GGUFError(RuntimeError):
    pass


class GGUF:
    """Lazily-read GGUF file. Holds the directory; reads tensor bytes on demand."""

    def __init__(self, path: str):
        self.path = path
        self.kv: dict[str, Any] = {}
        self.tensors: dict[str, tuple[list[int], int, int]] = {}   # name -> (ne, type, offset)
        self._data_start = 0
        self._read_header()

    # ── header ──────────────────────────────────────────────────────────────
    def _read_header(self) -> None:
        with open(self.path, "rb") as f:
            if f.read(4) != b"GGUF":
                raise GGUFError(f"{self.path}: not a GGUF file")
            _ver, ntensor, nkv = (self._u32(f), self._u64(f), self._u64(f))
            for _ in range(nkv):
                k = self._str(f)
                self.kv[k] = self._val(f, self._u32(f))
            for _ in range(ntensor):
                name = self._str(f)
                nd = self._u32(f)
                ne = [self._u64(f) for _ in range(nd)]
                ttype = self._u32(f)
                off = self._u64(f)
                self.tensors[name] = (ne, ttype, off)
            # tensor data begins at the next `alignment` boundary after the directory
            align = int(self.kv.get("general.alignment", 32))
            pos = f.tell()
            self._data_start = pos + (-pos % align)

    @staticmethod
    def _u32(f) -> int: return struct.unpack("<I", f.read(4))[0]

    @staticmethod
    def _u64(f) -> int: return struct.unpack("<Q", f.read(8))[0]

    @classmethod
    def _str(cls, f) -> str:
        return f.read(cls._u64(f)).decode("utf-8", "replace")

    @classmethod
    def _val(cls, f, t: int):
        if t in _FIX:
            fmt, n = _FIX[t]
            return struct.unpack(fmt, f.read(n))[0]
        if t == _STR:
            return cls._str(f)
        if t == _ARR:
            et, n = cls._u32(f), cls._u64(f)
            if et == _STR:
                return [cls._str(f) for _ in range(n)]
            if et == _ARR:
                raise GGUFError("nested arrays in GGUF metadata are not supported")
            fmt, w = _FIX[et]
            raw = f.read(n * w)
            return list(struct.unpack(f"<{n}{fmt[1]}", raw))
        raise GGUFError(f"unknown GGUF metadata type {t}")

    # ── tensors ─────────────────────────────────────────────────────────────
    def has(self, name: str) -> bool:
        return name in self.tensors

    def tensor(self, name: str) -> np.ndarray:
        """Read one tensor as float32, in numpy (slowest-axis-first) order."""
        try:
            ne, ttype, off = self.tensors[name]
        except KeyError:
            raise GGUFError(f"{self.path}: no tensor '{name}'") from None
        if ttype not in _ITEMSIZE:
            raise GGUFError(
                f"{self.path}: tensor '{name}' has ggml type {ttype}, which this "
                f"reader does not decode. Use an F16/BF16/F32 mmproj — a guessed "
                f"dequantisation returns plausible wrong numbers, which is worse "
                f"than failing here.")
        count = 1
        for d in ne:
            count *= int(d)
        nbytes = count * _ITEMSIZE[ttype]
        with open(self.path, "rb") as f:
            f.seek(self._data_start + off)
            raw = f.read(nbytes)
        if len(raw) != nbytes:
            raise GGUFError(f"{self.path}: short read for '{name}' "
                            f"({len(raw)} of {nbytes} bytes)")
        if ttype == GGML_F32:
            arr = np.frombuffer(raw, dtype="<f4")
        elif ttype == GGML_F16:
            arr = np.frombuffer(raw, dtype="<f2").astype(np.float32)
        else:                                        # BF16: top 16 bits of an f32
            u16 = np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 16
            arr = u16.view(np.float32)
        # GGUF stores ne fastest-axis-first; numpy wants the reverse.
        return arr.reshape(tuple(int(d) for d in reversed(ne))).copy()

    def __repr__(self) -> str:
        return f"<GGUF {self.path} tensors={len(self.tensors)} kv={len(self.kv)}>"
