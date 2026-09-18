"""Stage: one committed summary of the vision lane, for the web and for CI.

Writes data/derived/vision/ingestion.json: per source, what was fetched (clips, frames, bytes), what was
rendered and accepted by contract 1, its license, and the angle between neighbouring columns its lens gives
(measured over every frame's intrinsics where they vary); then the splits and the cases as committed. Every
number is read from the renderings' manifests, the fetch logs and the sources' own camera data; nothing is
estimated.
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.stages.vision_data import load_config
from conectoma.vision import eye

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "vision"
STEP_PX = eye.KERNEL


def spacing_deg(focal_436_px: float) -> float:
    return math.degrees(2 * math.atan(STEP_PX / 2 / focal_436_px))


def _range(values: list[float]) -> dict:
    array = np.asarray(values, dtype=np.float64)
    return {"min": round(float(array.min()), 4), "median": round(float(np.median(array)), 4),
            "max": round(float(array.max()), 4)}


def _bytes(directory: Path, pattern: str = "*.zip") -> int:
    return int(sum(p.stat().st_size for p in directory.rglob(pattern)))


def _rendered(base: Path) -> dict:
    manifest = json.loads((base / "rendered" / "manifest.json").read_text(encoding="utf-8"))
    summary = manifest["summary"]
    frames = sum(r["statistics"]["frames"] for r in manifest["clips"])
    masked = sum(r["statistics"]["depth_masked_columns"] for r in manifest["clips"])
    return {"clips": summary["clips"], "accepted": summary["accepted"], "rejected": summary["rejected"],
            "failed": summary["failed"], "frames": frames,
            "depth_masked_share": round(masked / max(frames * 721, 1), 6),
            "render_version": summary["render_version"]}


def _spring_spacing(base: Path) -> dict:
    fys = []
    for path in sorted((base / "data").glob("*/clip_*.zip")):
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.endswith("intrinsics.txt"))
            fys += list(np.loadtxt(io.StringIO(archive.read(name).decode("utf-8")), ndmin=2)[:, 1])
    return _range([spacing_deg(fy * eye.ROWS / 1080) for fy in fys])


def _hypersim_spacing() -> dict:
    from conectoma.vision.hypersim import cameras, test_images, vertical_fov_deg

    scenes = test_images()
    return _range([spacing_deg((eye.ROWS / 2) / math.tan(math.radians(vertical_fov_deg(c)) / 2))
                   for s, c in cameras().items() if s in scenes])


def _sintel(models_root: Path) -> dict:
    from conectoma.vision import sintel

    root = sintel.sintel_dir(models_root) / "training"
    spacing = [spacing_deg(sintel.read_camera(p)[1, 1])
               for p in sorted((root / "camdata_left").glob("*/*.cam"))]
    rendered = models_root / "flyvis" / "renderings" / "RenderedSintel_0000"
    strips = sorted(p.name for p in rendered.iterdir() if p.is_dir()) if rendered.exists() else []
    return {"sequences": len(list((root / "final").iterdir())), "held_out": list(sintel.HELD_OUT),
            "frames": sum(len(list(p.glob("*.png"))) for p in (root / "final").iterdir()),
            "engine_rendering": {"strips": len(strips), "complete": (rendered / "_meta.yaml").exists()
                                 and "status: done" in (rendered / "_meta.yaml").read_text(encoding="utf-8")},
            "column_spacing_deg": _range(spacing)}


def _flygym() -> dict:
    from conectoma.vision import flygym_scenes

    eye_map = json.loads((DERIVED / "flygym-eye.json").read_text(encoding="utf-8"))
    scene = flygym_scenes.build(lambda spec: None)
    return {"flygym": eye_map["flygym"], "ommatidia": eye_map["ommatidia"],
            "orientation": eye_map["orientation"]["best"],
            "orientation_score": eye_map["orientation"]["best_score"],
            "column_spacing_deg": round(scene.eye.spacing_deg, 4)}


def summarize_vision(root: Path, models_root: Path, derived: Path = DERIVED) -> dict:
    config, digest = load_config()
    vision = root / "vision"
    tartanair = {**_rendered(vision / "tartanair"), "bytes": _bytes(vision / "tartanair" / "data"),
                 "license": config["tartanair"]["license"], "attribution": config["tartanair"]["attribution"],
                 "frame_interval_s": config["tartanair"]["frame_interval_s"],
                 "column_spacing_deg": round(spacing_deg(config["tartanair"]["intrinsics"]["fy"] * eye.ROWS
                                                         / config["tartanair"]["intrinsics"]["height"]), 4)}
    spring = {**_rendered(vision / "spring"), "bytes": _bytes(vision / "spring" / "data"),
              "license": config["spring"]["license"], "attribution": config["spring"]["attribution"],
              "frame_interval_s": None, "column_spacing_deg": _spring_spacing(vision / "spring")}
    hypersim = {**_rendered(vision / "hypersim"), "bytes": _bytes(vision / "hypersim" / "data"),
                "license": config["hypersim"]["license"], "attribution": config["hypersim"]["attribution"],
                "column_spacing_deg": _hypersim_spacing()}
    panorama = json.loads((vision / "panorama" / "fetch-summary.json").read_text(encoding="utf-8"))
    splits = json.loads((derived / "splits.json").read_text(encoding="utf-8"))
    cases = json.loads((derived / "cases.json").read_text(encoding="utf-8"))
    summary = {
        "config_sha256": digest,
        "sources": {
            "tartanair": tartanair,
            "panorama": {"clips": panorama["clips"], "bytes": _bytes(vision / "panorama" / "data"),
                         "license": config["tartanair"]["license"]},
            "sintel": {**_sintel(models_root), "license": config["sintel"]["license"],
                       "attribution": config["sintel"]["attribution"],
                       "frame_interval_s": config["sintel"]["frame_interval_s"]},
            "spring": spring,
            "hypersim": hypersim,
            "flygym": {**_flygym(), "license": "Apache-2.0"},
        },
        "splits": {"unit": splits["unit"], "families": len(splits["families"]), "counts": splits["counts"],
                   "leakage": splits["leakage"]},
        "cases": {"count": len(cases["cases"]),
                  "renderings": sum(lv["clips"] for c in cases["cases"].values() for lv in c["levels"]),
                  "accepted": sum(lv["accepted"] for c in cases["cases"].values() for lv in c["levels"]),
                  "cases_sha256": cases["cases_sha256"]},
    }
    write_json(derived / "ingestion.json", summary)
    return summary
