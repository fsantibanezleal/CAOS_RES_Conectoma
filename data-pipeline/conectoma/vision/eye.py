"""The fly's eye: planar frames rendered onto the network's hexagonal lattice, as the engine does it.

The published model was trained on frames rendered by the engine's `BoxEye(extent=15, kernel_size=13)`, and
this module reproduces that rendering exactly (tested against BoxEye on random frames and against the
engine's own rendered Sintel):

- column (u, v) sits at pixel `y = trunc(13 (u + v/2))`, `x = trunc(13 v)` from the frame centre (BoxEye
  builds these as floats and casts them to integers, which truncates toward zero);
- a column's value is its 13 x 13 box: the mean for luminance and the sum for flow, both over a zero-padded
  frame, and the median for depth, over a frame padded by reflection;
- frames smaller than the lattice's window (391 x 391 pixels: both axes span 13 x 15 pixels either side of
  the centre) are resized to it first; the engine's Sintel pipeline keeps the central 0.7 of the width and
  cuts it into three overlapping strips of 417 pixels, which at 436 rows are already large enough.

Flow is in the engine's convention: pixels divided by the source image height, with y pointing up.

Written with numpy on the boxes at the column centres rather than a convolution over the whole frame: the
result is the same, it runs without a GPU, and targets the engine never rendered (segment boundaries, the
share of a box that is figure, the share whose flow is valid) come from the same boxes.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

EXTENT = 15
KERNEL = 13
CROP_FRACTION = 0.7


@lru_cache(maxsize=8)
def receptor_centers(extent: int = EXTENT, kernel: int = KERNEL) -> np.ndarray:
    """(columns, 2) integer (y, x) offsets from the frame centre, in the engine's (u, v) order."""
    centers = []
    for u in range(-extent, extent + 1):
        for v in range(max(-extent, -extent - u), min(extent, extent - u) + 1):
            centers.append((int(kernel * (u + v / 2)), int(kernel * v)))  # int() truncates toward zero
    return np.array(centers, dtype=np.int64)


def lattice_coordinates(extent: int = EXTENT) -> np.ndarray:
    """(columns, 2) integer (u, v) in the same order as `receptor_centers`."""
    return np.array([(u, v) for u in range(-extent, extent + 1)
                     for v in range(max(-extent, -extent - u), min(extent, extent - u) + 1)], dtype=np.int64)


def min_frame_size(extent: int = EXTENT, kernel: int = KERNEL) -> tuple[int, int]:
    c = receptor_centers(extent, kernel)
    size = c.max(axis=0) - c.min(axis=0) + 1
    return int(size[0]), int(size[1])


def center_crop_width(frames: np.ndarray, fraction: float = CROP_FRACTION) -> np.ndarray:
    """The engine's central crop of the last axis (`flyvis.datasets.rendering.utils.center_crop`)."""
    n = frames.shape[-1]
    out = int(fraction * n)
    return frames[..., (n - out) // 2: (n + out) // 2]


def fit_to_lattice(frames: np.ndarray, extent: int = EXTENT, kernel: int = KERNEL) -> np.ndarray:
    """Frames (..., H, W) resized to the lattice window when smaller, exactly as BoxEye does (torchvision)."""
    h_min, w_min = min_frame_size(extent, kernel)
    h, w = frames.shape[-2:]
    if h >= h_min and w >= w_min:
        return frames
    import torch
    import torchvision.transforms.functional as ttf

    lead = frames.shape[:-2]
    tensor = torch.as_tensor(np.ascontiguousarray(frames, dtype=np.float32)).reshape(-1, 1, h, w)
    resized = ttf.resize(tensor.cpu(), [h_min, w_min])
    return resized.reshape(*lead, h_min, w_min).numpy()


def _boxes(frames: np.ndarray, extent: int, kernel: int, mode: str) -> np.ndarray:
    """(..., columns, kernel * kernel): the box around every column centre, after the engine's padding."""
    h, w = frames.shape[-2:]
    lo = (kernel - 1) // 2
    hi = kernel - 1 - lo
    pad = [(0, 0)] * (frames.ndim - 2) + [(lo, hi), (lo, hi)]
    padded = np.pad(frames, pad, mode="constant") if mode == "zero" else np.pad(frames, pad, mode="reflect")
    centers = receptor_centers(extent, kernel) + np.array([h // 2, w // 2])
    offsets = np.arange(kernel)
    rows = centers[:, 0, None] + offsets[None, :]            # padded row index of each box row
    cols = centers[:, 1, None] + offsets[None, :]
    return padded[..., rows[:, :, None], cols[:, None, :]].reshape(*frames.shape[:-2], len(centers), -1)


def box_mean(frames: np.ndarray, extent: int = EXTENT, kernel: int = KERNEL) -> np.ndarray:
    return _boxes(frames.astype(np.float32), extent, kernel, "zero").sum(axis=-1) / kernel**2


def box_sum(frames: np.ndarray, extent: int = EXTENT, kernel: int = KERNEL) -> np.ndarray:
    return _boxes(frames.astype(np.float32), extent, kernel, "zero").sum(axis=-1)


def box_median(frames: np.ndarray, extent: int = EXTENT, kernel: int = KERNEL) -> np.ndarray:
    # 169 values per box: the median is a single element, identical to torch's
    return np.median(_boxes(frames.astype(np.float32), extent, kernel, "reflect"), axis=-1).astype(np.float32)


def box_distinct(labels: np.ndarray, extent: int = EXTENT, kernel: int = KERNEL) -> np.ndarray:
    """How many distinct labels each column's box holds (reflect padding: no label invented at a border)."""
    boxes = np.sort(_boxes(labels, extent, kernel, "reflect"), axis=-1)
    return (1 + (np.diff(boxes, axis=-1) != 0).sum(axis=-1)).astype(np.int16)


def box_share(mask: np.ndarray, extent: int = EXTENT, kernel: int = KERNEL) -> np.ndarray:
    """The fraction of each column's box where the mask holds (reflect padding)."""
    return _boxes(mask.astype(np.float32), extent, kernel, "reflect").mean(axis=-1).astype(np.float32)


def engine_flow(flow_px: np.ndarray, image_height: int) -> np.ndarray:
    """Pixel flow (..., 2, H, W) with y down, in the engine's units: per image height, y up."""
    return flow_px / image_height * np.array([1.0, -1.0], dtype=np.float32)[:, None, None]
