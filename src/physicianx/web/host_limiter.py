"""Per-host asyncio semaphores to cap concurrent requests per origin during crawls."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse


class HostLimiter:
    """Acquire one slot per URL's hostname before a batch fetch; release after."""

    def __init__(self, max_per_host: int) -> None:
        self.max_per_host = max_per_host
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._registry = asyncio.Lock()

    @staticmethod
    def _host(url: str) -> str:
        return urlparse(url).netloc or "_"

    async def acquire(self, url: str) -> None:
        host = self._host(url)
        async with self._registry:
            if host not in self._sems:
                self._sems[host] = asyncio.Semaphore(self.max_per_host)
            sem = self._sems[host]
        await sem.acquire()

    def release(self, url: str) -> None:
        host = self._host(url)
        sem = self._sems.get(host)
        if sem is not None:
            sem.release()
