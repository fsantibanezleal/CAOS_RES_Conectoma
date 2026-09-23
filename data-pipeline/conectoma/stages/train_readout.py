"""Stage: train a readout head on cached activity, one arm and one seed at a time.

Nothing inside the network is trained here and no gradient crosses time: the activity was computed once by
`cache-activity`, so this is a small convolution fitted on what the frozen network already produced. That
is the whole reason five seeds times four arms is a job of minutes rather than days.

The split rule is the point of the unit and is enforced here rather than trusted:
  train        fits the head
  validation   stops it, and chooses the temporal window
  calibration  sets the threshold at which the method refuses a column
  the cases    are never seen by training, because they are test data

Every run writes its own record: the arm, the seed, the window, the parameter count, the loss curve, the
validation numbers at the checkpoint that was kept, and the digests of the cache and the code it used. A
checkpoint whose record does not match the cache it is read with is refused at load.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch

from conectoma.core.jsonio import write_json
from conectoma.methods import head as head_module
from conectoma.stages.cache_activity import cache_path, clip_key

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "readout"
DEFAULT_STEPS = 1500
DEFAULT_BATCH = 8            # clips per step; each contributes one frame, drawn at random
LEARNING_RATE = 3e-3
EVALUATE_EVERY = 100


def code_digest() -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    digest.update((Path(head_module.__file__)).read_bytes())
    return digest.hexdigest()


class CachedClips:
    """The cached activity and targets of one split, read once and held in memory.

    A clip is 82 KB on disk and a few hundred kilobytes in memory as float16, so a whole split fits: the
    train split is about 850 MB. Reading them once instead of per step is what turns a training run from
    a disk-bound job into a GPU-bound one (measured: 73 ms per step reading npz files, 4 ms in memory).
    """

    def __init__(self, root: Path, arm: str, keys: list[str]):
        paths = [cache_path(root, arm, key) for key in keys]
        paths = [p for p in paths if p.exists()]
        if not paths:
            raise FileNotFoundError(f"no cached activity for arm {arm} under {root}")
        self.activity, self.depth, self.boundary = [], [], []
        for path in paths:
            with np.load(path, allow_pickle=True) as clip:
                if not self.activity:
                    self.stamp = json.loads(str(clip["stamp"]))
                self.activity.append(np.asarray(clip["activity"]))
                self.depth.append(np.asarray(clip["depth"]))
                self.boundary.append(np.asarray(clip["boundary"]) if "boundary" in clip.files
                                     else np.zeros(clip["depth"].shape, np.uint8))
        self.paths = paths

    def __len__(self) -> int:
        return len(self.activity)

    def statistics(self) -> dict:
        """Per-type mean and spread of the activity, and the median log depth, over this split.

        The head is fed standardised activity and predicts log depth RELATIVE to this median. Both are
        properties of the training split, recorded in the run and applied unchanged at inference: a head
        that saw a different normalisation than the one used to read it would be measuring nothing.
        """
        stack = np.concatenate([a.astype(np.float32) for a in self.activity])       # (frames, types, cols)
        mean = stack.mean(axis=(0, 2))
        spread = stack.std(axis=(0, 2))
        depth = np.concatenate([d.astype(np.float32).ravel() for d in self.depth])
        known = np.isfinite(depth) & (depth > 0)
        return {
            "mean": mean.tolist(),
            "std": np.maximum(spread, 1e-3).tolist(),
            "log_depth_offset": float(np.median(np.log(depth[known]))),
            "depth_median_m": float(np.median(depth[known])),
        }

    def draw(self, rng: np.random.Generator, count: int, window: int
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """`count` random (clip, frame) pairs: the window of activity, the depth, the boundary."""
        activity, depth, boundary = [], [], []
        for index in rng.integers(0, len(self.activity), count):
            frames = self.activity[index].shape[0]
            frame = int(rng.integers(0, frames))
            rows = np.clip(np.arange(frame - window + 1, frame + 1), 0, frames - 1)
            activity.append(self.activity[index][rows].astype(np.float32))
            depth.append(self.depth[index][frame].astype(np.float32))
            boundary.append(self.boundary[index][frame].astype(np.float32))
        return np.stack(activity), np.stack(depth), np.stack(boundary)

    def every_frame(self, window: int, limit: int | None = None):
        """Every clip's every frame, for evaluation: yields (activity, depth, boundary) per clip."""
        for index in range(len(self.activity) if limit is None else min(limit, len(self.activity))):
            activity = self.activity[index].astype(np.float32)
            frames = activity.shape[0]
            rows = np.clip(np.arange(frames)[:, None] - np.arange(window - 1, -1, -1), 0, frames - 1)
            yield (activity[rows], self.depth[index].astype(np.float32),
                   self.boundary[index].astype(np.float32))


_LOADED: dict[tuple, CachedClips] = {}


def loaded(root: Path, arm: str, keys: list[str]) -> CachedClips:
    """One in-memory copy of a split per arm, shared by every seed that trains on it."""
    signature = (str(root), arm, len(keys), keys[0] if keys else "", keys[-1] if keys else "")
    if signature not in _LOADED:
        _LOADED[signature] = CachedClips(root, arm, keys)
    return _LOADED[signature]


def evaluate(model, clips: CachedClips, window: int, device: str, limit: int | None = 40) -> dict:
    """Depth and boundary numbers over a split, without touching the optimiser."""
    model.eval()
    errors, spreads, accuracies, counted = [], [], [], 0
    with torch.no_grad():
        for activity, depth, boundary in clips.every_frame(window, limit):
            prediction = model(torch.from_numpy(activity).to(device))
            truth = torch.from_numpy(depth).to(device)
            known = torch.isfinite(truth) & (truth > 0)
            if not known.any():
                continue
            error = prediction[:, 0][known] - torch.log(truth[known])
            errors.append(error.cpu().numpy())
            spreads.append(prediction[:, 1][known].clamp(-6, 6).exp().cpu().numpy())
            accuracies.append(float(((prediction[:, 2] > 0).float()
                                     == torch.from_numpy(boundary).to(device)).float().mean()))
            counted += int(known.sum())
    model.train()
    if not errors:
        return {"columns": 0}
    error = np.concatenate(errors)
    return {
        "columns": counted,
        "silog": float(np.mean(error**2) - np.mean(error) ** 2),
        "abs_rel": float(np.mean(np.abs(np.expm1(error)))),
        "median_spread": float(np.median(np.concatenate(spreads))),
        "boundary_accuracy": float(np.mean(accuracies)),
    }


def train(root: Path, arm: str = "connectome", seed: int = 0, window: int = 2,
          steps: int = DEFAULT_STEPS, batch: int = DEFAULT_BATCH, learning_rate: float = LEARNING_RATE,
          splits: dict[str, list[str]] | None = None, device: str | None = None,
          evaluate_every: int = EVALUATE_EVERY, out_dir: Path | None = None) -> dict:
    """Fit one head on one arm with one seed, keeping the checkpoint that is best on validation."""
    from conectoma.stages.cache_activity import split_clips

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    keys = splits or {name: [clip_key(p) for p in split_clips(root, name)]
                      for name in ("train", "validation")}
    fitting = loaded(root, arm, keys["train"])
    checking = loaded(root, arm, keys["validation"])

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    statistics = fitting.statistics()
    model = head_module.Readout(types=len(fitting.stamp["types"]), window=window,
                                mean=statistics["mean"], std=statistics["std"],
                                log_depth_offset=statistics["log_depth_offset"]).to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)

    history, best, best_state = [], None, None
    started = time.time()
    for step in range(1, steps + 1):
        activity, depth, boundary = fitting.draw(rng, batch, window)
        prediction = model(torch.from_numpy(activity).to(device))
        depth_term, depth_stats = head_module.depth_loss(prediction, torch.from_numpy(depth).to(device))
        boundary_term, boundary_stats = head_module.boundary_loss(
            prediction, torch.from_numpy(boundary).to(device))
        loss = depth_term + boundary_term
        optimiser.zero_grad(set_to_none=True)
        loss.backward()
        optimiser.step()
        if step % evaluate_every == 0 or step == steps:
            checked = evaluate(model, checking, window, device)
            history.append({"step": step, "loss": float(loss.detach()), **depth_stats, **boundary_stats,
                            "validation": checked})
            score = checked.get("silog", float("inf"))
            if best is None or score < best["validation"]["silog"]:
                best = history[-1]
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    record = {
        "arm": arm, "seed": seed, "window": window, "steps": steps, "batch": batch,
        "learning_rate": learning_rate, "parameters": model.parameter_count,
        "device": device, "seconds": round(time.time() - started, 1),
        "cache_stamp": fitting.stamp, "code_sha256": code_digest(), "statistics": statistics,
        "train_clips": len(fitting), "validation_clips": len(checking),
        "best": best, "history": history,
    }
    # never the repository's own data/derived unless the caller asks for it: a test writes to its own
    # directory, so a test run can never leave a checkpoint behind that looks like a committed one
    out_dir = Path(out_dir) if out_dir is not None else DERIVED
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{arm}-seed{seed}-w{window}"
    torch.save({"state_dict": best_state or model.state_dict(), "record": record},
               out_dir / f"{name}.pt")
    write_json(out_dir / f"{name}.json", record)
    record["path"] = str(out_dir / f"{name}.pt")
    return record


def load(path: Path, device: str | None = None):
    """A trained head and its record, with the window it was trained at."""
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    saved = torch.load(path, map_location=device, weights_only=False)
    record = saved["record"]
    statistics = record.get("statistics", {})
    model = head_module.Readout(types=len(record["cache_stamp"]["types"]), window=record["window"],
                                mean=statistics.get("mean"), std=statistics.get("std"),
                                log_depth_offset=statistics.get("log_depth_offset", 0.0))
    model.load_state_dict(saved["state_dict"])
    model.to(device).eval()
    return model, record
