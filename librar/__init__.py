"""Runtime package shim to expose src-layout modules for `python -m`."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC_PACKAGE = _ROOT / "src" / "librar"

if _SRC_PACKAGE.is_dir():
    __path__.append(str(_SRC_PACKAGE))
