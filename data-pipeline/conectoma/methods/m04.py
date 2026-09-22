"""M04: the published connectome-constrained network, frozen, with its own trained flow decoder.

This is the method this product generalises, used exactly as published: the fifty-model ensemble of
Lappalainen et al. (2024, Nature, doi:10.1038/s41586-024-07939-3), every parameter frozen, with the
`DecoderGAVP` head it was trained with (`flyvis/config/task/task.yaml`: shape [8, 2], kernel 5, constant
weight 0.001). The decoder emits a flow vector per column, in the engine's own units, which is the unit
the corpus already stores its flow in (pixels per image height, y up, summed over the 13 x 13 box). That
flow then goes through the SAME parallax inversion M01 uses, so M01 and M04 differ only in how the
displacement was obtained. That is the comparison this unit exists to make.

Two things are stated rather than smoothed over:

- **The published model was trained at Sintel's frame rate**, and it is simulated at the task's own time
  step (`dt` 0.02 s). A clip of another source is resampled to that step by holding each frame for the
  whole of its own interval, which is what the engine's own dataset does; a source whose interval is far
  from Sintel's is therefore outside the temporal statistics the model was trained on, and the report
  records the interval each clip was run at.
- **The ensemble is fifty models.** M04 reports the median across the models it was run with and the
  spread; a single model is never the headline. Running all fifty on every clip is expensive, so the
  number of models is a parameter and the report records it.
"""

from __future__ import annotations

import numpy as np

from conectoma.methods import readout
from conectoma.methods.m01 import (
    FLOW_NOISE_PX,
    MAX_DEVIATION_DEG,
    MIN_PARALLAX_PX,
    UNCERTAINTY_TOLERANCE,
    _clip_motions,
    _result,
)

DT_S = 0.02            # the published task's integration step
MODELS = ("000",)      # the ensemble is ranked by task error, so 000 is its best model


def decode_flow(lum: np.ndarray, interval_s: float, models: tuple = MODELS, dt_s: float = DT_S,
                ) -> dict[str, np.ndarray]:
    """Run the frozen published network on a clip and decode its flow, model by model.

    Returns the median flow across the models, in the engine's units (frames - 1, 2, columns), and the
    spread across them, which is what says whether the ensemble agrees.
    """
    import torch

    from conectoma.network.engine import load_engine, published_model_dir

    flyvis = load_engine()
    lum = np.asarray(lum, dtype=np.float32)
    repeats = max(int(round(float(interval_s) / dt_s)), 1)
    movie = torch.from_numpy(np.repeat(lum, repeats, axis=0))[None, :, None, :]   # (1, steps, 1, hexals)

    per_model = []
    for model in models:
        view = flyvis.NetworkView(str(published_model_dir(model)))
        network = view.init_network("best")
        decoder = view.init_decoder("best")["flow"]
        network.eval()
        decoder.eval()
        with torch.no_grad():
            activity = network.simulate(movie, dt_s, as_layer_activity=False)
            decoded = decoder(activity)                      # (1, steps, 2, hexals)
        held = decoded[0].detach().cpu().numpy()
        # one answer per source frame: the last simulated step of that frame, which is the one the network
        # has seen the whole frame for
        sampled = held[repeats - 1:: repeats][: len(lum)]
        per_model.append(sampled[:-1] if len(sampled) > 1 else sampled)
    stack = np.stack(per_model)
    return {
        "flow_engine": np.median(stack, axis=0),
        "spread": stack.std(axis=0) if len(stack) > 1 else np.zeros_like(stack[0]),
        "models": len(per_model),
        "repeats": repeats,
    }


def run(clip: dict, column_spacing_deg: float, *, interval_s: float | None = None,
        motion: tuple | None = None, models: tuple = MODELS, dt_s: float = DT_S,
        flow_noise_px: float = FLOW_NOISE_PX, tolerance: float = UNCERTAINTY_TOLERANCE,
        max_deviation_deg: float = MAX_DEVIATION_DEG, min_parallax_px: float = MIN_PARALLAX_PX,
        ) -> dict[str, np.ndarray]:
    """Run M04 on a rendered clip: the frozen ensemble's flow, through the shared inversion."""
    lum, motions, steps = _clip_motions(clip, motion)
    step_s = interval_s if interval_s is not None else clip.get("interval_s")
    if step_s is None:
        raise ValueError("M04 needs the clip's frame interval: the network is simulated in time")
    decoded = decode_flow(lum, float(step_s), models, dt_s)
    flow_px = readout.pixel_flow(decoded["flow_engine"])

    distance = np.full((steps, readout.COLUMNS), np.nan)
    uncertainty = np.full((steps, readout.COLUMNS), np.inf)
    refused = np.ones((steps, readout.COLUMNS), dtype=bool)
    independent = np.zeros((steps, readout.COLUMNS), dtype=bool)
    deviation = np.full((steps, readout.COLUMNS), np.nan)
    spread = np.zeros((steps, readout.COLUMNS), dtype=np.float32)

    for step in range(min(steps, len(flow_px))):
        rotation, translation = motions[step]
        if not np.any(translation):
            continue
        out = readout.triangulate(flow_px[step], rotation, translation, column_spacing_deg)
        sigma = readout.distance_uncertainty(out["distance_m"], out["baseline_m"],
                                             column_spacing_deg, flow_noise_px)
        bad = readout.unknown(out["distance_m"], sigma, tolerance)
        distance[step] = np.where(bad, np.nan, out["distance_m"])
        uncertainty[step] = sigma
        refused[step] = bad
        deviation[step] = out["deviation_deg"]
        spread[step] = np.linalg.norm(decoded["spread"][step], axis=0)
        independent[step] = readout.moving(out["deviation_deg"], out["parallax_px"],
                                           max_deviation_deg, min_parallax_px) & ~bad
    return _result(distance, refused, independent, uncertainty, spread, deviation)
