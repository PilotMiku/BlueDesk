"""BLE scanning service built on Bleak.

Bleak provides a single API over CoreBluetooth (macOS) and WinRT (Windows).
Classic discovery is handled by the platform adapters because neither OS
offers a portable public classic-inquiry API to Python.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .classifier import explain_device
from .models import DeviceInfo, Transport
from .async_runner import AsyncRunner

try:
    from bleak import BleakScanner
    BLEAK_AVAILABLE = True
    BLEAK_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on host
    BleakScanner = None  # type: ignore[assignment]
    BLEAK_AVAILABLE = False
    BLEAK_IMPORT_ERROR = str(exc)

# PyObjC/CoreBluetooth must be imported on the Qt main thread. If Bleak imports
# the CoreBluetooth backend lazily inside the asyncio worker thread, importing
# PyObjC while AppKit is running can deadlock on macOS. Preloading it here is
# safe because this module is imported by the UI thread before scanning starts.
if sys.platform == "darwin" and BLEAK_AVAILABLE:
    try:  # pragma: no cover - platform specific
        import objc  # noqa: F401
        from bleak.backends.corebluetooth import client as _cb_client  # noqa: F401
        from bleak.backends.corebluetooth import scanner as _cb_scanner  # noqa: F401
    except Exception:
        pass


class ScanService(QObject):
    device_found = Signal(object)
    scanning_changed = Signal(bool, str)
    error = Signal(str)

    def __init__(self, runner: AsyncRunner, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.runner = runner
        self._active = False
        self._scanner = None
        self._stop_event: Optional[asyncio.Event] = None
        self._stop_requested = False

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        if self._active:
            return
        if not BLEAK_AVAILABLE:
            self.error.emit("Bleak 不可用：%s" % (BLEAK_IMPORT_ERROR or "未安装"))
            self.scanning_changed.emit(False, "BLE 依赖不可用")
            return
        self._active = True
        self._stop_requested = False
        self.scanning_changed.emit(True, "正在扫描 BLE 设备…")
        try:
            self.runner.submit(self._scan())
        except Exception as exc:
            self._active = False
            self.error.emit("无法启动 BLE 扫描：%s" % exc)
            self.scanning_changed.emit(False, "扫描启动失败")

    def stop(self) -> None:
        if not self._active or self._stop_requested:
            return
        self._stop_requested = True
        if self._stop_event is not None:
            self.runner.call_soon_threadsafe(self._stop_event.set)
        self.scanning_changed.emit(True, "正在停止扫描…")

    async def _scan(self) -> None:
        self._stop_event = asyncio.Event()
        scanner = None
        try:
            if self._stop_requested:
                return
            scanner = BleakScanner(detection_callback=self._on_detection)
            self._scanner = scanner
            await scanner.start()
            while not self._stop_event.is_set():
                await asyncio.sleep(0.25)
            try:
                await asyncio.wait_for(scanner.stop(), timeout=3.0)
            except asyncio.TimeoutError:
                # CoreBluetooth occasionally misses the isScanning KVO update.
                # Release the underlying scan directly and continue.
                self.error.emit("停止 BLE 扫描超时，已强制释放扫描器")
                try:
                    central = scanner._manager.central_manager  # type: ignore[attr-defined]
                    central.stopScan()
                except Exception:
                    pass
            self.scanning_changed.emit(False, "扫描已停止")
        except Exception as exc:
            self.error.emit("BLE 扫描失败：%s" % exc)
            self.scanning_changed.emit(False, "扫描失败")
        finally:
            self._active = False
            self._scanner = None
            self._stop_event = None
            self._stop_requested = False

    def _on_detection(self, device, advertisement_data=None) -> None:
        try:
            address = getattr(device, "address", "") or ""
            if not address:
                return
            adv = advertisement_data
            local_name = getattr(adv, "local_name", "") or ""
            name = local_name or getattr(device, "name", "") or ""
            rssi = getattr(adv, "rssi", None)
            if rssi is None:
                rssi = getattr(device, "rssi", None)
            service_uuids = [str(u) for u in (getattr(adv, "service_uuids", None) or [])]
            manufacturer = {
                int(key): bytes(value)
                for key, value in (getattr(adv, "manufacturer_data", None) or {}).items()
            }
            service_data = {
                str(key): bytes(value)
                for key, value in (getattr(adv, "service_data", None) or {}).items()
            }
            appearance = getattr(adv, "appearance", None)
            tx_power = getattr(adv, "tx_power", None)
            classification = explain_device(
                name=name,
                ble_appearance=appearance,
                service_uuids=service_uuids,
                manufacturer_data=manufacturer,
                platform=sys.platform,
            )
            info = DeviceInfo(
                address=address,
                name=name,
                device_type=classification.device_type,
                transport=Transport.BLE,
                rssi=rssi,
                tx_power=tx_power,
                paired=False,
                connected=False,
                ble_appearance=appearance,
                service_uuids=service_uuids,
                manufacturer_data=manufacturer,
                service_data=service_data,
                platform=sys.platform,
                source="bleak",
                confidence=classification.confidence,
                classification_source=classification.source,
                classification_reason=classification.reason,
                metadata={"advertisement": True},
            )
            self.device_found.emit(info)
        except Exception as exc:
            self.error.emit("解析 BLE 广播失败：%s" % exc)
