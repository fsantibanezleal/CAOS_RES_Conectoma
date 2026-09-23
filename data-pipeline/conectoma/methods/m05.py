"""M05: the connectome as a reservoir, with a readout trained on this product's own corpus.

The first row where the measured wiring does the computing. The network is frozen, its activity over a
clip was computed once by `cache-activity`, and the only trained part is the small head of
`conectoma.methods.head`, which every arm of the comparison shares: the connectome and its three nulls
get the same head, the same optimiser and the same seeds, so a difference between them is a difference in
the wiring.

What the row returns is what every other row returns, so the same stage scores it: a planar depth per
column, the columns it refuses, and a boundary mask. It refuses on the uncertainty the head itself
predicts, in log depth, which is a relative uncertainty in depth: the threshold is chosen on the
CALIBRATION split and frozen, never on the cases.

A trained row has one failure mode a geometric row does not: it can answer confidently where nothing is
observable, because nothing in its input tells it the camera did not move. Cases C13 and C14 grade exactly
that, and M05 is not exempted from them.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from conectoma.methods import head as head_module
from conectoma.methods.readout import COLUMNS

DEFAULT_TOLERANCE = 0.5      # the head's predicted spread in log depth, chosen on calibration


_HEADS: dict[tuple, tuple] = {}


def load_head(checkpoint: Path, device: str | None = None):
    """A trained head, loaded once per process: scoring a case reads the same five heads 756 times."""
    from conectoma.stages.train_readout import load

    signature = (str(checkpoint), str(device))
    if signature not in _HEADS:
        _HEADS[signature] = load(checkpoint, device)
    return _HEADS[signature]


def cached_activity(root: Path, arm: str, key: str) -> np.ndarray | None:
    """The activity this arm's network produced for that clip, or None when it was never cached."""
    from conectoma.stages.cache_activity import cache_path

    path = cache_path(root, arm, key)
    if not path.exists():
        return None
    with np.load(path, allow_pickle=True) as cached:
        return np.asarray(cached["activity"], dtype=np.float32)


def run_on_activity(model, activity: np.ndarray, record: dict, tolerance: float = DEFAULT_TOLERANCE,
                    device: str | None = None) -> dict[str, np.ndarray]:
    """Read one clip's cached activity: depth, what is refused, and the boundary mask."""
    device = device or next(model.parameters()).device
    window = record["window"]
    frames = activity.shape[0]
    rows = np.clip(np.arange(frames)[:, None] - np.arange(window - 1, -1, -1), 0, frames - 1)
    batch = torch.from_numpy(activity[rows]).to(device)
    with torch.no_grad():
        prediction = model(batch)
    read = head_module.predictions(prediction)
    # one row per STEP, as every motion row reports, so a comparison pairs frame for frame
    steps = max(frames - 1, 1)
    distance = read["distance_m"][:steps]
    spread = read["uncertainty"][:steps]
    refused = ~np.isfinite(distance) | (distance <= 0) | ~np.isfinite(spread) | (spread > tolerance)
    return {
        "distance_m": np.where(refused, np.nan, distance).astype(np.float32),
        "unknown": refused,
        "moving": np.zeros((steps, COLUMNS), dtype=bool),      # a reservoir row claims no motion mask
        "uncertainty": spread.astype(np.float32),
        "match_uncertainty": spread.astype(np.float32),
        "deviation_deg": np.full((steps, COLUMNS), np.nan, dtype=np.float32),
        "boundary": read["boundary"][:steps],
    }


def seed_checkpoints(arm: str, window: int = 2, derived: Path | None = None) -> list[Path]:
    """Every seed trained for this arm, sorted. A single seed is never the headline."""
    from conectoma.stages.train_readout import DERIVED

    return sorted((derived or DERIVED).glob(f"{arm}-seed*-w{window}.pt"))


def run(clip: dict, column_spacing_deg: float, *, root: Path, arm: str = "connectome",
        key: str | None = None, window: int = 2, tolerance: float = DEFAULT_TOLERANCE,
        checkpoints: list[Path] | None = None, motion: tuple | None = None,
        device: str | None = None) -> dict[str, np.ndarray]:
    """Run M05 on a rendered clip, reading the activity this arm's network produced for it.

    Every seed trained for the arm is read and the answer is their MEDIAN, with the spread across them
    reported: five seeds of the same head on the same cache disagree, and hiding that behind one seed
    would make a comparison between arms unreadable. A column is refused when the seeds' own predicted
    uncertainty exceeds the tolerance, which is chosen on the calibration split.

    `motion` is accepted and ignored: this row needs no camera motion, which is itself worth reporting,
    because it is also why it cannot know that a camera did not move.
    """
    paths = list(checkpoints) if checkpoints else seed_checkpoints(arm, window)
    if not paths:
        raise FileNotFoundError(f"no trained head for arm {arm} at window {window}")
    activity = cached_activity(Path(root), arm, key) if key else None
    if activity is None:
        raise FileNotFoundError(
            f"no cached activity for {key} on arm {arm}: run cache-activity for the cases first")
    if len(activity) != len(np.asarray(clip["lum"])):
        raise ValueError(f"cached activity has {len(activity)} frames, the clip has {len(clip['lum'])}")

    per_seed = []
    for path in paths:
        model, record = load_head(Path(path), device)
        per_seed.append(run_on_activity(model, activity, record, tolerance, device))
    distance = np.stack([one["distance_m"] for one in per_seed])
    spread = np.stack([one["uncertainty"] for one in per_seed])
    with np.errstate(invalid="ignore"):
        median = np.nanmedian(distance, axis=0)
        disagreement = np.nanstd(distance, axis=0) / np.maximum(np.abs(median), 1e-6)
    refused = np.stack([one["unknown"] for one in per_seed]).mean(axis=0) > 0.5
    return {
        "distance_m": np.where(refused, np.nan, median).astype(np.float32),
        # what this row would have answered everywhere, for a comparison at matched coverage: the
        # refusal threshold is the thing such a comparison neutralises, so it cannot be applied first
        "distance_all_m": median.astype(np.float32),
        "unknown": refused | ~np.isfinite(median),
        "moving": np.zeros_like(refused),
        "uncertainty": np.median(spread, axis=0).astype(np.float32),
        "match_uncertainty": np.nan_to_num(disagreement, nan=np.inf).astype(np.float32),
        "deviation_deg": np.full(median.shape, np.nan, dtype=np.float32),
        "boundary": np.stack([one["boundary"] for one in per_seed]).mean(axis=0) > 0.5,
        "seeds": len(per_seed),
    }


def arm_checkpoint(arm: str, seed: int, window: int, derived: Path | None = None) -> Path:
    from conectoma.stages.train_readout import DERIVED

    return (derived or DERIVED) / f"{arm}-seed{seed}-w{window}.pt"


def records(derived: Path | None = None) -> list[dict]:
    """Every training record on disk, so a report can say which heads exist and what they scored."""
    from conectoma.stages.train_readout import DERIVED

    out = []
    for path in sorted((derived or DERIVED).glob("*.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


# ------------------------------------------------------------------ the threshold, chosen on calibration

TOLERANCE_GRID = (0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0)


def calibrate_tolerance(root: Path, arm: str = "connectome", window: int = 2,
                        grid: tuple = TOLERANCE_GRID, clips: int | None = 60,
                        device: str | None = None) -> dict:
    """Choose what the row refuses, on the CALIBRATION split, by asking the head to be honest.

    At each candidate tolerance the claimed columns have an observed root mean square error in log depth.
    A head whose predicted spread means what it says has that error equal to the tolerance it was allowed;
    below it the row is refusing columns it could have read, above it the row is claiming columns it
    cannot. The chosen tolerance is the grid point where the two are closest, which is a calibration
    criterion rather than a knob: no accuracy target is set and no case is touched.
    """
    from conectoma.stages.cache_activity import clip_key, split_clips
    from conectoma.stages.train_readout import CachedClips

    keys = [clip_key(p) for p in split_clips(Path(root), "calibration", clips)]
    cached = CachedClips(Path(root), arm, keys)
    heads = [load_head(path, device) for path in seed_checkpoints(arm, window)]
    if not heads:
        raise FileNotFoundError(f"no trained head for arm {arm} at window {window}")

    errors, spreads = [], []
    for index in range(len(cached)):
        activity = cached.activity[index].astype(np.float32)
        truth = cached.depth[index].astype(np.float32)
        frames = activity.shape[0]
        rows = np.clip(np.arange(frames)[:, None] - np.arange(window - 1, -1, -1), 0, frames - 1)
        batch = torch.from_numpy(activity[rows])
        per_seed_depth, per_seed_spread = [], []
        for model, _ in heads:
            with torch.no_grad():
                read = head_module.predictions(model(batch.to(next(model.parameters()).device)))
            per_seed_depth.append(read["distance_m"])
            per_seed_spread.append(read["uncertainty"])
        depth = np.median(np.stack(per_seed_depth), axis=0)
        spread = np.median(np.stack(per_seed_spread), axis=0)
        known = np.isfinite(truth) & (truth > 0) & np.isfinite(depth) & (depth > 0)
        errors.append(np.log(depth[known]) - np.log(truth[known]))
        spreads.append(spread[known])
    error = np.concatenate(errors)
    spread = np.concatenate(spreads)

    rows = []
    for tolerance in grid:
        claimed = spread <= tolerance
        if claimed.sum() < 100:
            continue
        observed = float(np.sqrt(np.mean(error[claimed] ** 2)))
        rows.append({"tolerance": float(tolerance), "coverage": float(claimed.mean()),
                     "observed_rms_log_error": observed, "gap": abs(observed - float(tolerance))})
    if not rows:
        raise RuntimeError("the calibration split produced no usable column at any tolerance")
    chosen = min(rows, key=lambda row: row["gap"])
    return {"arm": arm, "window": window, "clips": len(cached), "columns": int(len(error)),
            "chosen": chosen, "grid": rows}
