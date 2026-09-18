"""Render fetched clips onto the lattice: one compact array file per clip, with what each column saw.

For a TartanAir clip (32 frames), the output holds, per lattice column and frame:
  lum          luminance in [0, 1], box mean                                   (frames, columns)
  depth        planar depth in metres, box median                              (frames, columns)
  flow         flow to the next frame, engine units (per image height, y up)   (frames - 1, 2, columns)
  flow_valid   share of the box whose flow the release marks valid            (frames - 1, columns)
  boundary     1 where the box holds more than one segment                    (frames, columns)
and the camera poses (frames, 7). TartanAir's frame centre is the image centre and the lattice window
(391 x 391) fits inside its 640 x 640 frames, so no crop or resize changes what a column sees.

Depth is kept where the release gives a finite positive value; a column whose median is not finite stays NaN,
and the clip manifest counts it: masked, not dropped.
"""

from __future__ import annotations

import io
import warnings
import zipfile
from pathlib import Path

import numpy as np
from conectoma.vision import decode, eye

RENDER_VERSION = 1


def _frames(names: list[str], suffix: str) -> list[str]:
    return sorted(n for n in names if n.endswith(suffix))


def render_tartanair_clip(path: Path, height: int = 640, extent: int = eye.EXTENT) -> dict:
    """The lattice rendering of one TartanAir clip archive."""
    import cv2

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        images = _frames(names, "_lcam_front.png")
        depths = _frames(names, "_lcam_front_depth.png")
        segs = _frames(names, "_lcam_front_seg.png")
        flows = _frames(names, "_flow.png")
        poses_name = next(n for n in names if n.endswith("pose_lcam_front.txt"))
        if not (len(images) == len(depths) == len(segs) == len(flows) + 1):
            raise ValueError(f"{path}: {len(images)} images, {len(depths)} depths, {len(segs)} segs, "
                             f"{len(flows)} flows")

        def decode_bytes(name: str, flags: int) -> np.ndarray:
            image = cv2.imdecode(np.frombuffer(archive.read(name), dtype=np.uint8), flags)
            if image is None:
                raise ValueError(f"{path}:{name}: not a readable image")
            return image

        lum = np.stack([_luminance(decode_bytes(n, cv2.IMREAD_COLOR)) for n in images])
        depth = np.stack([_depth(decode_bytes(n, cv2.IMREAD_UNCHANGED), n) for n in depths])
        seg = np.stack([_seg(decode_bytes(n, cv2.IMREAD_UNCHANGED)) for n in segs])
        flow_px, mask = zip(*[_flow(decode_bytes(n, cv2.IMREAD_UNCHANGED), n) for n in flows], strict=True)
        flow_px, mask = np.stack(flow_px), np.stack(mask)
        poses = np.loadtxt(io.StringIO(archive.read(poses_name).decode("utf-8")), dtype=np.float64)

    first = int(Path(images[0]).name[:6])
    frame_ids = [int(Path(n).name[:6]) for n in images]
    if frame_ids != list(range(first, first + len(images))):
        raise ValueError(f"{path}: frames are not consecutive: {frame_ids[:3]}...")
    depth = np.where(np.isfinite(depth) & (depth > 0), depth, np.nan).astype(np.float32)
    return {
        "lum": eye.box_mean(lum, extent),
        "depth": _nan_median(depth, extent),
        "flow": np.stack([eye.box_sum(component, extent)
                          for component in np.moveaxis(eye.engine_flow(flow_px, height), 1, 0)], axis=1),
        "flow_valid": eye.box_share(mask == 0, extent),
        "boundary": (eye.box_distinct(seg, extent) > 1).astype(np.uint8),
        "poses": poses[first: first + len(images)].astype(np.float64),
        "frames": np.array(frame_ids, dtype=np.int32),
    }


def _luminance(bgr: np.ndarray) -> np.ndarray:
    b, g, r = (bgr[..., i].astype(np.float32) for i in range(3))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _depth(rgba: np.ndarray, name: str) -> np.ndarray:
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype != np.uint8:
        raise ValueError(f"{name}: expected an 8-bit four-channel depth PNG")
    return np.ascontiguousarray(rgba).view("<f4")[..., 0]


def _seg(seg: np.ndarray) -> np.ndarray:
    return seg if seg.ndim == 2 else seg[..., 0]


def _flow(raw: np.ndarray, name: str) -> tuple[np.ndarray, np.ndarray]:
    if raw.ndim != 3 or raw.shape[2] < 3 or raw.dtype != np.uint16:
        raise ValueError(f"{name}: expected a 16-bit flow PNG")
    flow = (raw[..., :2].astype(np.float32) - decode.FLOW_OFFSET) / decode.FLOW_SCALE
    return np.moveaxis(flow, -1, 0), raw[..., 2]


def _nan_median(depth: np.ndarray, extent: int) -> np.ndarray:
    """Box median that ignores masked (NaN) pixels; identical to the plain median where none are masked."""
    boxes = eye._boxes(depth, extent, eye.KERNEL, "reflect")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # an all-NaN box is the case being kept
        return np.nanmedian(boxes, axis=-1).astype(np.float32)
