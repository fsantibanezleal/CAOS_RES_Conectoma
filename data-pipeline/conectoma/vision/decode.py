"""Decoders for the vision sources, each written against its source's own reference reader.

TartanAir V2 (tartanairpy `reader.py`): depth is a float32 packed into the four 8-bit channels of a PNG, and
flow is a 16-bit PNG holding `(value - 32768) / 64` pixels in its first two channels and a validity or
occlusion mask in its third. The channel order is OpenCV's (BGR), which is how the reference reads the
files, so this module reads them through OpenCV too: a PIL decode returns RGB and would silently swap flow's
components with its mask.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

FLOW_OFFSET = 32768.0
FLOW_SCALE = 64.0


def _read(path: Path, flags: int) -> np.ndarray:
    # np.fromfile + imdecode reads paths with non-ASCII characters on Windows, which cv2.imread does not
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), flags)
    if image is None:
        raise OSError(f"{path}: not a readable image")
    return image


def tartanair_luminance(path: Path) -> np.ndarray:
    """Luminance in [0, 1], the engine's convention (PIL-style 'L': ITU-R 601-2 luma of the RGB frame)."""
    bgr = _read(path, cv2.IMREAD_COLOR)
    b, g, r = (bgr[..., i].astype(np.float32) for i in range(3))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def tartanair_rgb(path: Path) -> np.ndarray:
    return cv2.cvtColor(_read(path, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def tartanair_depth(path: Path) -> np.ndarray:
    """Depth in metres, float32 (H, W)."""
    rgba = _read(path, cv2.IMREAD_UNCHANGED)
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype != np.uint8:
        raise OSError(f"{path}: expected an 8-bit four-channel depth PNG, got {rgba.dtype} {rgba.shape}")
    return np.ascontiguousarray(rgba).view("<f4")[..., 0]


def tartanair_flow(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Forward flow in pixels, float32 (2, H, W) as (dx, dy) with y down, and the uint8 mask (H, W)."""
    raw = _read(path, cv2.IMREAD_UNCHANGED)
    if raw.ndim != 3 or raw.shape[2] < 3 or raw.dtype != np.uint16:
        raise OSError(f"{path}: expected a 16-bit flow PNG, got {raw.dtype} {raw.shape}")
    flow = (raw[..., :2].astype(np.float32) - FLOW_OFFSET) / FLOW_SCALE
    return np.moveaxis(flow, -1, 0), raw[..., 2].astype(np.uint8)


def tartanair_seg(path: Path) -> np.ndarray:
    """Segment IDs, uint8 (H, W). The release names none of them."""
    seg = _read(path, cv2.IMREAD_UNCHANGED)
    return seg if seg.ndim == 2 else seg[..., 0]


def tartanair_poses(path: Path) -> np.ndarray:
    """Camera poses, one row per frame: tx ty tz qx qy qz qw, in the release's NED frame."""
    poses = np.loadtxt(path, dtype=np.float64)
    if poses.ndim != 2 or poses.shape[1] != 7:
        raise OSError(f"{path}: expected 7 columns per pose, got {poses.shape}")
    return poses


def quaternion_matrix(q: np.ndarray) -> np.ndarray:
    """Rotation matrix of a unit quaternion (x, y, z, w)."""
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


# The release's camera axes are NED (x forward, y right, z down); the pinhole convention is x right, y down,
# z forward. This matrix takes NED camera coordinates to pinhole camera coordinates.
NED_TO_CAMERA = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])


def relative_motion(pose_a: np.ndarray, pose_b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotation and translation taking points from camera a to camera b, in pinhole camera coordinates."""
    rotation_a, rotation_b = quaternion_matrix(pose_a[3:]), quaternion_matrix(pose_b[3:])
    # world point p: camera-a NED coordinates are R_a^T (p - t_a)
    rotation = rotation_b.T @ rotation_a
    translation = rotation_b.T @ (pose_a[:3] - pose_b[:3])
    return NED_TO_CAMERA @ rotation @ NED_TO_CAMERA.T, NED_TO_CAMERA @ translation


def flow_from_depth(depth: np.ndarray, rotation: np.ndarray, translation: np.ndarray, fx: float, fy: float,
                    cx: float, cy: float) -> np.ndarray:
    """The flow a static scene induces: back-project with depth, move the camera, project again. (2, H, W)."""
    h, w = depth.shape
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    points = np.stack([(u - cx) / fx * depth, (v - cy) / fy * depth, depth.astype(np.float64)])
    moved = np.tensordot(rotation, points, axes=1) + translation[:, None, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        u2 = fx * moved[0] / moved[2] + cx
        v2 = fy * moved[1] / moved[2] + cy
    return np.stack([u2 - u, v2 - v]).astype(np.float32)
