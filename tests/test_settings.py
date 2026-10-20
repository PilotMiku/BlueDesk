from __future__ import annotations

import json

from bluedesk.models import DeviceInfo, DeviceType, LogEntry
from bluedesk.settings import LogStore, SettingsStore


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.settings.auto_scan = False
    store.settings.default_device = "AA:BB"
    device = DeviceInfo(address="AA:BB", name="Test Headset", device_type=DeviceType.HEADPHONES)
    store.remember_device(device)
    store.save()
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["default_device"] == "AA:BB"
    assert raw["auto_scan"] is False
    loaded = SettingsStore(path)
    assert loaded.settings.default_device == "AA:BB"
    assert loaded.recent_devices()[0].name == "Test Headset"


def test_settings_save_survives_unwritable_path(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    store = SettingsStore(blocker / "settings.json")
    store.save()  # must not raise
    assert store.last_error


def test_log_store_exports(tmp_path):
    path = tmp_path / "logs.jsonl"
    store = LogStore(path)
    store.add(LogEntry(level="INFO", message="hello", category="test"))
    store.add(LogEntry(level="DATA", message="01 02", category="data", data="01 02"))
    assert len(store.entries) == 2
    csv_path = tmp_path / "out.csv"
    json_path = tmp_path / "out.json"
    text_path = tmp_path / "out.txt"
    store.export_csv(csv_path)
    store.export_json(json_path)
    store.export_text(text_path)
    assert "hello" in csv_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["entries"][0]["message"] == "hello"
    assert "hello" in text_path.read_text(encoding="utf-8")
