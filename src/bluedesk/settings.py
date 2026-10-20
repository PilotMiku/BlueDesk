"""Persistent settings and the in-memory/file log store."""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import DeviceInfo, LogEntry

APP_DIR_NAME = "BlueDesk"
SETTINGS_FILE = "settings.json"
LOG_FILE = "bluedeck.jsonl"


def app_data_dir() -> Path:
    override = os.environ.get("BLUEDESK_DATA_DIR")
    if override:
        return Path(override).expanduser()
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / APP_DIR_NAME


@dataclass
class AppSettings:
    default_device: str = ""
    last_selected: str = ""
    auto_scan: bool = True
    demo_mode: bool = False
    recent_devices: List[Dict[str, Any]] = field(default_factory=list)
    scan_timeout_seconds: int = 0
    last_filter: str = "all"
    window_geometry: str = ""

    def add_recent(self, device: DeviceInfo) -> None:
        data = device.to_dict()
        self.recent_devices = [
            item for item in self.recent_devices if item.get("address") != device.address
        ]
        self.recent_devices.insert(0, data)
        self.recent_devices = self.recent_devices[:12]


class SettingsStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else app_data_dir() / SETTINGS_FILE
        self.settings = AppSettings()
        self.last_error = ""
        self.load()

    def load(self) -> AppSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            self.settings = AppSettings()
            return self.settings
        self.settings = AppSettings(
            default_device=str(raw.get("default_device") or ""),
            last_selected=str(raw.get("last_selected") or ""),
            auto_scan=bool(raw.get("auto_scan", True)),
            demo_mode=bool(raw.get("demo_mode", False)),
            recent_devices=list(raw.get("recent_devices") or []),
            scan_timeout_seconds=int(raw.get("scan_timeout_seconds") or 0),
            last_filter=str(raw.get("last_filter") or "all"),
            window_geometry=str(raw.get("window_geometry") or ""),
        )
        return self.settings

    def save(self) -> None:
        try:
            self._save_atomic()
        except OSError as exc:
            self.last_error = str(exc)

    def _save_atomic(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "default_device": self.settings.default_device,
            "last_selected": self.settings.last_selected,
            "auto_scan": self.settings.auto_scan,
            "demo_mode": self.settings.demo_mode,
            "recent_devices": self.settings.recent_devices,
            "scan_timeout_seconds": self.settings.scan_timeout_seconds,
            "last_filter": self.settings.last_filter,
            "window_geometry": self.settings.window_geometry,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def remember_device(self, device: DeviceInfo) -> None:
        self.settings.add_recent(device)

    def set_default(self, address: str) -> None:
        self.settings.default_device = address

    def recent_devices(self) -> List[DeviceInfo]:
        result: List[DeviceInfo] = []
        for item in self.settings.recent_devices:
            try:
                result.append(DeviceInfo.from_dict(item))
            except (TypeError, ValueError):
                continue
        return result


class LogStore:
    """Thread-safe ring buffer that also mirrors entries to JSON Lines."""

    def __init__(self, path: Optional[Path] = None, max_entries: int = 5000) -> None:
        self.path = Path(path) if path else app_data_dir() / LOG_FILE
        self.max_entries = max_entries
        self._entries: List[LogEntry] = []
        self._lock = threading.Lock()

    @property
    def entries(self) -> List[LogEntry]:
        with self._lock:
            return list(self._entries)

    def add(self, entry: LogEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries :]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
        try:
            self.path.unlink()
        except OSError:
            pass

    def export_json(self, target: Path) -> None:
        payload = {
            "app": "BlueDesk",
            "exported_at": time.time(),
            "entries": [entry.to_dict() for entry in self.entries],
        }
        Path(target).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_csv(self, target: Path) -> None:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp", "iso_time", "level", "category", "address", "message", "data"])
        for entry in self.entries:
            writer.writerow(
                [
                    entry.timestamp,
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp)),
                    entry.level,
                    entry.category,
                    entry.address,
                    entry.message,
                    entry.data,
                ]
            )
        Path(target).write_text(buffer.getvalue(), encoding="utf-8")

    def export_text(self, target: Path) -> None:
        lines = []
        for entry in self.entries:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            lines.append("[%s] %-5s %-8s %s" % (stamp, entry.level.upper(), entry.category, entry.message))
        Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
