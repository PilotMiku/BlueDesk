"""A dedicated asyncio event loop for Bleak operations."""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any, Callable, Coroutine, Optional


class AsyncRunner:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._closed = False

    @property
    def running(self) -> bool:
        return bool(self._loop and self._loop.is_running() and not self._closed)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="bluedesk-asyncio", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                loop.close()

    def submit(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        if not self.running or self._loop is None:
            coro.close()
            raise RuntimeError("异步事件循环尚未启动")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call_soon_threadsafe(self, callback: Callable[..., Any], *args: Any) -> None:
        if self.running and self._loop is not None:
            self._loop.call_soon_threadsafe(callback, *args)

    def create_task(self, factory: Callable[[], Coroutine[Any, Any, Any]]) -> concurrent.futures.Future:
        if not self.running or self._loop is None:
            raise RuntimeError("异步事件循环尚未启动")
        future: concurrent.futures.Future = concurrent.futures.Future()

        def runner() -> None:
            try:
                task = self._loop.create_task(factory())  # type: ignore[union-attr]
                task.add_done_callback(
                    lambda done: future.set_result(done.result())
                    if not done.cancelled() and done.exception() is None
                    else future.set_exception(done.exception() or RuntimeError("任务取消"))
                )
            except Exception as exc:
                future.set_exception(exc)

        self._loop.call_soon_threadsafe(runner)
        return future

    def stop(self, timeout: float = 4.0) -> None:
        self._closed = True
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=timeout)
        self._loop = None
        self._thread = None
