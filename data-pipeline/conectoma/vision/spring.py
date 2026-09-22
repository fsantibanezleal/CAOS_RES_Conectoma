"""Spring (train split, left camera): which frames are fetched, and fetching exactly those.

The archives are one per modality over all 37 training scenes (frames, reference-frame disparity, the
evaluation maps, camera data). The same clip rule as TartanAir applies per scene: clips of 32 consecutive
frames centred at a quarter and three quarters of the scene. A clip's members are its frames, disparities
and sky maps, the non-rigid-motion maps between consecutive frames, and the scene's camera files.

Spring is a transfer domain: test only. Its metric depth comes from disparity with the 6.5 cm baseline of the
dataset paper, as the authors' own code computes it (`render.spring_depth`).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from conectoma.vision.clipstore import ClipSpec, FetchLog, fetch_clips
from conectoma.vision.remote_zip import RemoteZip

FRAME = re.compile(r"^spring/train/(?P<scene>\d{4})/frame_left/frame_left_(?P<index>\d{4})\.png$")
ACCESS = "{dataverse}/api/access/datafile/{id}"


def plan(frame_names: list[str], length: int, centres: list[float]) -> list[tuple[str, int]]:
    """(scene, first frame) of every clip, by the same rule as TartanAir."""
    frames: dict[str, list[int]] = defaultdict(list)
    for name in frame_names:
        match = FRAME.match(name)
        if match:
            frames[match["scene"]].append(int(match["index"]))
    clips = []
    for scene, indices in sorted(frames.items()):
        indices.sort()
        n = len(indices)
        if n < length or indices != list(range(indices[0], indices[0] + n)):
            continue
        wanted = centres if n >= length * len(centres) else [0.5]
        starts: list[int] = []
        for centre in wanted:
            start = min(max(round(centre * n) - length // 2, 0), n - length)
            if all(abs(start - s) >= length for s in starts):
                starts.append(start)
        clips.extend((scene, indices[0] + s) for s in starts)
    return clips


def members(scene: str, start: int, length: int) -> dict[str, list[str]]:
    base = f"spring/train/{scene}"
    frames = range(start, start + length)
    return {
        "frame": [f"{base}/frame_left/frame_left_{i:04d}.png" for i in frames],
        "disp": [f"{base}/disp1_left/disp1_left_{i:04d}.dsp5" for i in frames],
        "maps": [f"{base}/maps/skymap_left/skymap_left_{i:04d}.png" for i in frames]
        + [f"{base}/maps/rigidmap_FW_left/rigidmap_FW_left_{i:04d}.png" for i in list(frames)[:-1]],
        "cam": [f"{base}/cam_data/{f}.txt" for f in ("intrinsics", "extrinsics", "focaldistance")],
    }


def clip_path(root: Path, scene: str, start: int) -> Path:
    return root / scene / f"clip_{start:04d}.zip"


def fetch(config: dict, root: Path, log: FetchLog, workers: int = 12) -> dict:
    """Plan and fetch every Spring clip. Returns what was planned and fetched."""
    archives = {kind: RemoteZip(ACCESS.format(dataverse=config["dataverse"], id=spec["id"]))
                for kind, spec in config["archives"].items()}
    clips = plan(archives["frame"].names(), config["clip_length"], config["clip_centres"])
    specs = [ClipSpec(f"spring/{scene}/{start:04d}", clip_path(root, scene, start),
                      members(scene, start, config["clip_length"])) for scene, start in clips]
    report = fetch_clips(archives, specs, log, workers)
    report["clips"] = [{"scene": scene, "start": start} for scene, start in clips]
    return report
