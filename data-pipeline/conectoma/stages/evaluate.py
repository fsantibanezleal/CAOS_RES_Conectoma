"""Stage: run a method over the case clips and score it, case by case, level by level.

Every method is scored on exactly the same clips: the ones `build-cases` rendered and `cases.json` records,
which come from families that are always in the test split. A run reads each clip, calls the method, and
compares what it claimed against the ground truth that clip carries, with the metrics of
`conectoma/methods/metrics.py`.

What is written, under `data/derived/evaluation/`:
  <method>.json    per case and level: coverage and the depth metrics, the figure-ground and
                   moving-object scores where the case grades them, the refusal share for the cases where
                   depth is not observable at all, and one row per clip so a later comparison can be
                   PAIRED on the clip rather than pooled
  ../manifests/evaluation.json   which methods have been run, over which cases.json, with which
                   thresholds and which code, and the digest of each report

A case whose depth cannot be observed (C13, pure rotation; C14, a static camera) is graded by what the
method refused, not by an error: `metrics.refusal`. The registry says which those are through the case's
`grades` list, so nothing here hard-codes a case id beyond that.

The stage never writes into the corpus and never re-renders anything: it reads the clips and writes its own
report, so a rerun with a different threshold costs a run and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.methods import m01, m02, m03, m04, m05, metrics
from conectoma.vision import cases

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "evaluation"
MANIFESTS = REPO_ROOT / "data" / "derived" / "manifests"
CODE = ("readout", "flow_lattice", "sweep", "m01", "m02", "emd", "m03", "m04", "m05",
        "head", "metrics")

# Each method is a callable (clip, column_spacing_deg, **thresholds) -> per-step arrays. `floor` is not a
# method: it is the readout applied to the flow the corpus committed, and every flow-based row is reported
# against it.
# What a row IS, which the page states beside every number: a method that consumes only what the eye
# receives, a bound that consumes more, or the readout applied to the flow the corpus committed.
KINDS = {
    "M01": "native",
    "M02": "upper bound: two cameras 0.25 m apart and a full pixel grid",
    "M03": "native",
    "M04": "native",
    "M05": "native, trained: the measured connectome as a reservoir",
    "M05-N1": "control for M05: the same wiring degree-preservingly rewired",
    "M05-N2": "control for M05: a size-matched random sparse graph",
    "M05-N3": "control for M05: the same wiring with its signs shuffled",
    "floor": "the committed flow through the same readout",
}

METHODS = {
    "M01": {"call": m01.run, "requires": ("lum",)},
    "M02": {"call": None, "requires": (), "stereo": True},      # run from the raw pair, not the lattice clip
    "M03": {"call": m03.run, "requires": ("lum",), "calibrate": m03.choose},
    "M04": {"call": m04.run, "requires": ("lum",)},
    "M05": {"call": None, "requires": ("lum",), "reservoir": "connectome"},
    "M05-N1": {"call": None, "requires": ("lum",), "reservoir": "N1"},
    "M05-N2": {"call": None, "requires": ("lum",), "reservoir": "N2"},
    "M05-N3": {"call": None, "requires": ("lum",), "reservoir": "N3"},
    "floor": {"call": m01.floor, "requires": ("flow",)},
}


def code_digest() -> str:
    digest = hashlib.sha256()
    for name in CODE:
        digest.update((Path(m01.__file__).parent / f"{name}.py").read_bytes())
    return digest.hexdigest()


def clip_path(root: Path, case_id: str, level: int, index: int) -> Path:
    return root / "vision" / "cases" / case_id / f"L{level}" / f"{index:02d}.npz"


def observable(case: dict) -> bool:
    """Whether depth can be measured in this case at all: a case that grades no depth cannot be scored."""
    return "depth" in case.get("grades", [])


def score_clip(clip: dict, result: dict, case: dict, metric_units: bool = True) -> dict:
    """The metrics of one clip: depth where the case grades it, masks where the clip carries them."""
    steps = result["distance_m"].shape[0]
    truth = np.asarray(clip["depth"], dtype=np.float64)[:steps]
    claimed = ~result["unknown"] & np.isfinite(result["distance_m"])
    out: dict = {"steps": int(steps)}
    if observable(case):
        out |= metrics.depth_metrics(truth, result["distance_m"], claimed, metric_units)
    out |= {f"refusal_{k}": v for k, v in
            metrics.refusal(result["unknown"], observable(case)).items()}

    truth_moving = None
    if "moving" in clip:
        truth_moving = np.asarray(clip["moving"], dtype=np.float64)[:steps] > 0.5
    elif "figure" in clip:
        truth_moving = np.asarray(clip["figure"], dtype=np.float64)[:steps] > 0.5
    if truth_moving is not None and truth_moving.shape == result["moving"].shape:
        out |= {f"moving_{k}": v for k, v in metrics.mask_metrics(truth_moving, result["moving"]).items()}
    if "boundary" in clip:
        boundary = np.asarray(clip["boundary"])[:steps] > 0
        predicted = _depth_edges(result["distance_m"])
        if boundary.shape == predicted.shape:
            out |= metrics.boundary_f(boundary, predicted)
    return out


def _depth_edges(distance: np.ndarray, ratio: float = 1.25) -> np.ndarray:
    """Columns whose claimed depth differs from a neighbour's by more than `ratio`: a depth edge."""
    from conectoma.methods import flow_lattice

    index = flow_lattice.neighbours()
    padded = np.concatenate([distance, np.full(distance.shape[:-1] + (1,), np.nan)], axis=-1)
    neighbours = padded[..., index]                                  # (..., columns, 6)
    with np.errstate(divide="ignore", invalid="ignore"):
        jump = np.maximum(neighbours / distance[..., None], distance[..., None] / neighbours)
    # a column with no claimed neighbour is not an edge; it is a column with nothing to compare
    return np.where(np.isfinite(jump), jump, 0.0).max(axis=-1) > ratio


def _run_one(method: str, case_id: str, level: int, index: int, root: str,
             thresholds: dict) -> dict | None:
    registry, _ = cases.load_cases()
    case = registry["cases"][case_id]
    path = clip_path(Path(root), case_id, level, index)
    if not path.exists():
        return None
    with np.load(path, allow_pickle=True) as loaded:
        stamp = json.loads(str(loaded["stamp"]))
        clip = {key: loaded[key] for key in loaded.files if key != "stamp"}
    spacing = stamp["measured"].get("column_spacing_deg")
    if spacing is None:
        return None
    row = {"method": method, "case": case_id, "level": level, "clip": index,
           "item": stamp["item"], "column_spacing_deg": spacing, "interval_s": stamp.get("interval_s")}
    missing = [key for key in METHODS[method]["requires"] if key not in clip]
    if missing:
        # a method is not run on a clip that does not carry what it needs, and the report says which
        # clips those were rather than leaving a silent gap
        return row | {"skipped": f"the clip carries no {', '.join(missing)}"}
    # A synthetic or panorama clip records no poses because its camera motion is not measured: it is the
    # case itself, and the registry states it.
    motion = None if "poses" in clip else cases.step_motion(case, level)
    if "interval_s" not in clip and stamp.get("interval_s") is not None:
        clip["interval_s"] = float(stamp["interval_s"])
    if motion is None and "poses" not in clip:
        return row | {"skipped": "the clip carries no poses and its case declares no motion"}
    started = time.time()
    if METHODS[method].get("reservoir"):
        arm = METHODS[method]["reservoir"]
        key = f"case_{case_id}_L{level}_{index:02d}"
        try:
            result = m05.run(clip, spacing, root=Path(root), arm=arm, key=key, **thresholds)
        except FileNotFoundError as missing:
            return row | {"skipped": str(missing)}
    elif METHODS[method].get("stereo"):
        pair = _stereo_pair(Path(root), case, stamp, level)
        if isinstance(pair, str):
            return row | {"skipped": pair}
        result = m02.run(*pair)
    else:
        result = METHODS[method]["call"](clip, spacing, motion=motion, **thresholds)
    row["seconds"] = round(time.time() - started, 3)
    row |= score_clip(clip, result, case, metric_units=_metric_units(case))
    return row


def _stereo_pair(root: Path, case: dict, stamp: dict, level: int):
    """The left and right frames of a case clip, with the level's variant applied to both.

    Returns a reason (a string) instead of the pair when the case cannot be run: a source with no second
    camera, or a variant that cannot be reproduced on the right image from the image alone (fog needs the
    right camera's depth, exposure blur its flow, and neither was fetched).
    """
    from conectoma.vision import render, variants

    if cases.contract_source(case) != "tartanair":
        return "this case has no stereo pair: only TartanAir ships a second camera"
    transform = case["variant"].get("transform")
    if transform not in m02.REPLICABLE:
        return f"the {transform} variant cannot be applied to the right camera with the data fetched"
    item = stamp["item"]
    environment, difficulty, trajectory, start = item.split("/")
    base = root / "vision" / "tartanair"
    left_path = base / "data" / environment / difficulty / trajectory / f"clip_{int(start):06d}.zip"
    right_path = base / "stereo" / environment / difficulty / trajectory / f"clip_{int(start):06d}.zip"
    if not right_path.exists():
        return "the right camera of this clip has not been fetched (run.py fetch-stereo)"
    left = render.load_tartanair_clip(left_path)["lum"]
    right = m02.right_frames(right_path).astype(np.float32) / 255.0
    if transform == "illumination":
        gain = float(case["variant"]["levels"][level])
        left, right = variants.illumination(left, gain), variants.illumination(right, gain)
    elif transform == "photons":
        count = case["variant"]["levels"][level]
        seed = int(stamp.get("seed", 0))
        left = variants.photons(left, count, seed * 10 + level)
        right = variants.photons(right, count, seed * 10 + level + 1)
    return ((np.clip(left, 0, 1) * 255).astype(np.uint8),
            (np.clip(right, 0, 1) * 255).astype(np.uint8))


def _metric_units(case: dict) -> bool:
    """RMSE in metres is filled only where the source's depth is metric (Sintel's is not)."""
    return cases.contract_source(case) != "sintel"


def _aggregate(rows: list[dict], registry: dict) -> dict:
    """Per case and level, the median over clips of every number, with the clip rows kept for pairing."""
    out: dict = {}
    keys = sorted({k for r in rows for k, v in r.items() if isinstance(v, (int, float))
                   and not isinstance(v, bool)})
    for case_id, case in registry["cases"].items():
        levels = []
        for level, value in enumerate(case["variant"]["levels"]):
            mine = [r for r in rows if r["case"] == case_id and r["level"] == level]
            scored = [r for r in mine if "skipped" not in r]
            if not mine:
                continue
            if not scored:
                levels.append({"value": value, "clips": len(mine), "skipped": mine[0]["skipped"]})
                continue
            mine = scored
            summary = {}
            for key in keys:
                values = [r[key] for r in mine if isinstance(r.get(key), (int, float))
                          and not isinstance(r.get(key), bool) and np.isfinite(r[key])]
                if values:
                    summary[key] = round(float(np.median(values)), 6)
            levels.append({"value": value, "clips": len(mine), **summary})
        if levels:
            out[case_id] = {"name": case["name"], "category": case["category"],
                            "grades": case.get("grades", []),
                            "quantity": case["variant"]["quantity"], "unit": case["variant"]["unit"],
                            "observable": observable(case), "levels": levels}
    return out


def run(root: Path, method: str, *, cases_wanted: list[str] | None = None,
        levels_wanted: list[int] | None = None, clips: int | None = None, workers: int = 1,
        thresholds: dict | None = None) -> dict:
    """Score `method` over the case clips under `root` and write its report."""
    if method not in METHODS:
        raise KeyError(f"unknown method {method}; known: {', '.join(sorted(METHODS))}")
    registry, digest = cases.load_cases()
    thresholds = dict(thresholds or {})
    # a method that must be calibrated is calibrated here, on its own synthetic set, and the calibration
    # is written beside the report so the numbers can be read with the thing that produced them
    calibration = None
    if "calibrate" in METHODS[method] and "gain" not in thresholds:
        calibration = METHODS[method]["calibrate"]()
        thresholds |= {"tau_s": calibration["chosen"]["tau_s"], "gain": calibration["chosen"]["gain"],
                       "rings": calibration["rings"]}
    jobs = []
    for case_id, case in registry["cases"].items():
        if cases_wanted and case_id not in cases_wanted:
            continue
        for level in range(len(case["variant"]["levels"])):
            if levels_wanted is not None and level not in levels_wanted:
                continue
            for index in range(clips if clips is not None else registry["clips"]):
                jobs.append((case_id, level, index))

    rows: list[dict] = []
    started = time.time()
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_one, method, case_id, level, index, str(root), thresholds): (
                case_id, level, index) for case_id, level, index in jobs}
            for future in as_completed(futures):
                row = future.result()
                if row is not None:
                    rows.append(row)
    else:
        for case_id, level, index in jobs:
            row = _run_one(method, case_id, level, index, str(root), thresholds)
            if row is not None:
                rows.append(row)
    rows.sort(key=lambda r: (r["case"], r["level"], r["clip"]))

    report = {
        "method": method,
        "clips_skipped": sum(1 for r in rows if "skipped" in r),
        "cases_sha256": digest,
        "code_sha256": code_digest(),
        "thresholds": thresholds,
        "calibration": calibration,
        "clips_scored": len(rows),
        "seconds": round(time.time() - started, 1),
        "cases": _aggregate(rows, registry),
        "clips": rows,
    }
    DERIVED.mkdir(parents=True, exist_ok=True)
    write_json(DERIVED / f"{method}.json", report)
    write_summary()
    _update_manifest(method, report)
    return report


def write_summary() -> dict:
    """One compact file the web reads: every scored method's per-case numbers, no per-clip rows.

    A full report carries one row per clip, which is what a paired comparison needs and what a page does
    not. The page gets this projection instead, so a reader downloads kilobytes rather than megabytes, and
    it is regenerated from the reports themselves, never written by hand.
    """
    methods = {}
    for path in sorted(DERIVED.glob("*.json")):
        if path.name == "summary.json":
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        methods[report["method"]] = {
            "cases": report["cases"],
            "clips_scored": report["clips_scored"],
            "clips_skipped": report.get("clips_skipped", 0),
            "thresholds": report.get("thresholds", {}),
            "calibration": (report.get("calibration") or {}).get("chosen"),
            "seconds": report.get("seconds"),
        }
    paired = {}
    for name in methods:
        if name == "floor" or "floor" not in methods:
            continue
        try:
            paired[name] = compare(name, "floor", "abs_rel")
        except FileNotFoundError:
            continue
    # A connectome row's claim is never its own number: it is the paired difference against the nulls
    # built from the same wiring, with the same head, the same seeds and the same clips.
    against_nulls = {}
    for name in methods:
        controls = [null for null in methods if null.startswith(f"{name}-N")]
        for null in sorted(controls):
            try:
                against_nulls[f"{name} vs {null}"] = compare(name, null, "abs_rel")
            except FileNotFoundError:
                continue
    summary = {"artifact": "evaluation-summary", "version": 1, "methods": methods,
               "against_floor": paired, "against_nulls": against_nulls, "kind": KINDS}
    write_json(DERIVED / "summary.json", summary)
    return summary


def _update_manifest(method: str, report: dict) -> None:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    path = MANIFESTS / "evaluation.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "artifact": "evaluation", "version": 1, "methods": {}}
    file = DERIVED / f"{method}.json"
    manifest["source"] = {"cases": "cases.json", "cases_sha256": report["cases_sha256"]}
    manifest["methods"][method] = {
        "path": f"evaluation/{method}.json",
        "bytes": file.stat().st_size,
        "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        "code_sha256": report["code_sha256"],
        "thresholds": report["thresholds"],
        "clips_scored": report["clips_scored"],
    }
    write_json(path, manifest)


def compare(first: str, second: str, key: str = "abs_rel") -> dict:
    """The paired difference between two reports, clip by clip: `first` minus `second`."""
    reports = {}
    for name in (first, second):
        path = DERIVED / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"{name} has not been scored yet ({path})")
        reports[name] = json.loads(path.read_text(encoding="utf-8"))
    index = {name: {(r["case"], r["level"], r["clip"]): r for r in report["clips"]}
             for name, report in reports.items()}
    shared = sorted(set(index[first]) & set(index[second]))
    a = np.array([index[first][k].get(key, np.nan) for k in shared], dtype=np.float64)
    b = np.array([index[second][k].get(key, np.nan) for k in shared], dtype=np.float64)
    return {"first": first, "second": second, "key": key, "clips": len(shared),
            **metrics.paired_difference(a, b)}
