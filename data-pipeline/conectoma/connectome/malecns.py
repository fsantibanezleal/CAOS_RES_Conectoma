"""Build a type-level consensus connectome of the optic lobe from the MaleCNS v1.0 tables.

The release gives, per neuron, its cell type, its side, and for optic-lobe neurons its hexagonal column
coordinate (`assignedOlHex1`, `assignedOlHex2`); and, per ordered pair of neurons, a synapse count. This
module turns those measurements into the average convolutional filters that a connectome-constrained
network is built from: for each ordered pair of cell types, how many synapses a presynaptic neuron makes
onto a postsynaptic neuron sitting at a given column offset, averaged over the columns that could have
contributed.

Two conventions matter and both are taken from the consuming engine rather than invented here:

- an offset is defined from the source, so a target sits at `(u_src + du, v_src + dv)`; this module
  therefore computes `du = u_post - u_pre`;
- the per-connection certainty the engine reads as `lambda_mult` is recorded as the fraction of eligible
  column pairs that actually carry the connection, so a filter built from one lucky pair is not presented
  with the same weight as one seen across the whole eye;
- offsets are written in the engine's lattice frame, which is the release's column frame turned half a
  turn (`RELEASE_TO_ENGINE`, measured, not assumed).

The output is the JSON the engine consumes directly, which is why this product needs no library of its own.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow.dataset as ds

from conectoma.connectome.columns import UNASSIGNED, build_graph, infer_columns, validate_by_holdout
from conectoma.connectome.signs import call_sign, majority_sign
from conectoma.io.contract import (
    MIN_WEIGHT,
    NT_CONFIDENCE_FLAG,
    IngestReport,
    read_feather,
    validate_hex,
)

# Superclasses of the release that make up the visual system.
OPTIC_LOBE_SUPERCLASSES = ("ol_intrinsic", "ol_sensory")
VISUAL_PROJECTION_SUPERCLASSES = ("visual_projection", "visual_centrifugal")

# Photoreceptor types as the release names them: the outer receptors share one type ("R1-R6"), while the
# inner pair is split by spectral subtype ("R7p", "R7y", "R8p", "R8y", "R7d", "R8d") with an explicit
# "_unclear" variant where the call could not be made. HBeyelet is the extraretinal eyelet, a photoreceptor
# but not a retinal one, so it is kept as a node and is not an input unit.
PHOTORECEPTOR_PATTERN = re.compile(r"^R\d")
EXTRARETINAL_TYPES = ("HBeyelet",)

# The inner photoreceptors are pooled across spectral subtypes for the network. Pale and yellow ommatidia
# are interleaved at random and the dorsal rim is a strip, so no subtype tiles the eye on its own, while an
# input type of the network must: the stimulus lands on one cell of every input type in every column. The
# input is luminance, not colour, so the split carries nothing the network could use, and the published
# consensus model makes the same choice (one R7, one R8).
SPECTRAL_POOLS = (("R7", re.compile(r"^R7(?!R8)")), ("R8", re.compile(r"^R8")))

# Placeholder types for cells the release could not call: "R7R8_unclear" (R7 or R8), "T4_unclear",
# "Tm_unclear", "ME_unclear" and the like. Their synapses cannot be attributed to a real type without an
# inference that would itself need validating, and as types of their own they would be network populations
# that do not exist, so they are left out and counted. The rule is applied after pooling, so "R7_unclear"
# (an R7 of unknown spectral subtype) is kept as an R7.
AMBIGUOUS_SUFFIX = "_unclear"


def is_photoreceptor(cell_type: str) -> bool:
    """True for a retinal photoreceptor type of the release."""
    return bool(PHOTORECEPTOR_PATTERN.match(cell_type))


def network_type(cell_type: str) -> str:
    """The cell type a neuron takes in the network: its release type, with spectral subtypes pooled."""
    for pooled, pattern in SPECTRAL_POOLS:
        if pattern.match(cell_type):
            return pooled
    return cell_type

# The motion-output types a readout reads first; they are the best-characterised outputs of the optic lobe.
DEFAULT_OUTPUT_TYPES = ("T4a", "T4b", "T4c", "T4d", "T5a", "T5b", "T5c", "T5d")

# Placement. A cell type is laid out over the lattice at the density it has in the eye: on every column, or
# on every k-th column along both lattice axes (one cell per k*k columns), with k chosen so that 1/k^2 is
# the closest such density to the measured cells per column. A type sparser than the coarsest sublattice
# (fewer than one cell per 20 columns, about 44 cells in a medulla of 892 columns) is represented by one
# population node: it stands for the mean activity of its cells, it receives through its measured filters
# like any cell at the centre, and it drives every cell of each target type with the measured average
# per-target total, because each target cell is reached by some member of the population.
MAX_STRIDE = 4
POPULATION_BELOW = 1.0 / (MAX_STRIDE + 0.5) ** 2

# The release's column axes (assignedOlHex1, assignedOlHex2) point the opposite way from the lattice axes of
# the network engine, whose stimulus renderer and published tuning are defined in its own frame. Measured by
# comparing the direction of every spatially extended filter shared with the published consensus under all
# twelve symmetries of the hexagonal lattice (`compare.orientation`): as built from the release the identity
# scores -0.42 and the half-turn +0.42 over 98 filters, and the direction-defining inputs of T4 and T5 (Mi9,
# Mi4, Tm9) are each turned by 120 to 170 degrees. Offsets are therefore written in the engine's frame by
# turning them half a turn, (du, dv) -> (-du, -dv); the comparison report re-measures it on every build.
RELEASE_TO_ENGINE = -1


def placement(density: float) -> list:
    """The lattice pattern of a cell type with the given measured cells per column."""
    if density < POPULATION_BELOW:
        return ["single", None]
    stride = int(min(MAX_STRIDE, max(1, round(1.0 / np.sqrt(density)))))
    return ["stride", [stride, stride]]



@dataclass(frozen=True)
class BuildConfig:
    """Everything that changes the output, recorded in the manifest next to it."""

    side: str = "R"
    # Chosen by the threshold sweep recorded in docs/architecture/02_connectome-construction.md: at 0.5 and
    # 0.02 the build recovers 76.0 percent of the published consensus connections with the highest sign
    # agreement of the three settings tried, where 1.0 and 0.05 recovered only 66.6 percent and 0.2 and 0.01
    # recovered 84.8 percent at a lower rank correlation and 11.5 MB of artifact.
    min_mean_synapses: float = 0.5
    min_certainty: float = 0.02
    max_offset: int = 8
    confidence_threshold: float = NT_CONFIDENCE_FLAG
    include_projection_neurons: bool = False
    assignment_rounds: int = 4
    assignment_min_partners: int = 3

    def as_dict(self) -> dict:
        return {
            "side": self.side,
            "min_mean_synapses": self.min_mean_synapses,
            "min_certainty": self.min_certainty,
            "max_offset": self.max_offset,
            "confidence_threshold": self.confidence_threshold,
            "include_projection_neurons": self.include_projection_neurons,
            "assignment_rounds": self.assignment_rounds,
            "assignment_min_partners": self.assignment_min_partners,
        }


@dataclass
class Selection:
    """The neurons this build keeps, in a form the scan can look up quickly."""

    body_ids: np.ndarray  # sorted int64
    type_index: np.ndarray  # int32 index into `types`
    hex1: np.ndarray  # int16
    hex2: np.ndarray  # int16
    types: list[str]
    cells_per_type: Counter  # every selected neuron of the type, placed or not
    report: IngestReport

    def __len__(self) -> int:
        return int(self.body_ids.size)

    def placed_per_type(self) -> Counter:
        """How many neurons of each type carry a column, annotated or inferred."""
        counts: Counter = Counter()
        for type_index, u in zip(self.type_index.tolist(), self.hex1.tolist(), strict=True):
            if u != UNASSIGNED:
                counts[self.types[type_index]] += 1
        return counts


def resolve_side(soma_side: str | None, instance: str | None) -> str | None:
    """Which optic lobe a neuron belongs to.

    `somaSide` answers this for optic-lobe neurons, but not for photoreceptors: their somata sit in the
    retina, so the release leaves the field empty for all 6,062 of them. The `instance` name carries the
    side as a suffix for every annotated neuron, including those, so it is the fallback. A neuron with
    neither is rejected rather than assigned to a default eye.
    """
    if soma_side in ("R", "L"):
        return soma_side
    if instance:
        suffix = instance.rsplit("_", 1)[-1]
        if suffix in ("R", "L"):
            return suffix
    return None


def select_neurons(annotations_path: Path, config: BuildConfig) -> Selection:
    """Keep the optic-lobe neurons of one side that carry a usable column coordinate and a cell type."""
    wanted = list(OPTIC_LOBE_SUPERCLASSES)
    if config.include_projection_neurons:
        wanted += list(VISUAL_PROJECTION_SUPERCLASSES)

    table = read_feather(
        annotations_path,
        "annotations",
        columns=[
            "bodyId", "type", "superclass", "somaSide", "instance", "assignedOlHex1", "assignedOlHex2",
        ],
    ).to_pydict()

    report = IngestReport(table="annotations", rows_in=len(table["bodyId"]), rows_out=0)
    ids: list[int] = []
    type_names: list[str] = []
    h1: list[int] = []
    h2: list[int] = []

    for body, cell_type, superclass, soma_side, instance, hex1, hex2 in zip(
        table["bodyId"], table["type"], table["superclass"], table["somaSide"], table["instance"],
        table["assignedOlHex1"], table["assignedOlHex2"], strict=True,
    ):
        if superclass not in wanted:
            report.rejected["other_superclass"] += 1
            continue
        if not cell_type:
            report.rejected["no_cell_type"] += 1
            continue
        side = resolve_side(soma_side, instance)
        if side is None:
            report.rejected["unknown_side"] += 1
            continue
        if side != config.side:
            report.rejected["other_side"] += 1
            continue
        pooled = network_type(cell_type)
        if pooled.endswith(AMBIGUOUS_SUFFIX):
            report.rejected["ambiguous_type"] += 1
            continue
        if pooled != cell_type:
            report.flagged["pooled_spectral_subtype"] += 1
        reason = validate_hex(hex1, hex2)
        if reason is None:
            h1.append(int(hex1))
            h2.append(int(hex2))
            report.flagged["annotated_column"] += 1
        else:
            # Kept without a column: the assignment step infers one from connectivity and the holdout
            # validation measures how well that works. Rejecting these would discard most of the optic lobe,
            # including the direction-selective populations.
            h1.append(UNASSIGNED)
            h2.append(UNASSIGNED)
            report.flagged[reason] += 1
        ids.append(int(body))
        type_names.append(str(pooled))
        report.rows_out += 1

    order = np.argsort(np.asarray(ids, dtype=np.int64), kind="stable")
    body_ids = np.asarray(ids, dtype=np.int64)[order]
    sorted_types = [type_names[i] for i in order]
    types = sorted(set(sorted_types))
    type_to_index = {t: i for i, t in enumerate(types)}

    cells_per_type: Counter = Counter(sorted_types)
    return Selection(
        body_ids=body_ids,
        type_index=np.asarray([type_to_index[t] for t in sorted_types], dtype=np.int32),
        hex1=np.asarray(h1, dtype=np.int16)[order],
        hex2=np.asarray(h2, dtype=np.int16)[order],
        types=types,
        cells_per_type=cells_per_type,
        report=report,
    )


def load_signs(neurotransmitters_path: Path, selection: Selection, config: BuildConfig) -> dict:
    """Assign a sign to every selected neuron, keeping the provenance of each call."""
    table = read_feather(
        neurotransmitters_path,
        "neurotransmitters",
        columns=["body", "consensus_nt", "celltype_predicted_nt", "celltype_predicted_nt_confidence"],
    ).to_pydict()

    wanted = set(selection.body_ids.tolist())
    calls: dict[int, object] = {}
    for body, consensus, celltype_nt, confidence in zip(
        table["body"], table["consensus_nt"], table["celltype_predicted_nt"],
        table["celltype_predicted_nt_confidence"], strict=True,
    ):
        body = int(body)
        if body not in wanted or body in calls:
            continue
        calls[body] = call_sign(
            body_id=body,
            consensus_nt=consensus,
            celltype_nt=celltype_nt,
            celltype_confidence=confidence,
            confidence_threshold=config.confidence_threshold,
        )
    return calls


def _lookup(sorted_ids: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Index of each query id in `sorted_ids`, or -1 when absent."""
    position = np.searchsorted(sorted_ids, query)
    position_clipped = np.clip(position, 0, sorted_ids.size - 1)
    found = sorted_ids[position_clipped] == query
    return np.where(found, position_clipped, -1)


def scan_edges(weights_path: Path, selection: Selection) -> dict:
    """Scan the full connection table once and keep the edges inside the selection.

    The table holds more than 150 million ordered pairs, so it is read in batches with only the three
    columns this needs. What survives is the optic-lobe subgraph: two index arrays into the selection and
    the synapse count of each edge.
    """
    dataset = ds.dataset(str(weights_path), format="feather")
    pre_parts: list[np.ndarray] = []
    post_parts: list[np.ndarray] = []
    weight_parts: list[np.ndarray] = []
    scanned = 0

    for batch in dataset.to_batches(columns=["body_pre", "body_post", "weight"]):
        pre = batch.column("body_pre").to_numpy(zero_copy_only=False)
        post = batch.column("body_post").to_numpy(zero_copy_only=False)
        weight = batch.column("weight").to_numpy(zero_copy_only=False)
        scanned += pre.size

        i_pre = _lookup(selection.body_ids, pre)
        i_post = _lookup(selection.body_ids, post)
        keep = (i_pre >= 0) & (i_post >= 0) & (weight >= MIN_WEIGHT) & (i_pre != i_post)
        if not keep.any():
            continue
        pre_parts.append(i_pre[keep].astype(np.int32))
        post_parts.append(i_post[keep].astype(np.int32))
        weight_parts.append(weight[keep].astype(np.int32))

    if not pre_parts:
        empty = np.zeros(0, dtype=np.int32)
        return {"i_pre": empty, "i_post": empty, "weight": empty, "rows_scanned": scanned, "rows_kept": 0}

    i_pre = np.concatenate(pre_parts)
    i_post = np.concatenate(post_parts)
    weight = np.concatenate(weight_parts)
    return {
        "i_pre": i_pre,
        "i_post": i_post,
        "weight": weight,
        "rows_scanned": scanned,
        "rows_kept": int(weight.size),
    }


def assign_columns(edges: dict, selection: Selection, config: BuildConfig) -> dict:
    """Infer the missing column coordinates and measure the method by holding out annotated types."""
    graph = build_graph(edges["i_pre"], edges["i_post"], edges["weight"], len(selection))

    validation = validate_by_holdout(
        graph,
        selection.hex1,
        selection.hex2,
        selection.type_index,
        selection.types,
        max_rounds=config.assignment_rounds,
        min_partners=config.assignment_min_partners,
    )
    annotated = int(np.count_nonzero(selection.hex1 != UNASSIGNED))
    result = infer_columns(
        graph,
        selection.hex1,
        selection.hex2,
        max_rounds=config.assignment_rounds,
        min_partners=config.assignment_min_partners,
    )
    selection.hex1, selection.hex2 = result.hex1, result.hex2

    return {
        "annotated": annotated,
        "inferred": result.inferred,
        "placed_total": annotated + result.inferred,
        "unplaced": result.unplaced,
        "rounds": result.rounds,
        "validation": validation,
    }


def accumulate_filters(edges: dict, selection: Selection, config: BuildConfig) -> dict:
    """Sum synapses per (source type, target type, column offset) over the placed neurons."""
    n_types = len(selection.types)
    span = 2 * config.max_offset + 1

    i_pre, i_post, weight = edges["i_pre"], edges["i_post"], edges["weight"]

    # Whole-pair totals, over every selected neuron whether or not it has a column and at any distance:
    # what a population node sends is the average total a target cell receives from the whole type, and
    # windowing it by offset or dropping unplaced cells would understate exactly the wide-field types that
    # are represented that way. Alongside, how many distinct target cells the type reaches at all.
    pair_of_edge = (
        selection.type_index[i_pre].astype(np.int64) * n_types + selection.type_index[i_post].astype(np.int64)
    )
    pair_totals = np.bincount(pair_of_edge, weights=weight.astype(np.float64), minlength=n_types * n_types)
    reached_keys = np.unique(pair_of_edge * len(selection) + i_post.astype(np.int64))
    pair_reached = np.bincount(reached_keys // len(selection), minlength=n_types * n_types)

    placed = (selection.hex1[i_pre] != UNASSIGNED) & (selection.hex1[i_post] != UNASSIGNED)
    i_pre, i_post, weight = i_pre[placed], i_post[placed], weight[placed]

    du = selection.hex1[i_post].astype(np.int32) - selection.hex1[i_pre].astype(np.int32)
    dv = selection.hex2[i_post].astype(np.int32) - selection.hex2[i_pre].astype(np.int32)
    within = (np.abs(du) <= config.max_offset) & (np.abs(dv) <= config.max_offset)
    i_pre, i_post, weight, du, dv = i_pre[within], i_post[within], weight[within], du[within], dv[within]

    t_pre = selection.type_index[i_pre].astype(np.int64)
    t_post = selection.type_index[i_post].astype(np.int64)
    key = ((t_pre * n_types + t_post) * span + (du + config.max_offset)) * span + (dv + config.max_offset)

    unique_keys, inverse = np.unique(key, return_inverse=True)
    summed = np.zeros(unique_keys.size, dtype=np.float64)
    np.add.at(summed, inverse, weight.astype(np.float64))
    counted = np.bincount(inverse, minlength=unique_keys.size)

    totals = {int(k): float(s) for k, s in zip(unique_keys.tolist(), summed.tolist(), strict=True)}
    pairs = {int(k): int(c) for k, c in zip(unique_keys.tolist(), counted.tolist(), strict=True)}
    return {
        "totals": totals,
        "pairs": pairs,
        "pair_totals": pair_totals,
        "pair_reached": pair_reached,
        "span": span,
        "rows_scanned": edges["rows_scanned"],
        "rows_kept": edges["rows_kept"],
        "edges_placed": int(weight.size),
    }


def build_filters(accumulated: dict, selection: Selection, signs: dict, config: BuildConfig) -> dict:
    """Turn the accumulator into average filters per ordered type pair, with certainty and sign."""
    n_types = len(selection.types)
    span = accumulated["span"]
    offsets_by_pair: dict[tuple[int, int], list] = defaultdict(list)
    dropped = Counter()
    # Computed once: it walks every neuron, and the loop below runs over hundreds of thousands of entries.
    placed_per_type = selection.placed_per_type()

    for key, total in accumulated["totals"].items():
        dv = key % span - config.max_offset
        rest = key // span
        du = rest % span - config.max_offset
        rest //= span
        t_post = rest % n_types
        t_pre = rest // n_types

        target_columns = placed_per_type[selection.types[t_post]]
        mean_synapses = total / max(target_columns, 1)
        certainty = accumulated["pairs"][key] / max(target_columns, 1)

        if mean_synapses < config.min_mean_synapses:
            dropped["below_min_mean_synapses"] += 1
            continue
        if certainty < config.min_certainty:
            dropped["below_min_certainty"] += 1
            continue
        offsets_by_pair[(t_pre, t_post)].append(
            ((int(du), int(dv)), round(mean_synapses, 4), round(certainty, 4))
        )

    # Sign of a type-to-type connection: the majority sign of its presynaptic neurons of that type.
    signs_by_type: dict[str, int] = {}
    disagreement = Counter()
    per_type_signs: dict[str, list[int]] = defaultdict(list)
    for position, body in enumerate(selection.body_ids.tolist()):
        call = signs.get(body)
        if call is None:
            continue
        per_type_signs[selection.types[selection.type_index[position]]].append(call.sign)
    for cell_type, values in per_type_signs.items():
        signs_by_type[cell_type] = majority_sign(values)
        minority = min(sum(1 for s in values if s > 0), sum(1 for s in values if s < 0))
        if minority:
            disagreement[cell_type] = minority / len(values)

    # Whole-pair averages for the population nodes: synapses per target cell and the fraction of target
    # cells reached, over every selected neuron of the target type.
    population_by_pair: dict[tuple[int, int], tuple[float, float]] = {}
    for flat in np.nonzero(accumulated["pair_totals"])[0].tolist():
        t_pre, t_post = divmod(flat, n_types)
        cells = max(selection.cells_per_type[selection.types[t_post]], 1)
        population_by_pair[(t_pre, t_post)] = (
            round(float(accumulated["pair_totals"][flat]) / cells, 4),
            round(float(accumulated["pair_reached"][flat]) / cells, 4),
        )

    return {
        "offsets_by_pair": offsets_by_pair,
        "population_by_pair": population_by_pair,
        "signs_by_type": signs_by_type,
        "sign_disagreement": disagreement,
        "dropped": dropped,
    }


def lattice_columns(selection: Selection) -> int:
    """Number of distinct columns occupied by placed neurons: the size of the eye this lobe sees with."""
    placed = selection.hex1 != UNASSIGNED
    return len(set(zip(selection.hex1[placed].tolist(), selection.hex2[placed].tolist(), strict=True)))


def to_flyvis_spec(built: dict, selection: Selection, config: BuildConfig) -> dict:
    """Emit the JSON schema the connectome-constrained network engine reads.

    Nodes carry a placement pattern chosen from their measured density (see `placement`). Edges from a
    tiled type carry the measured average filter, which the compiler hands in full to every target cell;
    edges from a population node carry one entry, the measured average synapses per target cell over the
    whole pair, which the compiler spreads to every target cell. The `compile` block states both rules, so
    the file says how it is meant to be read.
    """
    columns = lattice_columns(selection)
    placed = selection.placed_per_type()
    nodes = []
    patterns: dict[str, list] = {}
    for cell_type in selection.types:
        density = placed[cell_type] / max(columns, 1)
        patterns[cell_type] = placement(density)
        nodes.append({
            "name": cell_type,
            "pattern": patterns[cell_type],
            "activation": "relu",
            "bias": 0.0,
            "bias_fixed": False,
            "time_constant": None,
            "time_constant_fixed": False,
            "n_cells": selection.cells_per_type[cell_type],
            "n_cells_placed": placed[cell_type],
            "density": round(density, 4),
        })

    def edge(source: str, target: str, offsets: list, certainty: float) -> dict:
        return {
            "src": source,
            "tar": target,
            "offsets": offsets,
            "alpha": built["signs_by_type"].get(source, 1),
            "alpha_fixed": True,
            "alpha_references": ["Eckstein2024"],
            "time_constant": None,
            "time_constant_fixed": False,
            "lambda_mult": round(certainty, 4),
            "edge_type": "chem",
        }

    edges = []
    dropped = Counter()
    pairs = sorted(set(built["offsets_by_pair"]) | set(built["population_by_pair"]))
    for t_pre, t_post in pairs:
        source, target = selection.types[t_pre], selection.types[t_post]
        if patterns[source][0] == "single":
            per_target, reach = built["population_by_pair"].get((t_pre, t_post), (0.0, 0.0))
            if per_target < config.min_mean_synapses:
                dropped["population_below_min_mean_synapses"] += 1
                continue
            if reach < config.min_certainty:
                dropped["population_below_min_certainty"] += 1
                continue
            edges.append(edge(source, target, [[[0, 0], per_target]], reach))
            continue
        offsets = built["offsets_by_pair"].get((t_pre, t_post))
        if not offsets:
            continue
        certainty = float(np.mean([c for _, _, c in offsets]))
        turned = sorted(
            ((RELEASE_TO_ENGINE * du, RELEASE_TO_ENGINE * dv), value) for (du, dv), value, _ in offsets
        )
        edges.append(edge(source, target, [[list(o), value] for o, value in turned], certainty))

    present = set(selection.types)
    receptors = sorted(t for t in present if is_photoreceptor(t))
    # The engine drives one cell of every input type in every column, so every input type must sit on the
    # full lattice; anything else would break the stimulus rather than weaken it. Fail here, where the
    # cause is visible.
    untiled = [t for t in receptors if patterns[t] != ["stride", [1, 1]]]
    if untiled:
        raise ValueError(f"input types must occupy every column; these do not: {untiled}")
    return {
        "nodes": nodes,
        "edges": edges,
        "receptors": receptors,
        "input_units": receptors,
        "extraretinal_units": sorted(t for t in EXTRARETINAL_TYPES if t in present),
        "output_units": sorted(t for t in DEFAULT_OUTPUT_TYPES if t in present),
        "compile": {
            # read by the product's compiler (conectoma.network.lattice); an engine that ignores the block
            # reads the filters as plain convolutions from their sources, which is exact between types on
            # every column, loses entries between sublattices, and reaches one target from a population
            "population_broadcast": True,
            "target_centric": True,
        },
        "provenance": {
            "dataset": "male-cns:v1.0",
            "license": "CC-BY",
            "citation": "Berg et al., Cell, 2026, sexual dimorphism in the complete connectome of the "
                        "Drosophila male central nervous system",
            "sign_source": "Eckstein et al., Cell, 2024, doi:10.1016/j.cell.2024.03.016",
            "config": config.as_dict(),
            "frame": {
                "offsets": "engine lattice axes; the release's column offsets turned half a turn",
                "release_to_engine": RELEASE_TO_ENGINE,
            },
            "placement": {
                "columns": columns,
                "max_stride": MAX_STRIDE,
                "population_below_density": round(POPULATION_BELOW, 4),
                "types_by_pattern": dict(Counter(json.dumps(p) for p in patterns.values())),
            },
            "dropped_population_edges": dict(dropped),
        },
    }


def write_spec(spec: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    return path
