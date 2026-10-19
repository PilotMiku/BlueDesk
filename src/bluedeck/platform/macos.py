"""macOS platform adapter.

BLE is handled by Bleak/CoreBluetooth. Classic Bluetooth does not have a
public Python API on macOS, so paired/connected information is read from
system_profiler and, when installed, blueutil. System media keys are emulated
through AppleScript and therefore need Automation/Accessibility consent.
"""
from __future__ import annotations

import hashlib
import json
from typing import List, Optional, Tuple

from ..models import DeviceInfo, Transport
from .base import PlatformAdapter, PlatformCapabilities, PlatformError, run_command, which
from .parsers import (
    build_paired_device,
    parse_blueutil_paired,
    parse_system_profiler_bluetooth,
)

BLUETIL_CANDIDATES = ("/opt/homebrew/bin/blueutil", "/usr/local/bin/blueutil", "blueutil")
MEDIA_APPS = ("Spotify", "Music")


def _synthetic_address(name: str) -> str:
    digest = hashlib.sha1(name.strip().lower().encode("utf-8")).hexdigest()
    return "macos:" + digest[:12]


class MacOSPlatform(PlatformAdapter):
    system = "macOS"

    def __init__(self) -> None:
        self.blueutil = which(*BLUETIL_CANDIDATES)
        self.capabilities = PlatformCapabilities(
            name="macOS",
            classic_discovery=bool(self.blueutil),
            classic_control=bool(self.blueutil),
            absolute_volume=True,
            media_keys=True,
            system_pairing=bool(self.blueutil),
            gatt=True,
            notes=(
                "CoreBluetooth does not expose classic inquiry or RFCOMM.",
                "system_profiler lists paired/connected devices, not nearby unpaired classic devices.",
                "blueutil is optional and can connect/disconnect paired devices.",
                "AppleScript media control requires Automation permission; native media-key injection also needs Accessibility.",
            ),
        )

    def paired_devices(self) -> List[DeviceInfo]:
        devices: List[DeviceInfo] = []
        code, out, _ = run_command(
            ["system_profiler", "SPBluetoothDataType", "-json"], timeout=15.0
        )
        if code == 0 and out.strip():
            for item in parse_system_profiler_bluetooth(out):
                transport = (
                    Transport.CLASSIC
                    if item.get("minor_type")
                    else Transport.UNKNOWN
                )
                devices.append(
                    build_paired_device(
                        name=item["name"],
                        address=item["address"],
                        minor_type=item.get("minor_type", ""),
                        connected=item.get("connected", False),
                        paired=item.get("paired", True),
                        transport=transport,
                        platform="macos",
                        source="system_profiler",
                        metadata={"minor_type": item.get("minor_type", "")},
                    )
                )
        if self.blueutil:
            code, out, _ = run_command([self.blueutil, "--paired", "--format", "json"], timeout=8.0)
            if code == 0 and out.strip():
                for item in parse_blueutil_paired(out):
                    devices.append(
                        build_paired_device(
                            name=item["name"],
                            address=item["address"],
                            connected=item.get("connected", False),
                            paired=True,
                            transport=Transport.UNKNOWN,
                            platform="macos",
                            source="blueutil",
                        )
                    )
        # Merge duplicate names from the two sources.
        merged: List[DeviceInfo] = []
        by_name = {}
        for device in devices:
            key = (device.name or device.address).strip().lower()
            if key in by_name:
                by_name[key].merge(device)
            else:
                by_name[key] = device
                merged.append(device)
        return merged

    def open_bluetooth_settings(self) -> Tuple[bool, str]:
        code, _, err = run_command(
            ["open", "x-apple.systempreferences:com.apple.BluetoothSettings"],
            timeout=5.0,
        )
        if code == 0:
            return True, "已打开系统蓝牙设置"
        code, _, err = run_command(["open", "/System/Library/PreferencePanes/Bluetooth.prefPane"])
        return (code == 0, "已打开系统蓝牙设置" if code == 0 else (err or "无法打开蓝牙设置"))

    def open_sound_settings(self) -> Tuple[bool, str]:
        code, _, err = run_command(
            ["open", "x-apple.systempreferences:com.apple.Sound-Settings.extension"],
            timeout=5.0,
        )
        return (code == 0, "已打开系统声音设置" if code == 0 else (err or "无法打开声音设置"))

    def system_connect(self, device: DeviceInfo) -> Tuple[bool, str]:
        if self.blueutil and device.address and not device.address.startswith("macos:"):
            code, out, err = run_command([self.blueutil, "--connect", device.address], timeout=20.0)
            if code == 0:
                return True, "已请求 macOS 连接 %s" % device.display_name
            return False, (err or out or "blueutil 连接失败").strip()
        self.open_bluetooth_settings()
        return False, "请在弹出的系统蓝牙设置中连接此设备（未安装 blueutil）"

    def system_disconnect(self, device: DeviceInfo) -> Tuple[bool, str]:
        if self.blueutil and device.address and not device.address.startswith("macos:"):
            code, out, err = run_command([self.blueutil, "--disconnect", device.address], timeout=20.0)
            if code == 0:
                return True, "已请求 macOS 断开 %s" % device.display_name
            return False, (err or out or "blueutil 断开失败").strip()
        return False, "断开经典蓝牙设备需要安装 blueutil 或在系统设置中操作"

    def _osascript(self, script: str, timeout: float = 5.0) -> Tuple[int, str, str]:
        return run_command(["osascript", "-e", script], timeout=timeout)

    def set_output_volume(self, percent: int) -> None:
        value = max(0, min(100, int(percent)))
        code, _, err = self._osascript("set volume output volume %d" % value)
        if code != 0:
            raise PlatformError(err.strip() or "osascript 音量设置失败")

    def get_output_volume(self) -> Optional[int]:
        code, out, _ = self._osascript("output volume of (get volume settings)")
        if code != 0:
            return None
        try:
            return max(0, min(100, int(float(out.strip()))))
        except ValueError:
            return None

    def set_output_muted(self, muted: bool) -> None:
        code, _, err = self._osascript("set volume output muted %s" % ("true" if muted else "false"))
        if code != 0:
            raise PlatformError(err.strip() or "osascript 静音设置失败")

    def media_command(self, command: str) -> Tuple[bool, str]:
        actions = {
            "play_pause": ("playpause", "播放/暂停"),
            "next": ("next track", "下一首"),
            "previous": ("previous track", "上一首"),
            "stop": ("stop", "停止"),
        }
        if command not in actions:
            return False, "未知媒体命令: %s" % command
        action, label = actions[command]
        script = """
set runningApps to {}
tell application "System Events" to set runningApps to name of every process
if runningApps contains "Spotify" then
    tell application "Spotify" to %s
else if runningApps contains "Music" then
    tell application "Music" to %s
else
    error "Spotify/Music 均未运行"
end if
""" % (action, action)
        code, _, err = self._osascript(script)
        if code == 0:
            return True, "已发送媒体指令：%s" % label
        return False, (err.strip() or "媒体控制失败，请检查自动化权限")

    def rename_device(self, device: DeviceInfo, new_name: str) -> Tuple[bool, str]:
        return False, "macOS 未向第三方应用开放系统配对设备重命名；请在系统设置中操作"

    def permission_hint(self) -> str:
        return (
            "首次使用 BLE 时 macOS 会弹出蓝牙授权；若拒绝，请前往 系统设置 > 隐私与安全性 > 蓝牙 开启。"
            "媒体控制还会请求自动化权限。"
        )
