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
  with the same weight as one seen across the whole eye.

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


def is_photoreceptor(cell_type: str) -> bool:
    """True for a retinal photoreceptor type of the release."""
    return bool(PHOTORECEPTOR_PATTERN.match(cell_type))

# The motion-output types a readout reads first; they are the best-characterised outputs of the optic lobe.
DEFAULT_OUTPUT_TYPES = ("T4a", "T4b", "T4c", "T4d", "T5a", "T5b", "T5c", "T5d")

# A cell type is treated as columnar (one cell per column, tiled across the eye) when it occupies at least
# this fraction of the columns its neuropil spans. Below it, the type is placed once, at the centre.
COLUMNAR_COVERAGE = 0.25



@dataclass(frozen=True)
class BuildConfig:
    """Everything that changes the output, recorded in the manifest next to it."""

    side: str = "R"
    # Chosen by the threshold sweep recorded in docs/architecture/02_connectome-construction.md: at 0.5 and
    # 0.02 the build recovers 75.8 percent of the published consensus connections with the highest sign
    # agreement of the three settings tried, where 1.0 and 0.05 recovered only 66.2 percent and 0.2 and 0.01
    # recovered 84.8 percent at a lower rank correlation and 12 MB of artifact.
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
    columns_per_type: Counter
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
        type_names.append(str(cell_type))
        report.rows_out += 1

    order = np.argsort(np.asarray(ids, dtype=np.int64), kind="stable")
    body_ids = np.asarray(ids, dtype=np.int64)[order]
    sorted_types = [type_names[i] for i in order]
    types = sorted(set(sorted_types))
    type_to_index = {t: i for i, t in enumerate(types)}

    columns_per_type: Counter = Counter(sorted_types)
    return Selection(
        body_ids=body_ids,
        type_index=np.asarray([type_to_index[t] for t in sorted_types], dtype=np.int32),
        hex1=np.asarray(h1, dtype=np.int16)[order],
        hex2=np.asarray(h2, dtype=np.int16)[order],
        types=types,
        columns_per_type=columns_per_type,
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

    return {
        "offsets_by_pair": offsets_by_pair,
        "signs_by_type": signs_by_type,
        "sign_disagreement": disagreement,
        "dropped": dropped,
    }


def to_flyvis_spec(built: dict, selection: Selection, config: BuildConfig) -> dict:
    """Emit the JSON schema the connectome-constrained network engine reads.

    Nodes carry a placement pattern: a columnar type is tiled with stride one, a type that occupies few
    columns is placed once at the centre. Edges carry the average filter, the measured sign, and the
    certainty of the count.
    """
    placed = selection.placed_per_type()
    max_columns = max(placed.values()) if placed else 1
    nodes = []
    for cell_type in selection.types:
        columns = placed[cell_type]
        columnar = columns >= COLUMNAR_COVERAGE * max_columns
        nodes.append({
            "name": cell_type,
            "pattern": ["stride", [1, 1]] if columnar else ["single", None],
            "activation": "relu",
            "bias": 0.0,
            "bias_fixed": False,
            "time_constant": None,
            "time_constant_fixed": False,
            "n_cells_measured": columns,
        })

    edges = []
    for (t_pre, t_post), offsets in sorted(built["offsets_by_pair"].items()):
        source, target = selection.types[t_pre], selection.types[t_post]
        certainty = float(np.mean([c for _, _, c in offsets]))
        edges.append({
            "src": source,
            "tar": target,
            "offsets": [[list(offset), value] for offset, value, _ in sorted(offsets)],
            "alpha": built["signs_by_type"].get(source, 1),
            "alpha_fixed": True,
            "alpha_references": ["Eckstein2024"],
            "time_constant": None,
            "time_constant_fixed": False,
            "lambda_mult": round(certainty, 4),
            "edge_type": "chem",
        })

    present = set(selection.types)
    receptors = sorted(t for t in present if is_photoreceptor(t))
    return {
        "nodes": nodes,
        "edges": edges,
        "receptors": receptors,
        "input_units": receptors,
        "extraretinal_units": sorted(t for t in EXTRARETINAL_TYPES if t in present),
        "output_units": sorted(t for t in DEFAULT_OUTPUT_TYPES if t in present),
        "provenance": {
            "dataset": "male-cns:v1.0",
            "license": "CC-BY",
            "citation": "Berg et al., Cell, 2026, sexual dimorphism in the complete connectome of the "
                        "Drosophila male central nervous system",
            "sign_source": "Eckstein et al., Cell, 2024, doi:10.1016/j.cell.2024.03.016",
            "config": config.as_dict(),
        },
    }


def write_spec(spec: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    return path
