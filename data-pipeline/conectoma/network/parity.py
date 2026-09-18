"""Parity with the published connectome-constrained model.

Two questions, answered separately because either can fail without the other:

1. **Does this product's construction path build the published network?** The published model is loaded
   twice from the same checkpoint: once by the engine's own loader (its compiler, its parameter layout),
   once through this product's compiler and regime builder with the published consensus connectome as the
   specification. Both are driven with the same stimuli and every recorded voltage is compared. The
   gate is a numerical tolerance, not a visual impression.
2. **Does the published model behave as published?** Each model of the published ensemble, built through
   this product's path, is characterised with moving edges, and the T4 and T5 subtypes are compared with
   their known preferred directions. This reproduces the headline property of the published model with the
   code that will later carry the MaleCNS connectome, so a difference found there is about the connectome,
   not about the plumbing.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from conectoma.network.engine import PUBLISHED_ENSEMBLE, load_engine, published_model_dir, run_log
from conectoma.network.regimes import PER_OFFSET, build_network
from conectoma.network.tuning import (
    central_responses,
    ensemble_quality,
    motion_tuning,
    moving_edges,
    response_dataset,
    stimulus_description,
    summarise_tuning,
)

# float32 simulation of identical operations in identical order is expected to agree to the last bit; the
# tolerance leaves room for a different summation order on another device, and nothing more.
VOLTAGE_TOLERANCE = 1e-5
ENSEMBLE_SIZE = 50


def checkpoint_path(model_dir: Path) -> Path:
    flyvis = load_engine()
    return Path(flyvis.NetworkView(model_dir).get_checkpoint("best"))


def reference_network(model_dir: Path):
    """The published model as the engine itself loads it."""
    flyvis = load_engine()
    network = flyvis.NetworkView(model_dir).init_network()
    network.eval()
    return network


def product_network(model_dir: Path):
    """The published model built through this product's compiler and regime builder, then restored."""
    flyvis = load_engine()
    from flyvis.utils.chkpt_utils import recover_network

    network = build_network(
        Path(flyvis.connectome_file), "R1", extent=15, n_syn_fill=1, count_groupby=PER_OFFSET,
    )
    recover_network(network, checkpoint_path(model_dir))
    network.eval()
    return network


def voltage_parity(model: str = "000", samples: tuple[int, ...] = (0, 17, 71, 143), runs=None) -> dict:
    """Every voltage of every cell, both paths, the same stimuli: the largest absolute difference."""
    key = f"voltage/{model}/{'-'.join(str(s) for s in samples)}"
    if runs is not None:
        return runs.step(key, lambda: voltage_parity(model, samples))
    import torch

    model_dir = published_model_dir(model)
    dataset = moving_edges()
    everything = None  # all cells, not only the central ones
    results = {}
    for name, factory in (("engine", reference_network), ("product", product_network)):
        network = factory(model_dir)
        everything = np.arange(network.n_nodes)
        with torch.no_grad():
            parts = [
                responses
                for _, responses in network.stimulus_response(
                    dataset, dataset.dt, indices=list(samples), t_pre=1.0, t_fade_in=0.0, batch_size=1,
                )
            ]
        results[name] = parts
        del network
        torch.cuda.empty_cache()

    differences = [
        float(np.abs(a - b).max()) for a, b in zip(results["engine"], results["product"], strict=True)
    ]
    scale = max(float(np.abs(a).max()) for a in results["engine"])
    return {
        "model": f"{PUBLISHED_ENSEMBLE}/{model}",
        "stimuli": list(samples),
        "cells": int(everything.size),
        "frames": [int(a.shape[1]) for a in results["engine"]],
        "max_abs_difference": max(differences),
        "largest_voltage": round(scale, 4),
        "tolerance": VOLTAGE_TOLERANCE,
        "passed": max(differences) <= VOLTAGE_TOLERANCE,
    }


def parity_log(dataset):
    """The resumable log of a parity run; valid only for this ensemble, engine and stimulus."""
    flyvis = load_engine()
    return run_log("parity-published", {
        "ensemble": PUBLISHED_ENSEMBLE,
        "engine": getattr(flyvis, "__version__", "1.2.0"),
        "stimulus": stimulus_description(dataset),
        "tolerance": VOLTAGE_TOLERANCE,
    })


def ensemble_tuning(models: list[str] | None = None, batch_size: int = 4, log=print, runs=None) -> dict:
    """Motion tuning of every model of the published ensemble, built through this product's path.

    With a run log, each model's tuning is stored as soon as it is measured and reused on a rerun.
    """
    import torch

    models = models or [f"{i:03d}" for i in range(ENSEMBLE_SIZE)]
    dataset = moving_edges()
    per_model = []
    tuning_rows: dict[str, dict[str, list]] = {}
    started = time.time()

    def measure(model: str) -> dict:
        network = product_network(published_model_dir(model))
        with torch.no_grad():
            responses = central_responses(network, dataset, batch_size=batch_size)
        result = motion_tuning(response_dataset(responses[None], dataset, network))
        del network
        torch.cuda.empty_cache()
        return result

    for position, model in enumerate(models):
        key = f"tuning/{model}"
        tuning = runs.step(key, lambda model=model: measure(model)) if runs is not None else measure(model)
        per_model.append({"model": model, "tuning": tuning})
        for cell_type, row in tuning.items():
            merged = tuning_rows.setdefault(cell_type, {name: [] for name in row})
            for name, values in row.items():
                merged[name].extend(values)
        log(f"      {position + 1}/{len(models)} {model} ({time.time() - started:.0f}s)")
    return {
        "ensemble": PUBLISHED_ENSEMBLE,
        "models": models,
        "summary": summarise_tuning(tuning_rows),
        "quality": ensemble_quality(per_model),
        "per_model": per_model,
        "stimulus": stimulus_description(dataset),
    }


def engine_pipeline_tuning(model: str) -> dict:
    """The same model characterised end to end by the engine's own pipeline (loader, responses, analysis)."""
    flyvis = load_engine()
    from flyvis.analysis.moving_bar_responses import direction_selectivity_index, preferred_direction
    from flyvis.analysis.stimulus_responses import moving_edge_responses

    from conectoma.network.tuning import KNOWN_PREFERRED, MOTION_TYPES, POLARITY, _angle_distance

    data = moving_edge_responses(flyvis.NetworkView(published_model_dir(model)))
    dsi = direction_selectivity_index(data)
    theta = preferred_direction(data)
    cell_types = data["cell_type"].values
    result = {}
    for cell_type in MOTION_TYPES:
        neuron = int(np.nonzero(cell_types == cell_type)[0][0])
        intensity = POLARITY[cell_type[:2]]
        d = float(dsi.sel(intensity=intensity).isel(neuron=neuron).values.reshape(-1)[0])
        t = float(theta.sel(intensity=intensity).isel(neuron=neuron).values.reshape(-1)[0])
        result[cell_type] = {
            "dsi": round(d, 4),
            "preferred_direction_degrees": round(float(np.degrees(t)) % 360, 1),
            "distance_to_known_degrees": round(
                float(np.degrees(_angle_distance(t, KNOWN_PREFERRED[cell_type[-1]]))), 1
            ),
        }
    return result


def pipeline_crosscheck(product_tuning: dict, models: list[str], runs=None) -> dict:
    """Does this product's tuning analysis equal the engine's end-to-end pipeline, model by model?

    Voltage parity shows the networks are the same; this shows the way responses are gathered and analysed
    is the same, so a tuning number here means what the engine's would.
    """
    rows = []
    for model in models:
        key = f"engine_pipeline/{model}"
        engine = runs.step(key, lambda m=model: engine_pipeline_tuning(m)) if runs is not None else (
            engine_pipeline_tuning(model)
        )
        ours = product_tuning[model]
        dsi_gap = max(abs(engine[t]["dsi"] - ours[t]["dsi"][0]) for t in engine)
        angle_gap = max(
            float(np.degrees(_wrapped(engine[t]["preferred_direction_degrees"],
                                      ours[t]["preferred_direction_degrees"][0])))
            for t in engine
        )
        rows.append({"model": model, "largest_dsi_difference": round(dsi_gap, 6),
                     "largest_direction_difference_degrees": round(angle_gap, 3), "engine": engine})
    return {
        "models": models,
        "largest_dsi_difference": max(r["largest_dsi_difference"] for r in rows),
        "largest_direction_difference_degrees": max(r["largest_direction_difference_degrees"] for r in rows),
        "per_model": rows,
    }


def _wrapped(a_degrees: float, b_degrees: float) -> float:
    """Angle between two directions given in degrees, in radians, in [0, pi]."""
    difference = np.radians(a_degrees - b_degrees)
    return float(np.abs((difference + np.pi) % (2 * np.pi) - np.pi))
