"""M03: depth from a Hassenstein-Reichardt array, the fly's own motion detector, untrained.

The detector (`conectoma.methods.emd`) is the model of the fly's elementary motion detector, and it is not
a velocity sensor: its response depends on the temporal frequency a pattern presents, so the same speed
over a finer texture gives a different answer (measured in `tests/test_methods_emd.py`: a ratio above 1.5
between two periods at one speed). A response therefore cannot be read as a displacement without a
calibration, and this module is explicit about the one it uses:

1. **Pool, then calibrate.** A single column's correlator cannot be read as a displacement at all: one
   gain fitted from it explains less than the mean does (r2 = -0.14 on a synthetic scene, measured).
   Averaged over neighbours it becomes something a gain fits, r2 = 0.33, 0.50 and 0.60 after one, two and
   three rings, which is what the fly's wide-field cells do with the outputs of its detectors. The gain is
   then fitted by least squares on clips whose displacement is known, on the calibration split and on
   synthetic scenes only, never on the test clips a case is scored on. The cost is stated with the result:
   the depth M03 produces is smoothed over the pooled neighbourhood.
2. **Read.** `velocity = k * response`, then the same parallax inversion every motion method here uses
   (`conectoma.methods.readout`), so M03 and M01 differ only in how the displacement was obtained.
3. **Report what the calibration does not cover.** The gain is fitted at one texture and one contrast; the
   residual dependence on both is a result of this unit, not an error to tune away. It predicts where M03
   must fail (C07 contrast, C16 texture) and the prediction is stated before the numbers.

The time constant `tau` is not taken from the literature. The reviews that state one for the fly are
paywalled and the secondary summaries disagree, so it is swept over a decade around the frame interval
and chosen on the calibration clips by the same criterion for every source (`sweep_tau`). What was swept
and what was chosen is recorded in the report that used it.
"""

from __future__ import annotations

import numpy as np

from conectoma.methods import emd, readout
from conectoma.methods.m01 import (
    FLOW_NOISE_PX,
    MAX_DEVIATION_DEG,
    MIN_PARALLAX_PX,
    UNCERTAINTY_TOLERANCE,
    _clip_motions,
    _result,
)

TAU_FACTORS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)   # a decade around the frame interval
POOL_RINGS = 3                                   # measured below: a single column's response fits nothing
MIN_RESPONSE = 1e-12                             # below this the column saw nothing to correlate


def gain_for(response_vectors: np.ndarray, flow_px: np.ndarray) -> dict[str, float]:
    """The least-squares gain taking correlator units to pixels, with how well one number fits.

    One scalar for both axes, because the correlator's units are the same on both and a per-axis gain
    would hide a geometric error as a calibration.
    """
    response = np.asarray(response_vectors, dtype=np.float64)
    flow = np.asarray(flow_px, dtype=np.float64)
    usable = np.isfinite(response).all(axis=1) & np.isfinite(flow).all(axis=1)
    x = response[:, :, :][np.broadcast_to(usable[:, None, :], response.shape)]
    y = flow[np.broadcast_to(usable[:, None, :], flow.shape)]
    if x.size < 2 or not np.any(x):
        return {"gain": float("nan"), "r2": float("nan"), "samples": 0}
    gain = float(x @ y / (x @ x))
    residual = y - gain * x
    total = float(((y - y.mean()) ** 2).sum())
    return {
        "gain": gain,
        "r2": float(1.0 - (residual**2).sum() / total) if total > 0 else float("nan"),
        "samples": int(x.size),
    }


def calibrate(clips: list[dict], tau_s: float, interval_s: float | None = None,
              rings: int = POOL_RINGS) -> dict[str, float]:
    """Fit the gain over several clips that carry a committed flow (the calibration set)."""
    responses, flows = [], []
    for clip in clips:
        if "flow" not in clip:
            continue
        step = interval_s if interval_s is not None else clip.get("interval_s")
        if step is None:
            raise ValueError("a calibration clip needs its frame interval")
        vectors = emd.pool(emd.motion_vectors(emd.responses(clip["lum"], tau_s, float(step))), rings)
        responses.append(vectors)
        flows.append(readout.pixel_flow(clip["flow"])[: len(vectors)])
    if not responses:
        return {"gain": float("nan"), "r2": float("nan"), "samples": 0, "tau_s": tau_s}
    return {"tau_s": tau_s, "rings": rings,
            **gain_for(np.concatenate(responses), np.concatenate(flows))}


def sweep_tau(clips: list[dict], interval_s: float, factors: tuple = TAU_FACTORS,
              rings: int = POOL_RINGS) -> list[dict]:
    """Calibrate at each time constant; the caller keeps the one that fits the calibration clips best."""
    return [calibrate(clips, factor * interval_s, interval_s, rings) for factor in factors]


def run(clip: dict, column_spacing_deg: float, *, tau_s: float, gain: float,
        rings: int = POOL_RINGS, interval_s: float | None = None, motion: tuple | None = None,
        flow_noise_px: float = FLOW_NOISE_PX, tolerance: float = UNCERTAINTY_TOLERANCE,
        max_deviation_deg: float = MAX_DEVIATION_DEG, min_parallax_px: float = MIN_PARALLAX_PX,
        ) -> dict[str, np.ndarray]:
    """Run M03 on a rendered clip with a calibration that was fitted elsewhere."""
    lum, motions, steps = _clip_motions(clip, motion)
    step_s = interval_s if interval_s is not None else clip.get("interval_s")
    if step_s is None:
        raise ValueError("M03 needs the clip's frame interval: the correlator has a time constant")
    response = emd.responses(lum, tau_s, float(step_s))
    vectors = emd.pool(emd.motion_vectors(response), rings)
    strength = np.linalg.norm(vectors, axis=1)
    velocity = gain * vectors

    distance = np.full((steps, readout.COLUMNS), np.nan)
    uncertainty = np.full((steps, readout.COLUMNS), np.inf)
    refused = np.ones((steps, readout.COLUMNS), dtype=bool)
    independent = np.zeros((steps, readout.COLUMNS), dtype=bool)
    deviation = np.full((steps, readout.COLUMNS), np.nan)
    disagreement = emd.residual(response, vectors)

    for step in range(steps):
        rotation, translation = motions[step]
        if not np.any(translation):
            continue
        out = readout.triangulate(velocity[step], rotation, translation, column_spacing_deg)
        sigma = readout.distance_uncertainty(out["distance_m"], out["baseline_m"],
                                             column_spacing_deg, flow_noise_px)
        # a column whose three axes barely responded has no motion to read, whatever the gain says
        quiet = strength[step] <= MIN_RESPONSE
        bad = readout.unknown(out["distance_m"], sigma, tolerance) | quiet
        distance[step] = np.where(bad, np.nan, out["distance_m"])
        uncertainty[step] = sigma
        refused[step] = bad
        deviation[step] = out["deviation_deg"]
        independent[step] = readout.moving(out["deviation_deg"], out["parallax_px"],
                                           max_deviation_deg, min_parallax_px) & ~bad
    return _result(distance, refused, independent, uncertainty, disagreement, deviation)


# ------------------------------------------------------------------- the calibration set, and choosing on it

CALIBRATION_SEED = 20260922
CALIBRATION_DEPTHS = ([1.5, 3.0, 6.0], [2.5, 5.0, 10.0], [4.0, 8.0, 16.0], [1.0, 2.0, 4.0])
CALIBRATION_CONTRASTS = (0.35, 0.2, 0.35, 0.1)


def calibration_clips(frames: int = 12, seed: int = CALIBRATION_SEED) -> list[dict]:
    """Synthetic scenes generated for the calibration, with their own seeds.

    NOT the synthetic cases: those are test data, and fitting a gain on them would be fitting on what the
    method is scored on. These use their own depths, contrasts and seed, and the same camera motion the
    positive control uses, which is what makes the fitted gain transferable at all.
    """
    from conectoma.vision import cases, render, synthetic

    out = []
    for index, (depths, contrast) in enumerate(zip(CALIBRATION_DEPTHS, CALIBRATION_CONTRASTS,
                                                   strict=True)):
        scene = synthetic.textured_planes(cases.TARTANAIR_K, 640, 640, list(depths),
                                          cases.PLANES_SPEED_M_S, frames, cases.TARTANAIR_INTERVAL_S,
                                          contrast, seed + index)
        clip = render.to_lattice(scene["lum"], scene["depth"], flow_px=scene["flow_px"],
                                 flow_ok=scene["flow_ok"])
        clip["interval_s"] = cases.TARTANAIR_INTERVAL_S
        out.append(clip)
    return out


def choose(interval_s: float | None = None, rings: int = POOL_RINGS) -> dict:
    """Sweep the time constant on the calibration set and keep the one that fits it best."""
    from conectoma.vision import cases

    step = interval_s if interval_s is not None else cases.TARTANAIR_INTERVAL_S
    clips = calibration_clips()
    swept = sweep_tau(clips, step, rings=rings)
    usable = [row for row in swept if np.isfinite(row.get("r2", np.nan))]
    if not usable:
        raise RuntimeError("the calibration set produced no usable fit")
    best = max(usable, key=lambda row: row["r2"])
    return {
        "chosen": best,
        "swept": swept,
        "interval_s": step,
        "rings": rings,
        "seed": CALIBRATION_SEED,
        "clips": len(clips),
        "depths_m": [list(d) for d in CALIBRATION_DEPTHS],
        "contrasts": list(CALIBRATION_CONTRASTS),
    }
