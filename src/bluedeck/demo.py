"""Deterministic demo devices used by --demo and screenshot mode."""
from __future__ import annotations

import random
from typing import Dict, List

from .ble_uuids import describe_characteristic, describe_service
from .models import (
    ConnectionState,
    DeviceInfo,
    DeviceType,
    GattCharacteristicInfo,
    GattServiceInfo,
    Telemetry,
    Transport,
)


def _uid(short: str) -> str:
    return "0000%s-0000-1000-8000-00805f9b34fb" % short


def demo_devices() -> List[DeviceInfo]:
    items = [
        DeviceInfo(
            address="demo:wh1000xm5",
            name="WH-1000XM5",
            device_type=DeviceType.HEADPHONES,
            transport=Transport.DUAL,
            rssi=-47,
            paired=True,
            platform="demo",
            source="demo",
            confidence=0.98,
            classification_source="cod",
            classification_reason="CoD 音频设备 -> 耳机（演示数据）",
            service_uuids=[_uid("110b"), _uid("110e"), _uid("180f"), _uid("180a")],
            metadata={"demo": True, "battery": 82, "firmware": "2.1.0", "model": "WH-1000XM5"},
        ),
        DeviceInfo(
            address="demo:mxmaster3s",
            name="MX Master 3S",
            device_type=DeviceType.MOUSE,
            transport=Transport.BLE,
            rssi=-61,
            paired=True,
            platform="demo",
            source="demo",
            confidence=0.95,
            classification_source="name",
            classification_reason="设备名称命中鼠标关键词（演示数据）",
            service_uuids=[_uid("1812"), _uid("180f"), _uid("180a")],
            metadata={
                "demo": True,
                "battery": 64,
                "firmware": "3.0.4",
                "dpi": 1600,
                "polling_rate": 1000,
                "profile": 2,
            },
        ),
        DeviceInfo(
            address="demo:mxkeys",
            name="MX Keys S",
            device_type=DeviceType.KEYBOARD,
            transport=Transport.BLE,
            rssi=-69,
            paired=True,
            platform="demo",
            source="demo",
            confidence=0.95,
            classification_source="name",
            classification_reason="设备名称命中键盘关键词（演示数据）",
            service_uuids=[_uid("1812"), _uid("180f")],
            metadata={"demo": True, "battery": 91, "backlight": 65, "layout": "ANSI"},
        ),
        DeviceInfo(
            address="demo:dualsense",
            name="DualSense Wireless Controller",
            device_type=DeviceType.GAMEPAD,
            transport=Transport.BLE,
            rssi=-73,
            paired=False,
            platform="demo",
            source="demo",
            confidence=0.95,
            classification_source="name",
            classification_reason="设备名称命中手柄关键词（演示数据）",
            service_uuids=[_uid("1812"), _uid("180f")],
            metadata={"demo": True, "battery": 47},
        ),
        DeviceInfo(
            address="demo:miband8",
            name="Mi Smart Band 8",
            device_type=DeviceType.WEARABLE,
            transport=Transport.BLE,
            rssi=-58,
            paired=True,
            platform="demo",
            source="demo",
            confidence=0.93,
            classification_source="appearance",
            classification_reason="BLE Appearance 可穿戴设备（演示数据）",
            service_uuids=[_uid("180d"), _uid("180f"), _uid("180a")],
            metadata={
                "demo": True,
                "battery": 76,
                "heart_rate": 72,
                "steps": 6420,
                "firmware": "1.0.8",
                "model": "Mi Band 8",
            },
        ),
        DeviceInfo(
            address="demo:soundlink",
            name="SoundLink Flex",
            device_type=DeviceType.SPEAKER,
            transport=Transport.CLASSIC,
            rssi=-66,
            paired=True,
            platform="demo",
            source="demo",
            confidence=0.96,
            classification_source="name",
            classification_reason="设备名称命中音箱关键词（演示数据）",
            service_uuids=[_uid("110b")],
            metadata={"demo": True, "battery": 58, "firmware": "1.3.2"},
        ),
        DeviceInfo(
            address="demo:car",
            name="Tesla Model 3",
            device_type=DeviceType.CAR_AUDIO,
            transport=Transport.CLASSIC,
            rssi=-81,
            paired=True,
            platform="demo",
            source="demo",
            confidence=0.86,
            classification_source="name",
            classification_reason="设备名称命中车载关键词（演示数据）",
            metadata={"demo": True, "battery": None},
        ),
        DeviceInfo(
            address="demo:unknown",
            name="BT-5.3 Module",
            device_type=DeviceType.UNKNOWN,
            transport=Transport.BLE,
            rssi=-88,
            paired=False,
            platform="demo",
            source="demo",
            confidence=0.1,
            classification_source="fallback",
            classification_reason="无足够特征，归类为通用蓝牙设备（演示数据）",
            service_uuids=[_uid("180a")],
            metadata={"demo": True},
        ),
    ]
    return items


def jitter_rssi(device: DeviceInfo) -> None:
    if device.rssi is not None:
        device.rssi = max(-95, min(-35, device.rssi + random.randint(-2, 2)))


def demo_services(device: DeviceInfo) -> List[GattServiceInfo]:
    services: List[GattServiceInfo] = []

    def add(uuid: str, chars: List[GattCharacteristicInfo]) -> None:
        services.append(
            GattServiceInfo(
                uuid=uuid,
                handle=len(services) + 1,
                description=describe_service(uuid),
                characteristics=chars,
            )
        )

    add(
        _uid("1800"),
        [
            GattCharacteristicInfo(_uid("2a00"), 2, ["read", "write"], describe_characteristic(_uid("2a00"))),
            GattCharacteristicInfo(_uid("2a01"), 3, ["read"], describe_characteristic(_uid("2a01"))),
        ],
    )
    add(
        _uid("180a"),
        [
            GattCharacteristicInfo(_uid("2a29"), 5, ["read"], "Manufacturer Name String"),
            GattCharacteristicInfo(_uid("2a24"), 6, ["read"], "Model Number String"),
            GattCharacteristicInfo(_uid("2a26"), 7, ["read"], "Firmware Revision String"),
            GattCharacteristicInfo(_uid("2a25"), 8, ["read"], "Serial Number String"),
        ],
    )
    battery = device.metadata.get("battery")
    if battery is not None:
        add(
            _uid("180f"),
            [
                GattCharacteristicInfo(_uid("2a19"), 10, ["read", "notify"], "Battery Level"),
            ],
        )
    if device.device_type is DeviceType.WEARABLE:
        add(
            _uid("180d"),
            [
                GattCharacteristicInfo(_uid("2a37"), 13, ["notify"], "Heart Rate Measurement"),
                GattCharacteristicInfo(_uid("2a38"), 14, ["read"], "Body Sensor Location"),
            ],
        )
    if device.device_type in (DeviceType.MOUSE, DeviceType.KEYBOARD, DeviceType.GAMEPAD):
        add(
            _uid("1812"),
            [
                GattCharacteristicInfo(_uid("2a4a"), 16, ["read"], "HID Information"),
                GattCharacteristicInfo(_uid("2a4b"), 17, ["read"], "Report Map"),
                GattCharacteristicInfo(_uid("2a4d"), 18, ["read", "notify"], "Report"),
                GattCharacteristicInfo(_uid("2a4e"), 19, ["read", "write"], "Protocol Mode"),
            ],
        )
    if device.device_type is DeviceType.MOUSE:
        add(
            "0000ffe1-0000-1000-8000-00805f9b34fb",
            [GattCharacteristicInfo("0000ffe1-0000-1000-8000-00805f9b34fb", 21, ["write", "notify"], "Vendor DPI Control")],
        )
    if device.device_type is DeviceType.KEYBOARD:
        add(
            "0000ffe2-0000-1000-8000-00805f9b34fb",
            [GattCharacteristicInfo("0000ffe2-0000-1000-8000-00805f9b34fb", 22, ["write"], "Vendor Backlight Control")],
        )
    if device.device_type in (DeviceType.HEADPHONES, DeviceType.SPEAKER, DeviceType.CAR_AUDIO):
        add(
            "0000ffe3-0000-1000-8000-00805f9b34fb",
            [GattCharacteristicInfo("0000ffe3-0000-1000-8000-00805f9b34fb", 24, ["read", "write", "notify"], "Vendor EQ Control")],
        )
    return services


def demo_telemetry(device: DeviceInfo) -> Telemetry:
    meta = device.metadata
    return Telemetry(
        battery=meta.get("battery"),
        heart_rate=meta.get("heart_rate"),
        steps=meta.get("steps"),
        firmware=str(meta.get("firmware") or ""),
        model=str(meta.get("model") or device.name),
        manufacturer="Demo Devices",
        updated_at=0.0,
    )


def demo_read_value(device: DeviceInfo, uuid: str) -> bytes:
    short = uuid.lower()[-12:-8] if len(uuid) >= 12 else uuid.lower()
    actual = uuid.lower()
    if "2a19" in actual:
        battery = device.metadata.get("battery")
        return bytes([int(battery if battery is not None else 50)])
    if "2a37" in actual:
        heart = int(device.metadata.get("heart_rate") or 72)
        return bytes([0x00, heart])
    if "2a24" in actual or "2a26" in actual or "2a29" in actual or "2a25" in actual:
        key = {"2a24": "model", "2a26": "firmware", "2a29": "manufacturer", "2a25": "serial"}.get(short, "")
        value = device.metadata.get(key, "")
        if not value:
            value = "BlueDesk Demo"
        return str(value).encode("utf-8")
    if "2a00" in actual:
        return device.name.encode("utf-8")
    return b"DEMO"
