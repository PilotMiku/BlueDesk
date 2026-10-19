from __future__ import annotations

import pytest

from bluedeck.classifier import (
    Classification,
    classify_device,
    decode_class_of_device,
    explain_device,
    normalize_uuid,
    uuid16,
)
from bluedeck.models import DeviceType


def cod(major: int, minor: int = 0, services: int = 0) -> int:
    return (services << 13) | (major << 8) | (minor << 2)


def test_decode_cod():
    value = cod(0x04, 0x05, 0x01)
    major, minor, services = decode_class_of_device(value)
    assert major == 0x04
    assert minor == 0x05
    assert services == 0x01


@pytest.mark.parametrize(
    "major,minor,expected",
    [
        (0x04, 0x01, DeviceType.HEADPHONES),
        (0x04, 0x02, DeviceType.HEADPHONES),
        (0x04, 0x05, DeviceType.HEADPHONES),
        (0x04, 0x04, DeviceType.SPEAKER),
        (0x04, 0x06, DeviceType.SPEAKER),
        (0x04, 0x07, DeviceType.CAR_AUDIO),
        (0x05, 0x10, DeviceType.KEYBOARD),
        (0x05, 0x20, DeviceType.MOUSE),
        (0x05, 0x30, DeviceType.KEYBOARD),
        (0x05, 0x08, DeviceType.GAMEPAD),
        (0x07, 0x00, DeviceType.WEARABLE),
        (0x02, 0x00, DeviceType.PHONE),
    ],
)
def test_cod_priority(major, minor, expected):
    assert classify_device(name="Totally Ambiguous", class_of_device=cod(major, minor)) is expected


def test_cod_beats_name():
    result = classify_device(
        name="WH-1000XM5 Headphones",
        class_of_device=cod(0x05, 0x20),
    )
    assert result is DeviceType.MOUSE


@pytest.mark.parametrize(
    "appearance,expected",
    [
        (0x03C1, DeviceType.KEYBOARD),
        (0x03C2, DeviceType.MOUSE),
        (0x03C4, DeviceType.GAMEPAD),
        (0x00C2, DeviceType.WEARABLE),
        (0x0340, DeviceType.WEARABLE),
        (0x0840, DeviceType.SPEAKER),
        (0x0040, DeviceType.PHONE),
    ],
)
def test_ble_appearance(appearance, expected):
    assert classify_device(ble_appearance=appearance) is expected


def test_appearance_beats_name():
    assert classify_device(name="Keyboard", ble_appearance=0x03C2) is DeviceType.MOUSE


def test_audio_appearance_refined_by_name():
    assert classify_device(name="AirPods Pro", ble_appearance=0x0840) is DeviceType.HEADPHONES
    assert classify_device(name="SoundLink Flex", ble_appearance=0x0840) is DeviceType.SPEAKER


def test_service_heart_rate():
    uid = "0000180d-0000-1000-8000-00805f9b34fb"
    assert classify_device(service_uuids=[uid]) is DeviceType.WEARABLE


def test_service_handsfree_with_audio_name_refinement():
    uid = "0000111e-0000-1000-8000-00805f9b34fb"
    assert classify_device(name="Mystery Headset", service_uuids=[uid]) is DeviceType.HEADPHONES
    # A speakerphone can expose HFP; the product name refines that ambiguity.
    assert classify_device(name="Bose SoundLink", service_uuids=[uid]) is DeviceType.SPEAKER


def test_a2dp_service_refined_by_name():
    uid = "0000110b-0000-1000-8000-00805f9b34fb"
    assert classify_device(name="AirPods", service_uuids=[uid]) is DeviceType.HEADPHONES
    assert classify_device(name="JBL Flip 6", service_uuids=[uid]) is DeviceType.SPEAKER


@pytest.mark.parametrize(
    "name,expected",
    [
        ("WH-1000XM5", DeviceType.HEADPHONES),
        ("LE_WH-1000XM5", DeviceType.HEADPHONES),
        ("LE-Bose Revolve+ II SoundL", DeviceType.SPEAKER),
        ("UGREEN HiTune S5", DeviceType.HEADPHONES),
        ("Jabra Elite 85t", DeviceType.HEADPHONES),
        ("SoundLink Flex", DeviceType.SPEAKER),
        ("JBL Flip 6", DeviceType.SPEAKER),
        ("MX Master 3S", DeviceType.MOUSE),
        ("MX Keys S", DeviceType.KEYBOARD),
        ("DualSense Wireless Controller", DeviceType.GAMEPAD),
        ("Mi Smart Band 8", DeviceType.WEARABLE),
        ("Apple Watch", DeviceType.WEARABLE),
        ("Tesla Model 3", DeviceType.CAR_AUDIO),
        ("Galaxy S24", DeviceType.PHONE),
        ("BT-5.3 Module", DeviceType.UNKNOWN),
    ],
)
def test_name_heuristics(name, expected):
    assert classify_device(name=name) is expected


def test_os_hint():
    assert classify_device(name="Mystery", os_hint="Headphones") is DeviceType.HEADPHONES
    assert classify_device(name="Mystery", os_hint="鼠标") is DeviceType.MOUSE


def test_manufacturer_apple_hint():
    assert classify_device(name="Mystery", manufacturer_data={0x004C: b"\x07\x19\x01\x02"}) is DeviceType.HEADPHONES


def test_unknown_and_explanation():
    result = explain_device(name="BT-5.3 Module")
    assert isinstance(result, Classification)
    assert result.device_type is DeviceType.UNKNOWN
    assert result.confidence < 0.2


def test_uuid_normalisation():
    full = "0000180f-0000-1000-8000-00805f9b34fb"
    assert uuid16(full) == "180f"
    assert uuid16("0x180F") == "180f"
    assert normalize_uuid(full).startswith("0000180f")


def test_service_class_accepted():
    value = cod(0x04, 0x05, services=0x01)
    result = explain_device(name="", class_of_device=value, service_class=0x40)
    assert result.device_type is DeviceType.HEADPHONES
