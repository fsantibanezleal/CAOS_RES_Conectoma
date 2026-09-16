"""Unit tests for the comparison against the published consensus.

The comparison is the acceptance evidence of the connectome build, so its own arithmetic is tested on
synthetic specifications where the right answer is known by construction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data-pipeline"))

from conectoma.connectome.compare import aliases_for, central_count, compare, spearman  # noqa: E402


def node(name: str) -> dict:
    return {"name": name, "pattern": ["stride", [1, 1]], "activation": "relu"}


def edge(src: str, tar: str, alpha: int, central: float, extra: list | None = None) -> dict:
    offsets = [[[0, 0], central]] + (extra or [])
    return {"src": src, "tar": tar, "alpha": alpha, "offsets": offsets, "edge_type": "chem"}


def test_central_count_reads_the_zero_offset_entry() -> None:
    assert central_count(edge("A", "B", 1, 12.0, [[[1, 0], 3.0]])) == 12.0
    assert central_count({"offsets": [[[1, 0], 3.0]]}) == 0.0


def test_spearman_is_one_for_a_monotone_relation_and_none_when_undefined() -> None:
    assert spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]) == pytest.approx(1.0)
    assert spearman([1.0, 2.0, 3.0, 4.0], [40.0, 30.0, 20.0, 10.0]) == pytest.approx(-1.0)
    assert spearman([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None  # no variance on one side
    assert spearman([1.0], [2.0]) is None  # not enough points


def test_aliases_map_the_renamed_types_and_pass_others_through() -> None:
    assert aliases_for("R1") == ("R1-R6",)
    assert aliases_for("CT1(M10)") == ("CT1",)
    assert aliases_for("Mi1") == ("Mi1",)


def test_comparison_counts_recovery_agreement_and_correlation() -> None:
    reference = {
        "nodes": [node("R1"), node("L1"), node("Mi1"), node("Ghost")],
        "edges": [
            edge("R1", "L1", -1, 40.0),
            edge("L1", "Mi1", -1, 80.0),
            edge("Mi1", "L1", 1, 10.0),
            edge("Ghost", "L1", 1, 5.0),  # a type this release does not carry
        ],
    }
    built = {
        "nodes": [node("R1-R6"), node("L1"), node("Mi1")],
        "edges": [
            edge("R1-R6", "L1", -1, 30.0),   # alias of the reference connection, sign agrees
            edge("L1", "Mi1", 1, 90.0),      # sign disagrees
            # Mi1 to L1 is absent here
            edge("Mi1", "R1-R6", 1, 9.0),    # present here, absent from the reference
        ],
    }

    result = compare(built, reference, strong_threshold=5.0)

    assert result["types"]["reference_matched"] == 3          # R1 via its alias, L1, Mi1; not Ghost
    assert result["types"]["reference_unmatched"] == ["Ghost"]
    assert result["connections"]["reference_comparable"] == 3  # the Ghost connection is not comparable
    assert result["connections"]["recovered"] == 2
    assert result["connections"]["missing_here"] == [["Mi1", "L1"]]
    assert result["signs"]["compared"] == 2
    assert result["signs"]["agreeing"] == 1
    assert result["signs"]["disagreeing"][0]["connection"] == ["L1", "Mi1"]
    assert result["central_synapse_counts"]["n"] == 2
    assert result["connections"]["strong_connections_absent_from_reference"] == [["Mi1", "R1-R6"]]


def test_comparison_takes_the_strongest_match_of_a_one_to_many_rename() -> None:
    reference = {"nodes": [node("R7"), node("Dm8")], "edges": [edge("R7", "Dm8", 1, 20.0)]}
    built = {
        "nodes": [node("R7p"), node("R7y"), node("Dm8")],
        "edges": [edge("R7p", "Dm8", 1, 5.0), edge("R7y", "Dm8", 1, 25.0)],
    }
    result = compare(built, reference)
    assert result["connections"]["recovered"] == 1
    assert result["signs"]["agreement_fraction"] == 1.0
