"""M04: the published ensemble's own flow decoder, read through the shared inversion.

The checkpoints are not in the repository, so these tests skip where they are absent and say so. What
they check when they run is the wiring: the decoder emits a flow per column in the engine's units, the
inversion turns it into a depth, and a clip with no translation is refused like every other method.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import m04, readout  # noqa: E402
from conectoma.vision import cases, render, synthetic  # noqa: E402

INTERVAL_S = cases.TARTANAIR_INTERVAL_S
SPACING_DEG = cases.TARTANAIR_SPACING_DEG
PLANES_MOTION = {"variant": {"transform": "planes", "levels": [1]}}


def ensemble_available() -> bool:
    if not os.environ.get("CONECTOMA_MODELS_ROOT"):
        return False
    try:
        from conectoma.network.engine import published_model_dir

        published_model_dir("000")
        return True
    except (FileNotFoundError, ImportError):
        return False


needs_ensemble = pytest.mark.skipif(not ensemble_available(), reason="published ensemble not downloaded")


def planes_clip(depths, frames=6):
    K = synthetic.intrinsics(640, 640, 90.0)
    scene = synthetic.textured_planes(K, 640, 640, depths, cases.PLANES_SPEED_M_S, frames, INTERVAL_S,
                                      0.35, seed=5)
    clip = render.to_lattice(scene["lum"], scene["depth"], flow_px=scene["flow_px"],
                             flow_ok=scene["flow_ok"])
    clip["interval_s"] = INTERVAL_S
    return clip


@needs_ensemble
def test_the_decoder_emits_a_flow_per_column_in_the_engines_units():
    clip = planes_clip([2.0, 4.0, 8.0])
    out = m04.decode_flow(clip["lum"], INTERVAL_S)
    assert out["flow_engine"].shape == (len(clip["lum"]) - 1, 2, readout.COLUMNS)
    assert out["repeats"] == round(INTERVAL_S / m04.DT_S)
    assert np.isfinite(out["flow_engine"]).all()
    # the same units the corpus stores: converting gives a displacement of the order of a few pixels
    pixels = readout.pixel_flow(out["flow_engine"])
    assert 0.05 < np.median(np.linalg.norm(pixels, axis=1)) < 50.0


@needs_ensemble
def test_it_produces_a_depth_through_the_shared_inversion():
    clip = planes_clip([2.0, 4.0, 8.0])
    out = m04.run(clip, SPACING_DEG, motion=cases.step_motion(PLANES_MOTION, 0))
    assert out["distance_m"].shape[1] == readout.COLUMNS
    claimed = ~out["unknown"] & np.isfinite(out["distance_m"])
    assert claimed.any()
    assert (out["distance_m"][claimed] > 0).all()


@needs_ensemble
def test_a_clip_with_no_translation_is_refused():
    clip = planes_clip([4.0])
    out = m04.run(clip, SPACING_DEG, motion=(np.eye(3), np.zeros(3)))
    assert out["unknown"].all()


def test_a_clip_without_an_interval_is_refused_loudly():
    clip = planes_clip([4.0])
    clip.pop("interval_s")
    with pytest.raises(ValueError):
        m04.run(clip, SPACING_DEG, motion=cases.step_motion(PLANES_MOTION, 0))
