"""Contract 1 for vision clips: what a rendered clip must hold before anything downstream may read it.

Every rendered clip is checked here, and a clip that fails is rejected with its reasons rather than repaired:
shapes that disagree, luminance outside [0, 1], depth that is not positive (masked depth is NaN, never zero or
negative), non-finite flow, shares outside [0, 1], a boundary map that is not binary, poses that are not
finite or whose rotation is not a unit quaternion, frames that are not consecutive. The same checks run in
the tests on synthetic clips built to break each one.
"""

from __future__ import annotations

import numpy as np

COLUMNS = 721  # the ethological lattice, extent 15


def clip_problems(clip: dict, columns: int = COLUMNS) -> list[str]:
    """Every way a rendered clip breaks contract 1 (empty when it holds)."""
    problems = []
    required = ("lum", "depth", "flow", "flow_valid", "boundary", "poses", "frames")
    missing = [k for k in required if k not in clip]
    if missing:
        return [f"missing arrays: {', '.join(missing)}"]
    n = len(clip["frames"])
    expected = {
        "lum": (n, columns), "depth": (n, columns), "boundary": (n, columns), "poses": (n, 7),
        "flow": (n - 1, 2, columns), "flow_valid": (n - 1, columns),
    }
    for key, shape in expected.items():
        if tuple(clip[key].shape) != shape:
            problems.append(f"{key} has shape {tuple(clip[key].shape)}, expected {shape}")
    if problems:
        return problems
    frames = np.asarray(clip["frames"])
    if n < 2 or not np.array_equal(frames, np.arange(frames[0], frames[0] + n)):
        problems.append("frames are not consecutive")
    lum = clip["lum"]
    if not np.isfinite(lum).all() or lum.min() < 0 or lum.max() > 1:
        problems.append("luminance is not finite within [0, 1]")
    depth = clip["depth"]
    finite = np.isfinite(depth)
    if (depth[finite] <= 0).any():
        problems.append("depth has non-positive values (masked depth must be NaN)")
    if np.isinf(depth).any():
        problems.append("depth has infinite values")
    if not np.isfinite(clip["flow"]).all():
        problems.append("flow is not finite")
    share = clip["flow_valid"]
    if not np.isfinite(share).all() or share.min() < 0 or share.max() > 1:
        problems.append("flow_valid is not a share within [0, 1]")
    if not np.isin(clip["boundary"], (0, 1)).all():
        problems.append("boundary is not binary")
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
    translation = np.diff(clip["poses"][:, :3], axis=0)
    return {
        "frames": int(len(clip["frames"])),
        "depth_masked_columns": int((~np.isfinite(depth)).sum()),
        "depth_min_m": float(finite.min()) if finite.size else None,
        "depth_median_m": float(np.median(finite)) if finite.size else None,
        "depth_max_m": float(finite.max()) if finite.size else None,
        "flow_valid_share": float(clip["flow_valid"].mean()),
        "boundary_share": float(clip["boundary"].mean()),
        "lum_mean": float(clip["lum"].mean()),
        "lum_std": float(clip["lum"].std()),
        # camera speed from the poses, metres per frame interval
        "step_m_median": float(np.median(np.linalg.norm(translation, axis=1))) if len(translation) else 0.0,
    }
