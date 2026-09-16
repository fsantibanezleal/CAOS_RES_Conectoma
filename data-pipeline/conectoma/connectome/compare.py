"""Compare the connectome built here against the published consensus it generalises.

The reference is the connectome shipped with the connectome-constrained network library: 65 cell types and
605 type-to-type connections, distilled from the FIB-25 and FIB-19 medulla volumes and used for the Nature
2024 result. The connectome built here comes from a different, newer volume (the whole male nervous system)
and covers the whole optic lobe, so the two are not expected to be identical. What they must do is agree
where they overlap, and this module measures that rather than asserting it.

Three numbers matter:

- **sign agreement** on shared connections. The signs come from different evidence: the reference uses
  receptor expression per cell-type pair, this build uses the per-neuron neurotransmitter classifier. A
  disagreement is a real finding about one of the two, not a rounding difference.
- **rank correlation of the central synapse count**. Absolute counts should differ between volumes and
  reconstruction pipelines; the ordering of connection strengths should not.
- **coverage**: which reference connections are missing here, and which strong connections here are absent
  from the reference.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# Cell-type names differ between the two releases, and treating a rename as a missing connection would
# understate the overlap. Every entry below was checked against the annotation table of the newer release:
# the left name exists only in the reference, the right names are what this release calls the same cells.
#
# - the outer photoreceptors are one type here ("R1-R6") where the reference lists six;
# - the inner photoreceptors are split by spectral subtype here, with an explicit unclear variant;
# - the reference counts the wide-field CT1 twice, once per neuropil compartment, because its compartments
#   are electrically separate; this release carries it as one cell;
# - "Am" is "Am1" here.
#
# Reference types with no counterpart at all (Mi3, Mi11, Mi12, Tm28, TmY9) are absent from the annotation
# table of this release: they were renamed or reclassified between volumes, and they are reported as
# unmatched rather than silently mapped onto something similar.
REFERENCE_ALIASES: dict[str, tuple[str, ...]] = {
    "R1": ("R1-R6",),
    "R2": ("R1-R6",),
    "R3": ("R1-R6",),
    "R4": ("R1-R6",),
    "R5": ("R1-R6",),
    "R6": ("R1-R6",),
    "R7": ("R7p", "R7y", "R7d", "R7_unclear"),
    "R8": ("R8p", "R8y", "R8d", "R8_unclear"),
    "CT1(M10)": ("CT1",),
    "CT1(Lo1)": ("CT1",),
    "Am": ("Am1",),
}


def aliases_for(reference_type: str) -> tuple[str, ...]:
    """What this release calls a reference cell type."""
    return REFERENCE_ALIASES.get(reference_type, (reference_type,))


def load_spec(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_reference() -> Path | None:
    """Locate the connectome file that ships with the installed network library, if it is installed."""
    try:
        import flyvis  # noqa: PLC0415
    except ImportError:
        return None
    candidate = Path(flyvis.__file__).parent / "connectome" / "fib25-fib19_v2.2.json"
    return candidate if candidate.is_file() else None


def central_count(edge: dict) -> float:
    """The synapse count at zero offset, which is the comparable quantity between two filter sets."""
    for offset, count in edge["offsets"]:
        if tuple(offset) == (0, 0):
            return float(count)
    return 0.0


def spearman(x: list[float], y: list[float]) -> float | None:
    """Rank correlation without a scipy dependency; None when there is nothing to correlate."""
    n = len(x)
    if n < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        result = [0.0] * n
        position = 0
        while position < n:
            end = position
            while end + 1 < n and values[order[end + 1]] == values[order[position]]:
                end += 1
            average = (position + end) / 2.0 + 1.0
            for index in range(position, end + 1):
                result[order[index]] = average
            position = end + 1
        return result

    rx, ry = ranks(x), ranks(y)
    mean_x, mean_y = sum(rx) / n, sum(ry) / n
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry, strict=True))
    var_x = math.sqrt(sum((a - mean_x) ** 2 for a in rx))
    var_y = math.sqrt(sum((b - mean_y) ** 2 for b in ry))
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y)


def compare(built: dict, reference: dict, strong_threshold: float = 5.0) -> dict:
    """Measure the overlap between the built connectome and the published one.

    A reference connection counts as recovered when any aliased pair of it exists here; the sign and the
    central count are then taken from the strongest matching pair, so a one-to-many rename cannot inflate
    or deflate the agreement.
    """
    built_types = {node["name"] for node in built["nodes"]}
    reference_types = {node["name"] for node in reference["nodes"]}

    matched_reference_types = {
        name for name in reference_types if any(alias in built_types for alias in aliases_for(name))
    }
    unmatched_reference_types = sorted(reference_types - matched_reference_types)

    built_edges = {(e["src"], e["tar"]): e for e in built["edges"]}
    reference_edges = {(e["src"], e["tar"]): e for e in reference["edges"]}

    comparable = [
        pair for pair in reference_edges
        if pair[0] in matched_reference_types and pair[1] in matched_reference_types
    ]

    recovered: dict[tuple[str, str], dict] = {}
    missing: list[tuple[str, str]] = []
    for source, target in comparable:
        candidates = [
            built_edges[(a, b)]
            for a in aliases_for(source) for b in aliases_for(target)
            if (a, b) in built_edges
        ]
        if not candidates:
            missing.append((source, target))
            continue
        recovered[(source, target)] = max(candidates, key=central_count)

    sign_agreements = sum(
        1 for pair, edge in recovered.items() if edge["alpha"] == reference_edges[pair]["alpha"]
    )
    disagreeing = sorted(
        (
            {
                "connection": list(pair),
                "reference": reference_edges[pair]["alpha"],
                "built": edge["alpha"],
            }
            for pair, edge in recovered.items()
            if edge["alpha"] != reference_edges[pair]["alpha"]
        ),
        key=lambda item: item["connection"],
    )

    built_counts = [central_count(edge) for edge in recovered.values()]
    reference_counts = [central_count(reference_edges[pair]) for pair in recovered]
    correlation = spearman(built_counts, reference_counts)

    aliased_reference_pairs = {
        (a, b)
        for source, target in reference_edges
        for a in aliases_for(source) for b in aliases_for(target)
    }
    extra_strong = sorted(
        pair for pair, edge in built_edges.items()
        if pair not in aliased_reference_pairs
        and central_count(edge) >= strong_threshold
        and any(pair[0] in aliases_for(name) for name in matched_reference_types)
        and any(pair[1] in aliases_for(name) for name in matched_reference_types)
    )

    return {
        "types": {
            "built": len(built_types),
            "reference": len(reference_types),
            "reference_matched": len(matched_reference_types),
            "reference_unmatched": unmatched_reference_types,
        },
        "connections": {
            "reference_comparable": len(comparable),
            "recovered": len(recovered),
            "recovered_fraction": round(len(recovered) / len(comparable), 4) if comparable else None,
            "missing_here": [list(pair) for pair in sorted(missing)[:50]],
            "missing_here_total": len(missing),
            "strong_connections_absent_from_reference": [list(pair) for pair in extra_strong[:50]],
            "strong_connections_absent_from_reference_total": len(extra_strong),
        },
        "signs": {
            "compared": len(recovered),
            "agreeing": sign_agreements,
            "agreement_fraction": round(sign_agreements / len(recovered), 4) if recovered else None,
            "disagreeing": disagreeing,
        },
        "central_synapse_counts": {
            "spearman": round(correlation, 4) if correlation is not None else None,
            "n": len(recovered),
        },
    }
