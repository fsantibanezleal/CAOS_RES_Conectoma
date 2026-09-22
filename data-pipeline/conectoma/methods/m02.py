"""M02: depth from a stereo pair by semi-global matching. An upper bound, not a native row.

M02 consumes more than the eye receives: the full 640 x 640 pixel grid of two cameras 0.25 m apart, which
is a camera rig and not a fly. It is in the ladder for exactly that reason. It bounds what a classical
geometric method gets from these scenes, and the gap between it and the native rows is a result rather
than an embarrassment. The report, the docs page and the Experiments page all label it an upper bound.

The matcher is Hirschmueller's semi-global matching (2008, IEEE TPAMI 30:328-341) as OpenCV implements it.
The geometry is the release's own, verified at tartanair.org/modalities.html on 2026-09-22: two stereo
sets of six cameras, **baseline 0.25 m**, pinhole, 640 x 640, 90 degree field of view, focal length 320
pixels. The pair is rectified by construction, being a synthetic rig, so nothing here rectifies anything.

    depth = focal * baseline / disparity

The depth map is then sampled onto the lattice by the same box rule the ground truth uses (the median over
the column's 13 x 13 box), so M02's numbers live in the same space as every other row's. A column whose
box holds no valid disparity is refused, not filled.

**What M02 cannot be run on, and why.** A case level that changes the left image (fog, exposure blur) would
have to change the right image the same way, and fog needs the right camera's depth while blur needs its
flow; neither was fetched. So M02 runs where the variant is either nothing at all (the ego-speed cases,
whose frames never change) or something reproducible on the right image from the image alone (a gain, or
photon noise). Everywhere else the report says `skipped` with the reason.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np

from conectoma.methods import readout
from conectoma.vision import eye

BASELINE_M = 0.25          # tartanair.org/modalities.html, read 2026-09-22
FOCAL_PX = 320.0           # at the source resolution of 640 x 640
MIN_DISPARITY_PX = 0.5     # below this the triangulation is beyond the release's own depth range
REPLICABLE = ("speed", "illumination", "photons")   # the variants that can be applied to the right image

MATCHER = dict(minDisparity=0, numDisparities=160, blockSize=5, P1=8 * 25, P2=32 * 25,
               disp12MaxDiff=1, uniquenessRatio=10, speckleWindowSize=100, speckleRange=2)


def right_frames(path: Path) -> np.ndarray:
    """The right camera's frames of one clip, as 8-bit luminance at source resolution."""
    import cv2

    with zipfile.ZipFile(path) as archive:
        names = sorted(name for name in archive.namelist() if name.endswith(".png"))
        if not names:
            raise OSError(f"{path}: no images in the right-camera clip")
        frames = []
        for name in names:
            decoded = cv2.imdecode(np.frombuffer(archive.read(name), np.uint8), cv2.IMREAD_COLOR)
            if decoded is None:
                raise OSError(f"{path}: {name} did not decode")
            frames.append(cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY))
    return np.stack(frames)


def disparity(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Semi-global matching on one rectified pair, in pixels (NaN where the matcher declined)."""
    import cv2

    matcher = cv2.StereoSGBM_create(mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY, **MATCHER)
    raw = matcher.compute(np.ascontiguousarray(left), np.ascontiguousarray(right))
    out = raw.astype(np.float32) / 16.0        # OpenCV returns fixed point with four fractional bits
    return np.where(out > MIN_DISPARITY_PX, out, np.nan)


def depth_from(left: np.ndarray, right: np.ndarray, baseline_m: float = BASELINE_M,
               focal_px: float = FOCAL_PX) -> np.ndarray:
    """Planar depth in metres from one rectified pair, at source resolution."""
    found = disparity(left, right)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.isfinite(found), focal_px * baseline_m / found, np.nan).astype(np.float32)


def run(left: np.ndarray, right: np.ndarray, *, baseline_m: float = BASELINE_M,
        focal_px: float = FOCAL_PX) -> dict[str, np.ndarray]:
    """Run M02 over a clip's frames. `left` and `right` are (frames, rows, columns) 8-bit images.

    Returns the same shape of answer every method here returns, one row per FRAME rather than per step
    (stereo needs no motion), truncated to the steps the other methods report so a comparison pairs.
    """
    left = np.asarray(left)
    right = np.asarray(right)
    if left.shape != right.shape:
        raise ValueError(f"the pair does not match: {left.shape} against {right.shape}")
    depths = np.stack([depth_from(left[t], right[t], baseline_m, focal_px) for t in range(len(left))])
    lattice = eye.box_median(eye.resize_rows(depths, nearest=True))
    claimed = np.isfinite(lattice) & (lattice > 0)
    steps = max(len(left) - 1, 1)
    return {
        "distance_m": lattice[:steps].astype(np.float32),
        "unknown": ~claimed[:steps],
        "moving": np.zeros((steps, readout.COLUMNS), dtype=bool),      # stereo says nothing about motion
        "uncertainty": np.where(claimed[:steps], 0.0, np.inf).astype(np.float32),
        "match_uncertainty": np.zeros((steps, readout.COLUMNS), dtype=np.float32),
        "deviation_deg": np.full((steps, readout.COLUMNS), np.nan, dtype=np.float32),
    }
