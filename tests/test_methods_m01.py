"""M01 on scenes whose distances are known exactly, and on the two scenes where nothing can be known.

The positive control is the one case C15 is built from: fronto-parallel textured planes at stated depths
with the camera translating sideways at a stated speed. The method must return those depths. The negative
controls are C13 (the camera turns in place) and C14 (nothing moves at all): the method must return
nothing, everywhere, because distance from motion is not observable without translation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import m01, readout, sweep  # noqa: E402
from conectoma.vision import render, synthetic  # noqa: E402

WIDTH = HEIGHT = 480
FOV_DEG = 90.0
SPACING_DEG = 3.415709      # the corpus's TartanAir spacing, so the geometry is the one in use


def planes_clip(depths, speed_m_s=1.0, frames=4, interval_s=0.1, contrast=0.4, seed=5):
    """A C15-style clip, rendered onto the lattice with the poses of its own sideways translation."""
    K = synthetic.intrinsics(WIDTH, HEIGHT, FOV_DEG)
    scene = synthetic.textured_planes(K, WIDTH, HEIGHT, depths, speed_m_s, frames, interval_s,
                                      contrast, seed)
    clip = render.to_lattice(scene["lum"], scene["depth"], flow_px=scene["flow_px"],
                             flow_ok=scene["flow_ok"])
    # the camera moves along its own x axis, which is +y in the release's NED pose frame
    step = speed_m_s * interval_s
    clip["poses"] = np.array([[0.0, step * t, 0.0, 0.0, 0.0, 0.0, 1.0] for t in range(frames)])
    clip["figure"] = scene["figure"]
    # what share of a column's box sits at the column's own depth: a column that straddles two planes
    # measures neither of them
    from conectoma.vision import eye
    nearest = np.abs(eye.resize_rows(scene["depth"], nearest=True)[:, None] - np.array(depths)[None, :,
                     None, None]).argmin(axis=1)
    shares = np.stack([eye.box_share(nearest == i) for i in range(len(depths))])
    clip["purity"] = shares.max(axis=0)
    return clip


def test_the_sweep_finds_the_distance_of_a_plane():
    """One plane, known distance, known translation: the sweep must land on it.

    The columns agree on the plane but each one is uncertain about it: the texture is 1/f and smooth, so a
    single column's patch matches over a range of depths. The median is the plane; the spread is the
    honest per-column uncertainty, and the sweep reports it rather than hiding it.
    """
    # a plane at 3 m moves 7.3 px between frames here, half a lattice step; one at 8 m moves 2.7 px, a
    # fifth of a step, and the lattice cannot resolve that: the measured bias is toward larger distance
    for distance, tolerance in ((3.0, 0.1), (8.0, 0.4)):
        clip = planes_clip([distance])
        rotation, translation = readout.relative_motions(clip["poses"])[0]
        out = sweep.sweep(clip["lum"][0], clip["lum"][1], rotation, translation, SPACING_DEG)
        answered = np.isfinite(out["distance_m"]) & ~out["at_edge"]
        assert answered.mean() > 0.5, (distance, answered.mean())
        found = np.median(out["distance_m"][answered])
        assert found == pytest.approx(distance, rel=tolerance), (distance, found)
        assert np.median(out["uncertainty"][answered]) > 0.2, "a smooth texture is not a sharp match"


def test_m01_recovers_three_planes_and_says_which_columns_it_claims():
    depths = [2.0, 5.0, 12.0]
    clip = planes_clip(depths)
    out = m01.run(clip, SPACING_DEG)
    truth = clip["depth"][:-1]
    claimed = ~out["unknown"] & np.isfinite(out["distance_m"]) & np.isfinite(truth)
    assert 0.05 < claimed.mean() < 0.95, claimed.mean()
    relative = np.abs(out["distance_m"][claimed] - truth[claimed]) / truth[claimed]
    assert np.median(relative) < 0.25, np.median(relative)
    # what it claims is what it was sure of: the columns it refused are not more accurate than these
    refused = out["unknown"] & np.isfinite(out["distance_m"]) & np.isfinite(truth)
    if refused.sum() > 50:
        refused_error = np.abs(out["distance_m"][refused] - truth[refused]) / truth[refused]
        assert np.median(refused_error) > np.median(relative)


def test_each_plane_is_found_where_it_is():
    """Per plane, over the columns whose box sees only that plane, before any confidence filter.

    The filter is deliberately left out here. On this scene the columns M01 is most confident about on the
    middle plane are the ones whose box catches a nearer band, because that band has the stronger parallax:
    a confident subset is not an unbiased subset, and the evaluation reports both.
    """
    depths = [2.0, 5.0, 12.0]
    clip = planes_clip(depths)
    rotation, translation = readout.relative_motions(clip["poses"])[0]
    out = sweep.sweep(clip["lum"][0], clip["lum"][1], rotation, translation, SPACING_DEG)
    truth, purity = clip["depth"][0], clip["purity"][0]
    for depth in depths:
        pure = (np.abs(truth - depth) < 1e-3) & (purity > 0.95) & np.isfinite(out["distance_m"])
        if pure.sum() > 50:
            found = np.median(out["distance_m"][pure])
            assert found == pytest.approx(depth, rel=0.3), (depth, found, pure.sum())


def test_the_committed_flow_gives_the_floor_on_the_same_scene():
    """With the exact flow the distance still is not exact: the box averages what it sees."""
    clip = planes_clip([2.0, 5.0, 12.0])
    out = m01.floor(clip, SPACING_DEG)
    truth = clip["depth"][:-1]
    claimed = ~out["unknown"] & np.isfinite(out["distance_m"]) & np.isfinite(truth)
    assert claimed.mean() > 0.5
    relative = np.abs(out["distance_m"][claimed] - truth[claimed]) / truth[claimed]
    assert np.median(relative) < 0.05, np.median(relative)


def test_pure_rotation_is_refused_everywhere():
    """C13: the camera turns in place, so no column has a baseline and none may claim a distance."""
    K = synthetic.intrinsics(WIDTH, HEIGHT, FOV_DEG)
    scene = synthetic.textured_planes(K, WIDTH, HEIGHT, [4.0, 9.0], 1.0, 1, 0.1, 0.4, seed=3)
    turned = synthetic.pure_rotation(scene["lum"][0], scene["depth"][0], K, 30.0, 4, 0.1)
    clip = render.to_lattice(turned["lum"], turned["depth"])
    clip["poses"] = np.array([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]] * 4)   # no translation at all

    out = m01.run(clip, SPACING_DEG)
    assert out["unknown"].all()
    assert np.isnan(out["distance_m"]).all()
    assert not out["moving"].any()


def test_a_static_camera_is_refused_everywhere():
    """C14: nothing moves, so there is nothing to invert."""
    K = synthetic.intrinsics(WIDTH, HEIGHT, FOV_DEG)
    scene = synthetic.textured_planes(K, WIDTH, HEIGHT, [3.0, 7.0], 1.0, 1, 0.1, 0.4, seed=9)
    still = synthetic.static_camera(scene["lum"][0], scene["depth"][0], 4, None, seed=1)
    clip = render.to_lattice(still["lum"], still["depth"])
    clip["poses"] = np.array([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]] * 4)

    out = m01.run(clip, SPACING_DEG)
    assert out["unknown"].all()


def test_a_clip_without_poses_or_flow_is_refused_loudly():
    clip = planes_clip([4.0])
    without_poses = {key: value for key, value in clip.items() if key != "poses"}
    with pytest.raises(KeyError):
        m01.run(without_poses, SPACING_DEG)
    without_flow = {key: value for key, value in clip.items() if key != "flow"}
    with pytest.raises(KeyError):
        m01.floor(without_flow, SPACING_DEG)
