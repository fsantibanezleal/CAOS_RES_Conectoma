"""Hypersim (official test partition): which images are fetched, fetching exactly those, and their depth.

Hypersim is indoor, photoreal, and not video: its cameras are keyframes along a path, so a scene is a set of
single images, used for the single-image indoor condition (case C04) and as the one source with semantic
labels. The official scene-level split is respected: only its test partition is taken, so nothing here was
seen by a model trained on Hypersim's own training scenes. Per test scene: camera cam_00, every fifth frame
of the public release, as one clip archive of the tonemapped colour, the distance image, and the semantic
and instance segmentations.

Depth. Hypersim's `depth_meters` is the Euclidean distance from the optical centre, not planar depth. Its
cameras are tilt-shifted, so the rays come from the scene's own `M_cam_from_uv` matrix (the dataset's
ray-casting notebook): pixel centres in u, v on [-1, 1] with v pointing up, ray `d = M [u, v, 1]`, the camera
looking down -z. Planar depth is the distance times |d_z| / |d|.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from conectoma.vision.clipstore import ClipSpec, FetchLog, fetch_clips
from conectoma.vision.remote_zip import RemoteZip

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(line for line in handle if not line.startswith("#")))


def test_images(camera: str = "cam_00", every: int = 5) -> dict[str, list[int]]:
    """Frames per test scene: the given camera, every `every`-th frame of the public release."""
    frames: dict[str, list[int]] = defaultdict(list)
    for row in _rows(CONFIG_DIR / "hypersim_test_split.csv"):
        if row["camera_name"] == camera and int(row["frame_id"]) % every == 0:
            frames[row["scene_name"]].append(int(row["frame_id"]))
    return {scene: sorted(ids) for scene, ids in sorted(frames.items())}


def cameras() -> dict[str, dict]:
    out = {}
    for row in _rows(CONFIG_DIR / "hypersim_cameras.csv"):
        out[row["scene_name"]] = {
            "width": int(float(row["settings_output_img_width"])),
            "height": int(float(row["settings_output_img_height"])),
            "meters_per_asset_unit": float(row["settings_units_info_meters_scale"]),
            "M_cam_from_uv": np.array([[float(row[f"M_cam_from_uv_{i}{j}"]) for j in range(3)]
                                       for i in range(3)]),
        }
    return out


def planar_factor(camera: dict) -> np.ndarray:
    """Per pixel, planar depth over Euclidean distance: |d_z| / |d| for the ray d through the pixel centre."""
    w, h = camera["width"], camera["height"]
    u = np.linspace(-1 + 1 / w, 1 - 1 / w, w)
    v = np.linspace(-1 + 1 / h, 1 - 1 / h, h)[::-1]
    uu, vv = np.meshgrid(u, v)
    rays = np.einsum("ij,jhw->ihw", camera["M_cam_from_uv"], np.stack([uu, vv, np.ones_like(uu)]))
    return (np.abs(rays[2]) / np.linalg.norm(rays, axis=0)).astype(np.float32)


def members(scene: str, camera: str, frames: list[int]) -> dict[str, list[str]]:
    image = f"{scene}/images/scene_{camera}"
    names = []
    for i in frames:
        names += [f"{image}_final_preview/frame.{i:04d}.color.jpg",
                  f"{image}_geometry_hdf5/frame.{i:04d}.depth_meters.hdf5",
                  f"{image}_geometry_hdf5/frame.{i:04d}.semantic.hdf5",
                  f"{image}_geometry_hdf5/frame.{i:04d}.semantic_instance.hdf5"]
    return {scene: names}


def fetch(config: dict, root: Path, log: FetchLog, workers: int = 12) -> dict:
    """Fetch every selected test image, one clip archive per scene."""
    selection = test_images(config["camera"], config["every"])
    specs, archives = [], {}
    for scene, frames in selection.items():
        archives[scene] = RemoteZip(f"{config['scenes_url']}{scene}.zip")
        camera = config["camera"]
        specs.append(ClipSpec(f"hypersim/{scene}/{camera}", root / scene / f"{camera}.zip",
                              members(scene, camera, frames)))
    report = fetch_clips(archives, specs, log, workers)
    report["clips"] = [{"scene": s, "frames": f} for s, f in selection.items()]
    return report
