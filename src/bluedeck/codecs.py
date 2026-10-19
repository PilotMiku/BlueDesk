"""Small codecs and protocol helpers used by panels and the GATT console."""
from __future__ import annotations

import csv
import io
import math
import re
from typing import Iterable, List, Optional


class CodecError(ValueError):
    pass


def parse_hex(text: str) -> bytes:
    """Parse HEX input such as 01 02 ff, 0x0102ff or 01:02:FF."""
    cleaned = re.sub(r"0x", "", (text or "").strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,:;\-]", "", cleaned)
    if not cleaned:
        return b""
    if len(cleaned) % 2:
        raise CodecError("HEX 长度必须为偶数")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise CodecError("包含非 HEX 字符: %s" % exc) from exc


def format_hex(data: bytes, separator: str = " ", upper: bool = True) -> str:
    rendered = separator.join("%02X" % b for b in data)
    return rendered if upper else rendered.lower()


def hexdump(data: bytes, width: int = 16) -> str:
    lines: List[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hex_part = " ".join("%02X" % b for b in chunk).ljust(width * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append("%08X  %s  |%s|" % (offset, hex_part, ascii_part))
    return "\n".join(lines)


def encode_payload(text: str, mode: str = "hex") -> bytes:
    if mode.lower() == "hex":
        return parse_hex(text)
    return text.encode("utf-8")


def decode_payload(data: bytes, mode: str = "hex") -> str:
    if mode.lower() == "hex":
        return format_hex(data)
    return data.decode("utf-8", errors="replace")


def checksum8_xor(data: Iterable[int]) -> int:
    value = 0
    for byte in data:
        value ^= int(byte) & 0xFF
    return value


def checksum8_sum(data: Iterable[int]) -> int:
    return sum(int(b) & 0xFF for b in data) & 0xFF


def build_dpi_packet(dpi: int, profile: int = 1, header: int = 0xA5) -> bytes:
    """Build an EXAMPLE vendor DPI packet, not a universal standard.

    Frame: A5 01 <profile> <dpi lo> <dpi hi> <xor checksum>
    Real mice use HID++ / vendor GATT protocols. Replace this builder and the
    UUID in protocols/vendor_examples.py with the protocol from the vendor SDK.
    """
    if not 100 <= dpi <= 32000:
        raise CodecError("DPI 必须在 100..32000 之间")
    if not 1 <= profile <= 5:
        raise CodecError("配置档必须在 1..5 之间")
    body = bytes([header & 0xFF, 0x01, profile & 0xFF, dpi & 0xFF, (dpi >> 8) & 0xFF])
    return body + bytes([checksum8_xor(body)])


def parse_battery_level(data: bytes) -> Optional[int]:
    if not data:
        return None
    value = data[0]
    if value > 100:
        return None
    return value


def parse_heart_rate(data: bytes) -> Optional[int]:
    """Parse the Bluetooth SIG Heart Rate Measurement characteristic."""
    if len(data) < 2:
        return None
    flags = data[0]
    if flags & 0x01:
        if len(data) < 3:
            return None
        return int.from_bytes(data[1:3], "little")
    return data[1]


def parse_utf8(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").rstrip("\x00")


def rssi_to_distance(rssi: Optional[int], tx_power: int = -59, path_loss: float = 2.0) -> Optional[float]:
    if rssi is None:
        return None
    try:
        return round(math.pow(10.0, (tx_power - float(rssi)) / (10.0 * path_loss)), 2)
    except (ValueError, OverflowError):
        return None


def csv_escape_rows(rows: Iterable[Iterable[object]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
