"""Fallback adapter for Linux/CI and unknown platforms."""
from __future__ import annotations

from typing import List

from ..models import DeviceInfo
from .base import PlatformAdapter, PlatformCapabilities


class UnsupportedPlatform(PlatformAdapter):
    system = "Unknown"

    def __init__(self) -> None:
        self.capabilities = PlatformCapabilities(
            name="Unsupported",
            classic_discovery=False,
            classic_control=False,
            absolute_volume=False,
            media_keys=False,
            system_pairing=False,
            gatt=True,
            notes=("This adapter is a safe placeholder; BLE scanning may still work through Bleak.",),
        )

    def paired_devices(self) -> List[DeviceInfo]:
        return []
