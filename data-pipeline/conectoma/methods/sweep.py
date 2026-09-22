"""A sweep along each column's epipolar line: the distance that best explains what the column saw.

Measured on the corpus before this was written: between consecutive frames of a TartanAir clip the columns
move by 39 pixels at the median, 96 at the ninth decile and 311 at the most, which is 3, 7 and 24 lattice
steps. A differential estimator has a capture range of about one step, so on this corpus it returns almost
nothing (its median endpoint error equals the median displacement, measured). The frame rate is the
source's own, so this is a property of the data, not a choice to be tuned away.

The geometry gives the search for free. With the camera motion known from the committed poses, a column's
point cannot land anywhere: as its distance runs from infinity to zero its image slides along one line, so
the unknown is ONE number, not two. This module sweeps that line, uniformly in inverse distance (uniform in
disparity, which is what the geometry is linear in), and keeps the distance whose patch matches best.

What comes out with the distance:

- **the match cost** at the best distance, and the cost at the best distance that is not adjacent to it. A
  column whose second-best match is nearly as good has not identified its distance (a repeating texture, or
  no texture at all), and the caller can refuse it on that margin.
- **the curvature** of the cost around its minimum, in the same units, which says how sharply the match
  localises the distance. It is zero where the sweep is flat, which is exactly what happens when the camera
  does not translate: then every distance predicts the same landing and the column cannot be measured.

The patch is assumed fronto-parallel over its seven columns (each member is tried at the centre's distance),
which is the standard assumption of a plane sweep and is why a column straddling a depth edge matches
poorly, which the cost then reports.
"""

from __future__ import annotations

import numpy as np

from conectoma.methods import flow_lattice, readout

NEAREST_M = 0.3          # the sweep starts here and runs to infinity, uniformly in inverse distance
STEP_PX = 0.5            # how far the landing point is allowed to move between two levels
MAX_LEVELS = 512


def inverse_distances(nearest_m: float = NEAREST_M, levels: int = 96) -> np.ndarray:
    """The sweep's grid: `levels` inverse distances from 0 (infinity) to 1 / nearest, inclusive."""
    return np.linspace(0.0, 1.0 / nearest_m, levels)


def levels_for(rotation: np.ndarray, translation: np.ndarray, column_spacing_deg: float,
               nearest_m: float = NEAREST_M, step_px: float = STEP_PX,
               max_levels: int = MAX_LEVELS) -> int:
    """How many levels the sweep needs so no level moves a landing point by more than `step_px`.

    A fixed count is wrong at both ends. The landing point moves along the epipolar line in proportion to
    the inverse depth, so a grid that is comfortable near the camera is far too coarse far from it: with 96
    levels over 0.3 m to infinity and a tenth of a metre of translation, two neighbouring levels straddle
    6.3 m and 11.1 m, and a plane at 8 m came back at 10.6 (measured, before this). The count is therefore
    taken from the geometry of the step itself.
    """
    focal = readout.focal_px(column_spacing_deg)
    rays = readout.planar_rays(column_spacing_deg)
    moved = rays @ np.asarray(rotation, dtype=np.float64).T
    near = _project(moved + np.asarray(translation) / nearest_m, focal)
    far = _project(moved, focal)
    span = np.nanmax(np.linalg.norm(near - far, axis=-1))
    if not np.isfinite(span):
        return max_levels
    return int(np.clip(np.ceil(span / max(step_px, 1e-6)) + 1, 8, max_levels))


def sweep(lum_a: np.ndarray, lum_b: np.ndarray, rotation: np.ndarray, translation: np.ndarray,
          column_spacing_deg: float, nearest_m: float = NEAREST_M, levels: int | None = None,
          step_px: float = STEP_PX) -> dict[str, np.ndarray]:
    """Match every column's patch along its epipolar line and keep the distance that fits best.

    With `levels` left out, the grid is as fine as the step's own geometry requires (`levels_for`).
    """
    if levels is None:
        levels = levels_for(rotation, translation, column_spacing_deg, nearest_m, step_px)
    focal = readout.focal_px(column_spacing_deg)
    rays = readout.planar_rays(column_spacing_deg)   # z = 1: the sweep runs over inverse PLANAR depth
    members, weights, _ = flow_lattice.patches()
    moved = rays @ np.asarray(rotation, dtype=np.float64).T          # (columns, 3)
    t = np.asarray(translation, dtype=np.float64)
    target = np.asarray(lum_a, dtype=np.float64)[members]            # (columns, 7)
    second = np.asarray(lum_b, dtype=np.float64)

    grid = inverse_distances(nearest_m, levels)
    costs = np.full((levels, len(rays)), np.inf)
    for level, s in enumerate(grid):
        # the patch member's own ray, taken to the centre column's distance: p = (R d) / s + t, and since
        # a projection is scale free, (R d) + s t may be projected instead, which stays finite at s = 0
        point = moved[members] + s * t                               # (columns, 7, 3)
        landing = _project(point, focal)
        value = flow_lattice.sample(second, flow_lattice.lattice_uv(landing))
        residual = value - target
        costs[level] = _cost(residual, weights)

    best = np.argmin(costs, axis=0)
    column = np.arange(len(rays))
    lowest = costs[best, column]
    refined = _parabolic(costs, best, grid)
    curvature = _curvature(costs, best, grid)
    margin = _second_best(costs, best)

    with np.errstate(divide="ignore", invalid="ignore"):
        distance = np.where(refined > 0, 1.0 / refined, np.inf)
        # How sharply the match fixes the answer: fitting a parabola to a sum of squared residuals, the
        # standard error of its minimum is sqrt(2 cost / curvature). Divided by the inverse distance
        # itself it is a RELATIVE uncertainty, the same quantity the geometric one is expressed in, so
        # one tolerance governs both. A flat sweep (no texture, no translation) gives infinity.
        spread = np.sqrt(2.0 * np.maximum(lowest, 0.0) / np.maximum(curvature, 0.0))
        uncertainty = np.where(refined > 0, spread / refined, np.inf)
    return {
        "distance_m": np.where(np.isfinite(lowest), distance, np.nan).astype(np.float32),
        "inverse_distance": refined.astype(np.float32),
        "uncertainty": uncertainty.astype(np.float32),
        "cost": lowest.astype(np.float32),
        "margin": margin.astype(np.float32),
        "curvature": curvature.astype(np.float32),
        "at_edge": ((best == 0) | (best == levels - 1)),
    }


def _project(points: np.ndarray, focal: float) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return focal * points[..., :2] / points[..., 2:3]


def _cost(residual: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted mean square residual over a patch; a patch that left the lattice costs infinity."""
    finite = np.isfinite(residual)
    total = (np.where(finite, residual, 0.0) ** 2 * weights).sum(axis=1)
    count = (weights * finite).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(finite.all(axis=1), total / np.maximum(count, 1e-12), np.inf)


def _parabolic(costs: np.ndarray, best: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """The minimum of the parabola through the best sample and its neighbours, in inverse distance."""
    levels, columns = costs.shape
    column = np.arange(columns)
    inner = (best > 0) & (best < levels - 1)
    left = costs[np.maximum(best - 1, 0), column]
    middle = costs[best, column]
    right = costs[np.minimum(best + 1, levels - 1), column]
    step = grid[1] - grid[0]
    denominator = left - 2 * middle + right
    with np.errstate(divide="ignore", invalid="ignore"):
        shift = np.where(np.abs(denominator) > 0, 0.5 * (left - right) / denominator, 0.0)
    shift = np.where(inner & np.isfinite(shift), np.clip(shift, -0.5, 0.5), 0.0)
    return grid[best] + shift * step


def _curvature(costs: np.ndarray, best: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """The second difference of the cost at its minimum: how sharply the match fixes the distance."""
    levels, columns = costs.shape
    column = np.arange(columns)
    left = costs[np.maximum(best - 1, 0), column]
    middle = costs[best, column]
    right = costs[np.minimum(best + 1, levels - 1), column]
    step = grid[1] - grid[0]
    with np.errstate(invalid="ignore"):
        curvature = (left - 2 * middle + right) / step**2
    return np.where(np.isfinite(curvature), np.maximum(curvature, 0.0), 0.0)


def _second_best(costs: np.ndarray, best: np.ndarray) -> np.ndarray:
    """cost(best) / cost(best elsewhere): near one, the column has not identified its distance."""
    levels, columns = costs.shape
    column = np.arange(columns)
    away = np.abs(np.arange(levels)[:, None] - best[None, :]) > 2
    elsewhere = np.where(away, costs, np.inf).min(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(elsewhere > 0, costs[best, column] / elsewhere, 1.0)


def landing_flow(inverse_distance: np.ndarray, rotation: np.ndarray, translation: np.ndarray,
                 column_spacing_deg: float) -> np.ndarray:
    """(2, columns) the displacement the sweep's distance predicts, to start a two-dimensional refinement."""
    focal = readout.focal_px(column_spacing_deg)
    rays = readout.planar_rays(column_spacing_deg)
    moved = rays @ np.asarray(rotation, dtype=np.float64).T
    point = moved + np.asarray(inverse_distance, dtype=np.float64)[:, None] * np.asarray(translation)
    return (_project(point, focal) - readout.column_pixels()).T
