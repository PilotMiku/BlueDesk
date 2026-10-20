"""Windows platform adapter.

BLE uses Bleak/WinRT. Paired devices are enumerated through PowerShell PnP
queries (no PyBluez dependency). Absolute volume control uses pycaw when
installed; media transport uses the standard Windows media virtual keys.
"""
from __future__ import annotations

import ctypes
from typing import List, Optional, Tuple

from ..models import DeviceInfo
from .base import PlatformAdapter, PlatformCapabilities, PlatformError, run_command
from .parsers import build_paired_device, parse_windows_pnp_devices

PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "Get-PnpDevice -Class Bluetooth | "
    "Where-Object { $_.InstanceId -match 'BTH' -and $_.FriendlyName } | "
    "Select-Object FriendlyName,InstanceId,Status,Present | ConvertTo-Json -Depth 3"
)

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


class WindowsPlatform(PlatformAdapter):
    system = "Windows"

    def __init__(self) -> None:
        self.capabilities = PlatformCapabilities(
            name="Windows 10/11",
            classic_discovery=True,
            classic_control=False,
            absolute_volume=self._pycaw_available(),
            media_keys=True,
            system_pairing=False,
            gatt=True,
            notes=(
                "Classic pairing is performed by the Windows Settings UI; WinRT can enumerate paired devices.",
                "BLE GATT is available through Bleak/WinRT.",
                "pycaw is needed for absolute volume; otherwise only media keys are available.",
            ),
        )

    def paired_devices(self) -> List[DeviceInfo]:
        code, out, _ = run_command(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", PS_SCRIPT],
            timeout=20.0,
        )
        if code != 0 or not out.strip():
            return []
        devices: List[DeviceInfo] = []
        for item in parse_windows_pnp_devices(out):
            devices.append(
                build_paired_device(
                    name=item["name"],
                    address=item["address"],
                    transport=item.get("transport"),
                    connected=item.get("connected", False),
                    paired=True,
                    platform="windows",
                    source="pnp",
                    metadata={
                        "instance_id": item.get("instance_id", ""),
                        "status": item.get("status", ""),
                    },
                )
            )
        return devices

    def open_bluetooth_settings(self) -> Tuple[bool, str]:
        code, _, err = run_command(["cmd", "/c", "start", "", "ms-settings:bluetooth"], timeout=5.0)
        return (code == 0, "已打开 Windows 蓝牙设置" if code == 0 else (err or "无法打开设置"))

    def open_sound_settings(self) -> Tuple[bool, str]:
        code, _, err = run_command(["cmd", "/c", "start", "", "ms-settings:sound"], timeout=5.0)
        return (code == 0, "已打开 Windows 声音设置" if code == 0 else (err or "无法打开设置"))

    def system_connect(self, device: DeviceInfo) -> Tuple[bool, str]:
        self.open_bluetooth_settings()
        return False, "Windows 未向 Python 暴露通用配对 UI；请在系统设置中确认连接"

    def system_disconnect(self, device: DeviceInfo) -> Tuple[bool, str]:
        return False, "请在 Windows 设置 > 蓝牙和其他设备 中移除此设备或断开连接"

    @staticmethod
    def _pycaw_available() -> bool:
        try:
            import pycaw  # noqa: F401
            import comtypes  # noqa: F401
        except Exception:
            return False
        return True

    def _volume_endpoint(self):
        try:
            from comtypes import CLSCTX_ALL, CoInitialize
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except Exception as exc:
            raise PlatformError("绝对音量控制需要 pycaw 和 comtypes: pip install pycaw comtypes") from exc
        try:
            CoInitialize()
        except Exception:
            pass
        try:
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return interface.QueryInterface(IAudioEndpointVolume)
        except Exception as exc:
            raise PlatformError("无法访问 Windows 音频终结点: %s" % exc) from exc

    def set_output_volume(self, percent: int) -> None:
        endpoint = self._volume_endpoint()
        endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, percent / 100.0)), None)

    def get_output_volume(self) -> Optional[int]:
        try:
            endpoint = self._volume_endpoint()
        except PlatformError:
            return None
        return int(round(endpoint.GetMasterVolumeLevelScalar() * 100))

    def set_output_muted(self, muted: bool) -> None:
        endpoint = self._volume_endpoint()
        endpoint.SetMute(1 if muted else 0, None)

    def media_command(self, command: str) -> Tuple[bool, str]:
        mapping = {
            "play_pause": (VK_MEDIA_PLAY_PAUSE, "播放/暂停"),
            "next": (VK_MEDIA_NEXT_TRACK, "下一首"),
            "previous": (VK_MEDIA_PREV_TRACK, "上一首"),
            "stop": (VK_MEDIA_STOP, "停止"),
        }
        if command not in mapping:
            return False, "未知媒体命令: %s" % command
        vk, label = mapping[command]
        try:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        except Exception as exc:
            return False, "发送媒体按键失败: %s" % exc
        return True, "已发送媒体指令：%s" % label

    def rename_device(self, device: DeviceInfo, new_name: str) -> Tuple[bool, str]:
        return False, "Windows 未向 Python 开放通用配对设备重命名；请在系统设置中操作"

    def permission_hint(self) -> str:
        return (
            "Windows 10/11 通常不会为桌面 Python 应用弹出蓝牙授权。"
            "若扫描或 GATT 访问失败，请检查 设置 > 隐私和安全性 > 蓝牙，"
            "并确认蓝牙已开启。"
        )
