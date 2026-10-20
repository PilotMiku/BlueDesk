from __future__ import annotations

from bluedesk.models import DeviceInfo, DeviceType, Transport
from bluedesk.protocols import FeatureStatus, ProtocolRegistry


def test_feature_matrix_standard_and_vendor():
    device = DeviceInfo(address="aa", device_type=DeviceType.MOUSE, transport=Transport.BLE)
    registry = ProtocolRegistry()
    features = registry.features(device)
    assert "volume" not in features
    assert features["dpi"].status is FeatureStatus.VENDOR_REQUIRED
    assert features["battery"].status is FeatureStatus.STANDARD


def test_example_protocol_only_matches_tagged_device():
    registry = ProtocolRegistry()
    device = DeviceInfo(address="aa", device_type=DeviceType.MOUSE, transport=Transport.BLE)
    assert not registry.matched(device)
    device.metadata["vendor_protocol"] = "example-dpi"
    assert registry.matched(device)
    assert registry.features(device)["dpi"].status is FeatureStatus.SUPPORTED
