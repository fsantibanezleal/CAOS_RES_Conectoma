"""Flow on the hexagonal lattice: what it recovers, and what it refuses to answer.

A synthetic pattern is moved by a known displacement and rendered through the same eye the corpus uses, so
the estimator is tested against a displacement that exists rather than against another estimator. The
refusals are tested too: an edge (the aperture problem) and a flat field must return no velocity, because a
method that answers everywhere is what cases C07 and C16 are built to catch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import flow_lattice, readout  # noqa: E402
from conectoma.vision import eye  # noqa: E402

SIZE = 436


def texture(rng: np.random.Generator, waves: int = 40):
    """One fixed band-limited texture, sampled wherever it is asked for.

    The lattice takes one value per 13 x 13 box, so a texture that varies faster than that is aliased
    before any estimator sees it. The frequencies here give structures of 70 pixels and more, several
    lattice steps wide, which is the regime a differential estimator is for.
    """
    frequencies = rng.uniform(-0.014, 0.014, (waves, 2))
    phases = rng.uniform(0, 2 * np.pi, waves)

    def sample(shift: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
        y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
        frame = np.zeros((SIZE, SIZE))
        for (fx, fy), phase in zip(frequencies, phases, strict=True):
            frame += np.cos(2 * np.pi * (fx * (x - shift[0]) + fy * (y - shift[1])) + phase)
        return (frame - frame.min()) / (frame.max() - frame.min())

    return sample


def lattice(frames: np.ndarray) -> np.ndarray:
    return eye.box_mean(frames)


def test_a_known_translation_is_recovered_on_a_textured_field():
    """Within a third of a pixel, and with no systematic scaling of the displacement.

    The second assertion is the one that matters. A single linear solve returns a velocity 12 to 24 percent
    too large here, because the gradient measured over a 13-pixel lattice step under-reads the slope, and a
    scale error in the flow is a scale error in every distance the readout computes from it.
    """
    sample = texture(np.random.default_rng(11))
    for shift in [(1.0, 0.0), (0.0, -1.5), (0.8, 0.6), (4.0, -3.0)]:
        pair = np.stack([sample(), sample(shift)])
        out = flow_lattice.flow(lattice(pair))
        strong = out["confidence"][0] > np.percentile(out["confidence"][0], 60)
        estimate = np.nanmedian(out["velocity_px"][0][:, strong], axis=1)
        assert np.allclose(estimate, shift, atol=0.3), (shift, estimate)
        scale = np.linalg.norm(estimate) / np.linalg.norm(shift)
        # measured on this texture: a displacement of one and a half pixels or more comes back within
        # 5 percent; a displacement of one pixel, 8 percent of a lattice step, within 20 percent. The
        # single linear solve this replaced was 12 to 24 percent too LARGE, in the direction of motion,
        # whatever the displacement, which is the error that would have scaled every distance.
        assert 0.8 < scale < 1.05, (shift, scale)
        if np.linalg.norm(shift) >= 1.5:
            assert 0.95 < scale < 1.05, (shift, scale)


def test_an_edge_is_refused_and_a_texture_is_not():
    """The aperture problem, measured: along an edge the smaller eigenvalue collapses."""
    sample = texture(np.random.default_rng(3))
    edge = np.zeros((SIZE, SIZE))
    edge[:, SIZE // 2:] = 1.0
    edge_pair = np.stack([edge, np.roll(edge, 1, axis=1)])
    texture_pair = np.stack([sample(), sample((1.0, 0.0))])

    edge_confidence = flow_lattice.flow(lattice(edge_pair))["confidence"][0]
    texture_confidence = flow_lattice.flow(lattice(texture_pair))["confidence"][0]
    assert np.median(edge_confidence) < 1e-6
    assert np.median(texture_confidence) > 100 * max(np.median(edge_confidence), 1e-12)


def test_a_flat_field_claims_no_velocity_anywhere():
    flat = np.full((2, SIZE, SIZE), 0.42)
    out = flow_lattice.flow(lattice(flat))
    assert np.allclose(out["confidence"], 0.0)
    assert np.isnan(out["velocity_px"]).all()


def test_interpolation_returns_a_column_its_own_value():
    """The engine truncates each column centre to a whole pixel, so the ideal grid is not where the
    columns are; interpolating on it would not even reproduce a column's own value."""
    rng = np.random.default_rng(5)
    values = rng.normal(size=readout.COLUMNS)
    pixels = readout.column_pixels()
    got = flow_lattice.sample(values, flow_lattice.lattice_uv(pixels))
    assert np.allclose(got, values, atol=1e-12)


def test_interpolation_is_nan_outside_the_lattice():
    values = np.ones(readout.COLUMNS)
    far = np.array([[0.0, 1e4], [1e4, 0.0]])
    assert np.isnan(flow_lattice.sample(values, flow_lattice.lattice_uv(far))).all()


def test_every_column_has_its_hexagonal_neighbours():
    index = flow_lattice.neighbours()
    assert index.shape == (readout.COLUMNS, 6)
    counts = (index >= 0).sum(axis=1)
    # the lattice is an extent-15 hexagon: the interior has six neighbours, the rim fewer, and nothing
    # outside the lattice is ever referenced
    assert counts.max() == 6
    assert counts.min() >= 3
    assert (counts == 6).sum() == readout.COLUMNS - 6 * 15
    assert index.max() < readout.COLUMNS


def test_the_neighbour_map_is_symmetric():
    index = flow_lattice.neighbours()
    for column, row in enumerate(index):
        for k, neighbour in enumerate(row):
            if neighbour >= 0:
                back = k + 1 if k % 2 == 0 else k - 1        # the steps are listed in opposite pairs
                assert index[neighbour, back] == column
