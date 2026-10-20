"""Platform adapter factory."""
from __future__ import annotations

import sys

from .base import PlatformAdapter, PlatformCapabilities, PlatformError, run_command, which
from .unsupported import UnsupportedPlatform


def get_platform() -> PlatformAdapter:
    if sys.platform == "darwin":
        from .macos import MacOSPlatform

        return MacOSPlatform()
    if sys.platform.startswith("win"):
        from .windows import WindowsPlatform

        return WindowsPlatform()
    return UnsupportedPlatform()


__all__ = [
    "PlatformAdapter",
    "PlatformCapabilities",
    "PlatformError",
    "get_platform",
    "run_command",
    "which",
]
