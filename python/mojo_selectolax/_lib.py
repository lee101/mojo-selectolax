"""ctypes bindings for the Mojo parser and selector library."""

from __future__ import annotations

import ctypes
import os
import subprocess

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.environ.get("MOJO_SELECTOLAX_LIB") or os.path.join(
    ROOT, "dist", "libmojo-selectolax.so"
)
I = ctypes.c_int64


class BuildError(RuntimeError):
    pass


def build(force: bool = False) -> str:
    if os.environ.get("MOJO_SELECTOLAX_LIB"):
        if os.path.exists(LIB):
            return LIB
        raise BuildError(f"MOJO_SELECTOLAX_LIB does not exist: {LIB}")
    source = os.path.join(ROOT, "src", "selectolax.mojo")
    if not force and os.path.exists(LIB) and os.path.getmtime(LIB) >= os.path.getmtime(source):
        return LIB
    proc = subprocess.run(
        ["bash", os.path.join(ROOT, "build", "build.sh")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if proc.returncode or not os.path.exists(LIB):
        raise BuildError((proc.stderr or proc.stdout).strip()[:4000])
    return LIB


_handle: ctypes.CDLL | None = None


def lib() -> ctypes.CDLL:
    global _handle
    if _handle is None:
        _handle = ctypes.CDLL(build())
        _handle.msx_parse.argtypes = [I] * 7
        _handle.msx_parse.restype = I
        _handle.msx_select.argtypes = [I] * 12
        _handle.msx_select.restype = I
        _handle.msx_select_first.argtypes = [I] * 10
        _handle.msx_select_first.restype = I
        _handle.msx_subtree_count.argtypes = [I] * 3
        _handle.msx_subtree_count.restype = I
    return _handle


def addr(array: np.ndarray) -> int:
    if not isinstance(array, np.ndarray):
        raise TypeError("FFI buffers must be NumPy arrays")
    if not array.flags.c_contiguous:
        raise ValueError("FFI buffers must be C-contiguous")
    address = int(array.ctypes.data)
    if address == 0:
        raise ValueError("FFI buffers must have non-null storage")
    return address
