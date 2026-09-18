"""Tests for contract 2, the compact artifacts the web reads.

The explorer artifact is a transcription of the connectome specification, so the tests check that it
transcribes (indices, signs, groups, the published matches through the cross-release renames), that the
same inputs give the same bytes, and that the committed artifact is exactly what the committed
specification produces. Every write goes to a temporary directory; the canonical artifacts are only read.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.connectome.compare import find_reference  # noqa: E402
from conectoma.stages.export_web import ARTIFACT_VERSION, build_explorer, export_explorer  # noqa: E402

DERIVED = ROOT / "data" / "derived"
SPEC = DERIVED / "connectome" / "malecns-optic-lobe-r.json"
MANIFEST = DERIVED / "manifests" / "explorer.json"


def spec_of(nodes: list[dict], edges: list[dict], inputs: list[str], outputs: list[str]) -> dict:
    return {
        "nodes": nodes,
        "edges": edges,
        "input_units": inputs,
        "output_units": outputs,
        "provenance": {
            "frame": {"offsets": "engine lattice axes", "release_to_engine": -1},
            "placement": {
                "columns": 7, "max_stride": 4, "population_below_density": 0.05, "types_by_pattern": {},
            },
            "dataset": "male-cns:v1.0",
            "license": "CC-BY",
            "citation": "test",
        },
        "compile": {"population_broadcast": True, "target_centric": True},
    }


def node(name: str, pattern: list, cells: int = 7) -> dict:
    return {"name": name, "pattern": pattern, "n_cells": cells, "n_cells_placed": cells, "density": 1.0}


def edge(src: str, tar: str, alpha: int, offsets: list, certainty: float = 1.0) -> dict:
    return {"src": src, "tar": tar, "alpha": alpha, "offsets": offsets, "lambda_mult": certainty}


@pytest.fixture
def small_spec() -> dict:
    nodes = [
        node("R1-R6", ["stride", [1, 1]]),
        node("L1", ["stride", [1, 1]]),
        node("Mi1", ["stride", [2, 2]]),
        node("Am1", ["single", None], cells=1),
        node("T4a", ["stride", [1, 1]]),
    ]
    edges = [
        edge("R1-R6", "L1", -1, [[[0, 0], 40.0]]),
        edge("L1", "Mi1", 1, [[[0, 0], 30.0], [[1, -1], 2.5]], certainty=1.19),
        edge("Am1", "L1", -1, [[[0, 0], 3.0]], certainty=0.4),
        edge("Mi1", "T4a", 1, [[[0, 0], 12.0], [[-1, 0], 1.0]]),
    ]
    return spec_of(nodes, edges, ["R1-R6"], ["T4a"])


def test_types_are_transcribed_with_their_group_and_sign(small_spec: dict) -> None:
    artifact = build_explorer(small_spec, None)
    by_name = {t["name"]: t for t in artifact["types"]}
    assert [t["name"] for t in artifact["types"]] == ["R1-R6", "L1", "Mi1", "Am1", "T4a"]
    assert by_name["R1-R6"]["group"] == "input" and by_name["R1-R6"]["photoreceptor"]
    assert by_name["T4a"]["group"] == "output"
    assert by_name["Mi1"]["group"] == "stride2"
    assert by_name["Am1"]["group"] == "population"
    # the sign of a type is the sign it sends with; a type that sends nothing has none
    assert by_name["R1-R6"]["sign"] == -1 and by_name["L1"]["sign"] == 1 and by_name["T4a"]["sign"] == 0


def test_connections_are_rows_of_parallel_arrays(small_spec: dict) -> None:
    artifact = build_explorer(small_spec, None)
    assert artifact["version"] == ARTIFACT_VERSION
    assert artifact["connection_fields"] == ["source", "target", "sign", "certainty", "du", "dv", "synapses"]
    source, target, sign, certainty, du, dv, synapses = artifact["connections"][1]
    assert (source, target, sign) == (1, 2, 1)
    # support above 1 is carried as it is: it counts cell pairs per target cell, it is not a probability
    assert certainty == pytest.approx(1.19)
    assert (du, dv, synapses) == ([0, 1], [0, -1], [30.0, 2.5])
    assert artifact["frame"]["release_to_engine"] == -1
    assert artifact["compile"] == {"population_broadcast": True, "target_centric": True}


def test_published_filters_are_matched_through_the_renames(small_spec: dict) -> None:
    reference = {
        "edges": [
            # R1-R6 is named per photoreceptor in the consensus; the alias table maps it back
            {"src": "R1", "tar": "L1", "alpha": -1, "offsets": [[[0, 0], 40.0]]},
            {"src": "Mi1", "tar": "T4a", "alpha": 1, "offsets": [[[0, 0], 10.0]]},
            # a pair the build does not have is left out, not approximated
            {"src": "Tm3", "tar": "T4a", "alpha": 1, "offsets": [[[0, 0], 5.0]]},
        ]
    }
    artifact = build_explorer(small_spec, reference)
    matched = {(p["src"], p["tar"]): p["matches"] for p in artifact["published"]}
    assert matched[("R1", "L1")] == [["R1-R6", "L1"]]
    assert matched[("Mi1", "T4a")] == [["Mi1", "T4a"]]
    assert ("Tm3", "T4a") not in matched


def test_export_is_deterministic_and_the_manifest_describes_it(small_spec: dict, tmp_path: Path) -> None:
    spec_path = tmp_path / "small.json"
    spec_path.write_text(json.dumps(small_spec), encoding="utf-8")
    first = export_explorer(spec_path, None, tmp_path / "a" / "explorer", tmp_path / "a" / "manifests")
    second = export_explorer(spec_path, None, tmp_path / "b" / "explorer", tmp_path / "b" / "manifests")
    assert first == second
    written = (tmp_path / "a" / first["path"]).read_bytes()
    assert len(written) == first["bytes"]
    assert hashlib.sha256(written).hexdigest() == first["sha256"]
    assert first["counts"] == {"types": 5, "connections": 4, "filter_entries": 6, "published_connections": 0}
    assert first["source"]["specification_sha256"] == hashlib.sha256(spec_path.read_bytes()).hexdigest()
    assert "created" not in first


def test_the_committed_artifact_is_what_the_committed_specification_produces(tmp_path: Path) -> None:
    reference = find_reference()
    if reference is None:
        pytest.skip("the published consensus ships with the engine, which is not installed here")
    committed = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rebuilt = export_explorer(SPEC, reference, tmp_path / "explorer", tmp_path / "manifests")
    assert rebuilt["source"]["specification_sha256"] == committed["source"]["specification_sha256"]
    assert rebuilt["reference"]["sha256"] == committed["reference"]["sha256"]
    assert rebuilt["sha256"] == committed["sha256"], "the committed explorer is stale: run export-web"
    assert rebuilt == committed
