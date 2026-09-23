"""Contract 2 for what the network CONCLUDES from each case: the rest of the chain, per frame.

The App already shows what the fly's eye receives (`export_eyeclips`) and what the pathway's cells do
(`export_brainclips`). Neither shows the answer. This artifact carries it: for every case and both ends of
its sweep, on the same clip the other two artifacts show, the depth the two connectome rows read out of
the network, frame by frame, with the ground truth it is graded against.

    M05   the measured connectome, frozen, read by its trained head
    M06   the same wiring with its biophysics trained (regime R1), read by its own head

Both are exactly the readout the Experiments page scores: `m05.run` and `m06.run`, the median over each
row's five seeds, refused where the tolerance recorded in the row's committed evaluation report refuses
it. Nothing is re-fitted here and nothing is chosen for the picture.

Beside the readout, the measured CIRCUIT between the pathway's cell types, read from the committed
connectome specification: which type drives which, with how many synapses onto one target cell and with
which sign. The web animates it with the pathway's activity, so what pulses on screen is the wiring the
network was built from, not a drawing of it.

And one measurement the web needs in order to refuse something: the direction selectivity of the frozen
network's T4 and T5 cells, read from the committed characterisation. It is at most 0.012, so the frozen
network carries no motion estimate a reader could be shown as arrows, and the web draws none.

Encodings, all recorded in the artifact:
  depth         one byte per column per frame, log-spaced from 0.1 m to 5 km (4.4 percent a step);
                0 means no value
  spread        the head's own predicted spread in log depth, 0 to 4 on one byte
  refused       one bit per column per frame, packed
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.stages.export_brainclips import CLIP, ENDS, case_clip_path
from conectoma.vision import cases

ARTIFACT_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "chain"
MANIFESTS = REPO_ROOT / "data" / "derived" / "manifests"
REPORTS = REPO_ROOT / "data" / "derived" / "evaluation"
SPEC = REPO_ROOT / "data" / "derived" / "connectome" / "malecns-optic-lobe-r.json"
CHARACTERISATION = (REPO_ROOT / "data" / "derived" / "connectome"
                    / "malecns-optic-lobe-r.characterization.json")

ROWS = ("M05", "M06")
DEPTH_LO_M = 0.1
DEPTH_HI_M = 5000.0
SPREAD_HI = 4.0

# The pathway the circuit draws, in the order the signal travels, and the layer each type is drawn in.
# `R1-R6` is the photoreceptor input the lamina receives; CT1 is wide-field (one cell for the whole
# lattice) and is drawn as a node although it has no map.
CIRCUIT_LAYERS = {
    "R1-R6": "retina",
    "L1": "lamina", "L2": "lamina", "L3": "lamina",
    "Mi1": "medulla", "Tm3": "medulla", "Tm1": "medulla", "Tm2": "medulla",
    "Mi9": "medulla", "Mi4": "medulla", "CT1": "medulla",
    "T4a": "output", "T4b": "output", "T4c": "output", "T4d": "output",
    "T5a": "output", "T5b": "output", "T5c": "output", "T5d": "output",
}


# ------------------------------------------------------------------ encodings


def encode_depth(depth: np.ndarray) -> str:
    """Metres on a log scale, one byte each; 0 is reserved for 'no value'."""
    depth = np.asarray(depth, dtype=np.float64)
    lo, hi = np.log(DEPTH_LO_M), np.log(DEPTH_HI_M)
    valid = np.isfinite(depth) & (depth > 0)
    out = np.zeros(depth.shape, dtype=np.uint8)
    with np.errstate(divide="ignore", invalid="ignore"):
        scaled = 1 + np.round(254 * (np.log(np.where(valid, depth, 1.0)) - lo) / (hi - lo))
    out[valid] = np.clip(scaled[valid], 1, 255).astype(np.uint8)
    return base64.b64encode(out.tobytes()).decode("ascii")


def decode_depth(encoded: str, shape: tuple[int, int]) -> np.ndarray:
    raw = np.frombuffer(base64.b64decode(encoded), dtype=np.uint8).reshape(shape)
    lo, hi = np.log(DEPTH_LO_M), np.log(DEPTH_HI_M)
    out = np.exp(lo + (raw.astype(np.float64) - 1) * (hi - lo) / 254)
    return np.where(raw == 0, np.nan, out)


def encode_spread(spread: np.ndarray) -> str:
    spread = np.nan_to_num(np.asarray(spread, dtype=np.float64), nan=SPREAD_HI, posinf=SPREAD_HI)
    out = np.clip(np.round(255 * spread / SPREAD_HI), 0, 255).astype(np.uint8)
    return base64.b64encode(out.tobytes()).decode("ascii")


def encode_mask(mask: np.ndarray) -> str:
    """One bit per column, rows padded to whole bytes: numpy's packbits, big-endian within a byte."""
    packed = np.packbits(np.asarray(mask, dtype=bool), axis=-1)
    return base64.b64encode(packed.tobytes()).decode("ascii")


def decode_mask(encoded: str, shape: tuple[int, int]) -> np.ndarray:
    raw = np.frombuffer(base64.b64decode(encoded), dtype=np.uint8)
    rows, columns = shape
    return np.unpackbits(raw.reshape(rows, -1), axis=-1)[:, :columns].astype(bool)


# ------------------------------------------------------------------ what the readout was scored with


def scored_thresholds(row: str, reports: Path | None = None) -> dict:
    """The tolerance and window the Experiments page scored `row` with, from its committed report."""
    path = (reports or REPORTS) / f"{row}.json"
    if not path.exists():
        raise FileNotFoundError(f"{row} has not been scored yet ({path.name} is missing)")
    report = json.loads(path.read_text(encoding="utf-8"))
    thresholds = report.get("thresholds") or {}
    if "tolerance" not in thresholds:
        raise ValueError(f"{row}'s report records no calibrated tolerance")
    return {"tolerance": float(thresholds["tolerance"]), "window": int(thresholds.get("window", 2))}


def readout(row: str, clip: dict, spacing: float, root: Path, key: str, thresholds: dict) -> dict:
    """What `row` reads out of this clip: the very call the scoring stage makes."""
    from conectoma.methods import m05, m06

    module = {"M05": m05, "M06": m06}[row]
    return module.run(clip, spacing, root=root, arm="connectome", key=key, **thresholds)


# ------------------------------------------------------------------ the circuit and the refusal


def circuit(spec_path: Path | None = None) -> dict:
    """The measured connections between the pathway's cell types, from the committed specification.

    `synapses` is the specification's own quantity: the synapses one target cell receives from the source
    type, summed over the column offsets the filter spans. `sign` is the specification's sign.
    """
    spec = json.loads((spec_path or SPEC).read_text(encoding="utf-8"))
    names = {node["name"] for node in spec["nodes"]}
    wanted = [name for name in CIRCUIT_LAYERS if name in names]
    edges = []
    for edge in spec["edges"]:
        if edge["src"] in CIRCUIT_LAYERS and edge["tar"] in CIRCUIT_LAYERS:
            synapses = float(sum(count for _, count in edge["offsets"]))
            if synapses <= 0:
                continue
            edges.append({"source": edge["src"], "target": edge["tar"],
                          "synapses": round(synapses, 3), "sign": int(np.sign(edge["alpha"]))})
    edges.sort(key=lambda e: (list(CIRCUIT_LAYERS).index(e["source"]),
                              list(CIRCUIT_LAYERS).index(e["target"])))
    return {
        "nodes": [{"type": name, "layer": CIRCUIT_LAYERS[name]} for name in wanted],
        "edges": edges,
        "source": "data/derived/connectome/malecns-optic-lobe-r.json",
    }


def direction_selectivity(path: Path | None = None) -> dict:
    """The measured direction selectivity of the frozen network's T4 and T5 (the transferred arm)."""
    report = json.loads((path or CHARACTERISATION).read_text(encoding="utf-8"))
    tuning = report["frozen"]["transfer"]["tuning"]
    per_type = {name: float(values["dsi"][0]) for name, values in tuning.items()}
    return {"per_type": per_type, "largest": max(per_type.values()),
            "protocol": "moving edges, 12 directions, 6 speeds, both polarities (network/tuning.py)",
            "network": "the frozen MaleCNS network with the published biophysics transferred (M05)"}


# ------------------------------------------------------------------ the run


def run(root: Path, cases_wanted: list[str] | None = None, reports: Path | None = None,
        out_dir: Path | None = None, manifests: Path | None = None) -> dict:
    """Write one chain file per case, the circuit, and the manifest that lists them with their digests."""
    root = Path(root)
    out_dir = Path(out_dir) if out_dir is not None else DERIVED
    manifests = Path(manifests) if manifests is not None else MANIFESTS
    registry, digest = cases.load_cases()
    thresholds = {}
    unscored = {}
    for row in ROWS:
        try:
            thresholds[row] = scored_thresholds(row, reports)
        except (FileNotFoundError, ValueError) as missing:
            unscored[row] = str(missing)

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "artifact": "chain", "version": ARTIFACT_VERSION,
        "source": {"cases": "cases.json", "cases_sha256": digest, "clip": CLIP},
        "rows": {row: ({"thresholds": thresholds[row]} if row in thresholds
                       else {"unscored": unscored[row]}) for row in ROWS},
        "encoding": {"depth": {"lo_m": DEPTH_LO_M, "hi_m": DEPTH_HI_M, "zero": "no value"},
                     "spread": {"hi": SPREAD_HI}, "refused": "packbits, one bit per column"},
        "cases": {}, "missing": {},
    }

    for case_id, case in registry["cases"].items():
        if cases_wanted and case_id not in cases_wanted:
            continue
        levels = {}
        for level in [i for i in ENDS if i < len(case["variant"]["levels"])]:
            path = case_clip_path(root, case_id, level)
            if not path.exists():
                manifest["missing"][f"{case_id}/L{level}"] = "the case clip has not been rendered"
                continue
            with np.load(path, allow_pickle=True) as loaded:
                stamp = json.loads(str(loaded["stamp"]))
                clip = {k: loaded[k] for k in loaded.files if k != "stamp"}
            spacing = stamp["measured"].get("column_spacing_deg")
            key = f"case_{case_id}_L{level}_{CLIP:02d}"
            frames = int(len(clip["lum"]))
            steps = max(frames - 1, 1)
            truth = np.asarray(clip["depth"], dtype=np.float64)[:steps] if "depth" in clip else None
            entry = {"frames": frames, "steps": steps, "value": case["variant"]["levels"][level],
                     "truth": encode_depth(truth) if truth is not None else None, "rows": {}}
            for row in ROWS:
                if row not in thresholds:
                    entry["rows"][row] = {"missing": unscored[row]}
                    continue
                try:
                    result = readout(row, clip, spacing, root, key, thresholds[row])
                except (FileNotFoundError, ValueError) as failed:
                    # named, never drawn as an empty map
                    entry["rows"][row] = {"missing": str(failed)}
                    manifest["missing"][f"{case_id}/L{level}/{row}"] = str(failed)
                    continue
                everywhere = result.get("distance_all_m", result["distance_m"])
                entry["rows"][row] = {
                    "depth": encode_depth(np.asarray(everywhere)[:steps]),
                    "spread": encode_spread(np.asarray(result["uncertainty"])[:steps]),
                    "refused": encode_mask(np.asarray(result["unknown"])[:steps]),
                    "seeds": int(result.get("seeds", 0)),
                }
            levels[str(level)] = entry
        if not levels:
            continue
        payload = {"artifact": "chainclip", "version": ARTIFACT_VERSION, "case": case_id,
                   "name": case["name"], "quantity": case["variant"]["quantity"],
                   "unit": case["variant"]["unit"], "grades": case.get("grades", []),
                   "columns": 721, "clip": CLIP, "levels": levels}
        out = out_dir / f"{case_id}.json"
        write_json(out, payload)
        manifest["cases"][case_id] = {"path": f"chain/{case_id}.json", "bytes": out.stat().st_size,
                                      "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                                      "levels": len(levels)}

    wiring = out_dir / "circuit.json"
    write_json(wiring, {"artifact": "circuit", "version": ARTIFACT_VERSION, **circuit(),
                        "direction_selectivity": direction_selectivity()})
    manifest["circuit"] = {"path": "chain/circuit.json", "bytes": wiring.stat().st_size,
                           "sha256": hashlib.sha256(wiring.read_bytes()).hexdigest()}
    manifests.mkdir(parents=True, exist_ok=True)
    write_json(manifests / "chain.json", manifest)
    return manifest
