"""Python bindings for the :mod:`strandtools` C++ extension."""

# Import OpenCV before loading the extension. On Windows this ensures that the
# OpenCV DLL directory is registered via ``os.add_dll_directory`` so that the
# nanobind extension can locate the native dependencies shipped with
# ``opencv-python``.
import cv2 as _cv2  # noqa: F401  (imported for its side effects)

from ._strandtools_impl import *  # noqa: F401,F403

del _cv2

