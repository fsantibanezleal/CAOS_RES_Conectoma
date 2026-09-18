"""The whole visual system as a neuron-level network: every cell its own node, every connection its own edge.

`NeuronConnectome` gives the engine the graph written by `connectome.visual_cns`, and
`PhotoreceptorStimulus` gives it an input: one value per photoreceptor neuron, in an order exported as
`input_layout` so a fly-eye renderer can produce exactly that vector. Nothing here is periodic, so the
filters, offsets and sublattices of the lattice network do not apply; parameters are shared by cell type
(R0, R1) or held per neuron and per connection (R2), and synapse counts and signs are always per connection,
because each presynaptic neuron carries its own measured transmitter.

The network regimes are the same three as on the lattice (`regimes.py`), with neuron granularity in place
of lattice granularity. At this size the plan runs R0; the cost of R1 is measured, not assumed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from conectoma.connectome.columns import UNASSIGNED
from conectoma.connectome.malecns import RELEASE_TO_ENGINE, is_photoreceptor
from conectoma.connectome.visual_cns import READOUT_PREFIXES, SIDES
from conectoma.network.engine import load_engine
from conectoma.network.lattice import _Table
from conectoma.network.regimes import REGIMES, broadcast_parameters, transfer

REGISTERED_NAME = "NeuronConnectome"
STIMULUS_NAME = "PhotoreceptorStimulus"

PER_TYPE = ("type",)
PER_NEURON = ("type", "index")
PER_TYPE_PAIR = ("source_type", "target_type")
# The engine reads the type pair and the offset back from a synapse-count grouping, so they stay in the key;
# the two cell indices make it unique.
PER_CONNECTION = ("source_type", "target_type", "du", "dv", "source_index", "target_index")


def graph_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class NeuronConnectome:
    """A neuron-level connectome the engine accepts, loaded from the graph `visual_cns` writes.

    Column coordinates are carried into the engine's frame with the half-turn measured on the right eye.
    The left eye's frame relative to a left-eye renderer has not been measured; its coordinates are carried
    the same way and the side of every input neuron is exported, so the renderer decides per eye.
    """

    def __init__(self, file: str, digest: str | None = None):
        path = Path(file)
        actual = graph_digest(path)
        if digest is not None and digest != actual:
            raise ValueError(
                f"{path.name} does not match the graph this network was built on "
                f"(expected {digest[:12]}, found {actual[:12]})"
            )
        self.file = str(path)
        self.digest = actual
        data = np.load(path, allow_pickle=False)
        types = [str(t) for t in data["types"]]
        type_index = data["type_index"].astype(np.int64)
        side = data["side"].astype(np.int8)
        hex1 = data["hex1"].astype(np.int32)
        hex2 = data["hex2"].astype(np.int32)
        placed = hex1 != UNASSIGNED
        u = np.where(placed, RELEASE_TO_ENGINE * hex1, UNASSIGNED).astype(np.int32)
        v = np.where(placed, RELEASE_TO_ENGINE * hex2, UNASSIGNED).astype(np.int32)
        n = type_index.size

        # nodes grouped by cell type, so every type is one contiguous layer, as the engine expects
        order = np.lexsort((np.arange(n), type_index))
        rank = np.empty(n, dtype=np.int64)
        rank[order] = np.arange(n)
        type_index, side, u, v, placed = type_index[order], side[order], u[order], v[order], placed[order]
        body = data["body_id"][order]

        photoreceptor_types = [t for t in types if is_photoreceptor(t)]
        readout_types = [t for t in types if t.startswith(READOUT_PREFIXES)]
        role_of = {
            t: "input" if t in photoreceptor_types else "output" if t in readout_types else "intermediate"
            for t in types
        }
        type_bytes = np.asarray(types).astype("S")

        self.nodes = _Table(
            index=np.arange(n, dtype=np.int64),
            type=type_bytes[type_index],
            u=u,
            v=v,
            role=np.asarray([role_of[types[t]] for t in type_index.tolist()]).astype("S"),
            side=side,
            body_id=body,
        )
        starts = np.searchsorted(type_index, np.arange(len(types)))
        ends = np.searchsorted(type_index, np.arange(len(types)), side="right")
        self.nodes.layer_index = {t: np.arange(s, e, dtype=np.int64) for t, s, e in zip(types, starts, ends,
                                                                                        strict=True)}

        pre = rank[data["pre"].astype(np.int64)]
        post = rank[data["post"].astype(np.int64)]
        sign = data["sign"].astype(np.float32)[order][pre]
        same_eye = placed[pre] & placed[post] & (side[pre] == side[post])
        self.edges = _Table(
            source_index=pre,
            target_index=post,
            sign=sign,
            n_syn=data["weight"].astype(np.float32),
            source_type=self.nodes.type[pre],
            target_type=self.nodes.type[post],
            source_u=u[pre],
            target_u=u[post],
            source_v=v[pre],
            target_v=v[post],
            du=np.where(same_eye, u[post] - u[pre], 0).astype(np.int32),
            dv=np.where(same_eye, v[post] - v[pre], 0).astype(np.int32),
            n_syn_certainty=np.ones(pre.size, dtype=np.float32),
        )

        self.unique_cell_types = type_bytes
        self.input_cell_types = np.asarray(photoreceptor_types).astype("S")
        self.output_cell_types = np.asarray(readout_types).astype("S")
        self.intermediate_cell_types = np.asarray(
            [t for t in types if role_of[t] == "intermediate"]
        ).astype("S")
        self.layout = np.bytes_(
            [(t, b"retina") for t in self.input_cell_types]
            + [(t, b"intermediate") for t in self.intermediate_cell_types]
            + [(t, b"output") for t in self.output_cell_types]
        )
        self.central_cells_index = self._central_cells(types, type_index, side, u, v, placed)

        # the input vector: every placed photoreceptor, ordered by eye, column and type
        is_input = np.isin(type_index, [types.index(t) for t in photoreceptor_types]) & placed
        inputs = np.nonzero(is_input)[0]
        inputs = inputs[np.lexsort((type_index[inputs], v[inputs], u[inputs], side[inputs]))]
        self.input_index = inputs
        self.input_layout = {
            "side": [SIDES[s] if s >= 0 else "" for s in side[inputs].tolist()],
            "u": u[inputs].tolist(),
            "v": v[inputs].tolist(),
            "type": [types[t] for t in type_index[inputs].tolist()],
            "frame": "engine lattice axes (half-turn of the release frame, measured on the right eye)",
        }
        self.compile_report = {
            "nodes": int(n),
            "edges": int(pre.size),
            "input_neurons": int(inputs.size),
            "photoreceptors_without_a_column": int(
                np.sum(np.isin(type_index, [types.index(t) for t in photoreceptor_types]) & ~placed)
            ),
        }

    @staticmethod
    def _central_cells(types, type_index, side, u, v, placed) -> np.ndarray:
        """Per type, the cell nearest the centre of the right eye, or its first cell if none is placed."""
        right = placed & (side == SIDES.index("R"))
        centre_u = int(np.median(u[right])) if right.any() else 0
        centre_v = int(np.median(v[right])) if right.any() else 0
        du, dv = u - centre_u, v - centre_v
        distance = np.where(right, np.maximum.reduce([np.abs(du), np.abs(dv), np.abs(du + dv)]), 10**6)
        central = []
        for t in range(len(types)):
            members = np.nonzero(type_index == t)[0]
            central.append(int(members[np.argmin(distance[members])]))
        return np.asarray(central, dtype=np.int64)


def _stimulus_class():
    from flyvis.network.stimulus import Stimulus

    class PhotoreceptorStimulus(Stimulus):
        """Input to one group: every placed photoreceptor neuron, in the connectome's `input_layout` order."""

        def __init__(self, connectome, n_samples: int = 1, n_frames: int = 1, init_buffer: bool = True):
            self.layer_index = {
                cell_type: index[:] for cell_type, index in connectome.nodes.layer_index.items()
            }
            self.central_cells_index = dict(
                zip(
                    connectome.unique_cell_types[:].astype(str),
                    connectome.central_cells_index[:],
                    strict=True,
                )
            )
            self.input_index = np.asarray(connectome.input_index)[None, :]
            self.n_input_elements = self.input_index.shape[1]
            self.n_samples, self.n_frames, self.n_nodes = n_samples, n_frames, len(connectome.nodes.type)
            self.connectome = connectome
            if init_buffer:
                self.zero()

    PhotoreceptorStimulus.__name__ = STIMULUS_NAME
    return PhotoreceptorStimulus


def register() -> None:
    """Make both classes available to the engine under their names. Idempotent; called by `load_engine`."""
    from flyvis.connectome.connectome import AVAILABLE_CONNECTOMES, register_connectome
    from flyvis.network.stimulus import AVAILABLE_STIMULI

    if REGISTERED_NAME not in AVAILABLE_CONNECTOMES:
        register_connectome(NeuronConnectome)
    if STIMULUS_NAME not in AVAILABLE_STIMULI:
        AVAILABLE_STIMULI[STIMULUS_NAME] = _stimulus_class()


def network_config(graph_path: Path, regime: str, seed: int = 0) -> dict:
    """The engine configuration of a regime at neuron granularity."""
    chosen = REGIMES[regime]
    per_element = chosen.key == "R2"
    return {
        "connectome": {"type": REGISTERED_NAME, "file": str(graph_path), "digest": graph_digest(graph_path)},
        "dynamics": {"type": "PPNeuronIGRSynapses", "activation": {"type": "relu"}},
        "node_config": {
            "bias": {
                "type": "RestingPotential", "groupby": list(PER_NEURON if per_element else PER_TYPE),
                "initial_dist": "Normal", "mode": "sample", "requires_grad": chosen.trainable,
                "mean": 0.5, "std": 0.05, "penalize": {"activity": True}, "seed": seed,
            },
            "time_const": {
                "type": "TimeConstant", "groupby": list(PER_NEURON if per_element else PER_TYPE),
                "initial_dist": "Value", "value": 0.05, "requires_grad": chosen.trainable,
            },
        },
        "edge_config": {
            # each presynaptic neuron carries its own measured transmitter, so signs are per connection
            "sign": {"type": "SynapseSign", "initial_dist": "Value", "requires_grad": False,
                     "groupby": list(PER_CONNECTION)},
            "syn_count": {"type": "SynapseCount", "initial_dist": "Lognormal", "mode": "mean",
                          "requires_grad": False, "std": 1.0, "groupby": list(PER_CONNECTION)},
            "syn_strength": {
                "type": "SynapseCountScaling", "initial_dist": "Value", "requires_grad": chosen.trainable,
                "scale": 0.01, "clamp": "non_negative",
                "groupby": list(PER_CONNECTION if per_element else PER_TYPE_PAIR),
            },
        },
        "stimulus_config": {"type": STIMULUS_NAME, "init_buffer": False},
    }


# The loop-gain bound every neuron-level network starts from (see `gain.py`): from the engine's
# initialisation the whole visual system runs away, so its synaptic strengths are scaled by one factor until
# the spectral radius of |W| is at most this.
GAIN_TARGET = 0.9


def build_neuron_network(
    graph_path: Path, regime: str = "R0", seed: int = 0, transfer_from: Path | None = None,
    gain_target: float | None = GAIN_TARGET,
):
    """A neuron-level network of the given regime, from the same starting values as the lattice regimes.

    R0 and R1 share their grouping (per cell type and type pair), so they are built directly and the
    published values are transferred into them; only R2, which groups per neuron and per connection, is
    built from an R1 network and broadcast. At twelve million connections that avoids holding two networks.
    The gain normalisation is applied to the starting values, before any broadcast, so all regimes share it.
    """
    from conectoma.network.gain import normalise_gain

    flyvis = load_engine()
    graph_path = Path(graph_path).resolve()
    gain = None
    if regime in ("R0", "R1"):
        network = flyvis.Network(**network_config(graph_path, regime, seed))
        report = transfer(Path(transfer_from), network) if transfer_from is not None else None
        if gain_target is not None:
            gain = normalise_gain(network, gain_target)
    else:
        base = flyvis.Network(**network_config(graph_path, "R1", seed))
        report = transfer(Path(transfer_from), base) if transfer_from is not None else None
        if gain_target is not None:
            gain = normalise_gain(base, gain_target)
        network = flyvis.Network(**network_config(graph_path, regime, seed))
        broadcast_parameters(base, network)
        del base
    network.regime = regime
    network.transfer_report = report
    network.gain_report = gain
    if not REGIMES[regime].trainable:
        network.eval()
    return network
