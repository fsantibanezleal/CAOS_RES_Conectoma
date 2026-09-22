"""The metrics every method is scored by, defined once, in the units the corpus records.

Depth metrics are computed over the columns where the ground truth is finite AND the method claimed a
value. Coverage is reported beside them always, because a method that answers one column in twenty can
look excellent and a method that answers everywhere can look poor for the opposite reason. Nothing here
fills in a refusal: a refused column is counted, never guessed.

Definitions, with `d` the ground truth planar depth, `z` the estimate and `N` the number of scored columns:

    AbsRel  = (1/N) sum |d - z| / d
    RMSE    = sqrt((1/N) sum (d - z)^2)                        metres, metric sources only
    delta_k = share with max(d/z, z/d) < 1.25^k,  k = 1, 2, 3
    SILog   = (1/N) sum e_i^2 - (1/N^2) (sum e_i)^2,   e_i = log z_i - log d_i

SILog is the scale-invariant error of Eigen, Puhrsch and Fergus (2014, arXiv:1406.2283), read from section
3.2 of the paper: their equation 3 with the training loss's lambda set to 1, which they state is the
scale-invariant error exactly. It is reported in log units squared. The KITTI leaderboard's percentage
convention is a different presentation of the same quantity and is not used here, because two conventions
under one name is how a number becomes unreadable.

The units gate: RMSE in metres is filled only for a source whose depth is metric. A relative-depth source
(Sintel) is compared after a least-squares scale and shift in inverse depth, `align_inverse_depth`, and the
alignment is named wherever the number appears.

For the cases where depth cannot be observed at all (C13, pure rotation; C14, a static camera) the grade is
not an error at all: it is `refusal`, the share of columns the method declined, and the share it answered
anyway. A method that reports depth everywhere on a pure rotation fails the case whatever its numbers look
like elsewhere.
"""

from __future__ import annotations

import numpy as np

from conectoma.methods import flow_lattice

THRESHOLDS = (1.25, 1.25**2, 1.25**3)


def depth_metrics(truth: np.ndarray, estimate: np.ndarray, claimed: np.ndarray,
                  metric_units: bool = True) -> dict[str, float | int]:
    """Every depth metric over the columns that have a truth and were claimed."""
    truth = np.asarray(truth, dtype=np.float64)
    estimate = np.asarray(estimate, dtype=np.float64)
    known = np.isfinite(truth) & (truth > 0)
    scored = known & np.asarray(claimed, dtype=bool) & np.isfinite(estimate) & (estimate > 0)
    out: dict[str, float | int] = {
        "columns_with_truth": int(known.sum()),
        "columns_scored": int(scored.sum()),
        "coverage": float(scored.sum() / known.sum()) if known.any() else 0.0,
    }
    if not scored.any():
        return out | {"abs_rel": float("nan"), "silog": float("nan"), "delta_1": float("nan"),
                      "delta_2": float("nan"), "delta_3": float("nan"), "rmse_m": float("nan")}
    d, z = truth[scored], estimate[scored]
    ratio = np.maximum(d / z, z / d)
    error = np.log(z) - np.log(d)
    out |= {
        "abs_rel": float(np.mean(np.abs(d - z) / d)),
        "silog": float(np.mean(error**2) - np.mean(error) ** 2),
        "delta_1": float(np.mean(ratio < THRESHOLDS[0])),
        "delta_2": float(np.mean(ratio < THRESHOLDS[1])),
        "delta_3": float(np.mean(ratio < THRESHOLDS[2])),
        "rmse_m": float(np.sqrt(np.mean((d - z) ** 2))) if metric_units else float("nan"),
    }
    return out


def align_inverse_depth(truth: np.ndarray, estimate: np.ndarray, claimed: np.ndarray) -> np.ndarray:
    """A relative-depth estimate scaled and shifted, in inverse depth, to fit the truth (least squares).

    The alignment a relative-depth method needs before any metric means anything. It is a fit to the
    ground truth, so wherever its result is reported the alignment is named with it.
    """
    truth = np.asarray(truth, dtype=np.float64)
    estimate = np.asarray(estimate, dtype=np.float64)
    use = (np.asarray(claimed, dtype=bool) & np.isfinite(truth) & (truth > 0)
           & np.isfinite(estimate) & (estimate > 0))
    if use.sum() < 2:
        return np.full_like(estimate, np.nan)
    x = 1.0 / estimate[use]
    y = 1.0 / truth[use]
    design = np.stack([x, np.ones_like(x)], axis=1)
    scale, shift = np.linalg.lstsq(design, y, rcond=None)[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        aligned = 1.0 / (scale / estimate + shift)
    return np.where(np.isfinite(aligned) & (aligned > 0), aligned, np.nan)


def refusal(unknown: np.ndarray, truth_is_observable: bool) -> dict[str, float]:
    """The grade of an unobservable case: what share the method declined, and what it claimed anyway."""
    unknown = np.asarray(unknown, dtype=bool)
    refused = float(unknown.mean()) if unknown.size else float("nan")
    return {
        "refused": refused,
        "claimed": 1.0 - refused,
        "correct": refused if not truth_is_observable else 1.0 - refused,
    }


def mask_metrics(truth: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    """Intersection over union and its parts, for figure-ground and for independent motion."""
    truth = np.asarray(truth, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    intersection = int((truth & predicted).sum())
    union = int((truth | predicted).sum())
    return {
        "iou": float(intersection / union) if union else float("nan"),
        "precision": float(intersection / predicted.sum()) if predicted.any() else float("nan"),
        "recall": float(intersection / truth.sum()) if truth.any() else float("nan"),
        "truth_share": float(truth.mean()) if truth.size else float("nan"),
        "predicted_share": float(predicted.mean()) if predicted.size else float("nan"),
    }


def boundary_f(truth: np.ndarray, predicted: np.ndarray, tolerance_steps: int = 1) -> dict[str, float]:
    """Boundary precision, recall and F, matching within `tolerance_steps` of the hexagonal lattice.

    The form is Martin, Fowlkes and Malik's (2004): a predicted boundary counts when a true boundary lies
    within the tolerance, and a true boundary counts when a predicted one does. The tolerance is one
    lattice step, not a number of pixels, because on this lattice a pixel tolerance means nothing; it is
    stated wherever the number appears.
    """
    truth = np.asarray(truth, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    near_truth = _dilate(truth, tolerance_steps)
    near_predicted = _dilate(predicted, tolerance_steps)
    precision = float((predicted & near_truth).sum() / predicted.sum()) if predicted.any() else float("nan")
    recall = float((truth & near_predicted).sum() / truth.sum()) if truth.any() else float("nan")
    if not np.isfinite(precision) or not np.isfinite(recall) or (precision + recall) == 0:
        score = float("nan")
    else:
        score = 2 * precision * recall / (precision + recall)
    return {"boundary_precision": precision, "boundary_recall": recall, "boundary_f": score}


def _dilate(mask: np.ndarray, steps: int) -> np.ndarray:
    """A mask grown by `steps` hexagonal neighbours, along the last axis (the columns)."""
    index = flow_lattice.neighbours()
    out = np.asarray(mask, dtype=bool).copy()
    for _ in range(max(steps, 0)):
        padded = np.concatenate([out, np.zeros(out.shape[:-1] + (1,), dtype=bool)], axis=-1)
        grown = padded[..., index]                       # (..., columns, 6), -1 picks the padded False
        out = out | grown.any(axis=-1)
    return out


def paired_difference(first: np.ndarray, second: np.ndarray, resamples: int = 10000,
                      seed: int = 20260922) -> dict[str, float | int]:
    """The difference between two methods, computed per clip and resampled over clips.

    Paired, because the methods saw the same clips: pooling two unpaired distributions and comparing their
    intervals answers a different question and can invert the sign of the one being asked.
    """
    first = np.asarray(first, dtype=np.float64)
    second = np.asarray(second, dtype=np.float64)
    if first.shape != second.shape:
        raise ValueError(f"paired arrays must match: {first.shape} against {second.shape}")
    paired = first - second
    usable = np.isfinite(paired)
    if usable.sum() < 2:
        return {"median": float("nan"), "low": float("nan"), "high": float("nan"),
                "pairs": int(usable.sum())}
    values = paired[usable]
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(values), size=(resamples, len(values)))
    medians = np.median(values[draws], axis=1)
    return {
        "median": float(np.median(values)),
        "low": float(np.percentile(medians, 2.5)),
        "high": float(np.percentile(medians, 97.5)),
        "pairs": int(len(values)),
        "resamples": int(resamples),
        "seed": int(seed),
    }
