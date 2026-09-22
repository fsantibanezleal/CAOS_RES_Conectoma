"""M03: what a correlator can give once it is calibrated, and what the calibration does not cover.

The calibration is fitted on one scene and used on another, never on the clip being scored, so the tests
say what the method does on data it has not been fitted to.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import emd, m03  # noqa: E402
from conectoma.vision import cases, render, synthetic  # noqa: E402

INTERVAL_S = cases.TARTANAIR_INTERVAL_S
SPACING_DEG = cases.TARTANAIR_SPACING_DEG


def planes(depths, contrast=0.35, seed=5, frames=8):
    K = synthetic.intrinsics(640, 640, 90.0)
    scene = synthetic.textured_planes(K, 640, 640, depths, cases.PLANES_SPEED_M_S, frames,
                                      INTERVAL_S, contrast, seed)
    clip = render.to_lattice(scene["lum"], scene["depth"], flow_px=scene["flow_px"],
                             flow_ok=scene["flow_ok"])
    clip["interval_s"] = INTERVAL_S
    return clip


def test_the_gain_is_one_number_and_it_fits():
    clip = planes([2.0, 4.0, 8.0])
    fitted = m03.calibrate([clip], tau_s=INTERVAL_S)
    assert fitted["samples"] > 1000
    assert np.isfinite(fitted["gain"]) and fitted["gain"] != 0
    assert fitted["r2"] > 0.2, fitted        # one scalar explains a real share of the displacement


def test_the_time_constant_is_swept_not_assumed():
    clip = planes([2.0, 4.0, 8.0])
    swept = m03.sweep_tau([clip], INTERVAL_S)
    assert len(swept) == len(m03.TAU_FACTORS)
    best = max(swept, key=lambda row: row["r2"] if np.isfinite(row["r2"]) else -np.inf)
    assert np.isfinite(best["r2"])
    # the fit is not flat across the decade: the time constant matters, which is why it is swept
    scores = [row["r2"] for row in swept if np.isfinite(row["r2"])]
    assert max(scores) - min(scores) > 0.02, scores


def test_a_calibrated_correlator_gives_a_depth_on_a_scene_it_was_not_fitted_to():
    fitting = planes([2.0, 4.0, 8.0], seed=5)
    scoring = planes([3.0, 6.0, 12.0], seed=11)
    fitted = m03.calibrate([fitting], tau_s=INTERVAL_S)

    out = m03.run(scoring, SPACING_DEG, tau_s=INTERVAL_S, gain=fitted["gain"],
                  motion=cases.step_motion({"variant": {"transform": "planes", "levels": [1]}}, 0))
    truth = scoring["depth"][:-1]
    claimed = ~out["unknown"] & np.isfinite(out["distance_m"]) & np.isfinite(truth)
    assert claimed.mean() > 0.2, claimed.mean()
    relative = np.abs(out["distance_m"][claimed] - truth[claimed]) / truth[claimed]
    # a correlator is a coarse instrument: the test states what it achieves rather than a wish
    assert np.median(relative) < 0.6, np.median(relative)


def test_the_calibration_does_not_transfer_across_contrast():
    """The result this unit is for: the gain fitted at one contrast is wrong at another."""
    bright = planes([2.0, 4.0, 8.0], contrast=0.35, seed=5)
    faint = planes([2.0, 4.0, 8.0], contrast=0.05, seed=5)
    first = m03.calibrate([bright], tau_s=INTERVAL_S)["gain"]
    second = m03.calibrate([faint], tau_s=INTERVAL_S)["gain"]
    assert abs(second / first) > 3, (first, second)


def test_a_clip_without_an_interval_is_refused_loudly():
    clip = planes([4.0])
    clip.pop("interval_s")
    with pytest.raises(ValueError):
        m03.run(clip, SPACING_DEG, tau_s=INTERVAL_S, gain=1.0,
                motion=cases.step_motion({"variant": {"transform": "planes", "levels": [1]}}, 0))


def test_the_response_used_is_the_correlators_own():
    clip = planes([4.0])
    response = emd.responses(clip["lum"], INTERVAL_S, INTERVAL_S)
    assert response.shape == (clip["lum"].shape[0] - 1, 3, clip["lum"].shape[1])
    assert np.isfinite(response).all()
