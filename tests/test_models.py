from __future__ import annotations

from bluedesk.models import (
    ConnectionState,
    DeviceInfo,
    DeviceType,
    Telemetry,
    Transport,
    capabilities_for,
    dedupe_devices,
    rssi_to_bars,
)


def test_device_round_trip():
    device = DeviceInfo(
        address="AA:BB",
        name="Test",
        device_type=DeviceType.MOUSE,
        transport=Transport.BLE,
        rssi=-55,
        manufacturer_data={0x004C: b"\x01\x02"},
    )
    loaded = DeviceInfo.from_dict(device.to_dict())
    assert loaded.name == "Test"
    assert loaded.device_type is DeviceType.MOUSE
    assert loaded.manufacturer_data[0x004C] == b"\x01\x02"


def test_merge_and_state():
    existing = DeviceInfo(address="aa", name="", device_type=DeviceType.UNKNOWN)
    incoming = DeviceInfo(
        address="aa",
        name="MX Master",
        device_type=DeviceType.MOUSE,
        confidence=0.9,
        rssi=-60,
        paired=True,
        transport=Transport.BLE,
    )
    assert existing.merge(incoming)
    assert existing.name == "MX Master"
    assert existing.device_type is DeviceType.MOUSE
    existing.mark_connected()
    assert existing.state is ConnectionState.CONNECTED
    existing.mark_disconnected(failed=True)
    assert existing.state is ConnectionState.FAILED
    assert existing.connected is False


def test_dedupe():
    devices = [DeviceInfo(address="AA", name="One"), DeviceInfo(address="aa", name="Two")]
    merged = dedupe_devices(devices)
    assert len(merged) == 1


def test_capabilities_and_rssi():
    assert capabilities_for(DeviceType.HEADPHONES).volume
    assert capabilities_for(DeviceType.MOUSE).dpi
    assert capabilities_for(DeviceType.UNKNOWN).gatt_browser
    assert rssi_to_bars(-50) == 4
    assert rssi_to_bars(-85) == 1
    assert rssi_to_bars(None) == 0


def test_telemetry_merge():
    a = Telemetry(battery=50)
    b = Telemetry(battery=60, firmware="1.2.3", heart_rate=70)
    a.merge(b)
    assert a.battery == 60
    assert a.firmware == "1.2.3"
    assert a.heart_rate == 70
