"""Concurrency tests for web.host_limiter.HostLimiter."""

from __future__ import annotations

import asyncio
import unittest

from physicianx.web.host_limiter import HostLimiter


class TestHostLimiter(unittest.TestCase):
    def test_caps_concurrent_acquires_per_host(self) -> None:
        async def _run() -> tuple[int, int]:
            limiter = HostLimiter(max_per_host=2)
            url = "https://example.com/a"
            in_flight = 0
            high_water = 0
            lock = asyncio.Lock()

            async def worker() -> None:
                nonlocal in_flight, high_water
                await limiter.acquire(url)
                async with lock:
                    in_flight += 1
                    high_water = max(high_water, in_flight)
                # Yield so other tasks have a chance to enter.
                await asyncio.sleep(0.01)
                async with lock:
                    in_flight -= 1
                limiter.release(url)

            await asyncio.gather(*(worker() for _ in range(8)))
            return in_flight, high_water

        in_flight, high_water = asyncio.run(_run())
        self.assertEqual(in_flight, 0)
        self.assertLessEqual(high_water, 2)
        self.assertGreaterEqual(high_water, 1)

    def test_separate_hosts_do_not_share_budget(self) -> None:
        async def _run() -> int:
            limiter = HostLimiter(max_per_host=1)
            in_flight = 0
            high_water = 0
            lock = asyncio.Lock()

            async def worker(url: str) -> None:
                nonlocal in_flight, high_water
                await limiter.acquire(url)
                async with lock:
                    in_flight += 1
                    high_water = max(high_water, in_flight)
                await asyncio.sleep(0.01)
                async with lock:
                    in_flight -= 1
                limiter.release(url)

            # Two distinct hosts × two tasks each. Cap is 1 per host, but 2 hosts
            # should be able to run in parallel → high water mark of 2.
            await asyncio.gather(
                worker("https://a.example.com/x"),
                worker("https://a.example.com/y"),
                worker("https://b.example.com/x"),
                worker("https://b.example.com/y"),
            )
            return high_water

        high_water = asyncio.run(_run())
        self.assertEqual(high_water, 2)

    def test_empty_netloc_is_grouped(self) -> None:
        async def _run() -> int:
            limiter = HostLimiter(max_per_host=1)
            in_flight = 0
            high_water = 0
            lock = asyncio.Lock()

            async def worker(url: str) -> None:
                nonlocal in_flight, high_water
                await limiter.acquire(url)
                async with lock:
                    in_flight += 1
                    high_water = max(high_water, in_flight)
                await asyncio.sleep(0.01)
                async with lock:
                    in_flight -= 1
                limiter.release(url)

            # Two URLs without netloc share the "_" bucket → cap=1.
            await asyncio.gather(worker("/relative/a"), worker("/relative/b"))
            return high_water

        self.assertEqual(asyncio.run(_run()), 1)


if __name__ == "__main__":
    unittest.main()
