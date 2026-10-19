"""Parsers for platform command output, kept pure for unit testing."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from ..classifier import explain_device
from ..models import ConnectionState, DeviceInfo, Transport


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in ("1", "true", "yes", "y", "attrib_yes", "connected", "ok", "on")


def _find_value(entry: Dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in entry and entry[name] not in (None, ""):
            return entry[name]
    return None


def _synthetic_address(name: str) -> str:
    digest = hashlib.sha1((name or "unknown").strip().lower().encode("utf-8")).hexdigest()
    return "macos:" + digest[:12]


def _walk_device_dicts(node: Any, context: str = "") -> Iterable[
    tuple[Dict[str, Any], str]
]:
    if isinstance(node, dict):
        name = _find_value(node, ("device_name", "name", "DeviceName", "FriendlyName"))
        address = _find_value(
            node,
            ("device_address", "device_addr", "address", "Address", "device_identifier", "identifier"),
        )
        if name and (address or "device_" in " ".join(node.keys())):
            yield node, context
        for key, value in node.items():
            key_lower = str(key).lower()
            if "not_connected" in key_lower or "disconnected" in key_lower:
                child_context = "disconnected"
            elif "connected" in key_lower:
                child_context = "connected"
            else:
                child_context = context
            if isinstance(value, (dict, list)):
                for item in _walk_device_dicts(value, child_context):
                    yield item
    elif isinstance(node, list):
        for item in node:
            for found in _walk_device_dicts(item, context):
                yield found


def parse_system_profiler_bluetooth(raw: Any) -> List[Dict[str, Any]]:
    """Normalise macOS system_profiler SPBluetoothDataType JSON.

    Apple has changed this schema several times. The parser walks both the
    old devices_list layout and the newer device_connected/device_not_connected
    lists, and tolerates a dict or a JSON string.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, (dict, list)):
        return []
    result: List[Dict[str, Any]] = []
    seen = set()
    for entry, context in _walk_device_dicts(raw):
        name = str(
            _find_value(entry, ("device_name", "name", "DeviceName", "FriendlyName")) or ""
        ).strip()
        if not name or name.lower() in ("bluetooth power", "controller"):
            continue
        address = str(
            _find_value(
                entry,
                ("device_address", "device_addr", "address", "Address", "device_identifier", "identifier"),
            )
            or ""
        ).strip()
        if not address:
            address = _synthetic_address(name)
        minor_type = str(
            _find_value(
                entry,
                ("device_minorType", "device_minor_type", "minor_type", "device_type", "type"),
            )
            or ""
        )
        connected = _as_bool(
            _find_value(entry, ("device_connected", "connected", "is_connected"))
        ) or context == "connected"
        paired_raw = _find_value(entry, ("device_paired", "paired", "is_paired"))
        paired = _as_bool(paired_raw) if paired_raw is not None else True
        # system_profiler's list is primarily paired devices; only an explicit
        # false value marks a known-but-unpaired entry.
        key = address.lower() if address else name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "name": name,
                "address": address,
                "minor_type": minor_type,
                "connected": connected,
                "paired": paired,
                "raw": entry,
            }
        )
    return result


def parse_blueutil_paired(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if isinstance(raw, dict):
        raw = raw.get("devices") or raw.get("paired") or []
    if not isinstance(raw, list):
        return []
    result: List[Dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("device_name") or "").strip()
        address = str(entry.get("address") or entry.get("device_address") or "").strip()
        if not name and not address:
            continue
        result.append(
            {
                "name": name or address,
                "address": address or _synthetic_address(name),
                "minor_type": "",
                "connected": _as_bool(entry.get("connected")),
                "paired": _as_bool(entry.get("paired", True)),
                "raw": entry,
            }
        )
    return result


_MAC_RE = re.compile(r"(?:DEV_|&)([0-9A-F]{12})(?=[\\_&]|$)", re.IGNORECASE)


def extract_mac_from_instance_id(instance_id: str) -> Optional[str]:
    text = instance_id or ""
    match = _MAC_RE.search(text)
    if not match:
        # Some PowerShell paths use the address as the final 12 hex digits.
        tail = re.search(r"([0-9A-F]{12})$", text, re.IGNORECASE)
        if not tail:
            return None
        match = tail
    raw = match.group(1).upper()
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def parse_windows_pnp_devices(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    result: List[Dict[str, Any]] = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("FriendlyName") or entry.get("Name") or "").strip()
        instance_id = str(entry.get("InstanceId") or entry.get("DeviceID") or "").strip()
        address = extract_mac_from_instance_id(instance_id)
        if not address or not name:
            continue
        if address in seen:
            continue
        seen.add(address)
        transport = Transport.BLE if "BTHLE" in instance_id.upper() else Transport.CLASSIC
        result.append(
            {
                "name": name,
                "address": address,
                "connected": False,
                "paired": True,
                "transport": transport,
                "status": str(entry.get("Status") or ""),
                "instance_id": instance_id,
            }
        )
    return result


def build_paired_device(
    name: str,
    address: str,
    minor_type: str = "",
    connected: bool = False,
    paired: bool = True,
    transport: Transport = Transport.UNKNOWN,
    platform: str = "unknown",
    source: str = "system",
    metadata: Optional[Dict[str, Any]] = None,
) -> DeviceInfo:
    classification = explain_device(
        name=name,
        platform=platform,
        os_hint=minor_type,
        paired=paired,
        connected=connected,
    )
    return DeviceInfo(
        address=address,
        name=name,
        device_type=classification.device_type,
        transport=transport,
        paired=paired,
        connected=connected,
        state=ConnectionState.CONNECTED if connected else ConnectionState.DISCONNECTED,
        platform=platform,
        source=source,
        confidence=classification.confidence,
        classification_source=classification.source,
        classification_reason=classification.reason,
        metadata=dict(metadata or {}),
    )
