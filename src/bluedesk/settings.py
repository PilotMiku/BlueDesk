"""Persistent settings and the in-memory/file log store."""
from __future__ import annotations

import csv
import io
import hashlib
import hmac
import secrets
import stat
import json
import os
import platform
import tempfile
import threading
import time
from dataclasses import dataclass, field, replace
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
        # Persist only the identity needed for reconnection, not advertisement
        # payloads, system serial numbers, or old connection aliases.
        data = {key: data[key] for key in (
            "address", "name", "device_type", "transport", "paired", "platform", "source",
            "confidence", "classification_source", "classification_reason",
        )}
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
            if self.path.stat().st_size > 256 * 1024:
                raise ValueError("Settings file is too large")
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Settings must be an object")
        except (OSError, ValueError, TypeError):
            self.settings = AppSettings()
            return self.settings
        self.settings = AppSettings(
            default_device=str(raw.get("default_device") or ""),
            last_selected=str(raw.get("last_selected") or ""),
            auto_scan=bool(raw.get("auto_scan", True)),
            demo_mode=bool(raw.get("demo_mode", False)),
            recent_devices=[],
            scan_timeout_seconds=int(raw.get("scan_timeout_seconds") or 0),
            last_filter=str(raw.get("last_filter") or "all"),
            window_geometry=str(raw.get("window_geometry") or ""),
        )
        recent = raw.get("recent_devices")
        if isinstance(recent, list):
            for item in reversed(recent[:12]):
                try:
                    self.settings.add_recent(DeviceInfo.from_dict(item))
                except (TypeError, ValueError, AttributeError):
                    continue
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


def private_write(path: Path, text: str) -> None:
    """Atomically write a user-only file without following a destination symlink."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="bluedesk-", dir=path.parent)
    try:
        # Preserve csv.writer's CRLF verbatim. Windows text-mode translation
        # would turn it into CRCRLF and introduce empty CSV records.
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class LogStore:
    """Bounded session detail; redacted, rotating, private persistent logs."""

    def __init__(self, path: Optional[Path] = None, max_entries: int = 1000,
                 max_bytes: int = 1024 * 1024, backups: int = 2) -> None:
        self.path = Path(path) if path else app_data_dir() / LOG_FILE
        self.max_entries = max(1, min(max_entries, 5000))
        self.max_bytes = max(1024, max_bytes)
        self.backups = max(0, min(backups, 5))
        self._entries: List[LogEntry] = []
        self._lock = threading.Lock()
        self._salt = secrets.token_bytes(32)
        self._prepared = False

    @property
    def entries(self) -> List[LogEntry]:
        with self._lock:
            return list(self._entries)

    def _record(self, entry: LogEntry, include_sensitive: bool = False) -> dict:
        if include_sensitive:
            return entry.to_dict()
        category = entry.category if entry.category in {
            "app", "scan", "connect", "gatt", "data", "audio", "platform",
            "permission", "demo", "log",
        } else "other"
        address = ""
        if entry.address:
            address = "device-" + hmac.new(self._salt, entry.address.encode(), hashlib.sha256).hexdigest()[:12]
        return {
            "privacy_version": 1, "time": entry.timestamp,
            "level": entry.level if entry.level in {"INFO", "DEBUG", "WARN", "ERROR", "DATA"} else "INFO",
            "category": category, "address": address,
            "message": "事件详情已隐藏，仅保留时间、级别和分类", "data": "",
        }

    def _file(self, index: int) -> Path:
        return self.path if index == 0 else self.path.with_name(self.path.name + ".%d" % index)

    def _prepare(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        for index in range(self.backups + 1):
            path = self._file(index)
            if not path.exists():
                continue
            if path.is_symlink():
                raise OSError("Refusing a symlink as a log file")
            if not stat.S_ISREG(path.stat().st_mode):
                raise OSError("Refusing a non-regular log file")
            with path.open("rb") as handle:
                size = handle.seek(0, os.SEEK_END)
                offset = max(0, size - self.max_bytes)
                handle.seek(offset)
                if offset:
                    handle.readline(self.max_bytes + 1)
                tail = handle.read(self.max_bytes)
            records = []
            for line in tail.splitlines():
                try:
                    record = json.loads(line)
                    # Rebuild even already-redacted records: the marker is not
                    # trusted input and must never bypass sanitisation.
                    entry = LogEntry(level=str(record.get("level", "INFO")),
                        message="", address=str(record.get("address", ""))[:128],
                        category=str(record.get("category", "app"))[:64],
                        timestamp=float(record.get("time", 0)))
                    records.append(json.dumps(self._record(entry), ensure_ascii=False) + "\n")
                except (ValueError, TypeError, AttributeError):
                    continue
            retained = []
            budget = 0
            for record in reversed(records):
                size = len(record.encode("utf-8"))
                if budget + size > self.max_bytes:
                    break
                retained.append(record)
                budget += size
            private_write(path, "".join(reversed(retained)))
        self._prepared = True

    def add(self, entry: LogEntry) -> LogEntry:
        entry = replace(entry, message=str(entry.message)[:4096], data=str(entry.data)[:1536],
                        address=str(entry.address)[:128], category=str(entry.category)[:64], level=str(entry.level)[:16])
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                del self._entries[:-self.max_entries]
            try:
                if not self._prepared:
                    self._prepare()
                line = (json.dumps(self._record(entry), ensure_ascii=False) + "\n").encode()
                if self.path.exists() and self.path.stat().st_size + len(line) > self.max_bytes:
                    for index in range(self.backups, 0, -1):
                        previous = self._file(index - 1)
                        if previous.exists():
                            os.replace(previous, self._file(index))
                    if not self.backups:
                        private_write(self.path, "")
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(self.path, flags, 0o600)
                with os.fdopen(fd, "ab") as handle:
                    if os.name == "posix":
                        os.fchmod(handle.fileno(), 0o600)
                    handle.write(line)
            except OSError:
                pass  # Session details remain usable when disk logging is unavailable.
        return entry

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            for index in range(self.backups + 1):
                try:
                    self._file(index).unlink(missing_ok=True)
                except OSError:
                    pass

    def export_json(self, target: Path, include_sensitive: bool = False) -> None:
        payload = {"app": "BlueDesk", "exported_at": time.time(),
            "redacted": not include_sensitive,
            "entries": [self._record(entry, include_sensitive) for entry in self.entries]}
        private_write(target, json.dumps(payload, ensure_ascii=False, indent=2))

    def export_csv(self, target: Path, include_sensitive: bool = False) -> None:
        def cell(value):
            text = str(value)
            return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp", "iso_time", "level", "category", "address", "message", "data"])
        for entry in self.entries:
            record = self._record(entry, include_sensitive)
            writer.writerow([entry.timestamp, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp)),
                *[cell(record[key]) for key in ("level", "category", "address", "message", "data")]])
        private_write(target, buffer.getvalue())

    def export_text(self, target: Path, include_sensitive: bool = False) -> None:
        lines = []
        for entry in self.entries:
            record = self._record(entry, include_sensitive)
            lines.append("[%s] %-5s %-8s %s" % (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp)),
                record["level"], record["category"], record["message"]))
        private_write(target, "\n".join(lines) + "\n")
