from __future__ import annotations

import asyncio
import csv
import json
import os
from typing import Any, Iterable, Protocol

import aiofiles

_registry_lock = asyncio.Lock()
_path_locks: dict[str, asyncio.Lock] = {}


async def _lock_for_path(path: str) -> asyncio.Lock:
    key = os.path.abspath(path)
    async with _registry_lock:
        if key not in _path_locks:
            _path_locks[key] = asyncio.Lock()
        return _path_locks[key]


async def append_jsonl(path: str, record: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = await _lock_for_path(path)
    async with lock:
        async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
            await f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def append_jsonl_records(path: str, records: Iterable[Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = await _lock_for_path(path)
    async with lock:
        async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
            for record in records:
                await f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def append_text_line(path: str, line: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = await _lock_for_path(path)
    async with lock:
        async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
            await f.write(line + "\n")


async def append_json(path: str, record: Any) -> None:
    await append_jsonl(path, record)


def resolve_output_path(path: str) -> str:
    return path


class _JobLinkLike(Protocol):
    title: str
    url: str


def write_job_links_csv(path: str, jobs: Iterable[_JobLinkLike]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rows = [{"Title": j.title, "URL": j.url} for j in jobs]
    with open(path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Title", "URL"])
        writer.writeheader()
        writer.writerows(rows)
