"""Stage: render every case at every level, check each against contract 1, and record what each level
measured.

Each case's clips are drawn once (`cases.select`, test data only) and rendered at its six levels. A level's
rendering lands in `<data root>/vision/cases/<case>/L<level>/<clip>.npz` with a stamp (the registry digest,
the render version, the source item, the frame interval and the measured quantities); a clip whose six
renderings carry the current stamp is not rendered again. Two files record the result:
  <data root>/vision/cases/manifest.json   one row per case, level and clip: statistics, measurements,
                                            contract problems and the SHA-256 of the rendering
  data/derived/vision/cases.json           committed: the registry, the items each case drew, and per level
                                            how many clips were accepted and the median of each measurement
The stage fails when any rendering breaks contract 1 or any clip fails to render.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.vision import cases
from conectoma.vision.contract import clip_problems
from conectoma.vision.render import RENDER_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "vision"
HEAVY = ("flygym", "panorama", "tartanair")       # started first, so the long ones do not trail


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _out(root: Path, case_id: str, level: int, index: int) -> Path:
    return root / "vision" / "cases" / case_id / f"L{level}" / f"{index:02d}.npz"


def _row(case_id: str, case: dict, level: int, index: int, item: str, path: Path, clip: dict,
         stamp: dict) -> dict:
    return {"case": case_id, "level": level, "value": case["variant"]["levels"][level], "clip": index,
            "item": item, "interval_s": stamp["interval_s"], "measured": stamp["measured"],
            "statistics": cases.statistics(clip),
            "problems": clip_problems(clip, cases.contract_source(case)),
            "sha256": _sha256(path)}


def _build_one(case_id: str, index: int, item: str, root: str, models_root: str | None,
               digest: str) -> list[dict]:
    registry, _ = cases.load_cases()
    case = registry["cases"][case_id]
    root_path = Path(root)
    levels = len(case["variant"]["levels"])
    paths = [_out(root_path, case_id, level, index) for level in range(levels)]
    kept = []
    for level, path in enumerate(paths):
        if not path.exists():
            break
        with np.load(path) as existing:
            stamp = json.loads(str(existing["stamp"]))
            if (stamp.get("cases_sha256"), stamp.get("render_version"), stamp.get("item")) != (
                    digest, RENDER_VERSION, item):
                break
            clip = {k: existing[k] for k in existing.files if k != "stamp"}
        kept.append(_row(case_id, case, level, index, item, path, clip, stamp))
    if len(kept) == levels:
        return kept
    seed = cases.clip_seed(registry["seed"], case_id, index)
    models = Path(models_root) if models_root else None
    rendered = cases.render_clip(case_id, case, item, root_path, models, seed)
    rows = []
    for level, (path, result) in enumerate(zip(paths, rendered, strict=True)):
        stamp = {"cases_sha256": digest, "render_version": RENDER_VERSION, "case": case_id, "level": level,
                 "value": case["variant"]["levels"][level], "item": item, "seed": seed,
                 "interval_s": result["interval_s"], "measured": result["measured"]}
        clip = result["clip"]
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.stem + ".partial.npz")
        np.savez_compressed(partial, stamp=json.dumps(stamp), **clip)
        os.replace(partial, path)
        rows.append(_row(case_id, case, level, index, item, path, clip, stamp))
    return rows


def _median(values: list) -> float | list | None:
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and v is not None]
    if numbers and len(numbers) == len(values):
        return round(float(np.median(numbers)), 6)
    lists = [v for v in values if isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v)]
    if lists and len(lists) == len(values):
        return [round(float(np.median([v[0] for v in lists])), 6),
                round(float(np.median([v[-1] for v in lists])), 6)]
    return None


def _summary(registry: dict, digest: str, selections: dict, rows: list[dict], failed: dict) -> dict:
    out = {"cases_sha256": digest, "render_version": RENDER_VERSION, "seed": registry["seed"],
           "clips_per_case": registry["clips"], "cases": {}}
    for case_id, case in registry["cases"].items():
        levels = []
        for level, value in enumerate(case["variant"]["levels"]):
            mine = [r for r in rows if r["case"] == case_id and r["level"] == level]
            accepted = [r for r in mine if not r["problems"]]
            measured = {k: _median([r["measured"].get(k) for r in accepted])
                        for k in sorted({k for r in accepted for k in r["measured"]})}
            stats = {k: _median([r["statistics"].get(k) for r in accepted])
                     for k in sorted({k for r in accepted for k in r["statistics"]})}
            levels.append({"value": value, "clips": len(mine), "accepted": len(accepted),
                           "interval_s": _median([r["interval_s"] for r in accepted]) if accepted else None,
                           "measured": {k: v for k, v in measured.items() if v is not None},
                           "statistics": {k: v for k, v in stats.items() if v is not None}})
        out["cases"][case_id] = {
            **{k: case[k] for k in ("name", "category", "reason", "source", "grades")},
            "family": case.get("family"), "contract": cases.contract_source(case),
            "variant": {k: case["variant"][k] for k in ("quantity", "unit", "levels")},
            "items": selections[case_id], "levels": levels,
            "failed": {k: v for k, v in failed.items() if k.startswith(f"{case_id}/")},
        }
    return out


def build_cases(root: Path, models_root: Path | None, workers: int = 4, only: list[str] | None = None,
                derived: Path = DERIVED) -> dict:
    registry, digest = cases.load_cases()
    selected = [c for c in registry["cases"] if not only or c in only]
    selections = {c: cases.select(c, registry["cases"][c], registry, root) for c in registry["cases"]
                  if c in selected}
    tasks = [(c, i, item) for c in selected for i, item in enumerate(selections[c])]
    tasks.sort(key=lambda t: registry["cases"][t[0]]["source"] not in HEAVY)
    started = time.time()
    rows, failed = [], {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_build_one, c, i, item, str(root), str(models_root) if models_root else None,
                               digest): (c, i, item) for c, i, item in tasks}
        for n, future in enumerate(as_completed(futures), 1):
            c, i, item = futures[future]
            try:
                rows.extend(future.result())
            except Exception as error:  # one clip that cannot render is listed, and the stage fails
                failed[f"{c}/{i:02d}/{item}"] = f"{type(error).__name__}: {error}"
            print(f"  {n}/{len(tasks)} clips, {(time.time() - started) / 60:.1f} min", flush=True)
    rows.sort(key=lambda r: (r["case"], r["level"], r["clip"]))
    base = root / "vision" / "cases"
    previous = {}
    if only and (base / "manifest.json").exists():
        previous = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        rows = [r for r in previous.get("rows", []) if r["case"] not in selected] + rows
        failed = {**{k: v for k, v in previous.get("failed", {}).items() if k.split("/")[0] not in selected},
                  **failed}
        selections = {**previous.get("selections", {}), **selections}
        rows.sort(key=lambda r: (r["case"], r["level"], r["clip"]))
    write_json(base / "manifest.json", {"cases_sha256": digest, "render_version": RENDER_VERSION,
                                        "selections": selections, "rows": rows, "failed": failed})
    complete = all(c in selections for c in registry["cases"])
    summary = {"cases": len(selected), "clips": len(tasks), "renderings": len(rows),
               "rejected": sum(1 for r in rows if r["problems"]), "failed": len(failed),
               "elapsed_seconds": round(time.time() - started, 1), "complete": complete}
    if complete:
        derived.mkdir(parents=True, exist_ok=True)
        write_json(derived / "cases.json", _summary(registry, digest, selections, rows, failed))
    return summary
