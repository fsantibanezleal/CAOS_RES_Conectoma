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


def load_head(checkpoint: Path, device: str | None = None):
    from conectoma.stages.train_readout import load

    return load(checkpoint, device)


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


def run(clip: dict, column_spacing_deg: float, *, checkpoint: Path, root: Path, arm: str = "connectome",
        key: str | None = None, tolerance: float = DEFAULT_TOLERANCE, motion: tuple | None = None,
        device: str | None = None) -> dict[str, np.ndarray]:
    """Run M05 on a rendered clip, reading the activity this arm's network produced for it.

    `motion` is accepted and ignored: this row needs no camera motion, which is itself a property worth
    reporting, because it is also why it cannot know that a camera did not move.
    """
    model, record = load_head(Path(checkpoint), device)
    activity = cached_activity(Path(root), arm, key) if key else None
    if activity is None:
        raise FileNotFoundError(
            f"no cached activity for {key} on arm {arm}: run cache-activity for the cases first")
    if len(activity) != len(np.asarray(clip["lum"])):
        raise ValueError(f"cached activity has {len(activity)} frames, the clip has {len(clip['lum'])}")
    return run_on_activity(model, activity, record, tolerance, device)


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
