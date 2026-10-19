"""Protocol adapter contracts for vendor-specific features."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..models import DeviceInfo


class FeatureStatus(str, Enum):
    SUPPORTED = "supported"
    SYSTEM = "system"
    STANDARD = "standard"
    VENDOR_REQUIRED = "vendor_required"
    UNAVAILABLE = "unavailable"

    @property
    def label(self) -> str:
        return {
            FeatureStatus.SUPPORTED: "已支持",
            FeatureStatus.SYSTEM: "系统级",
            FeatureStatus.STANDARD: "标准协议",
            FeatureStatus.VENDOR_REQUIRED: "需要厂商协议",
            FeatureStatus.UNAVAILABLE: "不可用",
        }[self]


@dataclass(frozen=True)
class FeatureAvailability:
    feature: str
    status: FeatureStatus
    detail: str = ""


class ProtocolError(RuntimeError):
    pass


class ProtocolAdapter:
    id = "base"
    vendor = ""
    display_name = "Base protocol"

    def matches(self, device: DeviceInfo) -> bool:
        return False

    def set_dpi(self, device: DeviceInfo, dpi: int) -> bytes:
        raise ProtocolError("该设备没有可用的 DPI 协议适配器")

    def set_equalizer(self, device: DeviceInfo, bands: dict) -> bytes:
        raise ProtocolError("该设备没有可用的 EQ 协议适配器")

    def set_backlight(self, device: DeviceInfo, percent: int) -> bytes:
        raise ProtocolError("该设备没有可用的背光协议适配器")

    def set_key_mapping(self, device: DeviceInfo, mapping: dict) -> bytes:
        raise ProtocolError("该设备没有可用的按键映射协议适配器")
