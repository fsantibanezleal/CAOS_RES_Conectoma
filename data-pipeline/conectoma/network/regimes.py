"""What "frozen weights" means here: three regimes, one network, one switch.

In every regime the wiring is the measured connectome and never changes: which cell types connect, at which
column offsets, with how many synapses, and with which sign. What differs is which of the remaining
biophysical quantities a task may adjust:

- **R0 reservoir**: nothing inside the network trains (0 parameters on the right optic lobe);
- **R1 biophysical**: resting potential and time constant per cell type, synaptic strength per connected
  type pair (8,409 parameters on the right optic lobe);
- **R2 edge gain**: resting potential and time constant per neuron, synaptic strength per individual
  connection (3,002,181 parameters on the right optic lobe).

R0 is the literal reading of a connectome used as an architecture with frozen weights: only a readout
outside the network learns. R1 is the regime of the published connectome-constrained model, whose 734
trained parameters are of exactly these three kinds. R2 keeps every connection and its sign but lets each
one scale on its own, the most freedom that still respects the wiring.

Every regime starts from the same values. They are built at type granularity first (the engine's
initialisation, or the published model's trained values where cell types match) and then broadcast to the
finer granularity of R2, so a comparison between regimes compares what training was allowed to change,
never where it started.

The edge gain is the engine's own non-negative synaptic strength, one per connection, rather than an
exponential gain: the two describe the same set of networks (a non-negative scale per connection) and the
engine's parameter keeps the sign, the clamp and the checkpoint format of the published model.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from conectoma.network.engine import load_engine
from conectoma.network.lattice import REGISTERED_NAME, spec_digest

NODE_PARAMETERS = ("bias", "time_const")
EDGE_PARAMETERS = ("syn_strength",)
FROZEN_ALWAYS = ("sign", "syn_count")

PER_TYPE = ("type",)
PER_NEURON = ("type", "u", "v")
PER_TYPE_PAIR = ("source_type", "target_type")
# One group per connection. The engine reads the offset and the type pair back from any synapse-count
# grouping, so those columns stay in the key; the target column makes it unique, because a target cell
# receives at most one connection from each source cell.
PER_CONNECTION = ("source_type", "target_type", "du", "dv", "target_u", "target_v")
# The published model shares one synapse count per type pair and offset, which is exact when every type
# sits on every column. Its checkpoints carry that shape, so loading one needs the same grouping.
PER_OFFSET = ("source_type", "target_type", "du", "dv")


@dataclass(frozen=True)
class Regime:
    key: str
    name: str
    trainable: bool
    node_groupby: tuple[str, ...]
    edge_groupby: tuple[str, ...]
    summary: str


REGIMES: dict[str, Regime] = {
    "R0": Regime(
        "R0", "reservoir", False, PER_TYPE, PER_TYPE_PAIR,
        "every network parameter frozen; only a readout outside the network learns",
    ),
    "R1": Regime(
        "R1", "biophysical", True, PER_TYPE, PER_TYPE_PAIR,
        "resting potential and time constant per cell type, synaptic strength per connected type pair",
    ),
    "R2": Regime(
        "R2", "edge gain", True, PER_NEURON, PER_CONNECTION,
        "resting potential and time constant per neuron, synaptic strength per individual connection",
    ),
}


def network_config(
    spec_path: Path,
    regime: Regime,
    extent: int = 15,
    n_syn_fill: float = 0,
    seed: int = 0,
    count_groupby: tuple[str, ...] = PER_CONNECTION,
) -> dict:
    """The engine configuration of a regime, enough to rebuild the network from a checkpoint.

    Synapse counts are frozen in every regime and held per connection by default: after the
    target-centric expansion the same type pair and offset can carry different counts at different
    targets, and a shared value would average them away. `PER_OFFSET` reproduces the published model.
    """
    return {
        "connectome": {
            "type": REGISTERED_NAME,
            "file": str(spec_path),
            "extent": extent,
            "n_syn_fill": n_syn_fill,
            "digest": spec_digest(spec_path),
        },
        "dynamics": {"type": "PPNeuronIGRSynapses", "activation": {"type": "relu"}},
        "node_config": {
            "bias": {
                "type": "RestingPotential",
                "groupby": list(regime.node_groupby),
                "initial_dist": "Normal",
                "mode": "sample",
                "requires_grad": regime.trainable,
                "mean": 0.5,
                "std": 0.05,
                "penalize": {"activity": True},
                "seed": seed,
            },
            "time_const": {
                "type": "TimeConstant",
                "groupby": list(regime.node_groupby),
                "initial_dist": "Value",
                "value": 0.05,
                "requires_grad": regime.trainable,
            },
        },
        "edge_config": {
            "sign": {
                "type": "SynapseSign",
                "initial_dist": "Value",
                "requires_grad": False,
                "groupby": ["source_type", "target_type"],
            },
            "syn_count": {
                "type": "SynapseCount",
                "initial_dist": "Lognormal",
                "mode": "mean",
                "requires_grad": False,
                "std": 1.0,
                "groupby": list(count_groupby),
            },
            "syn_strength": {
                "type": "SynapseCountScaling",
                "initial_dist": "Value",
                "requires_grad": regime.trainable,
                "scale": 0.01,
                "clamp": "non_negative",
                "groupby": list(regime.edge_groupby),
            },
        },
    }


def _parameter(network, name: str):
    if name in network.node_params:
        return network.node_params[name]
    return network.edge_params[name]


def element_values(network, name: str) -> np.ndarray:
    """A parameter expanded to one value per neuron or per connection, whatever its grouping."""
    import torch

    parameter = _parameter(network, name)
    with torch.no_grad():
        values = parameter.raw_values.detach()[parameter.indices]
    return values.cpu().numpy()


def broadcast_parameters(source, target, names=NODE_PARAMETERS + EDGE_PARAMETERS) -> None:
    """Write the values of `source` into `target`, which shares its graph and groups at least as finely.

    Every group of the target takes the value its elements carry in the source. If a target group spans
    elements with different source values, the target is coarser than the source and the copy is refused.
    """
    import torch

    for name in names:
        values = element_values(source, name)
        parameter = _parameter(target, name)
        indices = parameter.indices.detach().cpu().numpy()
        grouped = np.full(parameter.raw_values.shape[0], np.nan, dtype=np.float64)
        grouped[indices] = values
        spread = np.zeros_like(grouped)
        np.maximum.at(spread, indices, np.abs(values - grouped[indices]))
        if np.nanmax(spread) > 1e-6 * max(1.0, float(np.nanmax(np.abs(grouped)))):
            raise ValueError(f"{name}: the target groups more coarsely than the source")
        with torch.no_grad():
            parameter.raw_values.copy_(torch.as_tensor(grouped, dtype=parameter.raw_values.dtype))


def build_network(
    spec_path: Path,
    regime: str = "R1",
    extent: int = 15,
    n_syn_fill: float = 0,
    seed: int = 0,
    transfer_from: Path | None = None,
    count_groupby: tuple[str, ...] = PER_CONNECTION,
):
    """A network of the given regime on the given connectome, with the shared starting values.

    `transfer_from` names a trained model of the published ensemble; where cell types match, its trained
    values replace the engine's initialisation (see `transfer`). The network is returned in training mode
    only if the regime trains anything.
    """
    flyvis = load_engine()
    spec_path = Path(spec_path).resolve()
    base = flyvis.Network(
        **network_config(spec_path, REGIMES["R1"], extent, n_syn_fill, seed, count_groupby)
    )
    report = None
    if transfer_from is not None:
        report = transfer(Path(transfer_from), base)
    chosen = REGIMES[regime]
    if chosen.key == "R1":
        network = base
    else:
        network = flyvis.Network(
            **network_config(spec_path, chosen, extent, n_syn_fill, seed, count_groupby)
        )
        broadcast_parameters(base, network)
        del base
    network.regime = chosen.key
    network.transfer_report = report
    if not chosen.trainable:
        network.eval()
    return network


def trainable_report(network) -> dict:
    """Parameter counts by name, split into trainable and frozen, as the regime claims them."""
    rows = {}
    for name, value in network.named_parameters():
        rows[name] = {"count": int(value.numel()), "trainable": bool(value.requires_grad)}
    return {
        "parameters": rows,
        "trainable": sum(r["count"] for r in rows.values() if r["trainable"]),
        "frozen": sum(r["count"] for r in rows.values() if not r["trainable"]),
    }


def gradient_check(network, n_frames: int = 6, dt: float = 0.02, seed: int = 0) -> dict:
    """Run a short simulation with gradients and report which parameters received one.

    The flag on a parameter is a promise; this is the check that the promise holds through the dynamics:
    a frozen parameter must receive no gradient, a trainable one must receive a non-zero gradient.
    """
    import torch

    generator = torch.Generator(device=network._source_indices.device).manual_seed(seed)
    network.zero_grad(set_to_none=True)
    stimulus = network.stimulus
    stimulus.zero(1, n_frames)
    # The input requires a gradient so that a graph exists even when no parameter does (R0); a frozen
    # parameter then provably receives none, rather than trivially for lack of a graph.
    movie = torch.rand(
        (1, n_frames, 1, stimulus.n_input_elements), generator=generator,
        device=network._source_indices.device,
    )
    movie.requires_grad_(True)
    stimulus.add_input(movie)
    with torch.enable_grad():
        activity = network(stimulus(), dt)
        activity.relu().sum().backward()
    input_gradient = movie.grad is not None and float(movie.grad.abs().sum()) > 0
    received = {}
    for name, value in network.named_parameters():
        grad = value.grad
        received[name] = {
            "trainable": bool(value.requires_grad),
            "gradient_norm": None if grad is None else float(grad.norm()),
        }
    violations = [
        name for name, row in received.items()
        if (row["trainable"] and not row["gradient_norm"]) or (not row["trainable"] and row["gradient_norm"])
    ]
    network.zero_grad(set_to_none=True)
    return {"parameters": received, "violations": violations, "input_gradient": input_gradient}


# -- transfer from the published model ------------------------------------------------------------------


def _reverse_aliases() -> dict[str, list[str]]:
    from conectoma.connectome.compare import REFERENCE_ALIASES

    reverse: dict[str, list[str]] = {}
    for reference, names in REFERENCE_ALIASES.items():
        for name in names:
            reverse.setdefault(name, []).append(reference)
    return reverse


def central_input(network) -> dict[tuple[str, str], float]:
    """Synapses a central cell of each target type receives from each source type.

    This is the quantity the trained synaptic strength multiplies, summed over the filter: the total drive
    one presynaptic type exerts on one postsynaptic cell, per unit of strength.
    """
    edges = network.connectome.edges
    central = set(network.connectome.central_cells_index[:].tolist())
    target = np.asarray(edges.target_index[:])
    mask = np.fromiter((t in central for t in target.tolist()), dtype=bool, count=target.size)
    totals: dict[tuple[str, str], float] = {}
    sources = np.asarray(edges.source_type[:])[mask]
    targets = np.asarray(edges.target_type[:])[mask]
    counts = np.asarray(edges.n_syn[:])[mask]
    for s, t, n in zip(sources.tolist(), targets.tolist(), counts.tolist(), strict=True):
        key = (s.decode(), t.decode())
        totals[key] = totals.get(key, 0.0) + float(n)
    return totals


def transfer(model_dir: Path, network) -> dict:
    """Replace initial values with the published model's trained ones where cell types match.

    Resting potentials and time constants are copied per matched cell type (averaged where one type here
    stands for several in the reference, as R1-R6 does for six). Synaptic strengths are copied per matched
    type pair so that the total drive onto a central cell is preserved: the reference strength is rescaled
    by the ratio of central synapse totals, because the two reconstructions count different numbers of
    synapses for the same connection and a per-synapse copy would carry that difference into the dynamics.
    Everything unmatched keeps the engine's initialisation. The report lists what moved.
    """
    import torch

    flyvis = load_engine()
    reference = flyvis.NetworkView(model_dir).init_network()
    reverse = _reverse_aliases()

    def candidates(name: str, known: set[str]) -> list[str]:
        return [r for r in reverse.get(name, [name]) if r in known]

    report: dict = {"model": str(Path(model_dir).relative_to(flyvis.results_dir)).replace("\\", "/")}
    for name in NODE_PARAMETERS:
        ref_param = reference.node_params[name]
        ref_values = dict(zip(ref_param.keys, ref_param.raw_values.detach().cpu().numpy().tolist(),
                              strict=True))
        param = network.node_params[name]
        new = param.raw_values.detach().cpu().numpy().copy()
        moved = []
        for i, key in enumerate(param.keys):
            matches = candidates(key, set(ref_values))
            if matches:
                new[i] = float(np.mean([ref_values[m] for m in matches]))
                moved.append(key)
        with torch.no_grad():
            param.raw_values.copy_(torch.as_tensor(new, dtype=param.raw_values.dtype))
        report[name] = {"transferred": len(moved), "of": len(param.keys)}

    ref_strength = reference.edge_params["syn_strength"]
    ref_values = dict(zip(ref_strength.keys, ref_strength.raw_values.detach().cpu().numpy().tolist(),
                          strict=True))
    ref_types = {t for pair in ref_values for t in pair}
    ref_total = central_input(reference)
    our_total = central_input(network)
    param = network.edge_params["syn_strength"]
    new = param.raw_values.detach().cpu().numpy().copy()
    moved = 0
    for i, (source, target) in enumerate(param.keys):
        pairs = [
            (s, t)
            for s in candidates(source, ref_types)
            for t in candidates(target, ref_types)
            if (s, t) in ref_values and ref_total.get((s, t))
        ]
        if not pairs or not our_total.get((source, target)):
            continue
        drive = float(np.mean([ref_values[p] * ref_total[p] for p in pairs]))
        new[i] = drive / our_total[(source, target)]
        moved += 1
    with torch.no_grad():
        param.raw_values.copy_(torch.as_tensor(new, dtype=param.raw_values.dtype))
    report["syn_strength"] = {"transferred": moved, "of": len(param.keys)}
    del reference
    return report


def clone_config(network) -> dict:
    """The engine configuration a network was built from, as plain data."""
    return copy.deepcopy(network.config.to_dict())
