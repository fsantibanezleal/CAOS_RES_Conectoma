"""Contract 2 for the eye's input: one compact file per case the web reads, and their manifest.

The App shows what the 721 columns see: for each case, its first drawn clip at all six levels, frame by
frame, with the ground truth the case grades. The renderings are float arrays of a few hundred kilobytes per
level; the web gets them quantised, every array a base64 string of bytes in the engine's column order:

  lum        uint8, round(255 * luminance)
  depth      uint8, log-encoded between the case's nearest and farthest finite depth, 255 for masked
  figure     uint8, round(255 * share) (and sky, labelled, flow_valid the same way where present)
  boundary   uint8, 0 or 1
  flow       int8 pairs (x then y per step), scaled by the case's largest flow component, engine units

A target identical at every level (most variants act on the image, not on the scene) is stored once. The
manifest gives each column's pixel offset from the frame centre (the engine's sampling positions, rows
down and columns right), each case file's size and SHA-256, and what each case's source may be shown under.
Nothing is recomputed: every value is the committed case rendering, quantised.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import numpy as np

from conectoma.vision import eye

ARTIFACT_VERSION = 1
SHARES = ("figure", "sky", "labelled", "flow_valid")
LICENSES = {
    "tartanair": "TartanAir V2, Carnegie Mellon University AirLab (tartanair.org), CC BY 4.0",
    "panorama": "TartanAir V2 panoramas, Carnegie Mellon University AirLab (tartanair.org), CC BY 4.0",
    "sintel": ("MPI Sintel (Butler et al. 2012); film content (c) Blender Foundation, durian.blender.org, "
               "CC BY 3.0"),
    "spring": "Spring (Mehl et al. 2023), University of Stuttgart, doi:10.18419/DARUS-3376, CC BY 4.0",
    "hypersim": "Hypersim (Roberts et al. 2021), Apple, CC BY-SA 3.0; this derived clip is shared alike",
    "flygym": "rendered with FlyGym 2.1.0 (NeuroMechFly v2, Apache-2.0) by this product",
    "synthetic": "computed by this product",
}


def _b64(array: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode("ascii")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _depth_range(levels: list[dict]) -> tuple[float, float]:
    finite = np.concatenate([lv["depth"][np.isfinite(lv["depth"])] for lv in levels])
    return float(finite.min()), float(finite.max())


def encode_depth(depth: np.ndarray, near: float, far: float) -> np.ndarray:
    code = np.full(depth.shape, 255, dtype=np.uint8)
    ok = np.isfinite(depth)
    if far > near:
        scaled = (np.log(depth[ok]) - np.log(near)) / (np.log(far) - np.log(near))
    else:
        scaled = np.zeros(ok.sum())
    code[ok] = np.clip(np.rint(254 * scaled), 0, 254).astype(np.uint8)
    return code


def decode_depth(code: np.ndarray, near: float, far: float) -> np.ndarray:
    """The inverse of `encode_depth` (NaN for masked), for the tests and for the web's own check."""
    out = np.exp(np.log(near) + code.astype(np.float64) / 254 * (np.log(far) - np.log(near)))
    return np.where(code == 255, np.nan, out)


def encode_case(case_id: str, case: dict, levels: list[dict]) -> dict:
    """The web file of one case from its six level renderings (each a dict of arrays plus `stamp`)."""
    near, far = _depth_range(levels)
    flows = [lv["flow"] for lv in levels if "flow" in lv]
    flow_scale = float(max(np.abs(f).max() for f in flows)) if flows else 0.0
    encoded = []
    for lv in levels:
        arrays = {"lum": np.clip(np.rint(lv["lum"] * 255), 0, 255).astype(np.uint8),
                  "depth": encode_depth(lv["depth"], near, far)}
        for key in SHARES:
            if key in lv:
                share = np.asarray(lv[key], dtype=np.float64)
                arrays[key] = np.clip(np.rint(share * 255), 0, 255).astype(np.uint8)
        if "boundary" in lv:
            arrays["boundary"] = lv["boundary"].astype(np.uint8)
        if "flow" in lv and flow_scale > 0:
            arrays["flow"] = np.clip(np.rint(lv["flow"] / flow_scale * 127), -127, 127).astype(np.int8)
        encoded.append(arrays)
    shared = {key: _b64(encoded[0][key]) for key in encoded[0]
              if key != "lum" and all(key in e and np.array_equal(e[key], encoded[0][key]) for e in encoded)}
    out_levels = []
    for lv, arrays in zip(levels, encoded, strict=True):
        stamp = lv["stamp"]
        out_levels.append({
            "value": stamp["value"], "interval_s": stamp["interval_s"], "measured": stamp["measured"],
            "frames": [int(f) for f in lv["frames"]],
            "arrays": {key: _b64(a) for key, a in arrays.items() if key not in shared},
        })
    return {
        "artifact": "eyeclip", "version": ARTIFACT_VERSION, "case": case_id, "name": case["name"],
        "category": case["category"], "source": case["source"], "family": case.get("family"),
        "grades": case["grades"], "variant": case["variant"], "item": levels[0]["stamp"]["item"],
        "columns": int(levels[0]["lum"].shape[-1]), "frames": int(levels[0]["lum"].shape[0]),
        "depth": {"near_m": near, "far_m": far, "encoding": "log", "masked": 255,
                  "units": "relative" if case["source"] == "sintel" else "metres"},
        "flow": {"scale": flow_scale, "units": "engine (per image height, y up, summed over the box)"}
        if flows else None,
        "shared": shared, "levels": out_levels, "license": LICENSES[case["source"]],
    }


def _load(path: Path) -> dict:
    with np.load(path) as data:
        out = {k: data[k] for k in data.files if k != "stamp"}
        out["stamp"] = json.loads(str(data["stamp"]))
    return out


def export_eyeclips(root: Path, summary_path: Path, out_dir: Path, manifests_dir: Path,
                    clip: int = 0) -> dict:
    """Write one web file per case (its clip `clip` at every level) and the manifest; return the manifest."""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for case_id, case in summary["cases"].items():
        levels = [_load(root / "vision" / "cases" / case_id / f"L{level}" / f"{clip:02d}.npz")
                  for level in range(len(case["levels"]))]
        items = {lv["stamp"]["item"] for lv in levels}
        if items != {case["items"][clip]}:
            raise ValueError(f"{case_id}: the renderings are not of the summary's clip {clip} ({items})")
        document = encode_case(case_id, case, levels)
        path = out_dir / f"{case_id}.json"
        path.write_text(json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        files[case_id] = {"path": f"eyeclips/{path.name}", "bytes": path.stat().st_size,
                          "sha256": _digest(path), "name": case["name"], "category": case["category"],
                          "source": case["source"]}
    centres, uv = eye.receptor_centers(), eye.lattice_coordinates()
    manifest = {
        "artifact": "eyeclips", "version": ARTIFACT_VERSION,
        "source": {"cases": summary_path.name, "cases_sha256": _digest(summary_path),
                   "render_version": summary["render_version"], "clip": clip},
        "lattice": {"extent": eye.EXTENT, "kernel_px": eye.KERNEL, "rows_px": eye.ROWS,
                    "row_px": centres[:, 0].tolist(), "col_px": centres[:, 1].tolist(),
                    "u": uv[:, 0].tolist(), "v": uv[:, 1].tolist()},
        "cases": files,
    }
    manifests_dir.mkdir(parents=True, exist_ok=True)
    (manifests_dir / "eyeclips.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8",
                                                 newline="\n")
    return manifest
