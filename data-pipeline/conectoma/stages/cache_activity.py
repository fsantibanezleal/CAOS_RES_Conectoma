"""Stage: run a frozen network over the corpus once and keep what a readout needs.

In the reservoir regime nothing inside the network is trained, so a clip's activity depends only on the
clip and on which network it is. Computing it once and caching it is what makes this unit feasible: five
seeds times four arms of readout training then costs minutes rather than days, because no gradient ever
crosses the network or the time axis (design: management repo, wip/connectome-vision/10).

What is kept, per clip: the voltage of the cell types the connectome specification DECLARES as its output
units (`T4a` to `T4d`, `T5a` to `T5d` for the MaleCNS optic lobe), on the 721 columns, one row per source
frame, as float16. That is 369 KB for a 32-frame clip. Reading depth out of the fly's motion detectors
alone is the biological question this row asks, not a shortcut.

One row per frame, not per simulated step: the network is stepped at the published `dt` (0.02 s) with each
frame held for its own interval, and the row kept is the LAST step of that frame, which is the state after
the network has seen the whole frame. The stamp records the interval, the step, the regime, the arm and
the digests of the specification and of this code, so a cache can never be read as if it came from another
network.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import torch

from conectoma.core.jsonio import write_json

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC = REPO_ROOT / "data" / "derived" / "connectome" / "malecns-optic-lobe-r.json"
DT_S = 0.02
CACHE_VERSION = 1


def arm_spec(arm: str, seed: int = 0) -> tuple[dict, str]:
    """The connectome specification of one arm: the measured one, or a null built from it."""
    from conectoma.connectome import nulls

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    if arm == "connectome":
        return spec, "the measured MaleCNS optic-lobe connectome"
    builders = {
        "N1": (nulls.degree_preserving_rewire, "degree-preserving rewiring"),
        "N2": (nulls.random_sparse, "size-matched random sparse graph"),
        "N3": (nulls.sign_shuffle, "sign shuffle"),
    }
    if arm not in builders:
        raise KeyError(f"unknown arm {arm}; known: connectome, {', '.join(sorted(builders))}")
    build, description = builders[arm]
    return build(spec, seed), description


def code_digest() -> str:
    here = Path(__file__)
    digest = hashlib.sha256(here.read_bytes())
    for name in ("regimes.py", "engine.py"):
        digest.update((here.parents[1] / "network" / name).read_bytes())
    return digest.hexdigest()


def spec_digest(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()


def output_types(network) -> list[str]:
    return [t.decode() if isinstance(t, bytes) else str(t)
            for t in network.connectome.output_cell_types[:]]


def activity_of(network, lum: np.ndarray, interval_s: float, dt_s: float = DT_S) -> np.ndarray:
    """(frames, types, columns) the output units' voltage, one row per frame, on the given network."""
    from flyvis.utils.activity_utils import LayerActivity

    repeats = max(int(round(float(interval_s) / dt_s)), 1)
    device = next(network.parameters()).device
    movie = torch.from_numpy(np.repeat(np.asarray(lum, dtype=np.float32), repeats, axis=0))
    with torch.no_grad():
        states = network.simulate(movie[None, :, None, :].to(device), dt_s)
        layers = LayerActivity(states, network.connectome, use_central=False)
        stack = torch.stack([getattr(layers, name) for name in output_types(network)], dim=2)
    held = stack[0].detach().cpu().numpy()
    return held[repeats - 1:: repeats][: len(lum)].astype(np.float16)


def cache_path(root: Path, arm: str, key: str) -> Path:
    return root / "activity" / arm / f"{key.replace('/', '_')}.npz"


def build_arm(arm: str, seed: int = 0, regime: str = "R0", transfer: bool = True):
    """The network of one arm, frozen, on the fastest device available.

    `transfer` is what R0 was specified to mean (design dossier 06 section 1.3): the per-cell-type
    biophysics come from the published ensemble where the types match, and only the wiring is this
    product's. It is not a detail. Measured on a drifting pattern, with the engine's DEFAULT
    initialisation instead, the signal dies before it reaches the output units: the standard deviation
    over time is 0.005 at L1, 0.0002 at Tm3 and 0.0001 at T4a, against 0.086, 0.014 and 0.039 with the
    transfer. A reservoir read from inert cells measures nothing, so every arm uses the transfer and the
    stamp records it.
    """
    from conectoma.network.engine import published_model_dir
    from conectoma.network.regimes import build_network

    spec, description = arm_spec(arm, seed)
    source = SPEC
    scratch = None
    if arm != "connectome":
        scratch = REPO_ROOT / "data" / "derived" / "connectome" / f".arm-{arm}-{seed}.json"
        write_json(scratch, spec)
        source = scratch
    try:
        network = build_network(str(source), regime,
                                transfer_from=published_model_dir("000") if transfer else None)
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)
    network.eval()
    if torch.cuda.is_available():
        network = network.cuda()
    return network, spec, description


def run(root: Path, clips: list, arm: str = "connectome", seed: int = 0, regime: str = "R0",
        interval_s: float = 0.1, dt_s: float = DT_S, progress_every: int = 50,
        transfer: bool = True) -> dict:
    """Cache every clip's activity for one arm. `clips` are paths or (key, path); a cached one is skipped."""
    network, spec, description = build_arm(arm, seed, regime, transfer)
    stamp = {
        "cache_version": CACHE_VERSION, "arm": arm, "seed": seed, "regime": regime,
        "transfer": transfer,
        "spec_sha256": spec_digest(spec), "code_sha256": code_digest(), "dt_s": dt_s,
        "interval_s": interval_s, "types": output_types(network), "description": description,
    }
    started = time.time()
    written = skipped = 0
    for index, item in enumerate(clips):
        key, path = item if isinstance(item, tuple) else (item.stem, item)
        out = cache_path(root, arm, key)
        if out.exists():
            with np.load(out, allow_pickle=True) as existing:
                if json.loads(str(existing["stamp"])) == stamp:
                    skipped += 1
                    continue
        with np.load(path, allow_pickle=True) as clip:
            lum = np.asarray(clip["lum"], dtype=np.float32)
            frames = np.asarray(clip["frames"])
            depth = np.asarray(clip["depth"], dtype=np.float32)
            boundary = np.asarray(clip["boundary"]) if "boundary" in clip.files else None
        activity = activity_of(network, lum, interval_s, dt_s)
        out.parent.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(out.stem + ".partial.npz")
        arrays = {"activity": activity, "depth": depth.astype(np.float16), "frames": frames}
        if boundary is not None:
            arrays["boundary"] = boundary.astype(np.uint8)
        np.savez_compressed(partial, stamp=json.dumps(stamp), **arrays)
        os.replace(partial, out)
        written += 1
        if progress_every and (index + 1) % progress_every == 0:
            done = index + 1
            rate = (time.time() - started) / max(done, 1)
            print(f"{arm}: {done}/{len(clips)} clips, {rate:.2f} s each, "
                  f"{rate * (len(clips) - done) / 60:.1f} min left", flush=True)
    return {"arm": arm, "seed": seed, "clips": len(clips), "written": written, "skipped": skipped,
            "seconds": round(time.time() - started, 1), "stamp": stamp}


def case_clips(root: Path, cases_wanted: list[str] | None = None, levels: list[int] | None = None,
               clips: int | None = None) -> list[tuple[str, Path]]:
    """The case renderings, as (cache key, path): what a method is finally scored on.

    The key carries the case, the level and the clip index, because a case clip is not a corpus clip: the
    same source item appears at six levels and each is its own rendering.
    """
    from conectoma.vision import cases as registry

    loaded, _ = registry.load_cases()
    out = []
    for case_id, case in loaded["cases"].items():
        if cases_wanted and case_id not in cases_wanted:
            continue
        for level in range(len(case["variant"]["levels"])):
            if levels is not None and level not in levels:
                continue
            for index in range(clips if clips is not None else loaded["clips"]):
                path = root / "vision" / "cases" / case_id / f"L{level}" / f"{index:02d}.npz"
                if path.exists():
                    out.append((f"case_{case_id}_L{level}_{index:02d}", path))
    return out


def split_clips(root: Path, split: str, limit: int | None = None) -> list[Path]:
    """The rendered clips of one split, from the committed split table."""
    import csv

    table = REPO_ROOT / "data" / "derived" / "vision" / "tartanair-clips.csv"
    wanted = []
    with table.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["split"] != split:
                continue
            environment, difficulty, trajectory, start = row["key"].split("/")
            path = (root / "vision" / "tartanair" / "rendered" / environment / difficulty / trajectory
                    / f"clip_{int(start):06d}.npz")
            if path.exists():
                wanted.append(path)
    wanted.sort()
    return wanted[:limit] if limit else wanted
