"""Null controls: connectomes that keep one property of the measured wiring and destroy the rest.

A claim that "the connectome helps" is only falsifiable against networks that share its size, sparsity and
statistics but not its biology. Without them, an advantage could come from having a sparse recurrent graph
of the right size, from the balance of excitation and inhibition, or from the filter shapes, and nothing
could tell those apart. Each control here removes exactly one of those explanations:

- **degree-preserving rewiring (N1).** Every cell type keeps its number of incoming and outgoing type-level
  connections and every connection keeps its filter; only who connects to whom is scrambled. What survives
  is the degree sequence; what is destroyed is the specific wiring.
- **size-matched random graph (N2).** The same number of type-level connections, drawn uniformly over type
  pairs, with filters drawn from the measured pool. What survives is the size and the filter statistics;
  what is destroyed is the degree structure as well.
- **sign shuffle (N3).** The wiring and the filters are untouched; the signs are permuted across
  connections. What survives is the topology and the excitation-to-inhibition ratio; what is destroyed is
  which connections are inhibitory.

The same precedent appears in the robot-navigation work that trained a network on the full fly brain: its
matched random graph is the reason its out-of-distribution result can be read at all.

Every control is a pure function of the measured specification and a seed, so the same seed always gives
the same control, and different seeds give the spread a result is compared against.
"""

from __future__ import annotations

import copy
import random
from collections import Counter

# A rewiring swap is attempted this many times per connection; the acceptance rate is reported, so a graph
# too dense to mix is visible rather than silently returned almost unchanged.
SWAPS_PER_EDGE = 10


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
    provenance["null_control"] = {"kind": kind, "seed": seed, **details}
    control["provenance"] = provenance
    return control


def degree_preserving_rewire(spec: dict, seed: int) -> dict:
    """N1: scramble who connects to whom while keeping every type's in- and out-degree.

    Double-edge swaps: pick two connections (a to b) and (c to d), and replace them with (a to d) and
    (c to b) when neither exists yet and neither is a self-connection that was not there before. Each
    connection keeps its filter; its sign follows its new source.
    """
    rng = random.Random(seed)
    edges = [dict(edge) for edge in spec["edges"]]
    pairs = {(edge["src"], edge["tar"]) for edge in edges}
    attempts = SWAPS_PER_EDGE * len(edges)
    accepted = 0

    for _ in range(attempts):
        i, j = rng.randrange(len(edges)), rng.randrange(len(edges))
        if i == j:
            continue
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

    signs = _source_sign(spec)
    for edge in edges:
        edge["alpha"] = signs.get(edge["src"], edge["alpha"])

    return _with_edges(
        spec, edges, "degree_preserving_rewire", seed,
        {"attempted_swaps": attempts, "accepted_swaps": accepted},
    )


def random_sparse(spec: dict, seed: int) -> dict:
    """N2: the same number of connections between uniformly drawn type pairs, with measured filters.

    Filters are drawn without replacement from the measured pool, so the distribution of filter shapes and
    synapse counts is exactly the measured one; only their placement is random.
    """
    rng = random.Random(seed)
    types = [node["name"] for node in spec["nodes"]]
    filters = [edge["offsets"] for edge in spec["edges"]]
    certainties = [edge.get("lambda_mult", 1.0) for edge in spec["edges"]]
    order = list(range(len(filters)))
    rng.shuffle(order)

    chosen: set[tuple[str, str]] = set()
    total_pairs = len(types) * len(types)
    if len(filters) > total_pairs:
        raise ValueError("more connections than type pairs; a random graph of this size cannot exist")
    while len(chosen) < len(filters):
        chosen.add((rng.choice(types), rng.choice(types)))

    signs = _source_sign(spec)
    template = spec["edges"][0]
    edges = []
    for (source, target), index in zip(sorted(chosen), order, strict=True):
        edge = {key: value for key, value in template.items()}
        edge.update({
            "src": source,
            "tar": target,
            "offsets": copy.deepcopy(filters[index]),
            "alpha": signs.get(source, 1),
            "lambda_mult": certainties[index],
        })
        edges.append(edge)

    return _with_edges(spec, edges, "random_sparse", seed, {"connections": len(edges)})


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
