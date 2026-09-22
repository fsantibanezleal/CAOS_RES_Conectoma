"""The readout every motion method shares: flow on the lattice plus the known ego-motion gives distance.

The tests are analytic. A scene is built at known distances, projected exactly through the same pinhole
model the corpus uses, and the readout must return the distances it was built from. Then the cases that
must NOT return a number (pure rotation, a column looking along the direction of travel) and the one that
must be flagged without any distance at all (an independently moving object).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import readout  # noqa: E402
from conectoma.vision import cases, decode, eye  # noqa: E402


def project(points: np.ndarray, focal: float) -> np.ndarray:
    return focal * points[:, :2] / points[:, 2:3]


def displacement(distance: np.ndarray, rotation: np.ndarray, translation: np.ndarray,
                 spacing_deg: float) -> np.ndarray:
    """The exact pixel displacement of each column's point, (2, columns), y down."""
    focal = readout.focal_px(spacing_deg)
    rays = readout.ray_directions(spacing_deg)
    seen = project(rays * np.asarray(distance)[:, None] @ rotation.T + translation, focal)
    return (seen - readout.column_pixels()).T


def test_focal_inverts_the_recorded_column_spacing():
    for focal in (218.0, 895.98, 100.0):
        assert readout.focal_px(cases.column_spacing_deg(focal)) == pytest.approx(focal, rel=1e-12)


def test_rays_point_where_the_lattice_looks():
    spacing = 3.415709                                    # TartanAir, as every rendering records it
    rays = readout.ray_directions(spacing)
    assert rays.shape == (readout.COLUMNS, 3)
    assert np.allclose(np.linalg.norm(rays, axis=1), 1.0)
    centre = np.argmin(np.linalg.norm(readout.column_pixels(), axis=1))
    assert np.allclose(rays[centre], [0.0, 0.0, 1.0])
    # The neighbour one kernel away on the row axis lies at atan(13 / f) from the centre, which is NOT the
    # recorded column spacing: that is the on-axis subtense 2 atan(6.5 / f), and a pinhole camera is not
    # linear in angle. The readout uses the exact rays, so the difference (0.003 degrees here, and larger
    # off axis) never enters a distance.
    pixels = readout.column_pixels()
    focal = readout.focal_px(spacing)
    neighbour = np.argmin(np.linalg.norm(pixels - np.array([0.0, readout.COLUMN_STEP_PX]), axis=1))
    angle = math.degrees(math.acos(float(rays[centre] @ rays[neighbour])))
    assert angle == pytest.approx(math.degrees(math.atan(readout.COLUMN_STEP_PX / focal)), rel=1e-12)
    assert angle < spacing


def test_distance_is_recovered_exactly_from_an_exact_displacement():
    spacing = 3.415709
    rng = np.random.default_rng(20260922)
    distance = rng.uniform(2.0, 60.0, readout.COLUMNS)
    rotation = decode.quaternion_matrix(np.array([0.01, -0.02, 0.005, 1.0]))
    translation = np.array([0.15, -0.05, 0.4])            # sideways, down and forward, in metres
    flow = displacement(distance, rotation, translation, spacing)

    out = readout.triangulate(flow, rotation, translation, spacing)
    assert np.allclose(out["distance_m"], distance, rtol=1e-5)
    assert np.nanmax(out["residual_px"]) < 1e-6           # nothing off the epipolar line
    assert np.nanmax(out["deviation_deg"]) < 1e-3


def test_pure_rotation_leaves_no_baseline_and_claims_nothing():
    spacing = 3.415709
    rotation = decode.quaternion_matrix(np.array([0.0, 0.03, 0.0, 1.0]))
    translation = np.zeros(3)
    distance = np.full(readout.COLUMNS, 12.0)
    flow = displacement(distance, rotation, translation, spacing)

    out = readout.triangulate(flow, rotation, translation, spacing)
    assert np.allclose(out["baseline_m"], 0.0)
    uncertainty = readout.distance_uncertainty(out["distance_m"], out["baseline_m"], spacing, 0.2)
    assert np.all(~np.isfinite(uncertainty))
    assert readout.unknown(out["distance_m"], uncertainty, tolerance=0.25).all()


def test_the_focus_of_expansion_has_no_baseline_either():
    """Translating straight ahead: the column looking along the motion cannot measure its distance."""
    spacing = 3.415709
    rotation = np.eye(3)
    translation = np.array([0.0, 0.0, 0.5])
    distance = np.full(readout.COLUMNS, 20.0)
    flow = displacement(distance, rotation, translation, spacing)
    out = readout.triangulate(flow, rotation, translation, spacing)

    centre = np.argmin(np.linalg.norm(readout.column_pixels(), axis=1))
    rim = np.argmax(np.linalg.norm(readout.column_pixels(), axis=1))
    assert out["baseline_m"][centre] == pytest.approx(0.0, abs=1e-12)
    assert out["baseline_m"][rim] > 0.1
    uncertainty = readout.distance_uncertainty(out["distance_m"], out["baseline_m"], spacing, 0.2)
    flagged = readout.unknown(out["distance_m"], uncertainty, tolerance=0.25)
    assert flagged[centre]
    assert not flagged[rim]


def test_uncertainty_grows_with_the_square_of_distance_over_baseline():
    spacing = 3.415709
    baseline = np.full(readout.COLUMNS, 0.3)
    near = readout.distance_uncertainty(np.full(readout.COLUMNS, 10.0), baseline, spacing, 0.2)
    far = readout.distance_uncertainty(np.full(readout.COLUMNS, 40.0), baseline, spacing, 0.2)
    assert np.allclose(far / near, 4.0, rtol=1e-6)
    # a column 40 m away, on a 0.3 m baseline, with a fifth of a pixel of flow noise, is not measurable
    assert np.all(readout.unknown(np.full(readout.COLUMNS, 40.0), far, tolerance=0.1))


def test_an_independently_moving_object_is_found_without_any_distance():
    spacing = 3.415709
    rng = np.random.default_rng(7)
    distance = rng.uniform(5.0, 30.0, readout.COLUMNS)
    rotation = decode.quaternion_matrix(np.array([0.004, 0.01, 0.0, 1.0]))
    translation = np.array([0.2, 0.0, 0.35])
    flow = displacement(distance, rotation, translation, spacing)

    out = readout.triangulate(flow, rotation, translation, spacing)
    epipolar = np.stack([out["deviation_deg"], out["parallax_px"]])
    assert np.nanmax(epipolar[0]) < 1e-3                  # the rigid scene is on its epipolar lines

    # push 40 columns sideways off their line by two pixels: a body moving on its own
    object_columns = np.arange(200, 240)
    perpendicular = np.array([-flow[1, object_columns], flow[0, object_columns]])
    perpendicular /= np.linalg.norm(perpendicular, axis=0, keepdims=True)
    moved_flow = flow.copy()
    moved_flow[:, object_columns] += 2.0 * perpendicular

    out = readout.triangulate(moved_flow, rotation, translation, spacing)
    flagged = readout.moving(out["deviation_deg"], out["parallax_px"],
                             max_deviation_deg=5.0, min_parallax_px=1.0)
    assert flagged[object_columns].mean() > 0.9
    rigid = np.ones(readout.COLUMNS, dtype=bool)
    rigid[object_columns] = False
    assert not flagged[rigid].any()


def test_engine_flow_becomes_the_mean_pixel_displacement():
    """A uniform flow of one pixel per frame, expressed the way the corpus stores it, reads back as one."""
    one_pixel_up = np.zeros((2, readout.COLUMNS))
    one_pixel_up[1] = eye.KERNEL**2 / eye.ROWS            # y up, per image height, summed over the box
    pixels = readout.pixel_flow(one_pixel_up)
    assert np.allclose(pixels[0], 0.0)
    assert np.allclose(pixels[1], -1.0)                   # y up in the engine is y down in the frame
