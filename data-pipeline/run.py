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
from conectoma.core.jsonio import write_json  # noqa: E402

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


def write_report(report: dict, path: Path) -> Path:
    """Numpy values made plain and the file replaced in one step (conectoma.core.jsonio)."""
    return write_json(path, report)


def cmd_parity_published(args: argparse.Namespace) -> int:
    """Rebuild the published model through this product's path and check it against the engine's."""
    from conectoma.network.parity import (
        ENSEMBLE_SIZE,
        ensemble_tuning,
        parity_log,
        pipeline_crosscheck,
        voltage_parity,
    )
    from conectoma.network.tuning import moving_edges

    started = time.time()
    runs = parity_log(moving_edges())
    if runs.steps:
        print(f"      resuming: {len(runs.steps)} finished steps in {runs.path}")
    print("[1/3] voltage parity, engine loader against this product's builder")
    voltages = []
    for model in args.parity_models:
        result = voltage_parity(model, runs=runs)
        voltages.append(result)
        print(f"      {result['model']}: max |dV| {result['max_abs_difference']:.3g} over {result['cells']} "
              f"cells, passed {result['passed']}")
    count = args.ensemble_models or ENSEMBLE_SIZE
    print(f"[2/3] motion tuning of {count} published models, built through this product's path")
    tuning = ensemble_tuning([f"{i:03d}" for i in range(count)], log=print, runs=runs)
    print("[3/3] the same models through the engine's own end-to-end pipeline")
    per_model = {row["model"]: row["tuning"] for row in tuning["per_model"]}
    checked = [model for model in args.crosscheck_models if model in per_model]
    crosscheck = pipeline_crosscheck(per_model, checked, runs=runs)
    print(f"      largest DSI difference {crosscheck['largest_dsi_difference']}, largest direction "
          f"difference {crosscheck['largest_direction_difference_degrees']} degrees")
    report = {
        "elapsed_seconds": round(time.time() - started, 1),
        "reused_steps": len(runs.reused),
        "voltage_parity": voltages,
        "tuning": tuning,
        "pipeline_crosscheck": crosscheck,
    }
    out = Path(args.out) if args.out else REPO_ROOT / "data/derived/network/parity-published.json"
    write_report(report, out)
    for cell_type, row in tuning["summary"].items():
        print(f"      {cell_type}: median DSI {row['median_dsi']}, median distance to known "
              f"{row['median_distance_to_known_degrees']} deg, "
              f"within 45 deg {row['share_within_45_degrees']}")
    print(f"wrote {out}")
    passed = all(v["passed"] for v in voltages) and crosscheck["largest_dsi_difference"] <= 1e-3
    return 0 if passed else 1


def cmd_characterize_connectome(args: argparse.Namespace) -> int:
    """Stability, cost, motion tuning and null controls of the built connectome as a frozen network."""
    from conectoma.network.characterize import characterize

    spec = Path(args.spec) if args.spec else REPO_ROOT / "data/derived/connectome/malecns-optic-lobe-r.json"
    started = time.time()
    report = characterize(spec, seeds=tuple(range(args.seeds)))
    report["elapsed_seconds"] = round(time.time() - started, 1)
    out = Path(args.out) if args.out else spec.with_suffix(".characterization.json")
    write_report(report, out)
    print(f"wrote {out} in {report['elapsed_seconds']}s")
    return 0


def models_root() -> Path:
    root = os.environ.get("CONECTOMA_MODELS_ROOT")
    if not root:
        raise SystemExit("set CONECTOMA_MODELS_ROOT (see docs/guides/03_network-engine.md)")
    return Path(root)


VISUAL_CNS_SUMMARY = REPO_ROOT / "data/derived/connectome/malecns-visual-cns.summary.json"


def cmd_build_visual_cns(args: argparse.Namespace) -> int:
    """The whole visual system as a neuron-level graph, written outside git with a committed summary."""
    from conectoma.connectome.visual_cns import VisualCNSConfig, build_visual_system, write_graph

    started = time.time()
    config = VisualCNSConfig(min_weight=args.min_weight)
    arrays, summary = build_visual_system(
        data_root(args.data_root) / "malecns", config, ANNOTATIONS, NEUROTRANSMITTERS, WEIGHTS,
    )
    default_out = models_root() / "specs" / f"malecns-visual-cns-w{args.min_weight}.npz"
    out = Path(args.out) if args.out else default_out
    digest = write_graph(arrays, out)
    summary.update({
        "graph": out.name,
        "graph_bytes": out.stat().st_size,
        "digest": digest,
        "elapsed_seconds": round(time.time() - started, 1),
        "provenance": {
            "dataset": "male-cns:v1.0",
            "license": "CC-BY",
            "sign_source": "Eckstein et al., Cell, 2024, doi:10.1016/j.cell.2024.03.016",
        },
    })
    summary_path = Path(args.summary) if args.summary else VISUAL_CNS_SUMMARY
    write_json(summary_path, summary)
    print(f"wrote {out} ({summary['neurons']} neurons, {summary['connections']} connections, "
          f"{summary['graph_bytes'] / 1e6:.0f} MB) and {summary_path.name} in {summary['elapsed_seconds']}s")
    return 0


def cmd_characterize_visual_cns(args: argparse.Namespace) -> int:
    """Stability, simulation cost and memory of the neuron-level network, and the cost of R1."""
    from conectoma.network.visual_cns_character import characterize_visual_cns

    graph = Path(args.graph) if args.graph else models_root() / "specs" / "malecns-visual-cns-w1.npz"
    started = time.time()
    report = characterize_visual_cns(graph)
    report["elapsed_seconds"] = round(time.time() - started, 1)
    out = Path(args.out) if args.out else (
        REPO_ROOT / "data/derived/connectome/malecns-visual-cns.characterization.json"
    )
    write_json(out, report)
    print(f"wrote {out} in {report['elapsed_seconds']}s")
    return 0


def cmd_export_web(args: argparse.Namespace) -> int:
    """Contract 2: the compact artifacts the web reads, each with a manifest."""
    from conectoma.stages.export_web import export_explorer

    spec = Path(args.spec) if args.spec else REPO_ROOT / "data/derived/connectome/malecns-optic-lobe-r.json"
    reference_path = Path(args.reference) if args.reference else find_reference()
    manifest = export_explorer(
        spec, reference_path, REPO_ROOT / "data/derived/explorer", REPO_ROOT / "data/derived/manifests",
    )
    counts = manifest["counts"]
    print(f"wrote {manifest['path']} ({manifest['bytes'] / 1e6:.2f} MB): {counts['types']} types, "
          f"{counts['connections']} connections, {counts['published_connections']} published matches")
    return 0


def cmd_fetch_vision(args: argparse.Namespace) -> int:
    """Fetch a vision source into the data root (resumable; see docs/guides/05_vision-data.md)."""
    from conectoma.stages.vision_data import fetch_tartanair

    if args.source == "sintel":
        from conectoma.stages.vision_data import fetch_sintel

        summary = fetch_sintel()
        print(f"sintel: {summary['rendered_sequences']} rendered sequences at {summary['rendered_dir']}")
        return 0
    root = data_root(args.data_root)
    if args.source == "spring":
        from conectoma.stages.vision_data import fetch_spring

        summary = fetch_spring(root, args.workers)
        print(f"spring: {summary['clips']} clips planned, {summary['written']} written, "
              f"{summary['bytes'] / 1e9:.1f} GB; failed {summary['failed']}, missing {summary['missing']}")
        return 1 if summary["failed"] else 0
    if args.source == "hypersim":
        from conectoma.stages.vision_data import fetch_hypersim

        summary = fetch_hypersim(root, args.workers)
        print(f"hypersim: {summary['images']} images in {summary['scenes']} scenes, "
              f"{summary['written']} written, {summary['bytes'] / 1e9:.1f} GB; "
              f"failed {summary['failed']}, missing {summary['missing']}")
        return 1 if summary["failed"] else 0
    if args.source == "panorama":
        from conectoma.stages.vision_data import fetch_panorama

        summary = fetch_panorama(root, min(args.workers, 4))
        print(f"panorama: {summary['clips']} panoramas for C13, {summary['written']} written, "
              f"{summary['skipped']} already present; failed {summary['failed']}, "
              f"missing {summary['missing']}")
        return 1 if summary["failed"] or summary["missing"] or not summary["clips"] else 0
    summary = fetch_tartanair(root, args.environments, args.workers)
    print(f"tartanair: {summary['clips']} clips from {summary['pairs']} environment-difficulty pairs, "
          f"{summary['bytes'] / 1e9:.1f} GB; failed {summary['failed']}, missing {summary['missing']}")
    return 1 if summary["failed"] else 0


def cmd_render_vision(args: argparse.Namespace) -> int:
    """Render the fetched clips onto the lattice and check them against contract 1."""
    from conectoma.stages.vision_render import render_source

    summary = render_source(data_root(args.data_root), args.source, args.workers)
    print(f"{args.source}: {summary['accepted']} of {summary['clips']} clips rendered and accepted, "
          f"{summary['rejected']} rejected, {summary['failed']} failed")
    # a rejection is contract 1 doing its job (listed with its reasons in the manifest); a failure is not
    return 1 if summary["failed"] else 0


def cmd_build_splits(args: argparse.Namespace) -> int:
    """Assign rendered clips to splits by geometry family and run the leakage test (the U4 gate)."""
    from conectoma.stages.vision_splits import build_splits

    summary = build_splits(data_root(args.data_root))
    for name, counts in summary["counts"].items():
        print(f"{name:12s} {counts['families']:3d} families {counts['environments']:3d} environments "
              f"{counts['clips']:5d} clips {counts['frames']:6d} frames")
    problems = summary["leakage"]["problems"]
    print("leakage: none" if not problems else "LEAKAGE: " + "; ".join(problems))
    return 1 if problems else 0


def cmd_build_cases(args: argparse.Namespace) -> int:
    """Render every case at its six levels (contract 1), and write the committed case summary."""
    from conectoma.network.engine import engine_root
    from conectoma.stages.vision_cases import build_cases

    engine = engine_root()
    summary = build_cases(data_root(args.data_root), engine.parent if engine else None, args.workers,
                          args.cases or None)
    print(f"cases: {summary['cases']} cases, {summary['clips']} clips, {summary['renderings']} renderings, "
          f"{summary['rejected']} rejected, {summary['failed']} failed, "
          f"{summary['elapsed_seconds'] / 60:.1f} min"
          + ("" if summary["complete"] else " (partial: no summary)"))
    return 1 if summary["rejected"] or summary["failed"] else 0


def cmd_export_eyeclips(args: argparse.Namespace) -> int:
    """The eye's input for the web: one compact file per case and their manifest (contract 2)."""
    from conectoma.stages.export_eyeclips import export_eyeclips

    manifest = export_eyeclips(data_root(args.data_root), REPO_ROOT / "data/derived/vision/cases.json",
                               REPO_ROOT / "data/derived/eyeclips", REPO_ROOT / "data/derived/manifests")
    total = sum(f["bytes"] for f in manifest["cases"].values())
    print(f"eyeclips: {len(manifest['cases'])} case files, {total / 1e6:.1f} MB")
    return 0


def cmd_summarize_vision(args: argparse.Namespace) -> int:
    """One committed summary of the vision lane: sources, renderings, splits and cases."""
    from conectoma.stages.vision_summary import summarize_vision

    summary = summarize_vision(data_root(args.data_root), models_root())
    for name, source in summary["sources"].items():
        print(f"{name:10s} " + ", ".join(f"{k} {v}" for k, v in source.items()
                                         if k in ("clips", "accepted", "rejected", "sequences", "ommatidia")))
    return 0


def cmd_case_docs(args: argparse.Namespace) -> int:
    """Write the generated tables of the case pages from the committed case summary."""
    from conectoma.vision import case_docs

    summary = json.loads((REPO_ROOT / "data/derived/vision/cases.json").read_text(encoding="utf-8"))
    changed = case_docs.update(summary, REPO_ROOT / "docs", write=not args.check)
    print(("out of date: " if args.check else "rewrote: ") + (", ".join(changed) or "nothing"))
    return 1 if args.check and changed else 0


def cmd_fetch_stereo(args: argparse.Namespace) -> int:
    """Fetch the right camera of the TartanAir clips the cases draw (the stereo pair M02 needs)."""
    import yaml
    from conectoma.vision import stereo
    from conectoma.vision.clipstore import FetchLog

    config = yaml.safe_load((REPO_ROOT / "data-pipeline/config/vision.yaml").read_text(encoding="utf-8"))
    clips = stereo.case_clips(REPO_ROOT / "data/derived/vision/cases.json", args.cases,
                              config["tartanair"]["clip_length"])
    if not clips:
        print("no TartanAir clips selected: nothing to fetch")
        return 1
    base = data_root(args.data_root) / "vision" / "tartanair"
    log = FetchLog(base / "stereo-fetch-log.jsonl")
    try:
        report = stereo.fetch(config["tartanair"], clips, base / "stereo", log, args.workers)
    finally:
        log.close()
    print(f"stereo: {report['written']} clips written, {report['skipped']} already there, "
          f"{report['bytes'] / 1e9:.2f} GB, {len(report['failed'])} failed")
    return 1 if report["failed"] or report["missing"] else 0


def cmd_cache_activity(args: argparse.Namespace) -> int:
    """Run a frozen network over the corpus once and keep what a readout needs."""
    from conectoma.stages import cache_activity

    root = data_root(args.data_root)
    if args.cases:
        clips = cache_activity.case_clips(root)
    else:
        clips = []
        for split in args.splits:
            clips += cache_activity.split_clips(root, split, args.limit)
    if not clips:
        print("no clips to cache")
        return 1
    report = cache_activity.run(root, clips, arm=args.arm, seed=args.seed, regime=args.regime,
                                transfer=not args.no_transfer)
    print(f"{args.arm}: {report['written']} cached, {report['skipped']} already there, "
          f"{report['seconds']} s")
    return 0


def cmd_train_readout(args: argparse.Namespace) -> int:
    """Fit a readout head on cached activity, one arm and one seed at a time."""
    from conectoma.stages import train_readout

    root = data_root(args.data_root)
    for seed in args.seeds:
        record = train_readout.train(root, arm=args.arm, seed=seed, window=args.window,
                                     steps=args.steps, batch=args.batch,
                                     out_dir=Path(args.out_dir) if args.out_dir else None)
        best = record["best"]["validation"]
        print(f"{args.arm} seed {seed}: {record['parameters']} parameters, {record['seconds']} s, "
              f"best validation silog {best['silog']:.4f} absrel {best['abs_rel']:.3f} "
              f"boundary {best['boundary_accuracy']:.3f}")
    return 0


def cmd_train_network(args: argparse.Namespace) -> int:
    """Train the network itself in a biophysical regime, together with the head that reads it."""
    from conectoma.stages import train_network

    root = data_root(args.data_root)
    out_dir = Path(args.out_dir) if args.out_dir else None
    shared = {"regime": args.regime, "window": args.window, "train_clips": args.train_clips,
              "out_dir": out_dir}
    if args.steps is not None:
        shared["steps"] = args.steps
    if args.batch is not None:
        shared["batch"] = args.batch
    rate = args.network_lr
    if rate is None:
        # the first seed resolves the arm's learning rate on the validation split and IS that seed's run
        chosen = train_network.choose_rate(root, arm=args.arm, seed=args.seeds[0], **shared)
        rate = chosen["chosen"]
        print(f"{args.regime} {args.arm}: network lr {rate:g} chosen on validation "
              f"(silog {chosen['validation_silog']:.4f}); grid "
              + ", ".join(f"{row['network_learning_rate']:g}:{row['validation_silog']:.4f}"
                          for row in chosen["grid"]))
        remaining = args.seeds[1:]
    else:
        remaining = args.seeds
    for seed in remaining:
        record = train_network.train(root, arm=args.arm, seed=seed, network_learning_rate=rate, **shared)
        best = record["best"]["validation"]
        print(f"{args.regime} {args.arm} seed {seed}: {record['network_parameters']} network + "
              f"{record['head_parameters']} head parameters, {record['seconds']} s "
              f"({record['seconds_per_step']} s/step), best validation silog {best['silog']:.4f} "
              f"absrel {best['abs_rel']:.3f} boundary {best['boundary_accuracy']:.3f}")
    return 0


def cmd_cache_trained(args: argparse.Namespace) -> int:
    """Cache the activity of networks that were TRAINED, one cache per arm and seed."""
    from conectoma.stages import cache_activity, train_network

    root = data_root(args.data_root)
    out_dir = Path(args.out_dir) if args.out_dir else None
    clips = cache_activity.case_clips(root) if args.cases else [
        (cache_activity.clip_key(path), path) for split in args.splits
        for path in cache_activity.split_clips(root, split, args.limit)]
    if not clips:
        print("no clips to cache")
        return 1
    paths = [p for seed in args.seeds
             for p in [train_network.checkpoint_path(args.regime, args.arm, seed, args.window, out_dir)]
             if p.exists()]
    if not paths:
        print(f"no trained {args.regime} checkpoint for arm {args.arm}")
        return 1
    for path in paths:
        network, _, record = train_network.load(path)
        stamp = {
            "cache_version": cache_activity.CACHE_VERSION, "arm": record["arm"], "seed": record["seed"],
            "regime": record["regime"], "transfer": True, "trained": True,
            "spec_sha256": record["spec_sha256"], "code_sha256": record["code_sha256"],
            "dt_s": record["dt_s"], "interval_s": record["interval_s"], "types": record["types"],
            "description": f"{record['description']}, trained in regime {record['regime']}",
            "checkpoint": path.name,
        }
        key = train_network.cache_arm(record["regime"], record["arm"], record["seed"])
        report = cache_activity.cache_with(network, stamp, root, clips, key,
                                           interval_s=record["interval_s"], dt_s=record["dt_s"])
        print(f"{key}: {report['written']} cached, {report['skipped']} already there, "
              f"{report['seconds']} s")
        del network
    return 0


def cmd_export_brainclips(args: argparse.Namespace) -> int:
    """What the connectome does with each case's clip, for the web (contract 2)."""
    from conectoma.stages import export_brainclips

    manifest = export_brainclips.run(data_root(args.data_root), cases_wanted=args.cases,
                                     levels=args.levels, arm=args.arm)
    total = sum(entry["bytes"] for entry in manifest["cases"].values())
    print(f"brainclips: {len(manifest['cases'])} cases, {len(manifest['types'])} cell types, "
          f"{total / 1e6:.1f} MB")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Score a method over the case clips and write its report."""
    from conectoma.stages.evaluate import compare, run

    report = run(data_root(args.data_root), args.method, cases_wanted=args.cases,
                 levels_wanted=args.levels, clips=args.clips, workers=args.workers)
    print(f"{args.method}: {report['clips_scored']} clips in {report['seconds']} s")
    for case_id, case in report["cases"].items():
        first = case["levels"][0]
        if "skipped" in first:
            print(f"  {case_id} {case['name']:22s} skipped: {first['skipped']}")
        elif case["observable"]:
            print(f"  {case_id} {case['name']:22s} coverage {first.get('coverage', 0):.2f} "
                  f"AbsRel {first.get('abs_rel', float('nan')):.4f} "
                  f"delta1 {first.get('delta_1', float('nan')):.3f}")
        else:
            print(f"  {case_id} {case['name']:22s} refused {first.get('refusal_refused', 0):.3f} "
                  f"(nothing to measure: the grade IS the refusal)")
    if args.against:
        paired = compare(args.method, args.against, key=args.key)
        print(f"paired {args.key}, {args.method} minus {args.against}: median {paired['median']:.4f} "
              f"[{paired['low']:.4f}, {paired['high']:.4f}] over {paired['pairs']} clips")
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

    parity = sub.add_parser(
        "parity-published", help="rebuild the published model through this product's path and check it"
    )
    parity.add_argument("--parity-models", nargs="+", default=["000", "001", "002"],
                        help="models of the published ensemble for the voltage comparison")
    parity.add_argument("--crosscheck-models", nargs="+", default=["004", "009", "022"],
                        help="models also run through the engine's own end-to-end pipeline")
    parity.add_argument("--ensemble-models", type=int, default=None,
                        help="how many ensemble models to characterise (default: all fifty)")
    parity.add_argument("--out", default=None, help="where to write the parity report")
    parity.set_defaults(func=cmd_parity_published)

    character = sub.add_parser(
        "characterize-connectome", help="stability, cost, tuning and null controls of the frozen network"
    )
    character.add_argument("--spec", default=None, help="connectome JSON (default: the right optic lobe)")
    character.add_argument("--seeds", type=int, default=5, help="seeds per null control")
    character.add_argument("--out", default=None, help="where to write the characterisation report")
    character.set_defaults(func=cmd_characterize_connectome)

    web = sub.add_parser("export-web", help="the compact artifacts the web reads, with manifests")
    web.add_argument("--spec", default=None, help="connectome JSON (default: the right optic lobe)")
    web.add_argument("--reference", default=None, help="published consensus JSON (default: the engine's)")
    web.set_defaults(func=cmd_export_web)

    fetch = sub.add_parser("fetch-vision", help="fetch a vision source's selected members into the data root")
    fetch.add_argument("--source", default="tartanair",
                       choices=["tartanair", "sintel", "spring", "hypersim", "panorama"])
    fetch.add_argument("--data-root", default=None, help="directory of the local data cache")
    fetch.add_argument("--environments", nargs="*", default=None, help="restrict to these environments")
    fetch.add_argument("--workers", type=int, default=12, help="parallel member requests")
    fetch.set_defaults(func=cmd_fetch_vision)

    render = sub.add_parser("render-vision", help="render fetched clips onto the lattice (contract 1)")
    render.add_argument("--source", default="tartanair", choices=["tartanair", "spring", "hypersim"])
    render.add_argument("--data-root", default=None, help="directory of the local data cache")
    render.add_argument("--workers", type=int, default=4, help="parallel rendering processes")
    render.set_defaults(func=cmd_render_vision)

    split = sub.add_parser("build-splits", help="assign clips to splits by geometry family; leakage test")
    split.add_argument("--data-root", default=None, help="directory of the local data cache")
    split.set_defaults(func=cmd_build_splits)

    case = sub.add_parser("build-cases", help="render every case at its six levels; the committed summary")
    case.add_argument("--data-root", default=None, help="directory of the local data cache")
    case.add_argument("--cases", nargs="*", default=None, help="only these cases (C01 ... C16)")
    case.add_argument("--workers", type=int, default=4, help="parallel rendering processes")
    case.set_defaults(func=cmd_build_cases)

    eyeclips = sub.add_parser("export-eyeclips", help="the eye's input per case for the web (contract 2)")
    eyeclips.add_argument("--data-root", default=None, help="directory of the local data cache")
    eyeclips.set_defaults(func=cmd_export_eyeclips)

    vsummary = sub.add_parser("summarize-vision", help="the committed summary of the vision lane")
    vsummary.add_argument("--data-root", default=None, help="directory of the local data cache")
    vsummary.set_defaults(func=cmd_summarize_vision)

    stereo_parser = sub.add_parser("fetch-stereo",
                                   help="the right camera of the case clips, for the stereo method")
    stereo_parser.add_argument("--data-root", default=None, help="directory of the local data cache")
    stereo_parser.add_argument("--cases", nargs="*", default=None, help="only these cases")
    stereo_parser.add_argument("--workers", type=int, default=12, help="parallel member fetches")
    stereo_parser.set_defaults(func=cmd_fetch_stereo)

    cache = sub.add_parser("cache-activity", help="a frozen network's activity over the corpus, cached")
    cache.add_argument("--data-root", default=None, help="directory of the local data cache")
    cache.add_argument("--arm", default="connectome", help="connectome, N1, N2 or N3")
    cache.add_argument("--seed", type=int, default=0, help="the seed a null is built with")
    cache.add_argument("--regime", default="R0", help="the regime the network is built in")
    cache.add_argument("--splits", nargs="*", default=["train", "validation", "calibration"],
                       help="which corpus splits to cache")
    cache.add_argument("--cases", action="store_true", help="cache the case renderings instead")
    cache.add_argument("--limit", type=int, default=None, help="only the first N clips of each split")
    cache.add_argument("--no-transfer", action="store_true",
                       help="use the engine's default biophysics instead of the published model's")
    cache.set_defaults(func=cmd_cache_activity)

    readout = sub.add_parser("train-readout", help="fit a readout head on cached activity")
    readout.add_argument("--data-root", default=None, help="directory of the local data cache")
    readout.add_argument("--arm", default="connectome", help="connectome, N1, N2 or N3")
    readout.add_argument("--seeds", nargs="*", type=int, default=[0], help="one run per seed")
    readout.add_argument("--window", type=int, default=2, help="frames the head sees at once")
    readout.add_argument("--steps", type=int, default=3000, help="optimiser steps")
    readout.add_argument("--batch", type=int, default=16, help="clips per step")
    readout.add_argument("--out-dir", default=None, help="where the checkpoints go")
    readout.set_defaults(func=cmd_train_readout)

    netparser = sub.add_parser("train-network",
                               help="train the network itself in a biophysical regime, with its head")
    netparser.add_argument("--data-root", default=None, help="directory of the local data cache")
    netparser.add_argument("--arm", default="connectome", help="connectome, N1, N2 or N3")
    netparser.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2, 3, 4],
                           help="one run per seed; the first also chooses the learning rate")
    netparser.add_argument("--regime", default="R1", help="R1 (biophysical) or R2 (edge gain)")
    netparser.add_argument("--window", type=int, default=2, help="frames the head sees at once")
    netparser.add_argument("--steps", type=int, default=None, help="optimiser steps")
    netparser.add_argument("--batch", type=int, default=None, help="clips per step, simulated whole")
    netparser.add_argument("--network-lr", type=float, default=None,
                           help="skip the validation grid and train at this rate")
    netparser.add_argument("--train-clips", type=int, default=None,
                           help="only the first N clips of the train split")
    netparser.add_argument("--out-dir", default=None, help="where the checkpoints go")
    netparser.set_defaults(func=cmd_train_network)

    trained = sub.add_parser("cache-trained", help="a TRAINED network's activity, one cache per seed")
    trained.add_argument("--data-root", default=None, help="directory of the local data cache")
    trained.add_argument("--arm", default="connectome", help="connectome, N1, N2 or N3")
    trained.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2, 3, 4], help="which seeds")
    trained.add_argument("--regime", default="R1", help="the regime the checkpoints were trained in")
    trained.add_argument("--window", type=int, default=2, help="the window they were trained at")
    trained.add_argument("--splits", nargs="*", default=["calibration"], help="which corpus splits")
    trained.add_argument("--cases", action="store_true", help="cache the case renderings instead")
    trained.add_argument("--limit", type=int, default=None, help="only the first N clips of each split")
    trained.add_argument("--out-dir", default=None, help="where the checkpoints are")
    trained.set_defaults(func=cmd_cache_trained)

    brains = sub.add_parser("export-brainclips", help="what the connectome does with each case, for the web")
    brains.add_argument("--data-root", default=None, help="directory of the local data cache")
    brains.add_argument("--cases", nargs="*", default=None, help="only these cases")
    brains.add_argument("--levels", nargs="*", type=int, default=None, help="only these levels")
    brains.add_argument("--arm", default="connectome", help="connectome, N1, N2 or N3")
    brains.set_defaults(func=cmd_export_brainclips)

    evaluate = sub.add_parser("evaluate", help="score a method over the case clips (test data only)")
    evaluate.add_argument("method", help="M01, or floor (the readout on the committed flow)")
    evaluate.add_argument("--data-root", default=None, help="directory of the local data cache")
    evaluate.add_argument("--cases", nargs="*", default=None, help="only these cases (C01 ... C16)")
    evaluate.add_argument("--levels", nargs="*", type=int, default=None, help="only these levels (0 ... 5)")
    evaluate.add_argument("--clips", type=int, default=None, help="only the first N clips of each level")
    evaluate.add_argument("--workers", type=int, default=1, help="parallel scoring processes")
    evaluate.add_argument("--against", default=None, help="also report the paired difference with this run")
    evaluate.add_argument("--key", default="abs_rel", help="which metric the paired difference uses")
    evaluate.set_defaults(func=cmd_evaluate)

    docs = sub.add_parser("case-docs", help="the generated tables of the case pages, from cases.json")
    docs.add_argument("--check", action="store_true", help="only report pages that are out of date")
    docs.set_defaults(func=cmd_case_docs)

    visual = sub.add_parser("build-visual-cns", help="the whole visual system as a neuron-level graph")
    visual.add_argument("--data-root", default=None, help="directory holding the MaleCNS tables")
    visual.add_argument("--min-weight", type=int, default=1, help="minimum synapses per kept connection")
    visual.add_argument("--out", default=None, help="graph path (default: under CONECTOMA_MODELS_ROOT/specs)")
    visual.add_argument("--summary", default=None, help="where to write the committed summary")
    visual.set_defaults(func=cmd_build_visual_cns)

    visual_character = sub.add_parser(
        "characterize-visual-cns", help="stability, cost and memory of the neuron-level network"
    )
    visual_character.add_argument("--graph", default=None, help="graph written by build-visual-cns")
    visual_character.add_argument("--out", default=None, help="where to write the report")
    visual_character.set_defaults(func=cmd_characterize_visual_cns)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
