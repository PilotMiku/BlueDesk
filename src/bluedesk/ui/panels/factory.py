"""Panel factory: device type -> control panel."""
from __future__ import annotations

from ...controller import AppController
from ...models import DeviceInfo, DeviceType
from .audio import AudioPanel
from .base import ControlPanel
from .generic import GamepadPanel, GenericPanel
from .keyboard import KeyboardPanel
from .mouse import MousePanel
from .wearable import WearablePanel


def create_panel(controller: AppController, device: DeviceInfo) -> ControlPanel:
    if device.device_type in (DeviceType.HEADPHONES, DeviceType.SPEAKER, DeviceType.CAR_AUDIO):
        return AudioPanel(controller, device)
    if device.device_type is DeviceType.MOUSE:
        return MousePanel(controller, device)
    if device.device_type is DeviceType.KEYBOARD:
        return KeyboardPanel(controller, device)
    if device.device_type is DeviceType.WEARABLE:
        return WearablePanel(controller, device)
    if device.device_type is DeviceType.GAMEPAD:
        return GamepadPanel(controller, device)
    return GenericPanel(controller, device)
