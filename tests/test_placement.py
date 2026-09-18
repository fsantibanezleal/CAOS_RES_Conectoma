"""Which cell types the network has, and where on the lattice each one sits.

Two build decisions are tested here because both changed the network, silently, before they were made
explicit: the spectral subtypes of the inner photoreceptors are pooled into R7 and R8 and placeholder types
are dropped; and a type is laid out at its measured density instead of being collapsed to one node when it
is sparser than the photoreceptors.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data-pipeline"))

from conectoma.connectome.columns import UNASSIGNED  # noqa: E402
from conectoma.connectome.malecns import (  # noqa: E402
    MAX_STRIDE,
    POPULATION_BELOW,
    BuildConfig,
    Selection,
    network_type,
    placement,
    select_neurons,
    to_flyvis_spec,
)
from conectoma.io.contract import IngestReport  # noqa: E402

# --- pooling and placeholders -------------------------------------------------------------------------


def test_spectral_subtypes_pool_into_r7_and_r8() -> None:
    for name in ("R7p", "R7y", "R7d", "R7_unclear"):
        assert network_type(name) == "R7"
    for name in ("R8p", "R8y", "R8d", "R8_unclear"):
        assert network_type(name) == "R8"


def test_pooling_leaves_other_types_and_the_ambiguous_photoreceptor_alone() -> None:
    assert network_type("R1-R6") == "R1-R6"
    assert network_type("L1") == "L1"
    # neither R7 nor R8: must not be pooled into either
    assert network_type("R7R8_unclear") == "R7R8_unclear"


def _annotations(tmp_path: Path) -> Path:
    rows = [
        # body, type, superclass, somaSide, instance, hex1, hex2
        (1, "L1", "ol_intrinsic", "R", "L1_R", 0, 0),
        (2, "R7p", "ol_sensory", None, "R7p_R", None, None),
        (3, "R7y", "ol_sensory", None, "R7y_R", None, None),
        (4, "R8_unclear", "ol_sensory", None, "R8_unclear_R", None, None),
        (5, "R7R8_unclear", "ol_sensory", None, "R7R8_unclear_R", None, None),
        (6, "T4_unclear", "ol_intrinsic", "R", "T4_unclear_R", None, None),
        (7, "Mi1", "ol_intrinsic", "L", "Mi1_L", 1, 0),
    ]
    columns = list(zip(*rows, strict=True))
    table = pa.table({
        "bodyId": pa.array(columns[0], pa.int64()),
        "type": pa.array(columns[1]),
        "class": pa.array(["optic"] * len(rows)),
        "superclass": pa.array(columns[2]),
        "somaSide": pa.array(columns[3]),
        "instance": pa.array(columns[4]),
        "assignedOlHex1": pa.array(columns[5], pa.int64()),
        "assignedOlHex2": pa.array(columns[6], pa.int64()),
    })
    path = tmp_path / "annotations.feather"
    feather.write_feather(table, path)
    return path


def test_selection_pools_subtypes_and_drops_placeholders(tmp_path: Path) -> None:
    selection = select_neurons(_annotations(tmp_path), BuildConfig(side="R"))
    assert selection.types == ["L1", "R7", "R8"]
    assert selection.cells_per_type == Counter({"R7": 2, "L1": 1, "R8": 1})
    assert selection.report.rejected["ambiguous_type"] == 2  # R7R8_unclear and T4_unclear
    assert selection.report.rejected["other_side"] == 1
    assert selection.report.flagged["pooled_spectral_subtype"] == 3


# --- placement by density -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("density", "expected"),
    [
        (2.5, ["stride", [1, 1]]),   # several cells per column, as the pooled outer photoreceptors
        (1.0, ["stride", [1, 1]]),
        (0.55, ["stride", [1, 1]]),  # closer to one per column than to one per four
        (0.42, ["stride", [2, 2]]),
        (0.25, ["stride", [2, 2]]),
        (0.11, ["stride", [3, 3]]),
        (0.06, ["stride", [4, 4]]),
        (0.03, ["single", None]),
        (0.0, ["single", None]),
    ],
)
def test_placement_follows_the_measured_density(density: float, expected: list) -> None:
    assert placement(density) == expected


def test_the_population_threshold_sits_below_the_coarsest_sublattice() -> None:
    assert POPULATION_BELOW < 1.0 / MAX_STRIDE**2
    assert placement(POPULATION_BELOW) == ["stride", [MAX_STRIDE, MAX_STRIDE]]


def _selection(per_type: dict[str, int], columns: int = 100) -> Selection:
    """A selection with the given placed cells per type, spread over `columns` distinct columns."""
    types = sorted(per_type)
    type_index, hex1, hex2 = [], [], []
    for index, name in enumerate(types):
        for cell in range(per_type[name]):
            type_index.append(index)
            hex1.append(cell % columns)
            hex2.append(0)
    n = len(type_index)
    return Selection(
        body_ids=np.arange(n, dtype=np.int64),
        type_index=np.asarray(type_index, dtype=np.int32),
        hex1=np.asarray(hex1, dtype=np.int16),
        hex2=np.asarray(hex2, dtype=np.int16),
        types=types,
        cells_per_type=Counter({t: per_type[t] for t in types}),
        report=IngestReport(table="annotations", rows_in=n, rows_out=n),
    )


def test_spec_places_types_by_density_and_routes_population_edges() -> None:
    selection = _selection({"R1-R6": 100, "Mi": 40, "Pop": 2, "T4a": 100})
    index = {t: i for i, t in enumerate(selection.types)}
    built = {
        "offsets_by_pair": {
            (index["R1-R6"], index["Mi"]): [((0, 0), 4.0, 0.9), ((1, 0), 1.0, 0.5)],
            (index["Mi"], index["T4a"]): [((0, 0), 3.0, 0.8)],
            (index["Pop"], index["T4a"]): [((2, 0), 9.0, 0.1)],  # windowed filter: ignored for populations
        },
        "population_by_pair": {
            (index["Pop"], index["T4a"]): (12.5, 0.6),  # the whole-pair average is what a population sends
            (index["Pop"], index["Mi"]): (0.1, 0.9),    # below the minimum mean: dropped
        },
        "signs_by_type": {"Pop": -1},
    }
    spec = to_flyvis_spec(built, selection, BuildConfig())
    patterns = {n["name"]: n["pattern"] for n in spec["nodes"]}
    assert patterns == {
        "Mi": ["stride", [2, 2]], "Pop": ["single", None], "R1-R6": ["stride", [1, 1]], "T4a": ["stride", [1, 1]],
    }
    edges = {(e["src"], e["tar"]): e for e in spec["edges"]}
    assert edges[("Pop", "T4a")]["offsets"] == [[[0, 0], 12.5]]
    assert edges[("Pop", "T4a")]["alpha"] == -1
    assert ("Pop", "Mi") not in edges
    assert edges[("R1-R6", "Mi")]["offsets"] == [[[0, 0], 4.0], [[1, 0], 1.0]]
    assert spec["compile"] == {"population_broadcast": True, "target_centric": True}
    assert spec["provenance"]["placement"]["columns"] == 100


def test_spec_refuses_an_input_type_that_does_not_occupy_every_column() -> None:
    selection = _selection({"R1-R6": 100, "R7": 30, "L1": 100})
    built = {"offsets_by_pair": {}, "population_by_pair": {}, "signs_by_type": {}}
    with pytest.raises(ValueError, match="input types"):
        to_flyvis_spec(built, selection, BuildConfig())


def test_unplaced_cells_do_not_count_towards_density() -> None:
    selection = _selection({"L1": 100, "Mi": 100})
    selection.hex1[selection.type_index == 1] = UNASSIGNED  # every Mi cell lost its column
    spec = to_flyvis_spec(
        {"offsets_by_pair": {}, "population_by_pair": {}, "signs_by_type": {}}, selection, BuildConfig()
    )
    assert {n["name"]: n["pattern"][0] for n in spec["nodes"]}["Mi"] == "single"
