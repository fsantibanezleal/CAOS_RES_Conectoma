"""Unit tests for the connectome build: the ingestion contract, signs, and column assignment.

These run on synthetic tables built in the test, never on the multi-gigabyte cache, so they are fast and
run anywhere. The integration test that uses the real release lives in `test_connectome_integration.py`
and skips itself when the cache is absent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data-pipeline"))

from conectoma.connectome.columns import (  # noqa: E402
    UNASSIGNED,
    build_graph,
    hex_distance,
    infer_columns,
    validate_by_holdout,
    weighted_median,
)
from conectoma.connectome.signs import call_sign, majority_sign, normalize  # noqa: E402
from conectoma.io.contract import (  # noqa: E402
    ContractViolation,
    read_feather,
    validate_hex,
    validate_weights,
)

# --- contract 1 ---------------------------------------------------------------------------------


def test_read_feather_rejects_a_table_missing_a_required_column(tmp_path: Path) -> None:
    path = tmp_path / "weights.feather"
    feather.write_feather(pa.table({"body_pre": [1], "body_post": [2]}), path)
    with pytest.raises(ContractViolation, match="missing required columns"):
        read_feather(path, "weights")


def test_read_feather_rejects_a_truncated_file(tmp_path: Path) -> None:
    path = tmp_path / "weights.feather"
    feather.write_feather(pa.table({"body_pre": [1], "body_post": [2], "weight": [3]}), path)
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])  # the exact failure a half-finished download produces
    with pytest.raises(ContractViolation, match="not a readable Arrow file"):
        read_feather(path, "weights")


def test_weights_contract_rejects_non_positive_and_self_loops() -> None:
    report = validate_weights(
        body_pre=[1, 2, 3, 4],
        body_post=[2, 2, 4, 5],
        weight=[5, 7, 0, 3],
    )
    assert report.rows_out == 2
    assert report.rejected["self_loop"] == 1
    assert report.rejected["non_positive_weight"] == 1


def test_hex_contract_flags_missing_and_out_of_range() -> None:
    assert validate_hex(3, -4) is None
    assert validate_hex(None, 2) == "missing_column_coordinate"
    assert validate_hex(3, 900) == "column_coordinate_out_of_range"


# --- signs --------------------------------------------------------------------------------------


def test_normalize_maps_the_release_unknowns_to_none() -> None:
    assert normalize("Acetylcholine") == "acetylcholine"
    assert normalize("unclear") is None
    assert normalize(None) is None


def test_sign_prefers_the_body_call_and_keeps_its_provenance() -> None:
    call = call_sign(1, "gaba", "acetylcholine", 0.9, confidence_threshold=0.5)
    assert (call.sign, call.source, call.low_confidence) == (-1, "body", False)


def test_sign_falls_back_to_the_cell_type_call() -> None:
    call = call_sign(2, None, "glutamate", 0.8, confidence_threshold=0.5)
    assert (call.sign, call.source) == (-1, "cell_type")


def test_sign_without_any_call_is_defaulted_and_flagged() -> None:
    call = call_sign(3, "unclear", None, None, confidence_threshold=0.5)
    assert call.sign == 1
    assert call.source == "default"
    assert call.low_confidence is True


def test_low_confidence_is_flagged_rather_than_dropped() -> None:
    call = call_sign(4, "acetylcholine", "acetylcholine", 0.31, confidence_threshold=0.5)
    assert call.sign == 1
    assert call.low_confidence is True


def test_modulatory_transmitters_are_marked() -> None:
    assert call_sign(5, "dopamine", None, 0.9, confidence_threshold=0.5).modulatory is True
    assert call_sign(6, "acetylcholine", None, 0.9, confidence_threshold=0.5).modulatory is False


def test_majority_sign_breaks_ties_towards_excitatory() -> None:
    assert majority_sign([1, 1, -1]) == 1
    assert majority_sign([-1, -1, 1]) == -1
    assert majority_sign([1, -1]) == 1
    assert majority_sign([]) == 1


# --- column assignment --------------------------------------------------------------------------


def test_weighted_median_follows_the_weight_not_the_count() -> None:
    values = np.array([0, 1, 10])
    assert weighted_median(values, np.array([1.0, 1.0, 1.0])) == 1
    assert weighted_median(values, np.array([1.0, 1.0, 50.0])) == 10


def test_hex_distance_is_the_axial_lattice_distance() -> None:
    assert hex_distance(0, 0, 0, 0) == 0
    assert hex_distance(0, 0, 1, 0) == 1
    assert hex_distance(0, 0, 1, -1) == 1  # a neighbour along the third axis
    assert hex_distance(0, 0, 2, -1) == 2


def _lattice_graph() -> tuple:
    """A small patch of columns: annotated neurons wired within their column, plus one neuron to place.

    Index layout: three annotated neurons per column for twenty five columns, then one unannotated neuron
    per column wired to the three annotated ones. Annotated neurons of a column are wired to each other, as
    they are in the real optic lobe; without that, a held-out type has no placed partner to be re-inferred
    from, and the holdout would measure the fixture rather than the method.
    """
    columns = [(u, v) for u in range(-2, 3) for v in range(-2, 3)]
    per_column = 3
    n_annotated = len(columns) * per_column
    n_total = n_annotated + len(columns)

    hex1 = np.full(n_total, UNASSIGNED, dtype=np.int16)
    hex2 = np.full(n_total, UNASSIGNED, dtype=np.int16)
    type_index = np.zeros(n_total, dtype=np.int32)
    types = ["known0", "known1", "known2", "unknown"]

    pre: list[int] = []
    post: list[int] = []
    weight: list[int] = []

    for column_position, (u, v) in enumerate(columns):
        members = [column_position * per_column + k for k in range(per_column)]
        for slot, node in enumerate(members):
            hex1[node], hex2[node] = u, v
            type_index[node] = slot
        for a in members:
            for b in members:
                if a != b:
                    pre.append(a)
                    post.append(b)
                    weight.append(8)

        target = n_annotated + column_position
        type_index[target] = 3
        for node in members:
            pre.append(node)
            post.append(target)
            weight.append(10)

    graph = build_graph(
        np.asarray(pre, dtype=np.int32),
        np.asarray(post, dtype=np.int32),
        np.asarray(weight, dtype=np.int32),
        n_total,
    )
    return graph, hex1, hex2, type_index, types, n_annotated, len(columns)


def test_infer_columns_places_a_neuron_in_the_column_of_its_partners() -> None:
    graph, hex1, hex2, _, _, n_annotated, n_columns = _lattice_graph()
    result = infer_columns(graph, hex1, hex2, max_rounds=2, min_partners=3)
    assert result.inferred == n_columns
    assert result.unplaced == 0
    for column_position in range(n_columns):
        target = n_annotated + column_position
        partner = column_position * 3
        assert (result.hex1[target], result.hex2[target]) == (hex1[partner], hex2[partner])


def test_infer_columns_refuses_a_neuron_with_too_few_placed_partners() -> None:
    hex1 = np.asarray([UNASSIGNED, 0], dtype=np.int16)
    hex2 = np.asarray([UNASSIGNED, 0], dtype=np.int16)
    graph = build_graph(
        np.asarray([0], dtype=np.int32), np.asarray([1], dtype=np.int32),
        np.asarray([5], dtype=np.int32), 2,
    )
    result = infer_columns(graph, hex1, hex2, max_rounds=2, min_partners=3)
    assert result.inferred == 0
    assert result.unplaced == 1


def test_infer_columns_never_overwrites_an_annotated_coordinate() -> None:
    graph, hex1, hex2, _, _, n_annotated, _ = _lattice_graph()
    result = infer_columns(graph, hex1, hex2, max_rounds=2, min_partners=3)
    annotated = slice(0, n_annotated)
    assert np.array_equal(result.hex1[annotated], hex1[annotated])
    assert np.array_equal(result.hex2[annotated], hex2[annotated])


def test_holdout_validation_reports_the_error_of_the_method() -> None:
    graph, hex1, hex2, type_index, types, _, _ = _lattice_graph()
    report = validate_by_holdout(graph, hex1, hex2, type_index, types, max_rounds=2, min_partners=2)
    assert report["summary"]["types_tested"] == 3
    # partners share a column exactly here, so holding a type out must recover it exactly
    assert report["summary"]["median_exact_fraction"] == 1.0
    assert report["summary"]["worst_p95_error_columns"] == 0.0
