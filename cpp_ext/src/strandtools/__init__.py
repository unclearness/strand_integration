"""Python bindings for the :mod:`strandtools` C++ extension."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Iterable, Union


def _load_cv2() -> object:
    """Import :mod:`cv2` and provide a helpful error if it is unavailable."""

    try:
        return importlib.import_module("cv2")
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive programming
        raise ImportError(
            "strandtools requires OpenCV. Install the `opencv-python` package "
            "before importing strandtools."
        ) from exc


PathStr = Union[str, os.PathLike[str]]


def _normalise_directories(paths: Iterable[PathStr]) -> list[Path]:
    """Return a de-duplicated list of existing directories."""

    unique: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        if not path:
            continue

        try:
            candidate = Path(path).resolve()
        except (OSError, RuntimeError):
            continue

        if not candidate.is_dir() or candidate in seen:
            continue

        unique.append(candidate)
        seen.add(candidate)

    return unique


def _gather_windows_candidate_dirs(cv2_module: object) -> list[Path]:
    """Collect directories that are likely to contain OpenCV runtime DLLs."""

    package_dir = Path(__file__).resolve().parent
    candidates: list[PathStr] = [package_dir]

    cv2_location = getattr(cv2_module, "__file__", None)
    if cv2_location:
        cv2_dir = Path(cv2_location).resolve().parent
        candidates.extend(
            [
                cv2_dir,
                cv2_dir / "opencv_python.libs",
                cv2_dir / "opencv" / "bin",
                cv2_dir / "bin",
            ]
        )

    opencv_dir = os.environ.get("OpenCV_DIR")
    if opencv_dir:
        base = Path(opencv_dir)
        candidates.extend(
            [
                base,
                base / "bin",
                base / "x64" / "vc16" / "bin",
                base / "x64" / "vc17" / "bin",
            ]
        )

    extra_dirs = os.environ.get("STRANDTOOLS_EXTRA_DLL_DIRS")
    if extra_dirs:
        candidates.extend(Path(entry) for entry in extra_dirs.split(os.pathsep) if entry)

    return _normalise_directories(candidates)


def _register_windows_dll_search_path(directories: list[Path]) -> None:
    """Add *directories* to Windows' DLL search path."""

    add_dll_directory = getattr(os, "add_dll_directory", None)

    if add_dll_directory is None:
        path_env = os.environ.get("PATH", "")
        for directory in directories:
            path_env = f"{directory}{os.pathsep}{path_env}" if path_env else str(directory)
        os.environ["PATH"] = path_env
        return

    for directory in directories:
        try:
            add_dll_directory(str(directory))
        except OSError:
            continue


def _load_dependency_dlls(directories: list[Path]) -> list[str]:
    """Load known OpenCV-related DLLs eagerly so Windows keeps them resident."""

    try:
        import ctypes
    except ImportError:  # pragma: no cover - ctypes is always available on CPython
        return []

    loaded: list[str] = []
    patterns = (
        "opencv_*.dll",
        "libopencv_*.dll",
        "tbb*.dll",
        "libiomp*.dll",
        "omp*.dll",
        "vcomp*.dll",
    )

    for directory in directories:
        for pattern in patterns:
            for candidate in directory.glob(pattern):
                try:
                    ctypes.WinDLL(str(candidate))
                except OSError:
                    continue
                else:
                    loaded.append(candidate.name)

    return loaded


_cv2 = _load_cv2()

_windows_dll_dirs: list[Path] = []
if os.name == "nt":  # pragma: no branch - Windows specific workaround
    _windows_dll_dirs = _gather_windows_candidate_dirs(_cv2)
    _register_windows_dll_search_path(_windows_dll_dirs)

try:
    from ._strandtools_impl import *  # noqa: F401,F403
except ImportError as exc:
    if os.name == "nt" and getattr(exc, "name", None) == "_strandtools_impl":
        loaded = _load_dependency_dlls(_windows_dll_dirs or _gather_windows_candidate_dirs(_cv2))

        try:
            from ._strandtools_impl import *  # noqa: F401,F403
        except ImportError as inner_exc:  # pragma: no cover - Windows specific failure
            searched = ", ".join(str(path) for path in _windows_dll_dirs) or "<none>"
            message = (
                "strandtools failed to load its native extension on Windows because "
                "the OpenCV runtime libraries could not be located. "
                "Specify the directories that contain the OpenCV DLLs via the "
                "STRANDTOOLS_EXTRA_DLL_DIRS environment variable or add them to PATH. "
                f"Searched directories: {searched}."
            )
            if loaded:
                message += f" Loaded DLLs: {', '.join(loaded)}."
            raise ImportError(message) from inner_exc
    else:
        raise
finally:
    del _cv2
    if "_windows_dll_dirs" in globals():
        del _windows_dll_dirs

