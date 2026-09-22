"""The evaluation stage: what it scores, what it refuses to score, and the motion a case declares.

Nothing here needs the corpus. The clips are built in memory, so the test says what the stage does rather
than what one machine's data happens to contain.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import readout  # noqa: E402
from conectoma.stages import evaluate  # noqa: E402
from conectoma.vision import cases, render, synthetic  # noqa: E402

COLUMNS = readout.COLUMNS


def a_case(grades=("depth", "flow"), transform="speed"):
    return {"name": "a case", "category": "nominal-outdoor", "grades": list(grades),
            "variant": {"quantity": "ego speed", "unit": "x", "transform": transform,
                        "levels": [0.5, 1, 2, 4, 8, 16]}}


def test_a_case_that_grades_depth_is_scored_and_one_that_does_not_is_not():
    steps = 3
    truth = np.full((steps + 1, COLUMNS), 10.0)
    result = {"distance_m": np.full((steps, COLUMNS), 10.0),
              "unknown": np.zeros((steps, COLUMNS), dtype=bool),
              "moving": np.zeros((steps, COLUMNS), dtype=bool)}
    scored = evaluate.score_clip({"depth": truth}, result, a_case())
    assert scored["abs_rel"] == pytest.approx(0.0)
    assert scored["coverage"] == pytest.approx(1.0)
    assert scored["refusal_refused"] == pytest.approx(0.0)

    unobservable = evaluate.score_clip({"depth": truth}, result, a_case(grades=("uncertainty",)))
    assert "abs_rel" not in unobservable
    assert unobservable["refusal_correct"] == pytest.approx(0.0)   # it claimed what it could not know


def test_refusing_everything_is_the_right_answer_where_nothing_is_observable():
    steps = 2
    truth = np.full((steps + 1, COLUMNS), 5.0)
    result = {"distance_m": np.full((steps, COLUMNS), np.nan),
              "unknown": np.ones((steps, COLUMNS), dtype=bool),
              "moving": np.zeros((steps, COLUMNS), dtype=bool)}
    scored = evaluate.score_clip({"depth": truth}, result, a_case(grades=("uncertainty",)))
    assert scored["refusal_refused"] == pytest.approx(1.0)
    assert scored["refusal_correct"] == pytest.approx(1.0)


def test_a_depth_edge_needs_two_claimed_neighbours():
    distance = np.full((1, COLUMNS), 10.0)
    assert not evaluate._depth_edges(distance).any()
    distance[0, 300] = 40.0
    edges = evaluate._depth_edges(distance)
    assert edges[0, 300]
    assert edges[0].sum() > 1                       # its neighbours see the jump too
    nothing = np.full((1, COLUMNS), np.nan)
    assert not evaluate._depth_edges(nothing).any()


def test_the_motion_a_synthetic_case_declares_matches_its_own_rendering():
    """The declared motion must reproduce the flow the renderer committed, or a sign error would survive.

    Built here exactly as the case builder builds it: planes at known depths, the camera sliding sideways.
    The committed flow, inverted with the declared motion, must return the committed depth.
    """
    from conectoma.methods import m01

    K = synthetic.intrinsics(640, 640, 90.0)
    scene = synthetic.textured_planes(K, 640, 640, [2.0, 4.0, 8.0], cases.PLANES_SPEED_M_S, 4,
                                      cases.TARTANAIR_INTERVAL_S, 0.35, seed=5)
    clip = render.to_lattice(scene["lum"], scene["depth"], flow_px=scene["flow_px"],
                             flow_ok=scene["flow_ok"])
    motion = cases.step_motion(a_case(transform="planes"), level=0)
    assert motion is not None

    out = m01.floor(clip, cases.TARTANAIR_SPACING_DEG, motion=motion)
    truth = clip["depth"][:-1]
    claimed = ~out["unknown"] & np.isfinite(out["distance_m"]) & np.isfinite(truth)
    assert claimed.mean() > 0.5
    relative = np.abs(out["distance_m"][claimed] - truth[claimed]) / truth[claimed]
    assert np.median(relative) < 0.02, np.median(relative)


def test_a_turning_camera_declares_a_rotation_and_no_translation():
    motion = cases.step_motion({"variant": {"transform": "rotation", "levels": [0, 15, 30]}}, level=2)
    rotation, translation = motion
    assert np.allclose(translation, 0.0)
    angle = np.degrees(np.arccos((np.trace(rotation) - 1) / 2))
    assert angle == pytest.approx(30.0 * cases.TARTANAIR_INTERVAL_S, rel=1e-9)


def test_a_case_with_no_declared_motion_says_so():
    assert cases.step_motion(a_case(transform="speed"), level=0) is None
