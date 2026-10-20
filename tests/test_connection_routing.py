from __future__ import annotations

from bluedesk.connection_manager import ConnectionManager, short_uuid
from bluedesk.models import DeviceInfo, DeviceType, Transport


def test_ble_routing_audio_uses_system():
    audio = DeviceInfo(
        address="macos:abc",
        device_type=DeviceType.HEADPHONES,
        transport=Transport.DUAL,
        metadata={"ble_address": "CB-UUID"},
    )
    assert ConnectionManager._should_use_ble(audio) is False


def test_ble_routing_hid_uses_gatt():
    mouse = DeviceInfo(
        address="macos:abc",
        device_type=DeviceType.MOUSE,
        transport=Transport.DUAL,
        metadata={"ble_address": "CB-UUID"},
    )
    assert ConnectionManager._should_use_ble(mouse) is True


def test_ble_routing_native_ble():
    device = DeviceInfo(address="CB-UUID", transport=Transport.BLE, source="bleak")
    assert ConnectionManager._should_use_ble(device) is True


def test_short_uuid():
    assert short_uuid("00002a19-0000-1000-8000-00805f9b34fb") == "2a19"
    assert short_uuid("0000ffe1-0000-1000-8000-00805f9b34fb") == "ffe1"
