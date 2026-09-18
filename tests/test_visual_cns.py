"""The whole visual system as a neuron-level network: selection, graph, engine class, stimulus, regimes.

Everything runs on small synthetic tables and graphs whose right answers are known by construction. The
real graph is built by `run.py build-visual-cns` and measured by `characterize-visual-cns`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "data-pipeline"))

from conectoma.connectome.columns import UNASSIGNED  # noqa: E402
from conectoma.connectome.visual_cns import (  # noqa: E402
    SUPERCLASSES,
    select_visual_system,
    write_graph,
)

requires_engine = pytest.mark.skipif(
    importlib.util.find_spec("flyvis") is None, reason="network engine not installed (offline lane)"
)


def _annotations(tmp_path: Path) -> Path:
    rows = [
        # body, type, superclass, somaSide, instance, hex1, hex2
        (10, "L1", "ol_intrinsic", "R", "L1_R", 0, 0),
        (11, "L1", "ol_intrinsic", "L", "L1_L", 0, 0),
        (12, "R7p", "ol_sensory", None, "R7p_R", None, None),
        (13, "R7R8_unclear", "ol_sensory", None, "R7R8_unclear_R", None, None),
        (14, "LC4", "visual_projection", "R", "LC4_R", None, None),
        (15, "LT1", "visual_projection", None, "LT1", None, None),   # side unresolved: kept, flagged
        (16, "DNa01", "descending_neuron", "R", "DNa01_R", None, None),
        (17, None, "ol_intrinsic", "R", "", None, None),
    ]
    columns = list(zip(*rows, strict=True))
    table = pa.table({
        "bodyId": pa.array(columns[0], pa.int64()),
        "type": pa.array(columns[1]),
        "class": pa.array(["x"] * len(rows)),
        "superclass": pa.array(columns[2]),
        "somaSide": pa.array(columns[3]),
        "instance": pa.array(columns[4]),
        "assignedOlHex1": pa.array(columns[5], pa.int64()),
        "assignedOlHex2": pa.array(columns[6], pa.int64()),
    })
    path = tmp_path / "annotations.feather"
    feather.write_feather(table, path)
    return path


def test_selection_keeps_both_sides_and_the_projection_neurons(tmp_path: Path) -> None:
    selection = select_visual_system(_annotations(tmp_path))
    assert selection.body_ids.tolist() == [10, 11, 12, 14, 15]
    assert selection.types == ["L1", "LC4", "LT1", "R7"]
    assert selection.side.tolist() == [1, 0, 1, 1, -1]
    assert [SUPERCLASSES[i] for i in selection.superclass_index] == [
        "ol_intrinsic", "ol_intrinsic", "ol_sensory", "visual_projection", "visual_projection",
    ]
    report = selection.report
    assert report.rejected["ambiguous_type"] == 1
    assert report.rejected["other_superclass"] == 1
    assert report.rejected["no_cell_type"] == 1
    assert report.flagged["side_unresolved"] == 1
    assert report.flagged["pooled_spectral_subtype"] == 1


def synthetic_graph(path: Path) -> Path:
    """Two eyes of three columns, photoreceptors to L1 to an LC readout, plus one unplaced photoreceptor."""
    types = np.asarray(["L1", "LC4", "R1-R6"])
    #        body  type side  hex1  hex2
    cells = [
        (1, 2, 1, 0, 0), (2, 2, 1, 1, 0), (3, 2, 1, 0, 1),      # right photoreceptors
        (4, 2, 0, 0, 0), (5, 2, 0, 1, 0),                       # left photoreceptors
        (6, 2, 1, UNASSIGNED, UNASSIGNED),                      # a photoreceptor without a column
        (7, 0, 1, 0, 0), (8, 0, 1, 1, 0), (9, 0, 1, 0, 1),      # right L1
        (10, 0, 0, 0, 0), (11, 0, 0, 1, 0),                     # left L1
        (12, 1, 1, UNASSIGNED, UNASSIGNED),                     # LC4 readout, no column
    ]
    body, type_index, side, hex1, hex2 = (np.asarray(c) for c in zip(*cells, strict=True))
    pre = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]
    post = [6, 7, 8, 9, 10, 11, 11, 11, 11, 11]
    weight = [30, 30, 30, 30, 30, 5, 5, 5, 2, 2]
    sign = np.where(type_index == 2, -1, 1)  # photoreceptors are histaminergic, inhibitory
    arrays = {
        "body_id": body.astype(np.int64), "type_index": type_index.astype(np.int32), "types": types,
        "side": side.astype(np.int8), "superclass_index": np.zeros(body.size, dtype=np.int8),
        "superclasses": np.asarray(SUPERCLASSES),
        "hex1": hex1.astype(np.int16), "hex2": hex2.astype(np.int16),
        "sign": sign.astype(np.int8), "low_confidence_sign": np.zeros(body.size, dtype=bool),
        "pre": np.asarray(pre, dtype=np.int32), "post": np.asarray(post, dtype=np.int32),
        "weight": np.asarray(weight, dtype=np.int32),
    }
    write_graph(arrays, path)
    return path


def test_the_graph_digest_is_the_file_digest(tmp_path: Path) -> None:
    import hashlib

    path = synthetic_graph(tmp_path / "g.npz")
    arrays = dict(np.load(path))
    digest = write_graph(arrays, tmp_path / "again.npz")
    assert digest == hashlib.sha256((tmp_path / "again.npz").read_bytes()).hexdigest()


@requires_engine
def test_the_engine_class_groups_cells_by_type_and_keeps_every_connection(tmp_path: Path) -> None:
    from conectoma.network.engine import load_engine
    from conectoma.network.neurons import NeuronConnectome

    load_engine()
    connectome = NeuronConnectome(str(synthetic_graph(tmp_path / "g.npz")))
    types = np.asarray(connectome.nodes.type).astype(str)
    assert types.tolist() == ["L1"] * 5 + ["LC4"] + ["R1-R6"] * 6
    for name, index in connectome.nodes.layer_index.items():
        assert set(types[index]) == {name}
    edges = connectome.edges
    assert edges.source_index.size == 10
    # every photoreceptor connection is inhibitory, every L1 connection excitatory
    source_types = np.asarray(edges.source_type).astype(str)
    assert set(edges.sign[source_types == "R1-R6"]) == {-1.0}
    assert set(edges.sign[source_types == "L1"]) == {1.0}
    # the readout receives from all five L1 cells with the measured counts
    readout = connectome.nodes.layer_index["LC4"][0]
    assert sorted(edges.n_syn[edges.target_index == readout].tolist()) == [2, 2, 5, 5, 5]
    assert connectome.compile_report["input_neurons"] == 5
    assert connectome.compile_report["photoreceptors_without_a_column"] == 1


@requires_engine
def test_the_input_layout_orders_by_eye_then_column_in_the_engine_frame(tmp_path: Path) -> None:
    from conectoma.network.engine import load_engine
    from conectoma.network.neurons import NeuronConnectome

    load_engine()
    connectome = NeuronConnectome(str(synthetic_graph(tmp_path / "g.npz")))
    layout = connectome.input_layout
    assert layout["side"] == ["L", "L", "R", "R", "R"]
    # engine frame: the release's (1, 0) is (-1, 0)
    assert list(zip(layout["u"], layout["v"], strict=True))[:2] == [(-1, 0), (0, 0)]


@requires_engine
def test_a_changed_graph_is_refused(tmp_path: Path) -> None:
    from conectoma.network.engine import load_engine
    from conectoma.network.neurons import NeuronConnectome, graph_digest

    load_engine()
    path = synthetic_graph(tmp_path / "g.npz")
    digest = graph_digest(path)
    synthetic_graph(tmp_path / "other.npz")
    arrays = dict(np.load(tmp_path / "other.npz"))
    arrays["weight"] = arrays["weight"] + 1
    write_graph(arrays, path)
    with pytest.raises(ValueError, match="does not match"):
        NeuronConnectome(str(path), digest=digest)


@pytest.fixture(scope="module")
def neuron_networks(tmp_path_factory):
    if importlib.util.find_spec("flyvis") is None:
        pytest.skip("network engine not installed (offline lane)")
    from conectoma.network.neurons import build_neuron_network

    path = synthetic_graph(tmp_path_factory.mktemp("graph") / "g.npz")
    return {regime: build_neuron_network(path, regime) for regime in ("R0", "R1", "R2")}


def test_neuron_regimes_train_exactly_what_they_claim(neuron_networks) -> None:
    from conectoma.network.regimes import gradient_check, trainable_report

    r1 = neuron_networks["R1"]
    pairs = {(s, t) for s, t in zip(r1.connectome.edges.source_type, r1.connectome.edges.target_type,
                                    strict=True)}
    assert trainable_report(neuron_networks["R0"])["trainable"] == 0
    assert trainable_report(r1)["trainable"] == 2 * 3 + len(pairs)
    assert trainable_report(neuron_networks["R2"])["trainable"] == 2 * r1.n_nodes + r1.n_edges
    for regime, network in neuron_networks.items():
        check = gradient_check(network)
        assert check["violations"] == [], regime
        assert check["input_gradient"], regime


def test_a_flash_on_the_eyes_reaches_the_readout(neuron_networks) -> None:
    from conectoma.network.visual_cns_character import flash_response

    response = flash_response(neuron_networks["R0"])
    assert response["by_role"]["input"]["responding_fraction"] > 0.5
    assert response["by_role"]["output"]["responding_fraction"] == 1.0
