"""Stage: assign every rendered clip to a split by its geometry family, and prove the split does not leak.

Writes two committed files, small enough for git and enough for CI to re-check the assignment:
  data/derived/vision/splits.json         families, the split of each, counts per split, the leakage check
  data/derived/vision/tartanair-clips.csv one row per accepted clip, with its family, split and statistics

The identical-frame check hashes each rendered frame (its 721 luminances, SHA-1): two frames with the same
bytes on the lattice are the same image, whatever their names. It needs the renderings, so it runs here
and its result is recorded; CI re-checks the family and environment conditions from the committed table.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.stages.vision_data import CONFIG_DIR, load_config
from conectoma.vision import splits, tartanair

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "vision"
CLIP_FIELDS = ["key", "environment", "family", "difficulty", "trajectory", "start", "frames", "split",
               "depth_median_m", "depth_max_m", "depth_masked_columns", "flow_valid_share", "boundary_share",
               "lum_mean", "step_m_median", "sha256"]


def build_splits(root: Path, derived: Path = DERIVED) -> dict:
    config, digest = load_config()
    index = tartanair.read_index(CONFIG_DIR / config["tartanair"]["index"])
    environments = sorted({env for env, _, _, _ in index})
    family = splits.family_of(config, environments)
    split_of_family = splits.assign(config, environments)

    base = root / "vision" / "tartanair"
    manifest = json.loads((base / "rendered" / "manifest.json").read_text(encoding="utf-8"))
    rows, frame_hashes = [], {}
    for entry in manifest["clips"]:
        environment, difficulty, trajectory, name = Path(entry["clip"]).parts
        start = int(name.removeprefix("clip_").removesuffix(".zip"))
        key = f"{environment}/{difficulty}/{trajectory}/{start:06d}"
        stats = entry["statistics"]
        rows.append({
            "key": key, "environment": environment, "family": family[environment], "difficulty": difficulty,
            "trajectory": trajectory, "start": start, "frames": stats["frames"],
            "split": split_of_family[family[environment]],
            "depth_median_m": round(stats["depth_median_m"], 4) if stats["depth_median_m"] else "",
            "depth_max_m": round(stats["depth_max_m"], 2) if stats["depth_max_m"] else "",
            "depth_masked_columns": stats["depth_masked_columns"],
            "flow_valid_share": round(stats["flow_valid_share"], 4),
            "boundary_share": round(stats["boundary_share"], 4),
            "lum_mean": round(stats["lum_mean"], 4), "step_m_median": round(stats["step_m_median"], 4),
            "sha256": entry["sha256"],
        })
        rendered = base / "rendered" / environment / difficulty / trajectory / f"clip_{start:06d}.npz"
        with np.load(rendered) as clip:
            lum = np.ascontiguousarray(clip["lum"], dtype=np.float32)
        frame_hashes[key] = [hashlib.sha1(frame.tobytes()).hexdigest() for frame in lum]

    problems = splits.leakage_problems(rows, family, split_of_family, frame_hashes)
    by_split = defaultdict(Counter)
    for row in rows:
        by_split[row["split"]]["clips"] += 1
        by_split[row["split"]]["frames"] += row["frames"]
    families_by_split = Counter(split_of_family.values())
    environments_by_split = Counter(split_of_family[family[e]] for e in environments)
    fetched = sorted({row["environment"] for row in rows})
    summary = {
        "config_sha256": digest,
        "unit": "geometry family",
        "families": {f: {"members": sorted(e for e in environments if family[e] == f),
                         "split": split_of_family[f]} for f in sorted(split_of_family)},
        "counts": {name: {"families": families_by_split.get(name, 0),
                          "environments": environments_by_split.get(name, 0),
                          "clips": by_split[name]["clips"], "frames": by_split[name]["frames"]}
                   for name in splits.SPLITS},
        "environments_indexed": len(environments),
        "environments_fetched": len(fetched),
        "leakage": {"checked": ["family", "environment", "identical frames (SHA-1 of the 721 luminances)"],
                    "frames_hashed": sum(len(v) for v in frame_hashes.values()),
                    "problems": problems},
    }
    derived.mkdir(parents=True, exist_ok=True)
    write_json(derived / "splits.json", summary)
    with open(derived / "tartanair-clips.csv", "w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLIP_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: r["key"]):
            writer.writerow(row)
    return summary
