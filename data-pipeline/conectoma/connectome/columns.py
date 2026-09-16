"""Retinotopic column assignment for optic-lobe neurons the release does not annotate.

The MaleCNS release carries `assignedOlHex1` and `assignedOlHex2` for 23,720 neurons, which is the classic
columnar set of the lamina and medulla (L1 to L5, C2, C3, T1, Mi1, Mi4, Mi9, Tm1, Tm2, Tm4, Tm9, Tm20). The
optic lobe holds 282 cell types, so most of the visual system, including the direction-selective T4 and T5
populations, has no column coordinate in the table. A consensus connectome needs one for every columnar
neuron, because a filter is defined by the offset between the column of the source and the column of the
target.

This module infers the missing coordinate from connectivity: a neuron sits in the column its partners sit
in. The coordinate of an unplaced neuron is the synapse-weighted median of the coordinates of its placed
partners, repeated for a few rounds so a neuron two steps from the annotated set can still be placed.

A median is used rather than a mean because an arbor that reaches a few distant columns should not drag the
centre with it, and because the coordinate must be an integer lattice position, not an average of two.

The method is validated by holding out annotated types: each is re-inferred from the others and the
distance to its annotation is reported, per type, in columns. That measurement travels next to the
connectome the coordinates produced.

Everything works on compressed sparse row arrays rather than dictionaries of lists. That is not
micro-optimisation: the first implementation looped over ninety thousand Python dictionaries inside fifteen
holdout passes and had produced no output after several minutes, which is the kind of run that gets killed
rather than waited on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# A neuron with no column coordinate yet.
UNASSIGNED = np.iinfo(np.int16).min


@dataclass(frozen=True)
class Graph:
    """Undirected partner lists in compressed sparse row form, over neuron indices."""

    indptr: np.ndarray  # int64, size n + 1
    indices: np.ndarray  # int32 partner index
    weights: np.ndarray  # float64 synapse counts
    size: int

    def partners(self, node: int) -> tuple[np.ndarray, np.ndarray]:
        start, end = int(self.indptr[node]), int(self.indptr[node + 1])
        return self.indices[start:end], self.weights[start:end]


def build_graph(i_pre: np.ndarray, i_post: np.ndarray, weight: np.ndarray, size: int) -> Graph:
    """Build the undirected graph of the selection from the directed edge arrays."""
    source = np.concatenate([i_pre, i_post]).astype(np.int64)
    target = np.concatenate([i_post, i_pre]).astype(np.int32)
    values = np.concatenate([weight, weight]).astype(np.float64)

    order = np.argsort(source, kind="stable")
    source, target, values = source[order], target[order], values[order]
    counts = np.bincount(source, minlength=size)
    indptr = np.zeros(size + 1, dtype=np.int64)
    np.cumsum(counts, out=indptr[1:])
    return Graph(indptr=indptr, indices=target, weights=values, size=size)


def weighted_median(values: np.ndarray, weights: np.ndarray) -> int:
    """The smallest value at which the cumulative weight reaches half of the total."""
    order = np.argsort(values, kind="stable")
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    index = int(np.searchsorted(cumulative, cumulative[-1] / 2.0, side="left"))
    return int(values[min(index, values.size - 1)])


def hex_distance(u1: int, v1: int, u2: int, v2: int) -> int:
    """Distance on the hexagonal lattice, in columns.

    The optic-lobe coordinates are axial, so the third cube coordinate is the negated sum of the other two
    and the distance is the largest absolute difference among the three.
    """
    du, dv = u1 - u2, v1 - v2
    dw = -(du + dv)
    return max(abs(du), abs(dv), abs(dw))


@dataclass
class AssignmentResult:
    """The coordinates after inference, plus what it took to get them."""

    hex1: np.ndarray
    hex2: np.ndarray
    inferred: int
    unplaced: int
    rounds: list[dict]


def infer_columns(
    graph: Graph,
    hex1: np.ndarray,
    hex2: np.ndarray,
    max_rounds: int = 4,
    min_partners: int = 3,
) -> AssignmentResult:
    """Place every neuron reachable from the annotated set, without overwriting an annotation."""
    hex1 = hex1.copy()
    hex2 = hex2.copy()
    rounds: list[dict] = []
    inferred = 0

    for round_index in range(max_rounds):
        placed_mask = hex1 != UNASSIGNED
        pending = np.flatnonzero(~placed_mask)
        if pending.size == 0:
            break

        new_u: list[int] = []
        new_v: list[int] = []
        new_index: list[int] = []
        skipped = 0

        for node in pending.tolist():
            partner_index, partner_weight = graph.partners(node)
            if partner_index.size == 0:
                skipped += 1
                continue
            usable = placed_mask[partner_index]
            if int(usable.sum()) < min_partners:
                skipped += 1
                continue
            selected = partner_index[usable]
            weights = partner_weight[usable]
            new_index.append(node)
            new_u.append(weighted_median(hex1[selected].astype(np.int64), weights))
            new_v.append(weighted_median(hex2[selected].astype(np.int64), weights))

        if not new_index:
            rounds.append({"round": round_index + 1, "placed": 0, "skipped_few_partners": skipped})
            break

        index_array = np.asarray(new_index, dtype=np.int64)
        hex1[index_array] = np.asarray(new_u, dtype=np.int16)
        hex2[index_array] = np.asarray(new_v, dtype=np.int16)
        inferred += len(new_index)
        rounds.append({"round": round_index + 1, "placed": len(new_index), "skipped_few_partners": skipped})

    unplaced = int(np.count_nonzero(hex1 == UNASSIGNED))
    return AssignmentResult(hex1=hex1, hex2=hex2, inferred=inferred, unplaced=unplaced, rounds=rounds)


def validate_by_holdout(
    graph: Graph,
    hex1: np.ndarray,
    hex2: np.ndarray,
    type_index: np.ndarray,
    types: list[str],
    max_rounds: int = 4,
    min_partners: int = 3,
) -> dict:
    """Re-infer each annotated type from the others and report the error, in columns.

    This is the honest measure of the method. If holding out a type reproduces its annotated columns, the
    inferred coordinates for the unannotated types can be trusted to the same order; if it does not, the
    connectome built on them carries that number and says so.
    """
    annotated = hex1 != UNASSIGNED
    per_type: dict[str, dict] = {}

    for type_position in np.unique(type_index[annotated]).tolist():
        members = np.flatnonzero(annotated & (type_index == type_position))
        if members.size == 0:
            continue

        partial1, partial2 = hex1.copy(), hex2.copy()
        partial1[members] = UNASSIGNED
        partial2[members] = UNASSIGNED
        if not np.any(partial1 != UNASSIGNED):
            continue

        result = infer_columns(graph, partial1, partial2, max_rounds=max_rounds, min_partners=min_partners)
        recovered = members[result.hex1[members] != UNASSIGNED]
        name = types[type_position]
        if recovered.size == 0:
            per_type[name] = {"n": int(members.size), "recovered": 0}
            continue

        distances = np.asarray([
            hex_distance(
                int(result.hex1[node]), int(result.hex2[node]), int(hex1[node]), int(hex2[node])
            )
            for node in recovered.tolist()
        ])
        per_type[name] = {
            "n": int(members.size),
            "recovered": int(recovered.size),
            "exact_fraction": round(float(np.mean(distances == 0)), 4),
            "within_one_fraction": round(float(np.mean(distances <= 1)), 4),
            "median_error_columns": float(np.median(distances)),
            "p95_error_columns": float(np.percentile(distances, 95)),
        }

    scored = [m for m in per_type.values() if m.get("recovered")]
    exact = [m["exact_fraction"] for m in scored]
    within_one = [m["within_one_fraction"] for m in scored]
    summary = {
        "types_tested": len(per_type),
        "types_recovered": len(scored),
        "median_exact_fraction": round(float(np.median(exact)), 4) if exact else 0.0,
        "median_within_one_fraction": round(float(np.median(within_one)), 4) if within_one else 0.0,
        "worst_p95_error_columns": max((m["p95_error_columns"] for m in scored), default=None),
    }
    return {"per_type": per_type, "summary": summary}
