"""What the neuron-level visual system does as a frozen network, and what it costs.

Measured, because none of it can be assumed at this size (about a hundred thousand neurons and twelve
million connections):

- **stability** after grey input, from the engine's initialisation and from the published model's values;
- **cost**: simulated seconds per wall-clock second, and peak GPU memory;
- **whether training R1 fits**: one forward and backward pass through a training clip, or the fact that it
  does not fit on this GPU, recorded rather than crashed on;
- **whether the eye reaches the readouts**: a full-field flash after grey, and the response of the input,
  intermediate and readout (LC and LPLC) populations. A frozen graph whose readouts never move carries no
  visual signal for a head to learn from.

Every stage is kept in a run log so a rerun resumes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from conectoma.network.characterize import TRAIN_DT, simulation_rate, stability, training_step
from conectoma.network.engine import load_engine, published_model_dir, run_log
from conectoma.network.neurons import build_neuron_network, graph_digest
from conectoma.network.regimes import trainable_report


def flash_response(network, intensity: float = 1.0, seconds: float = 0.5, dt: float = TRAIN_DT,
                   threshold: float = 1e-5) -> dict:
    """Grey to a steady state, then a full-field step on every input; how far each role moves.

    A cell counts as responding when its voltage moves by more than `threshold` volts, well above float32
    resolution around the resting range; the size of the change is reported separately, because at the
    engine's initial strengths each synaptic layer attenuates a signal by about two orders of magnitude.
    """
    import torch

    stimulus = network.stimulus
    frames = int(seconds / dt)
    with torch.no_grad():
        state = network.steady_state(t_pre=1.0, dt=dt, batch_size=1, value=0.5)
        baseline = state.nodes.activity[0].clone()
        stimulus.zero(1, frames)
        stimulus.add_input(torch.full((1, frames, 1, stimulus.n_input_elements), intensity,
                                      device=baseline.device))
        activity = network(stimulus(), dt, state=state)[0]
    change = (activity - baseline[None]).abs().max(dim=0).values.cpu().numpy()
    roles = np.asarray(network.connectome.nodes.role).astype(str)
    result = {}
    for role in ("input", "intermediate", "output"):
        members = change[roles == role]
        result[role] = {
            "cells": int(members.size),
            "responding_fraction": round(float(np.mean(members > threshold)), 4) if members.size else None,
            "median_change": round(float(np.median(members)), 6) if members.size else None,
            "max_change": round(float(members.max()), 4) if members.size else None,
        }
    return {"intensity": intensity, "seconds": seconds, "dt": dt, "threshold": threshold, "by_role": result}


def peak_memory_gb() -> float | None:
    import torch

    return round(torch.cuda.max_memory_allocated() / 1e9, 2) if torch.cuda.is_available() else None


def characterize_visual_cns(graph_path: Path, log=print) -> dict:
    import torch

    load_engine()
    transfer_from = published_model_dir("000")
    digest = graph_digest(graph_path)
    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    runs = run_log(f"characterize-visual-cns-{digest[:12]}", {"digest": digest, "device": device})
    report: dict = {
        "graph": Path(graph_path).name, "digest": digest, "device": device, "torch": torch.__version__,
    }

    def frozen(init: str) -> dict:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        network = build_neuron_network(
            graph_path, "R0", transfer_from=transfer_from if init == "transfer" else None,
        )
        entry = {
            "parameters": trainable_report(network),
            "transfer": network.transfer_report,
            "compile": network.connectome.compile_report,
            "stability": stability(network),
            "simulation": simulation_rate(network, seconds=1.0, batch_size=1),
            "flash": flash_response(network),
            "peak_memory_gb": peak_memory_gb(),
        }
        del network
        torch.cuda.empty_cache()
        return entry

    log("[1/2] the frozen network (R0) from both starting points")
    report["frozen"] = {}
    for init in ("default", "transfer"):
        report["frozen"][init] = runs.step(f"frozen/{init}", lambda init=init: frozen(init))
        entry = report["frozen"][init]
        log(f"      {init}: stable {entry['stability']['finite']}, readouts responding "
            f"{entry['flash']['by_role']['output']['responding_fraction']}, "
            f"peak {entry['peak_memory_gb']} GB")

    def r1_step() -> dict:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        network = build_neuron_network(graph_path, "R1", transfer_from=transfer_from)
        network.train()
        try:
            result = training_step(network, batch_size=1, repeats=2)
        except torch.cuda.OutOfMemoryError as error:
            result = {"out_of_memory": True, "batch_size": 1, "message": str(error).splitlines()[0]}
        result["trainable"] = trainable_report(network)["trainable"]
        del network
        torch.cuda.empty_cache()
        return result

    log("[2/2] the cost of one R1 training step")
    report["training_step_R1"] = runs.step("training_step/R1", r1_step)
    log(f"      {report['training_step_R1']}")
    report["reused_steps"] = runs.reused
    return report
