"""Platform abstraction used by the scanner, connection manager and UI."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..models import DeviceInfo


class PlatformError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlatformCapabilities:
    name: str
    classic_discovery: bool
    classic_control: bool
    absolute_volume: bool
    media_keys: bool
    system_pairing: bool
    gatt: bool
    notes: Tuple[str, ...] = ()


def run_command(
    args: Sequence[str],
    timeout: float = 12.0,
    input_text: Optional[str] = None,
) -> Tuple[int, str, str]:
    """Run a command without a shell. Returns (returncode, stdout, stderr)."""
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "input": input_text,
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        completed = subprocess.run(list(args), **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def which(*candidates: str) -> Optional[str]:
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    return None


class PlatformAdapter:
    system = "Unknown"
    capabilities = PlatformCapabilities(
        name="Unknown",
        classic_discovery=False,
        classic_control=False,
        absolute_volume=False,
        media_keys=False,
        system_pairing=False,
        gatt=True,
    )

    def paired_devices(self) -> List[DeviceInfo]:
        return []

    def open_bluetooth_settings(self) -> Tuple[bool, str]:
        return False, "当前平台不支持打开蓝牙设置"

    def open_sound_settings(self) -> Tuple[bool, str]:
        return self.open_bluetooth_settings()

    def system_connect(self, device: DeviceInfo) -> Tuple[bool, str]:
        return False, "当前平台不支持系统级连接"

    def system_disconnect(self, device: DeviceInfo) -> Tuple[bool, str]:
        return False, "当前平台不支持系统级断开"

    def set_output_volume(self, percent: int) -> None:
        raise PlatformError("当前平台不支持系统音量控制")

    def get_output_volume(self) -> Optional[int]:
        return None

    def set_output_muted(self, muted: bool) -> None:
        raise PlatformError("当前平台不支持静音控制")

    def media_command(self, command: str) -> Tuple[bool, str]:
        return False, "当前平台不支持媒体按键控制"

    def rename_device(self, device: DeviceInfo, new_name: str) -> Tuple[bool, str]:
        return False, "系统级重命名需要平台专用 API 或厂商协议"

    def permission_hint(self) -> str:
        return ""

    def command_available(self, name: str) -> bool:
        return which(name) is not None
