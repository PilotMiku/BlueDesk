"""Connection lifecycle, GATT operations and telemetry collection."""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from .async_runner import AsyncRunner
from .ble_uuids import describe_characteristic, describe_service
from .codecs import parse_battery_level, parse_heart_rate, parse_utf8
from .demo import demo_read_value, demo_services, demo_telemetry
from .models import (
    ConnectionState,
    DeviceInfo,
    GattCharacteristicInfo,
    GattServiceInfo,
    Telemetry,
    Transport,
)
from .platform.base import PlatformAdapter, PlatformError

try:
    from bleak import BleakClient
except Exception:  # pragma: no cover
    BleakClient = None  # type: ignore[assignment]

BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
HEART_RATE_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"
FIRMWARE_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
MODEL_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
MANUFACTURER_UUID = "00002a29-0000-1000-8000-00805f9b34fb"


def short_uuid(value: str) -> str:
    text = (value or "").lower()
    if len(text) >= 8 and text.endswith("-0000-1000-8000-00805f9b34fb"):
        return text[4:8]
    return text


class ConnectionManager(QObject):
    state_changed = Signal(str, str, str)
    services_ready = Signal(str, object)
    telemetry_changed = Signal(str, object)
    value_received = Signal(str, str, object, str)
    operation_finished = Signal(str, str, bool)
    log = Signal(str, str, str)  # level, address, message

    _system_result = Signal(str, bool, str)

    def __init__(
        self,
        runner: AsyncRunner,
        platform: PlatformAdapter,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.runner = runner
        self.platform = platform
        self._clients: Dict[str, object] = {}
        self._services: Dict[str, List[GattServiceInfo]] = {}
        self._notifying: Set[Tuple[str, str]] = set()
        self._pending: Set[str] = set()
        self._system_connected: Set[str] = set()
        self._demo_connected: Set[str] = set()
        self._demo_devices: Dict[str, DeviceInfo] = {}
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="bluedeck-system")
        self._system_result.connect(self._on_system_result)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def services_for(self, address: str) -> List[GattServiceInfo]:
        return list(self._services.get(address, []))

    def is_connected(self, address: str) -> bool:
        return address in self._clients or address in self._system_connected or address in self._demo_connected

    def connect_device(self, device: DeviceInfo) -> None:
        address = device.address
        if not address:
            return
        if address in self._pending or self.is_connected(address):
            return
        self._pending.add(address)
        self.state_changed.emit(address, ConnectionState.CONNECTING.value, "正在建立连接…")
        if device.metadata.get("demo"):
            QTimer.singleShot(600, lambda: self._demo_connect(device))
            return
        if self._should_use_ble(device):
            if BleakClient is None:
                self._pending.discard(address)
                self.state_changed.emit(address, ConnectionState.FAILED.value, "Bleak 未安装，无法连接 BLE")
                return
            try:
                self.runner.submit(self._connect_ble(device))
            except Exception as exc:
                self._pending.discard(address)
                self.state_changed.emit(address, ConnectionState.FAILED.value, "连接启动失败：%s" % exc)
        else:
            self._connect_with_system(device)

    def disconnect_device(self, device: DeviceInfo) -> None:
        address = device.address
        if address in self._demo_connected:
            self.state_changed.emit(address, ConnectionState.DISCONNECTING.value, "正在断开…")
            QTimer.singleShot(350, lambda: self._demo_disconnect(address))
            return
        if address in self._clients:
            self.state_changed.emit(address, ConnectionState.DISCONNECTING.value, "正在断开 GATT 连接…")
            self.runner.submit(self._disconnect_ble(address))
            return
        if address in self._system_connected:
            self.state_changed.emit(address, ConnectionState.DISCONNECTING.value, "正在请求系统断开…")
            self._disconnect_with_system(device)
            return
        self.state_changed.emit(address, ConnectionState.DISCONNECTED.value, "设备未连接")

    def read_characteristic(self, address: str, uuid: str) -> None:
        device = self._demo_device(address)
        if device is not None:
            data = demo_read_value(device, uuid)
            self.value_received.emit(address, uuid, data, "read")
            self._log("INFO", address, "读取 %s -> %s" % (short_uuid(uuid), data.hex(" ")))
            return
        client = self._clients.get(address)
        if client is None:
            self.operation_finished.emit(address, "设备未连接", False)
            return
        self.runner.submit(self._read_async(address, client, uuid))

    def write_characteristic(self, address: str, uuid: str, data: bytes, response: bool = True) -> None:
        device = self._demo_device(address)
        if device is not None:
            self.value_received.emit(address, uuid, data, "write")
            self.operation_finished.emit(address, "写入成功（演示）", True)
            self._log("INFO", address, "写入 %s <- %s" % (short_uuid(uuid), data.hex(" ")))
            return
        client = self._clients.get(address)
        if client is None:
            self.operation_finished.emit(address, "设备未连接", False)
            return
        self.runner.submit(self._write_async(address, client, uuid, data, response))

    def toggle_notify(self, address: str, uuid: str) -> None:
        client = self._clients.get(address)
        key = (address, uuid)
        if client is None:
            device = self._demo_device(address)
            if device is not None:
                if key in self._notifying:
                    self._notifying.discard(key)
                    self.operation_finished.emit(address, "已取消订阅（演示）", True)
                else:
                    self._notifying.add(key)
                    self.operation_finished.emit(address, "已订阅通知（演示）", True)
                return
            self.operation_finished.emit(address, "设备未连接", False)
            return
        self.runner.submit(self._toggle_notify_async(address, client, uuid))

    def refresh_telemetry(self, device: DeviceInfo) -> None:
        if device.metadata.get("demo"):
            self.telemetry_changed.emit(device.address, demo_telemetry(device))
            return
        client = self._clients.get(device.address)
        if client is None:
            self.telemetry_changed.emit(device.address, Telemetry())
            return
        self.runner.submit(self._read_telemetry_async(device.address, client))

    def rename_ble_device(self, address: str, new_name: str) -> None:
        device = self._demo_device(address)
        if device is not None:
            device.name = new_name
            self.operation_finished.emit(address, "设备名称已更新（演示）", True)
            return
        client = self._clients.get(address)
        if client is None:
            self.operation_finished.emit(address, "仅已连接的 BLE 设备支持写入 GAP Device Name", False)
            return
        self.runner.submit(self._write_name_async(address, client, new_name))

    def shutdown(self) -> None:
        for client in list(self._clients.values()):
            try:
                future = self.runner.submit(client.disconnect())  # type: ignore[attr-defined]
                future.result(timeout=1.5)
            except Exception:
                pass
        self._clients.clear()
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    # BLE connection
    # ------------------------------------------------------------------
    @staticmethod
    def _should_use_ble(device: DeviceInfo) -> bool:
        if device.transport is Transport.DUAL and device.device_type.group == "audio":
            # Audio should be connected by the OS so A2DP/HFP are available;
            # a BLE GATT connection alone would not route audio.
            return False
        if device.source == "bleak":
            return True
        if device.transport is Transport.BLE:
            return True
        if device.transport is Transport.DUAL:
            return device.device_type.group not in ("audio",)
        return bool(device.metadata.get("ble_address"))

    async def _connect_ble(self, device: DeviceInfo) -> None:
        address = device.address
        connect_address = str(device.metadata.get("ble_address") or address)
        client = None
        try:
            if BleakClient is None:
                raise RuntimeError("Bleak 未安装")
            client = BleakClient(
                connect_address,
                disconnected_callback=lambda c: self._on_ble_disconnected(address),
                timeout=15.0,
            )
            await client.connect()
            services = self._extract_services(client)
            self._clients[address] = client
            self._services[address] = services
            self._pending.discard(address)
            self.state_changed.emit(address, ConnectionState.CONNECTED.value, "GATT 已连接")
            self.services_ready.emit(address, services)
            self._log("INFO", address, "BLE GATT 已连接，发现 %d 个服务" % len(services))
            await self._read_telemetry_async(address, client)
            await self._start_standard_notifications(address, client, services)
        except Exception as exc:
            self._pending.discard(address)
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            self._clients.pop(address, None)
            self.state_changed.emit(address, ConnectionState.FAILED.value, "连接失败：%s" % exc)
            self._log("ERROR", address, "BLE 连接失败：%s" % exc)

    def _extract_services(self, client: object) -> List[GattServiceInfo]:
        collection = getattr(client, "services", None)
        result: List[GattServiceInfo] = []
        if collection is None:
            return result
        for service in collection:
            chars: List[GattCharacteristicInfo] = []
            for char in getattr(service, "characteristics", []) or []:
                try:
                    props = [str(p) for p in (getattr(char, "properties", []) or [])]
                except TypeError:
                    props = []
                uid = str(getattr(char, "uuid", ""))
                chars.append(
                    GattCharacteristicInfo(
                        uuid=uid,
                        handle=getattr(char, "handle", None),
                        properties=props,
                        description=describe_characteristic(uid),
                    )
                )
            uid = str(getattr(service, "uuid", ""))
            result.append(
                GattServiceInfo(
                    uuid=uid,
                    handle=getattr(service, "handle", None),
                    description=describe_service(uid),
                    characteristics=chars,
                )
            )
        return result

    async def _disconnect_ble(self, address: str) -> None:
        client = self._clients.pop(address, None)
        try:
            if client is not None:
                await client.disconnect()  # type: ignore[attr-defined]
        except Exception as exc:
            self._log("WARN", address, "断开时发生错误：%s" % exc)
        finally:
            self._system_connected.discard(address)
            self._demo_connected.discard(address)
            self._services.pop(address, None)
            self.state_changed.emit(address, ConnectionState.DISCONNECTED.value, "已断开连接")

    def _on_ble_disconnected(self, address: str) -> None:
        if address in self._clients:
            self._log("WARN", address, "BLE 连接意外断开")
        self._clients.pop(address, None)
        self._services.pop(address, None)
        self.state_changed.emit(address, ConnectionState.DISCONNECTED.value, "设备已断开")

    async def _read_async(self, address: str, client: object, uuid: str) -> None:
        try:
            data = await client.read_gatt_char(uuid)  # type: ignore[attr-defined]
            payload = bytes(data)
            self.value_received.emit(address, uuid, payload, "read")
            self._log("INFO", address, "读取 %s -> %s" % (short_uuid(uuid), payload.hex(" ")))
        except Exception as exc:
            self.operation_finished.emit(address, "读取失败：%s" % exc, False)
            self._log("ERROR", address, "读取失败 %s：%s" % (short_uuid(uuid), exc))

    async def _write_async(
        self, address: str, client: object, uuid: str, data: bytes, response: bool
    ) -> None:
        try:
            await client.write_gatt_char(uuid, data, response=response)  # type: ignore[attr-defined]
            self.value_received.emit(address, uuid, data, "write")
            self.operation_finished.emit(address, "写入成功", True)
            self._log("INFO", address, "写入 %s <- %s" % (short_uuid(uuid), data.hex(" ")))
        except Exception as exc:
            self.operation_finished.emit(address, "写入失败：%s" % exc, False)
            self._log("ERROR", address, "写入失败 %s：%s" % (short_uuid(uuid), exc))

    async def _toggle_notify_async(self, address: str, client: object, uuid: str) -> None:
        key = (address, uuid)
        try:
            if key in self._notifying:
                await client.stop_notify(uuid)  # type: ignore[attr-defined]
                self._notifying.discard(key)
                self.operation_finished.emit(address, "已取消通知订阅", True)
            else:
                await client.start_notify(  # type: ignore[attr-defined]
                    uuid,
                    lambda _char, data: self.value_received.emit(
                        address, uuid, bytes(data), "notify"
                    ),
                )
                self._notifying.add(key)
                self.operation_finished.emit(address, "已订阅通知", True)
        except Exception as exc:
            self.operation_finished.emit(address, "通知订阅失败：%s" % exc, False)
            self._log("ERROR", address, "通知订阅失败 %s：%s" % (short_uuid(uuid), exc))

    async def _write_name_async(self, address: str, client: object, new_name: str) -> None:
        try:
            await client.write_gatt_char(DEVICE_NAME_UUID, new_name.encode("utf-8"), response=True)  # type: ignore[attr-defined]
            self.operation_finished.emit(address, "GAP Device Name 已写入；系统配对名称可能不会变化", True)
            self._log("INFO", address, "写入 GAP Device Name：%s" % new_name)
        except Exception as exc:
            self.operation_finished.emit(address, "重命名失败：%s" % exc, False)
            self._log("ERROR", address, "重命名失败：%s" % exc)

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------
    async def _read_telemetry_async(self, address: str, client: object) -> None:
        telemetry = Telemetry()
        chars = self._characteristic_map(address)
        if "2a19" in chars:
            try:
                data = await client.read_gatt_char(chars["2a19"])  # type: ignore[attr-defined]
                telemetry.battery = parse_battery_level(bytes(data))
            except Exception as exc:
                self._log("WARN", address, "读取电量失败：%s" % exc)
        for short, attr in (
            ("2a26", "firmware"),
            ("2a24", "model"),
            ("2a25", "serial"),
            ("2a29", "manufacturer"),
        ):
            if short not in chars:
                continue
            try:
                data = await client.read_gatt_char(chars[short])  # type: ignore[attr-defined]
                setattr(telemetry, attr, parse_utf8(bytes(data)))
            except Exception as exc:
                self._log("WARN", address, "读取 %s 失败：%s" % (short, exc))
        telemetry.updated_at = time.time()
        self.telemetry_changed.emit(address, telemetry)
        self._log(
            "INFO",
            address,
            "遥测：电量=%s 固件=%s 型号=%s"
            % (
                telemetry.battery if telemetry.battery is not None else "—",
                telemetry.firmware or "—",
                telemetry.model or "—",
            ),
        )

    async def _start_standard_notifications(
        self, address: str, client: object, services: List[GattServiceInfo]
    ) -> None:
        chars = self._characteristic_map(address)
        if "2a37" not in chars:
            return
        try:
            uid = chars["2a37"]

            def callback(_char, data) -> None:
                payload = bytes(data)
                self.value_received.emit(address, uid, payload, "notify")
                heart_rate = parse_heart_rate(payload)
                if heart_rate is not None:
                    telemetry = Telemetry(heart_rate=heart_rate, updated_at=time.time())
                    self.telemetry_changed.emit(address, telemetry)

            await client.start_notify(uid, callback)  # type: ignore[attr-defined]
            self._notifying.add((address, uid))
            self._log("INFO", address, "已订阅心率测量通知")
        except Exception as exc:
            self._log("WARN", address, "订阅心率通知失败：%s" % exc)

    def _characteristic_map(self, address: str) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for service in self._services.get(address, []):
            for char in service.characteristics:
                mapping[short_uuid(char.uuid)] = char.uuid
        return mapping

    # ------------------------------------------------------------------
    # system connection
    # ------------------------------------------------------------------
    def _connect_with_system(self, device: DeviceInfo) -> None:
        future = self._executor.submit(self.platform.system_connect, device)
        future.add_done_callback(lambda done: self._emit_system_result(device.address, done))

    def _disconnect_with_system(self, device: DeviceInfo) -> None:
        future = self._executor.submit(self.platform.system_disconnect, device)
        future.add_done_callback(lambda done: self._emit_system_result(device.address, done))

    def _emit_system_result(self, address: str, future: concurrent.futures.Future) -> None:
        try:
            ok, message = future.result()
        except Exception as exc:
            ok, message = False, "系统连接操作失败：%s" % exc
        self._system_result.emit(address, bool(ok), str(message))

    def _on_system_result(self, address: str, ok: bool, message: str) -> None:
        self._pending.discard(address)
        if ok:
            self._system_connected.add(address)
            self.state_changed.emit(address, ConnectionState.CONNECTED.value, message)
            self._log("INFO", address, message)
        else:
            self._system_connected.discard(address)
            self.state_changed.emit(address, ConnectionState.DISCONNECTED.value, message)
            self._log("WARN", address, message)

    # ------------------------------------------------------------------
    # demo connection
    # ------------------------------------------------------------------
    def _demo_device(self, address: str) -> Optional[DeviceInfo]:
        if address not in self._demo_connected:
            return None
        return self._demo_devices.get(address)

    def _demo_connect(self, device: DeviceInfo) -> None:
        self._pending.discard(device.address)
        self._demo_devices[device.address] = device
        self._demo_connected.add(device.address)
        services = demo_services(device)
        self._services[device.address] = services
        self.state_changed.emit(device.address, ConnectionState.CONNECTED.value, "演示模式：已连接")
        self.services_ready.emit(device.address, services)
        self.telemetry_changed.emit(device.address, demo_telemetry(device))
        self._log("INFO", device.address, "演示设备已连接（不会发送真实数据）")

    def _demo_disconnect(self, address: str) -> None:
        self._demo_connected.discard(address)
        self._services.pop(address, None)
        self.state_changed.emit(address, ConnectionState.DISCONNECTED.value, "演示模式：已断开")
        self._log("INFO", address, "演示设备已断开")

    # ------------------------------------------------------------------
    def _log(self, level: str, address: str, message: str) -> None:
        self.log.emit(level, address, message)
