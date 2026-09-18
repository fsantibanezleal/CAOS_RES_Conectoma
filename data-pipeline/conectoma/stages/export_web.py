"""Contract 2 for the connectome explorer: a compact artifact the web reads, and its manifest.

The connectome specification is written for the network engine and is too heavy to ship as it is (about
8 MB, mostly indentation and repeated keys). The explorer needs the same facts in a form a browser reads
quickly: one row per cell type, and one row per connection whose filter is three parallel arrays (the two
column offsets and the synapse count). Nothing is recomputed here; every number is copied from the
specification or from the published consensus, so the explorer shows what the build produced.

The manifest records where the artifact came from (the SHA-256 of the specification and of the reference),
under which terms it may be redistributed, and its own size and digest, so the web can check it loaded the
artifact it was built against. It carries no timestamp: the same inputs give the same bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from conectoma.connectome.compare import aliases_for
from conectoma.connectome.malecns import is_photoreceptor

ARTIFACT_VERSION = 1


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _neuropil_group(name: str, pattern: list, is_input: bool, is_output: bool) -> str:
    """The group a type is listed under in the explorer: input, output, then by placement."""
    if is_input:
        return "input"
    if is_output:
        return "output"
    kind, args = pattern
    if kind == "single":
        return "population"
    return f"stride{args[0]}"


def build_explorer(spec: dict, reference: dict | None) -> dict:
    """The explorer artifact: types, connections with their filters, and the published filters that match."""
    inputs = set(spec["input_units"])
    outputs = set(spec["output_units"])
    names = [node["name"] for node in spec["nodes"]]
    index = {name: i for i, name in enumerate(names)}
    signs: dict[str, int] = {}
    for edge in spec["edges"]:
        signs.setdefault(edge["src"], edge["alpha"])

    types = []
    for node in spec["nodes"]:
        name = node["name"]
        types.append({
            "name": name,
            "pattern": node["pattern"],
            "group": _neuropil_group(name, node["pattern"], name in inputs, name in outputs),
            "density": node.get("density"),
            "cells": node.get("n_cells"),
            "cells_placed": node.get("n_cells_placed"),
            "sign": signs.get(name, 0),
            "photoreceptor": is_photoreceptor(name),
        })

    connections = []
    for edge in spec["edges"]:
        offsets = edge["offsets"]
        connections.append([
            index[edge["src"]],
            index[edge["tar"]],
            edge["alpha"],
            round(float(edge.get("lambda_mult", 1.0)), 4),
            [int(o[0]) for o, _ in offsets],
            [int(o[1]) for o, _ in offsets],
            [round(float(n), 3) for _, n in offsets],
        ])

    published = []
    if reference is not None:
        built_pairs = {(edge["src"], edge["tar"]) for edge in spec["edges"]}
        for edge in reference["edges"]:
            matches = [
                [a, b]
                for a in aliases_for(edge["src"])
                for b in aliases_for(edge["tar"])
                if (a, b) in built_pairs
            ]
            if not matches:
                continue
            published.append({
                "src": edge["src"],
                "tar": edge["tar"],
                "matches": matches,
                "sign": edge["alpha"],
                "du": [int(o[0]) for o, _ in edge["offsets"]],
                "dv": [int(o[1]) for o, _ in edge["offsets"]],
                "n": [round(float(n), 3) for _, n in edge["offsets"]],
            })

    return {
        "version": ARTIFACT_VERSION,
        "types": types,
        "connection_fields": ["source", "target", "sign", "certainty", "du", "dv", "synapses"],
        "connections": connections,
        "published": published,
        "frame": spec.get("provenance", {}).get("frame"),
        "placement": spec.get("provenance", {}).get("placement"),
        "compile": spec.get("compile"),
    }


def export_explorer(spec_path: Path, reference_path: Path | None, out_dir: Path, manifests_dir: Path) -> dict:
    """Write the explorer artifact and its manifest; return the manifest."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    reference = json.loads(Path(reference_path).read_text(encoding="utf-8")) if reference_path else None
    artifact = build_explorer(spec, reference)

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / f"{Path(spec_path).stem}.json"
    text = json.dumps(artifact, separators=(",", ":")) + "\n"
    artifact_path.write_text(text, encoding="utf-8", newline="\n")

    manifest = {
        "artifact": "explorer",
        "version": ARTIFACT_VERSION,
        "path": f"explorer/{artifact_path.name}",
        "bytes": artifact_path.stat().st_size,
        "sha256": _digest(artifact_path),
        "source": {
            "specification": Path(spec_path).name,
            "specification_sha256": _digest(spec_path),
            "dataset": spec.get("provenance", {}).get("dataset"),
            "license": spec.get("provenance", {}).get("license"),
            "citation": spec.get("provenance", {}).get("citation"),
        },
        "reference": None if reference_path is None else {
            "file": Path(reference_path).name,
            "sha256": _digest(reference_path),
            "license": "MIT (flyvis, published consensus connectome)",
        },
        "counts": {
            "types": len(artifact["types"]),
            "connections": len(artifact["connections"]),
            "filter_entries": sum(len(c[4]) for c in artifact["connections"]),
            "published_connections": len(artifact["published"]),
        },
    }
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / "explorer.json"
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest
