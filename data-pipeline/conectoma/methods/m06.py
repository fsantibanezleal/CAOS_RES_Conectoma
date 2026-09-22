"""M06: the measured connectome in the biophysical regime, trained on this product's own corpus.

M05 asked what the wiring computes with nothing inside it allowed to move. This row asks what it computes
when the quantities the published connectome-constrained model trains are allowed to move: a resting
potential and a time constant per cell type, and a synaptic strength per connected type pair. That is
8,409 parameters against R0's zero, and it is regime R1 of `conectoma.network.regimes`. The wiring, the
signs and the synapse counts are the measured ones in both rows and are never trained.

Everything downstream of the network is M05's, unchanged and shared: the same head, the same window, the
same refusal rule on the head's own predicted spread in log depth, the same threshold chosen on the
CALIBRATION split and frozen, the same median over five seeds with their disagreement reported. What
differs between the two rows is exactly what training was allowed to change inside the network, which is
the only way the comparison means anything.

One structural difference follows from that. A reservoir's activity belongs to the ARM, so U6 cached it
once per arm and every seed read the same cache. A trained network's activity belongs to the SEED: each
seed trained its own network, so each has its own cache, written under `R1-<arm>-seed<n>` by
`run.py cache-trained`. A seed whose cache is missing is named in the report rather than silently
averaged away.

The nulls are the same three graphs U6 used, built with the same construction seed, and each is trained
exactly as the connectome arm is. A claim about the wiring is the paired difference against them and
never an absolute number.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from conectoma.methods import head as head_module
from conectoma.methods.m05 import DEFAULT_TOLERANCE, run_on_activity

REGIME = "R1"


_HEADS: dict[tuple, tuple] = {}


def load_head(checkpoint: Path, device: str | None = None):
    """The head of a trained checkpoint, without rebuilding its network.

    Scoring reads the same five heads 756 times, and the network that produced the activity is not needed
    to read the activity back: it already ran, into the cache this row reads. Building it here would cost
    twenty seconds per seed for nothing.
    """
    signature = (str(checkpoint), str(device))
    if signature in _HEADS:
        return _HEADS[signature]
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    saved = torch.load(Path(checkpoint), map_location=device, weights_only=False)
    record = saved["record"]
    statistics = record.get("statistics", {})
    model = head_module.Readout(types=len(record["types"]), window=record["window"],
                                mean=statistics.get("mean"), std=statistics.get("std"),
                                log_depth_offset=statistics.get("log_depth_offset", 0.0))
    model.load_state_dict(saved["head"])
    model.to(device).eval()
    _HEADS[signature] = (model, record)
    return _HEADS[signature]


def seed_checkpoints(arm: str, window: int = 2, regime: str = REGIME,
                     derived: Path | None = None) -> list[Path]:
    """Every seed trained for this arm in this regime, sorted. A single seed is never the headline."""
    from conectoma.stages.train_network import DERIVED

    return sorted((derived or DERIVED).glob(f"{regime}-{arm}-seed*-w{window}.pt"))


def cached_activity(root: Path, regime: str, arm: str, seed: int, key: str) -> np.ndarray | None:
    """What THIS SEED's trained network produced for that clip, or None when it was never cached."""
    from conectoma.stages.cache_activity import cache_path
    from conectoma.stages.train_network import cache_arm

    path = cache_path(Path(root), cache_arm(regime, arm, seed), key)
    if not path.exists():
        return None
    with np.load(path, allow_pickle=True) as cached:
        return np.asarray(cached["activity"], dtype=np.float32)


def run(clip: dict, column_spacing_deg: float, *, root: Path, arm: str = "connectome",
        key: str | None = None, window: int = 2, regime: str = REGIME,
        tolerance: float = DEFAULT_TOLERANCE, checkpoints: list[Path] | None = None,
        motion: tuple | None = None, device: str | None = None) -> dict[str, np.ndarray]:
    """Run M06 on a rendered clip: each seed's own trained network, read by its own head.

    `motion` is accepted and ignored, as in M05 and for the same reason: this row is never told that the
    camera moved, which is also why it cannot know that it did not (cases C13 and C14).
    """
    paths = list(checkpoints) if checkpoints else seed_checkpoints(arm, window, regime)
    if not paths:
        raise FileNotFoundError(f"no trained {regime} network for arm {arm} at window {window}")
    if key is None:
        raise ValueError("M06 reads a cached activity and needs the clip's cache key")

    per_seed, missing = [], []
    for path in paths:
        model, record = load_head(Path(path), device)
        activity = cached_activity(Path(root), regime, arm, record["seed"], key)
        if activity is None:
            missing.append(record["seed"])
            continue
        if len(activity) != len(np.asarray(clip["lum"])):
            raise ValueError(
                f"the cached activity of seed {record['seed']} has {len(activity)} frames, "
                f"the clip has {len(clip['lum'])}")
        per_seed.append(run_on_activity(model, activity, record, tolerance, device))
    if not per_seed:
        raise FileNotFoundError(
            f"no cached activity for {key} on {regime}-{arm} (seeds {missing}): run cache-trained")

    distance = np.stack([one["distance_m"] for one in per_seed])
    spread = np.stack([one["uncertainty"] for one in per_seed])
    with np.errstate(invalid="ignore"):
        median = np.nanmedian(distance, axis=0)
        disagreement = np.nanstd(distance, axis=0) / np.maximum(np.abs(median), 1e-6)
    refused = np.stack([one["unknown"] for one in per_seed]).mean(axis=0) > 0.5
    return {
        "distance_m": np.where(refused, np.nan, median).astype(np.float32),
        "unknown": refused | ~np.isfinite(median),
        "moving": np.zeros_like(refused),
        "uncertainty": np.median(spread, axis=0).astype(np.float32),
        "match_uncertainty": np.nan_to_num(disagreement, nan=np.inf).astype(np.float32),
        "deviation_deg": np.full(median.shape, np.nan, dtype=np.float32),
        "boundary": np.stack([one["boundary"] for one in per_seed]).mean(axis=0) > 0.5,
        "seeds": len(per_seed),
    }


def records(arm: str | None = None, regime: str = REGIME, derived: Path | None = None) -> list[dict]:
    """Every training record of this regime on disk, so a report can say which networks exist."""
    from conectoma.stages.train_network import DERIVED

    pattern = f"{regime}-{arm or '*'}-seed*-w*.json"
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((derived or DERIVED).glob(pattern))]


# ------------------------------------------------------------------ the threshold, chosen on calibration

TOLERANCE_GRID = (0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0)


def calibrate_tolerance(root: Path, arm: str = "connectome", window: int = 2,
                        regime: str = REGIME, grid: tuple = TOLERANCE_GRID,
                        clips: int | None = 60, device: str | None = None,
                        derived: Path | None = None) -> dict:
    """Choose what this row refuses, on the CALIBRATION split, by the criterion M05 uses.

    A head whose predicted spread means what it says has, among the columns it claims at a tolerance, an
    observed root mean square error in log depth equal to that tolerance. The chosen grid point is the one
    where the two are closest. No accuracy target is set and no case clip is read, here or anywhere else
    in this row's calibration.
    """
    from conectoma.stages.cache_activity import clip_key, split_clips

    keys = [clip_key(p) for p in split_clips(Path(root), "calibration", clips)]
    paths = seed_checkpoints(arm, window, regime, derived)
    if not paths:
        raise FileNotFoundError(f"no trained {regime} network for arm {arm} at window {window}")

    errors, spreads = [], []
    for key in keys:
        per_seed_depth, per_seed_spread, truth = [], [], None
        for path in paths:
            model, record = load_head(Path(path), device)
            activity = cached_activity(Path(root), regime, arm, record["seed"], key)
            if activity is None:
                continue
            if truth is None:
                from conectoma.stages.cache_activity import cache_path
                from conectoma.stages.train_network import cache_arm

                with np.load(cache_path(Path(root), cache_arm(regime, arm, record["seed"]), key),
                             allow_pickle=True) as cached:
                    truth = np.asarray(cached["depth"], dtype=np.float32)
            frames = activity.shape[0]
            rows = np.clip(np.arange(frames)[:, None] - np.arange(window - 1, -1, -1), 0, frames - 1)
            batch = torch.from_numpy(activity[rows]).to(next(model.parameters()).device)
            with torch.no_grad():
                read = head_module.predictions(model(batch))
            per_seed_depth.append(read["distance_m"])
            per_seed_spread.append(read["uncertainty"])
        if not per_seed_depth or truth is None:
            continue
        depth = np.median(np.stack(per_seed_depth), axis=0)
        spread = np.median(np.stack(per_seed_spread), axis=0)
        known = np.isfinite(truth) & (truth > 0) & np.isfinite(depth) & (depth > 0)
        errors.append(np.log(depth[known]) - np.log(truth[known]))
        spreads.append(spread[known])
    if not errors:
        raise FileNotFoundError(
            f"no cached calibration activity for {regime}-{arm}: run cache-trained on the split")
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
    return {"arm": arm, "regime": regime, "window": window, "clips": len(errors),
            "seeds": len(paths), "columns": int(len(error)), "chosen": chosen, "grid": rows}
