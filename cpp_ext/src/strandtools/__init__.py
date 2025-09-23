"""Python bindings for the :mod:`strandtools` C++ extension."""

from __future__ import annotations

import importlib
import os
import re
import warnings
from pathlib import Path
from typing import Iterable, Union

try:  # pragma: no cover - build metadata is generated at install time
    from . import _opencv_config as _opencv_build_config
except ImportError:  # pragma: no cover - source tree without a build
    _opencv_build_config = None


_BUILD_OPENCV_VERSION: str | None
_BUILD_OPENCV_RUNTIME_DIRS: list[str]

if _opencv_build_config is None:  # pragma: no branch - import fallback
    _BUILD_OPENCV_VERSION = None
    _BUILD_OPENCV_RUNTIME_DIRS = []
else:
    _BUILD_OPENCV_VERSION = getattr(_opencv_build_config, "OPENCV_VERSION", None)
    if not _BUILD_OPENCV_VERSION:
        _BUILD_OPENCV_VERSION = None
    runtime_dirs = getattr(_opencv_build_config, "OPENCV_RUNTIME_DIRS", [])
    _BUILD_OPENCV_RUNTIME_DIRS = list(runtime_dirs) if runtime_dirs else []

_INSTALLED_CV2_VERSION: str | None = None


def _normalise_version(value: str) -> tuple[int, int, int]:
    """Extract the first three numeric components of a version string."""

    numbers: list[int] = []

    for token in value.split("."):
        match = re.match(r"(\d+)", token)
        if match is None:
            break
        numbers.append(int(match.group(1)))
        if len(numbers) == 3:
            break

    while len(numbers) < 3:
        numbers.append(0)

    return tuple(numbers)


def _versions_match(installed: str | None, expected: str | None) -> bool:
    """Return ``True`` when *installed* matches *expected* up to the patch level."""

    if not installed or not expected:
        return True

    return _normalise_version(installed) == _normalise_version(expected)


def _load_cv2(expected_version: str | None) -> object:
    """Import :mod:`cv2` and provide a helpful error if it is unavailable."""

    try:
        module = importlib.import_module("cv2")
    except ModuleNotFoundError as exc:  # pragma: no cover - defensive programming
        raise ImportError(
            "strandtools requires OpenCV. Install the `opencv-python` package "
            "before importing strandtools."
        ) from exc

    installed_version = getattr(module, "__version__", None)
    global _INSTALLED_CV2_VERSION
    _INSTALLED_CV2_VERSION = installed_version

    if (
        os.name == "nt"
        and expected_version
        and installed_version
        and not _versions_match(installed_version, expected_version)
    ):
        warnings.warn(
            "strandtools was built against OpenCV "
            f"{expected_version}, but the installed cv2 package reports "
            f"version {installed_version}. DLL discovery will prefer the "
            "build-time OpenCV runtime directories.",
            RuntimeWarning,
            stacklevel=2,
        )

    return module


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


def _gather_windows_candidate_dirs(
    cv2_module: object, build_runtime_dirs: Iterable[PathStr]
) -> list[Path]:
    """Collect directories that are likely to contain OpenCV runtime DLLs."""

    package_dir = Path(__file__).resolve().parent
    candidates: list[PathStr] = [package_dir]

    candidates.extend(build_runtime_dirs)

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


_cv2 = _load_cv2(_BUILD_OPENCV_VERSION)

_windows_dll_dirs: list[Path] = []
if os.name == "nt":  # pragma: no branch - Windows specific workaround
    _windows_dll_dirs = _gather_windows_candidate_dirs(
        _cv2, _BUILD_OPENCV_RUNTIME_DIRS
    )
    _register_windows_dll_search_path(_windows_dll_dirs)

try:
    from ._strandtools_impl import *  # noqa: F401,F403
except ImportError as exc:
    if os.name == "nt" and getattr(exc, "name", None) == "_strandtools_impl":
        loaded = _load_dependency_dlls(
            _windows_dll_dirs
            or _gather_windows_candidate_dirs(_cv2, _BUILD_OPENCV_RUNTIME_DIRS)
        )

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
            if _BUILD_OPENCV_RUNTIME_DIRS:
                build_dirs = ", ".join(_BUILD_OPENCV_RUNTIME_DIRS)
                message += (
                    " Build-time OpenCV runtime directories: "
                    f"{build_dirs or '<none>'}."
                )
            if not _versions_match(_INSTALLED_CV2_VERSION, _BUILD_OPENCV_VERSION):
                message += (
                    " strandtools was compiled against OpenCV "
                    f"{_BUILD_OPENCV_VERSION or '<unknown>'} but detected cv2 "
                    f"version {_INSTALLED_CV2_VERSION or '<unknown>'}."
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

