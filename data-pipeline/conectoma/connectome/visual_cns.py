"""The whole visual system of the MaleCNS release as a neuron-level graph.

The lattice connectome (`malecns.py`) averages each cell type into filters on a periodic eye. This module
keeps the individual neurons instead: both optic lobes and the neurons that carry vision to and from the
central brain (the visual projection and visual centrifugal superclasses), every measured connection between
them, and a sign per presynaptic neuron. Nothing is averaged and nothing is periodic; it is the graph the
network engine simulates for the visual-CNS variant.

The same rules as the lattice build decide which cells take part: the inner photoreceptors are pooled into
R7 and R8, placeholder types ("_unclear") are left out, and every neuron needs a cell type. Column
coordinates are inferred per eye, because each optic lobe carries its own column frame, with the method and
holdout validation of the lattice build.

The graph is written outside git (tens of megabytes); a compact summary with its SHA-256 is committed.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from conectoma.connectome.columns import UNASSIGNED, build_graph, infer_columns, validate_by_holdout
from conectoma.connectome.malecns import (
    AMBIGUOUS_SUFFIX,
    OPTIC_LOBE_SUPERCLASSES,
    VISUAL_PROJECTION_SUPERCLASSES,
    is_photoreceptor,
    load_signs,
    network_type,
    resolve_side,
    scan_edges,
)
from conectoma.io.contract import NT_CONFIDENCE_FLAG, IngestReport, read_feather, validate_hex

SUPERCLASSES = OPTIC_LOBE_SUPERCLASSES + VISUAL_PROJECTION_SUPERCLASSES
SIDES = ("L", "R")
NO_SIDE = -1

# Readout populations: the lobula columnar (LC) and lobula plate-lobula columnar (LPLC) projection neurons,
# which carry visual features from the optic lobe to the central brain.
READOUT_PREFIXES = ("LC", "LPLC")


@dataclass(frozen=True)
class VisualCNSConfig:
    """Everything that changes the graph, recorded next to it."""

    # Every measured connection is kept by default. A cut at three synapses would halve the connections but
    # drop 20 percent of the synapses (measured on this release), and the network's drive is proportional to
    # the count, so a cut is a recorded option rather than the default.
    min_weight: int = 1
    confidence_threshold: float = NT_CONFIDENCE_FLAG
    assignment_rounds: int = 4
    assignment_min_partners: int = 3

    def as_dict(self) -> dict:
        return {
            "min_weight": self.min_weight,
            "confidence_threshold": self.confidence_threshold,
            "assignment_rounds": self.assignment_rounds,
            "assignment_min_partners": self.assignment_min_partners,
        }


@dataclass
class NeuronSelection:
    """The neurons of the visual system, sorted by body id, with their type, side and class."""

    body_ids: np.ndarray       # int64, sorted
    type_index: np.ndarray     # int32 into `types`
    types: list[str]
    side: np.ndarray           # int8: 0 left, 1 right, -1 unresolved
    superclass_index: np.ndarray  # int8 into SUPERCLASSES
    hex1: np.ndarray           # int16, release frame, UNASSIGNED when absent
    hex2: np.ndarray
    report: IngestReport

    def __len__(self) -> int:
        return int(self.body_ids.size)


def select_visual_system(annotations_path: Path) -> NeuronSelection:
    """Keep every typed neuron of the visual superclasses, on either side."""
    table = read_feather(
        annotations_path,
        "annotations",
        columns=["bodyId", "type", "superclass", "somaSide", "instance", "assignedOlHex1", "assignedOlHex2"],
    ).to_pydict()
    report = IngestReport(table="annotations", rows_in=len(table["bodyId"]), rows_out=0)
    rows = []
    for body, cell_type, superclass, soma_side, instance, hex1, hex2 in zip(
        table["bodyId"], table["type"], table["superclass"], table["somaSide"], table["instance"],
        table["assignedOlHex1"], table["assignedOlHex2"], strict=True,
    ):
        if superclass not in SUPERCLASSES:
            report.rejected["other_superclass"] += 1
            continue
        if not cell_type:
            report.rejected["no_cell_type"] += 1
            continue
        pooled = network_type(cell_type)
        if pooled.endswith(AMBIGUOUS_SUFFIX):
            report.rejected["ambiguous_type"] += 1
            continue
        if pooled != cell_type:
            report.flagged["pooled_spectral_subtype"] += 1
        side = resolve_side(soma_side, instance)
        if side is None:
            report.flagged["side_unresolved"] += 1
        if validate_hex(hex1, hex2) is None:
            report.flagged["annotated_column"] += 1
            u, v = int(hex1), int(hex2)
        else:
            u = v = UNASSIGNED
        rows.append((int(body), pooled, SIDES.index(side) if side in SIDES else NO_SIDE,
                     SUPERCLASSES.index(superclass), u, v))
        report.rows_out += 1

    rows.sort()
    types = sorted({r[1] for r in rows})
    index = {t: i for i, t in enumerate(types)}
    return NeuronSelection(
        body_ids=np.asarray([r[0] for r in rows], dtype=np.int64),
        type_index=np.asarray([index[r[1]] for r in rows], dtype=np.int32),
        types=types,
        side=np.asarray([r[2] for r in rows], dtype=np.int8),
        superclass_index=np.asarray([r[3] for r in rows], dtype=np.int8),
        hex1=np.asarray([r[4] for r in rows], dtype=np.int16),
        hex2=np.asarray([r[5] for r in rows], dtype=np.int16),
        report=report,
    )


def assign_columns_per_eye(edges: dict, selection: NeuronSelection, config: VisualCNSConfig) -> dict:
    """Infer missing columns separately in each optic lobe, and validate by holdout on each.

    Each eye has its own column frame, so partners across the midline must not vote on a position: the
    inference runs on the optic-lobe subgraph of one side at a time.
    """
    optic = np.isin(selection.superclass_index, [SUPERCLASSES.index(s) for s in OPTIC_LOBE_SUPERCLASSES])
    result = {}
    for side_index, side in enumerate(SIDES):
        members = np.nonzero(optic & (selection.side == side_index))[0]
        local = np.full(len(selection), -1, dtype=np.int64)
        local[members] = np.arange(members.size)
        keep = (local[edges["i_pre"]] >= 0) & (local[edges["i_post"]] >= 0)
        graph = build_graph(
            local[edges["i_pre"][keep]], local[edges["i_post"][keep]], edges["weight"][keep], members.size,
        )
        hex1, hex2 = selection.hex1[members], selection.hex2[members]
        validation = validate_by_holdout(
            graph, hex1, hex2, selection.type_index[members], selection.types,
            max_rounds=config.assignment_rounds, min_partners=config.assignment_min_partners,
        )
        inferred = infer_columns(
            graph, hex1, hex2,
            max_rounds=config.assignment_rounds, min_partners=config.assignment_min_partners,
        )
        selection.hex1[members] = inferred.hex1
        selection.hex2[members] = inferred.hex2
        result[side] = {
            "optic_lobe_neurons": int(members.size),
            "annotated": int(np.count_nonzero(hex1 != UNASSIGNED)),
            "inferred": inferred.inferred,
            "unplaced": inferred.unplaced,
            "holdout": validation["summary"],
        }
    return result


def build_visual_system(release: Path, config: VisualCNSConfig, annotations: str, neurotransmitters: str,
                        weights: str, log=print) -> tuple[dict, dict]:
    """The arrays of the neuron-level graph and a summary of how they were obtained."""
    log("[1/4] selecting the visual system (both sides)")
    selection = select_visual_system(release / annotations)
    log(f"      {selection.report.summary()}")

    log("[2/4] signs per presynaptic neuron")
    calls = load_signs(release / neurotransmitters, selection, config)
    sign = np.ones(len(selection), dtype=np.int8)
    low = np.zeros(len(selection), dtype=bool)
    sources = Counter()
    for i, body in enumerate(selection.body_ids.tolist()):
        call = calls.get(body)
        if call is None:
            sources["missing"] += 1
            continue
        sign[i] = call.sign
        low[i] = call.low_confidence
        sources[call.source] += 1

    log("[3/4] scanning the connection table")
    scanned = scan_edges(release / weights, selection)
    all_weights = scanned["weight"]
    kept = all_weights >= config.min_weight
    edges = {key: scanned[key][kept] for key in ("i_pre", "i_post", "weight")}
    mass_kept = float(all_weights[kept].sum()) / max(float(all_weights.sum()), 1.0)
    log(f"      {int(kept.sum())} of {all_weights.size} connections kept, {mass_kept:.1%} of the synapses")

    log("[4/4] column coordinates per eye")
    columns = assign_columns_per_eye(scanned, selection, config)
    for side, row in columns.items():
        log(f"      {side}: annotated {row['annotated']}, inferred {row['inferred']}, "
            f"unplaced {row['unplaced']}")

    arrays = {
        "body_id": selection.body_ids,
        "type_index": selection.type_index,
        "types": np.asarray(selection.types),
        "side": selection.side,
        "superclass_index": selection.superclass_index,
        "superclasses": np.asarray(SUPERCLASSES),
        "hex1": selection.hex1,
        "hex2": selection.hex2,
        "sign": sign,
        "low_confidence_sign": low,
        "pre": edges["i_pre"].astype(np.int32),
        "post": edges["i_post"].astype(np.int32),
        "weight": edges["weight"].astype(np.int32),
    }
    photoreceptor = np.asarray([is_photoreceptor(t) for t in selection.types])[selection.type_index]
    readout = np.asarray([t.startswith(READOUT_PREFIXES) for t in selection.types])
    summary = {
        "neurons": len(selection),
        "cell_types": len(selection.types),
        "by_superclass": {
            s: int(np.sum(selection.superclass_index == i)) for i, s in enumerate(SUPERCLASSES)
        },
        "by_side": {
            **{s: int(np.sum(selection.side == i)) for i, s in enumerate(SIDES)},
            "unresolved": int(np.sum(selection.side == NO_SIDE)),
        },
        "connections": int(edges["weight"].size),
        "connections_scanned_inside": int(all_weights.size),
        "synapses_kept_fraction": round(mass_kept, 4),
        "synapses": int(edges["weight"].sum()),
        "photoreceptors": {
            s: {
                "cells": int(np.sum(photoreceptor & (selection.side == i))),
                "placed": int(np.sum(photoreceptor & (selection.side == i) & (selection.hex1 != UNASSIGNED))),
            }
            for i, s in enumerate(SIDES)
        },
        "readout_types": int(readout.sum()),
        "signs": {"sources": dict(sources), "low_confidence": int(low.sum()),
                  "inhibitory_neurons": int(np.sum(sign < 0))},
        "columns": columns,
        "ingest": selection.report.as_dict(),
        "config": config.as_dict(),
    }
    return arrays, summary


def write_graph(arrays: dict, path: Path) -> str:
    """Write the graph compressed and return its SHA-256, the identity a network is bound to."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".partial.npz")
    np.savez_compressed(temporary, **arrays)
    temporary.replace(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
