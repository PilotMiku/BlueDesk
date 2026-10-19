from __future__ import annotations

import pytest

from bluedeck.codecs import (
    CodecError,
    build_dpi_packet,
    checksum8_xor,
    format_hex,
    hexdump,
    parse_battery_level,
    parse_heart_rate,
    parse_hex,
    rssi_to_distance,
)


def test_parse_hex_formats():
    assert parse_hex("01 02 ff") == b"\x01\x02\xff"
    assert parse_hex("0x0102FF") == b"\x01\x02\xff"
    assert parse_hex("01:02-FF") == b"\x01\x02\xff"
    assert parse_hex("") == b""


def test_parse_hex_errors():
    with pytest.raises(CodecError):
        parse_hex("123")
    with pytest.raises(CodecError):
        parse_hex("GG")


def test_format_and_dump():
    assert format_hex(b"\x01\xab") == "01 AB"
    assert "00000000" in hexdump(b"abc")
    assert "|abc|" in hexdump(b"abc")


def test_checksum_and_dpi_packet():
    assert checksum8_xor([0x01, 0x02, 0x03]) == 0
    packet = build_dpi_packet(1600, profile=2)
    assert packet[0] == 0xA5
    assert packet[1] == 0x01
    assert packet[2] == 2
    assert packet[3:5] == (1600).to_bytes(2, "little")
    assert packet[-1] == checksum8_xor(packet[:-1])
    with pytest.raises(CodecError):
        build_dpi_packet(50)


def test_parse_battery_and_heart_rate():
    assert parse_battery_level(b"\x4b") == 75
    assert parse_battery_level(b"\xff") is None
    assert parse_heart_rate(b"\x00\x48") == 72
    assert parse_heart_rate(b"\x01\x2c\x01") == 300


def test_rssi_distance():
    assert rssi_to_distance(None) is None
    one_meter = rssi_to_distance(-59, tx_power=-59)
    assert one_meter == 1.0
    assert rssi_to_distance(-80, tx_power=-59) > one_meter
