"""What the MaleCNS connectome does as a frozen network, before any task is trained on it.

Four measurements, each of which a later result depends on:

- **stability.** A recurrent network with three million connections and mostly untrained parameters can
  diverge. The steady state after grey input is recorded (bounded or not, and how far it still moves in the
  last half second), for both starting points: the engine's initialisation, and the published model's
  trained values transferred where cell types match.
- **cost.** Simulated seconds per wall-clock second, and the wall-clock time and peak memory of one
  training step (forward and backward through a clip of the length the published model was trained on) in
  R1 and R2, next to the same step on the published network. This is the measurement the training plan
  was waiting for.
- **motion tuning of the frozen network.** The published model's direction selectivity comes from training
  on optic flow. Whether the MaleCNS wiring carries any of it with borrowed parameters and no training is
  an open question with no expected answer; the numbers are reported as they come.
- **the same tuning on the null controls.** Degree-preserving rewiring, a size-matched random graph and a
  sign shuffle, several seeds each, with the same transferred parameters. Any tuning the real connectome
  shows is only attributable to its wiring if the controls do not show it too.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from conectoma.connectome.nulls import CONTROLS
from conectoma.network.engine import engine_root, load_engine, published_model_dir
from conectoma.network.lattice import spec_digest
from conectoma.network.regimes import build_network, trainable_report
from conectoma.network.tuning import (
    central_responses,
    motion_tuning,
    moving_edges,
    response_dataset,
    summarise_tuning,
)

# The clip the published model was trained on: 19 frames of optic flow at 50 Hz, four clips per batch.
TRAIN_FRAMES = 19
TRAIN_BATCH = 4
TRAIN_DT = 0.02


def stability(network, seconds: float = 2.0, dt: float = TRAIN_DT) -> dict:
    """Grey input for `seconds`: is the state bounded, and has it settled in the last half second?"""
    import torch

    with torch.no_grad():
        states = network.steady_state(t_pre=seconds, dt=dt, batch_size=1, value=0.5, return_last=False)
    activity = torch.stack([s.nodes.activity for s in states], dim=1)[0]
    last = activity[-1]
    half = activity[-int(0.5 / dt)]
    return {
        "finite": bool(torch.isfinite(activity).all()),
        "min": round(float(last.min()), 4),
        "max": round(float(last.max()), 4),
        "mean_abs": round(float(last.abs().mean()), 4),
        "drift_last_half_second": round(float((last - half).abs().max()), 6),
    }


def simulation_rate(network, seconds: float = 2.0, dt: float = 1 / 200, batch_size: int = 4) -> dict:
    """Simulated seconds per wall-clock second for a batch of grey movies, without gradients."""
    import torch

    stimulus = network.stimulus
    frames = int(seconds / dt)
    stimulus.zero(batch_size, frames)
    stimulus.add_pre_stim(0.5)
    with torch.no_grad():
        network(stimulus(), dt)  # warm-up
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        started = time.time()
        network(stimulus(), dt)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
    wall = time.time() - started
    return {
        "batch_size": batch_size,
        "dt": dt,
        "simulated_seconds": seconds,
        "wall_seconds": round(wall, 3),
        "simulated_seconds_per_wall_second_per_sample": round(seconds * batch_size / wall, 2),
    }


def training_step(network, frames: int = TRAIN_FRAMES, batch_size: int = TRAIN_BATCH, dt: float = TRAIN_DT,
                  repeats: int = 3) -> dict:
    """Wall-clock time and peak memory of one forward and backward pass through a training clip."""
    import torch

    device = network._source_indices.device
    stimulus = network.stimulus
    cuda = torch.cuda.is_available()
    times = []
    if cuda:
        torch.cuda.reset_peak_memory_stats()
    for _ in range(repeats + 1):
        network.zero_grad(set_to_none=True)
        stimulus.zero(batch_size, frames)
        stimulus.add_input(torch.rand((batch_size, frames, 1, stimulus.n_input_elements), device=device))
        if cuda:
            torch.cuda.synchronize()
        started = time.time()
        with torch.enable_grad():
            initial = network.steady_state(t_pre=0.5, dt=dt, batch_size=batch_size, value=0.5)
            activity = network(stimulus(), dt, state=initial)
            activity.relu().mean().backward()
        if cuda:
            torch.cuda.synchronize()
        times.append(time.time() - started)
    network.zero_grad(set_to_none=True)
    return {
        "frames": frames,
        "batch_size": batch_size,
        "dt": dt,
        "seconds_per_step": round(float(np.median(times[1:])), 3),
        "peak_memory_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2) if cuda else None,
    }


def control_spec_path(spec_path: Path, kind: str, seed: int) -> Path:
    """Write a null control next to the engine's data, named by the measured graph it was drawn from."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    control = CONTROLS[kind](spec, seed=seed)
    root = engine_root() or Path(spec_path).parent
    folder = Path(root).parent / "controls"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{spec_digest(spec_path)[:12]}-{kind}-seed{seed}.json"
    if not path.exists():
        path.write_text(json.dumps(control) + "\n", encoding="utf-8", newline="\n")
    return path


def tuning_of(network, dataset, batch_size: int = 4) -> dict:
    import torch

    with torch.no_grad():
        responses = central_responses(network, dataset, batch_size=batch_size)
    return motion_tuning(response_dataset(responses[None], dataset, network))


def merge(rows: list[dict]) -> dict:
    merged: dict[str, dict[str, list]] = {}
    for tuning in rows:
        for cell_type, row in tuning.items():
            target = merged.setdefault(cell_type, {k: [] for k in row})
            for key, values in row.items():
                target[key].extend(values)
    return merged


def characterize(spec_path: Path, seeds: tuple[int, ...] = (0, 1, 2, 3, 4), log=print) -> dict:
    import torch

    flyvis = load_engine()
    transfer_from = published_model_dir("000")
    dataset = moving_edges()
    report: dict = {
        "connectome": Path(spec_path).name,
        "digest": spec_digest(spec_path),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "torch": torch.__version__,
        "engine": getattr(flyvis, "__version__", "1.2.0"),
    }

    log("[1/4] the frozen network (R0) from both starting points")
    report["frozen"] = {}
    for init in ("default", "transfer"):
        network = build_network(spec_path, "R0", transfer_from=transfer_from if init == "transfer" else None)
        entry = {
            "parameters": trainable_report(network),
            "transfer": network.transfer_report,
            "compile": network.connectome.compile_report,
            "stability": stability(network),
            "simulation": simulation_rate(network),
        }
        tuning = tuning_of(network, dataset)
        entry["tuning"] = tuning
        entry["tuning_summary"] = summarise_tuning(tuning)
        report["frozen"][init] = entry
        log(f"      {init}: stable {entry['stability']['finite']}, "
            f"{entry['simulation']['simulated_seconds_per_wall_second_per_sample']} sim s per s per sample")
        del network
        torch.cuda.empty_cache()

    log("[2/4] cost of one training step per regime")
    report["training_step"] = {}
    for regime in ("R1", "R2"):
        network = build_network(spec_path, regime, transfer_from=transfer_from)
        network.train()
        report["training_step"][regime] = training_step(network) | {
            "trainable": trainable_report(network)["trainable"],
        }
        log(f"      {regime}: {report['training_step'][regime]}")
        del network
        torch.cuda.empty_cache()
    from conectoma.network.parity import product_network

    published = product_network(transfer_from)
    published.train()
    report["training_step"]["published_R1"] = training_step(published) | {
        "trainable": trainable_report(published)["trainable"],
    }
    log(f"      published R1: {report['training_step']['published_R1']}")
    del published
    torch.cuda.empty_cache()

    log("[3/4] null controls with the transferred parameters")
    report["controls"] = {}
    for kind in sorted(CONTROLS):
        rows = []
        stable = []
        for seed in seeds:
            path = control_spec_path(Path(spec_path), kind, seed)
            network = build_network(path, "R0", transfer_from=transfer_from)
            stable.append(stability(network))
            rows.append(tuning_of(network, dataset))
            log(f"      {kind} seed {seed}")
            del network
            torch.cuda.empty_cache()
        report["controls"][kind] = {
            "seeds": list(seeds),
            "stability": stable,
            "tuning": merge(rows),
            "tuning_summary": summarise_tuning(merge(rows)),
        }

    log("[4/4] done")
    report["stimulus"] = {"kind": "moving edges", "dt": dataset.dt, "speeds": list(dataset.speeds),
                          "angles": list(dataset.angles), "intensities": [0, 1]}
    return report
