"""Null controls: connectomes that keep one property of the measured wiring and destroy the rest.

A claim that "the connectome helps" is only falsifiable against networks that share its size, sparsity and
statistics but not its biology. Without them, an advantage could come from having a sparse recurrent graph
of the right size, from the balance of excitation and inhibition, or from the filter shapes, and nothing
could tell those apart. Each control here removes exactly one of those explanations:

- **degree-preserving rewiring (N1).** Every cell type keeps its number of incoming and outgoing type-level
  connections and every connection keeps its filter; only who connects to whom is scrambled. What survives
  is the degree sequence; what is destroyed is the specific wiring.
- **size-matched random graph (N2).** The same connections with the same filters, each placed between a
  source and a target drawn at random. What survives is the size and the filter statistics; what is
  destroyed is the degree structure as well.
- **sign shuffle (N3).** The wiring and the filters are untouched; the signs are permuted across
  connections. What survives is the topology and the excitation-to-inhibition ratio; what is destroyed is
  which connections are inhibitory.

Size is matched where the network is simulated, at the level of cells, not only at the level of types.
Cell types sit on lattices of different densities (every column, a sublattice, or one population node), so a
filter moved onto a denser target type expands into more cell connections: an unconstrained rewiring of the
measured connectome produced a control with 6.85 million connections and 3.3 times the synapses of the
original 2.92 million. Both N1 and N2 therefore move a connection only between types of the same placement
(`placement_class`): a connection's source placement, target placement and filter decide how many cell
connections it becomes, so the controls have exactly the cell-level size and synapse total of the measured
connectome.

The same precedent appears in the robot-navigation work that trained a network on the full fly brain: its
matched random graph is the reason its out-of-distribution result can be read at all.

Every control is a pure function of the measured specification and a seed, so the same seed always gives
the same control, and different seeds give the spread a result is compared against. `NULLS_VERSION` names
the algorithm; control files and run-log steps carry it, so a control drawn by an earlier algorithm is never
reused.
"""

from __future__ import annotations

import copy
import json
import random
from collections import Counter, defaultdict

NULLS_VERSION = 2

# A rewiring swap is attempted this many times per connection; the acceptance rate is reported, so a graph
# too dense to mix is visible rather than silently returned almost unchanged.
SWAPS_PER_EDGE = 10


def placement_class(spec: dict) -> dict[str, str]:
    """The placement of every cell type, as a comparable key."""
    return {node["name"]: json.dumps(node.get("pattern")) for node in spec["nodes"]}


def _source_sign(spec: dict) -> dict[str, int]:
    """The sign of each cell type, which travels with the presynaptic type after any rewiring.

    A neuron releases the same transmitter onto every target, so a rewired connection takes the sign of its
    new source rather than keeping the sign of the connection it replaced.
    """
    signs: dict[str, list[int]] = {}
    for edge in spec["edges"]:
        signs.setdefault(edge["src"], []).append(edge["alpha"])
    return {cell_type: (1 if sum(values) >= 0 else -1) for cell_type, values in signs.items()}


def _with_edges(spec: dict, edges: list[dict], kind: str, seed: int, details: dict) -> dict:
    control = copy.deepcopy({key: value for key, value in spec.items() if key != "edges"})
    control["edges"] = edges
    provenance = dict(control.get("provenance", {}))
    provenance["null_control"] = {"kind": kind, "seed": seed, "version": NULLS_VERSION, **details}
    control["provenance"] = provenance
    return control


def degree_preserving_rewire(spec: dict, seed: int) -> dict:
    """N1: scramble who connects to whom while keeping every type's in- and out-degree.

    Double-edge swaps: pick two connections (a to b) and (c to d) whose targets share a placement, and
    replace them with (a to d) and (c to b) when neither exists yet. Each connection keeps its source and its
    filter, so its sign is unchanged and it expands into the same cell connections.
    """
    rng = random.Random(seed)
    placement = placement_class(spec)
    edges = [dict(edge) for edge in spec["edges"]]
    pairs = {(edge["src"], edge["tar"]) for edge in edges}
    by_class: dict[str, list[int]] = defaultdict(list)
    for index, edge in enumerate(edges):
        by_class[placement[edge["tar"]]].append(index)
    pools = [members for members in by_class.values() if len(members) > 1]
    weights = [len(members) for members in pools]
    attempts = SWAPS_PER_EDGE * len(edges)
    accepted = 0

    for _ in range(attempts if pools else 0):
        members = rng.choices(pools, weights=weights)[0]
        i, j = rng.sample(members, 2)
        a, b = edges[i]["src"], edges[i]["tar"]
        c, d = edges[j]["src"], edges[j]["tar"]
        if a == c or b == d:
            continue
        if (a, d) in pairs or (c, b) in pairs:
            continue
        pairs.discard((a, b))
        pairs.discard((c, d))
        pairs.add((a, d))
        pairs.add((c, b))
        edges[i]["tar"], edges[j]["tar"] = d, b
        accepted += 1

    return _with_edges(
        spec, edges, "degree_preserving_rewire", seed,
        {"attempted_swaps": attempts, "accepted_swaps": accepted, "stratified_by": "target placement"},
    )


def random_sparse(spec: dict, seed: int) -> dict:
    """N2: every measured connection, with its filter, moved to a random source and target of its placements.

    Each connection is redrawn between a source type with the placement of its original source and a target
    type with the placement of its original target, without repeating a pair; its filter and certainty go
    with it and its sign follows the new source. The filter pool, the placement mix and therefore the
    cell-level size are exactly the measured ones; the degree structure is not.
    """
    rng = random.Random(seed)
    placement = placement_class(spec)
    types_by_class: dict[str, list[str]] = defaultdict(list)
    for node in spec["nodes"]:
        types_by_class[placement[node["name"]]].append(node["name"])
    signs = _source_sign(spec)

    order = list(range(len(spec["edges"])))
    rng.shuffle(order)
    chosen: set[tuple[str, str]] = set()
    used: Counter = Counter()
    edges: list[dict | None] = [None] * len(spec["edges"])
    for index in order:
        original = spec["edges"][index]
        key = (placement[original["src"]], placement[original["tar"]])
        sources, targets = types_by_class[key[0]], types_by_class[key[1]]
        if used[key] >= len(sources) * len(targets):
            raise ValueError("more connections than type pairs in a placement class")
        used[key] += 1
        while True:
            pair = (rng.choice(sources), rng.choice(targets))
            if pair not in chosen:
                break
        chosen.add(pair)
        edge = copy.deepcopy(original)
        edge.update({"src": pair[0], "tar": pair[1], "alpha": signs.get(pair[0], 1)})
        edges[index] = edge

    return _with_edges(
        spec, edges, "random_sparse", seed,
        {"connections": len(edges), "stratified_by": "source and target placement"},
    )


def sign_shuffle(spec: dict, seed: int) -> dict:
    """N3: keep every connection and filter, permute the signs across connections."""
    rng = random.Random(seed)
    edges = [dict(edge) for edge in spec["edges"]]
    alphas = [edge["alpha"] for edge in edges]
    rng.shuffle(alphas)
    changed = 0
    for edge, alpha in zip(edges, alphas, strict=True):
        changed += int(edge["alpha"] != alpha)
        edge["alpha"] = alpha
    return _with_edges(spec, edges, "sign_shuffle", seed, {"signs_changed": changed})


CONTROLS = {
    "N1": degree_preserving_rewire,
    "N2": random_sparse,
    "N3": sign_shuffle,
}


def degree_sequences(spec: dict) -> tuple[Counter, Counter]:
    """Type-level out- and in-degree, which N1 must leave unchanged."""
    out_degree: Counter = Counter()
    in_degree: Counter = Counter()
    for edge in spec["edges"]:
        out_degree[edge["src"]] += 1
        in_degree[edge["tar"]] += 1
    return out_degree, in_degree


def total_synapses(spec: dict) -> float:
    """Sum of all filter entries, which N1 and N2 must leave unchanged."""
    return sum(count for edge in spec["edges"] for _, count in edge["offsets"])


def placement_signature(spec: dict) -> Counter:
    """Each connection as (source placement, target placement, filter): what decides its cell-level size."""
    placement = placement_class(spec)
    return Counter(
        (placement[edge["src"]], placement[edge["tar"]], json.dumps(edge["offsets"]))
        for edge in spec["edges"]
    )
