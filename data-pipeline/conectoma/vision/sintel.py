"""MPI Sintel, the published model's own domain: the clips of case C08, read exactly as the engine reads them.

The engine downloads Sintel itself (`fetch-vision --source sintel`) into `<models root>/flyvis/SintelDataSet`,
and trains its published models on the final pass of 23 training sequences. It holds six sequences out for
validation (`flyvis.datasets.sintel_utils.original_train_and_validation_indices`); C08 draws only from
those six, so the published models never saw them. Frames are read as the engine reads them: luminance is
PIL's integer "L" conversion (ITU-R 601-2 luma, rounded to 8 bits), flow is the `.flo` field in pixels, depth
the `.dpt` map in Blender scene units (relative, not metres). Flow is valid where the dataset marks a pixel
neither occluded in the next frame nor invalid.

File formats, from the dataset's own READMEs: `.flo` is the tag 202021.25, width and height as int32, then
(u, v) float32 pairs row by row; `.dpt` is the same tag, width, height, then float32 depth row by row;
occlusion and invalid maps are 8-bit images, nonzero where occluded or invalid.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# flyvis 1.2.0, sintel_utils.original_train_and_validation_indices: the validation sequences
HELD_OUT = ("ambush_2", "bamboo_1", "bandage_1", "cave_4", "market_2", "mountain_1")
FRAME_INTERVAL_S = 1 / 24
TAG = 202021.25


def sintel_dir(models_root: Path) -> Path:
    return models_root / "flyvis" / "SintelDataSet"


def luminance(bgr: np.ndarray) -> np.ndarray:
    """PIL's `convert("L")` exactly: (19595 R + 38470 G + 7471 B + 32768) >> 16, over 255."""
    b, g, r = (bgr[..., i].astype(np.uint32) for i in range(3))
    return (((19595 * r + 38470 * g + 7471 * b + 0x8000) >> 16).astype(np.float32)) / 255.0


def _header(path: Path) -> tuple[np.ndarray, int, int]:
    raw = path.read_bytes()
    tag = np.frombuffer(raw[:4], "<f4")[0]
    width, height = np.frombuffer(raw[4:12], "<i4")
    if tag != TAG:
        raise ValueError(f"{path}: not a Sintel file (tag {tag})")
    return np.frombuffer(raw[12:], "<f4"), int(width), int(height)


def read_flow(path: Path) -> np.ndarray:
    """(2, H, W) flow in pixels, x right and y down."""
    data, width, height = _header(path)
    return np.moveaxis(data[: 2 * width * height].reshape(height, width, 2), -1, 0).astype(np.float32)


def read_depth(path: Path) -> np.ndarray:
    data, width, height = _header(path)
    return data[: width * height].reshape(height, width).astype(np.float32)


def read_camera(path: Path) -> np.ndarray:
    """The 3 x 3 intrinsic matrix of a `.cam` file (the tag, then nine float64, then the extrinsics)."""
    raw = path.read_bytes()
    if np.frombuffer(raw[:4], "<f4")[0] != TAG:
        raise ValueError(f"{path}: not a Sintel camera file")
    return np.frombuffer(raw[4:76], "<f8").reshape(3, 3).copy()


def engine_strips(width: int, crop_fraction: float = 0.7, strip_width: int = 391 + 2 * 13,
                  count: int = 3) -> list[tuple[int, int]]:
    """The column ranges of the engine's vertical strips of a frame `width` wide, as `RenderedSintel` cuts
    them: a central crop of `crop_fraction`, then `count` overlapping strips of `strip_width` (the lattice
    window plus a kernel either side). The same integer arithmetic as `flyvis.datasets.rendering.utils`.
    """
    kept = int(crop_fraction * width)
    left, right = (width - kept) // 2, (width + kept) // 2
    actual = right - left
    size = max(strip_width, int(actual / count))
    overlap = int(np.ceil((size * count - actual) / (count - 1)))
    return [(left + i * size - i * overlap, left + (i + 1) * size - i * overlap) for i in range(count)]


def load_sintel_clip(root: Path, sequence: str, length: int = 32, render_pass: str = "final",
                     strip: int | None = 1) -> dict:
    """The central `length` frames of a training sequence (all of them when it is shorter).

    `strip` cuts the frames to one of the engine's three vertical strips (1, the middle, by default), so a
    rendering of it is exactly what the engine renders; None keeps the whole frame. Flow is our convention,
    `flow[t]` the motion from frame t to t + 1; the engine labels frame t + 1 with that same flow.
    """
    base = root / "training"
    images = sorted((base / render_pass / sequence).glob("frame_*.png"))
    start = max(0, (len(images) - length) // 2)
    images = images[start: start + length]
    numbers = [int(p.stem.split("_")[1]) for p in images]
    lum = np.stack([luminance(cv2.imread(str(p), cv2.IMREAD_COLOR)) for p in images])
    depth = np.stack([read_depth(base / "depth" / sequence / f"{p.stem}.dpt") for p in images])
    flows = [read_flow(base / "flow" / sequence / f"{p.stem}.flo") for p in images[:-1]]

    def mask(kind: str, p: Path) -> np.ndarray:
        image = cv2.imread(str(base / kind / sequence / p.name), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"{sequence}: {kind} map missing for {p.name}")
        return image > 0

    ok = np.stack([~mask("occlusions", p) & ~mask("invalid", p) for p in images[:-1]])
    intrinsics = np.stack([read_camera(base / "camdata_left" / sequence / f"{p.stem}.cam") for p in images])
    intrinsics = intrinsics[:, [0, 1, 0, 1], [0, 1, 2, 2]]                   # fx, fy, cx, cy per frame
    clip = {"lum": lum, "depth": depth, "flow_px": np.stack(flows), "flow_ok": ok}
    if strip is not None:
        start, stop = engine_strips(lum.shape[-1])[strip]
        clip = {k: v[..., start:stop] for k, v in clip.items()}
        intrinsics[:, 2] -= start                                             # the principal point moves
    return {**clip, "frames": np.array(numbers, dtype=np.int32), "intrinsics": intrinsics,
            "strip": np.array([start, stop] if strip is not None else [0, lum.shape[-1]], dtype=np.int32)}
