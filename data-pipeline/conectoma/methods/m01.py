"""M01: distance and moving objects from motion parallax, on what the eye receives.

The method consumes the 721 luminances and the camera motion the clip commits, and nothing else, so it is
a native row of the ladder. Three steps:

1. **Sweep** each column's epipolar line for the distance whose patch matches best (`sweep`). The search is
   one-dimensional because the camera motion is known, which is what makes it possible at all on this
   corpus: between consecutive frames the columns move 39 pixels at the median and 96 at the ninth decile,
   three and seven lattice steps, far beyond the capture range of a differential estimator.
2. **Refine in two dimensions** from that distance (`flow_lattice`), which lets a column's displacement
   leave its epipolar line. For a rigid scene it cannot: the deviation from the line is therefore a test
   for independent motion that needs no distance at all.
3. **Refuse** where nothing can be claimed, for either of two independent reasons. The match did not fix
   the depth: a flat or repeating patch leaves the sweep's cost curve nearly level, and the standard error
   of its minimum, relative to the depth itself, exceeds the tolerance. Or the geometry could not have
   fixed it anyway: a column with no baseline across its line of sight, which is every column under pure
   rotation and the column looking along the direction of travel. Cases C13, C14 and C16 grade those
   refusals, and a method that answers everywhere fails them.

**The lattice's own limit.** A column's neighbours are 13 pixels away, so a displacement much smaller than
that is measured through the interpolation between columns and comes out slightly too small, which makes
the depth come out too large. Measured on planes at a known depth with a 0.1 m step and a focal length of
218 pixels: a plane at 3 m moves 7.3 pixels and comes back at 3.0 m, while a plane at 8 m moves 2.7 pixels,
a fifth of a lattice step, and comes back at 10.9 m. The uncertainty the method reports uses a flow noise
of 0.8 pixels for that reason, and it predicts the error it makes: 29 percent expected against 37 percent
observed for that plane. The honest reading is that distance beyond a few metres per 0.1 m of baseline is
not measurable from this eye, and the method says so instead of pretending otherwise.

**Depth here is planar depth**, the z coordinate in the camera frame, because that is what the corpus
records and what TartanAir, Spring and Hypersim all distribute. Solving for distance along the ray instead
inflates every off-axis column, by up to 1.41 at the corner of the lattice; the synthetic control caught
exactly that before any number was published.

The same inversion also runs on the flow the corpus committed (`floor`). That is not a method: it is what
the readout returns when the flow is exactly right, and it is the row every flow-based method is read
against. Measured on a TartanAir forest clip: with the committed flow the readout recovers the committed
depth to 0.9 percent median relative error over 88 percent of columns, so the arithmetic after the flow
costs essentially nothing and a method's error is its flow's error. The same clip, with this method's own
estimate: 8.1 percent over 43 percent of columns.
"""

from __future__ import annotations

import numpy as np

from conectoma.methods import flow_lattice, readout, sweep

# Defaults. The protocol fixes every threshold on the calibration split and freezes it; these are the
# values used until that sweep runs, and every report records what it used.
FLOW_NOISE_PX = 0.8          # measured: what a displacement below one lattice step is known to (below)
UNCERTAINTY_TOLERANCE = 0.5  # a distance is claimed while sigma_Z / Z stays below this
MATCH_TOLERANCE = 0.35       # the match must fix the inverse depth to within this, relatively
MAX_DEVIATION_DEG = 8.0      # farther off the epipolar line than this and the column is not rigid
MIN_PARALLAX_PX = 1.0        # a displacement smaller than this has no direction to judge
REFINEMENTS = 3              # two-dimensional steps from the sweep's answer


def run(clip: dict, column_spacing_deg: float, *, flow_noise_px: float = FLOW_NOISE_PX,
        tolerance: float = UNCERTAINTY_TOLERANCE, match_tolerance: float = MATCH_TOLERANCE,
        max_deviation_deg: float = MAX_DEVIATION_DEG, min_parallax_px: float = MIN_PARALLAX_PX,
        nearest_m: float = sweep.NEAREST_M, levels: int | None = None,
        refinements: int = REFINEMENTS) -> dict[str, np.ndarray]:
    """Run M01 on a rendered clip (contract 1), one row per consecutive pair of frames."""
    lum, poses, steps = _clip_arrays(clip)
    motions = readout.relative_motions(poses)
    distance = np.full((steps, readout.COLUMNS), np.nan)
    uncertainty = np.full((steps, readout.COLUMNS), np.inf)
    match = np.full((steps, readout.COLUMNS), np.inf)
    refused = np.ones((steps, readout.COLUMNS), dtype=bool)
    independent = np.zeros((steps, readout.COLUMNS), dtype=bool)
    deviation = np.full((steps, readout.COLUMNS), np.nan)

    for step in range(steps):
        rotation, translation = motions[step]
        found = sweep.sweep(lum[step], lum[step + 1], rotation, translation, column_spacing_deg,
                            nearest_m, levels)
        start = sweep.landing_flow(found["inverse_distance"], rotation, translation, column_spacing_deg)
        refined = flow_lattice.flow(lum[step:step + 2], refinements=refinements,
                                    initial=start[None, ...])
        rigid = readout.triangulate(np.where(np.isfinite(refined["velocity_px"][0]),
                                             refined["velocity_px"][0], start),
                                    rotation, translation, column_spacing_deg)
        sigma = readout.distance_uncertainty(found["distance_m"], rigid["baseline_m"],
                                             column_spacing_deg, flow_noise_px)
        # two independent reasons to refuse: the match did not localise the depth (no texture, a repeating
        # pattern, a patch that straddles an edge), and the geometry could not have localised it anyway
        bad = (readout.unknown(found["distance_m"], sigma, tolerance)
               | ~np.isfinite(found["uncertainty"]) | (found["uncertainty"] > match_tolerance)
               | found["at_edge"] | (found["curvature"] <= 0))
        distance[step] = np.where(bad, np.nan, found["distance_m"])
        uncertainty[step] = sigma
        match[step] = found["uncertainty"]
        refused[step] = bad
        deviation[step] = rigid["deviation_deg"]
        independent[step] = readout.moving(rigid["deviation_deg"], rigid["parallax_px"],
                                           max_deviation_deg, min_parallax_px) & ~bad
    return _result(distance, refused, independent, uncertainty, match, deviation)


def floor(clip: dict, column_spacing_deg: float, *, flow_noise_px: float = FLOW_NOISE_PX,
          tolerance: float = UNCERTAINTY_TOLERANCE, max_deviation_deg: float = MAX_DEVIATION_DEG,
          min_parallax_px: float = MIN_PARALLAX_PX) -> dict[str, np.ndarray]:
    """The same inversion on the flow the corpus committed: the best any flow-based row could do."""
    if "flow" not in clip:
        raise KeyError("this clip carries no committed flow, so it has no floor")
    lum, poses, steps = _clip_arrays(clip)
    committed = readout.pixel_flow(clip["flow"])
    motions = readout.relative_motions(poses)
    distance = np.full((steps, readout.COLUMNS), np.nan)
    uncertainty = np.full((steps, readout.COLUMNS), np.inf)
    refused = np.ones((steps, readout.COLUMNS), dtype=bool)
    independent = np.zeros((steps, readout.COLUMNS), dtype=bool)
    deviation = np.full((steps, readout.COLUMNS), np.nan)

    for step in range(min(steps, len(committed))):
        rotation, translation = motions[step]
        out = readout.triangulate(committed[step], rotation, translation, column_spacing_deg)
        sigma = readout.distance_uncertainty(out["distance_m"], out["baseline_m"],
                                             column_spacing_deg, flow_noise_px)
        bad = readout.unknown(out["distance_m"], sigma, tolerance)
        distance[step] = np.where(bad, np.nan, out["distance_m"])
        uncertainty[step] = sigma
        refused[step] = bad
        deviation[step] = out["deviation_deg"]
        independent[step] = readout.moving(out["deviation_deg"], out["parallax_px"],
                                           max_deviation_deg, min_parallax_px) & ~bad
    return _result(distance, refused, independent, uncertainty, np.zeros_like(uncertainty), deviation)


def _clip_arrays(clip: dict) -> tuple[np.ndarray, np.ndarray, int]:
    lum = np.asarray(clip["lum"], dtype=np.float64)
    poses = np.asarray(clip["poses"], dtype=np.float64)
    if lum.ndim != 2 or lum.shape[1] != readout.COLUMNS:
        raise ValueError(f"expected (frames, {readout.COLUMNS}) luminances, got {lum.shape}")
    if len(poses) != len(lum):
        raise ValueError(f"{len(lum)} frames but {len(poses)} poses")
    return lum, poses, len(lum) - 1


def _result(distance, refused, independent, uncertainty, match, deviation) -> dict[str, np.ndarray]:
    return {
        "distance_m": distance.astype(np.float32),
        "unknown": refused,
        "moving": independent,
        "uncertainty": uncertainty.astype(np.float32),
        "match_uncertainty": match.astype(np.float32),
        "deviation_deg": deviation.astype(np.float32),
    }
