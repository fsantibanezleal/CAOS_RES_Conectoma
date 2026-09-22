"""From flow on the lattice to distance in metres, with the ego-motion the corpus committed.

Longuet-Higgins and Prazdny (1980, Proc. R. Soc. Lond. B 208:385-397) decompose the motion field of a rigid
scene under a known camera motion into a rotational part that carries no distance and a translational part
whose magnitude is the distance. This module is that decomposition, done exactly rather than in the
small-angle form, in the pinhole coordinates the corpus already uses (`conectoma/vision/decode.py`).

A column looks along the ray `d` (unit). A point at distance `Z` along it lands, in the next frame, at

    p'(Z) = Z (R d) + t          R, t taking camera a to camera b (decode.relative_motion)
    x'(Z) = f p'_x / p'_z ,  y'(Z) = f p'_y / p'_z

so the measured displacement fixes `Z` through two linear equations in `Z`, solved together:

    Z = (A . b) / (A . A),   A = [x' a_z - f a_x,  y' a_z - f a_y],   b = [f t_x - x' t_z,  f t_y - y' t_z]

with `a = R d`. This is exact triangulation from a known relative pose: no linearisation, and the
degeneracy is explicit in `A`. Two quantities come out with the distance and matter as much as it does:

- **the baseline the column actually has.** Distance from motion needs translation ACROSS the line of
  sight. `t_perp = |t - (t . d) d|` is that translation, and the relative uncertainty of the distance is
  `sigma_Z / Z = Z sigma_px / (f t_perp)`: it grows with the square of distance over baseline. A column
  whose uncertainty exceeds the caller's tolerance reports unknown instead of a number. Under pure rotation
  `t_perp` is zero everywhere and EVERY column reports unknown, which is what case C13 grades; a column
  looking along the direction of travel has `t_perp = 0` for the same reason, which is the focus of
  expansion and is why C13 and C14 are graded by the share flagged unknown rather than by an error.
- **the epipolar deviation.** For a rigid scene the displacement must lie along the epipolar direction,
  whatever `Z` is. The angle between the measured displacement and that direction therefore finds
  independently moving objects WITHOUT knowing any distance, which is what the motion-segmentation arm of
  M01 uses.

Units. The corpus stores flow the way the engine does: per image height, y up, summed over the 13 x 13 box
(169 pixels). `pixel_flow` converts that to the mean displacement in pixels of the 436-row frame, y down,
which is the frame these equations live in.
"""

from __future__ import annotations

import math

import numpy as np

from conectoma.vision import decode, eye

COLUMNS = 721
BOX_PIXELS = eye.KERNEL**2
COLUMN_STEP_PX = 13.0      # neighbouring columns are one kernel apart on the row axis


def focal_px(column_spacing_deg: float) -> float:
    """The focal length in pixels of a 436-row frame whose columns are `column_spacing_deg` apart.

    The inverse of `conectoma.vision.cases.column_spacing_deg`, which is what every rendering records.
    """
    if not column_spacing_deg > 0:
        raise ValueError(f"column spacing must be positive, got {column_spacing_deg}")
    return COLUMN_STEP_PX / 2 / math.tan(math.radians(column_spacing_deg) / 2)


def column_pixels(extent: int = eye.EXTENT, kernel: int = eye.KERNEL) -> np.ndarray:
    """(columns, 2) the (x, y) pixel offset of each column centre from the frame centre, y down."""
    centers = eye.receptor_centers(extent, kernel)      # (columns, 2) as (y, x), y down
    return np.stack([centers[:, 1], centers[:, 0]], axis=1).astype(np.float64)


def ray_directions(column_spacing_deg: float, extent: int = eye.EXTENT) -> np.ndarray:
    """(columns, 3) unit viewing direction of each column in pinhole coordinates (x right, y down, z fwd)."""
    pixels = column_pixels(extent)
    rays = np.concatenate([pixels, np.full((len(pixels), 1), focal_px(column_spacing_deg))], axis=1)
    return rays / np.linalg.norm(rays, axis=1, keepdims=True)


def pixel_flow(flow_engine: np.ndarray, rows: int = eye.ROWS) -> np.ndarray:
    """Engine flow (..., 2, columns) as the mean displacement in pixels of a `rows`-row frame, y down.

    The rendering holds the box SUM of a flow expressed per image height with y up, so the mean pixel
    displacement of a column is `sum / 169 * rows`, with the y component's sign put back.
    """
    scale = np.array([rows / BOX_PIXELS, -rows / BOX_PIXELS], dtype=np.float64)
    return np.asarray(flow_engine, dtype=np.float64) * scale.reshape(
        (2, 1) if flow_engine.ndim == 2 else (1, 2, 1)
    )


def relative_motions(poses: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Rotation and translation between each consecutive pair of poses, in pinhole camera coordinates."""
    return [decode.relative_motion(poses[i], poses[i + 1]) for i in range(len(poses) - 1)]


def triangulate(
    flow_px: np.ndarray,
    rotation: np.ndarray,
    translation: np.ndarray,
    column_spacing_deg: float,
    extent: int = eye.EXTENT,
) -> dict[str, np.ndarray]:
    """Distance per column from one step's displacement and the known motion of the camera.

    `flow_px` is (2, columns): the displacement of each column between the two frames, in pixels, y down.
    Returns the distance (metres where the poses are metric), the across-the-line-of-sight baseline, the
    epipolar deviation in degrees, and the predicted displacement of the fitted distance.
    """
    focal = focal_px(column_spacing_deg)
    pixels = column_pixels(extent)
    rays = ray_directions(column_spacing_deg, extent)
    moved = rays @ np.asarray(rotation, dtype=np.float64).T        # (columns, 3) = R d
    t = np.asarray(translation, dtype=np.float64)
    seen = pixels + np.asarray(flow_px, dtype=np.float64).T        # where each column's point is next

    a = np.stack([seen[:, 0] * moved[:, 2] - focal * moved[:, 0],
                  seen[:, 1] * moved[:, 2] - focal * moved[:, 1]], axis=1)
    b = np.stack([focal * t[0] - seen[:, 0] * t[2],
                  focal * t[1] - seen[:, 1] * t[2]], axis=1)
    denominator = (a * a).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        distance = np.where(denominator > 0, (a * b).sum(axis=1) / denominator, np.nan)

    # the translation across each column's line of sight: the baseline that makes distance observable
    along = rays @ t
    baseline = np.linalg.norm(t[None, :] - along[:, None] * rays, axis=1)

    # Where the column's point lands if it is infinitely far (the rotation alone), and the direction the
    # landing point slides along as it comes closer. With s = 1/Z the projection is f (a + s t) / (a + s t)_z
    # and its derivative in s is f (t_x a_z - a_x t_z, t_y a_z - a_y t_z) / (a_z + s t_z)^2, so the DIRECTION
    # is the same at every distance: that is the epipolar line, written without dividing by t_z, which is
    # zero whenever the camera moves sideways.
    far = _project(moved, focal)
    epipolar = np.stack([t[0] * moved[:, 2] - moved[:, 0] * t[2],
                         t[1] * moved[:, 2] - moved[:, 1] * t[2]], axis=1)
    offset = seen - far
    return {
        "distance_m": distance.astype(np.float32),
        "baseline_m": baseline.astype(np.float32),
        "deviation_deg": _angle_between(offset, epipolar).astype(np.float32),
        "residual_px": _off_line(offset, epipolar).astype(np.float32),
        "parallax_px": np.linalg.norm(offset, axis=1).astype(np.float32),
    }


def _project(points: np.ndarray, focal: float) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return focal * points[:, :2] / points[:, 2:3]


def _off_line(offset: np.ndarray, direction: np.ndarray) -> np.ndarray:
    """The part of a displacement no distance can explain: its distance from the epipolar line, in pixels."""
    length = np.linalg.norm(direction, axis=1)
    cross = np.abs(offset[:, 0] * direction[:, 1] - offset[:, 1] * direction[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(length > 0, cross / length, np.nan)


def _angle_between(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    nu, nv = np.linalg.norm(u, axis=1), np.linalg.norm(v, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cosine = np.clip((u * v).sum(axis=1) / (nu * nv), -1.0, 1.0)
    return np.degrees(np.arccos(np.where((nu > 0) & (nv > 0), cosine, np.nan)))


def distance_uncertainty(distance_m: np.ndarray, baseline_m: np.ndarray, column_spacing_deg: float,
                         flow_noise_px: float) -> np.ndarray:
    """Relative uncertainty of the distance: `sigma_Z / Z = Z sigma_px / (f t_perp)`.

    It is the whole story of distance from motion: the uncertainty grows with the square of the distance
    for a fixed baseline, so a far column under a short baseline is unknown however clean its flow is.
    """
    focal = focal_px(column_spacing_deg)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(baseline_m > 0,
                        np.asarray(distance_m, dtype=np.float64) * flow_noise_px / (focal * baseline_m),
                        np.inf).astype(np.float32)


def unknown(distance_m: np.ndarray, relative_uncertainty: np.ndarray, tolerance: float,
            confidence: np.ndarray | None = None, min_confidence: float = 0.0) -> np.ndarray:
    """Where a distance must not be claimed: not finite, not positive, too uncertain, or unresolved flow."""
    bad = ~np.isfinite(distance_m) | (np.asarray(distance_m) <= 0)
    bad |= ~np.isfinite(relative_uncertainty) | (relative_uncertainty > tolerance)
    if confidence is not None:
        bad |= ~np.isfinite(confidence) | (confidence < min_confidence)
    return bad


def moving(deviation_deg: np.ndarray, parallax_px: np.ndarray, max_deviation_deg: float,
           min_parallax_px: float) -> np.ndarray:
    """Columns whose displacement does not lie along the epipolar direction: something else is moving.

    The test needs no distance: for a rigid scene every displacement lies on that line whatever the
    distance is. A displacement too small to have a direction is not called moving.
    """
    return (np.isfinite(deviation_deg) & (deviation_deg > max_deviation_deg)
            & (parallax_px > min_parallax_px))
