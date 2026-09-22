"""Optical flow on the hexagonal lattice, from the 721 luminances the eye receives and nothing else.

A dense estimator written for a pixel grid does not apply here: the eye's columns are a hexagonal lattice,
each with six neighbours, and between two of them there is nothing. So the estimator is the classical
differential one, on that lattice:

- the brightness constancy constraint (Horn and Schunck 1981, Artif. Intell. 17:185-203) says a small
  displacement `v` satisfies `g . v + L_t = 0` with `g` the spatial gradient and `L_t` the temporal one;
- one column gives one equation for two unknowns, so the equations of a column and its six neighbours are
  solved together, weighted, as Lucas and Kanade's method does on a pixel patch;
- the gradient at a column is the least-squares plane through its own luminance and its neighbours', in the
  pixel coordinates of the 436-row frame, which is the frame the readout's geometry lives in.

What the estimator refuses to answer matters as much as what it returns. The normal matrix
`M = sum w g g^T` is singular where the local pattern is an edge (every gradient parallel: the aperture
problem) and near-singular where there is no texture at all. Its smaller eigenvalue is therefore the
confidence, in the same units for every column, and a column below the caller's threshold returns no
velocity rather than the arbitrary one the pseudo-inverse would give. Case C16 (textureless surfaces) and
case C07 (contrast) are built to grade exactly that refusal.

The lattice's neighbours are the six hexagonal ones, (u+1, v), (u-1, v), (u, v+1), (u, v-1), (u+1, v-1),
(u-1, v+1). A column on the rim has fewer, and uses the ones it has.
"""

from __future__ import annotations

import numpy as np

from conectoma.methods import readout
from conectoma.vision import eye

NEIGHBOUR_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1))
CENTRE_WEIGHT = 2.0       # the column's own equation counts double in its patch
NEIGHBOUR_WEIGHT = 1.0
REFINEMENTS = 6           # warping steps; the residual, not the gradient, decides where this stops


def lattice_uv(pixels: np.ndarray) -> np.ndarray:
    """Pixel positions (..., 2) as (x, y) to fractional lattice coordinates (u, v)."""
    x, y = pixels[..., 0], pixels[..., 1]
    v = x / eye.KERNEL
    u = y / eye.KERNEL - v / 2
    return np.stack([u, v], axis=-1)


def sample(values: np.ndarray, uv: np.ndarray, extent: int = eye.EXTENT,
           with_gradient: bool = False) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Interpolate a lattice signal at fractional lattice coordinates.

    In (u, v) the hexagonal lattice is a regular triangular one, so the cell a point falls in, and which of
    the cell's two triangles holds it, follow from the floor and the fractional part. The weights, though,
    are computed from the columns' REAL pixel positions, not from the ideal ones: the engine truncates each
    column's centre to a whole pixel (`int(13 (u + v/2))`), which moves it by up to a pixel of the thirteen,
    and interpolating on the ideal grid would not even return a column's own value at that column. With the
    real positions the interpolation is exact at every column, which is the least a reader may assume.

    Outside the lattice the value is NaN.
    """
    pixels = readout.column_pixels(extent)
    lookup = _lattice_lookup(extent)
    u, v = np.asarray(uv[..., 0], dtype=np.float64), np.asarray(uv[..., 1], dtype=np.float64)
    iu, iv = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fu, fv = u - iu, v - iv
    lower = (fu + fv) <= 1.0

    # the three columns of the triangle the point falls in
    corners = np.stack([
        np.stack([np.where(lower, iu, iu + 1), np.where(lower, iv, iv + 1)], axis=-1),
        np.stack([iu + 1, iv], axis=-1),
        np.stack([iu, iv + 1], axis=-1),
    ], axis=-2)                                                       # (..., 3, 2)
    index = _lookup(lookup, corners, extent)                          # (..., 3), -1 outside
    known = index >= 0
    safe = np.where(known, index, 0)

    # Barycentric weights from the REAL pixel positions of those three columns. A corner off the lattice
    # keeps its ideal position, so the triangle is still a triangle and the weights are still defined; the
    # result is only refused when such a corner actually carries weight (below), which leaves a query that
    # sits on a rim column answerable with that column's own value.
    triangle = np.where(known[..., None], pixels[safe], _ideal_pixels(corners))
    query = np.stack([v * eye.KERNEL, (u + v / 2) * eye.KERNEL], axis=-1)   # back to pixels (x, y)
    basis = np.stack([triangle[..., 1, :] - triangle[..., 0, :],
                      triangle[..., 2, :] - triangle[..., 0, :]], axis=-1)  # (..., 2, 2)
    offset = (query - triangle[..., 0, :])[..., None]
    determinant = basis[..., 0, 0] * basis[..., 1, 1] - basis[..., 0, 1] * basis[..., 1, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        inverse = np.stack([
            np.stack([basis[..., 1, 1], -basis[..., 0, 1]], axis=-1),
            np.stack([-basis[..., 1, 0], basis[..., 0, 0]], axis=-1),
        ], axis=-2) / determinant[..., None, None]
    with np.errstate(invalid="ignore"):
        pair = (inverse @ offset)[..., 0]                             # (..., 2)
        weights = np.stack([1.0 - pair[..., 0] - pair[..., 1], pair[..., 0], pair[..., 1]], axis=-1)

    taken = np.where(known, np.take(values, safe, axis=-1), 0.0)
    good = (determinant != 0) & (known | (np.abs(weights) < 1e-9)).all(axis=-1)
    out = np.where(good, (taken * weights).sum(axis=-1), np.nan)
    if not with_gradient:
        return out
    # The interpolant is linear inside the triangle, so its gradient is constant there and exact: with
    # (a, b) = M^-1 (q - P0) and value = v0 + a (v1 - v0) + b (v2 - v0), the gradient is
    # (v1 - v0) da/dq + (v2 - v0) db/dq, and da/dq, db/dq are the rows of M^-1. Using THIS gradient rather
    # than a difference over the lattice is what makes the refinement converge: a gradient read over 13
    # pixels under-reads the slope of the interpolant and the Gauss-Newton step then overshoots by exactly
    # that factor (12 to 24 percent on the test texture, measured).
    rise = np.stack([taken[..., 1] - taken[..., 0], taken[..., 2] - taken[..., 0]], axis=-1)
    gradient = np.einsum("...k,...kj->...j", rise, inverse)
    # a slope needs all three corners, whatever their weights: a missing one has no value to differ by
    whole = good & known.all(axis=-1)
    return out, np.where(whole[..., None], gradient, np.nan)


def _ideal_pixels(corners: np.ndarray) -> np.ndarray:
    """The pixel position a lattice coordinate would have before the engine truncates it."""
    u, v = corners[..., 0].astype(np.float64), corners[..., 1].astype(np.float64)
    return np.stack([eye.KERNEL * v, eye.KERNEL * (u + v / 2)], axis=-1)


def _lattice_lookup(extent: int) -> np.ndarray:
    """(2 extent + 3, 2 extent + 3) column index at each (u, v), -1 where the lattice has none."""
    lookup = np.full((2 * extent + 3, 2 * extent + 3), -1, dtype=np.int64)
    for i, (u, v) in enumerate(eye.lattice_coordinates(extent)):
        lookup[int(u) + extent, int(v) + extent] = i
    return lookup


def _lookup(lookup: np.ndarray, corners: np.ndarray, extent: int) -> np.ndarray:
    u, v = corners[..., 0], corners[..., 1]
    outside = (np.abs(u) > extent) | (np.abs(v) > extent)
    return np.where(outside, -1, lookup[np.clip(u, -extent, extent) + extent,
                                       np.clip(v, -extent, extent) + extent])


def neighbours(extent: int = eye.EXTENT) -> np.ndarray:
    """(columns, 6) index of each column's hexagonal neighbours, -1 where the lattice ends."""
    coordinates = eye.lattice_coordinates(extent)
    index = {(int(u), int(v)): i for i, (u, v) in enumerate(coordinates)}
    out = np.full((len(coordinates), len(NEIGHBOUR_STEPS)), -1, dtype=np.int64)
    for i, (u, v) in enumerate(coordinates):
        for k, (du, dv) in enumerate(NEIGHBOUR_STEPS):
            out[i, k] = index.get((int(u) + du, int(v) + dv), -1)
    return out


def gradients(lum: np.ndarray, extent: int = eye.EXTENT) -> np.ndarray:
    """(frames, columns, 2) luminance gradient per column, per pixel of the 436-row frame.

    The least-squares plane through the column and its neighbours: `g = (A^T A)^-1 A^T b` with `A` the
    neighbour offsets in pixels and `b` their luminance differences.
    """
    lum = np.asarray(lum, dtype=np.float64)
    pixels = readout.column_pixels(extent)
    index = neighbours(extent)
    out = np.zeros((*lum.shape[:-1], len(pixels), 2))
    for column in range(len(pixels)):
        present = index[column][index[column] >= 0]
        offsets = pixels[present] - pixels[column]                       # (n, 2)
        normal = offsets.T @ offsets
        if np.linalg.det(normal) <= 0:
            continue
        solve = np.linalg.inv(normal) @ offsets.T                        # (2, n)
        differences = lum[..., present] - lum[..., column, None]         # (..., n)
        out[..., column, :] = differences @ solve.T
    return out


def patches(extent: int = eye.EXTENT) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per column: the indices of its patch (itself and its neighbours), their weights, their pixels."""
    index = neighbours(extent)
    pixels = readout.column_pixels(extent)
    size = 1 + index.shape[1]
    members = np.zeros((len(pixels), size), dtype=np.int64)
    weights = np.zeros((len(pixels), size))
    for column in range(len(pixels)):
        present = index[column][index[column] >= 0]
        members[column, 0] = column
        members[column, 1:1 + len(present)] = present
        weights[column, 0] = CENTRE_WEIGHT
        weights[column, 1:1 + len(present)] = NEIGHBOUR_WEIGHT
    return members, weights, pixels[members]


def flow(lum: np.ndarray, extent: int = eye.EXTENT, refinements: int = REFINEMENTS,
         initial: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Flow between consecutive frames, in pixels of the 436-row frame, y down.

    The displacement is the one that makes the second frame, sampled where the first frame's columns are
    predicted to have moved, match the first frame over the column's patch. It is found by refinement, not
    by one linear solve, and both parts matter:

    - the residual is what is minimised, so the answer is where the two frames actually agree. One solve
      instead reads the answer off a gradient measured over a 13-pixel lattice step, which under-reads the
      slope of any structure that is not much wider than that and returns a velocity too large by that
      factor (measured: 12 to 24 percent on a band-limited texture, in the direction of the motion).
    - the gradient used in the refinement is the interpolant's own, exact inside each lattice triangle, so
      the step size is consistent with the objective and the iteration converges instead of overshooting.

    A step is taken only when it lowers the residual, halved up to four times otherwise: a column whose
    patch cannot be improved keeps the best displacement it found.

    The refinement starts at zero unless `initial` (steps, 2, columns) says otherwise. Its capture range is
    about one lattice step, so on a corpus whose columns move several steps between frames it must be
    started somewhere sensible: `conectoma.methods.sweep` provides that start from the geometry.

    Returns the velocity per column and per step, and the confidence: the smaller eigenvalue of the normal
    matrix of the column's patch, zero on an edge and on a flat patch.
    """
    lum = np.asarray(lum, dtype=np.float64)
    if lum.ndim != 2 or lum.shape[1] != readout.COLUMNS:
        raise ValueError(f"expected (frames, {readout.COLUMNS}) luminances, got {lum.shape}")
    members, weights, patch_pixels = patches(extent)
    steps, columns = len(lum) - 1, lum.shape[1]
    velocity = np.full((steps, 2, columns), np.nan)
    confidence = np.zeros((steps, columns))

    for step in range(steps):
        target = lum[step][members]                                    # (columns, 7)
        second = lum[step + 1]
        v = (np.zeros((columns, 2)) if initial is None
             else np.nan_to_num(np.asarray(initial, dtype=np.float64)[step].T.copy()))
        best = np.full(columns, np.inf)
        alive = np.ones(columns, dtype=bool)
        structure = np.zeros(columns)

        for _ in range(refinements):
            value, gradient = sample(second, lattice_uv(patch_pixels + v[:, None, :]), extent,
                                     with_gradient=True)
            residual = value - target
            weighted = gradient * weights[:, :, None]
            normal = np.einsum("cni,cnj->cij", np.nan_to_num(weighted), np.nan_to_num(gradient))
            smallest = np.linalg.eigvalsh(normal)[:, 0]
            structure = np.where(alive, smallest, structure)
            cost = _patch_cost(residual)
            alive &= np.isfinite(residual).all(axis=1) & (smallest > 0)
            if not alive.any():
                break
            best = np.where(alive, np.minimum(best, cost), best)
            right = -np.einsum("cni,cn->ci", np.nan_to_num(weighted), np.nan_to_num(residual))
            step_v, solved = _solve2(normal, right)
            step_v[~(alive & solved)] = 0.0
            alive &= solved
            v = _accept(second, target, patch_pixels, v, step_v, alive, best, extent)

        take = alive & (structure > 0)
        velocity[step, :, take] = v[take]
        confidence[step] = structure
    return {"velocity_px": velocity, "confidence": confidence}


def _solve2(normal: np.ndarray, right: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Solve a stack of 2 x 2 systems, saying which ones were solvable.

    Explicitly rather than through `np.linalg.solve`, which raises on the first singular matrix in the
    stack: on real data a column whose patch is flat or one-dimensional produces exactly that, and it is
    an answer (the aperture problem), not an error.
    """
    determinant = normal[:, 0, 0] * normal[:, 1, 1] - normal[:, 0, 1] * normal[:, 1, 0]
    scale = np.maximum(normal[:, 0, 0] + normal[:, 1, 1], 0.0) ** 2
    solvable = determinant > 1e-12 * np.maximum(scale, np.finfo(float).tiny)
    safe = np.where(solvable, determinant, 1.0)
    out = np.stack([(normal[:, 1, 1] * right[:, 0] - normal[:, 0, 1] * right[:, 1]) / safe,
                    (normal[:, 0, 0] * right[:, 1] - normal[:, 1, 0] * right[:, 0]) / safe], axis=1)
    return np.where(solvable[:, None], out, 0.0), solvable


def _patch_cost(residual: np.ndarray) -> np.ndarray:
    """The root mean square residual over a patch; a patch with nothing left to compare costs infinity."""
    finite = np.isfinite(residual)
    count = finite.sum(axis=1)
    total = np.where(finite, residual, 0.0) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(count > 0, np.sqrt(total.sum(axis=1) / np.maximum(count, 1)), np.inf)


def _accept(second: np.ndarray, target: np.ndarray, patch_pixels: np.ndarray, v: np.ndarray,
            step: np.ndarray, alive: np.ndarray, best: np.ndarray, extent: int,
            halvings: int = 4) -> np.ndarray:
    """Take the step where it lowers the patch residual, halving it where it does not."""
    out = v.copy()
    pending = alive.copy()
    scale = np.ones(len(v))
    for _ in range(halvings + 1):
        if not pending.any():
            break
        trial = v + step * scale[:, None]
        residual = sample(second, lattice_uv(patch_pixels + trial[:, None, :]), extent) - target
        cost = _patch_cost(residual)
        better = pending & np.isfinite(cost) & (cost <= best)
        out[better] = trial[better]
        pending &= ~better
        scale = scale / 2
    return out
