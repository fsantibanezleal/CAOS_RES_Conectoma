"""Stage: place FlyGym's compound eye on the engine's lattice, and write the evidence.

Writes data/derived/vision/flygym-eye.json: the lattice fit of FlyGym's 721 ommatidia, the score of every
one of the twelve lattice symmetries against the engine's anatomical frame, the chosen one, and the map from
each FlyGym ommatidium (by FlyGym's id) to the engine's column index. The map must be a bijection onto the
engine's 721 columns, or the stage fails.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.vision import eye, flygym_eye

REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED = REPO_ROOT / "data" / "derived" / "vision"


def column_map(uv_flygym: np.ndarray, symmetry: np.ndarray) -> np.ndarray:
    """For each FlyGym ommatidium, the engine column index it becomes under `symmetry`."""
    engine_uv = (symmetry @ uv_flygym.T).T
    index = {tuple(p): i for i, p in enumerate(eye.lattice_coordinates())}
    out = np.array([index.get(tuple(p), -1) for p in engine_uv], dtype=np.int64)
    if (out < 0).any() or len(set(out.tolist())) != len(out):
        raise ValueError("the FlyGym ommatidia do not map one to one onto the engine's columns")
    return out


def measure_flygym_eye(derived: Path = DERIVED) -> dict:
    import importlib.metadata

    from flygym import assets_dir

    with np.load(assets_dir / "model/neuromechfly/compound_eye.npz") as data:
        id_map = data["ommatidia_id_map"]
    fit = flygym_eye.fit_lattice(flygym_eye.ommatidium_centres(id_map))
    if not fit["fills_hexagon"]:
        raise ValueError(f"FlyGym's ommatidia do not fill the radius-15 hexagon: {fit}")
    orientation = flygym_eye.orientation()
    symmetry = flygym_eye.symmetries()[orientation["best"]]
    mapping = column_map(fit["uv"], symmetry)
    report = {
        "flygym": importlib.metadata.version("flygym"),
        "ommatidia": int(id_map.max()),
        "lattice_fit": {"basis_row_col": fit["basis_row_col"].round(4).tolist(),
                        "max_residual_px": round(fit["max_residual_px"], 4),
                        "fills_hexagon": fit["fills_hexagon"]},
        "orientation": orientation,
        "symmetry_matrix": symmetry.tolist(),
        "engine_column_of_ommatidium": mapping.tolist(),
    }
    derived.mkdir(parents=True, exist_ok=True)
    write_json(derived / "flygym-eye.json", report)
    return report
