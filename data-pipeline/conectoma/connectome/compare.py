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
# - the inner photoreceptors are split by spectral subtype in the release, with an explicit unclear
#   variant; the build pools them back into R7 and R8, and the subtype names stay listed so a build that
#   keeps the split still compares;
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
    "R7": ("R7", "R7p", "R7y", "R7d", "R7_unclear"),
    "R8": ("R8", "R8p", "R8y", "R8d", "R8_unclear"),
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


# -- orientation -------------------------------------------------------------------------------------------

# The twelve symmetries of the hexagonal lattice, in axial coordinates: a permutation of the three axial
# coordinates (u, v, w = -u - v) followed by an optional point reflection. Named by what (u, v) becomes.
_AXES = "uvw"
SYMMETRIES = [
    (perm, sign)
    for perm in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))
    for sign in (1, -1)
]


def symmetry_name(perm: tuple[int, ...], sign: int) -> str:
    return f"{'-' if sign < 0 else '+'}({_AXES[perm[0]]},{_AXES[perm[1]]})"


def apply_symmetry(offset, perm: tuple[int, ...], sign: int) -> tuple[int, int]:
    u, v = offset
    triple = (u, v, -u - v)
    return sign * triple[perm[0]], sign * triple[perm[1]]


def displacement(offsets: dict) -> tuple[float, float] | None:
    """Synapse-weighted mean offset of a filter in Cartesian lattice units, the centre entry excluded.

    It is the direction a target cell's inputs of this type sit in; a filter that is symmetric around the
    centre has none.
    """
    total = sum(n for o, n in offsets.items() if o != (0, 0))
    if total <= 0:
        return None
    x = sum(n * math.sqrt(3) * (o[0] + o[1] / 2) for o, n in offsets.items() if o != (0, 0)) / total
    y = sum(n * 1.5 * o[1] for o, n in offsets.items() if o != (0, 0)) / total
    return x, y


def orientation(built: dict, reference: dict, min_length: float = 0.4) -> dict:
    """How well the spatial layout of the filters agrees with the reference, under each lattice symmetry.

    For every connection present in both with at least three filter entries, the displacement of the
    built filter (after the symmetry) is compared with the reference displacement by the cosine of the angle
    between them, weighted by the reference length; displacements shorter than `min_length` columns carry
    no direction and are skipped. A build in the reference's frame scores highest with the identity. A
    count comparison cannot see a rotated or mirrored frame, which is why this exists.
    """
    built_edges = {(e["src"], e["tar"]): e for e in built["edges"]}
    pairs = []
    for edge in reference["edges"]:
        ref = {tuple(o): n for o, n in edge["offsets"]}
        if len(ref) < 3:
            continue
        for a in aliases_for(edge["src"]):
            for b in aliases_for(edge["tar"]):
                if (a, b) in built_edges and len(built_edges[(a, b)]["offsets"]) >= 3:
                    pairs.append((ref, {tuple(o): n for o, n in built_edges[(a, b)]["offsets"]}))

    scores = {}
    used = 0
    for perm, sign in SYMMETRIES:
        agree = weight = 0.0
        used = 0
        for ref, own in pairs:
            a = displacement(ref)
            b = displacement({apply_symmetry(o, perm, sign): n for o, n in own.items()})
            if a is None or b is None:
                continue
            la, lb = math.hypot(*a), math.hypot(*b)
            if la < min_length or lb < min_length:
                continue
            agree += (a[0] * b[0] + a[1] * b[1]) / lb
            weight += la
            used += 1
        scores[symmetry_name(perm, sign)] = round(agree / weight, 4) if weight else None
    ranked = sorted((v, k) for k, v in scores.items() if v is not None)
    return {
        "filters_compared": used,
        "identity": scores[symmetry_name((0, 1, 2), 1)],
        "best": ranked[-1][1] if ranked else None,
        "by_symmetry": scores,
    }


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
        "orientation": orientation(built, reference),
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
