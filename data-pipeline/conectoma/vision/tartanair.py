"""TartanAir V2, left front camera: which frames are fetched, and fetching exactly those.

The archives are one per environment, difficulty and modality (image, depth, seg, flow). The selection is a
rule over their members: every trajectory keeps clips of consecutive frames centred at fixed fractions of
its length. Clips are planned from the image archive's listing, and a clip's members are its frames in the
image, depth and seg archives, the flow between each consecutive pair, and the trajectory's poses.

A clip is stored as one uncompressed ZIP of its members, byte for byte as fetched, and logged as one JSON line
carrying the CRC32 of every member; a rerun skips the clips the log holds, so the multi-hour fetch resumes
where it stopped.
"""

from __future__ import annotations

import csv
import json
import os
import queue
import re
import threading
import zipfile
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from conectoma.vision.remote_zip import RemoteZip

CLIPS_IN_FLIGHT = 4  # about 50 MB per clip in memory while its members arrive

FRAME = re.compile(r"^(?P<env>[^/]+)/Data_(?P<difficulty>easy|hard)/(?P<trajectory>P\d+)/image_lcam_front/"
                   r"(?P<index>\d{6})_lcam_front\.png$")


@dataclass(frozen=True)
class Clip:
    environment: str
    difficulty: str
    trajectory: str
    start: int
    length: int
    trajectory_frames: int

    @property
    def key(self) -> str:
        return f"{self.environment}/{self.difficulty}/{self.trajectory}/{self.start:06d}"

    def frames(self) -> range:
        return range(self.start, self.start + self.length)


def read_index(path: Path) -> list[tuple[str, str, str, int]]:
    """The pinned archive index: (environment, difficulty, modality, bytes)."""
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            environment, difficulty, modality, size = line.rstrip("\n").split("\t")
            rows.append((environment, difficulty, modality, int(size)))
    return rows


def archive_url(endpoint: str, environment: str, difficulty: str, modality: str, camera: str) -> str:
    return f"{endpoint}{environment}/Data_{difficulty}/{modality}_{camera}.zip"


def plan_clips(image_names: list[str], length: int, centres: list[float]) -> list[Clip]:
    """Clips of `length` consecutive frames per trajectory, centred at fractions of the trajectory.

    A trajectory shorter than the clip gives nothing; one too short for disjoint clips at every centre gives
    one clip at the middle, so no frame is ever in two clips.
    """
    frames: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for name in image_names:
        match = FRAME.match(name)
        if match:
            frames[(match["env"], match["difficulty"], match["trajectory"])].append(int(match["index"]))
    clips = []
    for (environment, difficulty, trajectory), indices in sorted(frames.items()):
        indices.sort()
        n = len(indices)
        if n < length or indices != list(range(indices[0], indices[0] + n)):
            # too short, or frames missing from the listing: planned from nothing rather than from a gap
            continue
        wanted = centres if n >= length * len(centres) else [0.5]
        starts = []
        for centre in wanted:
            start = min(max(round(centre * n) - length // 2, 0), n - length)
            if all(abs(start - s) >= length for s in starts):
                starts.append(start)
        for start in starts:
            clips.append(Clip(environment, difficulty, trajectory, indices[0] + start, length, n))
    return clips


def clip_members(clip: Clip, camera: str) -> dict[str, list[str]]:
    """The member names a clip needs, per modality archive."""
    base = f"{clip.environment}/Data_{clip.difficulty}/{clip.trajectory}"
    frames = list(clip.frames())
    return {
        "image": [f"{base}/image_{camera}/{i:06d}_{camera}.png" for i in frames]
        + [f"{base}/pose_{camera}.txt"],
        "depth": [f"{base}/depth_{camera}/{i:06d}_{camera}_depth.png" for i in frames],
        "seg": [f"{base}/seg_{camera}/{i:06d}_{camera}_seg.png" for i in frames],
        # flow from each frame to the next inside the clip
        "flow": [f"{base}/flow_{camera}/{i:06d}_{i + 1:06d}_flow.png" for i in frames[:-1]],
    }


class FetchLog:
    """Append-only record of the clips written; a rerun reads it and skips them.

    One line per clip, carrying the CRC32 each of its members was verified against. The file stays open and
    is flushed per clip, from one thread (the writer) under a lock.
    """

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


def clip_path(root: Path, clip: Clip) -> Path:
    return root / clip.environment / clip.difficulty / clip.trajectory / f"clip_{clip.start:06d}.zip"


def write_clip(path: Path, members: dict[str, bytes]) -> int:
    """One stored (uncompressed) ZIP per clip, members byte for byte as fetched, written atomically.

    E: sustains about 18 MB/s written as one file and about 5 MB/s as many small ones (measured: 200 files
    of 700 kB took 29.5 s, the same bytes as one archive 7.8 s), so a clip is one file, not 128.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    os.replace(partial, path)
    return sum(len(v) for v in members.values())


def fetch_environment(config: dict, environment: str, difficulty: str, root: Path, log: FetchLog,
                      workers: int = 12) -> dict:
    """Plan and fetch the clips of one environment and difficulty. Returns what was planned and fetched.

    Members are read in parallel into memory and checked against their CRC32; a clip is handed to a writer
    thread only when every member arrived, so the next clip downloads while this one is written. A clip
    with a failed or missing member is not written and not logged, so a rerun tries it again.
    """
    endpoint, camera = config["endpoint"], config["camera"]
    archives = {m: RemoteZip(archive_url(endpoint, environment, difficulty, m, camera))
                for m in config["modalities"]}
    clips = plan_clips(archives["image"].names(), config["clip_length"], config["clip_centres"])
    report = {"environment": environment, "difficulty": difficulty, "clips": [asdict(c) for c in clips],
              "missing": [], "failed": {}, "bytes": 0, "skipped": 0}
    pending: queue.Queue = queue.Queue(maxsize=3)
    written: list[int] = []

    def writer() -> None:
        while (item := pending.get()) is not None:
            clip, data, crcs = item
            size = write_clip(clip_path(root, clip), data)
            log.record(clip.key, crcs, size)
            written.append(size)

    def submit(pool: ThreadPoolExecutor, clip: Clip) -> tuple[Clip, dict, list[str]]:
        jobs, missing = {}, []
        for modality, names in clip_members(clip, camera).items():
            archive = archives[modality]
            for name in names:
                if name in archive.members:
                    jobs[pool.submit(archive.read, name)] = (name, archive.members[name].crc)
                else:
                    missing.append(name)
        return clip, jobs, missing

    def finish(clip: Clip, jobs: dict, missing: list[str]) -> None:
        data, crcs, failed = {}, {}, {}
        for future in as_completed(jobs):
            name, crc = jobs[future]
            try:
                data[name] = future.result()
                crcs[name] = crc
            except Exception as error:  # recorded; the clip is retried on the next run
                failed[name] = str(error)
        report["missing"].extend(missing)
        report["failed"].update(failed)
        if not missing and not failed:
            pending.put((clip, data, crcs))

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # several clips in flight, so the pool never drains while one clip waits for its slowest member
            window: deque = deque()
            for clip in clips:
                if clip.key in log.done:
                    report["skipped"] += 1
                    continue
                window.append(submit(pool, clip))
                if len(window) >= CLIPS_IN_FLIGHT:
                    finish(*window.popleft())
            while window:
                finish(*window.popleft())
    finally:
        pending.put(None)
        thread.join()
    report["bytes"] = sum(written)
    return report


def write_clip_table(clips: list[dict], path: Path) -> None:
    """The planned clips as a table, the input of the split and case stages."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Clip.__dataclass_fields__))
        writer.writeheader()
        for clip in clips:
            writer.writerow(clip)
