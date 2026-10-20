from __future__ import annotations

import asyncio

import pytest

from bluedesk import scan_service


@pytest.mark.asyncio
async def test_failed_scan_cleans_up_and_explains_permission(monkeypatch):
    class Scanner:
        stopped = False

        def __init__(self, **kwargs):
            pass

        async def start(self):
            raise RuntimeError("BLE is not authorized - check macOS privacy settings")

        async def stop(self):
            Scanner.stopped = True

    monkeypatch.setattr(scan_service, "BleakScanner", Scanner)
    service = scan_service.ScanService(None)
    errors = []
    service.error.connect(errors.append)
    service._active = True
    await service._scan()
    assert not service.active
    assert Scanner.stopped
    assert "权限" in errors[0]
    assert service._scanner is None


@pytest.mark.asyncio
async def test_cancelling_scan_releases_scanner(monkeypatch):
    started = asyncio.Event()

    class Scanner:
        stopped = False

        def __init__(self, **kwargs):
            pass

        async def start(self):
            started.set()

        async def stop(self):
            Scanner.stopped = True

    monkeypatch.setattr(scan_service, "BleakScanner", Scanner)
    service = scan_service.ScanService(None)
    service._active = True
    task = asyncio.create_task(service._scan())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert Scanner.stopped
    assert not service.active
