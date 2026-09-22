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


# The fly's own visual pathway, in the order the signal travels: the lamina monopolar cells, the medulla
# types that feed motion detection, and the direction-selective outputs. Used for what the web animates;
# the training cache keeps the declared output units only, because that is what the readout reads.
PATHWAY = ("L1", "L2", "L3", "Mi1", "Tm3", "Tm1", "Tm2", "Mi9", "Mi4", "CT1",
           "T4a", "T4b", "T4c", "T4d", "T5a", "T5b", "T5c", "T5d")


def output_types(network) -> list[str]:
    return [t.decode() if isinstance(t, bytes) else str(t)
            for t in network.connectome.output_cell_types[:]]


def available(network, wanted: tuple[str, ...], columns: int = 721) -> list[str]:
    """Those of `wanted` the network carries with ONE CELL PER COLUMN, in the order given.

    A wide-field type is not dropped for being uninteresting: it has a single cell for the whole lattice
    (CT1 in the MaleCNS optic lobe), so it cannot be drawn on the lattice at all and would break a stack
    of per-column maps. What is dropped is named by the caller's report.
    """
    from collections import Counter

    kinds = [t.decode() if isinstance(t, bytes) else str(t) for t in network.connectome.nodes.type[:]]
    counts = Counter(kinds)
    return [name for name in wanted if counts.get(name) == columns]


def wide_field(network, wanted: tuple[str, ...], columns: int = 721) -> list[str]:
    """Those of `wanted` the network carries with fewer cells than columns: one cell sees everything."""
    from collections import Counter

    kinds = [t.decode() if isinstance(t, bytes) else str(t) for t in network.connectome.nodes.type[:]]
    counts = Counter(kinds)
    return [name for name in wanted if 0 < counts.get(name, 0) < columns]


def activity_of(network, lum: np.ndarray, interval_s: float, dt_s: float = DT_S,
                types: list[str] | None = None, every_step: bool = False) -> np.ndarray:
    """(frames, types, columns) the voltage of `types`, one row per frame, on the given network.

    With `every_step` the rows are the simulated steps rather than the source frames, which is what an
    animation wants: the network is stepped at 0.02 s and a source frame lasts several steps, so the
    response moves between frames and a per-frame sample hides it.
    """
    from flyvis.utils.activity_utils import LayerActivity

    repeats = max(int(round(float(interval_s) / dt_s)), 1)
    device = next(network.parameters()).device
    wanted = types or output_types(network)
    movie = torch.from_numpy(np.repeat(np.asarray(lum, dtype=np.float32), repeats, axis=0))
    with torch.no_grad():
        states = network.simulate(movie[None, :, None, :].to(device), dt_s)
        layers = LayerActivity(states, network.connectome, use_central=False)
        stack = torch.stack([getattr(layers, name) for name in wanted], dim=2)
    held = stack[0].detach().cpu().numpy()
    if every_step:
        return held.astype(np.float16)
    return held[repeats - 1:: repeats][: len(lum)].astype(np.float16)


def cache_path(root: Path, arm: str, key: str) -> Path:
    return root / "activity" / arm / f"{key.replace('/', '_')}.npz"


def clip_key(path: Path) -> str:
    """The cache key of a rendered corpus clip: its whole place in the corpus, not its file name.

    A clip's file name is `clip_000665.npz` and the SAME name occurs in many trajectories: across the
    three corpus splits, 1,860 rendered clips carry only 981 distinct file names. Keying the cache by the
    name alone was a silent defect with two consequences, both measured before this function existed:

      - 879 clips never reached the cache at all, because the first writer of a name wins and the stamp of
        a later clip of the same arm is identical, so it is skipped as already cached. The train split
        lost 591 of its 1,437 clips, 41 percent.
      - 199 names occur in more than one split, so a cache read for one split returned another split's
        clip: 107 validation clips and 106 calibration clips resolved to a TRAIN clip's activity and its
        depth. U4's leakage gate was green throughout, and correctly so: it proves the split TABLE has no
        family overlap, and it cannot see a key collapsing distinct clips downstream of it.

    The key is therefore the path below `rendered`, which is the source, environment, difficulty,
    trajectory and clip that the split table itself is keyed by.
    """
    parts = list(Path(path).with_suffix("").parts)
    if "rendered" in parts:
        below = parts[parts.index("rendered") + 1:]
        source = parts[parts.index("rendered") - 1]
        return "_".join([source, *below])
    return Path(path).stem


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
    return cache_with(network, stamp, root, clips, arm, interval_s, dt_s, progress_every)


def cache_with(network, stamp: dict, root: Path, clips: list, cache_key: str,
               interval_s: float = 0.1, dt_s: float = DT_S, progress_every: int = 50) -> dict:
    """Cache the activity a GIVEN network produces, under `cache_key`, with a stamp the caller owns.

    Split out of `run` so a network that was trained rather than built from a specification, whose
    activity is its own per seed (U7), writes exactly the same artifact under its own key, and so a cache
    can still never be read as if it came from another network: the stamp is compared in full.
    """
    label = stamp.get("arm", cache_key)
    started = time.time()
    written = skipped = 0
    for index, item in enumerate(clips):
        key, path = item if isinstance(item, tuple) else (clip_key(item), item)
        out = cache_path(root, cache_key, key)
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
            print(f"{label}: {done}/{len(clips)} clips, {rate:.2f} s each, "
                  f"{rate * (len(clips) - done) / 60:.1f} min left", flush=True)
    return {"arm": label, "cache": cache_key, "seed": stamp.get("seed"),
            "clips": len(clips), "written": written, "skipped": skipped,
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
