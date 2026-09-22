"""Contract 2 for what the connectome DOES with the eye's input: one compact file per case, and a manifest.

The App shows the fly's input frame by frame. This is the other half: what the measured network's cells do
while it plays. For each case, the frozen network is run on the case's first drawn clip and the voltage of
the fly's visual pathway is kept, in the order the signal travels:

    L1, L2, L3                     the lamina monopolar cells
    Mi1, Tm3, Tm1, Tm2, Mi9, Mi4   the medulla types that feed motion detection
    T4a..T4d, T5a..T5d             the direction-selective outputs

CT1 belongs to that pathway and is NOT here: the MaleCNS optic lobe carries one CT1 cell for the whole
lattice rather than one per column, so it has no map to draw. The manifest names it under `wide_field`
instead of dropping it silently.

Rows are SIMULATED STEPS, not source frames. The network is stepped at the published 0.02 s and a source
frame lasts several steps, so a per-frame sample would hide the response moving between frames; an
animation wants the steps. The manifest records how many steps make a frame.

Voltages are signed and centred on nothing in particular, so each type is quantised on its own symmetric
scale, recorded per case and per type: `value = scale * (byte - 128) / 127`. A reader multiplies back and
gets millivolts of the engine's units, which is what the hover readout shows.

Nothing is simulated in the browser: 40,051 cells and 2.9 million connections is not honest client-side
performance, and a visitor would be shown a different network from the one the numbers come from. The
artifact is the same network the Experiments page reports on, verified against its digest before it is
drawn.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.stages.cache_activity import (
    DT_S,
    PATHWAY,
    activity_of,
    available,
    build_arm,
    wide_field,
)
from conectoma.vision import cases

ARTIFACT_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "brainclips"
MANIFESTS = REPO_ROOT / "data" / "derived" / "manifests"
CLIP = 0                      # the same clip the eye artifact shows, so the two play in lockstep
MAX_STEPS = 160               # a clip of 32 frames at five steps each; longer clips are cut and say so
STRIDE = 3                    # every third simulated step: 1.7 rows per source frame (see the budget)
ENDS = (0, 5)                 # the two ends of a case's sweep: its mildest level and its most extreme

# The size budget, measured rather than guessed. One case-level with 17 types at every step is 1.96 MB of
# bytes, 0.74 MB once delta-coded over time and gzipped, so all sixteen cases at all six levels would be
# 71 MB served and a repository nobody wants to clone. Two levels per case at every third step is 8 MB,
# which is the same order as the eye clips already committed. What is lost is the four middle levels of
# each sweep; what is kept is its two ends, which is where a case's physical quantity actually bites.


def quantise(values: np.ndarray) -> tuple[str, float]:
    """A signed array as base64 bytes on its own symmetric scale, delta-coded over time, with the scale.

    The first row is stored as it is and every later row as its difference from the one before, as a
    signed byte. Activity moves smoothly between simulated steps 20 ms apart, so the differences are
    small and repetitive and the transport compresses them: measured on a case, 1.36 MB gzipped stored
    plainly against 0.74 MB delta-coded, for the same bytes.
    """
    scale = float(np.nanmax(np.abs(values))) if values.size else 0.0
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0
    bytes_ = np.clip(np.round(127 * values / scale) + 128, 0, 255).astype(np.uint8)
    if len(bytes_) > 1:
        difference = (bytes_[1:].astype(np.int16) - bytes_[:-1].astype(np.int16)).astype(np.int8)
        bytes_ = np.concatenate([bytes_[:1], difference.view(np.uint8)])
    return base64.b64encode(bytes_.tobytes()).decode("ascii"), scale


def case_clip_path(root: Path, case_id: str, level: int, index: int = CLIP) -> Path:
    return root / "vision" / "cases" / case_id / f"L{level}" / f"{index:02d}.npz"


def run(root: Path, cases_wanted: list[str] | None = None, levels: list[int] | None = None,
        arm: str = "connectome", dt_s: float = DT_S, stride: int = STRIDE) -> dict:
    """Run the frozen network on each case's clip and write what its pathway did."""
    registry, digest = cases.load_cases()
    network, _, description = build_arm(arm)
    types = available(network, PATHWAY)
    # a type with one cell for the whole lattice cannot be drawn on it; it is named rather than hidden
    spanning = wide_field(network, PATHWAY)
    DERIVED.mkdir(parents=True, exist_ok=True)
    manifest = {
        "artifact": "brainclips", "version": ARTIFACT_VERSION,
        "source": {"cases": "cases.json", "cases_sha256": digest, "arm": arm,
                   "description": description, "dt_s": dt_s},
        "types": types, "wide_field": spanning, "stride": stride, "encoding": "delta-int8",
        "cases": {},
    }

    for case_id, case in registry["cases"].items():
        if cases_wanted and case_id not in cases_wanted:
            continue
        wanted_levels = (levels if levels is not None
                         else [i for i in ENDS if i < len(case["variant"]["levels"])])
        written = {}
        for level in wanted_levels:
            path = case_clip_path(root, case_id, level)
            if not path.exists():
                continue
            with np.load(path, allow_pickle=True) as clip:
                stamp = json.loads(str(clip["stamp"]))
                lum = np.asarray(clip["lum"], dtype=np.float32)
            interval = float(stamp.get("interval_s") or 0.1)
            activity = activity_of(network, lum, interval, dt_s, types=types, every_step=True)
            steps_per_frame = max(int(round(interval / dt_s)), 1)
            activity = activity[:MAX_STEPS][::stride]
            data, scales = {}, {}
            for index, name in enumerate(types):
                encoded, scale = quantise(np.asarray(activity[:, index], dtype=np.float32))
                data[name] = encoded
                scales[name] = round(scale, 6)
            written[str(level)] = {
                "steps": int(activity.shape[0]), "frames": int(len(lum)),
                "steps_per_frame": steps_per_frame, "stride": stride,
                "step_s": round(dt_s * stride, 6), "interval_s": interval,
                "value": case["variant"]["levels"][level],
                "scales": scales, "activity": data,
            }
        if not written:
            continue
        payload = {
            "artifact": "brainclip", "version": ARTIFACT_VERSION, "case": case_id,
            "name": case["name"], "quantity": case["variant"]["quantity"],
            "unit": case["variant"]["unit"], "types": types, "columns": 721,
            "arm": arm, "dt_s": dt_s, "levels": written,
        }
        out = DERIVED / f"{case_id}.json"
        write_json(out, payload)
        manifest["cases"][case_id] = {
            "path": f"brainclips/{case_id}.json",
            "bytes": out.stat().st_size,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "levels": len(written),
            "steps": written[next(iter(written))]["steps"],
        }
    write_json(MANIFESTS / "brainclips.json", manifest)
    return manifest
