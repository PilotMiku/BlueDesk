from __future__ import annotations

import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bluedesk.controller import AppController
from bluedesk.models import ConnectionState, DeviceInfo, DeviceType, Transport
from bluedesk.platform.base import PlatformAdapter
from bluedesk.platform.parsers import parse_system_profiler_bluetooth, system_telemetry
from bluedesk.settings import SettingsStore
from bluedesk.ui.main_window import MainWindow


class TestPlatform(PlatformAdapter):
    __test__ = False

    def __init__(self):
        self.devices = []
        self.disconnected = []

    def paired_devices(self):
        return self.devices

    def system_disconnect(self, device):
        self.disconnected.append(device.address)
        return True, "已断开"


@pytest.fixture
def real_controller(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEDESK_DATA_DIR", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    platform = TestPlatform()
    settings = SettingsStore(tmp_path / "settings.json")
    settings.settings.demo_mode = True  # Legacy saved preferences must not win.
    controller = AppController(settings_store=settings, platform=platform, auto_scan=False)
    QTest.qWait(40)
    monkeypatch.setattr(controller.scan_service, "start", Mock())
    yield controller, platform
    controller.shutdown()
    app.processEvents()


def test_current_macos_named_device_records_and_real_battery():
    raw = {"SPBluetoothDataType": [{
        "controller_properties": {"controller_state": "attrib_on"},
        "device_connected": [{"OPPO Enco Air5 Pro": {
            "device_address": "AA:BB:CC:DD:EE:FF", "device_minorType": "Headset",
            "device_batteryLevelMain": "100%",
        }}],
        "device_not_connected": [{"Mouse": {
            "device_address": "11:22:33:44:55:66", "device_minorType": "Mouse",
        }}],
    }]}
    devices = parse_system_profiler_bluetooth(raw)
    assert [(d["name"], d["connected"]) for d in devices] == [
        ("OPPO Enco Air5 Pro", True), ("Mouse", False),
    ]
    assert system_telemetry(devices[0]["raw"]).battery == 100
    assert system_telemetry(devices[1]["raw"]).battery is None
    assert system_telemetry({"device_batteryLevelMain": "105%"}).battery is None


def test_normal_launch_ignores_saved_demo_mode(real_controller):
    controller, _ = real_controller
    assert not controller.demo_mode
    assert not controller.devices()


def test_exit_demo_removes_simulation_and_cancels_delayed_connection(real_controller):
    controller, _ = real_controller
    controller.load_demo_devices()
    device = controller.devices()[0]
    controller.connect_device(device.address)
    controller.use_real_devices()
    QTest.qWait(750)
    assert not controller.demo_mode
    assert not controller.devices()
    assert not controller.connections.is_connected(device.address)
    assert not controller.connections.services_for(device.address)
    assert not controller.settings.last_selected.startswith("demo:")
    controller.scan_service.start.assert_called_once()


def test_scan_button_and_mode_button_leave_demo(real_controller):
    controller, _ = real_controller
    window = MainWindow(controller)
    try:
        controller.load_demo_devices()
        assert window.demo_btn.text() == "使用真实设备"
        window.demo_btn.click()
        assert not controller.demo_mode
        assert window.demo_pill.text() == "真实设备"
        controller.load_demo_devices()
        window.scan_btn.click()
        assert not controller.demo_mode
    finally:
        window.close()


def test_system_snapshot_selects_connected_device_and_tracks_disconnect(real_controller):
    controller, _ = real_controller
    def snapshot(connected):
        return DeviceInfo(
            address="AA:BB", name="Real Headset", device_type=DeviceType.HEADPHONES,
            paired=True, connected=connected, transport=Transport.CLASSIC,
            state=ConnectionState.CONNECTED if connected else ConnectionState.DISCONNECTED,
            source="system_profiler", metadata={"system_info": {"device_batteryLevelMain": "83%"}},
        )
    controller._on_paired_loaded([snapshot(True)], "")
    assert controller.selected.address == "AA:BB"
    assert controller.telemetry_for("AA:BB").battery == 83
    assert controller.connections.is_connected("AA:BB")
    controller._on_paired_loaded([snapshot(False)], "")
    assert not controller.device("AA:BB").connected
    assert not controller.connections.is_connected("AA:BB")
    assert controller.telemetry_for("AA:BB") is None


def test_disconnect_device_connected_outside_app(real_controller):
    controller, platform = real_controller
    device = DeviceInfo(address="AA:BB", connected=True, transport=Transport.CLASSIC)
    states = []
    controller.connections.state_changed.connect(lambda address, state, message: states.append(state))
    controller.connections.disconnect_device(device)
    QTest.qWait(60)
    assert platform.disconnected == [device.address]
    assert states == [ConnectionState.DISCONNECTING.value, ConnectionState.DISCONNECTED.value]
    assert not controller.connections.is_connected(device.address)


def test_failed_disconnect_preserves_existing_connection(real_controller):
    controller, _ = real_controller
    states = []
    controller.connections.state_changed.connect(lambda address, state, message: states.append(state))
    controller.connections._on_system_result("AA:BB", False, False, "failed")
    assert controller.connections.is_connected("AA:BB")
    assert states[-1] == ConnectionState.CONNECTED.value


def test_same_name_advertisement_stays_separate_from_paired_device(real_controller):
    controller, _ = real_controller
    paired = DeviceInfo(address="AA:BB", name="Headset", paired=True,
                        transport=Transport.CLASSIC, source="system_profiler")
    controller._upsert(paired)
    controller._on_device_found(DeviceInfo(address="CB-UUID", name="Headset", rssi=-50,
                                          transport=Transport.BLE, source="bleak"))
    assert len(controller.devices()) == 2
    assert controller.device("AA:BB") is paired
    assert "ble_address" not in paired.metadata
    assert paired.transport is Transport.CLASSIC
    assert not controller.device("CB-UUID").paired


def test_same_name_system_devices_remain_distinct(real_controller):
    controller, _ = real_controller
    for address in ("AA:BB", "CC:DD"):
        controller._upsert(DeviceInfo(address=address, name="Headset", paired=True, source="system_profiler"))
    assert len(controller.devices()) == 2


def test_late_advertised_name_does_not_merge_identities(real_controller):
    controller, _ = real_controller
    paired = DeviceInfo(address="AA:BB", name="Headset", paired=True,
                        transport=Transport.CLASSIC, source="system_profiler")
    controller._upsert(paired)
    controller._on_device_found(DeviceInfo(address="CB-UUID", rssi=-50, transport=Transport.BLE, source="bleak"))
    assert len(controller.devices()) == 2
    controller._on_device_found(DeviceInfo(address="CB-UUID", name="Headset", rssi=-49,
                                          transport=Transport.BLE, source="bleak"))
    assert len(controller.devices()) == 2
    assert controller.device("CB-UUID") is not paired
    assert controller.device("CB-UUID").name == "Headset"
    assert "ble_address" not in paired.metadata


def test_scanning_before_system_enumeration_keeps_mac_and_ble_identity(real_controller):
    controller, _ = real_controller
    controller._on_device_found(DeviceInfo(address="CB-UUID", name="Headset", rssi=-50,
                                          transport=Transport.BLE, source="bleak"))
    controller._on_paired_loaded([DeviceInfo(address="AA:BB", name="Headset", paired=True, connected=True,
        state=ConnectionState.CONNECTED, source="system_profiler", transport=Transport.CLASSIC,
        metadata={"system_info": {"device_batteryLevelMain": "83%"}})], "")
    assert len(controller.devices()) == 2
    assert controller.device("AA:BB") is not controller.device("CB-UUID")
    assert controller.telemetry_for("AA:BB").battery == 83
    assert not controller.device("CB-UUID").paired


def test_startup_scan_does_not_override_user_switching_to_demo(real_controller):
    controller, _ = real_controller
    controller.load_demo_devices()
    controller._start_initial_scan()
    controller.scan_service.start.assert_not_called()
    assert controller.demo_mode


def test_rapid_mode_switch_does_not_reuse_old_demo_auto_connect(real_controller):
    controller, _ = real_controller
    controller.load_demo_devices(auto_connect=True)
    controller.use_real_devices(scan=False)
    controller.load_demo_devices(auto_connect=True)
    QTest.qWait(1450)
    assert controller.demo_mode
    assert sum(controller.connections.is_connected(d.address) for d in controller.devices()) == 1


def test_native_macos_connection_uses_system_address_and_checks_result(monkeypatch):
    from bluedesk.platform import macos

    connected = [False]
    native = Mock()
    native.isConnected.side_effect = lambda: connected[0]
    def change_state(value):
        connected[0] = value
        return 0
    native.openConnection.side_effect = lambda: change_state(True)
    native.closeConnection.side_effect = lambda: change_state(False)
    bridge = Mock()
    bridge.deviceWithAddressString_.return_value = native
    monkeypatch.setattr(macos, "IOBluetoothDevice", bridge)
    platform = macos.MacOSPlatform()
    device = DeviceInfo(address="AA:BB:CC:DD:EE:FF", metadata={"system_address": "UNTRUSTED"})
    assert platform.system_connect(device)[0]
    bridge.deviceWithAddressString_.assert_called_with("AA:BB:CC:DD:EE:FF")
    assert platform.system_disconnect(device)[0]
    assert not connected[0]
    native.openConnection.side_effect = None
    native.openConnection.return_value = 5
    assert not platform.system_connect(device)[0]
    native.openConnection.return_value = 0
    assert not platform.system_connect(device)[0]  # OS has not confirmed a link.
