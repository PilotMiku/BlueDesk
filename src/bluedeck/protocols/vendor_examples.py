"""Example vendor protocol adapters and integration points.

These adapters deliberately do NOT match arbitrary devices. Writing undocumented
packets to a real mouse/keyboard can change settings or even brick the device.
Enable an adapter only after implementing the vendor specification and matching
on a trusted vendor service UUID / manufacturer ID.
"""
from __future__ import annotations

from typing import Dict

from ..codecs import build_dpi_packet, checksum8_xor
from ..models import DeviceInfo
from .base import ProtocolAdapter, ProtocolError

EXAMPLE_DPI_SERVICE = "0000ffe1-0000-1000-8000-00805f9b34fb"
EXAMPLE_BACKLIGHT_SERVICE = "0000ffe2-0000-1000-8000-00805f9b34fb"


class ExampleDpiProtocol(ProtocolAdapter):
    """Integration example for a fictional mouse vendor.

    Frame: A5 01 <profile> <dpi lo> <dpi hi> <xor>
    Match only devices explicitly tagged by the user/imported profile.
    """

    id = "example-dpi"
    vendor = "Example Peripherals"
    display_name = "Example DPI 协议（示例）"

    def matches(self, device: DeviceInfo) -> bool:
        return device.metadata.get("vendor_protocol") == self.id

    def set_dpi(self, device: DeviceInfo, dpi: int) -> bytes:
        return build_dpi_packet(dpi, profile=int(device.metadata.get("profile", 1)))

    @property
    def characteristic_uuid(self) -> str:
        return EXAMPLE_DPI_SERVICE


class ExampleBacklightProtocol(ProtocolAdapter):
    """Example backlight frame builder for a fictional keyboard."""

    id = "example-backlight"
    vendor = "Example Peripherals"
    display_name = "Example 背光协议（示例）"

    def matches(self, device: DeviceInfo) -> bool:
        return device.metadata.get("vendor_protocol") == self.id

    def set_backlight(self, device: DeviceInfo, percent: int) -> bytes:
        if not 0 <= percent <= 100:
            raise ProtocolError("背光亮度必须在 0..100")
        body = bytes([0xB2, 0x01, int(percent), 0x00])
        return body + bytes([checksum8_xor(body)])

    @property
    def characteristic_uuid(self) -> str:
        return EXAMPLE_BACKLIGHT_SERVICE


def example_eq_packet(bands: Dict[str, int]) -> bytes:
    """Build a toy 5-band EQ packet for protocol tests only.

    bands keys: 60, 230, 910, 3600, 14000 (Hz), values -12..12 dB.
    Frame: E1 05 <band1+12> ... <band5+12> <xor>
    """
    values = []
    for key in ("60", "230", "910", "3600", "14000"):
        value = int(bands.get(key, 0))
        values.append(max(0, min(24, value + 12)))
    body = bytes([0xE1, 0x05] + values)
    return body + bytes([checksum8_xor(body)])
