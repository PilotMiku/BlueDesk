from __future__ import annotations

import json

from bluedesk.models import ConnectionState, DeviceType, Transport
from bluedesk.platform.parsers import (
    build_paired_device,
    extract_mac_from_instance_id,
    parse_blueutil_paired,
    parse_system_profiler_bluetooth,
    parse_windows_pnp_devices,
)


OLD_PROFILER = {
    "SPBluetoothDataType": [
        {
            "controller_properties": {"controller_address": "AA:BB:CC:DD:EE:FF"},
            "devices_list": [
                {
                    "device_address": "11:22:33:44:55:66",
                    "device_name": "WH-1000XM5",
                    "device_minorType": "Headphones",
                    "device_connected": "attrib_Yes",
                    "device_paired": "attrib_Yes",
                },
                {
                    "device_address": "77:88:99:AA:BB:CC",
                    "device_name": "MX Keys",
                    "device_minorType": "Keyboard",
                    "device_connected": "attrib_No",
                    "device_paired": "attrib_Yes",
                },
                {
                    "device_address": "99:88:77:66:55:44",
                    "device_name": "Known Not Paired",
                    "device_connected": "attrib_No",
                    "device_paired": "attrib_No",
                },
            ],
        }
    ]
}


def test_system_profiler_old_schema():
    items = parse_system_profiler_bluetooth(OLD_PROFILER)
    assert len(items) == 3
    headphones = items[0]
    assert headphones["name"] == "WH-1000XM5"
    assert headphones["address"] == "11:22:33:44:55:66"
    assert headphones["connected"] is True
    assert headphones["paired"] is True
    assert items[2]["paired"] is False


def test_system_profiler_new_schema_and_string_input():
    raw = {
        "SPBluetoothDataType": [
            {
                "device_connected": [
                    {"device_name": "AirPods Pro", "device_address": "AA:AA:AA:AA:AA:AA"}
                ],
                "device_not_connected": [
                    {"device_name": "MX Master", "device_address": "BB:BB:BB:BB:BB:BB"}
                ],
            }
        ]
    }
    items = parse_system_profiler_bluetooth(json.dumps(raw))
    assert [item["name"] for item in items] == ["AirPods Pro", "MX Master"]
    assert items[0]["connected"] is True
    assert items[1]["connected"] is False


def test_blueutil_pairs():
    raw = [
        {"address": "aa:bb:cc:dd:ee:ff", "name": "SoundLink", "connected": True, "paired": True}
    ]
    items = parse_blueutil_paired(raw)
    assert items[0]["address"] == "aa:bb:cc:dd:ee:ff"
    assert items[0]["connected"] is True


def test_windows_pnp_parsing():
    raw = [
        {
            "FriendlyName": "MX Master 3S",
            "InstanceId": r"BTHLE\DEV_AABBCCDDEEFF\7&1234&0&0000",
            "Status": "OK",
            "Present": True,
        },
        {
            "FriendlyName": "WH-1000XM5",
            "InstanceId": r"BTHENUM\DEV_112233445566\7&ABC&0&0000",
            "Status": "OK",
            "Present": True,
        },
        {"FriendlyName": "Not Bluetooth", "InstanceId": r"USB\VID_1234", "Status": "OK"},
    ]
    items = parse_windows_pnp_devices(raw)
    assert len(items) == 2
    assert items[0]["address"] == "AA:BB:CC:DD:EE:FF"
    assert items[0]["transport"] is Transport.BLE
    assert items[1]["transport"] is Transport.CLASSIC


def test_extract_mac_variants():
    assert extract_mac_from_instance_id(r"BTHENUM\DEV_AABBCCDDEEFF\x") == "AA:BB:CC:DD:EE:FF"
    assert extract_mac_from_instance_id("BTHENUM&112233445566") == "11:22:33:44:55:66"
    assert extract_mac_from_instance_id(r"USB\VID_1234") is None


def test_build_paired_device():
    device = build_paired_device(
        "Sony WH-1000XM5",
        "AA:BB:CC:DD:EE:FF",
        minor_type="Headphones",
        connected=True,
        platform="macos",
        source="system_profiler",
    )
    assert device.device_type is DeviceType.HEADPHONES
    assert device.state is ConnectionState.CONNECTED
    assert device.connected is True
