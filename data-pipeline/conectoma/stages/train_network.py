"""Stage: train the network itself, in the biophysical regime, with the head M05 already reads.

U6 asked what the measured wiring computes when nothing inside it may change. This unit asks the next
question: what it computes when the quantities the published connectome-constrained model trains are
allowed to move. That is regime R1 of `conectoma.network.regimes` and nothing else: the wiring, the signs
and the synapse counts stay exactly as measured, and 8,409 parameters (a resting potential and a time
constant per cell type, a synaptic strength per connected type pair) are fitted together with the readout.

Why this stage exists at all, rather than another call into `train_readout`: in R0 the activity of a clip
depends only on the clip, so it was computed once and cached, and five seeds times four arms cost minutes.
Here the gradient crosses the network and the whole time axis, so every step simulates clips from scratch.
That is the entire difference in cost between U6 and U7, and it is why this stage is written to be
measured rather than guessed.

What is kept from U6, deliberately unchanged, so that a difference between M05 and M06 is a difference in
what training was allowed to change and not in anything else:

  the head            `conectoma.methods.head.Readout`, same architecture, same window, same loss, and
                      STARTED FROM M05's OWN TRAINED HEAD for the same arm and seed
  the head's optimiser Adam at 3e-3, the value U6 fitted with
  the input statistics whatever that M05 head was trained with, carried in its checkpoint, frozen here:
                      not merely the same recipe as M05's, literally the same numbers
  the splits          train fits, validation stops and chooses, calibration sets the refusal threshold,
                      the cases are never touched
  the arms            the connectome and the same three nulls, built from the same graph seed as U6
  the seeds           five per arm, and no single seed is ever the headline

Why the head is warm-started rather than fitted from scratch. A cold head needs about 1,500 optimiser
steps to converge, and here a step simulates two whole clips instead of reading a cache, so a cold run is
23 minutes per seed and 11 hours for the unit. Measured on the connectome arm with a cold head at the
published rate, validation scale-invariant error was still bouncing between 6.4 and 7.8 at step 150 while
M05's converged heads sit at 3.5. Starting from M05's solution turns the question into the one the unit
actually asks: GIVEN the readout the frozen network supports, what does letting the biophysics move buy?
A regime that buys nothing is then a finding about the regime rather than about a training budget, and the
two rows can be read side by side because one begins where the other ended.

What comes from the engine's own published training, because R1 is the regime of the published model and
its hyperparameters are a primary source (flyvis `config/optim`, `config/scheduler`, `config/penalizer`):

  Adam on the network parameters, stepwise decay from `lr_network` to a tenth of it over ten stages
  the activity penalty on the resting potentials, `flyvis.solver.Penalty`, run exactly where the engine's
  own solver runs it: after the task loss has stepped, with the graph retained
  a steady state from 0.5 s of grey, computed once per batch shape and detached, as `t_pre_train` does

What is NOT taken from it is the learning rate itself. The published run is 250,000 iterations; this one
is hundreds. The rate is therefore chosen on the VALIDATION split from a small grid, per arm, and frozen
for that arm's remaining seeds; it is also RELATIVE to each parameter group's own size rather than
absolute, because Adam's step does not care how large the quantity it moves is and R1's three groups
differ by eighty times (see NETWORK_GRID). The cases are never involved in that choice.

Batch size is 2 where the engine's is 4, and that number is measured, not preferred: on this machine a
32-frame clip at batch 4 peaks at 8.41 GB and spills, falling to 65.9 supervised frames per second, while
batch 2 peaks at 4.36 GB and sustains 108.0. Clips are always simulated whole, from the grey steady state,
so no sub-sequence ever starts mid-motion from a state that never existed.
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
from conectoma.stages.cache_activity import DT_S, cache_path, clip_key, spec_digest, split_clips

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "network"
CHECKPOINT_VERSION = 1

DEFAULT_STEPS = 300
DEFAULT_BATCH = 2            # clips per step, each simulated whole; measured, see the module docstring
HEAD_LEARNING_RATE = 3e-3    # U6's value, for a head that starts cold
# A head that starts from M05's is already converged, and U6's rate does not fine-tune it, it destroys
# it. Measured with the network FROZEN, so that whatever moves is the head's own rate alone, over 100
# steps of validation scale-invariant error (M05's own value is 2.724):
#   3e-3   2.862  3.673  4.090  2.979     it wanders off and does not come back
#   3e-4   2.840  2.899  3.000  2.873     still worse than where it started
#   3e-5   2.728  2.728  2.733  2.730     stable
# The reason is the batch, not the head: U6 fitted on 16 independent frames per step, and a step here is
# 2 whole clips, whose 64 frames are highly correlated. The warm rate is therefore a hundredth of U6's.
HEAD_FINETUNE_RATE = 3e-5
# The network's rate is RELATIVE to each parameter group's own size, not absolute, and that is measured
# rather than preferred. Adam's step is the rate regardless of the gradient, and the three trainable
# groups of R1 differ by eighty times in magnitude:
#
#   nodes_bias          253 values, median 0.502     one 5e-5 step is 0.01% of it
#   nodes_time_const    253 values, median 0.050     one 5e-5 step is 0.10% of it
#   edges_syn_strength  7,903 values, median 0.0063  one 5e-5 step is 0.79% of it
#
# At the published absolute rate, 600 steps can move a synaptic strength by four times its own median
# while a resting potential moves by six percent, and the readout the head was fitted to is gone. Measured
# that way on the connectome arm, validation scale-invariant error went from 2.72 at the start to 4.2 and
# never came back within 600 steps. Each group therefore gets `relative_rate * rms(group)`, so one step is
# the same fraction of every quantity. 1e-4 is the published 5e-5 as the resting potentials see it.
# Measured on the connectome arm over 200 steps, validation scale-invariant error from a start of 2.729:
#   1e-2   9.18 at step 25, still 4.64 at 200         the readout is gone
#   1e-3   4.11, 2.71, 3.89, 2.89 ...                 unstable, best 2.711
#   1e-4   2.94, 2.97, 2.87, 2.667, 2.673, drifting   best 2.667, and the only one that improves
# The grid keeps three points and moves them to where the answer is, rather than keeping a point that is
# known to destroy every arm it is given to.
NETWORK_GRID = (3e-5, 1e-4, 1e-3)
# The engine ties the penalty's rate to the network's (`lr_pen` mirrors `lr_net`), which is safe at the
# published 5e-5 and is not safe here, because this run may train the network a hundred times faster. Tied
# to a network rate of 5e-3 the penalty's plain SGD overshoots its own quadratic and runs away: measured
# over six steps, the resting potentials moved by 0.007, 0.108, 0.386, 2.514 and stopped only against the
# activation's floor, on parameters whose whole range is 0.007 to 0.795. The penalty therefore keeps the
# PUBLISHED rate whatever the network is trained at: it is a slow guard, not a training signal.
PENALTY_LEARNING_RATE = 5e-5
DECAY_STAGES = 10            # the engine's stepwise schedule, start to start/10
T_PRE_S = 0.5                # the engine's `t_pre_train`
INTERVAL_S = 0.1             # the corpus's frame interval, as U4 rendered it
EVALUATE_EVERY = 25
# Clips of the validation split read at each evaluation. 40 was too few to select on: the curve moved by
# more between neighbouring evaluations of the same run than between the runs being compared. 80 clips
# cost about 10 s per evaluation and 2 minutes over a run, which is the right trade at 300 steps.
VALIDATION_CLIPS = 80

# The engine's own activity penalty, with its published weights and asymmetry. Its BASELINE is the one
# number here that cannot be imported: 5.0 is the activity level the published ensemble was trained to
# hold under its own stimuli and its own reconstruction, and this product's network, on this product's
# renderings, starts nowhere near it (measured: the central cells of the transferred network average 0.67
# over a sample of train clips, not 5.0). Left at 5.0 the penalty is not a guard but the dominant
# force: in six steps it moved every resting potential by 11.3, which is training the penalty rather than
# the connectome. The baseline is therefore MEASURED on the starting network of each arm, which keeps what
# the penalty is for, a guard against cells that go dead or run away, and drops what does not transfer.
PENALIZER = {
    "activity_penalty": {
        "activity_baseline": None,          # measured per arm at step zero; see `measured_baseline`
        "activity_penalty": 0.1,
        "stop_iter": 150000,
        "below_baseline_penalty_weight": 1.0,
        "above_baseline_penalty_weight": 0.1,
    },
    "optim": "SGD",
}
BASELINE_CLIPS = 8


def code_digest() -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for path in (Path(head_module.__file__),
                 Path(__file__).parents[1] / "network" / "regimes.py",
                 Path(__file__).parents[1] / "network" / "engine.py"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def checkpoint_path(regime: str, arm: str, seed: int, window: int,
                    out_dir: Path | None = None) -> Path:
    return (out_dir or DERIVED) / f"{regime}-{arm}-seed{seed}-w{window}.pt"


def cache_arm(regime: str, arm: str, seed: int) -> str:
    """The activity cache key of ONE TRAINED network: a trained arm's activity is its own, per seed."""
    return f"{regime}-{arm}-seed{seed}"


# ----------------------------------------------------------------- the corpus, in memory


class ClipSplit:
    """The rendered clips of one split, held in memory as the network's input and its targets.

    A clip is 32 frames by 721 columns; luminance, depth and the boundary mask together are 138 KB as
    float16, so the 1,437 clips of the train split are 199 MB and are read once rather than per step.
    """

    def __init__(self, root: Path, split: str, limit: int | None = None):
        self.paths = split_clips(Path(root), split, limit)
        if not self.paths:
            raise FileNotFoundError(f"no rendered clips for split {split} under {root}")
        self.lum, self.depth, self.boundary = [], [], []
        for path in self.paths:
            with np.load(path, allow_pickle=True) as clip:
                self.lum.append(np.asarray(clip["lum"], dtype=np.float16))
                self.depth.append(np.asarray(clip["depth"], dtype=np.float16))
                self.boundary.append(
                    np.asarray(clip["boundary"], dtype=np.uint8) if "boundary" in clip.files
                    else np.zeros(clip["depth"].shape, np.uint8))
        self.split = split

    def __len__(self) -> int:
        return len(self.lum)

    def batch(self, index: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (np.stack([self.lum[i] for i in index]).astype(np.float32),
                np.stack([self.depth[i] for i in index]).astype(np.float32),
                np.stack([self.boundary[i] for i in index]).astype(np.float32))


_SPLITS: dict[tuple, ClipSplit] = {}


def loaded_split(root: Path, split: str, limit: int | None = None) -> ClipSplit:
    """One in-memory copy of a split per process, shared by every arm and seed that trains on it."""
    signature = (str(root), split, limit)
    if signature not in _SPLITS:
        _SPLITS[signature] = ClipSplit(root, split, limit)
    return _SPLITS[signature]


def start_statistics(root: Path, arm: str, limit: int | None = None) -> dict:
    """The per-type mean and spread of the STARTING network's activity, and the median log depth.

    Read from the R0 cache this arm already carries, streamed rather than loaded: the head's input
    normalisation is a property of where training starts, is identical to the one M05's head was given,
    and is then frozen for the whole run. A head that saw a different normalisation than the one it is
    read with would be measuring nothing, which is why it travels in the checkpoint.
    """
    keys = [clip_key(p) for p in split_clips(Path(root), "train", limit)]
    total = squared = count = None
    depths = []
    for key in keys:
        path = cache_path(Path(root), arm, key)
        if not path.exists():
            continue
        with np.load(path, allow_pickle=True) as cached:
            activity = np.asarray(cached["activity"], dtype=np.float32)      # (frames, types, columns)
            depth = np.asarray(cached["depth"], dtype=np.float32)
        if total is None:
            total = np.zeros(activity.shape[1], dtype=np.float64)
            squared = np.zeros_like(total)
            count = 0
        total += activity.sum(axis=(0, 2))
        squared += (activity.astype(np.float64) ** 2).sum(axis=(0, 2))
        count += activity.shape[0] * activity.shape[2]
        finite = depth[np.isfinite(depth) & (depth > 0)]
        if finite.size:
            depths.append(np.log(finite[:: max(finite.size // 2000, 1)]))
    if total is None:
        raise FileNotFoundError(f"no R0 activity cache for arm {arm} under {root}: run cache-activity")
    mean = total / count
    spread = np.sqrt(np.maximum(squared / count - mean**2, 0.0))
    return {
        "mean": mean.astype(float).tolist(),
        "std": np.maximum(spread, 1e-3).astype(float).tolist(),
        "log_depth_offset": float(np.median(np.concatenate(depths))),
        "clips": len(depths),
        "source": f"the R0 activity cache of arm {arm} over the train split",
    }


_STATISTICS: dict[tuple, dict] = {}


def statistics_of(root: Path, arm: str, limit: int | None = None) -> dict:
    signature = (str(root), arm, limit)
    if signature not in _STATISTICS:
        _STATISTICS[signature] = start_statistics(root, arm, limit)
    return _STATISTICS[signature]


def reservoir_head(arm: str, seed: int, window: int, derived: Path | None = None) -> Path | None:
    """M05's trained head for the same arm and seed, if U6 left one: this run's starting point."""
    from conectoma.stages.train_readout import DERIVED as READOUT

    path = (derived or READOUT) / f"{arm}-seed{seed}-w{window}.pt"
    return path if path.exists() else None


# ----------------------------------------------------------------- the network, in training mode


def build_trainable(arm: str, seed: int = 0, regime: str = "R1", transfer: bool = True):
    """The network of one arm in a TRAINING regime, on the fastest device, in training mode.

    The null graphs are built with the same construction seed U6 used (0), so the arm a trained network
    carries is literally the arm M05 was read on; the training seed is a separate number and never
    touches the graph.
    """
    from conectoma.network.engine import published_model_dir
    from conectoma.network.regimes import REGIMES, build_network
    from conectoma.stages.cache_activity import SPEC, arm_spec

    if not REGIMES[regime].trainable:
        raise ValueError(f"regime {regime} trains nothing; this stage is for R1 and R2")
    spec, description = arm_spec(arm, 0)
    source = SPEC
    scratch = None
    if arm != "connectome":
        scratch = REPO_ROOT / "data" / "derived" / "connectome" / f".train-{arm}.json"
        write_json(scratch, spec)
        source = scratch
    try:
        network = build_network(str(source), regime,
                                transfer_from=published_model_dir("000") if transfer else None)
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)
    if torch.cuda.is_available():
        network = network.cuda()
    network.train()
    return network, spec, description


def output_stack(network, activity: torch.Tensor, types: list[str], repeats: int) -> torch.Tensor:
    """(batch, frames, types, columns): the output units' voltage at the last step of each frame."""
    from flyvis.utils.activity_utils import LayerActivity

    layers = LayerActivity(activity, network.connectome, use_central=False)
    stack = torch.stack([getattr(layers, name) for name in types], dim=2)
    return stack[:, repeats - 1 :: repeats]


def simulate(network, lum: np.ndarray, types: list[str], state, dt_s: float, repeats: int,
             device) -> tuple[torch.Tensor, torch.Tensor]:
    """Run a batch of whole clips through the network: the whole activity, and what the head reads.

    The whole activity is returned because the engine's activity penalty is defined on it, over the
    central cells; the second value is the output units at frame boundaries, which is the head's input.

    `network.simulate` cannot be used here: the engine refuses it unless the network is in evaluation mode
    with no parameter requiring a gradient, which is exactly the opposite of this stage. The call below is
    what `simulate` does inside, minus that guard.
    """
    movie = torch.from_numpy(np.repeat(lum, repeats, axis=1)).to(device)[:, :, None, :]
    network.stimulus.zero(movie.shape[0], movie.shape[1])
    network.stimulus.add_input(movie)
    activity = network(network.stimulus(), dt_s, state=state)
    return activity, output_stack(network, activity, types, repeats)


def steady(network, batch: int, dt_s: float, t_pre_s: float = T_PRE_S):
    """The state after grey input, computed once per batch shape and detached, as the engine's solver does."""
    with torch.no_grad():
        return network.steady_state(t_pre_s, dt_s, batch, value=0.5)


def measured_baseline(network, clips: ClipSplit, types: list[str], dt_s: float, repeats: int, device,
                      sample: int = BASELINE_CLIPS, batch: int = 2) -> float:
    """The activity level the penalty should hold: what the STARTING network already does.

    Computed exactly as `flyvis.solver.Penalty` computes the quantity it penalises, so the two are the
    same number: the temporal mean over the central cells, after the first quarter of the frames, which
    the engine drops as the initial transient.
    """
    central = network.connectome.central_cells_index[:]
    was_training = network.training
    network.eval()
    means = []
    with torch.no_grad():
        for start in range(0, min(sample, len(clips)), batch):
            index = np.arange(start, min(start + batch, min(sample, len(clips))))
            lum, _, _ = clips.batch(index)
            state = steady(network, len(index), dt_s)
            activity, _ = simulate(network, lum, types, state, dt_s, repeats, device)
            frames = activity.shape[1]
            means.append(float(activity[:, frames // 4 :, central].mean()))
    if was_training:
        network.train()
    return float(np.mean(means))


def schedule(start: float, steps: int, stages: int = DECAY_STAGES, floor: float = 0.1) -> np.ndarray:
    """The engine's stepwise decay: `stages` plateaus from `start` down to `floor` times it."""
    values = np.linspace(start, start * floor, stages).repeat(max(steps // stages, 1))
    return np.pad(values, (0, max(steps - len(values) + 1, 0)), constant_values=start * floor)


def parameter_groups(network, relative_rate: float) -> list[dict]:
    """One optimiser group per trainable quantity, at a rate scaled to that quantity's own size.

    See NETWORK_GRID: Adam takes a step of the size of the rate whatever the gradient is, so a single
    absolute rate across groups that differ by eighty times trains one of them and destroys another.
    """
    groups = []
    for name, parameter in network.named_parameters():
        if not parameter.requires_grad:
            continue
        rms = float(parameter.detach().pow(2).mean().sqrt())
        groups.append({"params": [parameter], "lr": relative_rate * max(rms, 1e-8), "name": name,
                       "rms": rms})
    return groups


# ----------------------------------------------------------------- evaluation on a split


def evaluate(network, model, clips: ClipSplit, types: list[str], window: int, dt_s: float,
             repeats: int, device, limit: int = VALIDATION_CLIPS, batch: int = 2) -> dict:
    """Depth and boundary numbers over a split, with no gradient and no optimiser touched."""
    was_training = network.training
    network.eval()
    model.eval()
    errors, spreads, accuracies, counted = [], [], [], 0
    state, held_for = None, -1
    with torch.no_grad():
        for start in range(0, min(limit, len(clips)), batch):
            index = np.arange(start, min(start + batch, min(limit, len(clips))))
            lum, depth, boundary = clips.batch(index)
            if state is None or held_for != len(index):
                state, held_for = steady(network, len(index), dt_s), len(index)
            _, held = simulate(network, lum, types, state, dt_s, repeats, device)
            frames = held.shape[1]
            rows = torch.arange(frames, device=held.device)[:, None] - torch.arange(
                window - 1, -1, -1, device=held.device)
            windowed = held[:, rows.clamp(min=0)]                       # (batch, frames, window, ...)
            flat = windowed.reshape(-1, window, len(types), windowed.shape[-1])
            prediction = model(flat)
            truth = torch.from_numpy(depth.reshape(-1, depth.shape[-1])).to(device)
            known = torch.isfinite(truth) & (truth > 0)
            if not known.any():
                continue
            error = prediction[:, 0][known] - torch.log(truth[known])
            errors.append(error.cpu().numpy())
            spreads.append(prediction[:, 1][known].clamp(-6, 6).exp().cpu().numpy())
            target = torch.from_numpy(boundary.reshape(-1, boundary.shape[-1])).to(device)
            accuracies.append(float(((prediction[:, 2] > 0).float() == target).float().mean()))
            counted += int(known.sum())
    model.train()
    if was_training:
        network.train()
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


# ----------------------------------------------------------------- the run


def train(root: Path, arm: str = "connectome", seed: int = 0, regime: str = "R1", window: int = 2,
          steps: int = DEFAULT_STEPS, batch: int = DEFAULT_BATCH,
          network_learning_rate: float = NETWORK_GRID[0],
          head_learning_rate: float | None = None, dt_s: float = DT_S,
          interval_s: float = INTERVAL_S, train_clips: int | None = None,
          validation_clips: int = VALIDATION_CLIPS, evaluate_every: int = EVALUATE_EVERY,
          out_dir: Path | None = None, save: bool = True, progress_every: int = 50,
          head_from: Path | None = None, head_dir: Path | None = None) -> dict:
    """Fit one network and its head, on one arm with one seed, keeping the best validation checkpoint."""
    from flyvis.solver import Penalty

    root = Path(root)
    network, spec, description = build_trainable(arm, seed, regime)
    device = next(network.parameters()).device
    types = [t.decode() if isinstance(t, bytes) else str(t)
             for t in network.connectome.output_cell_types[:]]
    repeats = max(int(round(float(interval_s) / dt_s)), 1)

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    warm = reservoir_head(arm, seed, window, head_dir) if head_from is None else Path(head_from)
    if warm is not None and Path(warm).exists():
        saved = torch.load(Path(warm), map_location="cpu", weights_only=False)
        statistics = saved["record"]["statistics"]
        model = head_module.Readout(types=len(types), window=window, mean=statistics["mean"],
                                    std=statistics["std"],
                                    log_depth_offset=statistics["log_depth_offset"]).to(device)
        model.load_state_dict({k: v.to(device) for k, v in saved["state_dict"].items()})
        started_from = Path(warm).name
    else:
        statistics = statistics_of(root, arm, train_clips)
        model = head_module.Readout(types=len(types), window=window, mean=statistics["mean"],
                                    std=statistics["std"],
                                    log_depth_offset=statistics["log_depth_offset"]).to(device)
        started_from = None
    model.train()

    fitting = loaded_split(root, "train", train_clips)
    checking = loaded_split(root, "validation")
    if head_learning_rate is None:
        head_learning_rate = HEAD_FINETUNE_RATE if started_from else HEAD_LEARNING_RATE
    groups = parameter_groups(network, network_learning_rate)
    optimiser = torch.optim.Adam(
        [*groups, {"params": list(model.parameters()), "lr": head_learning_rate, "name": "head"}])
    base_rates = [group["lr"] for group in optimiser.param_groups]
    penalizer = {k: dict(v) if isinstance(v, dict) else v for k, v in PENALIZER.items()}
    penalizer["activity_penalty"]["activity_baseline"] = measured_baseline(
        network, fitting, types, dt_s, repeats, device)
    try:
        from datamate import Namespace

        penalty = Penalty(Namespace(**{k: Namespace(**v) if isinstance(v, dict) else v
                                       for k, v in penalizer.items()}), network)
    except Exception as refused:        # the penalty is the engine's; a version without it is not fatal
        penalty = None
        penalty_refused = str(refused)
    else:
        penalty_refused = None
    rates = schedule(network_learning_rate, steps)
    penalty_rates = schedule(PENALTY_LEARNING_RATE, steps)

    # the grey steady state is a property of the network, which is moving, so it is recomputed on the
    # same cadence as validation rather than once for the whole run (the engine recomputes it per epoch)
    state = steady(network, batch, dt_s)
    history, best, best_state = [], None, None
    started = time.time()
    # where this run STARTS, measured before any update. It is recorded and it is eligible to be kept: if
    # no step of this regime improves on the frozen network's own readout, that is the finding, and a
    # checkpoint that is quietly worse than its starting point is not.
    zero = evaluate(network, model, checking, types, window, dt_s, repeats, device, validation_clips)
    history.append({"step": 0, "loss": None, "mean_activity": None, "network_lr": None,
                    "validation": zero})
    best = history[0]
    best_state = {"network": {k: v.detach().cpu().clone() for k, v in network.state_dict().items()},
                  "head": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
    for step in range(1, steps + 1):
        if step > 1 and evaluate_every and (step - 1) % evaluate_every == 0:
            state = steady(network, batch, dt_s)
        decay = float(rates[min(step - 1, len(rates) - 1)]) / max(network_learning_rate, 1e-12)
        for index, group in enumerate(optimiser.param_groups):
            if group.get("name") != "head":
                group["lr"] = base_rates[index] * decay
        if penalty is not None:
            for optim in penalty.optimizers.values():
                for group in optim.param_groups:
                    group["lr"] = float(penalty_rates[min(step - 1, len(penalty_rates) - 1)])
        index = rng.integers(0, len(fitting), batch)
        lum, depth, boundary = fitting.batch(index)
        optimiser.zero_grad(set_to_none=True)
        activity, held = simulate(network, lum, types, state, dt_s, repeats, device)
        frames = held.shape[1]
        rows = torch.arange(frames, device=held.device)[:, None] - torch.arange(
            window - 1, -1, -1, device=held.device)
        windowed = held[:, rows.clamp(min=0)].reshape(-1, window, len(types), held.shape[-1])
        prediction = model(windowed)
        depth_term, depth_stats = head_module.depth_loss(
            prediction, torch.from_numpy(depth.reshape(-1, depth.shape[-1])).to(device))
        boundary_term, boundary_stats = head_module.boundary_loss(
            prediction, torch.from_numpy(boundary.reshape(-1, boundary.shape[-1])).to(device))
        loss = depth_term + boundary_term
        # the engine's own order: the task loss steps first with the graph retained, then the activity
        # penalty takes its own step on the resting potentials and frees the graph
        loss.backward(retain_graph=penalty is not None)
        optimiser.step()
        if penalty is not None:
            penalty(activity=activity, iteration=step)
        if step % evaluate_every == 0 or step == steps:
            checked = evaluate(network, model, checking, types, window, dt_s, repeats, device,
                               validation_clips)
            row = {"step": step, "loss": float(loss.detach()),
                   "mean_activity": float(activity.detach().mean()),
                   "network_lr": {g["name"]: g["lr"] for g in optimiser.param_groups
                                  if g.get("name") != "head"},
                   **depth_stats, **boundary_stats, "validation": checked}
            history.append(row)
            score = checked.get("silog", float("inf"))
            if best is None or score < best["validation"].get("silog", float("inf")):
                best = row
                best_state = {
                    "network": {k: v.detach().cpu().clone() for k, v in network.state_dict().items()},
                    "head": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                }
            if progress_every:
                print(f"{regime} {arm} seed {seed} lr {network_learning_rate:g}: step {step}/{steps}, "
                      f"loss {row['loss']:.4f}, validation silog "
                      f"{checked.get('silog', float('nan')):.4f}, "
                      f"{(time.time() - started) / step:.3f} s/step", flush=True)

    from conectoma.network.regimes import trainable_report

    record = {
        "checkpoint_version": CHECKPOINT_VERSION, "regime": regime, "arm": arm, "seed": seed,
        "window": window, "steps": steps, "batch": batch,
        "network_learning_rate": network_learning_rate, "head_learning_rate": head_learning_rate,
        "validation_at_start": history[0]["validation"] if history else None,
        "penalty_learning_rate": PENALTY_LEARNING_RATE,
        "decay_stages": DECAY_STAGES, "t_pre_s": T_PRE_S, "dt_s": dt_s, "interval_s": interval_s,
        "types": types, "description": description, "device": str(device),
        "spec_sha256": spec_digest(spec), "code_sha256": code_digest(),
        "statistics": statistics, "head_parameters": model.parameter_count,
        "head_started_from": started_from,
        "network_parameters": trainable_report(network)["trainable"],
        "network_group_rates": {g["name"]: {"rms": g["rms"], "rate": g["lr"]} for g in groups},
        "penalty": penalizer if penalty is not None else {"refused": penalty_refused, **penalizer},
        "train_clips": len(fitting), "validation_clips": len(checking),
        "seconds": round(time.time() - started, 1),
        "seconds_per_step": round((time.time() - started) / max(steps, 1), 3),
        "best": best, "history": history,
    }
    if save:
        out = Path(out_dir) if out_dir is not None else DERIVED
        out.mkdir(parents=True, exist_ok=True)
        path = checkpoint_path(regime, arm, seed, window, out)
        torch.save({"network": (best_state or {}).get("network", network.state_dict()),
                    "head": (best_state or {}).get("head", model.state_dict()),
                    "record": record}, path)
        write_json(path.with_suffix(".json"), record)
        record["path"] = str(path)
    del network, model
    torch.cuda.empty_cache()
    return record


def choose_rate(root: Path, arm: str = "connectome", regime: str = "R1", seed: int = 0,
                grid: tuple = NETWORK_GRID, out_dir: Path | None = None, **kwargs) -> dict:
    """Choose this arm's network learning rate on the VALIDATION split, and keep the run that won.

    The grid is resolved with the arm's first seed, and the winning run IS that seed's checkpoint: it was
    selected on validation, which is what the validation split is for. The remaining seeds then train at
    the chosen rate. No case clip is read anywhere in here.
    """
    rows = []
    best = None
    for rate in grid:
        record = train(root, arm=arm, seed=seed, regime=regime, network_learning_rate=rate,
                       out_dir=out_dir, save=False, **kwargs)
        score = (record["best"] or {}).get("validation", {}).get("silog", float("inf"))
        rows.append({"network_learning_rate": rate, "validation_silog": score,
                     "seconds": record["seconds"], "steps": record["steps"],
                     "mean_activity": (record["best"] or {}).get("mean_activity")})
        if best is None or score < best[0]:
            best = (score, rate, record)
    if best is None:
        raise RuntimeError(f"the learning-rate grid produced no run for arm {arm}")
    score, rate, record = best
    # rerun the winner with saving on, rather than keeping a state in memory across three runs
    kept = train(root, arm=arm, seed=seed, regime=regime, network_learning_rate=rate,
                 out_dir=out_dir, save=True, **kwargs)
    return {"arm": arm, "regime": regime, "seed": seed, "chosen": rate, "grid": rows,
            "validation_silog": (kept["best"] or {}).get("validation", {}).get("silog"),
            "path": kept.get("path")}


def load(path: Path, device: str | None = None, transfer: bool = True):
    """A trained network and its head, rebuilt from the checkpoint's own record.

    The arm's graph is rebuilt from the specification, not stored: it is deterministic, and its digest is
    recorded, so a checkpoint read against a different connectome is refused here rather than producing
    numbers nobody can trace.
    """
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    saved = torch.load(Path(path), map_location=device, weights_only=False)
    record = saved["record"]
    network, spec, _ = build_trainable(record["arm"], record["seed"], record["regime"], transfer)
    if spec_digest(spec) != record["spec_sha256"]:
        raise ValueError(f"{Path(path).name} was trained on a different connectome specification")
    network.load_state_dict(saved["network"])
    network.eval()
    for parameter in network.parameters():
        parameter.requires_grad_(False)
    statistics = record.get("statistics", {})
    model = head_module.Readout(types=len(record["types"]), window=record["window"],
                                mean=statistics.get("mean"), std=statistics.get("std"),
                                log_depth_offset=statistics.get("log_depth_offset", 0.0))
    model.load_state_dict(saved["head"])
    model.to(device).eval()
    return network, model, record


def records(regime: str = "R1", out_dir: Path | None = None) -> list[dict]:
    """Every training record of a regime on disk, so a report can say which networks exist."""
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((out_dir or DERIVED).glob(f"{regime}-*.json"))]
