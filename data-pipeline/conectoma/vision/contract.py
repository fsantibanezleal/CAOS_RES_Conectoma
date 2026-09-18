"""Contract 1 for vision clips: what a rendered clip must hold before anything downstream may read it.

Every rendered clip is checked here, and a clip that fails is rejected with its reasons rather than repaired:
shapes that disagree, luminance outside [0, 1], depth that is not positive (masked depth is NaN, never zero or
negative), non-finite flow, shares outside [0, 1], a boundary map that is not binary, poses that are not
finite or whose rotation is not a unit quaternion, frames that are not consecutive. Every source requires
luminance, depth and frames; each declares what else it must carry (`REQUIRED`), and any optional array that
is present is checked all the same. The tests build clips that break each rule.
"""

from __future__ import annotations

import numpy as np

COLUMNS = 721  # the ethological lattice, extent 15

REQUIRED = {
    "tartanair": ("lum", "depth", "frames", "flow", "flow_valid", "boundary", "poses"),
    "spring": ("lum", "depth", "frames", "sky", "moving"),
    "hypersim": ("lum", "depth", "frames", "boundary", "figure", "labelled", "semantic"),
    "synthetic": ("lum", "depth", "frames", "flow", "flow_valid"),
    "flygym": ("lum", "depth", "frames", "figure"),
    "sintel": ("lum", "depth", "frames", "flow"),
}
# Per-frame arrays have one row per frame; per-step arrays one row per consecutive pair.
PER_FRAME = ("lum", "depth", "boundary", "sky", "figure", "labelled", "semantic")
PER_STEP = ("flow_valid", "moving")
SHARES = ("flow_valid", "sky", "moving", "figure", "labelled")
# single images (Hypersim) are not a video: their frames are ids, not consecutive
VIDEO = ("tartanair", "spring", "synthetic", "flygym", "sintel")


def clip_problems(clip: dict, source: str = "tartanair", columns: int = COLUMNS) -> list[str]:
    """Every way a rendered clip breaks contract 1 (empty when it holds)."""
    missing = [k for k in REQUIRED[source] if k not in clip]
    if missing:
        return [f"missing arrays: {', '.join(missing)}"]
    problems = []
    n = len(clip["frames"])
    shapes = {key: (n, columns) for key in PER_FRAME}
    shapes.update({key: (n - 1, columns) for key in PER_STEP})
    shapes.update({"flow": (n - 1, 2, columns), "poses": (n, 7)})
    for key, shape in shapes.items():
        if key in clip and tuple(clip[key].shape) != shape:
            problems.append(f"{key} has shape {tuple(clip[key].shape)}, expected {shape}")
    if problems:
        return problems
    frames = np.asarray(clip["frames"])
    if source in VIDEO and (n < 2 or not np.array_equal(frames, np.arange(frames[0], frames[0] + n))):
        problems.append("frames are not consecutive")
    if len(set(frames.tolist())) != n:
        problems.append("frames repeat")
    lum = clip["lum"]
    if not np.isfinite(lum).all() or lum.min() < 0 or lum.max() > 1:
        problems.append("luminance is not finite within [0, 1]")
    depth = clip["depth"]
    finite = np.isfinite(depth)
    if (depth[finite] <= 0).any():
        problems.append("depth has non-positive values (masked depth must be NaN)")
    if np.isinf(depth).any():
        problems.append("depth has infinite values")
    if "flow" in clip and not np.isfinite(clip["flow"]).all():
        problems.append("flow is not finite")
    for key in SHARES:
        if key in clip:
            share = clip[key]
            if not np.isfinite(share).all() or share.min() < 0 or share.max() > 1:
                problems.append(f"{key} is not a share within [0, 1]")
    if "boundary" in clip and not np.isin(clip["boundary"], (0, 1)).all():
        problems.append("boundary is not binary")
    if "semantic" in clip and (clip["semantic"].min() < 0 or clip["semantic"].max() > 40):
        problems.append("semantic is not an NYU40 label (0 for unlabelled)")
    if "poses" in clip:
        poses = clip["poses"]
        if not np.isfinite(poses).all():
            problems.append("poses are not finite")
        elif np.abs(np.linalg.norm(poses[:, 3:], axis=1) - 1).max() > 1e-3:
            problems.append("pose rotations are not unit quaternions")
    return problems


def clip_statistics(clip: dict) -> dict:
    """What a manifest row records about a rendered clip."""
    depth = clip["depth"]
    finite = depth[np.isfinite(depth)]
    stats = {
        "frames": int(len(clip["frames"])),
        "depth_masked_columns": int((~np.isfinite(depth)).sum()),
        "depth_min_m": float(finite.min()) if finite.size else None,
        "depth_median_m": float(np.median(finite)) if finite.size else None,
        "depth_max_m": float(finite.max()) if finite.size else None,
        "lum_mean": float(clip["lum"].mean()),
        "lum_std": float(clip["lum"].std()),
    }
    for key in ("flow_valid", "boundary", "sky", "moving", "figure", "labelled"):
        if key in clip:
            stats[f"{key}_share"] = float(np.asarray(clip[key], dtype=np.float64).mean())
    if "poses" in clip:
        translation = np.diff(clip["poses"][:, :3], axis=0)
        steps = np.linalg.norm(translation, axis=1)
        stats["step_m_median"] = float(np.median(steps)) if len(steps) else 0.0
    return stats
