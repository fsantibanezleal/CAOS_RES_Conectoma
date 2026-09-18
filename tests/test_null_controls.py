"""Each null control must preserve exactly what it claims to preserve, and change what it claims to change.

A control that silently keeps more of the biology than it says would make the connectome look worse than it
is; one that destroys more would make it look better. Both errors are checked here, on a synthetic
specification and, when it exists, on the connectome built from the release.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "data-pipeline"))

from conectoma.connectome.nulls import (  # noqa: E402
    NULLS_VERSION,
    degree_preserving_rewire,
    degree_sequences,
    placement_signature,
    random_sparse,
    sign_shuffle,
    total_synapses,
)

ARTIFACT = REPO_ROOT / "data/derived/connectome/malecns-optic-lobe-r.json"


def synthetic_spec(n_types: int = 12, seed: int = 3) -> dict:
    """A small type graph with mixed signs and varied filters."""
    import random

    rng = random.Random(seed)
    names = [f"T{i}" for i in range(n_types)]
    edges = []
    for source in names:
        sign = 1 if rng.random() < 0.6 else -1
        for target in rng.sample(names, 4):
            offsets = [[[0, 0], round(rng.uniform(1, 40), 3)]]
            if rng.random() < 0.5:
                offsets.append([[1, 0], round(rng.uniform(0.5, 5), 3)])
            edges.append({
                "src": source, "tar": target, "alpha": sign, "offsets": offsets,
                "alpha_fixed": True, "lambda_mult": 1.0, "edge_type": "chem",
            })
    return {
        "nodes": [{"name": n, "pattern": ["stride", [1, 1]], "activation": "relu"} for n in names],
        "edges": edges,
        "provenance": {"dataset": "synthetic"},
    }


def pair_set(spec: dict) -> set[tuple[str, str]]:
    return {(e["src"], e["tar"]) for e in spec["edges"]}


# --- N1 -------------------------------------------------------------------------------------------


def test_rewiring_preserves_every_type_degree_and_the_synapse_total() -> None:
    spec = synthetic_spec()
    control = degree_preserving_rewire(spec, seed=7)
    assert degree_sequences(control) == degree_sequences(spec)
    assert total_synapses(control) == pytest.approx(total_synapses(spec))
    assert len(pair_set(control)) == len(control["edges"])  # no duplicate connection was created


def test_rewiring_actually_changes_the_wiring() -> None:
    spec = synthetic_spec()
    control = degree_preserving_rewire(spec, seed=7)
    overlap = len(pair_set(spec) & pair_set(control)) / len(pair_set(spec))
    assert overlap < 0.5, f"rewiring left {overlap:.0%} of connections in place"
    assert control["provenance"]["null_control"]["accepted_swaps"] > 0


def test_rewired_connections_take_the_sign_of_their_source() -> None:
    spec = synthetic_spec()
    source_sign = {e["src"]: e["alpha"] for e in spec["edges"]}
    control = degree_preserving_rewire(spec, seed=7)
    for edge in control["edges"]:
        assert edge["alpha"] == source_sign[edge["src"]]


# --- N2 -------------------------------------------------------------------------------------------


def test_random_graph_matches_size_and_filter_pool() -> None:
    spec = synthetic_spec()
    control = random_sparse(spec, seed=11)
    assert len(control["edges"]) == len(spec["edges"])
    assert total_synapses(control) == pytest.approx(total_synapses(spec))
    original_filters = sorted(json.dumps(e["offsets"]) for e in spec["edges"])
    control_filters = sorted(json.dumps(e["offsets"]) for e in control["edges"])
    assert control_filters == original_filters


def test_random_graph_breaks_the_degree_structure() -> None:
    spec = synthetic_spec()
    control = random_sparse(spec, seed=11)
    # every source has out-degree four in the synthetic graph; a uniform draw will not keep that
    out_degree, _ = degree_sequences(control)
    assert set(out_degree.values()) != {4}


# --- N3 -------------------------------------------------------------------------------------------


def test_sign_shuffle_keeps_topology_filters_and_the_sign_ratio() -> None:
    spec = synthetic_spec()
    control = sign_shuffle(spec, seed=5)
    assert pair_set(control) == pair_set(spec)
    assert [e["offsets"] for e in control["edges"]] == [e["offsets"] for e in spec["edges"]]
    assert Counter(e["alpha"] for e in control["edges"]) == Counter(e["alpha"] for e in spec["edges"])
    assert control["provenance"]["null_control"]["signs_changed"] > 0


# --- size at the level of cells -------------------------------------------------------------------


def mixed_spec(seed: int = 4) -> dict:
    """Types on three placements, so a careless control would change the cell-level size."""
    import random

    rng = random.Random(seed)
    patterns = {f"A{i}": ["stride", [1, 1]] for i in range(6)}
    patterns.update({f"B{i}": ["stride", [2, 2]] for i in range(5)})
    patterns.update({f"P{i}": ["single", None] for i in range(4)})
    names = list(patterns)
    edges = []
    for source in names:
        for target in rng.sample(names, 5):
            n = round(rng.uniform(1, 20), 2)
            offsets = [[[0, 0], n]] if patterns[source][0] == "single" else [[[0, 0], n], [[1, -1], 1.5]]
            edges.append({
                "src": source, "tar": target, "alpha": 1 if source < "B" else -1, "offsets": offsets,
                "lambda_mult": 1.0, "edge_type": "chem",
            })
    return {"nodes": [{"name": n, "pattern": p, "activation": "relu"} for n, p in patterns.items()],
            "edges": edges, "provenance": {}}


@pytest.mark.parametrize("control", [degree_preserving_rewire, random_sparse, sign_shuffle])
def test_every_control_keeps_the_placement_signature_that_decides_its_cell_level_size(control) -> None:
    spec = mixed_spec()
    result = control(spec, seed=3)
    assert placement_signature(result) == placement_signature(spec)
    assert result["provenance"]["null_control"]["version"] == NULLS_VERSION


def test_rewiring_on_mixed_placements_still_rewires_and_keeps_degrees() -> None:
    spec = mixed_spec()
    control = degree_preserving_rewire(spec, seed=3)
    assert degree_sequences(control) == degree_sequences(spec)
    assert control["provenance"]["null_control"]["accepted_swaps"] > 0
    overlap = len(pair_set(spec) & pair_set(control)) / len(pair_set(spec))
    assert overlap < 0.7


# --- determinism ----------------------------------------------------------------------------------


@pytest.mark.parametrize("control", [degree_preserving_rewire, random_sparse, sign_shuffle])
def test_a_control_is_a_pure_function_of_the_seed(control) -> None:
    spec = synthetic_spec()
    assert control(spec, seed=21)["edges"] == control(spec, seed=21)["edges"]
    assert control(spec, seed=21)["edges"] != control(spec, seed=22)["edges"]


@pytest.mark.parametrize("control", [degree_preserving_rewire, random_sparse, sign_shuffle])
def test_a_control_never_mutates_the_measured_connectome(control) -> None:
    spec = synthetic_spec()
    before = json.dumps(spec, sort_keys=True)
    control(spec, seed=1)
    assert json.dumps(spec, sort_keys=True) == before


# --- on the real connectome -----------------------------------------------------------------------


@pytest.mark.skipif(not ARTIFACT.is_file(), reason="connectome artifact not built")
def test_controls_hold_their_invariants_on_the_measured_connectome() -> None:
    spec = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    rewired = degree_preserving_rewire(spec, seed=0)
    assert degree_sequences(rewired) == degree_sequences(spec)
    assert total_synapses(rewired) == pytest.approx(total_synapses(spec))
    shuffled = sign_shuffle(spec, seed=0)
    assert pair_set(shuffled) == pair_set(spec)
    random_graph = random_sparse(spec, seed=0)
    assert len(random_graph["edges"]) == len(spec["edges"])
