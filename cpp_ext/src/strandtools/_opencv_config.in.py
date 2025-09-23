"""Build-time OpenCV metadata for strandtools (auto-generated)."""

from __future__ import annotations

OPENCV_VERSION: str | None = "@STRANDTOOLS_OPENCV_VERSION@"
if OPENCV_VERSION == "":
    OPENCV_VERSION = None

OPENCV_RUNTIME_DIRS: list[str] = [
@STRANDTOOLS_OPENCV_RUNTIME_DIRS_PY@
]
