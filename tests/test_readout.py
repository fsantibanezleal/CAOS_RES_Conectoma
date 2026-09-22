"""The readout head, the cache it trains on, and the row that reads it.

None of this needs the GPU, the engine or the corpus: the caches are written in the test's own directory
and the network's activity is replaced by something whose answer is known, so what is tested is the
machinery rather than one machine's data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.methods import head as head_module  # noqa: E402
from conectoma.methods import m05  # noqa: E402
from conectoma.stages import cache_activity, train_readout  # noqa: E402

TYPES = 8
FRAMES = 6
COLUMNS = head_module.COLUMNS


def write_cache(root: Path, arm: str, keys: list[str], rng: np.random.Generator, depth_from_activity=True):
    """A cache whose depth is a function of the activity: a head that learns is then visible as one."""
    stamp = {"cache_version": 1, "arm": arm, "seed": 0, "regime": "R0", "transfer": True,
             "spec_sha256": "x", "code_sha256": "y", "dt_s": 0.02, "interval_s": 0.1,
             "types": [f"T{i}" for i in range(TYPES)], "description": "a test cache"}
    for key in keys:
        activity = rng.normal(size=(FRAMES, TYPES, COLUMNS)).astype(np.float16)
        signal = np.asarray(activity, dtype=np.float32)[:, 0]
        depth = np.exp(1.5 + 0.5 * signal) if depth_from_activity else np.full((FRAMES, COLUMNS), 4.0)
        boundary = (signal > 0).astype(np.uint8)
        path = cache_activity.cache_path(root, arm, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, stamp=json.dumps(stamp), activity=activity,
                            depth=depth.astype(np.float16), boundary=boundary,
                            frames=np.arange(FRAMES, dtype=np.int32))


def test_the_head_maps_columns_to_columns_and_keeps_its_shape():
    model = head_module.Readout(types=TYPES, window=2)
    out = model(torch.zeros((3, 2, TYPES, COLUMNS)))
    assert out.shape == (3, 3, COLUMNS)
    assert model.parameter_count > 1000
    # every column has a place in the square map, and no two share one
    u, v, height, span = head_module.hex_map_indices()
    assert len(u) == COLUMNS
    assert len({(int(a), int(b)) for a, b in zip(u, v, strict=True)}) == COLUMNS
    assert height * span >= COLUMNS


def test_the_head_starts_at_the_corpus_median_rather_than_at_one_metre():
    model = head_module.Readout(types=TYPES, window=1, log_depth_offset=2.0)
    with torch.no_grad():
        out = model(torch.zeros((1, 1, TYPES, COLUMNS)))
    assert float(out[0, 0].mean()) == pytest.approx(2.0, abs=0.5)


def test_standardisation_uses_the_statistics_it_was_given():
    mean = [5.0] * TYPES
    std = [2.0] * TYPES
    model = head_module.Readout(types=TYPES, window=1, mean=mean, std=std)
    assert float(model.mean.mean()) == pytest.approx(5.0)
    assert float(model.std.mean()) == pytest.approx(2.0)
    # an input at the mean is rectified to zero, so the answer is the network's bias alone
    with torch.no_grad():
        at_mean = model(torch.full((1, 1, TYPES, COLUMNS), 5.0))
        above = model(torch.full((1, 1, TYPES, COLUMNS), 9.0))
    assert not torch.allclose(at_mean, above)


def test_the_depth_loss_prefers_being_right_and_lets_it_say_it_is_unsure():
    truth = torch.full((2, COLUMNS), 4.0)
    right = torch.zeros((2, 3, COLUMNS))
    right[:, 0] = float(np.log(4.0))
    wrong = torch.zeros((2, 3, COLUMNS))
    wrong[:, 0] = float(np.log(40.0))
    loss_right, stats = head_module.depth_loss(right, truth)
    loss_wrong, _ = head_module.depth_loss(wrong, truth)
    assert float(loss_right) < float(loss_wrong)
    assert stats["abs_rel"] == pytest.approx(0.0, abs=1e-6)

    # the same wrong answer, but admitting it: cheaper than claiming to be sure
    humble = wrong.clone()
    humble[:, 1] = 2.0
    assert float(head_module.depth_loss(humble, truth)[0]) < float(loss_wrong)


def test_a_masked_truth_is_not_scored():
    truth = torch.full((1, COLUMNS), float("nan"))
    loss, stats = head_module.depth_loss(torch.zeros((1, 3, COLUMNS)), truth)
    assert stats["columns"] == 0
    assert float(loss) == 0.0


def test_the_cache_statistics_are_the_splits_own(tmp_path):
    rng = np.random.default_rng(3)
    write_cache(tmp_path, "connectome", [f"clip_{i}" for i in range(4)], rng)
    clips = train_readout.CachedClips(tmp_path, "connectome", [f"clip_{i}" for i in range(4)])
    stats = clips.statistics()
    assert len(stats["mean"]) == TYPES
    assert len(stats["std"]) == TYPES
    assert stats["log_depth_offset"] == pytest.approx(1.5, abs=0.2)
    assert len(clips) == 4


def test_a_head_learns_a_cache_whose_depth_is_in_the_activity(tmp_path):
    rng = np.random.default_rng(11)
    write_cache(tmp_path, "connectome", [f"train_{i}" for i in range(6)], rng)
    write_cache(tmp_path, "connectome", [f"val_{i}" for i in range(2)], rng)
    splits = {"train": [f"train_{i}" for i in range(6)], "validation": [f"val_{i}" for i in range(2)]}
    record = train_readout.train(tmp_path, arm="connectome", seed=0, window=1, steps=120, batch=4,
                                 splits=splits, device="cpu", evaluate_every=40,
                                 out_dir=tmp_path / "readout")
    scores = [row["validation"]["silog"] for row in record["history"]]
    assert scores[-1] < scores[0]
    assert record["best"]["validation"]["columns"] > 0
    assert record["parameters"] == record["best"].get("parameters", record["parameters"])
    assert (tmp_path / "readout" / "connectome-seed0-w1.pt").exists()
    assert not (train_readout.DERIVED / "connectome-seed0-w1.pt").exists()


def test_a_trained_head_reloads_with_the_statistics_it_was_trained_with(tmp_path):
    rng = np.random.default_rng(5)
    write_cache(tmp_path, "connectome", [f"t_{i}" for i in range(4)], rng)
    write_cache(tmp_path, "connectome", [f"v_{i}" for i in range(2)], rng)
    splits = {"train": [f"t_{i}" for i in range(4)], "validation": [f"v_{i}" for i in range(2)]}
    record = train_readout.train(tmp_path, arm="connectome", seed=1, window=1, steps=40, batch=2,
                                 splits=splits, device="cpu", evaluate_every=20,
                                 out_dir=tmp_path / "readout")
    model, loaded = train_readout.load(tmp_path / "readout" / "connectome-seed1-w1.pt", device="cpu")
    assert loaded["statistics"] == record["statistics"]
    assert float(model.log_depth_offset) == pytest.approx(record["statistics"]["log_depth_offset"])


def test_m05_reads_a_cached_clip_and_refuses_where_it_is_unsure(tmp_path):
    rng = np.random.default_rng(7)
    write_cache(tmp_path, "connectome", ["case_C01_L0_00"], rng)
    model = head_module.Readout(types=TYPES, window=1, log_depth_offset=1.5)
    with torch.no_grad():                       # a head that is sure of half the columns and not the rest
        model.stack[-1].bias.fill_(0.0)
    record = {"window": 1}
    activity = m05.cached_activity(tmp_path, "connectome", "case_C01_L0_00")
    out = m05.run_on_activity(model, activity, record, tolerance=1e-6)
    assert out["distance_m"].shape == (FRAMES - 1, COLUMNS)
    assert out["unknown"].all()                 # nothing is inside a tolerance of one part in a million
    generous = m05.run_on_activity(model, activity, record, tolerance=10.0)
    assert not generous["unknown"].all()
    assert not generous["moving"].any()


def test_an_arm_is_the_connectome_or_a_named_null():
    spec, description = cache_activity.arm_spec("connectome")
    assert "nodes" in spec and "measured" in description
    with pytest.raises(KeyError):
        cache_activity.arm_spec("not-an-arm")
