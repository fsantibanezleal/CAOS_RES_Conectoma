"""Command line entry point for the offline pipeline. Invoked by path, never installed as a package.

    python data-pipeline/run.py build-connectome --out data/derived/connectome/malecns-optic-lobe-right.json

The heavy input tables are read from the local cache declared by CONECTOMA_DATA_ROOT (or --data-root) and
are never committed; the compact result is.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conectoma.connectome.compare import compare, find_reference, load_spec  # noqa: E402
from conectoma.connectome.malecns import (  # noqa: E402
    BuildConfig,
    accumulate_filters,
    assign_columns,
    build_filters,
    load_signs,
    scan_edges,
    select_neurons,
    to_flyvis_spec,
    write_spec,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
NEUROTRANSMITTERS = "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"


def data_root(explicit: str | None) -> Path:
    root = explicit or os.environ.get("CONECTOMA_DATA_ROOT")
    if not root:
        raise SystemExit(
            "no data root: pass --data-root or set CONECTOMA_DATA_ROOT to the directory holding the "
            "MaleCNS tables (see docs/guides/02_fetch-the-connectome.md)"
        )
    path = Path(root)
    if not path.is_dir():
        raise SystemExit(f"data root is not a directory: {path}")
    return path


def cmd_build_connectome(args: argparse.Namespace) -> int:
    root = data_root(args.data_root) / "malecns"
    config = BuildConfig(
        side=args.side,
        min_mean_synapses=args.min_mean_synapses,
        min_certainty=args.min_certainty,
        max_offset=args.max_offset,
        include_projection_neurons=args.include_projection_neurons,
    )

    started = time.time()
    print(f"[1/6] selecting neurons (side {config.side})")
    selection = select_neurons(root / ANNOTATIONS, config)
    print("     ", selection.report.summary())
    print(f"      {len(selection)} neurons, {len(selection.types)} cell types")

    print("[2/6] assigning synapse signs")
    signs = load_signs(root / NEUROTRANSMITTERS, selection, config)
    low = sum(1 for call in signs.values() if call.low_confidence)
    print(f"      {len(signs)} calls, {low} low confidence")

    print("[3/6] scanning the connection table")
    edges = scan_edges(root / WEIGHTS, selection)
    print(f"      {edges['rows_scanned']} rows scanned, {edges['rows_kept']} inside the selection")

    print("[4/6] assigning retinotopic columns")
    assignment = assign_columns(edges, selection, config)
    validation = assignment["validation"]["summary"]
    print(f"      annotated {assignment['annotated']}, inferred {assignment['inferred']}, "
          f"unplaced {assignment['unplaced']}")
    print(f"      holdout: exact {validation['median_exact_fraction']}, "
          f"within one column {validation['median_within_one_fraction']}, "
          f"worst p95 {validation['worst_p95_error_columns']}")

    print("[5/6] accumulating average filters")
    accumulated = accumulate_filters(edges, selection, config)
    print(f"      {accumulated['edges_placed']} placed edges")

    print("[6/6] building the connectome specification")
    built = build_filters(accumulated, selection, signs, config)
    spec = to_flyvis_spec(built, selection, config)
    spec["provenance"]["column_assignment"] = {
        "annotated": assignment["annotated"],
        "inferred": assignment["inferred"],
        "unplaced": assignment["unplaced"],
        "holdout": validation,
    }

    default_out = REPO_ROOT / "data/derived/connectome" / f"malecns-optic-lobe-{config.side.lower()}.json"
    out = Path(args.out) if args.out else default_out
    write_spec(spec, out)

    report = {
        "elapsed_seconds": round(time.time() - started, 1),
        "neurons": len(selection),
        "cell_types": len(selection.types),
        "nodes": len(spec["nodes"]),
        "edges": len(spec["edges"]),
        "offsets": sum(len(e["offsets"]) for e in spec["edges"]),
        "rows_scanned": accumulated["rows_scanned"],
        "rows_kept": accumulated["rows_kept"],
        "edges_placed": accumulated["edges_placed"],
        "column_assignment": assignment["annotated"],
        "column_inference": {
            "inferred": assignment["inferred"],
            "unplaced": assignment["unplaced"],
            "rounds": assignment["rounds"],
            "holdout": assignment["validation"],
        },
        "ingest": selection.report.as_dict(),
        "dropped_filters": dict(built["dropped"]),
        "sign_disagreement_types": len(built["sign_disagreement"]),
        "config": config.as_dict(),
        "output": str(out.relative_to(REPO_ROOT)) if out.is_relative_to(REPO_ROOT) else str(out),
    }
    report_path = out.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"wrote {out} ({len(spec['nodes'])} nodes, {len(spec['edges'])} edges, "
          f"{report['offsets']} offsets) in {report['elapsed_seconds']}s")
    return 0


def cmd_compare_consensus(args: argparse.Namespace) -> int:
    """Measure this connectome against the published consensus it generalises."""
    built_path = Path(args.built) if args.built else (
        REPO_ROOT / "data/derived/connectome/malecns-optic-lobe-r.json"
    )
    reference_path = Path(args.reference) if args.reference else find_reference()
    if reference_path is None or not Path(reference_path).is_file():
        raise SystemExit(
            "no reference connectome: install the network library, or pass --reference with the path to "
            "its connectome JSON"
        )

    result = compare(load_spec(built_path), load_spec(reference_path))
    result["built"] = str(built_path.name)
    result["reference"] = str(Path(reference_path).name)

    out = Path(args.out) if args.out else built_path.with_suffix(".comparison.json")
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")

    types, connections, signs = result["types"], result["connections"], result["signs"]
    print(f"types: {types['built']} built, {types['reference']} reference, "
          f"{types['reference_matched']} matched")
    print(f"connections: {connections['recovered']}/{connections['reference_comparable']} of the comparable "
          f"reference connections are present here "
          f"(recovered {connections['recovered_fraction']})")
    print(f"signs: {signs['agreeing']}/{signs['compared']} agree "
          f"({signs['agreement_fraction']})")
    print(f"central synapse counts: Spearman {result['central_synapse_counts']['spearman']} "
          f"over {result['central_synapse_counts']['n']} connections")
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run.py", description="Conectoma offline pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-connectome", help="build the consensus optic-lobe connectome")
    build.add_argument("--data-root", default=None, help="directory holding the MaleCNS tables")
    build.add_argument("--out", default=None, help="output JSON path")
    build.add_argument("--side", default="R", choices=["R", "L"], help="which optic lobe")
    build.add_argument("--min-mean-synapses", type=float, default=0.5)
    build.add_argument("--min-certainty", type=float, default=0.02)
    build.add_argument("--max-offset", type=int, default=8)
    build.add_argument("--include-projection-neurons", action="store_true")
    build.set_defaults(func=cmd_build_connectome)

    compare_parser = sub.add_parser(
        "compare-consensus", help="compare the built connectome against the published consensus"
    )
    compare_parser.add_argument("--built", default=None, help="path to the built connectome JSON")
    compare_parser.add_argument("--reference", default=None, help="path to the reference connectome JSON")
    compare_parser.add_argument("--out", default=None, help="where to write the comparison report")
    compare_parser.set_defaults(func=cmd_compare_consensus)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
