"""The network the connectome becomes: compiler, regimes, and the published model it must reproduce.

The compiler is checked against the engine's own on the published connectome (every table identical), and
on small synthetic connectomes for the two rules the engine does not have: every target cell receives its
full measured filter whatever the strides, and a population node reaches every cell of its targets. The
regimes are checked for what they promise: which parameters train, that gradients respect it through the
dynamics, and that all three start from the same values. When the published ensemble is present locally,
the published model is rebuilt through this product's path and compared voltage for voltage.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "data-pipeline"))

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("flyvis") is None, reason="network engine not installed (offline lane)"
)


def engine():
    from conectoma.network.engine import load_engine

    return load_engine()


def synthetic_spec(path: Path, compile_rules: bool = True) -> Path:
    """Five types on four placements, with filters whose totals are easy to check."""
    nodes = [
        {"name": "R1", "pattern": ["stride", [1, 1]]},
        {"name": "L1", "pattern": ["stride", [1, 1]]},
        {"name": "Mi", "pattern": ["stride", [2, 2]]},
        {"name": "Dm", "pattern": ["stride", [3, 3]]},
        {"name": "Pop", "pattern": ["single", None]},
        {"name": "T4a", "pattern": ["stride", [1, 1]]},
    ]
    for node in nodes:
        node["activation"] = "relu"

    def edge(src: str, tar: str, alpha: int, offsets: list) -> dict:
        return {"src": src, "tar": tar, "alpha": alpha, "offsets": offsets, "lambda_mult": 1.0,
                "alpha_fixed": True, "edge_type": "chem"}

    spec = {
        "nodes": nodes,
        "edges": [
            edge("R1", "L1", -1, [[[0, 0], 30.0]]),
            edge("L1", "Mi", 1, [[[0, 0], 5.0], [[1, 0], 2.0], [[0, 1], 1.5]]),
            edge("Mi", "Dm", 1, [[[0, 0], 3.0], [[1, -1], 2.0]]),        # 2x2 onto 3x3: few offsets meet
            edge("Mi", "T4a", 1, [[[0, 0], 4.0], [[1, 0], 1.0], [[-1, 1], 0.5]]),
            edge("Dm", "T4a", -1, [[[0, 0], 2.0], [[1, 1], 1.0]]),
            edge("L1", "Pop", 1, [[[0, 0], 1.0], [[2, 0], 1.0]]),
            edge("Pop", "T4a", -1, [[[0, 0], 6.0]]),
            edge("Pop", "Pop", 1, [[[0, 0], 2.0]]),
        ],
        "input_units": ["R1"],
        "output_units": ["T4a"],
    }
    if compile_rules:
        spec["compile"] = {"population_broadcast": True, "target_centric": True}
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def hex_distance(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.maximum.reduce([np.abs(u), np.abs(v), np.abs(u + v)])


# --- compiler -------------------------------------------------------------------------------------


def test_compiler_matches_the_engine_on_the_published_connectome() -> None:
    flyvis = engine()
    from flyvis.connectome.connectome import ConnectomeFromAvgFilters

    from conectoma.network.lattice import LatticeConnectome

    reference = ConnectomeFromAvgFilters(file=str(flyvis.connectome_file), extent=6, n_syn_fill=1)
    ours = LatticeConnectome(file=str(flyvis.connectome_file), extent=6, n_syn_fill=1)
    for key in ("index", "type", "u", "v", "role"):
        assert np.array_equal(reference.nodes[key][:], ours.nodes[key]), key
    for key in reference.edges.keys():
        assert np.array_equal(reference.edges[key][:], ours.edges[key]), key
    assert np.array_equal(reference.central_cells_index[:], ours.central_cells_index)
    assert np.array_equal(reference.layout[:], ours.layout)
    # The engine's own expansion drops one published connection: Lawf1 sits on a 3-by-2 sublattice and
    # its self-connection has a single entry at offset (1, 0), which no two Lawf1 cells are apart by. The
    # published model was trained on the graph without it; the report makes the loss visible.
    assert ours.compile_report["connections_unrealised"] == [["Lawf1", "Lawf1"]]


def test_every_target_cell_receives_its_full_filter(tmp_path: Path) -> None:
    engine()
    from conectoma.network.lattice import LatticeConnectome

    extent = 8
    connectome = LatticeConnectome(file=str(synthetic_spec(tmp_path / "s.json")), extent=extent)
    edges, nodes = connectome.edges, connectome.nodes
    spec = json.loads((tmp_path / "s.json").read_text())
    for edge in spec["edges"]:
        if edge["src"] == "Pop":
            continue
        total = sum(n for _, n in edge["offsets"])
        mask = (edges.source_type == edge["src"].encode()) & (edges.target_type == edge["tar"].encode())
        received = np.bincount(edges.target_index[mask], weights=edges.n_syn[mask], minlength=nodes.u.size)
        targets = nodes.layer_index[edge["tar"]]
        inner = targets[hex_distance(nodes.u[targets], nodes.v[targets]) <= extent - 4]
        assert inner.size > 0
        assert np.allclose(received[inner], total), (edge["src"], edge["tar"])


def test_source_centric_expansion_loses_entries_between_sublattices(tmp_path: Path) -> None:
    """The engine's own rule, kept for the published connectome, is wrong for sublattices: shown here."""
    engine()
    from conectoma.network.lattice import LatticeConnectome

    plain = LatticeConnectome(file=str(synthetic_spec(tmp_path / "p.json", compile_rules=False)), extent=8)
    mask = (plain.edges.source_type == b"Mi") & (plain.edges.target_type == b"Dm")
    received = np.bincount(plain.edges.target_index[mask], weights=plain.edges.n_syn[mask],
                           minlength=plain.nodes.u.size)
    targets = plain.nodes.layer_index["Dm"]
    assert (received[targets] < 5.0).any()  # the filter total is 5; some targets get less or nothing


def test_a_population_node_reaches_every_cell_of_its_targets(tmp_path: Path) -> None:
    engine()
    from conectoma.network.lattice import LatticeConnectome

    connectome = LatticeConnectome(file=str(synthetic_spec(tmp_path / "s.json")), extent=5)
    edges, nodes = connectome.edges, connectome.nodes
    population = int(nodes.layer_index["Pop"][0])
    to_t4 = (edges.source_index == population) & (edges.target_type == b"T4a")
    assert np.array_equal(np.sort(edges.target_index[to_t4]), nodes.layer_index["T4a"])
    assert np.all(edges.n_syn[to_t4] == 6.0)
    self_loop = (edges.source_index == population) & (edges.target_index == population)
    assert self_loop.sum() == 1 and edges.n_syn[self_loop][0] == 2.0


def test_a_changed_specification_is_refused_by_a_network_bound_to_the_old_one(tmp_path: Path) -> None:
    engine()
    from conectoma.network.lattice import LatticeConnectome, spec_digest

    path = synthetic_spec(tmp_path / "s.json")
    digest = spec_digest(path)
    LatticeConnectome(file=str(path), extent=3, digest=digest)
    path.write_text(path.read_text().replace("30.0", "31.0"))
    with pytest.raises(ValueError, match="does not match"):
        LatticeConnectome(file=str(path), extent=3, digest=digest)


def test_vectorised_grouping_equals_the_engine() -> None:
    engine()
    import pandas as pd
    import torch
    from flyvis.network import initialization

    from conectoma.network.engine import vectorised_scatter_indices

    rng = np.random.default_rng(0)
    frame = pd.DataFrame({
        "source_type": rng.choice(["L1", "Mi1", "T4a"], 500),
        "target_type": rng.choice(["Tm3", "T4a"], 500),
        "du": rng.integers(-2, 3, 500),
        "dv": rng.integers(-2, 3, 500),
        "n_syn": rng.random(500),
    })
    for groupby in (["source_type", "target_type"], ["source_type", "target_type", "du", "dv"]):
        grouped = frame.groupby(groupby, as_index=False, sort=False).mean()
        expected = initialization.reference_scatter_indices(frame, grouped, groupby)
        assert torch.equal(expected.cpu(), vectorised_scatter_indices(frame, grouped, groupby).cpu())


# --- regimes --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def networks(tmp_path_factory):
    engine()
    from conectoma.network.regimes import build_network

    path = synthetic_spec(tmp_path_factory.mktemp("spec") / "s.json")
    return {regime: build_network(path, regime, extent=4) for regime in ("R0", "R1", "R2")}


def test_regimes_train_exactly_what_they_claim(networks) -> None:
    from conectoma.network.regimes import trainable_report

    r1 = networks["R1"]
    n_types = len(r1.connectome.unique_cell_types)
    n_pairs = len({(s, t) for s, t in zip(r1.connectome.edges.source_type, r1.connectome.edges.target_type,
                                           strict=True)})
    assert trainable_report(networks["R0"])["trainable"] == 0
    assert trainable_report(r1)["trainable"] == 2 * n_types + n_pairs
    assert trainable_report(networks["R2"])["trainable"] == 2 * r1.n_nodes + r1.n_edges
    for network in networks.values():
        rows = trainable_report(network)["parameters"]
        assert not rows["edges_sign"]["trainable"]
        assert not rows["edges_syn_count"]["trainable"]


def test_gradients_respect_the_regime(networks) -> None:
    from conectoma.network.regimes import gradient_check

    for regime, network in networks.items():
        check = gradient_check(network)
        assert check["violations"] == [], regime
        assert check["input_gradient"], regime  # the graph existed, so "no gradient" means frozen


def test_all_regimes_start_from_the_same_values(networks) -> None:
    from conectoma.network.regimes import element_values

    for name in ("bias", "time_const", "syn_strength"):
        reference = element_values(networks["R1"], name)
        for regime in ("R0", "R2"):
            assert np.allclose(element_values(networks[regime], name), reference), (regime, name)


def test_a_coarser_target_is_refused(networks) -> None:
    """Copying per-neuron values into per-type groups would lose them once neurons of a type differ."""
    import torch

    from conectoma.network.regimes import broadcast_parameters

    bias = networks["R2"].node_params["bias"].raw_values
    original = bias.detach().clone()
    try:
        with torch.no_grad():
            bias[0] += 1.0  # one neuron now differs from the rest of its type
        with pytest.raises(ValueError, match="coarsely"):
            broadcast_parameters(networks["R2"], networks["R1"], names=("bias",))
    finally:
        with torch.no_grad():
            bias.copy_(original)


def test_the_network_records_the_graph_it_was_built_on(networks) -> None:
    config = networks["R1"].config.to_dict()["connectome"]
    assert config["type"] == "LatticeConnectome"
    assert len(config["digest"]) == 64


# --- the published model --------------------------------------------------------------------------


def published_available() -> bool:
    try:
        from conectoma.network.engine import published_model_dir

        published_model_dir("000")
        return True
    except (FileNotFoundError, ImportError):
        return False


@pytest.mark.skipif(not published_available(), reason="published ensemble not downloaded")
def test_the_published_model_rebuilt_here_matches_the_engine_voltage_for_voltage() -> None:
    from conectoma.network.parity import VOLTAGE_TOLERANCE, voltage_parity

    result = voltage_parity("000", samples=(17,))
    assert result["max_abs_difference"] <= VOLTAGE_TOLERANCE
    assert result["cells"] == 45669


PARITY = REPO_ROOT / "data/derived/network/parity-published.json"


@pytest.mark.skipif(not PARITY.is_file(), reason="parity report not produced yet")
def test_the_committed_parity_report_passes() -> None:
    report = json.loads(PARITY.read_text(encoding="utf-8"))
    assert all(v["passed"] for v in report["voltage_parity"])
    assert len(report["tuning"]["models"]) == 50
