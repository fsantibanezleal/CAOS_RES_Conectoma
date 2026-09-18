"""Integration checks against the real MaleCNS release and the artifact built from it.

These skip when the local cache or the built artifact is absent, so a clone without the multi-gigabyte
tables still has a green suite. When they do run, they assert the facts this product depends on rather than
re-deriving them: the schema of the release, and the shape and honesty of the committed connectome.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "data-pipeline"))

from conectoma.io.contract import HEX_MAX, HEX_MIN, read_feather  # noqa: E402

ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
ARTIFACT = REPO_ROOT / "data/derived/connectome/malecns-optic-lobe-r.json"
REPORT = REPO_ROOT / "data/derived/connectome/malecns-optic-lobe-r.report.json"


def cache_root() -> Path | None:
    root = os.environ.get("CONECTOMA_DATA_ROOT")
    if not root:
        return None
    path = Path(root) / "malecns"
    return path if path.is_dir() else None


requires_cache = pytest.mark.skipif(cache_root() is None, reason="local connectome cache not present")
requires_artifact = pytest.mark.skipif(not ARTIFACT.is_file(), reason="connectome artifact not built yet")


@requires_cache
def test_release_carries_the_columns_the_contract_declares() -> None:
    table = read_feather(cache_root() / ANNOTATIONS, "annotations")
    for column in ("bodyId", "type", "superclass", "somaSide", "assignedOlHex1", "assignedOlHex2"):
        assert column in table.column_names


@requires_cache
def test_annotated_column_coordinates_are_inside_the_contract_range() -> None:
    table = read_feather(
        cache_root() / ANNOTATIONS, "annotations", columns=["assignedOlHex1", "assignedOlHex2"]
    ).to_pydict()
    values = [v for v in table["assignedOlHex1"] + table["assignedOlHex2"] if v is not None]
    assert values, "the release should carry annotated column coordinates"
    assert min(values) >= HEX_MIN
    assert max(values) <= HEX_MAX


@requires_artifact
def test_artifact_matches_the_schema_the_engine_reads() -> None:
    spec = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for key in ("nodes", "edges", "receptors", "input_units", "output_units", "provenance"):
        assert key in spec

    names = {node["name"] for node in spec["nodes"]}
    assert len(names) == len(spec["nodes"]), "a cell type is declared twice"
    for node in spec["nodes"]:
        kind, args = node["pattern"]
        assert kind in {"stride", "single"}
        if kind == "stride":
            assert args[0] == args[1] and 1 <= args[0] <= 4
        assert node["activation"] == "relu"
        assert not node["name"].endswith("_unclear"), "placeholder types are left out of the network"
        assert 0 <= node["n_cells_placed"] <= node["n_cells"]

    patterns = {node["name"]: node["pattern"] for node in spec["nodes"]}
    for unit in spec["input_units"]:
        assert patterns[unit] == ["stride", [1, 1]], f"input {unit} must occupy every column"
    assert {"R7", "R8"} <= set(spec["input_units"]), "the inner photoreceptors are pooled into R7 and R8"
    assert spec["compile"] == {"population_broadcast": True, "target_centric": True}

    for edge in spec["edges"]:
        assert edge["src"] in names and edge["tar"] in names
        assert edge["alpha"] in (-1, 1)
        assert edge["edge_type"] == "chem"
        assert edge["offsets"], "an edge must carry at least one filter entry"
        for (offset, count) in edge["offsets"]:
            assert len(offset) == 2
            assert count > 0
        if patterns[edge["src"]][0] == "single":
            assert edge["offsets"] == [[[0, 0], edge["offsets"][0][1]]], "a population sends one average"


@requires_artifact
def test_artifact_carries_its_provenance_and_licence() -> None:
    provenance = json.loads(ARTIFACT.read_text(encoding="utf-8"))["provenance"]
    assert provenance["dataset"] == "male-cns:v1.0"
    assert provenance["license"] == "CC-BY"
    assert "Berg" in provenance["citation"]
    assert "Eckstein" in provenance["sign_source"]
    assert provenance["config"]["side"] in {"R", "L"}


@requires_artifact
def test_report_records_what_the_column_inference_actually_achieved() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    inference = report["column_inference"]
    assert inference["inferred"] >= 0
    holdout = inference["holdout"]["summary"]
    # the numbers may be good or bad, but they must exist: a connectome built on inferred coordinates
    # without a measurement of that inference is not auditable
    assert holdout["types_tested"] >= 1
    assert 0.0 <= holdout["median_within_one_fraction"] <= 1.0


COMPARISON = REPO_ROOT / "data/derived/connectome/malecns-optic-lobe-r.comparison.json"
requires_comparison = pytest.mark.skipif(
    not COMPARISON.is_file(), reason="comparison against the published consensus not run yet"
)


@requires_comparison
def test_the_committed_connectome_agrees_with_the_published_consensus() -> None:
    """Acceptance floors for the connectome build.

    These are floors, not targets, and they are deliberately below the measured values (76.0 percent
    recovery, 97.1 percent sign agreement, 0.80 rank correlation at the time of writing). A change that
    drops through a floor is a regression that has to be explained, not silently accepted.
    """
    report = json.loads(COMPARISON.read_text(encoding="utf-8"))
    assert report["types"]["reference_matched"] >= 55
    assert report["connections"]["recovered_fraction"] >= 0.70
    assert report["signs"]["agreement_fraction"] >= 0.95
    assert report["central_synapse_counts"]["spearman"] >= 0.70


@requires_comparison
def test_sign_disagreements_are_listed_rather_than_hidden() -> None:
    report = json.loads(COMPARISON.read_text(encoding="utf-8"))
    disagreeing = report["signs"]["disagreeing"]
    expected = report["signs"]["compared"] - report["signs"]["agreeing"]
    assert len(disagreeing) == min(expected, 50)
    for item in disagreeing:
        assert item["reference"] in (-1, 1) and item["built"] in (-1, 1)
        assert item["reference"] != item["built"]
