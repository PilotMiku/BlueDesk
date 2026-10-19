"""Human-readable names for common Bluetooth SIG UUIDs."""
from __future__ import annotations

from typing import Dict, Iterable, Optional

from .classifier import normalize_uuid, uuid16

SERVICE_NAMES: Dict[str, str] = {
    "1800": "Generic Access",
    "1801": "Generic Attribute",
    "180a": "Device Information",
    "180d": "Heart Rate",
    "180f": "Battery Service",
    "1812": "Human Interface Device",
    "1814": "Running Speed and Cadence",
    "1816": "Cycling Speed and Cadence",
    "1818": "Cycling Power",
    "1826": "Fitness Machine",
    "183e": "Physical Activity Monitor",
    "1108": "Headset",
    "110a": "Audio Source",
    "110b": "Audio Sink",
    "110c": "AVRCP Target",
    "110d": "A2DP",
    "110e": "AVRCP",
    "110f": "AVRCP Controller",
    "1112": "Headset (alt)",
    "111e": "Handsfree",
    "fe59": "Nordic Secure DFU",
}

CHARACTERISTIC_NAMES: Dict[str, str] = {
    "2a00": "Device Name",
    "2a01": "Appearance",
    "2a04": "Peripheral Preferred Connection Parameters",
    "2a05": "Service Changed",
    "2a19": "Battery Level",
    "2a24": "Model Number String",
    "2a25": "Serial Number String",
    "2a26": "Firmware Revision String",
    "2a27": "Hardware Revision String",
    "2a28": "Software Revision String",
    "2a29": "Manufacturer Name String",
    "2a37": "Heart Rate Measurement",
    "2a38": "Body Sensor Location",
    "2a4a": "HID Information",
    "2a4b": "Report Map",
    "2a4c": "HID Control Point",
    "2a4d": "Report",
    "2a4e": "Protocol Mode",
    "2a5b": "CSC Measurement",
    "2a63": "Cycling Power Measurement",
    "2a6e": "Temperature",
    "2a6f": "Humidity",
}

# Vendor 128-bit services worth surfacing in the UI.
VENDOR_SERVICE_NAMES: Dict[str, str] = {
    "0000fe59-0000-1000-8000-00805f9b34fb": "Nordic Secure DFU",
    "0000ffe0-0000-1000-8000-00805f9b34fb": "HM-10 / CC254x UART",
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART Service",
}


def describe_service(value: object) -> str:
    short = uuid16(value)
    if short and short in SERVICE_NAMES:
        return SERVICE_NAMES[short]
    normal = normalize_uuid(value)
    return VENDOR_SERVICE_NAMES.get(normal, "")


def describe_characteristic(value: object) -> str:
    short = uuid16(value)
    if short and short in CHARACTERISTIC_NAMES:
        return CHARACTERISTIC_NAMES[short]
    return ""


def compact_uuid(value: object) -> str:
    short = uuid16(value)
    return short.upper() if short else normalize_uuid(value).upper()
