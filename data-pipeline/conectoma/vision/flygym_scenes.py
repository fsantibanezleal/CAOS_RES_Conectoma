"""The ethological cases, rendered through the fly's own eye: a gap to cross (C10), a looming object (C11)
and a small moving target (C12).

Each scene is a MuJoCo world around FlyGym's NeuroMechFly, seen by its right eye exactly as FlyGym sees it:
the same camera (157 degree vertical field, 512 x 450 pixels), the same fisheye remap and the same pixels
per ommatidium (`flygym_eye`). The scene's surfaces are drawn in their own geom group and the fly's body is
left out of the eye's render, so a column sees the world and not the fly's own legs. The light is MuJoCo's
headlight, a directional light along the eye's axis; the eye only translates within a clip, so every
surface keeps its shading from frame to frame. For every ommatidium and frame the scene gives what its
pixels saw:
  lum      luminance of the render (0.299 R + 0.587 G + 0.114 B), mean over its pixels; the fisheye's empty
           pixels count as black, as in FlyGym
  depth    distance along each pixel's ray to the surface it sees, in metres, median over its pixels; the
           sky (nothing hit) is NaN. A compound eye has no image plane, so its depth is range, not planar
  figure   share of its pixels that see the scene's figure (the far platform, the looming disk, the target)
reordered from FlyGym's ommatidium ids to the engine's column order by the measured map
(data/derived/vision/flygym-eye.json). World units are FlyGym's millimetres; the fly faces +x, its right is
-y, up is +z. Frames are 10 ms apart, 32 per clip.

A seed fixes a scene (its textures, the approach direction, the path); the six levels of a case are
rendered in that same scene, so they differ only in the quantity the case varies.

- C10 gap crossing: the fly walks at 20 mm/s toward a gap in the ground, its right eye 1 mm above the
  surface, starting 8.2 mm before the near edge and walking 6.2 mm along a heading up to 30 degrees to the
  left of the gap's normal (so the gap sits in the right eye's frontal field). Surfaces carry 1/f texture;
  the pit is 10 mm deep. Level: the gap's width in mm. Figure: the platform beyond the gap, the surface
  the fly would have to reach.
- C11 looming: a dark disk of radius l = 2 mm approaches the eye head-on at constant speed v, its face
  toward the eye; the clip ends when it subtends 90 degrees, so its angular size follows
  `theta(t) = 2 atan(l / (v (t_c - t)))`. Level: l / v in ms.
- C12 small target: a dark sphere at 20 mm from the eye moves front to back across the right eye's field at
  90 degrees per second. Level: its angular diameter in degrees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from conectoma.vision import flygym_eye
from conectoma.vision.synthetic import pink_texture

FRAME_INTERVAL_S = 0.01
FRAMES = 32
SCENE_GROUP = 3                  # geom group of the scene; the eye renders only this group
NEAR_MM, FAR_MM = 0.05, 2000.0   # clip planes of the eye's render
REPO_ROOT = Path(__file__).resolve().parents[3]
EYE_MAP = REPO_ROOT / "data" / "derived" / "vision" / "flygym-eye.json"


# ------------------------------------------------------------------------------------------ the eye


class RightEye:
    """FlyGym's right eye over a compiled scene: luminance, range and figure per engine column."""

    def __init__(self, model, camera: int):
        import mujoco as mj
        import yaml
        from flygym import assets_dir

        with open(assets_dir / "model/neuromechfly/vision.yaml", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        with np.load(assets_dir / "model/neuromechfly/compound_eye.npz") as data:
            id_map = data["ommatidia_id_map"]
        self.rows, self.cols = config["raw_img_height_px"], config["raw_img_width_px"]
        self.camera = camera
        model.vis.map.znear = NEAR_MM / model.stat.extent
        model.vis.map.zfar = FAR_MM / model.stat.extent
        self.renderer = mj.Renderer(model, height=self.rows, width=self.cols)
        self.option = mj.MjvOption()
        for group in range(len(self.option.geomgroup)):
            self.option.geomgroup[group] = int(group == SCENE_GROUP)
        source = flygym_eye.fisheye_source_index(self.rows, self.cols, config["fisheye_zoom"],
                                                 config["fisheye_distortion_coefficient"]).reshape(-1)
        ids = id_map.reshape(-1)
        self.n = int(id_map.max())
        # every pixel of every ommatidium: its ommatidium and the rectilinear pixel it copies (-1: none)
        inside = ids > 0
        group, pixel = ids[inside] - 1, source[inside]
        self.total = np.bincount(group, minlength=self.n)
        mapped = pixel >= 0
        self.group, self.pixel = group[mapped], pixel[mapped]
        self.mapped = np.bincount(self.group, minlength=self.n)
        # pinhole rays of the rectilinear render: range = planar depth * |ray| / ray_z
        fovy = np.radians(float(model.cam_fovy[camera]))
        focal = (self.rows / 2) / np.tan(fovy / 2)
        v, u = np.mgrid[0:self.rows, 0:self.cols].astype(np.float64)
        self.ray_length = np.sqrt(1 + ((u + 0.5 - self.cols / 2) / focal) ** 2
                                  + ((v + 0.5 - self.rows / 2) / focal) ** 2).reshape(-1)
        # each ommatidium's viewing direction (the mean of its pixels' rays), and the angle to its nearest
        # neighbour: the eye's own column spacing, to set against the planar sources'
        rays = np.stack([(u + 0.5 - self.cols / 2) / focal, (v + 0.5 - self.rows / 2) / focal,
                         np.ones_like(u)], axis=-1).reshape(-1, 3)
        rays /= np.linalg.norm(rays, axis=1, keepdims=True)
        directions = np.stack([np.bincount(self.group, weights=rays[self.pixel, i], minlength=self.n)
                               for i in range(3)], axis=1)
        directions /= np.linalg.norm(directions, axis=1, keepdims=True)
        from scipy.spatial import cKDTree

        chord, _ = cKDTree(directions).query(directions, k=2)
        self.spacing_deg = float(np.degrees(np.median(2 * np.arcsin(chord[:, 1] / 2))))
        mapping = json.loads(EYE_MAP.read_text(encoding="utf-8"))
        self.column = np.asarray(mapping["engine_column_of_ommatidium"], dtype=np.int64)
        if sorted(self.column.tolist()) != list(range(self.n)):
            raise ValueError("the FlyGym eye map is not a bijection onto the engine's columns")

    def _render(self, data, kind: str) -> np.ndarray:
        if kind == "depth":
            self.renderer.enable_depth_rendering()
        elif kind == "segmentation":
            self.renderer.enable_segmentation_rendering()
        self.renderer.update_scene(data, self.camera, scene_option=self.option)
        image = self.renderer.render()
        self.renderer.disable_depth_rendering()
        self.renderer.disable_segmentation_rendering()
        return image

    def _median(self, values: np.ndarray) -> np.ndarray:
        """Per ommatidium, the median of its finite values (NaN where it has none), as np.median takes it."""
        ok = np.isfinite(values)
        group, value = self.group[ok], values[ok]
        order = np.lexsort((value, group))
        group, value = group[order], value[order]
        counts = np.bincount(group, minlength=self.n)
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        out = np.full(self.n, np.nan)
        has = counts > 0
        low, high = starts[has] + (counts[has] - 1) // 2, starts[has] + counts[has] // 2
        out[has] = (value[low] + value[high]) / 2
        return out

    def look(self, data, figure_geoms: set[int]) -> dict:
        """What each column sees now, in the engine's column order."""
        import mujoco as mj

        rgb = self._render(data, "rgb").astype(np.float64)
        lum = ((0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]) / 255.0).reshape(-1)
        planar = self._render(data, "depth").astype(np.float64).reshape(-1)
        segments = self._render(data, "segmentation")
        geom = np.where(segments[..., 1] == int(mj.mjtObj.mjOBJ_GEOM), segments[..., 0], -1).reshape(-1)
        distance = np.where(geom >= 0, planar * self.ray_length, np.nan)
        figure = np.isin(geom, list(figure_geoms)).astype(np.float64)
        out = {
            "lum": np.bincount(self.group, weights=lum[self.pixel], minlength=self.n) / self.total,
            "depth": self._median(distance[self.pixel]) * 1e-3,                  # millimetres to metres
            "figure": np.bincount(self.group, weights=figure[self.pixel], minlength=self.n)
            / np.maximum(self.mapped, 1),
        }
        return {key: _to_columns(value, self.column) for key, value in out.items()}


def _to_columns(values: np.ndarray, column: np.ndarray) -> np.ndarray:
    out = np.empty(len(values), dtype=np.float32)
    out[column] = values
    return out


# ------------------------------------------------------------------------------------------ the world


def _texture(spec, name: str, seed: int, contrast: float = 0.35, mean: float = 0.5, size: int = 256) -> str:
    """A 1/f grey texture added to the spec, as the material `name`."""
    import mujoco as mj

    grey = np.clip(mean + contrast * 0.5 * pink_texture(size, seed), 0.0, 1.0)
    pixels = np.repeat((grey * 255).astype(np.uint8)[..., None], 3, axis=-1)
    texture = spec.add_texture(name=f"{name}_tex", type=mj.mjtTexture.mjTEXTURE_2D, width=size, height=size,
                               nchannel=3)
    texture.data = pixels.tobytes()
    material = spec.add_material(name=name, texrepeat=[1, 1], texuniform=True)
    material.textures[int(mj.mjtTextureRole.mjTEXROLE_RGB)] = f"{name}_tex"
    return name


def _ground(spec, name: str, material: str, x: tuple[float, float], top: float, depth: float,
            half_y: float = 60.0) -> None:
    """A textured box whose top face is at z = `top`, spanning x in `x`."""
    import mujoco as mj

    spec.worldbody.add_geom(name=name, type=mj.mjtGeom.mjGEOM_BOX, material=material, group=SCENE_GROUP,
                            size=[(x[1] - x[0]) / 2, half_y, depth / 2],
                            pos=[(x[0] + x[1]) / 2, 0.0, top - depth / 2], contype=0, conaffinity=0)


def _mocap_body(spec, name: str, geom_type, size: list[float], rgba: list[float]) -> None:
    """A body the scene moves by hand (a mocap body), with one geom."""
    body = spec.worldbody.add_body(name=name, mocap=True, pos=[0.0, 0.0, -1000.0])
    body.add_geom(name=f"{name}_geom", type=geom_type, size=size, rgba=rgba, group=SCENE_GROUP,
                  contype=0, conaffinity=0)


@dataclass
class Scene:
    sim: object
    eye: RightEye
    root_mocap: int
    eye_offset: np.ndarray        # the right eye camera relative to the fly's root, heading 0

    @property
    def model(self):
        return self.sim.mj_model

    @property
    def data(self):
        return self.sim.mj_data

    def geom(self, name: str) -> int:
        import mujoco as mj

        return mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_GEOM, name)

    def mocap(self, body: str) -> int:
        import mujoco as mj

        return int(self.model.body_mocapid[mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_BODY, body)])

    def forward(self) -> None:
        import mujoco as mj

        mj.mj_forward(self.model, self.data)

    def set_fly(self, eye_position: np.ndarray, heading_rad: float) -> None:
        """Put the fly so its right eye is at `eye_position`, heading `heading_rad` (about +z from +x)."""
        c, s = np.cos(heading_rad), np.sin(heading_rad)
        turn = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
        self.data.mocap_quat[self.root_mocap] = [np.cos(heading_rad / 2), 0.0, 0.0, np.sin(heading_rad / 2)]
        self.data.mocap_pos[self.root_mocap] = eye_position - turn @ self.eye_offset
        self.forward()

    def eye_position(self) -> np.ndarray:
        return self.data.cam_xpos[self.eye.camera].copy()


def build(add_scene, eye_height_mm: float = 1.0) -> Scene:
    """A tethered NeuroMechFly in the scene `add_scene(spec)` builds, its right eye `eye_height_mm` above
    z = 0."""
    import mujoco as mj
    from flygym.anatomy import AxisOrder, JointPreset, Skeleton
    from flygym.compose.fly import NeuroMechFly
    from flygym.compose.pose import KinematicPosePreset
    from flygym.compose.world import TetheredWorld
    from flygym.simulation import Simulation
    from flygym.utils.math import Rotation3D

    skeleton = Skeleton(axis_order=AxisOrder.YAW_PITCH_ROLL, joint_preset=JointPreset.LEGS_ONLY)
    pose = KinematicPosePreset.NEUTRAL.get_pose_by_axis_order(AxisOrder.YAW_PITCH_ROLL)
    fly = NeuroMechFly(name="scene_fly")
    fly.add_joints(skeleton, neutral_pose=pose)
    fly.add_vision()
    world = TetheredWorld(name="scene_world")
    add_scene(world.mjcf_root)
    world.add_fly(fly, spawn_position=[0, 0, 0], spawn_rotation=Rotation3D("quat", [1, 0, 0, 0]))
    sim = Simulation(world)
    sim.reset()
    mj.mj_forward(sim.mj_model, sim.mj_data)
    camera = int(sim._intern_eye_camera_ids_by_fly[fly.name][1])          # right eye
    root_body = mj.mj_name2id(sim.mj_model, mj.mjtObj.mjOBJ_BODY,
                              f"{fly.name}/{fly.bodyseg_to_mjcfbody[fly.root_segment].name}")
    root_mocap = int(sim.mj_model.body_mocapid[root_body])
    offset = sim.mj_data.cam_xpos[camera] - sim.mj_data.mocap_pos[root_mocap]
    scene = Scene(sim, RightEye(sim.mj_model, camera), root_mocap, offset.copy())
    scene.set_fly(np.array([0.0, 0.0, eye_height_mm]), 0.0)
    return scene


def _clip(frames: list[dict], scene: dict, eye: RightEye) -> dict:
    return {"lum": np.stack([f["lum"] for f in frames]), "depth": np.stack([f["depth"] for f in frames]),
            "figure": np.stack([f["figure"] for f in frames]),
            "frames": np.arange(len(frames), dtype=np.int32),
            "scene": {**scene, "column_spacing_deg": round(eye.spacing_deg, 4)}}


def _direction(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    """A unit vector from the eye: azimuth from straight ahead toward the right, elevation up."""
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    return np.array([np.cos(el) * np.cos(az), -np.cos(el) * np.sin(az), np.sin(el)])


def _facing(axis: np.ndarray) -> np.ndarray:
    """The quaternion turning +z onto `axis` (a disk's face toward the eye)."""
    z = np.array([0.0, 0.0, 1.0])
    half = z + axis / np.linalg.norm(axis)
    if np.linalg.norm(half) < 1e-9:
        return np.array([0.0, 1.0, 0.0, 0.0])
    half /= np.linalg.norm(half)
    return np.concatenate([[z @ half], np.cross(z, half)])


# ------------------------------------------------------------------------------------------ C10 gap crossing

GAP_SPEED_MM_S = 20.0
GAP_START_MM = 8.2
PIT_DEPTH_MM = 10.0
EYE_HEIGHT_MM = 1.0
PLATFORM_MM = 80.0


def gap_crossing(gaps_mm: list[float], seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    heading = np.radians(rng.uniform(0.0, 30.0))            # to the left: the gap in the right eye

    def add(spec):
        near, far, pit = (_texture(spec, n, seed * 10 + i) for i, n in enumerate(("near", "far", "pit")))
        _ground(spec, "near_platform", near, (-PLATFORM_MM, 0.0), 0.0, PIT_DEPTH_MM)
        _ground(spec, "far_platform", far, (0.0, PLATFORM_MM), 0.0, PIT_DEPTH_MM)
        _ground(spec, "pit_floor", pit, (-PLATFORM_MM, 2 * PLATFORM_MM), -PIT_DEPTH_MM, 1.0)

    scene = build(add, EYE_HEIGHT_MM)
    far = scene.geom("far_platform")
    figure = {far}
    start = np.array([-GAP_START_MM, 0.0, EYE_HEIGHT_MM])
    direction = np.array([np.cos(heading), np.sin(heading), 0.0])
    clips = []
    for gap in gaps_mm:
        scene.model.geom_pos[far][0] = gap + PLATFORM_MM / 2        # the far platform begins at x = gap
        frames, edge = [], []
        for t in range(FRAMES):
            position = start + direction * GAP_SPEED_MM_S * FRAME_INTERVAL_S * t
            scene.set_fly(position, heading)
            frames.append(scene.eye.look(scene.data, figure))
            edge.append(round(float(-position[0]), 4))
        clips.append(_clip(frames, {"gap_mm": gap, "heading_deg": round(float(np.degrees(heading)), 3),
                                    "speed_mm_s": GAP_SPEED_MM_S, "eye_height_mm": EYE_HEIGHT_MM,
                                    "eye_to_near_edge_mm": edge}, scene.eye))
    return clips


# ------------------------------------------------------------------------------------------ C11 looming

LOOM_RADIUS_MM = 2.0


def looming(l_over_v_ms: list[float], seed: int) -> list[dict]:
    import mujoco as mj

    rng = np.random.default_rng(seed)
    azimuth, elevation = rng.uniform(40.0, 110.0), rng.uniform(30.0, 60.0)

    def add(spec):
        _ground(spec, "ground", _texture(spec, "ground", seed), (-200.0, 200.0), 0.0, 1.0, half_y=200.0)
        _mocap_body(spec, "disk", mj.mjtGeom.mjGEOM_CYLINDER, [LOOM_RADIUS_MM, 0.05, 0.0],
                    [0.05, 0.05, 0.05, 1.0])

    scene = build(add)
    disk = scene.mocap("disk")
    figure = {scene.geom("disk_geom")}
    eye = scene.eye_position()
    u = _direction(azimuth, elevation)
    clips = []
    for ratio in l_over_v_ms:
        tau = ratio * 1e-3
        speed = LOOM_RADIUS_MM / tau                              # mm/s
        frames, sizes = [], []
        for t in range(FRAMES):
            distance = speed * (tau + (FRAMES - 1 - t) * FRAME_INTERVAL_S)   # the last frame subtends 90 deg
            scene.data.mocap_pos[disk] = eye + u * distance
            scene.data.mocap_quat[disk] = _facing(u)
            scene.forward()
            frames.append(scene.eye.look(scene.data, figure))
            sizes.append(round(float(np.degrees(2 * np.arctan(LOOM_RADIUS_MM / distance))), 4))
        clips.append(_clip(frames, {"l_over_v_ms": ratio, "radius_mm": LOOM_RADIUS_MM,
                                    "speed_mm_s": round(speed, 4), "azimuth_deg": round(azimuth, 3),
                                    "elevation_deg": round(elevation, 3), "angular_size_deg": sizes},
                                   scene.eye))
    return clips


# ------------------------------------------------------------------------------------------ C12 small target

TARGET_DISTANCE_MM = 20.0
TARGET_SPEED_DEG_S = 90.0


def small_target(sizes_deg: list[float], seed: int) -> list[dict]:
    import mujoco as mj

    rng = np.random.default_rng(seed)
    start, elevation = rng.uniform(30.0, 60.0), rng.uniform(0.0, 20.0)

    def add(spec):
        _ground(spec, "ground", _texture(spec, "ground", seed), (-200.0, 200.0), 0.0, 1.0, half_y=200.0)
        _mocap_body(spec, "target", mj.mjtGeom.mjGEOM_SPHERE, [1.0, 0.0, 0.0], [0.05, 0.05, 0.05, 1.0])

    scene = build(add)
    target, geom = scene.mocap("target"), scene.geom("target_geom")
    figure = {geom}
    eye = scene.eye_position()
    clips = []
    for size in sizes_deg:
        radius = TARGET_DISTANCE_MM * np.sin(np.radians(size) / 2)
        scene.model.geom_size[geom][0] = radius
        scene.model.geom_rbound[geom] = radius
        frames = []
        for t in range(FRAMES):
            azimuth = start + TARGET_SPEED_DEG_S * FRAME_INTERVAL_S * t
            scene.data.mocap_pos[target] = eye + _direction(azimuth, elevation) * TARGET_DISTANCE_MM
            scene.forward()
            frames.append(scene.eye.look(scene.data, figure))
        clips.append(_clip(frames, {"size_deg": size, "radius_mm": round(float(radius), 5),
                                    "distance_mm": TARGET_DISTANCE_MM, "speed_deg_s": TARGET_SPEED_DEG_S,
                                    "start_azimuth_deg": round(start, 3),
                                    "elevation_deg": round(elevation, 3)}, scene.eye))
    return clips


SCENES = {"C10": gap_crossing, "C11": looming, "C12": small_target}
