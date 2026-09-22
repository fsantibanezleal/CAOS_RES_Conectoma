"""The correlator: that it is direction-selective, and that it measures temporal frequency, not speed.

The second property is the one that decides how M03 has to be built, so it is measured here rather than
asserted in prose: the same speed over a finer pattern gives a different response, so a response cannot be
read as a velocity without a calibration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import emd, readout  # noqa: E402
from conectoma.vision import eye  # noqa: E402

SIZE = 436
INTERVAL_S = 0.1


def drifting_grating(period_px: float, speed_px_per_frame: float, frames: int = 12,
                     angle_deg: float = 0.0) -> np.ndarray:
    """A sinusoidal grating drifting at a known speed, rendered onto the lattice frame by frame."""
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
    angle = np.radians(angle_deg)
    projected = x * np.cos(angle) + y * np.sin(angle)
    out = []
    for t in range(frames):
        phase = 2 * np.pi * (projected - speed_px_per_frame * t) / period_px
        out.append(0.5 + 0.25 * np.cos(phase))
    return eye.box_mean(np.stack(out))


def test_the_response_reverses_with_the_direction_of_motion():
    forward = emd.responses(drifting_grating(80.0, 4.0), 0.1, INTERVAL_S)
    backward = emd.responses(drifting_grating(80.0, -4.0), 0.1, INTERVAL_S)
    # the horizontal axis is the one the grating drifts along
    axis = int(np.argmax(np.abs(emd.axis_directions()[:, 0])))
    ahead = np.median(forward[3:, axis, :])
    behind = np.median(backward[3:, axis, :])
    assert ahead * behind < 0, (ahead, behind)
    assert abs(ahead) > 1e-6


def test_a_still_pattern_gives_no_response():
    still = drifting_grating(80.0, 0.0)
    response = emd.responses(still, 0.1, INTERVAL_S)
    assert np.allclose(response, 0.0, atol=1e-12)


def test_the_response_is_tuned_to_temporal_frequency_not_to_speed():
    """The measurement M03 is built around: at one speed, two periods give different responses."""
    axis = int(np.argmax(np.abs(emd.axis_directions()[:, 0])))
    speed = 3.0
    coarse = emd.responses(drifting_grating(160.0, speed), 0.1, INTERVAL_S)
    fine = emd.responses(drifting_grating(70.0, speed), 0.1, INTERVAL_S)
    first = abs(np.median(coarse[3:, axis, :]))
    second = abs(np.median(fine[3:, axis, :]))
    assert first > 0 and second > 0
    ratio = max(first, second) / min(first, second)
    assert ratio > 1.5, ratio          # the same speed, a different answer: a response is not a velocity


def test_the_low_pass_is_the_discrete_exponential():
    step = np.zeros((6, 1))
    step[1:] = 1.0
    tau = 0.2
    filtered = emd.low_pass(step, tau, INTERVAL_S)
    alpha = 1.0 - np.exp(-INTERVAL_S / tau)
    assert filtered[0, 0] == pytest.approx(0.0)
    assert filtered[1, 0] == pytest.approx(alpha)
    assert filtered[2, 0] == pytest.approx(alpha + alpha * (1 - alpha))
    assert emd.low_pass(step, 0.0, INTERVAL_S)[1, 0] == pytest.approx(1.0)   # no delay at all


def test_the_three_axes_combine_into_one_vector():
    response = emd.responses(drifting_grating(80.0, 4.0), 0.1, INTERVAL_S)
    vectors = emd.motion_vectors(response)
    assert vectors.shape == (response.shape[0], 2, readout.COLUMNS)
    # the grating drifts along x, so the vector must point along x, and the axes must agree
    late = vectors[4:]
    assert abs(np.median(late[:, 0, :])) > 3 * abs(np.median(late[:, 1, :]))
    assert np.median(emd.residual(response, vectors)[4:]) < np.median(np.abs(response[4:])) * 0.5


def test_the_axes_are_the_lattice_axes():
    """Three distinct axes that span the plane, at the angles the engine's lattice actually has.

    Not sixty degrees apart: the lattice is stretched along the row axis (vertical neighbours 13 pixels
    apart, diagonal ones at (13, 6.5)), so in pixels the axes sit at 27, 90 and 153 degrees. The fit uses
    them as they are rather than assuming a regular hexagon.
    """
    directions = emd.axis_directions()
    assert directions.shape == (3, 2)
    assert np.allclose(np.linalg.norm(directions, axis=1), 1.0)
    angles = np.sort(np.degrees(np.arctan2(directions[:, 1], directions[:, 0])) % 180)
    assert np.allclose(angles, [26.53, 90.0, 153.47], atol=0.1), angles
    assert np.linalg.matrix_rank(directions) == 2
