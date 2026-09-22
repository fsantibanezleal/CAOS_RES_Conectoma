"""The right camera of the TartanAir clips the cases use: the stereo pair M02 needs.

The corpus fetched the left front camera only, because that is the one the release distributes optical
flow for (`config/vision.yaml`). M02 is semi-global matching on a rectified stereo pair, so it needs the
right front camera of the same frames, and only of the clips the cases actually draw: 126 clips of 32
frames, one modality.

Verified at tartanair.org/modalities.html on 2026-09-22: 12 cameras arranged as two stereo sets of six,
**baseline 0.25 m**, pinhole, 640 x 640, 90 degree field of view, 10 Hz, focal length 320 pixels,
principal point (320, 320). The pair is rectified by construction, being a synthetic rig, so nothing here
rectifies anything and no rectification is invented.

Members land in `<data root>/vision/tartanair/stereo/<environment>/<difficulty>/<trajectory>/
clip_<start>.zip`, beside the left-camera clips and never committed. The fetch is resumable in the same
way as every other: a clip already written is skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

from conectoma.vision.clipstore import ClipSpec, FetchLog, fetch_clips
from conectoma.vision.remote_zip import RemoteZip
from conectoma.vision.tartanair import Clip, archive_url

CAMERA = "rcam_front"
BASELINE_M = 0.25          # tartanair.org/modalities.html, read 2026-09-22
FOCAL_PX = 320.0           # at the source resolution of 640 x 640


def case_clips(cases_json: Path, wanted: list[str] | None = None, length: int = 32) -> list[Clip]:
    """The distinct TartanAir clips the cases draw, from the committed case summary.

    The trajectory length is not recorded per case and is not needed here: the clip's own frames are what
    is fetched, so it is left at zero rather than guessed.
    """
    summary = json.loads(Path(cases_json).read_text(encoding="utf-8"))
    out: dict[str, Clip] = {}
    for case_id, case in summary["cases"].items():
        if case.get("contract") != "tartanair" or (wanted and case_id not in wanted):
            continue
        for item in case.get("items", []):
            environment, difficulty, trajectory, start = item.split("/")
            clip = Clip(environment=environment, difficulty=difficulty, trajectory=trajectory,
                        start=int(start), length=length, trajectory_frames=0)
            out[clip.key] = clip
    return [out[key] for key in sorted(out)]


def members(clip: Clip) -> dict[str, list[str]]:
    """The right-camera image members of one clip, plus that camera's pose file."""
    base = f"{clip.environment}/Data_{clip.difficulty}/{clip.trajectory}"
    frames = list(clip.frames())
    return {"image": [f"{base}/image_{CAMERA}/{i:06d}_{CAMERA}.png" for i in frames]
            + [f"{base}/pose_{CAMERA}.txt"]}


def clip_path(root: Path, clip: Clip) -> Path:
    return root / clip.environment / clip.difficulty / clip.trajectory / f"clip_{clip.start:06d}.zip"


def fetch(config: dict, clips: list[Clip], root: Path, log: FetchLog, workers: int = 12) -> dict:
    """Fetch the right camera of `clips`, one environment and difficulty at a time."""
    endpoint = config["endpoint"]
    report = {"clips": len(clips), "bytes": 0, "written": 0, "skipped": 0, "missing": [], "failed": {}}
    pairs = sorted({(clip.environment, clip.difficulty) for clip in clips})
    for environment, difficulty in pairs:
        mine = [clip for clip in clips if (clip.environment, clip.difficulty) == (environment, difficulty)]
        archives = {"image": RemoteZip(archive_url(endpoint, environment, difficulty, "image", CAMERA))}
        specs = [ClipSpec(f"{clip.key}/{CAMERA}", clip_path(root, clip), members(clip)) for clip in mine]
        one = fetch_clips(archives, specs, log, workers)
        report["bytes"] += one["bytes"]
        report["written"] += one["written"]
        report["skipped"] += one["skipped"]
        report["missing"] += one["missing"]
        report["failed"] |= one["failed"]
        print(f"{environment} {difficulty}: {len(mine)} clips, {one['bytes'] / 1e9:.2f} GB, "
              f"{one['skipped']} already done, {len(one['failed'])} failed", flush=True)
    return report
