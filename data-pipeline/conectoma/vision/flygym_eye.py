"""The fly's own eye, from FlyGym: its 721 ommatidia placed on the engine's lattice, and exact per-ommatidium
ground truth.

FlyGym renders each eye with a MuJoCo camera, corrects the rectilinear image to a fisheye by a nearest-pixel
remap, and averages each ommatidium's pixels (its `ommatidia_id_map`, 721 ommatidia per eye). The same remap
and the same pixel sets are applied here to MuJoCo's depth and segmentation renders of the same camera, so a
column's depth and its figure share come from exactly the pixels its luminance does.

FlyGym numbers ommatidia row by row on its own grid, not in the engine's (u, v) order. Two steps place them:
- geometry: the ommatidium centres (centroids of their pixel sets) form a hexagonal lattice, 16.5 pixels
  between neighbours along three directions 60 degrees apart (measured); fitting its two basis vectors gives
  every ommatidium integer lattice coordinates, which must fill the radius-15 hexagon exactly;
- orientation: which of the twelve lattice symmetries takes FlyGym's axes to the engine's is measured, not
  assumed, by where known world directions (forward, up) land on both lattices (`orientation`).
"""

from __future__ import annotations

import numpy as np

EXTENT = 15


def ommatidium_centres(id_map: np.ndarray) -> np.ndarray:
    """(721, 2) centroid (row, column) of each ommatidium's pixels, ordered by FlyGym's id (1..721)."""
    rows, cols = np.nonzero(id_map)
    ids = id_map[rows, cols]
    count = np.bincount(ids, minlength=id_map.max() + 1)[1:]
    cy = np.bincount(ids, weights=rows, minlength=id_map.max() + 1)[1:] / count
    cx = np.bincount(ids, weights=cols, minlength=id_map.max() + 1)[1:] / count
    return np.stack([cy, cx], axis=1)


def fit_lattice(centres: np.ndarray, extent: int = EXTENT) -> dict:
    """Integer axial coordinates of every ommatidium on FlyGym's own lattice, from its geometry.

    The basis is read from the data: `a` the neighbour step along the rows, `b` the neighbour step 60 degrees
    from it, both averaged over every neighbour pair. The fit must be exact to a fraction of a pixel and must
    fill the radius-`extent` hexagon with every coordinate once.
    """
    from scipy.spatial import cKDTree

    tree = cKDTree(centres)
    _, index = tree.query(centres, k=7)
    steps = (centres[index[:, 1:]] - centres[:, None, :]).reshape(-1, 2)
    angle = np.degrees(np.arctan2(steps[:, 0], steps[:, 1]))
    a = steps[np.abs(angle - 90) < 15].mean(axis=0)
    b = steps[np.abs(angle - 30) < 15].mean(axis=0)
    basis = np.stack([a, b], axis=1)                          # columns: a, b in (row, col)
    centre = centres[np.argmin(np.linalg.norm(centres - centres.mean(axis=0), axis=1))]
    uv_float = np.linalg.solve(basis, (centres - centre).T).T
    uv = np.rint(uv_float).astype(np.int64)
    residual = np.linalg.norm((uv_float - uv) @ basis.T, axis=1)
    inside = (np.abs(uv) <= extent).all(axis=1) & (np.abs(uv.sum(axis=1)) <= extent)
    unique = len({tuple(p) for p in uv}) == len(uv)
    return {"uv": uv, "basis_row_col": basis, "centre_row_col": centre,
            "max_residual_px": float(residual.max()),
            "all_inside": bool(inside.all()), "unique": unique,
            "fills_hexagon": bool(unique and inside.all() and len(uv) == 3 * extent * (extent + 1) + 1)}


# The twelve symmetries of the hexagonal lattice. In cube coordinates (q, r, s) = (u, v, -u - v) they are the
# six permutations of the three coordinates, each with or without a global sign. The lattice's neighbour
# steps are u, v and u - v (the hexagon is |u|, |v|, |u + v| <= extent), and every one of these maps takes
# that set onto itself. A name gives the old coordinates the new u and v are read from: "-(w,v)" makes the
# new u equal to -s and the new v equal to -v.
def symmetries() -> dict[str, np.ndarray]:
    from itertools import permutations

    in_axial = {0: np.array([1, 0]), 1: np.array([0, 1]), 2: np.array([-1, -1])}   # q, r, s from (u, v)
    letters = "uvw"
    out = {}
    for order in permutations(range(3)):
        for sign, mark in ((1, "+"), (-1, "-")):
            matrix = sign * np.stack([in_axial[order[0]], in_axial[order[1]]])      # rows: new u, new v
            out[f"{mark}({letters[order[0]]},{letters[order[1]]})"] = matrix
    return out


def fisheye_source_index(nrows: int, ncols: int, zoom: float, distortion: float) -> np.ndarray:
    """For each fisheye pixel, the flat index of the rectilinear pixel FlyGym copies into it (-1: none).

    The same arithmetic as `flygym.vision.Retina._correct_fisheye`, vectorised, so it can move depth and
    segment images exactly as FlyGym moves colour.
    """
    rows, cols = np.mgrid[0:nrows, 0:ncols].astype(np.float64)
    row_norm = ((2 * rows - nrows) / nrows) / zoom
    col_norm = ((2 * cols - ncols) / ncols) / zoom
    denom = 1 - distortion * (col_norm**2 + row_norm**2) + 1e-6
    # int() truncates toward zero, and so does numpy's cast, negative values included
    src_row = (((row_norm / denom) + 1) * nrows / 2).astype(np.int64)
    src_col = (((col_norm / denom) + 1) * ncols / 2).astype(np.int64)
    ok = (src_row >= 0) & (src_row < nrows) & (src_col >= 0) & (src_col < ncols)
    return np.where(ok, src_row * ncols + src_col, -1)


def pool(values: np.ndarray, source_index: np.ndarray, id_map: np.ndarray,
         reducer: str = "mean") -> np.ndarray:
    """One value per ommatidium from a rectilinear render (H, W): mean or median over its fisheye pixels.

    Pixels the fisheye leaves empty are black in FlyGym's image (they count as zero for luminance, as there);
    for depth and labels they are left out.
    """
    flat = values.reshape(-1)
    ids = id_map.reshape(-1)
    source = source_index.reshape(-1)
    n = int(id_map.max())
    out = np.full(n, np.nan, dtype=np.float64)
    for k in range(1, n + 1):
        pixels = source[ids == k]
        if reducer == "mean":
            sampled = np.where(pixels >= 0, flat[np.maximum(pixels, 0)], 0.0)
            out[k - 1] = sampled.mean()
        else:
            sampled = flat[pixels[pixels >= 0]]
            if sampled.size:
                out[k - 1] = np.median(sampled) if reducer == "median" else (sampled > 0).mean()
    return out


# ------------------------------------------------------------------------------------------ orientation

# A regular embedding of axial coordinates, for measuring angles: u along (1, 0), v at 60 degrees from it.
_REGULAR = np.array([[1.0, 0.5], [0.0, np.sqrt(3) / 2]])


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = _REGULAR @ a, _REGULAR @ b
    return float(ra @ rb / (np.linalg.norm(ra) * np.linalg.norm(rb)))


def engine_direction(angle_deg: float) -> np.ndarray:
    """The axial (u, v) direction in which the engine's own moving edge at `angle_deg` travels.

    Measured on the stimulus itself: the centroid of the lit columns of a bright edge, early against late
    in its sweep. The engine's known preferred directions are stated in this same stimulus frame.
    """
    from conectoma.network.tuning import moving_edges
    from conectoma.vision.eye import lattice_coordinates

    dataset = moving_edges(speeds=[9.7], device="cpu")
    table = dataset.arg_df
    row = table[(np.isclose(table["angle"], angle_deg)) & (table["intensity"] == 1)].index[0]
    frames = np.asarray(dataset[row].cpu()).reshape(-1, 721)
    uv = lattice_coordinates().astype(np.float64)
    lit = frames > 0.75
    counts = lit.sum(axis=1)
    moving = np.nonzero((counts > 30) & (counts < 690))[0]   # while the edge is inside the lattice
    early, late = moving[len(moving) // 4], moving[3 * len(moving) // 4]
    # the lit region grows in the direction of motion, so its centroid moves that way
    return uv[lit[late]].mean(axis=0) - uv[lit[early]].mean(axis=0)


def _eye_simulation(markers: dict, radius_mm: float):
    import mujoco as mj
    from flygym.anatomy import AxisOrder, JointPreset, Skeleton
    from flygym.compose.fly import NeuroMechFly
    from flygym.compose.pose import KinematicPosePreset
    from flygym.compose.world import TetheredWorld
    from flygym.simulation import Simulation
    from flygym.utils.math import Rotation3D

    skeleton = Skeleton(axis_order=AxisOrder.YAW_PITCH_ROLL, joint_preset=JointPreset.LEGS_ONLY)
    pose = KinematicPosePreset.NEUTRAL.get_pose_by_axis_order(AxisOrder.YAW_PITCH_ROLL)
    fly = NeuroMechFly(name="eye_fly")
    fly.add_joints(skeleton, neutral_pose=pose)
    fly.add_vision()
    world = TetheredWorld(name="eye_world")
    for name, position in markers.items():
        body = world.mjcf_root.worldbody.add_body(name=name, pos=[float(x) for x in position])
        body.add_geom(name=f"{name}_geom", type=mj.mjtGeom.mjGEOM_SPHERE, size=[radius_mm, 0, 0],
                      rgba=[1, 1, 1, 1], contype=0, conaffinity=0)
    world.add_fly(fly, spawn_position=[0, 0, 1.5], spawn_rotation=Rotation3D("quat", [1, 0, 0, 0]))
    sim = Simulation(world)
    sim.reset()
    mj.mj_forward(sim.mj_model, sim.mj_data)
    return sim, fly


def flygym_directions(distance_mm: float = 30.0, radius_mm: float = 1.5) -> dict:
    """Where forward and upward displacements land on FlyGym's own lattice, for the right eye.

    Four spheres are placed at `distance_mm` from the right eye's camera, 30 degrees forward and backward of
    the lateral direction and 30 degrees above and below it (the fly faces +x with z up, so its right is -y).
    Their images are found in the eye's segmentation render, through the same fisheye and ommatidium pixels
    FlyGym uses, and the axial centroid of the ommatidia each covers is its position on the lattice.
    """
    import mujoco as mj
    import yaml
    from flygym import assets_dir

    sim, fly = _eye_simulation({}, radius_mm)
    camera = int(sim._intern_eye_camera_ids_by_fly[fly.name][1])          # right eye
    eye = sim.mj_data.cam_xpos[camera].copy()
    c, s = np.cos(np.radians(30)), np.sin(np.radians(30))
    offsets = {"front": [s, -c, 0], "back": [-s, -c, 0], "up": [0, -c, s], "down": [0, -c, -s]}
    sim, fly = _eye_simulation({f"marker_{k}": eye + distance_mm * np.array(v) for k, v in offsets.items()},
                               radius_mm)
    camera = int(sim._intern_eye_camera_ids_by_fly[fly.name][1])

    with open(assets_dir / "model/neuromechfly/vision.yaml", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    with np.load(assets_dir / "model/neuromechfly/compound_eye.npz") as data:
        id_map = data["ommatidia_id_map"]
    renderer = mj.Renderer(sim.mj_model, height=config["raw_img_height_px"], width=config["raw_img_width_px"])
    option = mj.MjvOption()
    option.geomgroup[1] = 0
    option.geomgroup[2] = 0
    renderer.enable_segmentation_rendering()
    renderer.update_scene(sim.mj_data, camera, scene_option=option)
    segmentation = renderer.render()[..., 0]
    source = fisheye_source_index(config["raw_img_height_px"], config["raw_img_width_px"],
                                  config["fisheye_zoom"], config["fisheye_distortion_coefficient"])
    uv = fit_lattice(ommatidium_centres(id_map))["uv"].astype(np.float64)
    positions, covered = {}, {}
    for key in offsets:
        geom = mj.mj_name2id(sim.mj_model, mj.mjtObj.mjOBJ_GEOM, f"marker_{key}_geom")
        share = pool((segmentation == geom).astype(np.float64), source, id_map, reducer="mean")
        hit = share > 0.2
        covered[key] = int(hit.sum())
        positions[key] = (uv[hit] * share[hit, None]).sum(axis=0) / share[hit].sum() if hit.any() else None
    if any(p is None for p in positions.values()):
        raise RuntimeError(f"a marker is not seen by the right eye: ommatidia covered {covered}")
    return {"front_to_back": positions["back"] - positions["front"],
            "upward": positions["up"] - positions["down"], "ommatidia_covered": covered}


def orientation() -> dict:
    """The lattice symmetry taking FlyGym's axes to the engine's, with every candidate's score.

    The engine's frame is anatomical through the known preferred directions of T4 and T5: front-to-back is
    the direction of T4a (pi) and upward that of T4c (pi / 2). A symmetry scores the sum of the cosines
    between its image of FlyGym's front-to-back and upward displacements and the engine's; the best is
    taken, and the whole table is kept as the evidence.
    """
    engine = {"front_to_back": engine_direction(180.0), "upward": engine_direction(90.0)}
    fly = flygym_directions()
    scores = {name: round(sum(_cosine(matrix @ fly[k], engine[k]) for k in engine), 4)
              for name, matrix in symmetries().items()}
    best = max(scores, key=scores.get)
    return {"engine": {k: v.tolist() for k, v in engine.items()},
            "flygym": {k: fly[k].tolist() for k in engine}, "ommatidia_covered": fly["ommatidia_covered"],
            "scores": scores, "best": best, "best_score": scores[best]}
