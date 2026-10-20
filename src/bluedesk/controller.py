"""Application controller: device store, filtering and UI-facing operations."""
from __future__ import annotations

import concurrent.futures
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .async_runner import AsyncRunner
from .connection_manager import ConnectionManager
from .demo import demo_devices, jitter_rssi
from .models import (
    ConnectionState,
    DeviceInfo,
    DeviceType,
    LogEntry,
    Telemetry,
    Transport,
    normalize_name,
)
from .platform import PlatformAdapter, PlatformError, get_platform
from .platform.parsers import system_telemetry
from .protocols import ProtocolRegistry
from .scan_service import ScanService
from .settings import AppSettings, LogStore, SettingsStore
from .security import MAX_DEVICES, MAX_NAME_CHARS, NEARBY_TTL, MAX_GATT_BYTES, RateLimiter


class AppController(QObject):
    devices_changed = Signal()
    device_updated = Signal(object)
    selection_changed = Signal(object)
    scan_state_changed = Signal(bool, str)
    telemetry_changed = Signal(str, object)
    services_changed = Signal(str, object)
    log_entry = Signal(object)
    status_message = Signal(str)
    operation_finished = Signal(str, bool)
    volume_changed = Signal(int)
    gatt_value = Signal(str, str, object, str)
    mode_changed = Signal(bool)

    _paired_result = Signal(object, str)

    def __init__(
        self,
        settings_store: Optional[SettingsStore] = None,
        platform: Optional[PlatformAdapter] = None,
        demo_mode: bool = False,
        auto_scan: Optional[bool] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.settings_store = settings_store or SettingsStore()
        self.settings: AppSettings = self.settings_store.settings
        self.platform = platform or get_platform()
        self.log_store = LogStore()
        self.protocols = ProtocolRegistry()
        self._devices: Dict[str, DeviceInfo] = {}
        self._telemetry: Dict[str, Telemetry] = {}
        self._services: Dict[str, list] = {}
        self._selected_key = ""
        self._demo_mode = False
        self._mode_generation = 0
        self._demo_volume = 68
        self._paired_loading = False
        self._closed = False
        self._value_rate = RateLimiter(20)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="bluedesk-io"
        )
        self._runner = AsyncRunner()
        self._runner.start()
        self.scan_service = ScanService(self._runner, self)
        self.connections = ConnectionManager(self._runner, self.platform, self)

        self.scan_service.device_found.connect(self._on_device_found)
        self.scan_service.scanning_changed.connect(self._on_scan_state)
        self.scan_service.error.connect(self._on_scan_error)
        self.connections.state_changed.connect(self._on_connection_state)
        self.connections.services_ready.connect(self._on_services)
        self.connections.telemetry_changed.connect(self._on_telemetry)
        self.connections.value_received.connect(self._on_value_received)
        self.connections.operation_finished.connect(self._on_operation_finished)
        self.connections.log.connect(self._on_manager_log)
        self._paired_result.connect(self._on_paired_loaded)

        # Demo is an explicit, session-only choice. Old settings cannot trap
        # a normal launch in simulation mode.
        self.settings.demo_mode = False
        self._paired_timer = QTimer(self)
        self._paired_timer.setInterval(10000)
        self._paired_timer.timeout.connect(self.load_paired_async)
        self._paired_timer.start()
        self._prune_timer = QTimer(self)
        self._prune_timer.setInterval(10000)
        self._prune_timer.timeout.connect(self._prune_nearby)
        self._prune_timer.start()
        if demo_mode:
            self.load_demo_devices(auto_connect=True)
        else:
            self._load_recent()
            self.load_paired_async()
            should_scan = self.settings.auto_scan if auto_scan is None else auto_scan
            if should_scan:
                QTimer.singleShot(1200, self._start_initial_scan)

        self.log("INFO", "BlueDesk 已启动 · %s" % self.platform.system, category="app")
        hint = self.platform.permission_hint()
        if hint:
            self.log("INFO", hint, category="permission")

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------
    @property
    def demo_mode(self) -> bool:
        return self._demo_mode

    @property
    def scanning(self) -> bool:
        return self.scan_service.active

    @property
    def selected(self) -> Optional[DeviceInfo]:
        return self._devices.get(self._selected_key)

    def devices(self) -> List[DeviceInfo]:
        values = list(self._devices.values())
        values.sort(
            key=lambda d: (
                0 if d.connected else 1,
                0 if d.paired else 1,
                0 if d.device_type is not DeviceType.UNKNOWN else 1,
                d.display_name.lower(),
            )
        )
        return values

    def filtered_devices(
        self,
        mode: str = "all",
        query: str = "",
        device_type: Optional[DeviceType] = None,
    ) -> List[DeviceInfo]:
        needle = normalize_name(query)
        result: List[DeviceInfo] = []
        now = time.time()
        for device in self.devices():
            if mode == "paired" and not device.paired:
                continue
            if mode == "connected" and not device.connected:
                continue
            if mode == "nearby":
                recent = (now - device.last_seen) < 120
                if device.rssi is None or (not recent and device.source != "bleak"):
                    continue
            if device_type is not None and device.device_type is not device_type:
                continue
            if needle:
                haystack = normalize_name(device.display_name + " " + device.address)
                if needle not in haystack:
                    continue
            result.append(device)
        return result

    def device(self, address: str) -> Optional[DeviceInfo]:
        key = (address or "").strip().lower()
        direct = self._devices.get(key)
        if direct is not None or not key:
            return direct
        return None

    def telemetry_for(self, address: str) -> Optional[Telemetry]:
        return self._telemetry.get(address)

    def services_for(self, address: str) -> list:
        return self._services.get(address) or self.connections.services_for(address)

    def platform_summary(self) -> str:
        caps = self.platform.capabilities
        bits = [caps.name]
        bits.append("BLE/GATT")
        if caps.classic_discovery:
            bits.append("经典蓝牙枚举")
        if caps.absolute_volume:
            bits.append("系统音量")
        if caps.media_keys:
            bits.append("媒体键")
        return " · ".join(bits)

    # ------------------------------------------------------------------
    # device store
    # ------------------------------------------------------------------
    def _load_recent(self) -> None:
        for recent in self.settings_store.recent_devices():
            if recent.metadata.get("demo") or recent.address.startswith("demo:"):
                continue
            # Discard aliases persisted by older name-based merging releases.
            recent.metadata.pop("ble_address", None)
            recent.metadata.pop("system_address", None)
            if recent.transport is Transport.DUAL:
                recent.transport = Transport.BLE if recent.source == "bleak" else Transport.CLASSIC
            if recent.address and recent.address not in self._devices:
                recent.connected = False
                recent.state = ConnectionState.DISCONNECTED
                recent.source = recent.source or "recent"
                self._devices[recent.key] = recent

    def load_paired_async(self) -> None:
        if self._demo_mode or self._paired_loading or self._closed:
            return
        self._paired_loading = True
        future = self._executor.submit(self.platform.paired_devices)
        future.add_done_callback(self._paired_done)

    def _paired_done(self, future: concurrent.futures.Future) -> None:
        try:
            devices = future.result()
            self._paired_result.emit(devices, "")
        except Exception as exc:
            self._paired_result.emit([], str(exc))

    def _on_paired_loaded(self, devices: list, error: str) -> None:
        self._paired_loading = False
        if self._demo_mode or self._closed:
            return
        if error:
            self.log("WARN", "读取系统配对设备失败：%s" % error, category="platform")
        count = 0
        for device in devices or []:
            device.metadata["system_address"] = device.address
            if self._upsert(device):
                count += 1
            existing = self.device(device.address)
            if existing is not None:
                if not self.connections.has_gatt_connection(existing.address) and not self.connections.is_pending(existing.address):
                    existing.connected = device.connected
                    existing.state = device.state
                    self.connections.sync_system_state(existing.address, device.connected)
                if device.connected:
                    self._on_telemetry(existing.address, system_telemetry(device.metadata.get("system_info", {})))
                elif not self.connections.has_gatt_connection(existing.address):
                    self._telemetry.pop(existing.address, None)
                self.device_updated.emit(existing)
        if count:
            self.log("INFO", "已加载 %d 个系统配对设备" % count, category="platform")
            self.devices_changed.emit()
        self.select_default_if_available()

    def _upsert(self, incoming: DeviceInfo) -> bool:
        key = incoming.key
        existing = self._devices.get(key)
        if existing is None:
            if len(self._devices) >= MAX_DEVICES:
                self._prune_nearby()
            if len(self._devices) >= MAX_DEVICES:
                if not incoming.paired:
                    return False
                disposable = next((key for key, d in self._devices.items()
                    if not d.paired and not d.connected and key != self._selected_key
                    and not self.connections.is_pending(d.address)), None)
                if disposable is None:
                    return False
                self._remove_nearby(disposable)
            self._devices[key] = incoming
            return True
        changed = existing.merge(incoming)
        if changed:
            if incoming.connected:
                existing.connected = True
                existing.state = ConnectionState.CONNECTED
            self.device_updated.emit(existing)
        return changed

    def _remove_nearby(self, key: str) -> None:
        device = self._devices.pop(key)
        self._telemetry.pop(device.address, None)
        self._services.pop(device.address, None)

    def _prune_nearby(self) -> None:
        expired = [key for key, d in self._devices.items()
            if not d.paired and not d.connected and key != self._selected_key
            and not self.connections.is_pending(d.address)
            and time.time() - d.last_seen > NEARBY_TTL]
        for key in expired:
            self._remove_nearby(key)
        if expired:
            self.devices_changed.emit()

    def _on_device_found(self, device: DeviceInfo) -> None:
        if self._demo_mode or self._closed:
            return
        device.name = device.name[:MAX_NAME_CHARS]
        device.metadata = {"advertisement": True}
        device.paired = False
        device.connected = False
        changed = self._upsert(device)
        if self.device(device.address) is None:
            return
        if not self._selected_key and device.rssi is not None and device.name.strip():
            merged = self.device(device.address)
            if merged is None:
                return
            self._selected_key = merged.key
            self.selection_changed.emit(self.selected)
        if changed:
            self.devices_changed.emit()

    def select(self, address: str) -> None:
        device = self.device(address)
        if device is None:
            return
        self._selected_key = device.key
        if not device.metadata.get("demo"):
            self.settings.last_selected = device.address
        self.selection_changed.emit(device)

    def select_default_if_available(self) -> None:
        if self.selected is not None:
            return
        if self.settings.default_device:
            device = self.device(self.settings.default_device)
            if device:
                self.select(device.address)
                return
        if self.settings.last_selected:
            device = self.device(self.settings.last_selected)
            if device:
                self.select(device.address)
                return
        if self.devices():
            self.select(self.devices()[0].address)

    def set_default_device(self, address: str) -> None:
        device = self.device(address)
        if device is None:
            return
        if device.metadata.get("demo"):
            self.status_message.emit("请在真实设备模式中设置默认设备")
            return
        self.settings.default_device = device.address
        if not device.metadata.get("demo"):
            self.settings_store.set_default(device.address)
            self.settings_store.save()
        self.log("INFO", "已设置默认设备：%s" % device.display_name, address=device.address)
        self.status_message.emit("已设为默认设备")
        self.devices_changed.emit()

    def is_default(self, address: str) -> bool:
        return bool(address) and self.settings.default_device.lower() == address.lower()

    # ------------------------------------------------------------------
    # demo
    # ------------------------------------------------------------------
    def load_demo_devices(self, auto_connect: bool = False) -> None:
        if self._demo_mode:
            return
        self._demo_mode = True
        self._mode_generation += 1
        self.stop_scan()
        self._devices.clear()
        self._telemetry.clear()
        self._services.clear()
        self._selected_key = ""
        for device in demo_devices():
            self._upsert(device)
        self.log("INFO", "演示模式已启用：设备与数据均为模拟值", category="demo")
        devices = self.devices()
        if devices:
            self.select(devices[0].address)
            if auto_connect:
                generation = self._mode_generation
                QTimer.singleShot(700, lambda: self.connect_device(devices[0].address)
                    if self._demo_mode and generation == self._mode_generation and not self._closed else None)
        self.devices_changed.emit()
        self.mode_changed.emit(True)

    def use_real_devices(self, scan: bool = True) -> None:
        if self._demo_mode:
            self._demo_mode = False
            self._mode_generation += 1
            self.connections.clear_demo()
            self._devices.clear()
            self._telemetry.clear()
            self._services.clear()
            self._selected_key = ""
            self.selection_changed.emit(None)
            self._load_recent()
            self.devices_changed.emit()
            self.mode_changed.emit(False)
            self.log("INFO", "已切换至真实设备模式", category="app")
        self.load_paired_async()
        if scan:
            # Let any previous scanner finish stopping before restarting.
            self._restart_real_scan()

    def _restart_real_scan(self) -> None:
        if self._demo_mode or self._closed:
            return
        if self.scan_service.active:
            QTimer.singleShot(300, self._restart_real_scan)
        else:
            self.start_scan()

    def simulate_rssi(self) -> None:
        for device in self._devices.values():
            if device.metadata.get("demo"):
                jitter_rssi(device)
        self.devices_changed.emit()

    # ------------------------------------------------------------------
    # scanning
    # ------------------------------------------------------------------
    def _start_initial_scan(self) -> None:
        if not self._demo_mode and not self._closed:
            self.start_scan()

    def start_scan(self) -> None:
        if self._demo_mode:
            self.use_real_devices()
            return
        self.load_paired_async()
        self.log("INFO", "开始 BLE 扫描", category="scan")
        self.scan_service.start()

    def stop_scan(self) -> None:
        self.scan_service.stop()

    def toggle_scan(self) -> None:
        if self.scan_service.active:
            self.stop_scan()
        else:
            self.start_scan()

    def _on_scan_state(self, active: bool, message: str) -> None:
        self.scan_state_changed.emit(active, message)
        self.log("INFO" if active else "DEBUG", message, category="scan")

    def _on_scan_error(self, message: str) -> None:
        self.log("ERROR", message, category="scan")
        self.status_message.emit(message)

    # ------------------------------------------------------------------
    # connection
    # ------------------------------------------------------------------
    def connect_device(self, address: str) -> None:
        device = self.device(address)
        if device is None:
            return
        if device.connected:
            self.disconnect_device(address)
            return
        self.log("INFO", "请求连接：%s" % device.display_name, address=device.address, category="connect")
        self.connections.connect_device(device)

    def disconnect_device(self, address: str) -> None:
        device = self.device(address)
        if device is None:
            return
        self.log("INFO", "请求断开：%s" % device.display_name, address=device.address, category="connect")
        self.connections.disconnect_device(device)

    def toggle_connection(self, address: str) -> None:
        device = self.device(address)
        if device is None:
            return
        if device.connected:
            self.disconnect_device(address)
        else:
            self.connect_device(address)

    def _on_connection_state(self, address: str, state_value: str, message: str) -> None:
        device = self.device(address)
        try:
            state = ConnectionState(state_value)
        except ValueError:
            state = ConnectionState.DISCONNECTED
        if device is not None:
            device.state = state
            device.connected = state is ConnectionState.CONNECTED
            if state is ConnectionState.CONNECTED:
                if not device.metadata.get("demo"):
                    self.settings_store.remember_device(device)
                    self.settings_store.save()
            elif state is ConnectionState.FAILED:
                device.connected = False
            self.device_updated.emit(device)
        self.status_message.emit(message)
        if state is ConnectionState.CONNECTED:
            self.log("INFO", message, address=address, category="connect")
        elif state is ConnectionState.FAILED:
            self.log("ERROR", message, address=address, category="connect")
        self.devices_changed.emit()

    def _on_services(self, address: str, services: list) -> None:
        self._services[address] = services
        self.services_changed.emit(address, services)
        self.log("INFO", "GATT 服务已更新：%d 个服务" % len(services), address=address, category="gatt")

    def _on_telemetry(self, address: str, telemetry: Telemetry) -> None:
        if self.device(address) is None:
            return
        if self.device(address).metadata.get("demo"):
            telemetry.extra["battery_source"] = "演示数据"
        existing = self._telemetry.get(address)
        if existing is None:
            self._telemetry[address] = telemetry
        else:
            existing.merge(telemetry)
        self.telemetry_changed.emit(address, self._telemetry[address])

    def refresh_telemetry(self, address: str) -> None:
        device = self.device(address)
        if device is None:
            return
        self.connections.refresh_telemetry(device)
        if not device.metadata.get("demo") and not self.connections.has_gatt_connection(address):
            self.load_paired_async()
        self.log("INFO", "刷新遥测数据", address=address, category="gatt")

    # ------------------------------------------------------------------
    # GATT operations
    # ------------------------------------------------------------------
    def read_characteristic(self, address: str, uuid: str) -> None:
        self.connections.read_characteristic(address, uuid)

    def write_characteristic(self, address: str, uuid: str, data: bytes, response: bool = True) -> None:
        self.connections.write_characteristic(address, uuid, data, response)

    def toggle_notify(self, address: str, uuid: str) -> None:
        self.connections.toggle_notify(address, uuid)

    def _on_value_received(self, address: str, uuid: str, data: object, source: str) -> None:
        if len(data) > MAX_GATT_BYTES or (source == "notify" and not self._value_rate.allow(address)):
            return
        payload = bytes(data) if not isinstance(data, bytes) else data
        self.gatt_value.emit(address, uuid, payload, source)
        self.log(
            "DATA",
            "%s %s <- %s" % (source.upper(), uuid, payload.hex(" ")),
            address=address,
            category="data",
            data=payload.hex(" "),
        )

    def _on_operation_finished(self, address: str, message: str, ok: bool) -> None:
        self.log("INFO" if ok else "ERROR", message, address=address, category="gatt")
        self.status_message.emit(message)
        self.operation_finished.emit(message, ok)

    def _on_manager_log(self, level: str, address: str, message: str) -> None:
        self.log(level, message, address=address, category="connect")

    # ------------------------------------------------------------------
    # OS controls
    # ------------------------------------------------------------------
    def get_volume(self) -> Optional[int]:
        if self._demo_mode:
            return self._demo_volume
        try:
            return self.platform.get_output_volume()
        except PlatformError as exc:
            self.status_message.emit(str(exc))
            return None

    def set_volume(self, percent: int) -> None:
        value = max(0, min(100, int(percent)))
        if self._demo_mode:
            self._demo_volume = value
            self.volume_changed.emit(value)
            return
        try:
            self.platform.set_output_volume(value)
            self.volume_changed.emit(value)
            self.log("INFO", "系统输出音量设为 %d%%" % value, category="audio")
        except PlatformError as exc:
            self.log("ERROR", str(exc), category="audio")
            self.status_message.emit(str(exc))

    def set_muted(self, muted: bool) -> None:
        if self._demo_mode:
            self.status_message.emit("演示模式：已%s静音" % ("开启" if muted else "关闭"))
            return
        try:
            self.platform.set_output_muted(muted)
            self.log("INFO", "系统静音：%s" % ("开" if muted else "关"), category="audio")
        except PlatformError as exc:
            self.log("ERROR", str(exc), category="audio")
            self.status_message.emit(str(exc))

    def media_command(self, command: str) -> None:
        if self._demo_mode:
            self.log("INFO", "演示模式：媒体指令 %s" % command, category="audio")
            self.status_message.emit("演示模式：已模拟媒体指令")
            return
        ok, message = self.platform.media_command(command)
        self.log("INFO" if ok else "ERROR", message, category="audio")
        self.status_message.emit(message)

    def open_bluetooth_settings(self) -> None:
        ok, message = self.platform.open_bluetooth_settings()
        self.log("INFO" if ok else "WARN", message, category="platform")
        self.status_message.emit(message)

    def open_sound_settings(self) -> None:
        ok, message = self.platform.open_sound_settings()
        self.log("INFO" if ok else "WARN", message, category="platform")
        self.status_message.emit(message)

    def rename_device(self, address: str, new_name: str) -> None:
        device = self.device(address)
        if device is None or not new_name.strip():
            return
        name = new_name.strip()
        if device.metadata.get("demo"):
            device.name = name
            self.device_updated.emit(device)
            self.devices_changed.emit()
            self.log("INFO", "演示模式：设备已重命名为 %s" % name, address=address, category="demo")
            self.status_message.emit("演示模式：名称已更新")
            return
        if device.is_ble and device.connected:
            self.connections.rename_ble_device(address, name)
            device.name = name
            self.device_updated.emit(device)
            self.devices_changed.emit()
            return
        ok, message = self.platform.rename_device(device, name)
        if ok:
            device.name = name
            self.device_updated.emit(device)
            self.devices_changed.emit()
        self.log("INFO" if ok else "WARN", message, address=address, category="platform")
        self.status_message.emit(message)

    # ------------------------------------------------------------------
    # logs
    # ------------------------------------------------------------------
    def log(
        self,
        level: str,
        message: str,
        address: str = "",
        category: str = "app",
        data: str = "",
    ) -> None:
        entry = LogEntry(level=level, message=message, address=address, category=category, data=data)
        entry = self.log_store.add(entry)
        self.log_entry.emit(entry)
        if os.environ.get("BLUEDESK_DEBUG"):
            print("[%s] %-5s %-8s %s" % (time.strftime("%H:%M:%S"), level, category, message))
            sys.stdout.flush()

    def export_logs(self, path: str, include_sensitive: bool = False) -> None:
        target = Path(path)
        suffix = target.suffix.lower()
        if suffix == ".csv":
            self.log_store.export_csv(target, include_sensitive)
        elif suffix == ".json":
            self.log_store.export_json(target, include_sensitive)
        else:
            self.log_store.export_text(target, include_sensitive)
        self.log("INFO", "日志已导出：%s" % target, category="log")
        self.status_message.emit("日志已导出")

    def clear_logs(self) -> None:
        self.log_store.clear()
        self.status_message.emit("日志已清空")

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        self._closed = True
        self._paired_timer.stop()
        self._prune_timer.stop()
        try:
            self.stop_scan()
        except Exception:
            pass
        try:
            self.connections.shutdown()
        except Exception:
            pass
        try:
            self._runner.stop()
        except Exception:
            pass
        try:
            self.settings_store.save()
        except Exception:
            pass
        self._executor.shutdown(wait=False)
