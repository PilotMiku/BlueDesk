"""Feature availability and protocol adapter registry."""
from __future__ import annotations

from typing import Dict, List

from ..models import DeviceInfo, DeviceType, Transport, capabilities_for
from .base import FeatureAvailability, FeatureStatus, ProtocolAdapter
from .vendor_examples import ExampleBacklightProtocol, ExampleDpiProtocol


class ProtocolRegistry:
    def __init__(self, adapters: List[ProtocolAdapter] | None = None) -> None:
        self.adapters = list(adapters or [ExampleDpiProtocol(), ExampleBacklightProtocol()])

    def matched(self, device: DeviceInfo) -> List[ProtocolAdapter]:
        return [adapter for adapter in self.adapters if adapter.matches(device)]

    def features(self, device: DeviceInfo) -> Dict[str, FeatureAvailability]:
        caps = capabilities_for(device.device_type)
        has_vendor = bool(self.matched(device))
        is_ble = device.transport in (Transport.BLE, Transport.DUAL)
        connected = device.connected

        def vendor(feature: str, detail: str = "") -> FeatureAvailability:
            if has_vendor:
                return FeatureAvailability(feature, FeatureStatus.SUPPORTED, detail or "已加载厂商协议")
            return FeatureAvailability(
                feature,
                FeatureStatus.VENDOR_REQUIRED,
                detail or "需要厂商协议文档 / GATT 特征值；当前仅提供界面占位",
            )

        result: Dict[str, FeatureAvailability] = {}
        if caps.volume:
            result["volume"] = FeatureAvailability(
                "volume", FeatureStatus.SYSTEM, "控制当前系统输出音量；不保证只作用于该设备"
            )
        if caps.media_transport:
            result["media"] = FeatureAvailability(
                "media", FeatureStatus.SYSTEM, "发送系统媒体按键/AppleScript 指令"
            )
        if caps.equalizer:
            result["equalizer"] = vendor("equalizer", "标准 A2DP/AVRCP 不提供设备 EQ；需厂商协议")
        if caps.dpi:
            result["dpi"] = vendor("dpi", "标准 BLE HID 不提供 DPI；需 HID++/厂商 GATT")
        if caps.polling_rate:
            result["polling_rate"] = vendor("polling_rate", "轮询率通常只读且依赖厂商 HID 报告")
        if caps.key_mapping:
            result["key_mapping"] = vendor("key_mapping", "按键映射需要厂商配置协议")
        if caps.backlight:
            result["backlight"] = vendor("backlight", "背光控制需要厂商 HID/GATT 协议")
        if caps.battery:
            if is_ble:
                result["battery"] = FeatureAvailability(
                    "battery", FeatureStatus.STANDARD, "连接后尝试读取 Battery Level (0x2A19)"
                )
            else:
                result["battery"] = FeatureAvailability(
                    "battery", FeatureStatus.UNAVAILABLE, "经典蓝牙电量依赖系统/厂商协议"
                )
        if caps.heart_rate:
            result["heart_rate"] = FeatureAvailability(
                "heart_rate", FeatureStatus.STANDARD, "连接后尝试订阅 Heart Rate (0x2A37)"
            )
        if caps.steps:
            result["steps"] = vendor("steps", "步数没有统一的通用 GATT 特征值；需厂商协议")
        if caps.firmware:
            result["firmware"] = FeatureAvailability(
                "firmware", FeatureStatus.STANDARD, "设备信息服务的固件版本特征值 (0x2A26)"
            )
        result["gatt"] = FeatureAvailability(
            "gatt",
            FeatureStatus.STANDARD if is_ble else FeatureStatus.VENDOR_REQUIRED,
            "BLE GATT 服务发现、读写与通知" if is_ble else "经典蓝牙使用 RFCOMM/SPP 或系统 API",
        )
        result["connected"] = FeatureAvailability(
            "connected",
            FeatureStatus.SUPPORTED if connected else FeatureStatus.UNAVAILABLE,
            "连接状态",
        )
        return result

    def type_summary(self, device: DeviceInfo) -> str:
        if device.device_type is DeviceType.UNKNOWN:
            return "通用蓝牙设备：提供连接、GATT、RSSI 与日志"
        matched = self.matched(device)
        if matched:
            return "已加载协议：" + "、".join(adapter.display_name for adapter in matched)
        return "标准功能可用；高级功能需要厂商协议"
