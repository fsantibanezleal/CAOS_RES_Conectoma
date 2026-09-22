"""The metrics, against values worked out by hand.

A metric is the thing every later claim rests on, so each one is checked against an arithmetic answer
rather than against another implementation, and the definitions that have more than one convention in the
literature (the scale-invariant error) are checked against the paper's own equation.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import metrics, readout  # noqa: E402


def test_absrel_rmse_and_deltas_are_the_arithmetic():
    truth = np.array([10.0, 20.0, 40.0])
    estimate = np.array([11.0, 18.0, 40.0])
    claimed = np.ones(3, dtype=bool)
    out = metrics.depth_metrics(truth, estimate, claimed)
    assert out["abs_rel"] == pytest.approx((0.1 + 0.1 + 0.0) / 3)
    assert out["rmse_m"] == pytest.approx(math.sqrt((1 + 4 + 0) / 3))
    assert out["delta_1"] == pytest.approx(1.0)       # every ratio is below 1.25
    assert out["coverage"] == pytest.approx(1.0)
    assert out["columns_scored"] == 3


def test_a_scale_error_alone_leaves_silog_at_zero():
    """The point of the scale-invariant error: a prediction off by one constant factor scores zero."""
    truth = np.array([2.0, 5.0, 11.0, 30.0])
    for factor in (0.5, 1.0, 3.0):
        out = metrics.depth_metrics(truth, truth * factor, np.ones(4, dtype=bool))
        assert out["silog"] == pytest.approx(0.0, abs=1e-12), factor
        if factor != 1.0:
            assert out["abs_rel"] > 0.1                # while AbsRel sees it, which is why both exist


def test_silog_is_the_papers_equation_three():
    rng = np.random.default_rng(4)
    truth = rng.uniform(1.0, 50.0, 200)
    estimate = truth * rng.uniform(0.5, 2.0, 200)
    error = np.log(estimate) - np.log(truth)
    expected = np.mean(error**2) - (error.sum() / len(error)) ** 2
    out = metrics.depth_metrics(truth, estimate, np.ones(200, dtype=bool))
    assert out["silog"] == pytest.approx(expected, rel=1e-12)


def test_coverage_counts_the_refusals_and_the_metrics_ignore_them():
    truth = np.array([10.0, 20.0, 30.0, 40.0])
    estimate = np.array([10.0, np.nan, 30.0, 400.0])
    claimed = np.array([True, False, True, False])
    out = metrics.depth_metrics(truth, estimate, claimed)
    assert out["coverage"] == pytest.approx(0.5)
    assert out["abs_rel"] == pytest.approx(0.0)        # the wild value was refused, so it is not scored
    assert out["columns_with_truth"] == 4


def test_a_relative_estimate_is_aligned_before_it_is_scored():
    truth = np.array([2.0, 4.0, 8.0, 16.0])
    # a relative estimate: inverse depth scaled and shifted away from the truth
    estimate = 1.0 / (3.0 / truth + 0.05)
    claimed = np.ones(4, dtype=bool)
    raw = metrics.depth_metrics(truth, estimate, claimed)
    aligned = metrics.depth_metrics(truth, metrics.align_inverse_depth(truth, estimate, claimed), claimed)
    assert raw["abs_rel"] > 0.5
    assert aligned["abs_rel"] == pytest.approx(0.0, abs=1e-9)


def test_an_unobservable_case_is_graded_by_what_was_refused():
    unknown = np.array([True, True, True, False])
    out = metrics.refusal(unknown, truth_is_observable=False)
    assert out["refused"] == pytest.approx(0.75)
    assert out["claimed"] == pytest.approx(0.25)
    assert out["correct"] == pytest.approx(0.75)       # refusing is right when nothing can be measured
    observable = metrics.refusal(unknown, truth_is_observable=True)
    assert observable["correct"] == pytest.approx(0.25)


def test_iou_and_its_parts():
    truth = np.array([True, True, False, False])
    predicted = np.array([True, False, True, False])
    out = metrics.mask_metrics(truth, predicted)
    assert out["iou"] == pytest.approx(1 / 3)
    assert out["precision"] == pytest.approx(0.5)
    assert out["recall"] == pytest.approx(0.5)


def test_boundary_f_forgives_one_lattice_step_and_no_more():
    from conectoma.methods import flow_lattice
    index = flow_lattice.neighbours()
    centre = np.argmin(np.linalg.norm(readout.column_pixels(), axis=1))
    neighbour = index[centre][index[centre] >= 0][0]
    second = index[neighbour][(index[neighbour] >= 0) & (index[neighbour] != centre)][0]

    truth = np.zeros(readout.COLUMNS, dtype=bool)
    truth[centre] = True
    one_step = np.zeros(readout.COLUMNS, dtype=bool)
    one_step[neighbour] = True
    two_steps = np.zeros(readout.COLUMNS, dtype=bool)
    two_steps[second] = True

    assert metrics.boundary_f(truth, one_step)["boundary_f"] == pytest.approx(1.0)
    far = metrics.boundary_f(truth, two_steps)
    assert far["boundary_f"] == pytest.approx(0.0) or math.isnan(far["boundary_f"])
    assert metrics.boundary_f(truth, truth)["boundary_f"] == pytest.approx(1.0)


def test_the_paired_difference_is_paired():
    """Two methods that differ by a constant on every clip: the interval must exclude zero."""
    rng = np.random.default_rng(1)
    clips = rng.uniform(0.05, 0.5, 40)            # each clip's own difficulty, shared by both methods
    first = clips + 0.02
    second = clips
    paired = metrics.paired_difference(first, second)
    assert paired["median"] == pytest.approx(0.02, abs=1e-9)
    assert paired["low"] > 0.0
    assert paired["pairs"] == 40


def test_the_paired_difference_refuses_mismatched_arrays():
    with pytest.raises(ValueError):
        metrics.paired_difference(np.zeros(3), np.zeros(4))
