"""Bluetooth device type classification.

Priority order:
1. Classic Class of Device (major/minor/service class)
2. BLE Appearance
3. GATT / classic service UUIDs
4. Platform-provided minor type (system profiler / PnP)
5. Device-name keywords
6. Manufacturer data hints
7. UNKNOWN

Within the audio family the name is allowed to refine an ambiguous service or
appearance result (for example A2DP sink + AirPods -> HEADPHONES), because the
audio service classes cannot distinguish headphones from speakers.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

from .models import DeviceType, normalize_name

# ---------------------------------------------------------------------------
# Classic Bluetooth Class of Device
# ---------------------------------------------------------------------------
COD_MAJOR_MISC = 0x00
COD_MAJOR_COMPUTER = 0x01
COD_MAJOR_PHONE = 0x02
COD_MAJOR_LAN = 0x03
COD_MAJOR_AUDIO = 0x04
COD_MAJOR_PERIPHERAL = 0x05
COD_MAJOR_IMAGING = 0x06
COD_MAJOR_WEARABLE = 0x07
COD_MAJOR_TOY = 0x08
COD_MAJOR_HEALTH = 0x09

COD_MINOR_AUDIO_WEARABLE_HEADSET = 0x01
COD_MINOR_AUDIO_HANDSFREE = 0x02
COD_MINOR_AUDIO_MICROPHONE = 0x03
COD_MINOR_AUDIO_LOUDSPEAKER = 0x04
COD_MINOR_AUDIO_HEADPHONES = 0x05
COD_MINOR_AUDIO_PORTABLE = 0x06
COD_MINOR_AUDIO_CAR = 0x07
COD_MINOR_AUDIO_SETTOP = 0x08
COD_MINOR_AUDIO_HIFI = 0x09
COD_MINOR_AUDIO_DVD = 0x0A
COD_MINOR_AUDIO_GAMING = 0x0B
COD_MINOR_AUDIO_HEARING_AID = 0x0C

COD_MINOR_PERIPHERAL_JOYSTICK = 0x04
COD_MINOR_PERIPHERAL_GAMEPAD = 0x08
COD_MINOR_PERIPHERAL_REMOTE = 0x0C
COD_MINOR_PERIPHERAL_KEYBOARD = 0x10
COD_MINOR_PERIPHERAL_POINTING = 0x20
COD_MINOR_PERIPHERAL_COMBO = 0x30

# Service class bits are stored in bits 13..23 of the CoD.
COD_SERVICE_AUDIO = 1 << 6
COD_SERVICE_TELEPHONY = 1 << 5
COD_SERVICE_RENDERING = 1 << 3
COD_SERVICE_CAPTURING = 1 << 2

# ---------------------------------------------------------------------------
# BLE Appearance (Bluetooth SIG assigned numbers)
# ---------------------------------------------------------------------------
APPEARANCE_PHONE = 0x0040
APPEARANCE_COMPUTER = 0x0080
APPEARANCE_WATCH = 0x00C0
APPEARANCE_SPORTS_WATCH = 0x00C1
APPEARANCE_SMARTWATCH = 0x00C2
APPEARANCE_HID = 0x03C0
APPEARANCE_HID_KEYBOARD = 0x03C1
APPEARANCE_HID_MOUSE = 0x03C2
APPEARANCE_HID_JOYSTICK = 0x03C3
APPEARANCE_HID_GAMEPAD = 0x03C4
APPEARANCE_HID_DIGITIZER = 0x03C5
APPEARANCE_HID_CARD_READER = 0x03C6
APPEARANCE_HID_PEN = 0x03C7
APPEARANCE_HID_BARCODE = 0x03C8
APPEARANCE_HID_TOUCHPAD = 0x03C9
APPEARANCE_HID_PRESENTATION = 0x03CA
APPEARANCE_HEART_RATE = 0x0340
APPEARANCE_RUNNING_WALKING = 0x0440
APPEARANCE_AUDIO_SINK = 0x0840
APPEARANCE_AUDIO_SOURCE = 0x0880
APPEARANCE_AUDIO_BOTH = 0x08C0
APPEARANCE_WEARABLE = 0x0980

# ---------------------------------------------------------------------------
# Service UUIDs (16-bit forms; full 128-bit base UUIDs are normalised)
# ---------------------------------------------------------------------------
SERVICE_HEADSET = "1108"
SERVICE_AUDIO_SOURCE = "110a"
SERVICE_AUDIO_SINK = "110b"
SERVICE_AVRCP_TARGET = "110c"
SERVICE_A2DP = "110d"
SERVICE_AVRCP = "110e"
SERVICE_AVRCP_CONTROLLER = "110f"
SERVICE_HEADSET_ALT = "1112"
SERVICE_HANDSFREE = "111e"
SERVICE_BATTERY = "180f"
SERVICE_DEVICE_INFO = "180a"
SERVICE_HID = "1812"
SERVICE_HEART_RATE = "180d"
SERVICE_RSC = "1814"
SERVICE_CSC = "1816"
SERVICE_CYCLING_POWER = "1818"
SERVICE_FITNESS_MACHINE = "1826"
SERVICE_PHYSICAL_ACTIVITY = "183e"

UUID_BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb"

MANUFACTURER_APPLE = 0x004C
MANUFACTURER_MICROSOFT = 0x0006
MANUFACTURER_SAMSUNG = 0x0075
MANUFACTURER_LOGITECH = 0x005D
MANUFACTURER_SONY = 0x012D
MANUFACTURER_BOSE = 0x009E


@dataclass(frozen=True)
class Classification:
    device_type: DeviceType
    confidence: float
    source: str
    reason: str

    @property
    def label(self) -> str:
        return self.device_type.label


def decode_class_of_device(cod: int) -> Tuple[int, int, int]:
    """Return (major, minor, service_class) from a 24-bit CoD value."""
    cod = int(cod) & 0xFFFFFF
    major = (cod >> 8) & 0x1F
    minor = (cod >> 2) & 0x3F
    service = (cod >> 13) & 0x7FF
    return major, minor, service


def normalize_uuid(value: object) -> str:
    """Normalise an int / 16-bit / 128-bit UUID to a lowercase string."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if len(text) == 4 and re.fullmatch(r"[0-9a-f]{4}", text):
        return text
    if len(text) == 8 and re.fullmatch(r"[0-9a-f]{8}", text):
        # Some stacks expose 32-bit UUIDs; use the numeric string.
        return text
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError):
        return text
    return str(parsed).lower()


def uuid16(value: object) -> Optional[str]:
    """Return the 16-bit short UUID if this is a Bluetooth SIG UUID."""
    normal = normalize_uuid(value)
    if len(normal) == 4:
        return normal
    if normal.endswith(UUID_BASE_SUFFIX) and normal.startswith("0000"):
        short = normal[4:8]
        if re.fullmatch(r"[0-9a-f]{4}", short):
            return short
    return None


def _matches_any_uuid(service_uuids: Iterable[object], candidates: Set[str]) -> bool:
    for uid in service_uuids or ():
        short = uuid16(uid)
        if short in candidates:
            return True
        # Tolerate stacks that return a bare 128-bit UUID with the SIG base
        # UUID but without the leading 0000.
        if normalize_uuid(uid) in {c + UUID_BASE_SUFFIX for c in candidates}:
            return True
    return False


# ---------------------------------------------------------------------------
# Name heuristics
# ---------------------------------------------------------------------------
_NAME_RULES: Tuple[Tuple[DeviceType, Tuple[str, ...]], ...] = (
    (
        DeviceType.CAR_AUDIO,
        (
            r"\bcar\b",
            r"\bauto(motive)?\b",
            r"\bvehicle\b",
            r"\buconnect\b",
            r"\bmylink\b",
            r"\bsync\s?3\b",
            r"\bcarplay\b",
            r"\btesla\b",
            r"\bmodel\s+[3sxy]\b",
            r"\b(bmw|mercedes|audi|porsche|volvo|lexus|toyota|ford|chevrolet)\b",
            r"\bcar\s+multimedia\b",
        ),
    ),
    (
        DeviceType.MOUSE,
        (
            r"\bmouse\b",
            r"\btrackpad\b",
            r"\btrackball\b",
            r"\bmagic\s+mouse\b",
            r"\bmx\s+(master|anywhere)\b",
            r"\bm[0-9]{3}\b",
            r"\blift\s+vertical\b",
            r"\bmx\s+ergo\b",
            r"\bmx\s+vertical\b",
            r"\bprecision\s+mouse\b",
            r"\bquiet\s+comfort\b.*\bmouse\b",
        ),
    ),
    (
        DeviceType.KEYBOARD,
        (
            r"\bkeyboard\b",
            r"\bkeypad\b",
            r"\bmagic\s+keyboard\b",
            r"\bmx\s+keys\b",
            r"\bk[0-9]{3}\b",
            r"\bcraft\s+keyboard\b",
            r"\bmechanical\s+keyboard\b",
        ),
    ),
    (
        DeviceType.GAMEPAD,
        (
            r"\bgamepad\b",
            r"\bgame\s+pad\b",
            r"\bcontroller\b",
            r"\bdualsense\b",
            r"\bdualshock\b",
            r"\bjoy[\s-]?con\b",
            r"\b8bitdo\b",
            r"\bstadia\b",
            r"\bxbox\s+wireless\b",
            r"\bpro\s+controller\b",
            r"\bswitch\s+pro\b",
        ),
    ),
    (
        DeviceType.WEARABLE,
        (
            r"\bsmart[\s-]?watch\b",
            r"\bwatch\b",
            r"\bmi\s+band\b",
            r"\bredmi\s+band\b",
            r"\bhonor\s+band\b",
            r"\bhuawei\s+band\b",
            r"\bsmart[\s-]?band\b",
            r"\bband\s+[0-9]+\b",
            r"\bfitbit\b",
            r"\bgarmin\b",
            r"\bforerunner\b",
            r"\bfenix\b",
            r"\bvenu\b",
            r"\bamazfit\b",
            r"\bwhoop\b",
            r"\boura\s+ring\b",
            r"\bwearable\b",
        ),
    ),
    (
        DeviceType.SPEAKER,
        (
            r"\bspeaker\b",
            r"\bsoundbar\b",
            r"\bboombox\b",
            r"\bhomepod\b",
            r"\bsonos\b",
            r"\becho\s+(dot|show|pop|studio)?\b",
            r"\bsoundlink\b",
            r"\brevolve\b",
            r"\bpartybox\b",
            r"\bjbl\s+(flip|charge|go|party|pulse|xtreme)\b",
            r"\bsrs-[a-z0-9]+\b",
            r"\bsoundcore\s+(motion|flare|rave|boost|select)\b",
            r"\bmi\s+speaker\b",
            r"\bgoogle\s+home\b",
        ),
    ),
    (
        DeviceType.HEADPHONES,
        (
            r"\bheadphones?\b",
            r"\bheadset\b",
            r"\bearbuds?\b",
            r"\bearphones?\b",
            r"\bairpods?\b",
            r"\bearpods?\b",
            r"\btws\b",
            r"\bbuds?\b",
            r"\bwh-[a-z0-9]+\b",
            r"\bwf-[a-z0-9]+\b",
            r"\bwi-[a-z0-9]+\b",
            r"\bquietcomfort\b",
            r"\bqc[0-9]{2}\b",
            r"\bmomentum\b",
            r"\bbeats\b",
            r"\bjabra\b",
            r"\bsoundcore\s+(liberty|life|space|sleep)\b",
            r"\bjbl\s+(tune|live)\b",
            r"\bfreebuds\b",
            r"\bpixel\s+buds\b",
            r"\bnothing\s+ear\b",
            r"\boneplus\s+buds\b",
            r"\bhonor\s+choice\b",
            r"\bhitune\b",
            r"\b1000xm[0-9]\b",
            r"\bhearing\s+aid\b",
        ),
    ),
    (
        DeviceType.PHONE,
        (
            r"\biphone\b",
            r"\bgalaxy\b",
            r"\bpixel\s+[0-9]\b",
            r"\bphone\b",
            r"\bredmi\s+note\b",
        ),
    ),
)

_OS_HINT_RULES: Tuple[Tuple[DeviceType, Tuple[str, ...]], ...] = (
    (
        DeviceType.HEADPHONES,
        ("headphone", "headset", "earbud", "earphone", "耳机", "耳機", "头戴", "耳麥", "耳麦"),
    ),
    (DeviceType.SPEAKER, ("speaker", "loudspeaker", "音箱", "揚聲器", "扬声器", "音响", "音響")),
    (DeviceType.CAR_AUDIO, ("car", "车载", "車載", "automotive")),
    (DeviceType.MOUSE, ("mouse", "trackpad", "pointing", "鼠标", "滑鼠", "觸控板", "触控板")),
    (DeviceType.KEYBOARD, ("keyboard", "keypad", "键盘", "鍵盤")),
    (DeviceType.GAMEPAD, ("gamepad", "game controller", "joystick", "手柄", "游戏控制器", "遊戲控制器")),
    (DeviceType.WEARABLE, ("watch", "wearable", "band", "手表", "手錶", "手环", "手環", "穿戴")),
    (DeviceType.PHONE, ("phone", "手机", "手機")),
)


def _name_match(name: str) -> Optional[Classification]:
    if not name:
        return None
    text = normalize_name(name).replace("_", " ")
    text = re.sub(r"^le[\s-]+", "", text)
    for device_type, patterns in _NAME_RULES:
        for pattern in patterns:
            if re.search(pattern, text):
                return Classification(
                    device_type,
                    0.74,
                    "name",
                    "设备名称命中关键词 /%s/" % pattern,
                )
    return None


def _os_hint_match(hint: Optional[str]) -> Optional[Classification]:
    if not hint:
        return None
    text = normalize_name(hint)
    for device_type, words in _OS_HINT_RULES:
        for word in words:
            if word in text:
                return Classification(
                    device_type,
                    0.86,
                    "os",
                    "系统设备类型提示为 %s" % hint,
                )
    return None


def _cod_match(
    cod: Optional[int],
    major: Optional[int],
    minor: Optional[int],
    service_class: Optional[int] = None,
) -> Optional[Classification]:
    cod_service = 0
    if cod is not None:
        cod_major, cod_minor, cod_service = decode_class_of_device(int(cod))
        if major is None:
            major = cod_major
        if minor is None:
            minor = cod_minor
    if service_class is None:
        service_class = cod_service
    audio_service = bool(service_class and (service_class & COD_SERVICE_AUDIO))
    service_note = " · Audio Service" if audio_service else ""
    if major is None:
        return None
    if major == COD_MAJOR_AUDIO:
        if minor in (COD_MINOR_AUDIO_WEARABLE_HEADSET, COD_MINOR_AUDIO_HANDSFREE,
                     COD_MINOR_AUDIO_HEADPHONES, COD_MINOR_AUDIO_HEARING_AID):
            return Classification(DeviceType.HEADPHONES, 0.98, "cod", "CoD 音频设备 -> 耳机" + service_note)
        if minor == COD_MINOR_AUDIO_CAR:
            return Classification(DeviceType.CAR_AUDIO, 0.98, "cod", "CoD 音频设备 -> 车载音响" + service_note)
        if minor in (COD_MINOR_AUDIO_LOUDSPEAKER, COD_MINOR_AUDIO_PORTABLE,
                     COD_MINOR_AUDIO_SETTOP, COD_MINOR_AUDIO_HIFI,
                     COD_MINOR_AUDIO_DVD, COD_MINOR_AUDIO_GAMING):
            return Classification(DeviceType.SPEAKER, 0.96, "cod", "CoD 音频设备 -> 音箱" + service_note)
        if minor == COD_MINOR_AUDIO_MICROPHONE:
            return Classification(DeviceType.UNKNOWN, 0.2, "cod", "CoD 仅声明麦克风")
    if major == COD_MAJOR_PERIPHERAL:
        if minor in (COD_MINOR_PERIPHERAL_KEYBOARD, COD_MINOR_PERIPHERAL_COMBO):
            return Classification(DeviceType.KEYBOARD, 0.98, "cod", "CoD 外设 -> 键盘")
        if minor == COD_MINOR_PERIPHERAL_POINTING:
            return Classification(DeviceType.MOUSE, 0.98, "cod", "CoD 外设 -> 鼠标")
        if minor in (COD_MINOR_PERIPHERAL_JOYSTICK, COD_MINOR_PERIPHERAL_GAMEPAD):
            return Classification(DeviceType.GAMEPAD, 0.96, "cod", "CoD 外设 -> 手柄")
    if major in (COD_MAJOR_WEARABLE, COD_MAJOR_HEALTH):
        return Classification(DeviceType.WEARABLE, 0.95, "cod", "CoD 可穿戴/健康设备")
    if major == COD_MAJOR_PHONE:
        return Classification(DeviceType.PHONE, 0.92, "cod", "CoD 手机")
    if major == COD_MAJOR_TOY and minor in (0x01, 0x02, 0x03):
        return Classification(DeviceType.GAMEPAD, 0.78, "cod", "CoD 玩具/游戏设备")
    return None


def _appearance_match(appearance: Optional[int]) -> Optional[Classification]:
    if appearance is None:
        return None
    value = int(appearance)
    if value == APPEARANCE_HID_KEYBOARD:
        return Classification(DeviceType.KEYBOARD, 0.95, "appearance", "BLE Appearance HID 键盘")
    if value == APPEARANCE_HID_MOUSE or value == APPEARANCE_HID_TOUCHPAD:
        return Classification(DeviceType.MOUSE, 0.95, "appearance", "BLE Appearance HID 鼠标/触控板")
    if value in (APPEARANCE_HID_JOYSTICK, APPEARANCE_HID_GAMEPAD):
        return Classification(DeviceType.GAMEPAD, 0.95, "appearance", "BLE Appearance HID 手柄")
    if value in (APPEARANCE_WATCH, APPEARANCE_SPORTS_WATCH, APPEARANCE_SMARTWATCH,
                 APPEARANCE_HEART_RATE, APPEARANCE_RUNNING_WALKING, APPEARANCE_WEARABLE):
        return Classification(DeviceType.WEARABLE, 0.93, "appearance", "BLE Appearance 可穿戴设备")
    if value in (APPEARANCE_AUDIO_SINK, APPEARANCE_AUDIO_SOURCE, APPEARANCE_AUDIO_BOTH):
        return Classification(DeviceType.SPEAKER, 0.80, "appearance", "BLE Appearance 音频设备")
    if value == APPEARANCE_PHONE:
        return Classification(DeviceType.PHONE, 0.90, "appearance", "BLE Appearance 手机")
    return None


def _service_match(service_uuids: Sequence[object]) -> Optional[Classification]:
    if not service_uuids:
        return None
    if _matches_any_uuid(service_uuids, {SERVICE_HEADSET, SERVICE_HEADSET_ALT, SERVICE_HANDSFREE}):
        return Classification(DeviceType.HEADPHONES, 0.86, "service", "服务 UUID 为耳机/免提")
    if _matches_any_uuid(service_uuids, {SERVICE_AUDIO_SINK, SERVICE_AUDIO_SOURCE, SERVICE_A2DP}):
        return Classification(DeviceType.SPEAKER, 0.78, "service", "服务 UUID 为 A2DP 音频")
    if _matches_any_uuid(service_uuids, {SERVICE_AVRCP, SERVICE_AVRCP_TARGET,
                                        SERVICE_AVRCP_CONTROLLER}):
        return Classification(DeviceType.SPEAKER, 0.65, "service", "服务 UUID 为 AVRCP 音频控制")
    if _matches_any_uuid(service_uuids, {SERVICE_HEART_RATE, SERVICE_RSC, SERVICE_CSC,
                                        SERVICE_CYCLING_POWER, SERVICE_FITNESS_MACHINE,
                                        SERVICE_PHYSICAL_ACTIVITY}):
        return Classification(DeviceType.WEARABLE, 0.86, "service", "服务 UUID 为健康/运动数据")
    return None


def _manufacturer_match(manufacturer_data: Optional[Mapping[int, bytes]]) -> Optional[Classification]:
    if not manufacturer_data:
        return None
    apple = manufacturer_data.get(MANUFACTURER_APPLE)
    if apple and len(apple) >= 2:
        # Apple proximity-pairing payload starts with type 0x07 (AirPods) and a
        # length byte; it is only a weak hint and is never used over the name.
        if apple[0] == 0x07 and apple[1] in (0x19, 0x0E):
            return Classification(DeviceType.HEADPHONES, 0.60, "manufacturer", "Apple 耳机广播数据")
    return None


def explain_device(
    name: str = "",
    class_of_device: Optional[int] = None,
    major_device_class: Optional[int] = None,
    minor_device_class: Optional[int] = None,
    service_class: Optional[int] = None,
    ble_appearance: Optional[int] = None,
    service_uuids: Optional[Sequence[object]] = None,
    manufacturer_data: Optional[Mapping[int, bytes]] = None,
    paired: bool = False,
    connected: bool = False,
    platform: str = "",
    os_hint: Optional[str] = None,
) -> Classification:
    """Classify a device and explain which rule won.

    The paired/connected/platform arguments are accepted for API compatibility
    and future policy rules; they do not override a positive signal today.
    """
    del paired, connected, platform  # reserved for future policy tuning
    services = list(service_uuids or ())

    cod_result = _cod_match(
        class_of_device, major_device_class, minor_device_class, service_class
    )
    if cod_result is not None and cod_result.device_type is not DeviceType.UNKNOWN:
        return cod_result

    appearance_result = _appearance_match(ble_appearance)
    if appearance_result is not None:
        if appearance_result.device_type is not DeviceType.SPEAKER:
            return appearance_result
        # Audio appearance cannot distinguish headphones from speakers.
        name_result = _name_match(name)
        if name_result and name_result.device_type.group == "audio":
            return Classification(
                name_result.device_type,
                0.82,
                "appearance+name",
                "%s；名称细化为 %s" % (appearance_result.reason, name_result.device_type.label),
            )
        return appearance_result

    service_result = _service_match(services)
    if service_result is not None:
        if service_result.device_type in (DeviceType.HEADPHONES, DeviceType.SPEAKER):
            name_result = _name_match(name)
            if name_result and name_result.device_type.group == "audio":
                return Classification(
                    name_result.device_type,
                    0.84,
                    "service+name",
                    "%s；名称细化为 %s" % (service_result.reason, name_result.device_type.label),
                )
        return service_result

    hint_result = _os_hint_match(os_hint)
    if hint_result is not None:
        return hint_result

    name_result = _name_match(name)
    if name_result is not None:
        return name_result

    manufacturer_result = _manufacturer_match(manufacturer_data)
    if manufacturer_result is not None:
        return manufacturer_result

    return Classification(DeviceType.UNKNOWN, 0.1, "fallback", "无足够特征，归类为通用蓝牙设备")


def classify_device(
    name: str = "",
    class_of_device: Optional[int] = None,
    major_device_class: Optional[int] = None,
    minor_device_class: Optional[int] = None,
    service_class: Optional[int] = None,
    ble_appearance: Optional[int] = None,
    service_uuids: Optional[Sequence[object]] = None,
    manufacturer_data: Optional[Mapping[int, bytes]] = None,
    paired: bool = False,
    connected: bool = False,
    platform: str = "",
    os_hint: Optional[str] = None,
) -> DeviceType:
    """Return only the DeviceType, as required by the product specification."""
    return explain_device(
        name=name,
        class_of_device=class_of_device,
        major_device_class=major_device_class,
        minor_device_class=minor_device_class,
        service_class=service_class,
        ble_appearance=ble_appearance,
        service_uuids=service_uuids,
        manufacturer_data=manufacturer_data,
        paired=paired,
        connected=connected,
        platform=platform,
        os_hint=os_hint,
    ).device_type


def classify_from_metadata(
    name: str,
    cod: Optional[int] = None,
    appearance: Optional[int] = None,
    services: Optional[Sequence[object]] = None,
    manufacturer_data: Optional[Mapping[int, bytes]] = None,
    platform: str = "",
    os_hint: Optional[str] = None,
) -> Classification:
    return explain_device(
        name=name,
        class_of_device=cod,
        ble_appearance=appearance,
        service_uuids=services,
        manufacturer_data=manufacturer_data,
        platform=platform,
        os_hint=os_hint,
    )
