"""Protocol adapters."""

from .base import FeatureAvailability, FeatureStatus, ProtocolAdapter, ProtocolError
from .registry import ProtocolRegistry

__all__ = [
    "FeatureAvailability",
    "FeatureStatus",
    "ProtocolAdapter",
    "ProtocolError",
    "ProtocolRegistry",
]
