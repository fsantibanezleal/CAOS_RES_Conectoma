"""M02: semi-global matching on a stereo pair, scored where every other method is scored.

The pair is synthesised the same way the positive control is, with the camera step set to the release's
own baseline, so the test knows the depths it must recover.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import m02, readout  # noqa: E402
from conectoma.vision import cases, synthetic  # noqa: E402


def stereo_pair(depths, contrast=0.35, seed=3):
    """Two views of the same planes, the second one baseline metres to the right of the first."""
    K = synthetic.intrinsics(640, 640, 90.0)
    scene = synthetic.textured_planes(K, 640, 640, depths, m02.BASELINE_M, 2, 1.0, contrast, seed)
    frames = (np.clip(scene["lum"], 0, 1) * 255).astype(np.uint8)
    return frames[:1], frames[1:], scene["depth"][:1]


def test_the_matcher_recovers_planes_at_their_depths():
    depths = [3.0, 6.0, 12.0]
    left, right, truth = stereo_pair(depths)
    found = m02.depth_from(left[0], right[0])
    for depth in depths:
        on_plane = np.isfinite(found) & (np.abs(truth[0] - depth) < 1e-3)
        if on_plane.sum() > 500:
            assert np.median(found[on_plane]) == pytest.approx(depth, rel=0.1), depth


def test_the_answer_lands_on_the_lattice_with_the_shape_every_method_returns():
    left, right, _ = stereo_pair([4.0, 8.0])
    out = m02.run(np.repeat(left, 3, axis=0), np.repeat(right, 3, axis=0))
    assert out["distance_m"].shape == (2, readout.COLUMNS)
    assert out["unknown"].shape == out["distance_m"].shape
    assert not out["moving"].any()               # stereo says nothing about independent motion
    claimed = ~out["unknown"]
    assert claimed.mean() > 0.3


def test_an_invalid_disparity_is_refused_not_filled():
    """Two images of unrelated noise: the matcher must decline, not invent a depth."""
    rng = np.random.default_rng(2)
    left = rng.integers(0, 255, (1, 640, 640), dtype=np.uint8)
    right = rng.integers(0, 255, (1, 640, 640), dtype=np.uint8)
    out = m02.run(np.repeat(left, 2, axis=0), np.repeat(right, 2, axis=0))
    assert out["unknown"].mean() > 0.5


def test_a_mismatched_pair_is_refused_loudly():
    left, right, _ = stereo_pair([4.0])
    with pytest.raises(ValueError):
        m02.run(left, right[:, :100])


def test_the_geometry_is_the_releases_own():
    assert m02.BASELINE_M == 0.25
    assert m02.FOCAL_PX == 320.0
    assert cases.TARTANAIR_K[0, 0] == m02.FOCAL_PX
