"""Contract 1, ingestion: the MaleCNS connectome tables.

A table is accepted only if it carries the columns this product reads, with the types and ranges it
declares. Rows that violate the contract are rejected with a reason and counted; rows that are plausible
but suspicious are flagged, and the flags travel into the manifest so a later result can be read against
them. Nothing is silently coerced.

Source: Janelia MaleCNS v1.0 (`male-cns:v1.0`), CC-BY, released as Apache Arrow Feather tables.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather

# Columns this product reads, per table. A table may carry more; it may not carry fewer.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "annotations": (
        "bodyId", "type", "class", "superclass", "somaSide", "assignedOlHex1", "assignedOlHex2",
    ),
    "neurotransmitters": (
        "body", "consensus_nt", "celltype_predicted_nt", "celltype_predicted_nt_confidence",
    ),
    "weights": ("body_pre", "body_post", "weight"),
}

# A synapse count is a positive integer. Zero or negative is a corrupt row, not a weak connection.
MIN_WEIGHT = 1

# Below this, the neurotransmitter call is recorded as low confidence and the sign it implies is flagged.
# The classifier reports 87 percent accuracy per synapse and 94 percent per neuron (Eckstein et al., Cell,
# 2024), so a sign is an input with a known error rate, never a ground truth.
NT_CONFIDENCE_FLAG = 0.5

# The optic-lobe hexagonal coordinate system of the release. Columns outside this range are rejected as
# corrupt rather than clipped; the observed range is asserted by the ingest test against the real table.
HEX_MIN, HEX_MAX = -60, 60


@dataclass
class IngestReport:
    """What the contract accepted, rejected and flagged, for one table."""

    table: str
    rows_in: int
    rows_out: int
    rejected: Counter = field(default_factory=Counter)
    flagged: Counter = field(default_factory=Counter)

    @property
    def rows_rejected(self) -> int:
        return sum(self.rejected.values())

    def as_dict(self) -> dict:
        return {
            "table": self.table,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "rows_rejected": self.rows_rejected,
            "rejected": dict(self.rejected),
            "flagged": dict(self.flagged),
        }

    def summary(self) -> str:
        parts = [f"{self.table}: {self.rows_out}/{self.rows_in} rows accepted"]
        if self.rejected:
            parts.append("rejected " + ", ".join(f"{k}={v}" for k, v in sorted(self.rejected.items())))
        if self.flagged:
            parts.append("flagged " + ", ".join(f"{k}={v}" for k, v in sorted(self.flagged.items())))
        return "; ".join(parts)


class ContractViolation(RuntimeError):
    """The table itself is unusable: missing columns, or not the declared format."""


def read_feather(path: Path, table: str, columns: list[str] | None = None) -> pa.Table:
    """Read a declared table and check its schema before any row is interpreted."""
    if not path.is_file():
        raise ContractViolation(f"{table}: file not found: {path}")
    try:
        data = feather.read_table(path, columns=columns)
    except pa.ArrowInvalid as exc:  # truncated download, wrong format, corrupted cache
        raise ContractViolation(f"{table}: not a readable Arrow file ({exc}): {path}") from exc

    required = REQUIRED_COLUMNS[table]
    present = set(data.column_names)
    missing = [c for c in required if c not in present and (columns is None or c in columns)]
    if missing:
        raise ContractViolation(f"{table}: missing required columns {missing}")
    return data


def validate_weights(body_pre: list[int], body_post: list[int], weight: list[int]) -> IngestReport:
    """Reject non-positive or self-loop edges; keep the rest."""
    report = IngestReport(table="weights", rows_in=len(weight), rows_out=0)
    for pre, post, w in zip(body_pre, body_post, weight, strict=True):
        if w is None or w < MIN_WEIGHT:
            report.rejected["non_positive_weight"] += 1
            continue
        if pre is None or post is None:
            report.rejected["missing_body_id"] += 1
            continue
        if pre == post:
            report.rejected["self_loop"] += 1
            continue
        report.rows_out += 1
    return report


def validate_hex(hex1: int | None, hex2: int | None) -> str | None:
    """Return a rejection reason for an optic-lobe column coordinate, or None if it is usable."""
    if hex1 is None or hex2 is None:
        return "missing_column_coordinate"
    if not (HEX_MIN <= hex1 <= HEX_MAX and HEX_MIN <= hex2 <= HEX_MAX):
        return "column_coordinate_out_of_range"
    return None
