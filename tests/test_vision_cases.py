"""The case lane: the physical variants, the exact synthetic and panorama cases, the per-source readers, the
FlyGym eye's pooling, and the registry itself.

Every quantity a case varies must do what its unit says (a fog attenuation gives the stated visibility, an
exposure blurs by the motion it spans, a crop gives the stated field of view), and every synthetic target
must be exact (flow that carries one frame onto the next, depth that is the planes' depth).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.vision import cases, contract, panorama, render, synthetic, variants  # noqa: E402
from conectoma.vision.hypersim import crop_for_vertical_fov, planar_factor, vertical_fov_deg  # noqa: E402

K = np.array([[320.0, 0.0, 320.0], [0.0, 320.0, 320.0], [0.0, 0.0, 1.0]])


# ------------------------------------------------------------------------------------------ variants


def test_identity_levels_leave_the_image_alone():
    lum = np.random.default_rng(0).random((3, 20, 30)).astype(np.float32)
    flow = np.ones((2, 2, 20, 30), np.float32)
    assert np.array_equal(variants.photons(lum, None, 1), lum)
    assert np.array_equal(variants.fog(lum, np.full_like(lum, 5.0), 0.0), lum)
    assert np.array_equal(variants.illumination(lum, 1.0), lum)
    assert np.allclose(variants.contrast(lum, 1.0), lum, atol=1e-6)
    assert np.array_equal(variants.blur(lum, flow, 0.0, 0.1), lum)


def test_photon_noise_has_the_stated_count():
    lum = np.full((200, 721), 0.5, np.float32)
    noisy = variants.photons(lum, 100, seed=3)
    # Poisson at 50 expected photons: mean 0.5, standard deviation sqrt(50) / 100
    assert abs(noisy.mean() - 0.5) < 0.002
    assert abs(noisy.std() - math.sqrt(50) / 100) < 0.002


def test_fog_reaches_its_visibility_and_the_sky_becomes_airlight():
    b = 0.05
    visibility = variants.visibility_m(b)
    lum = np.zeros((1, 1, 3), np.float32)
    depth = np.array([[[0.0 + 1e-6, visibility, np.nan]]], np.float32)
    fogged = variants.fog(lum, depth, b)
    # at the visibility the object keeps 2 percent of its own light: a black object is 98 percent airlight
    assert fogged[0, 0, 1] == pytest.approx(0.98 * variants.AIRLIGHT, rel=1e-4)
    assert fogged[0, 0, 2] == pytest.approx(variants.AIRLIGHT)
    assert fogged[0, 0, 0] == pytest.approx(0.0, abs=1e-4)


def test_contrast_scales_about_the_mean():
    lum = np.random.default_rng(1).random((2, 10, 10)).astype(np.float32) * 0.5 + 0.25
    half = variants.contrast(lum, 0.5)
    assert np.allclose(half.mean(axis=(-2, -1)), lum.mean(axis=(-2, -1)), atol=1e-6)
    assert np.allclose(half.std(axis=(-2, -1)), 0.5 * lum.std(axis=(-2, -1)), atol=1e-6)


def test_blur_smears_each_pixel_along_its_own_motion():
    lum = np.zeros((1, 9, 41), np.float32)
    lum[0, :, 20] = 1.0                                     # a one-pixel vertical line
    flow = np.zeros((1, 2, 9, 41), np.float32)
    flow[0, 0] = 8.0                                        # moving 8 px right per frame
    smeared = variants.blur(lum, flow, 0.05, 0.1)           # exposure half the interval: 4 px
    row = smeared[0, 4]
    assert row.sum() == pytest.approx(1.0, abs=0.02)        # light is conserved
    spread = np.nonzero(row > 1e-3)[0]
    assert 3 <= spread.max() - spread.min() <= 5            # spread over the 4 px the line moved
    assert variants.blur_length_px(flow, 0.05, 0.1) == pytest.approx(4.0)
    still = np.zeros_like(flow)
    assert np.allclose(variants.blur(lum, still, 0.05, 0.1), lum)   # no motion, no blur


def test_the_speed_variant_changes_only_time():
    assert variants.speed_interval(0.1, 4) == pytest.approx(0.025)
    assert variants.crop_for_fov(90.0, 90.0) == pytest.approx(1.0)
    assert variants.crop_for_fov(90.0, 53.13010235) == pytest.approx(0.5, abs=1e-6)


# ------------------------------------------------------------------------------------------ geometry


def test_a_crop_keeps_the_aspect_and_carries_everything_else():
    source = {"lum": np.zeros((2, 100, 200)), "depth": np.zeros((2, 100, 200)),
              "flow_px": np.zeros((1, 2, 100, 200)), "flow_ok": np.zeros((1, 100, 200), bool),
              "frames": np.arange(2), "poses": np.zeros((2, 7))}
    crop = render.crop_centre(source, 0.5)
    assert crop["lum"].shape == (2, 50, 100) and crop["flow_px"].shape == (1, 2, 50, 100)
    assert crop["frames"] is source["frames"] and crop["poses"] is source["poses"]


def test_spring_depth_is_focal_times_baseline_over_disparity():
    disparity = np.full((8, 8), 20.0, np.float32)
    disparity[0, 0] = 0.0
    depth = render.spring_depth(disparity, fx=1000.0)
    assert depth.shape == (4, 4)
    assert np.isnan(depth[0, 0])
    assert depth[1, 1] == pytest.approx(1000.0 * render.SPRING_BASELINE_M / 20.0)


def _pinhole_camera(width=1024, height=768, hfov=60.0) -> dict:
    # rays M [u, v, 1] with u, v in [-1, 1] and the camera looking down -z
    tx = math.tan(math.radians(hfov) / 2)
    ty = tx * height / width
    return {"width": width, "height": height, "M_cam_from_uv": np.diag([tx, ty, -1.0])}


def test_hypersim_planar_depth_and_field_of_view():
    camera = _pinhole_camera()
    factor = planar_factor(camera)
    assert factor.max() == pytest.approx(1.0, abs=1e-4)             # the centre ray is the axis
    tx, ty = math.tan(math.radians(30)), math.tan(math.radians(30)) * 0.75
    corner = 1 / math.sqrt(1 + tx**2 + ty**2)
    assert factor[0, 0] == pytest.approx(corner, abs=2e-3)
    full = vertical_fov_deg(camera)
    assert full == pytest.approx(2 * math.degrees(math.atan(ty)), abs=1e-6)
    fraction = crop_for_vertical_fov(camera, 20.0)
    assert vertical_fov_deg(camera, fraction) == pytest.approx(20.0, abs=1e-6)
    with pytest.raises(ValueError):
        crop_for_vertical_fov(camera, full + 1)


def test_the_lattice_rendering_takes_every_optional_target():
    rng = np.random.default_rng(2)
    frames, h, w = 3, 436, 600
    clip = render.lattice_clip({
        "lum": rng.random((frames, h, w)).astype(np.float32),
        "depth": np.full((frames, h, w), 3.0, np.float32),
        "flow_px": np.zeros((frames - 1, 2, h, w), np.float32),
        "flow_ok": np.ones((frames - 1, h, w), bool),
        "figure": np.ones((frames, h, w), bool),
        "labels": np.ones((frames, h, w), np.int32),
        "frames": np.arange(frames, dtype=np.int32),
    })
    assert clip["figure"].shape == (frames, 721) and np.all(clip["figure"] == 1)
    assert np.all(clip["boundary"] == 0) and np.allclose(clip["depth"], 3.0)
    assert contract.clip_problems(clip, "synthetic") == []


# ------------------------------------------------------------------------------------------ exact cases


def _constancy(lum: np.ndarray, flow: np.ndarray, ok: np.ndarray) -> float:
    """Mean |I_t(p) - I_{t+1}(p + flow)| over valid pixels, nearest neighbour."""
    import cv2

    h, w = lum.shape[1:]
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    errors = []
    for t in range(len(flow)):
        warped = cv2.remap(lum[t + 1], u + flow[t, 0], v + flow[t, 1], cv2.INTER_NEAREST)
        errors.append(np.abs(warped - lum[t])[ok[t]])
    return float(np.concatenate(errors).mean())


def test_textured_planes_are_exact():
    depths = [2.0, 4.0, 8.0]
    clip = synthetic.textured_planes(K, 160, 120, depths, 1.0, 4, 0.1, 0.35, seed=5)
    assert set(np.unique(clip["depth"]).tolist()) <= set(depths)
    # a static scene under sideways translation: -f dx / z, nothing vertical
    assert np.allclose(clip["flow_px"][:, 0], -K[0, 0] * 0.1 / clip["depth"][:-1])
    assert np.all(clip["flow_px"][:, 1] == 0)
    assert clip["figure"].any() and not clip["figure"].all()
    assert np.array_equal(clip["figure"], clip["depth"] < max(depths))
    assert _constancy(clip["lum"], clip["flow_px"], clip["flow_ok"]) < 0.02
    # every plane keeps a figure in view for the whole clip
    assert all(frame.any() for frame in clip["figure"])


def test_a_textureless_scene_has_no_contrast_but_the_same_depth():
    flat = synthetic.textured_planes(K, 160, 120, [2.0, 4.0, 8.0], 1.0, 3, 0.1, 0.0, seed=5)
    textured = synthetic.textured_planes(K, 160, 120, [2.0, 4.0, 8.0], 1.0, 3, 0.1, 0.35, seed=5)
    assert np.all(flat["lum"] == 0.5)
    assert np.array_equal(flat["depth"], textured["depth"])


def _equirect(width=512, height=256, distance=10.0):
    """A panorama whose luminance is its longitude and whose range is constant."""
    longitude = (np.arange(width) + 0.5) / width * 2 * np.pi - np.pi
    lum = np.repeat(((longitude + np.pi) / (2 * np.pi))[None], height, axis=0).astype(np.float32)
    return lum, np.full((height, width), distance, np.float32)


def test_the_panorama_camera_looks_where_the_front_camera_looks():
    small = np.array([[32.0, 0.0, 31.5], [0.0, 32.0, 31.5], [0.0, 0.0, 1.0]])     # 64 px, 90 degrees
    lum, distance = _equirect()
    seen, planar = panorama.view(lum, distance, small, 64, 64, np.eye(3))
    # the forward axis is at longitude +90 degrees: 3/4 of the way across the panorama
    assert seen[32, 32] == pytest.approx(0.75, abs=0.01)
    # constant range: planar depth is range times the cosine to the axis
    rays = panorama._rays(small, 64, 64)
    assert np.allclose(planar, 10.0 * rays[2] / np.linalg.norm(rays, axis=0), rtol=1e-5)


def test_a_turn_to_the_right_moves_the_image_left_by_the_rotation_homography():
    small = np.array([[64.0, 0.0, 63.5], [0.0, 64.0, 63.5], [0.0, 0.0, 1.0]])     # 128 px, 90 degrees
    lum, distance = _equirect(2048, 1024)
    clip = panorama.turning_camera(lum, distance, small, 128, 128, 60.0, 3, 0.1)
    # 6 degrees per frame to the right: the centre moves left by f tan(6 degrees)
    assert clip["flow_px"][0, 0, 64, 64] == pytest.approx(-64 * math.tan(math.radians(6.0)), rel=0.02)
    # depth is unobservable from the motion: the flow is the same whatever the depth
    near = panorama.turning_camera(lum, distance * 0.1, small, 128, 128, 60.0, 3, 0.1)
    assert np.array_equal(near["flow_px"], clip["flow_px"])
    assert not np.array_equal(near["depth"], clip["depth"])
    # and the flow carries each frame onto the next
    assert _constancy(clip["lum"], clip["flow_px"], clip["flow_ok"]) < 0.01


def test_rotation_flow_matches_the_homography_at_the_centre():
    flow, ok = panorama.rotation_flow(K, 640, 640, math.radians(6.0))
    assert flow[0, 320, 320] == pytest.approx(-320 * math.tan(math.radians(6.0)), rel=1e-3)
    assert abs(flow[1, 320, 320]) < 1e-3
    assert ok[320, 320] and not ok[320, 0]                  # the left edge leaves the view


# ------------------------------------------------------------------------------------------ readers


def test_sintel_luminance_is_pils():
    from conectoma.vision import sintel
    from PIL import Image

    rgb = np.random.default_rng(4).integers(0, 256, (37, 53, 3), dtype=np.uint8)
    reference = np.asarray(Image.fromarray(rgb).convert("L"), dtype=np.float32) / 255
    assert np.array_equal(sintel.luminance(rgb[..., ::-1]), reference)


def test_sintel_files_read_as_written(tmp_path):
    from conectoma.vision import sintel

    flow = np.random.default_rng(5).normal(size=(6, 7, 2)).astype("<f4")
    depth = np.random.default_rng(6).random((6, 7)).astype("<f4")
    header = np.array([sintel.TAG], "<f4").tobytes() + np.array([7, 6], "<i4").tobytes()
    (tmp_path / "a.flo").write_bytes(header + flow.tobytes())
    (tmp_path / "a.dpt").write_bytes(header + depth.tobytes())
    assert np.array_equal(sintel.read_flow(tmp_path / "a.flo"), np.moveaxis(flow, -1, 0))
    assert np.array_equal(sintel.read_depth(tmp_path / "a.dpt"), depth)
    (tmp_path / "b.flo").write_bytes(b"\0" * 12)
    with pytest.raises(ValueError):
        sintel.read_flow(tmp_path / "b.flo")


def test_the_held_out_sequences_are_the_engines_validation_set():
    """Read from the engine's source rather than imported: importing the engine sets its storage root."""
    import importlib.util

    from conectoma.vision import sintel

    spec = importlib.util.find_spec("flyvis")
    if spec is None:
        pytest.skip("the engine is not installed")
    text = (Path(spec.origin).parent / "datasets" / "sintel_utils.py").read_text(encoding="utf-8")
    start = text.index("_validation = [")
    block = text[start: text.index("]", start)].splitlines()[1:]
    assert sorted(sintel.HELD_OUT) == sorted(line.strip().strip('",') for line in block if line.strip())


# ------------------------------------------------------------------------------------------ the fly's eye


def test_the_eye_median_matches_numpy_per_ommatidium():
    from conectoma.vision.flygym_scenes import RightEye

    eye = RightEye.__new__(RightEye)
    rng = np.random.default_rng(7)
    eye.n = 5
    eye.group = rng.integers(0, 4, 60)                       # ommatidium 4 has no pixels
    values = rng.random(60)
    values[rng.random(60) < 0.2] = np.nan
    got = eye._median(values)
    for k in range(5):
        mine = values[eye.group == k]
        mine = mine[np.isfinite(mine)]
        assert (np.isnan(got[k]) if mine.size == 0 else got[k] == pytest.approx(np.median(mine)))


def test_the_committed_eye_map_is_a_bijection():
    import json

    mapping = json.loads((ROOT / "data/derived/vision/flygym-eye.json").read_text(encoding="utf-8"))
    assert sorted(mapping["engine_column_of_ommatidium"]) == list(range(721))
    assert mapping["orientation"]["best_score"] > 1.9


def test_a_small_target_is_seen_at_its_distance():
    pytest.importorskip("flygym")
    import mujoco as mj

    try:
        mj.Renderer(mj.MjModel.from_xml_string("<mujoco/>"), 8, 8).close()
    except Exception as error:  # no OpenGL context on this machine (a headless runner)
        pytest.skip(f"no MuJoCo renderer: {error}")
    from conectoma.vision import flygym_scenes

    (clip,) = flygym_scenes.small_target([16.0], seed=1)
    seen = clip["figure"] > 0.5
    assert seen.any(axis=1).all()                           # the target is seen in every frame
    # range, not planar depth: the near surface of a sphere 20 mm away
    radius = clip["scene"]["radius_mm"]
    depth_mm = np.nanmedian(clip["depth"][seen]) * 1e3
    assert flygym_scenes.TARGET_DISTANCE_MM - radius - 0.2 < depth_mm < flygym_scenes.TARGET_DISTANCE_MM
    assert contract.clip_problems({k: v for k, v in clip.items() if k != "scene"}, "flygym") == []


# ------------------------------------------------------------------------------------------ the registry


def test_the_registry_declares_sixteen_cases_of_six_physical_levels():
    registry, _ = cases.load_cases()
    assert sorted(registry["cases"]) == [f"C{i:02d}" for i in range(1, 17)]
    for case_id, case in registry["cases"].items():
        variant = case["variant"]
        assert len(variant["levels"]) == 6, case_id
        assert variant["unit"] and variant["quantity"], case_id
        assert case["grades"], case_id
        assert cases.contract_source(case) in contract.REQUIRED, case_id


def test_every_tartanair_case_draws_from_a_test_family():
    from conectoma.stages.vision_data import load_config

    registry, _ = cases.load_cases()
    config, _ = load_config()
    test_families = set(config["splits"]["case_families"])
    for case_id, case in registry["cases"].items():
        if case["source"] in ("tartanair", "panorama"):
            assert case["family"] in test_families, case_id


def test_selection_is_seeded_and_spreads_over_groups():
    keys = [f"{g}/{i}" for g in "abcd" for i in range(10)]
    first = cases.spread(keys, 8, 11, lambda k: k.split("/")[0])
    assert first == cases.spread(keys, 8, 11, lambda k: k.split("/")[0])
    assert sorted({k.split("/")[0] for k in first}) == list("abcd")
    assert all(sum(k.startswith(g) for k in first) == 2 for g in "abcd")
    assert len(cases.spread(keys[:3], 8, 11, lambda k: k)) == 3


def test_a_case_family_outside_the_test_split_is_refused(tmp_path):
    table = tmp_path / "clips.csv"
    table.write_text("key,family,split\nA/easy/P000/000000,Fam,train\n", encoding="utf-8")
    with pytest.raises(ValueError, match="test split"):
        cases.tartanair_test_clips("Fam", table)


def test_sintel_renders_exactly_as_the_engine_renders_it():
    """Our loader and lattice against the engine's own Sintel rendering, where both are on this machine."""
    import os

    import h5py
    from conectoma.vision import sintel

    models = Path(os.environ.get("CONECTOMA_MODELS_ROOT", ""))
    rendered = models / "flyvis" / "renderings" / "RenderedSintel_0000"
    root = sintel.sintel_dir(models)
    if not (rendered / "_meta.yaml").exists() or not (root / "training").exists():
        pytest.skip("the engine's Sintel rendering is not on this machine")
    names = sorted(p.name for p in (root / "training" / "final").iterdir())
    for name in ("ambush_2", "market_2"):
        clip = sintel.load_sintel_clip(root, name, length=12)
        ours = render.lattice_clip(clip)
        base = rendered / f"sequence_{names.index(name):02d}_{name}_split_01"
        engine = {}
        for key in ("lum", "flow", "depth"):
            with h5py.File(base / f"{key}.h5") as handle:
                engine[key] = handle["data"][()]
        # the engine starts at frame 2 and labels frame n with the flow from n - 1 to n
        index = clip["frames"] - 2
        assert np.abs(ours["lum"] - engine["lum"][index, 0]).max() < 1e-6
        assert np.abs(ours["depth"] - engine["depth"][index, 0]).max() <= 1e-6 * np.abs(ours["depth"]).max()
        assert np.abs(ours["flow"] - engine["flow"][index[1:]]).max() < 1e-4


# ------------------------------------------------------------------------------------------ committed summary


def _summary() -> dict:
    import json

    return json.loads((ROOT / "data/derived/vision/cases.json").read_text(encoding="utf-8"))


def test_the_case_pages_carry_the_committed_measurements():
    from conectoma.vision import case_docs

    assert case_docs.update(_summary(), ROOT / "docs", write=False) == []


def test_the_committed_summary_is_the_registry_rendered_in_full():
    summary = _summary()
    registry, digest = cases.load_cases()
    assert summary["cases_sha256"] == digest, "cases.yaml changed after the cases were built"
    assert sorted(summary["cases"]) == sorted(registry["cases"])
    for case_id, case in summary["cases"].items():
        assert case["failed"] == {}, case_id
        assert len(case["levels"]) == 6, case_id
        for level in case["levels"]:
            assert level["accepted"] == level["clips"] == len(case["items"]), (case_id, level["value"])
        if case["source"] in ("tartanair", "panorama"):
            assert case["family"] in registry["cases"][case_id]["family"]
