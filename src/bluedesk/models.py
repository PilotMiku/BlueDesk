"""Domain models shared by the UI, platform adapters and protocol layer.

The models intentionally contain no Qt or Bleak imports so they can be tested
and reused by a future CLI, tray agent or alternative UI.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple


class DeviceType(str, Enum):
    """Device categories understood by the control-panel router."""

    HEADPHONES = "headphones"
    SPEAKER = "speaker"
    CAR_AUDIO = "car_audio"
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    GAMEPAD = "gamepad"
    WEARABLE = "wearable"
    PHONE = "phone"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            DeviceType.HEADPHONES: "耳机 / 头戴",
            DeviceType.SPEAKER: "音箱",
            DeviceType.CAR_AUDIO: "车载音频",
            DeviceType.MOUSE: "鼠标",
            DeviceType.KEYBOARD: "键盘",
            DeviceType.GAMEPAD: "游戏手柄",
            DeviceType.WEARABLE: "手表 / 手环",
            DeviceType.PHONE: "手机",
            DeviceType.UNKNOWN: "通用蓝牙设备",
        }[self]

    @property
    def short_label(self) -> str:
        return {
            DeviceType.HEADPHONES: "耳机",
            DeviceType.SPEAKER: "音箱",
            DeviceType.CAR_AUDIO: "车载",
            DeviceType.MOUSE: "鼠标",
            DeviceType.KEYBOARD: "键盘",
            DeviceType.GAMEPAD: "手柄",
            DeviceType.WEARABLE: "穿戴",
            DeviceType.PHONE: "手机",
            DeviceType.UNKNOWN: "通用",
        }[self]

    @property
    def group(self) -> str:
        if self in (DeviceType.HEADPHONES, DeviceType.SPEAKER, DeviceType.CAR_AUDIO):
            return "audio"
        if self in (DeviceType.MOUSE, DeviceType.KEYBOARD, DeviceType.GAMEPAD):
            return "hid"
        if self is DeviceType.WEARABLE:
            return "wearable"
        if self is DeviceType.PHONE:
            return "phone"
        return "other"

    @property
    def accent(self) -> str:
        return {
            DeviceType.HEADPHONES: "#6ea8ff",
            DeviceType.SPEAKER: "#52d6c8",
            DeviceType.CAR_AUDIO: "#f3b45f",
            DeviceType.MOUSE: "#b18cff",
            DeviceType.KEYBOARD: "#7fd58b",
            DeviceType.GAMEPAD: "#ff8a7a",
            DeviceType.WEARABLE: "#f58bc0",
            DeviceType.PHONE: "#80c7ff",
            DeviceType.UNKNOWN: "#8e9bb3",
        }[self]


class Transport(str, Enum):
    BLE = "ble"
    CLASSIC = "classic"
    DUAL = "dual"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            Transport.BLE: "BLE",
            Transport.CLASSIC: "经典蓝牙",
            Transport.DUAL: "双模",
            Transport.UNKNOWN: "未知传输",
        }[self]


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    FAILED = "failed"

    @property
    def label(self) -> str:
        return {
            ConnectionState.DISCONNECTED: "未连接",
            ConnectionState.CONNECTING: "连接中",
            ConnectionState.CONNECTED: "已连接",
            ConnectionState.DISCONNECTING: "断开中",
            ConnectionState.FAILED: "连接失败",
        }[self]


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip().lower()
        if text.startswith("0x"):
            return int(text, 16)
        return int(text, 10)
    except (TypeError, ValueError):
        return None


@dataclass
class DeviceInfo:
    """A normalised view of a classic and/or BLE device.

    The address is the stable identity used by the UI. It is a Bluetooth MAC
    on Windows/classic transports and a CoreBluetooth UUID on macOS BLE.
    Devices discovered through the system profiler may only expose a name and
    receive a synthetic macos: address.
    """

    address: str
    name: str = ""
    device_type: DeviceType = DeviceType.UNKNOWN
    transport: Transport = Transport.UNKNOWN
    rssi: Optional[int] = None
    tx_power: Optional[int] = None
    paired: bool = False
    connected: bool = False
    state: ConnectionState = ConnectionState.DISCONNECTED
    class_of_device: Optional[int] = None
    major_device_class: Optional[int] = None
    minor_device_class: Optional[int] = None
    service_class: Optional[int] = None
    ble_appearance: Optional[int] = None
    service_uuids: List[str] = field(default_factory=list)
    manufacturer_data: Dict[int, bytes] = field(default_factory=dict)
    service_data: Dict[str, bytes] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)
    platform: str = ""
    source: str = "unknown"
    confidence: float = 0.0
    classification_source: str = ""
    classification_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return (self.address or self.name or "unnamed").strip().lower()

    @property
    def display_name(self) -> str:
        return self.name.strip() or "未命名蓝牙设备"

    @property
    def short_address(self) -> str:
        addr = self.address
        if not addr:
            return "—"
        if addr.startswith("macos:"):
            return "macOS 配对设备"
        if len(addr) > 20:
            return addr[:8] + "…" + addr[-4:]
        return addr

    @property
    def rssi_bars(self) -> int:
        return rssi_to_bars(self.rssi)

    @property
    def is_ble(self) -> bool:
        return self.transport in (Transport.BLE, Transport.DUAL)

    @property
    def is_audio(self) -> bool:
        return self.device_type.group == "audio"

    def touch(self) -> None:
        self.last_seen = time.time()

    def merge(self, other: "DeviceInfo") -> bool:
        """Merge discovery data without weakening a high-confidence type."""
        before = self.to_dict()
        if other.name and not self.name:
            self.name = other.name
        if other.device_type is not DeviceType.UNKNOWN and (
            self.device_type is DeviceType.UNKNOWN or other.confidence > self.confidence
        ):
            self.device_type = other.device_type
            self.confidence = other.confidence
            self.classification_source = other.classification_source
            self.classification_reason = other.classification_reason
        self.paired = self.paired or other.paired
        self.connected = self.connected or other.connected
        if other.state is not ConnectionState.DISCONNECTED:
            self.state = other.state
        if other.rssi is not None:
            self.rssi = other.rssi
        if other.tx_power is not None:
            self.tx_power = other.tx_power
        if other.class_of_device is not None:
            self.class_of_device = other.class_of_device
        if other.major_device_class is not None:
            self.major_device_class = other.major_device_class
        if other.minor_device_class is not None:
            self.minor_device_class = other.minor_device_class
        if other.service_class is not None:
            self.service_class = other.service_class
        if other.ble_appearance is not None:
            self.ble_appearance = other.ble_appearance
        for uid in other.service_uuids:
            if uid not in self.service_uuids:
                self.service_uuids.append(uid)
        for cid, data in other.manufacturer_data.items():
            self.manufacturer_data[int(cid)] = bytes(data)
        for uid, data in other.service_data.items():
            self.service_data[uid] = bytes(data)
        if other.transport is not Transport.UNKNOWN:
            if self.transport is Transport.UNKNOWN:
                self.transport = other.transport
            elif self.transport is not other.transport:
                self.transport = Transport.DUAL
        if other.source and self.source == "unknown":
            self.source = other.source
        if other.last_seen > self.last_seen:
            self.last_seen = other.last_seen
        self.metadata.update(other.metadata)
        self.touch()
        return self.to_dict() != before

    def mark_connected(self) -> None:
        self.connected = True
        self.state = ConnectionState.CONNECTED
        self.paired = True

    def mark_disconnected(self, failed: bool = False) -> None:
        self.connected = False
        self.state = ConnectionState.FAILED if failed else ConnectionState.DISCONNECTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "device_type": self.device_type.value,
            "transport": self.transport.value,
            "rssi": self.rssi,
            "tx_power": self.tx_power,
            "paired": self.paired,
            "connected": self.connected,
            "state": self.state.value,
            "class_of_device": self.class_of_device,
            "major_device_class": self.major_device_class,
            "minor_device_class": self.minor_device_class,
            "service_class": self.service_class,
            "ble_appearance": self.ble_appearance,
            "service_uuids": list(self.service_uuids),
            "manufacturer_data": {
                str(cid): bytes(data).hex() for cid, data in self.manufacturer_data.items()
            },
            "service_data": {
                uid: bytes(data).hex() for uid, data in self.service_data.items()
            },
            "last_seen": self.last_seen,
            "platform": self.platform,
            "source": self.source,
            "confidence": self.confidence,
            "classification_source": self.classification_source,
            "classification_reason": self.classification_reason,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceInfo":
        manufacturer: Dict[int, bytes] = {}
        for cid, value in (data.get("manufacturer_data") or {}).items():
            try:
                manufacturer[int(cid)] = bytes.fromhex(str(value))
            except (TypeError, ValueError):
                continue
        service_data: Dict[str, bytes] = {}
        for uid, value in (data.get("service_data") or {}).items():
            try:
                service_data[str(uid)] = bytes.fromhex(str(value))
            except (TypeError, ValueError):
                continue
        return cls(
            address=str(data.get("address") or ""),
            name=str(data.get("name") or ""),
            device_type=_enum_or(DeviceType, data.get("device_type"), DeviceType.UNKNOWN),
            transport=_enum_or(Transport, data.get("transport"), Transport.UNKNOWN),
            rssi=_as_int(data.get("rssi")),
            tx_power=_as_int(data.get("tx_power")),
            paired=bool(data.get("paired")),
            connected=bool(data.get("connected")),
            state=_enum_or(ConnectionState, data.get("state"), ConnectionState.DISCONNECTED),
            class_of_device=_as_int(data.get("class_of_device")),
            major_device_class=_as_int(data.get("major_device_class")),
            minor_device_class=_as_int(data.get("minor_device_class")),
            service_class=_as_int(data.get("service_class")),
            ble_appearance=_as_int(data.get("ble_appearance")),
            service_uuids=[str(x) for x in (data.get("service_uuids") or [])],
            manufacturer_data=manufacturer,
            service_data=service_data,
            last_seen=float(data.get("last_seen") or time.time()),
            platform=str(data.get("platform") or ""),
            source=str(data.get("source") or "unknown"),
            confidence=float(data.get("confidence") or 0.0),
            classification_source=str(data.get("classification_source") or ""),
            classification_reason=str(data.get("classification_reason") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


def _enum_or(enum_type: Any, value: Any, default: Any) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return default


@dataclass
class GattCharacteristicInfo:
    uuid: str
    handle: Optional[int] = None
    properties: List[str] = field(default_factory=list)
    description: str = ""

    @property
    def can_read(self) -> bool:
        return "read" in self.properties

    @property
    def can_write(self) -> bool:
        return bool({"write", "write-without-response"} & set(self.properties))

    @property
    def can_notify(self) -> bool:
        return bool({"notify", "indicate"} & set(self.properties))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "handle": self.handle,
            "properties": list(self.properties),
            "description": self.description,
        }


@dataclass
class GattServiceInfo:
    uuid: str
    handle: Optional[int] = None
    description: str = ""
    characteristics: List[GattCharacteristicInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "handle": self.handle,
            "description": self.description,
            "characteristics": [c.to_dict() for c in self.characteristics],
        }


@dataclass
class Telemetry:
    battery: Optional[int] = None
    charging: Optional[bool] = None
    heart_rate: Optional[int] = None
    steps: Optional[int] = None
    firmware: str = ""
    model: str = ""
    serial: str = ""
    manufacturer: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = 0.0

    def merge(self, other: "Telemetry") -> None:
        for name in (
            "battery",
            "charging",
            "heart_rate",
            "steps",
            "firmware",
            "model",
            "serial",
            "manufacturer",
        ):
            value = getattr(other, name)
            if value not in (None, ""):
                setattr(self, name, value)
        self.extra.update(other.extra)
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "battery": self.battery,
            "charging": self.charging,
            "heart_rate": self.heart_rate,
            "steps": self.steps,
            "firmware": self.firmware,
            "model": self.model,
            "serial": self.serial,
            "manufacturer": self.manufacturer,
            "extra": dict(self.extra),
            "updated_at": self.updated_at,
        }


@dataclass
class LogEntry:
    level: str
    message: str
    address: str = ""
    category: str = "app"
    timestamp: float = field(default_factory=time.time)
    data: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.timestamp,
            "level": self.level,
            "category": self.category,
            "address": self.address,
            "message": self.message,
            "data": self.data,
        }


@dataclass(frozen=True)
class DeviceCapabilities:
    volume: bool = False
    media_transport: bool = False
    equalizer: bool = False
    dpi: bool = False
    polling_rate: bool = False
    key_mapping: bool = False
    backlight: bool = False
    battery: bool = False
    heart_rate: bool = False
    steps: bool = False
    firmware: bool = False
    gatt_browser: bool = False
    rfcomm: bool = False
    rename: bool = False
    system_pairing: bool = False

    @property
    def vendor_gated(self) -> Tuple[str, ...]:
        names: List[str] = []
        if self.equalizer:
            names.append("EQ")
        if self.dpi:
            names.append("DPI")
        if self.polling_rate:
            names.append("轮询率")
        if self.key_mapping:
            names.append("按键映射")
        if self.backlight:
            names.append("背光")
        if self.steps:
            names.append("步数")
        return tuple(names)


def capabilities_for(device_type: DeviceType) -> DeviceCapabilities:
    """Return the control-panel modules a type should show.

    Features marked as vendor-gated in the UI are only informational unless a
    matching protocol adapter is loaded.
    """
    if device_type in (DeviceType.HEADPHONES, DeviceType.SPEAKER, DeviceType.CAR_AUDIO):
        return DeviceCapabilities(
            volume=True,
            media_transport=True,
            equalizer=True,
            battery=True,
            firmware=True,
            gatt_browser=True,
            rfcomm=True,
            rename=True,
            system_pairing=True,
        )
    if device_type is DeviceType.MOUSE:
        return DeviceCapabilities(
            dpi=True,
            polling_rate=True,
            key_mapping=True,
            battery=True,
            firmware=True,
            gatt_browser=True,
            rfcomm=True,
            rename=True,
            system_pairing=True,
        )
    if device_type is DeviceType.KEYBOARD:
        return DeviceCapabilities(
            key_mapping=True,
            backlight=True,
            battery=True,
            firmware=True,
            gatt_browser=True,
            rfcomm=True,
            rename=True,
            system_pairing=True,
        )
    if device_type is DeviceType.GAMEPAD:
        return DeviceCapabilities(
            key_mapping=True,
            battery=True,
            firmware=True,
            gatt_browser=True,
            rfcomm=True,
            rename=True,
            system_pairing=True,
        )
    if device_type is DeviceType.WEARABLE:
        return DeviceCapabilities(
            battery=True,
            heart_rate=True,
            steps=True,
            firmware=True,
            gatt_browser=True,
            rfcomm=True,
            rename=True,
            system_pairing=True,
        )
    return DeviceCapabilities(
        battery=True,
        firmware=True,
        gatt_browser=True,
        rfcomm=True,
        rename=True,
        system_pairing=True,
    )


def rssi_to_bars(rssi: Optional[int]) -> int:
    if rssi is None:
        return 0
    if rssi >= -55:
        return 4
    if rssi >= -67:
        return 3
    if rssi >= -78:
        return 2
    return 1


def rssi_label(rssi: Optional[int]) -> str:
    if rssi is None:
        return "RSSI —"
    bars = rssi_to_bars(rssi)
    quality = {4: "极佳", 3: "良好", 2: "一般", 1: "较弱", 0: "未知"}[bars]
    return "RSSI %s dBm · %s" % (rssi, quality)


def normalize_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def dedupe_devices(devices: Iterable[DeviceInfo]) -> List[DeviceInfo]:
    by_key: Dict[str, DeviceInfo] = {}
    for device in devices:
        existing = by_key.get(device.key)
        if existing is None:
            by_key[device.key] = device
        else:
            existing.merge(device)
    return list(by_key.values())
