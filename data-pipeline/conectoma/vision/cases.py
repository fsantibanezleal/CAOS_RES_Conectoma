"""The case registry (config/cases.yaml) and the clips of every case at every level.

A case draws its clips once, from test data only, and renders each of them at its six levels; the physics of
a level is applied where it acts (`variants`), before or after the lattice, and nothing else changes. Every
rendered level is checked against contract 1 and records what it measured: the quantity it was set to and
what that means in the image (the speed in m/s, the visibility in metres, the blur in pixels, the column
spacing in degrees, the signal to noise ratio, the angular size of a looming disk).

The unit of work is one clip of one case (`render_clip`): it loads the clip once and returns its six levels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import yaml
from conectoma.vision import eye, panorama, render, variants
from conectoma.vision.contract import clip_statistics

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
REPO_ROOT = Path(__file__).resolve().parents[3]
CLIP_TABLE = REPO_ROOT / "data" / "derived" / "vision" / "tartanair-clips.csv"

TARTANAIR_INTERVAL_S = 0.1
TARTANAIR_K = np.array([[320.0, 0.0, 320.0], [0.0, 320.0, 320.0], [0.0, 0.0, 1.0]])
SYNTHETIC_FRAMES = 32
PLANES_SPEED_M_S = 1.0
PLANES_CONTRAST = 0.35
TEXTURELESS_DEPTHS_M = (2.0, 4.0, 8.0)
COLUMN_STEP_PX = eye.KERNEL      # neighbouring columns are one kernel apart along u, at 436 rows

# which contract a case's clips are held to
CONTRACT = {"tartanair": "tartanair", "hypersim": "hypersim", "spring": "spring", "sintel": "sintel",
            "flygym": "flygym", "panorama": "synthetic", "synthetic": "synthetic"}


def load_cases() -> tuple[dict, str]:
    raw = (CONFIG_DIR / "cases.yaml").read_bytes()
    return yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()


def contract_source(case: dict) -> str:
    if case["variant"]["transform"] == "static":
        return "synthetic"
    return CONTRACT[case["source"]]


def clip_seed(seed: int, case_id: str, index: int) -> int:
    return seed + 1000 * int(case_id[1:]) + index


# ------------------------------------------------------------------------------------------ selection


def spread(keys: list[str], count: int, seed: int, group) -> list[str]:
    """`count` keys drawn with `seed`, spread evenly over the groups `group(key)` names (round robin)."""
    rng = np.random.default_rng(seed)
    groups: dict[str, list[str]] = {}
    for key in sorted(keys):
        groups.setdefault(group(key), []).append(key)
    order = sorted(groups)
    rng.shuffle(order)
    for name in order:
        rng.shuffle(groups[name])
    chosen = []
    while len(chosen) < count and any(groups.values()):
        for name in order:
            if groups[name] and len(chosen) < count:
                chosen.append(groups[name].pop(0))
    return chosen


def tartanair_test_clips(family: str, table: Path = CLIP_TABLE) -> list[str]:
    """The keys of the family's rendered TartanAir clips; the family must be in the test split."""
    with open(table, encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["family"] == family]
    if any(r["split"] != "test" for r in rows):
        raise ValueError(f"family {family} is not in the test split; a case may draw only test data")
    return [r["key"] for r in rows]


def hypersim_scenes(root: Path, require: dict) -> list[str]:
    """The rendered Hypersim scenes whose lattice statistics meet `require` (share name: minimum)."""
    manifest = json.loads((root / "vision/hypersim/rendered/manifest.json").read_text(encoding="utf-8"))
    scenes = []
    for row in manifest["clips"]:
        stats = row["statistics"]
        if all(stats.get(name, 0.0) >= minimum for name, minimum in require.items()):
            scenes.append(Path(row["clip"]).parts[0])
    return sorted(scenes)


def select(case_id: str, case: dict, registry: dict, root: Path) -> list[str]:
    """The source items a case renders: clip keys, scene names, sequences, or seeds as strings."""
    count, seed = registry["clips"], registry["seed"] + int(case_id[1:])
    source = case["source"]
    if source in ("tartanair", "panorama"):
        return spread(tartanair_test_clips(case["family"]), count, seed, lambda k: k.split("/")[0])
    if source == "hypersim":
        return spread(hypersim_scenes(root, case.get("require", {})), count, seed,
                      lambda k: k.split("_")[1])                            # ai_VVV_NNN: by volume
    if source == "spring":
        archives = (root / "vision/spring/data").glob("*/clip_*.zip")
        clips = sorted(f"{p.parent.name}/{p.stem}" for p in archives)
        return spread(clips, count, seed, lambda k: k.split("/")[0])
    if source == "sintel":
        from conectoma.vision.sintel import HELD_OUT

        return list(HELD_OUT)[:count]
    return [str(clip_seed(registry["seed"], case_id, i)) for i in range(count)]          # flygym, synthetic


# ------------------------------------------------------------------------------------------ measurements


def rms_contrast(lum: np.ndarray) -> float:
    """Median over frames of the RMS contrast (standard deviation over mean) across the columns."""
    mean = lum.mean(axis=-1)
    return float(np.median(lum.std(axis=-1) / np.maximum(mean, 1e-9)))


def column_spacing_deg(focal_436_px: float) -> float:
    """The angle between neighbouring columns at the centre, for a focal length in pixels of 436 rows."""
    return math.degrees(2 * math.atan(COLUMN_STEP_PX / 2 / focal_436_px))


TARTANAIR_SPACING_DEG = column_spacing_deg(TARTANAIR_K[1, 1] * eye.ROWS / 640)


def _step_m(poses: np.ndarray) -> float:
    steps = np.linalg.norm(np.diff(poses[:, :3], axis=0), axis=1)
    return float(np.median(steps)) if len(steps) else 0.0


def _flow_speed(clip: dict) -> float:
    """Median flow magnitude over valid columns, in the engine's unit: per frame, the sum over a column's box
    of each pixel's motion in image heights (the engine sums flow over the box, as it renders Sintel)."""
    magnitude = np.hypot(clip["flow"][:, 0], clip["flow"][:, 1])
    valid = clip["flow_valid"] > 0.5
    return float(np.median(magnitude[valid])) if valid.any() else 0.0


# ------------------------------------------------------------------------------ one clip, six levels


def _level(clip: dict, interval: float | None, **measured) -> dict:
    return {"clip": clip, "interval_s": interval,
            "measured": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in measured.items()}}


def _tartanair_levels(case: dict, key: str, root: Path, seed: int) -> list[dict]:
    environment, difficulty, trajectory, start = key.split("/")
    path = root / "vision/tartanair/data" / environment / difficulty / trajectory / f"clip_{start}.zip"
    source = render.load_tartanair_clip(path)
    transform, levels = case["variant"]["transform"], case["variant"]["levels"]
    interval = TARTANAIR_INTERVAL_S
    out = []
    if transform == "speed":
        base = render.lattice_clip(source)
        step = _step_m(source["poses"])
        for factor in levels:
            shown = variants.speed_interval(interval, factor)
            out.append(_level(base, shown, speed_m_s=step / shown, frame_rate_hz=1 / shown))
    elif transform == "illumination":
        for gain in levels:
            clip = render.lattice_clip({**source, "lum": variants.illumination(source["lum"], gain)})
            out.append(_level(clip, interval, lum_mean=float(clip["lum"].mean())))
    elif transform == "photons":
        base = render.lattice_clip(source)
        for i, count in enumerate(levels):
            clip = {**base, "lum": variants.photons(base["lum"], count, seed * 10 + i)}
            snr = math.sqrt(count * float(base["lum"].mean())) if count else None
            out.append(_level(clip, interval, snr_at_mean=snr,
                              photons_per_column_per_s=count / interval if count else None))
    elif transform == "blur":
        for exposure_ms in levels:
            exposure = exposure_ms * 1e-3
            lum = variants.blur(source["lum"], source["flow_px"], exposure, interval)
            clip = render.lattice_clip({**source, "lum": lum})
            out.append(_level(clip, interval, blur_length_px=variants.blur_length_px(source["flow_px"],
                                                                                     exposure, interval)))
    elif transform == "fog":
        for attenuation in levels:
            lum = variants.fog(source["lum"], source["depth"], attenuation)
            clip = render.lattice_clip({**source, "lum": lum})
            out.append(_level(clip, interval, visibility_m=variants.visibility_m(attenuation),
                              rms_contrast=rms_contrast(clip["lum"])))
    elif transform == "static":
        # one frame held still: the first of the clip, at every step
        still = {"lum": np.repeat(source["lum"][:1], SYNTHETIC_FRAMES, axis=0),
                 "depth": np.repeat(source["depth"][:1], SYNTHETIC_FRAMES, axis=0),
                 "flow_px": np.zeros((SYNTHETIC_FRAMES - 1, 2) + source["lum"].shape[1:], np.float32),
                 "flow_ok": np.ones((SYNTHETIC_FRAMES - 1,) + source["lum"].shape[1:], bool),
                 "frames": np.arange(SYNTHETIC_FRAMES, dtype=np.int32)}
        base = render.lattice_clip(still)
        for i, count in enumerate(levels):
            clip = {**base, "lum": variants.photons(base["lum"], count, seed * 10 + i)}
            snr = math.sqrt(count * float(base["lum"].mean())) if count else None
            out.append(_level(clip, interval, snr_at_mean=snr))
    else:
        raise ValueError(f"unknown TartanAir transform {transform}")
    return out


def _uniform_frames(clip: dict) -> np.ndarray:
    """Frames whose 721 columns all carry the same luminance: nothing to see, whatever the value."""
    lum = clip["lum"]
    return lum.max(axis=-1) == lum.min(axis=-1)


def _keep_frames(clip: dict, keep: np.ndarray) -> dict:
    """The clip with only the frames `keep` marks (single images: the frame numbers are ids)."""
    out = dict(clip)
    for key, value in clip.items():
        if key != "frames" and getattr(value, "ndim", 0) and len(value) == len(keep):
            out[key] = value[keep]
    out["frames"] = clip["frames"][keep]
    return out


def _hypersim_levels(case: dict, scene: str, root: Path) -> list[dict]:
    from conectoma.vision import hypersim

    camera = hypersim.cameras()[scene]
    source = render.load_hypersim_clip(root / "vision/hypersim/data" / scene / "cam_00.zip", camera)
    rendered = []
    for level in case["variant"]["levels"]:
        fraction = 1.0 if level == "full" else hypersim.crop_for_vertical_fov(camera, float(level))
        clip = render.lattice_clip(render.crop_centre(source, fraction))
        fov = hypersim.vertical_fov_deg(camera, fraction)
        focal = (eye.ROWS / 2) / math.tan(math.radians(fov) / 2)
        rendered.append((clip, fov, fraction, column_spacing_deg(focal)))
    # A narrow crop can land on a surface with no structure at all (a lit wall, a blown-out window): the
    # image is uniform and shows nothing, and two uniform images are identical wherever they come from.
    # These are single images, not a video, so such an image is dropped from every level of the scene
    # rather than the scene being rejected, and every level keeps the same images.
    uniform = np.zeros(len(rendered[0][0]["frames"]), dtype=bool)
    for clip, *_ in rendered:
        uniform |= _uniform_frames(clip)
    if uniform.all():
        raise ValueError(f"{scene}: every image is uniform at some level")
    keep = ~uniform
    return [_level(_keep_frames(clip, keep), None, vertical_fov_deg=fov, crop_fraction=fraction,
                   column_spacing_deg=spacing, images_dropped_uniform=int(uniform.sum()))
            for clip, fov, fraction, spacing in rendered]


def _spring_levels(case: dict, key: str, root: Path) -> list[dict]:
    scene, name = key.split("/")
    source = render.load_spring_clip(root / "vision/spring/data" / scene / f"{name}.zip")
    fy = float(np.median(source["intrinsics"][:, 1]))
    height = source["lum"].shape[-2]
    out = []
    for rows in case["variant"]["levels"]:
        fraction = eye.ROWS / rows
        clip = render.lattice_clip(render.crop_centre(source, fraction))
        # a crop of `fraction` of `height` rows, resized to 436 rows: the focal length in those pixels
        focal = fy * eye.ROWS / (height * fraction)
        out.append(_level(clip, None, crop_fraction=fraction, column_spacing_deg=column_spacing_deg(focal),
                          focal_px_at_436_rows=focal))
    return out


def _sintel_levels(case: dict, sequence: str, models_root: Path) -> list[dict]:
    from conectoma.vision import sintel

    source = sintel.load_sintel_clip(sintel.sintel_dir(models_root), sequence)
    # Sintel's frames are 436 rows already: its focal length is the lattice's
    fy = float(np.median(source["intrinsics"][:, 1]))
    spacing = column_spacing_deg(fy * eye.ROWS / source["lum"].shape[-2])
    out = []
    for factor in case["variant"]["levels"]:
        clip = render.lattice_clip({**source, "lum": variants.contrast(source["lum"], factor)})
        out.append(_level(clip, sintel.FRAME_INTERVAL_S, rms_contrast=rms_contrast(clip["lum"]),
                          column_spacing_deg=spacing))
    return out


def _panorama_levels(case: dict, key: str, root: Path) -> list[dict]:
    environment, difficulty, trajectory, start = key.split("/")
    path = panorama.clip_path(root / "vision/panorama", environment, difficulty, trajectory, int(start))
    lum, distance = panorama.load(path)
    out = []
    for rate in case["variant"]["levels"]:
        source = panorama.turning_camera(lum, distance, TARTANAIR_K, 640, 640, float(rate), SYNTHETIC_FRAMES,
                                         TARTANAIR_INTERVAL_S)
        clip = render.lattice_clip(source)
        out.append(_level(clip, TARTANAIR_INTERVAL_S, rotation_deg_per_frame=rate * TARTANAIR_INTERVAL_S,
                          engine_flow_per_frame=_flow_speed(clip)))
    return out


def _synthetic_levels(case: dict, seed: int) -> list[dict]:
    from conectoma.vision import synthetic

    out = []
    for level in case["variant"]["levels"]:
        if case["variant"]["transform"] == "planes":
            depths, contrast = [float(level), 2.0 * level, 4.0 * level], PLANES_CONTRAST
        else:
            depths, contrast = list(TEXTURELESS_DEPTHS_M), float(level)
        source = synthetic.textured_planes(TARTANAIR_K, 640, 640, depths, PLANES_SPEED_M_S, SYNTHETIC_FRAMES,
                                           TARTANAIR_INTERVAL_S, contrast, seed)
        source["frames"] = np.arange(SYNTHETIC_FRAMES, dtype=np.int32)
        clip = render.lattice_clip(source)
        out.append(_level(clip, TARTANAIR_INTERVAL_S, plane_depths_m=depths, texture_contrast=contrast,
                          engine_flow_per_frame=_flow_speed(clip), rms_contrast=rms_contrast(clip["lum"])))
    return out


def _flygym_levels(case_id: str, case: dict, seed: int) -> list[dict]:
    from conectoma.vision import flygym_scenes

    clips = flygym_scenes.SCENES[case_id]([float(v) for v in case["variant"]["levels"]], seed)
    out = []
    for clip in clips:
        scene = clip.pop("scene")
        out.append(_level(clip, flygym_scenes.FRAME_INTERVAL_S, **scene))
    return out


def render_clip(case_id: str, case: dict, item: str, root: Path, models_root: Path | None,
                seed: int) -> list[dict]:
    """One selected clip of one case at every level: [{clip, interval_s, measured}] in level order."""
    levels = _render_levels(case_id, case, item, root, models_root, seed)
    if case["source"] in ("tartanair", "panorama", "synthetic"):
        # TartanAir's front camera (and the synthetic cases, which share it): 640 rows, focal 320 px
        for level in levels:
            level["measured"].setdefault("column_spacing_deg", round(TARTANAIR_SPACING_DEG, 6))
    return levels


def _render_levels(case_id: str, case: dict, item: str, root: Path, models_root: Path | None,
                   seed: int) -> list[dict]:
    source = case["source"]
    if source == "tartanair":
        return _tartanair_levels(case, item, root, seed)
    if source == "hypersim":
        return _hypersim_levels(case, item, root)
    if source == "spring":
        return _spring_levels(case, item, root)
    if source == "sintel":
        if models_root is None:
            raise ValueError("Sintel lives under the models root: set CONECTOMA_MODELS_ROOT")
        return _sintel_levels(case, item, models_root)
    if source == "panorama":
        return _panorama_levels(case, item, root)
    if source == "synthetic":
        return _synthetic_levels(case, seed)
    if source == "flygym":
        return _flygym_levels(case_id, case, seed)
    raise ValueError(f"unknown source {source}")


def statistics(clip: dict) -> dict:
    """What a manifest row records about a rendered level: the contract statistics, plus figure and flow."""
    stats = clip_statistics(clip)
    if "flow" in clip:
        stats["engine_flow_per_frame"] = _flow_speed(clip) if "flow_valid" in clip else None
    return stats


# ------------------------------------------------------------------------- the motion a case declares


def step_motion(case: dict, level: int) -> tuple[np.ndarray, np.ndarray] | None:
    """The camera motion between two frames of this case's level, in pinhole camera coordinates.

    TartanAir clips carry the poses the release recorded, so nothing is declared for them. The synthetic
    and panorama cases have no recorded poses because their motion is not measured: it IS the case. This
    function states it, in the same frame `decode.relative_motion` returns (x right, y down, z forward, the
    rotation and translation taking a point from this frame's camera to the next one's), so a method reads
    the two the same way. Returns None for a case whose motion is not declared here.

    A test checks each of these against the flow the rendering committed, so a sign error cannot survive.
    """
    from conectoma.vision import synthetic

    transform = case["variant"].get("transform")
    if transform in ("planes", "texture"):
        # the camera slides along its own x axis at a fixed speed: points move the other way
        return np.eye(3), np.array([-PLANES_SPEED_M_S * TARTANAIR_INTERVAL_S, 0.0, 0.0])
    if transform == "rotation":
        rate = float(case["variant"]["levels"][level])
        return synthetic.yaw(math.radians(rate) * TARTANAIR_INTERVAL_S), np.zeros(3)
    if transform == "static":
        return np.eye(3), np.zeros(3)
    return None
