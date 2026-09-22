"""The Hassenstein-Reichardt correlator on the eye's own lattice.

Hassenstein and Reichardt (1956, Z. Naturforsch. B 11:513-524) inferred this detector from the beetle's
optomotor turning, and it remains the model of the fly's elementary motion detector (Borst, Haag and Reiff,
2010, Annu. Rev. Neurosci. 33:49-70). Between two neighbouring columns `a` and `b`:

    h_x(t) = low-pass of the column's signal, first order, time constant tau
    EMD_ab = L_a(t) h_b(t) - L_b(t) h_a(t)

Each arm multiplies one column's undelayed signal by its neighbour's delayed one, and the two
mirror-symmetric arms are subtracted, which is what makes the output signed and direction-selective. The
input is the luminance with its own mean removed per column, as the fly's input stage is high-pass.

The lattice gives each column three neighbour axes, so each column carries three opponent responses, and a
two-dimensional motion vector follows by least squares over the three axis directions. Those directions
are not sixty degrees apart in pixels: the engine's lattice is stretched along the row axis (neighbours 13
pixels apart vertically, (13, 6.5) diagonally), so they sit at 27, 90 and 153 degrees. The fit uses the
directions as they are.

**A correlator does not measure velocity.** Its response depends on the temporal frequency the pattern
presents, so the same speed over a finer texture gives a different answer: the classic result, and the
reason this module returns a RESPONSE rather than a speed. `conectoma.methods.m03` calibrates it, on
synthetic scenes whose speed is known, before anything is called a distance. The test
`test_methods_emd.py` measures that dependence rather than asserting it away.
"""

from __future__ import annotations

import numpy as np

from conectoma.methods import flow_lattice, readout

# the three neighbour axes of the lattice, as index pairs into NEIGHBOUR_STEPS
AXES = ((0, 1), (2, 3), (4, 5))


def axis_directions(column_spacing_deg: float | None = None) -> np.ndarray:
    """(3, 2) the pixel direction of each neighbour axis, unit length."""
    pixels = readout.column_pixels()
    index = flow_lattice.neighbours()
    out = []
    for forward, _ in AXES:
        deltas = []
        for column, row in enumerate(index):
            if row[forward] >= 0:
                deltas.append(pixels[row[forward]] - pixels[column])
        mean = np.mean(deltas, axis=0)
        out.append(mean / np.linalg.norm(mean))
    return np.array(out)


def low_pass(signal: np.ndarray, tau_s: float, interval_s: float) -> np.ndarray:
    """A first-order low-pass along the frame axis, exactly as a discrete exponential filter.

    `y[t] = y[t-1] + (1 - exp(-dt / tau)) (x[t] - y[t-1])`, started at the first sample so the filter has
    no transient of its own to be mistaken for motion.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if tau_s <= 0:
        return signal.copy()
    alpha = 1.0 - np.exp(-interval_s / tau_s)
    out = np.empty_like(signal)
    out[0] = signal[0]
    for t in range(1, len(signal)):
        out[t] = out[t - 1] + alpha * (signal[t] - out[t - 1])
    return out


def responses(lum: np.ndarray, tau_s: float, interval_s: float) -> np.ndarray:
    """(steps, 3, columns) the opponent response of each column on each of the three lattice axes.

    A step's response is the correlator's output at the later of the two frames, so the array lines up with
    the flow arrays of the corpus: one row per consecutive pair of frames.
    """
    lum = np.asarray(lum, dtype=np.float64)
    if lum.ndim != 2 or lum.shape[1] != readout.COLUMNS:
        raise ValueError(f"expected (frames, {readout.COLUMNS}) luminances, got {lum.shape}")
    high = lum - lum.mean(axis=0, keepdims=True)        # the input stage is high-pass
    delayed = low_pass(high, tau_s, interval_s)
    index = flow_lattice.neighbours()
    out = np.zeros((len(lum) - 1, len(AXES), lum.shape[1]))
    for axis, (forward, backward) in enumerate(AXES):
        ahead, behind = index[:, forward], index[:, backward]
        have = (ahead >= 0) & (behind >= 0)
        a = high[1:, :]
        b = _take(high[1:, :], ahead)
        delayed_a = delayed[1:, :]
        delayed_b = _take(delayed[1:, :], ahead)
        out[:, axis, :] = np.where(have[None, :], a * delayed_b - b * delayed_a, 0.0)
    return out


def _take(values: np.ndarray, index: np.ndarray) -> np.ndarray:
    safe = np.where(index >= 0, index, 0)
    return np.where(index >= 0, values[..., safe], 0.0)


def motion_vectors(response: np.ndarray, column_spacing_deg: float | None = None) -> np.ndarray:
    """(steps, 2, columns) the two-dimensional response, least squares over the three axes.

    The three axes over-determine a plane vector, so the fit both combines them and says, through its
    residual, whether they agree. The result is in the correlator's own units, NOT pixels per frame.
    """
    directions = axis_directions(column_spacing_deg)                    # (3, 2)
    solve = np.linalg.pinv(directions)                                  # (2, 3)
    return np.einsum("ij,sjc->sic", solve, np.asarray(response, dtype=np.float64))


def pool(vectors: np.ndarray, rings: int) -> np.ndarray:
    """(steps, 2, columns) the response averaged over `rings` rounds of hexagonal neighbours.

    A single column's correlator cannot be read as a displacement: fitting one gain from the response to
    the true displacement on a synthetic scene explains LESS than the mean does (r2 = -0.14, measured).
    Averaging over neighbours turns it into something a gain does fit: r2 = 0.33 after one ring, 0.50
    after two and 0.60 after three, on the same scene. That is what the fly's wide-field cells do with the
    outputs of its elementary detectors, and it costs exactly what it sounds like: the depth that follows
    is smoothed over the pooled neighbourhood, which is reported with it.
    """
    members, _, _ = flow_lattice.patches()
    out = np.asarray(vectors, dtype=np.float64)
    for _ in range(max(rings, 0)):
        out = np.stack([out[:, axis][:, members].mean(axis=-1) for axis in (0, 1)], axis=1)
    return out


def residual(response: np.ndarray, vectors: np.ndarray,
             column_spacing_deg: float | None = None) -> np.ndarray:
    """(steps, columns) how far the three axes are from agreeing on one vector, in response units."""
    directions = axis_directions(column_spacing_deg)                    # (3, 2)
    predicted = np.einsum("ji,sic->sjc", directions, np.asarray(vectors, dtype=np.float64))
    return np.linalg.norm(np.asarray(response, dtype=np.float64) - predicted, axis=1)
