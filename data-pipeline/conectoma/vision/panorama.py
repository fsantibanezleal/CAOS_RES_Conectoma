"""Pure camera rotation rendered from TartanAir's equirectangular panoramas (case C13).

A camera turning about its optical centre sees no parallax: every scene point moves by the same homography
`K R K^-1` whatever its depth, so depth cannot be recovered from the motion. A model that reports structure
here is reporting a prior. Rendering the rotation from one ordinary frame would run out of image after a
quarter turn; TartanAir V2 publishes a full panorama (image and depth) at every pose, so a camera can turn
for the whole clip, at any rate, and every frame is real imagery.

Measured on BrushifyMoon (frame 0 of P001), against the front camera at the same pose:
- the panorama is 2048 x 1024, longitude across and latitude down, the front camera's forward axis at
  longitude +90 degrees (column 3/4), latitude positive up;
- its depth is the Euclidean range along the ray, not planar depth: the range read from the panorama
  matches the front camera's planar depth times |r| / r_z to a median of 0.15 percent;
- like the front camera's, depth saturates at float16's largest value (65504) where it is beyond range.

The virtual camera is TartanAir's own front camera (640 x 640, 90 degree FOV), starting where the front
camera looks and turning right about its vertical axis. Luminance is sampled bilinearly, the range at the
nearest pixel (so depth never blends across an edge) and made planar. Flow is exact: the pixel p of frame t
is at `K Y(step)^T K^-1 p` in frame t + 1, Y the yaw of one step; it is valid where that point is still in
front of the camera and inside the image.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import cv2
import numpy as np
from conectoma.vision.clipstore import ClipSpec, FetchLog, fetch_clips
from conectoma.vision.remote_zip import RemoteZip
from conectoma.vision.render import TARTANAIR_DEPTH_SATURATED, _luminance
from conectoma.vision.synthetic import yaw
from conectoma.vision.tartanair import archive_url

CAMERA = "lcam_equirect"
FRONT_LONGITUDE = np.pi / 2     # measured: the front camera's forward axis in the panorama


def members(environment: str, difficulty: str, trajectory: str, frame: int) -> dict[str, list[str]]:
    base = f"{environment}/Data_{difficulty}/{trajectory}"
    return {"image": [f"{base}/image_{CAMERA}/{frame:06d}_{CAMERA}_image.png"],
            "depth": [f"{base}/depth_{CAMERA}/{frame:06d}_{CAMERA}_depth.png"]}


def clip_path(root: Path, environment: str, difficulty: str, trajectory: str, frame: int) -> Path:
    return root / "data" / environment / difficulty / trajectory / f"pano_{frame:06d}.zip"


def fetch(config: dict, keys: list[str], root: Path, log: FetchLog, workers: int = 4) -> dict:
    """Fetch the panorama at the first frame of each TartanAir clip key ("env/difficulty/traj/start")."""
    by_archive: dict[tuple[str, str], list[str]] = {}
    for key in keys:
        environment, difficulty, _, _ = key.split("/")
        by_archive.setdefault((environment, difficulty), []).append(key)
    report = {"written": 0, "skipped": 0, "missing": [], "failed": {}, "bytes": 0}
    for (environment, difficulty), group in sorted(by_archive.items()):
        archives = {m: RemoteZip(archive_url(config["endpoint"], environment, difficulty, m, CAMERA))
                    for m in ("image", "depth")}
        specs = []
        for key in group:
            _, _, trajectory, start = key.split("/")
            specs.append(ClipSpec(f"panorama/{key}", clip_path(root, environment, difficulty, trajectory,
                                                               int(start)),
                                  members(environment, difficulty, trajectory, int(start))))
        part = fetch_clips(archives, specs, log, workers)
        for name in ("written", "skipped", "bytes"):
            report[name] += part[name]
        report["missing"] += part["missing"]
        report["failed"].update(part["failed"])
    return report


def load(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """The panorama's luminance in [0, 1] and its range in metres (NaN beyond range)."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        image = next(n for n in names if n.endswith("_image.png"))
        depth = next(n for n in names if n.endswith("_depth.png"))
        bgr = cv2.imdecode(np.frombuffer(archive.read(image), np.uint8), cv2.IMREAD_COLOR)
        raw = cv2.imdecode(np.frombuffer(archive.read(depth), np.uint8), cv2.IMREAD_UNCHANGED)
    if bgr is None or raw is None or raw.ndim != 3 or raw.shape[-1] != 4:
        raise ValueError(f"{path}: not a TartanAir panorama")
    distance = np.ascontiguousarray(raw).view("<f4")[..., 0]
    distance = np.where(distance >= TARTANAIR_DEPTH_SATURATED, np.nan, distance).astype(np.float32)
    return _luminance(bgr), distance


def _rays(K: np.ndarray, width: int, height: int) -> np.ndarray:
    v, u = np.mgrid[0:height, 0:width].astype(np.float64)
    return np.tensordot(np.linalg.inv(K), np.stack([u, v, np.ones_like(u)]), axes=1)   # (3, H, W)


def view(lum: np.ndarray, distance: np.ndarray, K: np.ndarray, width: int, height: int,
         rotation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """What a pinhole camera turned by `rotation` (camera to front-camera frame) sees of the panorama."""
    rays = _rays(K, width, height)
    d = np.tensordot(rotation, rays, axes=1)
    longitude = np.arctan2(d[0], d[2]) + FRONT_LONGITUDE
    latitude = np.arctan2(-d[1], np.hypot(d[0], d[2]))
    ph, pw = lum.shape
    col = (((longitude / (2 * np.pi) + 0.5) % 1.0) * pw - 0.5).astype(np.float32)
    row = ((0.5 - latitude / np.pi) * ph - 0.5).astype(np.float32)
    seen = cv2.remap(lum, col, row, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    reach = cv2.remap(distance, col, row, cv2.INTER_NEAREST, borderMode=cv2.BORDER_WRAP)
    planar = reach * (rays[2] / np.linalg.norm(rays, axis=0))
    return seen.astype(np.float32), planar.astype(np.float32)


def rotation_flow(K: np.ndarray, width: int, height: int, step_rad: float) -> tuple[np.ndarray, np.ndarray]:
    """Exact flow (pixels) of a rightward turn by `step_rad`, and where it is valid."""
    v, u = np.mgrid[0:height, 0:width].astype(np.float64)
    H = K @ yaw(step_rad).T @ np.linalg.inv(K)
    moved = np.tensordot(H, np.stack([u, v, np.ones_like(u)]), axes=1)
    nu, nv = moved[0] / moved[2], moved[1] / moved[2]
    ok = (moved[2] > 0) & (nu >= -0.5) & (nu <= width - 0.5) & (nv >= -0.5) & (nv <= height - 0.5)
    return np.stack([nu - u, nv - v]).astype(np.float32), ok


def turning_camera(lum: np.ndarray, distance: np.ndarray, K: np.ndarray, width: int, height: int,
                   rate_deg_s: float, frames: int, interval_s: float) -> dict:
    """A clip of a camera turning right at `rate_deg_s` in place, at source resolution."""
    step = np.radians(rate_deg_s) * interval_s
    views = [view(lum, distance, K, width, height, yaw(step * t)) for t in range(frames)]
    flow, ok = rotation_flow(K, width, height, step)
    return {"lum": np.stack([v[0] for v in views]), "depth": np.stack([v[1] for v in views]),
            "flow_px": np.repeat(flow[None], frames - 1, axis=0),
            "flow_ok": np.repeat(ok[None], frames - 1, axis=0),
            "frames": np.arange(frames, dtype=np.int32)}
