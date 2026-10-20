from __future__ import annotations

import csv
import json
import os
import stat
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from bluedesk import connection_manager
from bluedesk.controller import AppController
from bluedesk.models import ConnectionState, DeviceInfo, DeviceType, LogEntry, Transport
from bluedesk.platform.base import PlatformAdapter
from bluedesk.scan_service import ScanService
from bluedesk.security import MAX_DEVICES, MAX_GATT_BYTES, MAX_OUTPUT_BLOCKS, NEARBY_TTL, RateLimiter
from bluedesk.settings import LogStore, SettingsStore
from bluedesk.ui.device_list import DeviceCard
from bluedesk.ui.gatt_browser import GattBrowser


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEDESK_DATA_DIR", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    controller = AppController(platform=PlatformAdapter(), auto_scan=False)
    yield controller
    controller.shutdown()
    app.processEvents()


def test_same_name_broadcast_cannot_redirect_paired_device(controller):
    paired = DeviceInfo(address="SYSTEM-MOUSE", name="Audit Mouse", paired=True,
        transport=Transport.CLASSIC, source="system_profiler", device_type=DeviceType.MOUSE)
    controller._upsert(paired)
    controller._on_device_found(DeviceInfo(address="IMPOSTOR", name="Audit Mouse", transport=Transport.BLE,
        source="bleak", paired=True, connected=True,
        metadata={"system_address": "SYSTEM-MOUSE", "ble_address": "IMPOSTOR", "vendor_protocol": "example-dpi"}))
    assert controller.device("SYSTEM-MOUSE") is paired
    assert paired.transport is Transport.CLASSIC
    assert not controller.device("IMPOSTOR").paired
    assert not controller.device("IMPOSTOR").connected
    assert "vendor_protocol" not in controller.device("IMPOSTOR").metadata
    assert not controller.connections._should_use_ble(paired)


@pytest.mark.asyncio
async def test_old_alias_cannot_redirect_ble_connection(controller, monkeypatch):
    targets = []
    class Client:
        def __init__(self, address, **kwargs):
            targets.append(address)

        async def connect(self):
            raise RuntimeError("No hardware used in this test")

        async def disconnect(self):
            pass
    monkeypatch.setattr(connection_manager, "BleakClient", Client)
    await controller.connections._connect_ble(DeviceInfo(address="EXPLICIT-TARGET", metadata={"ble_address": "IMPOSTOR"}))
    assert targets == ["EXPLICIT-TARGET"]


def test_gatt_connection_is_not_treated_as_system_pairing(controller):
    controller._upsert(DeviceInfo(address="BLE-TARGET", transport=Transport.BLE))
    controller._on_connection_state("BLE-TARGET", ConnectionState.CONNECTED.value, "connected")
    assert controller.device("BLE-TARGET").connected
    assert not controller.device("BLE-TARGET").paired


def test_device_capacity_and_system_priority(controller):
    for index in range(MAX_DEVICES + 100):
        controller._on_device_found(DeviceInfo(address="nearby-%d" % index, source="bleak"))
    assert len(controller.devices()) == MAX_DEVICES
    paired = DeviceInfo(address="SYSTEM", paired=True)
    controller._upsert(paired)
    assert len(controller.devices()) == MAX_DEVICES
    assert controller.device("SYSTEM") is paired


def test_stale_advertisements_expire_without_removing_selection_or_pairing(controller):
    old = time.time() - NEARBY_TTL - 1
    for address in ("expired", "selected", "paired"):
        controller._upsert(DeviceInfo(address=address, last_seen=old, paired=address == "paired"))
    controller.select("selected")
    controller._prune_nearby()
    assert controller.device("expired") is None
    assert controller.selected.address == "selected"
    assert controller.device("paired") is not None


def test_scan_rate_is_limited_before_qt_signals():
    service = ScanService(None)
    emitted = []
    service.device_found.connect(emitted.append)
    for index in range(1000):
        service._on_detection(SimpleNamespace(address="scan-%d" % index, name="name"))
    assert 0 < len(emitted) <= 100


def test_advertisement_fields_are_bounded():
    service = ScanService(None)
    emitted = []
    service.device_found.connect(emitted.append)
    service._on_detection(SimpleNamespace(address="scan", name="x" * 10000), SimpleNamespace(
        manufacturer_data={i: b"x" * 1000 for i in range(100)}, service_uuids=["uuid"] * 1000))
    assert len(emitted[0].name) <= 256
    assert len(emitted[0].service_uuids) <= 64
    assert sum(map(len, emitted[0].manufacturer_data.values())) <= 16 * 512


def test_notification_limit_and_oversized_packet_rejection(controller):
    manager = controller.connections
    received = []
    manager.value_received.connect(lambda *args: received.append(args))
    for _ in range(1000):
        manager._receive_notification("target", "uuid", b"payload")
    assert 0 < len(received) <= 20
    received.clear()
    manager._receive_notification("another", "uuid", b"x" * (MAX_GATT_BYTES + 1))
    assert not received


def test_write_limit_prevents_submission(controller):
    results = []
    controller.connections.operation_finished.connect(lambda *args: results.append(args))
    controller.connections.write_characteristic("target", "uuid", b"x" * (MAX_GATT_BYTES + 1))
    assert results[-1][2] is False
    assert "512" in results[-1][1]


@pytest.mark.asyncio
async def test_oversized_read_and_telemetry_value_is_rejected(controller):
    class Client:
        async def read_gatt_char(self, uuid):
            return b"x" * (MAX_GATT_BYTES + 1)
    with pytest.raises(ValueError, match="512"):
        await controller.connections._read_limited(Client(), "uuid")


def test_excessive_gatt_services_are_rejected(controller):
    service = SimpleNamespace(uuid="0000180f-0000-1000-8000-00805f9b34fb", characteristics=[])
    with pytest.raises(ValueError, match="服务数量"):
        controller.connections._extract_services(SimpleNamespace(services=[service] * 1000))


def test_gatt_output_is_plain_text_and_bounded(controller):
    browser = GattBrowser(controller)
    device = DeviceInfo(address="target", transport=Transport.BLE)
    browser.set_device(device, [])
    for _ in range(300):
        browser._on_value("target", "uuid", b"<b>MARKER</b>", "notify")
    assert "<b>MARKER</b>" in browser.output.toPlainText()
    assert browser.output.document().blockCount() <= MAX_OUTPUT_BLOCKS


def test_device_name_cannot_render_html(controller):
    card = DeviceCard(DeviceInfo(address="target", name="<b>MARKER</b>"))
    name = next(label for label in card.findChildren(QLabel) if label.text() == "<b>MARKER</b>")
    assert name.textFormat() == Qt.PlainText


def test_rate_limiter_has_bounded_state():
    limiter = RateLimiter(2, max_keys=3)
    assert limiter.allow("first", now=0)
    assert limiter.allow("first", now=0)
    assert not limiter.allow("first", now=0)
    assert limiter.allow("first", now=2)
    for index in range(50):
        limiter.allow(str(index), now=2)
    assert len(limiter._windows) == 3


def test_logs_are_private_redacted_and_rotated(tmp_path):
    store = LogStore(tmp_path / "log.jsonl", max_entries=3, max_bytes=1024, backups=2)
    for _ in range(40):
        store.add(LogEntry(level="DATA", category="data", address="AA:BB:CC:DD:EE:FF",
            message="secret-device-and-content", data="DE AD BE EF"))
    assert len(store.entries) == 3
    paths = list(tmp_path.glob("log.jsonl*"))
    assert len(paths) == 3
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        assert path.stat().st_size <= 1024
        assert "AA:BB:CC:DD:EE:FF" not in raw
        assert "secret-device-and-content" not in raw
        assert "DE AD BE EF" not in raw
        for line in raw.splitlines():
            assert json.loads(line)["privacy_version"] == 1
        if os.name == "posix":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_legacy_logs_and_backups_are_sanitized(tmp_path):
    path = tmp_path / "log.jsonl"
    legacy = json.dumps({"privacy_version": 1, "time": 1, "level": "DATA", "category": "data",
        "address": "SECRET-ADDRESS", "message": "PRIVATE MESSAGE", "data": "SECRET-PAYLOAD"}) + "\n"
    path.write_text(legacy, encoding="utf-8")
    path.with_name("log.jsonl.1").write_text(legacy, encoding="utf-8")
    store = LogStore(path)
    store.add(LogEntry(level="INFO", message="new"))
    for p in tmp_path.glob("log.jsonl*"):
        content = p.read_text(encoding="utf-8")
        assert not any(secret in content for secret in ("SECRET-ADDRESS", "PRIVATE MESSAGE", "SECRET-PAYLOAD"))


@pytest.mark.parametrize("kind", ["json", "csv", "text"])
def test_exports_default_to_redaction_and_require_explicit_sensitive_option(tmp_path, kind):
    store = LogStore(tmp_path / "log.jsonl")
    store.add(LogEntry(level="DATA", message="PRIVATE-MESSAGE", address="PRIVATE-ADDRESS", data="PRIVATE-DATA"))
    export = getattr(store, "export_" + kind)
    path = tmp_path / ("export." + kind)
    export(path)
    assert "PRIVATE-" not in path.read_text(encoding="utf-8")
    export(path, include_sensitive=True)
    assert "PRIVATE-MESSAGE" in path.read_text(encoding="utf-8")
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_sensitive_csv_export_neutralizes_formulas(tmp_path):
    store = LogStore(tmp_path / "log.jsonl")
    store.add(LogEntry(level="INFO", message='=HYPERLINK("https://example.invalid")'))
    path = tmp_path / "out.csv"
    store.export_csv(path, include_sensitive=True)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 2
    assert rows[1][5].startswith("'=")


def test_csv_export_preserves_records_with_windows_newline_translation(tmp_path, monkeypatch):
    original_fdopen = os.fdopen

    def windows_fdopen(fd, mode="r", *args, **kwargs):
        # Emulate Windows' default translation even when this test runs on macOS.
        if "b" not in mode:
            kwargs.setdefault("newline", "\r\n")
        return original_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", windows_fdopen)
    store = LogStore(tmp_path / "log.jsonl")
    message = '中文消息，包含 "引号"\n第二行'
    store.add(LogEntry(level="INFO", message=message))
    path = tmp_path / "out.csv"
    store.export_csv(path, include_sensitive=True)

    assert b"\r\r\n" not in path.read_bytes()
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 2
    assert len(rows[1]) == len(rows[0]) == 7
    assert rows[1][5] == message


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink semantics")
def test_log_symlink_cannot_overwrite_target(tmp_path):
    target = tmp_path / "important"
    target.write_text("untouched", encoding="utf-8")
    path = tmp_path / "log.jsonl"
    path.symlink_to(target)
    store = LogStore(path)
    store.add(LogEntry(level="INFO", message="entry"))
    assert target.read_text(encoding="utf-8") == "untouched"
    assert len(store.entries) == 1


def test_saved_device_does_not_persist_payloads_or_aliases(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.remember_device(DeviceInfo(address="target", name="name", manufacturer_data={1: b"SECRET"},
        metadata={"ble_address": "IMPOSTOR", "system_info": {"serial": "PRIVATE"}}))
    store.save()
    raw = store.path.read_text(encoding="utf-8")
    assert not any(secret in raw for secret in ("SECRET", "IMPOSTOR", "PRIVATE", "534543524554"))
    assert store.recent_devices()[0].address == "target"
