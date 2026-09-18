"""Fetching clips from remote archives into one stored ZIP per clip, resumably. Shared by every source.

A source says which archives hold which members of a clip (`ClipSpec`: a key, where the clip archive goes,
and member names per archive). This module fetches the members in parallel, verifies each against the CRC32
its archive records, and hands a clip to a writer thread only when every member arrived, so the next clip
downloads while this one is written; several clips are kept in flight so the pool never drains waiting for one
clip's slowest member. A clip with a failed or missing member is neither written nor logged, and a rerun
tries it again.

Measured constraints behind the design (docs/architecture/05_vision-data.md):
- the data disk sustains about 18 MB/s written as one file and about 5 MB/s as many small ones, so a clip is
  one file of about 50 MB, not 128;
- reopening the log per record made the log the bottleneck (every close is scanned), so it stays open;
- a job started by Task Scheduler at its default priority has its disk writes starved; register it at
  normal priority.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import zipfile
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from conectoma.vision.remote_zip import RemoteZip

CLIPS_IN_FLIGHT = 4  # about 50 MB per clip held in memory while its members arrive


@dataclass
class ClipSpec:
    key: str
    path: Path
    members: dict[str, list[str]]           # archive name -> member names
    rename: Callable[[str], str] | None = field(default=None, repr=False)   # member name inside the clip


class FetchLog:
    """Append-only record of the clips written; a rerun reads it and skips them."""

    def __init__(self, path: Path):
        self.path = path
        self.done: set[str] = set()
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self.done.add(json.loads(line)["clip"])
                    except (json.JSONDecodeError, KeyError):
                        continue  # a line cut by a crash: that clip is simply fetched again
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def record(self, clip: str, members: dict[str, int], size: int) -> None:
        line = json.dumps({"clip": clip, "bytes": size, "crc32": {k: f"{v:08x}" for k, v in members.items()}})
        with self._lock:
            self._handle.write(line + "\n")
            self._handle.flush()
            self.done.add(clip)

    def close(self) -> None:
        with self._lock:
            self._handle.close()


def write_clip(path: Path, members: dict[str, bytes]) -> int:
    """One stored (uncompressed) ZIP per clip, members byte for byte as fetched, written atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    os.replace(partial, path)
    return sum(len(v) for v in members.values())


def fetch_clips(archives: dict[str, RemoteZip], clips: list[ClipSpec], log: FetchLog,
                workers: int = 12) -> dict:
    """Fetch clips from archives into clip archives. Returns what was missing, failed and written."""
    report = {"missing": [], "failed": {}, "bytes": 0, "skipped": 0, "written": 0}
    pending: queue.Queue = queue.Queue(maxsize=3)
    written: list[int] = []

    def writer() -> None:
        while (item := pending.get()) is not None:
            spec, data, crcs = item
            size = write_clip(spec.path, data)
            log.record(spec.key, crcs, size)
            written.append(size)

    def submit(pool: ThreadPoolExecutor, spec: ClipSpec) -> tuple[ClipSpec, dict, list[str]]:
        jobs, missing = {}, []
        for archive_name, names in spec.members.items():
            archive = archives[archive_name]
            for name in names:
                if name in archive.members:
                    jobs[pool.submit(archive.read, name)] = (name, archive.members[name].crc)
                else:
                    missing.append(name)
        return spec, jobs, missing

    def finish(spec: ClipSpec, jobs: dict, missing: list[str]) -> None:
        data, crcs, failed = {}, {}, {}
        for future in as_completed(jobs):
            name, crc = jobs[future]
            try:
                inside = spec.rename(name) if spec.rename else name
                data[inside] = future.result()
                crcs[name] = crc
            except Exception as error:  # recorded; the clip is retried on the next run
                failed[name] = str(error)
        report["missing"].extend(missing)
        report["failed"].update(failed)
        if not missing and not failed:
            pending.put((spec, data, crcs))

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            window: deque = deque()
            for spec in clips:
                if spec.key in log.done:
                    report["skipped"] += 1
                    continue
                window.append(submit(pool, spec))
                if len(window) >= CLIPS_IN_FLIGHT:
                    finish(*window.popleft())
            while window:
                finish(*window.popleft())
    finally:
        pending.put(None)
        thread.join()
    report["bytes"] = sum(written)
    report["written"] = len(written)
    return report
