"""The biophysical regime's training stage and the row that reads it.

Like the reservoir's tests, none of this needs the GPU, the engine or the corpus. What is exercised is the
machinery that has to be right whatever the machine: the schedules, the statistics the head is frozen
with, the per-seed cache naming a trained arm needs, and M06's reading of those caches.

The one thing these tests cannot do is train a network, which takes a GPU and minutes; that is measured in
the run records the unit commits, not asserted here.
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
from conectoma.methods import m06  # noqa: E402
from conectoma.stages import cache_activity, evaluate, train_network  # noqa: E402

TYPES = 8
FRAMES = 6
COLUMNS = head_module.COLUMNS


def write_cache(root: Path, arm: str, keys: list[str], rng: np.random.Generator) -> None:
    """A cache whose depth is a function of the activity, so a head that reads it is visible as one."""
    stamp = {"cache_version": 1, "arm": arm, "seed": 0, "regime": "R1", "transfer": True,
             "trained": True, "spec_sha256": "x", "code_sha256": "y", "dt_s": 0.02, "interval_s": 0.1,
             "types": [f"T{i}" for i in range(TYPES)], "description": "a test cache"}
    for key in keys:
        activity = rng.normal(size=(FRAMES, TYPES, COLUMNS)).astype(np.float16)
        signal = np.asarray(activity, dtype=np.float32)[:, 0]
        depth = np.exp(1.5 + 0.5 * signal)
        path = cache_activity.cache_path(root, arm, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, stamp=json.dumps(stamp), activity=activity,
                            depth=depth.astype(np.float16),
                            frames=np.arange(FRAMES), boundary=(signal > 0).astype(np.uint8))


def write_checkpoint(out_dir: Path, arm: str, seed: int, window: int = 2, regime: str = "R1",
                     offset: float = 1.5) -> Path:
    """A checkpoint in this stage's format: a head, a network state it does not need, and the record."""
    model = head_module.Readout(types=TYPES, window=window, log_depth_offset=offset)
    record = {"checkpoint_version": train_network.CHECKPOINT_VERSION, "regime": regime, "arm": arm,
              "seed": seed, "window": window, "types": [f"T{i}" for i in range(TYPES)],
              "statistics": {"mean": [0.0] * TYPES, "std": [1.0] * TYPES, "log_depth_offset": offset},
              "spec_sha256": "x", "code_sha256": "y", "dt_s": 0.02, "interval_s": 0.1,
              "description": "a test network"}
    out_dir.mkdir(parents=True, exist_ok=True)
    path = train_network.checkpoint_path(regime, arm, seed, window, out_dir)
    torch.save({"network": {}, "head": model.state_dict(), "record": record}, path)
    return path


# ---------------------------------------------------------------- the schedules


def test_the_network_rate_decays_stepwise_from_its_start_to_a_tenth():
    rates = train_network.schedule(5e-3, 600)
    assert rates[0] == pytest.approx(5e-3)
    assert rates[599] == pytest.approx(5e-4)
    assert len(rates) >= 600
    assert np.all(np.diff(rates) <= 1e-12)                      # never goes back up
    assert len(np.unique(rates.round(12))) == train_network.DECAY_STAGES


def test_the_penalty_keeps_the_published_rate_whatever_the_network_is_trained_at():
    """The engine ties the two; at a hundred times the published network rate that penalty runs away."""
    assert train_network.PENALTY_LEARNING_RATE == pytest.approx(5e-5)
    fast = train_network.schedule(5e-3, 200)
    penalty = train_network.schedule(train_network.PENALTY_LEARNING_RATE, 200)
    assert penalty[0] == pytest.approx(5e-5)
    assert penalty.max() < fast.min()


def test_the_activity_baseline_is_measured_rather_than_imported():
    """5.0 is the published ensemble's level under its own stimuli, and is not this product's."""
    assert train_network.PENALIZER["activity_penalty"]["activity_baseline"] is None
    assert train_network.PENALIZER["activity_penalty"]["activity_penalty"] == pytest.approx(0.1)
    assert train_network.PENALIZER["activity_penalty"]["below_baseline_penalty_weight"] == 1.0
    assert train_network.PENALIZER["activity_penalty"]["above_baseline_penalty_weight"] == 0.1


# ---------------------------------------------------------------- what the head is frozen with


def test_the_start_statistics_are_the_streamed_ones(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    keys = [f"clip_{i}" for i in range(4)]
    write_cache(tmp_path, "connectome", keys, rng)
    monkeypatch.setattr(train_network, "split_clips",
                        lambda root, split, limit=None: [Path(f"{k}.npz") for k in keys])
    statistics = train_network.start_statistics(tmp_path, "connectome")

    stack = np.concatenate([
        np.asarray(np.load(cache_activity.cache_path(tmp_path, "connectome", k))["activity"],
                   dtype=np.float32) for k in keys])
    assert statistics["mean"] == pytest.approx(stack.mean(axis=(0, 2)).tolist(), abs=1e-4)
    assert statistics["std"] == pytest.approx(
        np.maximum(stack.std(axis=(0, 2)), 1e-3).tolist(), abs=1e-4)
    assert statistics["source"].startswith("the R0 activity cache")


def test_a_missing_r0_cache_is_named_rather_than_silently_defaulted(tmp_path, monkeypatch):
    monkeypatch.setattr(train_network, "split_clips", lambda root, split, limit=None: [Path("none.npz")])
    with pytest.raises(FileNotFoundError, match="no R0 activity cache"):
        train_network.start_statistics(tmp_path, "connectome")


# ---------------------------------------------------------------- a trained arm's cache is its seed's


def test_a_trained_networks_cache_belongs_to_the_seed_not_the_arm():
    first = train_network.cache_arm("R1", "connectome", 0)
    second = train_network.cache_arm("R1", "connectome", 1)
    assert first != second
    assert first != "connectome"          # never the reservoir's cache, which every seed shares
    assert train_network.cache_arm("R2", "N1", 3) == "R2-N1-seed3"


def test_a_checkpoint_is_named_by_its_regime_arm_seed_and_window(tmp_path):
    path = train_network.checkpoint_path("R1", "N2", 4, 2, tmp_path)
    assert path.name == "R1-N2-seed4-w2.pt"


# ---------------------------------------------------------------- M06 reads those caches


def test_m06_loads_a_head_without_building_its_network(tmp_path):
    path = write_checkpoint(tmp_path, "connectome", 0)
    model, record = m06.load_head(path)
    assert record["arm"] == "connectome" and record["regime"] == "R1"
    assert float(model.log_depth_offset) == pytest.approx(1.5)


def test_m06_reads_each_seeds_own_cache_and_refuses_where_it_is_unsure(tmp_path):
    rng = np.random.default_rng(5)
    keys = ["case_C01_L0_00"]
    for seed in (0, 1):
        write_cache(tmp_path, train_network.cache_arm("R1", "connectome", seed), keys, rng)
        write_checkpoint(tmp_path / "ckpt", "connectome", seed)
    clip = {"lum": np.zeros((FRAMES, COLUMNS), dtype=np.float32)}
    result = m06.run(clip, 4.6, root=tmp_path, arm="connectome", key=keys[0],
                     checkpoints=sorted((tmp_path / "ckpt").glob("R1-*.pt")), tolerance=0.5)
    assert result["seeds"] == 2
    assert result["distance_m"].shape == (FRAMES - 1, COLUMNS)
    assert result["unknown"].any()                                  # an untrained head is unsure
    assert not result["moving"].any()                               # this row claims no motion mask


def test_m06_names_the_seed_whose_cache_is_missing(tmp_path):
    rng = np.random.default_rng(7)
    keys = ["case_C01_L0_00"]
    write_cache(tmp_path, train_network.cache_arm("R1", "connectome", 0), keys, rng)
    for seed in (0, 1):
        write_checkpoint(tmp_path / "ckpt", "connectome", seed)
    clip = {"lum": np.zeros((FRAMES, COLUMNS), dtype=np.float32)}
    result = m06.run(clip, 4.6, root=tmp_path, arm="connectome", key=keys[0],
                     checkpoints=sorted((tmp_path / "ckpt").glob("R1-*.pt")))
    assert result["seeds"] == 1                                     # the present one, not an average of two

    with pytest.raises(FileNotFoundError, match="run cache-trained"):
        m06.run(clip, 4.6, root=tmp_path, arm="N1", key=keys[0],
                checkpoints=sorted((tmp_path / "ckpt").glob("R1-*.pt")))


def test_m06_refuses_a_clip_whose_cache_has_another_length(tmp_path):
    rng = np.random.default_rng(9)
    keys = ["case_C01_L0_00"]
    write_cache(tmp_path, train_network.cache_arm("R1", "connectome", 0), keys, rng)
    write_checkpoint(tmp_path / "ckpt", "connectome", 0)
    clip = {"lum": np.zeros((FRAMES + 3, COLUMNS), dtype=np.float32)}
    with pytest.raises(ValueError, match="frames"):
        m06.run(clip, 4.6, root=tmp_path, arm="connectome", key=keys[0],
                checkpoints=sorted((tmp_path / "ckpt").glob("R1-*.pt")))


def test_m06_needs_a_cache_key(tmp_path):
    write_checkpoint(tmp_path / "ckpt", "connectome", 0)
    with pytest.raises(ValueError, match="cache key"):
        m06.run({"lum": np.zeros((FRAMES, COLUMNS), np.float32)}, 4.6, root=tmp_path,
                checkpoints=sorted((tmp_path / "ckpt").glob("R1-*.pt")))


def test_the_calibration_picks_the_tolerance_its_own_error_matches(tmp_path):
    rng = np.random.default_rng(11)
    keys = [f"clip_{i}" for i in range(3)]
    write_cache(tmp_path, train_network.cache_arm("R1", "connectome", 0), keys, rng)
    write_checkpoint(tmp_path / "ckpt", "connectome", 0)
    import conectoma.stages.cache_activity as cache_module

    original = cache_module.split_clips
    cache_module.split_clips = lambda root, split, limit=None: [Path(f"{k}.npz") for k in keys]
    try:
        report = m06.calibrate_tolerance(tmp_path, arm="connectome", clips=None,
                                         device="cpu", derived=tmp_path / "ckpt")
    finally:
        cache_module.split_clips = original
    m06._HEADS.clear()
    assert report["chosen"]["tolerance"] in m06.TOLERANCE_GRID
    assert report["chosen"]["gap"] == min(row["gap"] for row in report["grid"])
    assert 0 < report["chosen"]["coverage"] <= 1


# ---------------------------------------------------------------- the registry


def test_the_evaluation_registry_routes_every_m06_row_to_its_arm():
    for name in ("M06", "M06-N1", "M06-N2", "M06-N3"):
        assert name in evaluate.METHODS and name in evaluate.KINDS
        entry = evaluate.METHODS[name]
        assert entry["trained"] == (name.split("-")[1] if "-" in name else "connectome")
        assert entry["call"] is None                 # routed to m06, never called directly
        assert "calibrate" in entry
    assert "m06" in evaluate.CODE                    # a row whose code is not digested is not traceable

# ---------------------------------------------------------------- the cache key is the clip's place


def test_a_clips_cache_key_is_its_place_in_the_corpus_not_its_file_name():
    """The same file name occurs in many trajectories; keying by it collapsed 1,860 clips onto 981."""
    first = cache_activity.clip_key(
        Path("root/vision/tartanair/rendered/AbandonedCable/easy/P000/clip_000665.npz"))
    second = cache_activity.clip_key(
        Path("root/vision/tartanair/rendered/Apocalyptic/hard/P000/clip_000665.npz"))
    assert first == "tartanair_AbandonedCable_easy_P000_clip_000665"
    assert first != second
    assert Path("a/clip_000665.npz").stem == Path("b/clip_000665.npz").stem   # what it replaced


def test_a_path_outside_the_rendered_tree_keeps_its_name():
    assert cache_activity.clip_key(Path("somewhere/else/clip_000001.npz")) == "clip_000001"

def test_every_trained_row_declares_the_row_it_is_the_next_regime_of():
    """A regime's claim is a paired difference against the row it started from, arm for arm."""
    for name, before in evaluate.REGIME_PREDECESSOR.items():
        assert name in evaluate.METHODS and before in evaluate.METHODS
        # the pair must be the SAME arm: comparing the connectome's R1 with a null's R0 measures nothing
        assert name.split("-")[1:] == before.split("-")[1:]
        arm = lambda entry: entry.get("trained") or entry.get("reservoir")  # noqa: E731
        assert arm(evaluate.METHODS[name]) == arm(evaluate.METHODS[before])


def test_each_trained_row_reads_the_networks_of_its_own_regime():
    """M06 reads regime R1's networks and M07 regime R2's; a row that read another regime's caches would
    report one regime's numbers under another's name."""
    for name, entry in evaluate.METHODS.items():
        if entry.get("trained"):
            expected = "R2" if name.startswith("M07") else "R1"
            assert entry.get("regime", "R1") == expected, name
            assert entry["calibrate"].keywords.get("regime", "R1") == expected, name

# ---------------------------------------------------------------- comparing at the same coverage


def test_a_matched_coverage_error_keeps_the_same_share_for_every_row():
    """Two rows that refuse different amounts cannot be compared on the error of what each kept."""
    from conectoma.methods import metrics

    truth = np.full(100, 10.0)
    estimate = np.full(100, 10.0)
    estimate[:50] = 20.0                       # the half this row is unsure about is also the wrong half
    uncertainty = np.concatenate([np.full(50, 1.0), np.full(50, 0.01)])
    out = metrics.matched_coverage(truth, estimate, uncertainty)
    assert out["columns_rankable"] == 100
    assert out["abs_rel_at_50"] == pytest.approx(0.0)        # the surer half is exactly right
    assert out["abs_rel_at_75"] == pytest.approx(0.5 / 1.5, abs=1e-6)
    assert out["abs_rel_at_25"] == pytest.approx(0.0)


def test_a_matched_coverage_error_ignores_what_a_row_refused():
    """The refusal threshold is what the comparison neutralises, so it cannot be applied first."""
    from conectoma.methods import metrics

    truth = np.full(10, 4.0)
    estimate = np.full(10, 4.0)
    uncertainty = np.arange(10, dtype=float)
    full = metrics.matched_coverage(truth, estimate, uncertainty)
    # a column with no truth or no estimate is not rankable, and does not count towards the share
    truth_gap = truth.copy()
    truth_gap[:5] = np.nan
    fewer = metrics.matched_coverage(truth_gap, estimate, uncertainty)
    assert full["columns_rankable"] == 10
    assert fewer["columns_rankable"] == 5
    assert fewer["abs_rel_at_50"] == pytest.approx(0.0)


def test_a_comparison_between_trained_rows_is_read_at_matched_coverage():
    assert evaluate.COMPARISON_KEY == "abs_rel_at_50"


def test_the_answer_everywhere_is_the_answer_before_any_seed_refused(tmp_path):
    """The matched-coverage comparison ranks the whole lattice, so the row must supply it unrefused.

    The first version took the median of each seed's answer AFTER its refusal: where every seed refused,
    the 'answer everywhere' was missing, and a row that refused more had fewer columns to be ranked on,
    which is the bias the matched-coverage comparison exists to remove.
    """
    rng = np.random.default_rng(13)
    keys = ["case_C01_L0_00"]
    for seed in (0, 1):
        write_cache(tmp_path, train_network.cache_arm("R1", "connectome", seed), keys, rng)
        write_checkpoint(tmp_path / "ckpt", "connectome", seed)
    clip = {"lum": np.zeros((FRAMES, COLUMNS), dtype=np.float32)}
    result = m06.run(clip, 4.6, root=tmp_path, arm="connectome", key=keys[0],
                     checkpoints=sorted((tmp_path / "ckpt").glob("R1-*.pt")), tolerance=1e-6)
    assert result["unknown"].all()                        # a tolerance this tight refuses every column
    assert np.isfinite(result["distance_all_m"]).all()    # and the answer everywhere is still there
    assert np.isnan(result["distance_m"]).all()


def test_the_scale_invariant_error_at_matched_coverage_ignores_a_global_scale():
    """A row that answers in metres where the truth is centimetres has the structure right or wrong
    whatever its scale, and this is the number that says which."""
    from conectoma.methods import metrics

    truth = np.linspace(0.05, 0.20, 100)
    uncertainty = np.linspace(0.1, 1.0, 100)
    right_structure = metrics.matched_coverage(truth, truth * 150.0, uncertainty)
    exact = metrics.matched_coverage(truth, truth, uncertainty)
    assert right_structure["abs_rel_at_50"] == pytest.approx(149.0)          # the scale failure, in full
    assert right_structure["silog_at_50"] == pytest.approx(0.0, abs=1e-12)   # and nothing else wrong
    assert exact["silog_at_50"] == pytest.approx(0.0, abs=1e-12)


def test_a_comparison_is_kept_inside_one_domain():
    """A scale-dependent comparison is never pooled across domains a network cannot recover the scale of."""
    assert evaluate.HEADLINE_DOMAIN == "in_domain"
    assert evaluate.DOMAINS["in_domain"] == ("tartanair",)
    assert "flygym" in evaluate.DOMAINS["fly_scale"]
    every = [source for sources in evaluate.DOMAINS.values() for source in sources]
    assert len(every) == len(set(every))                                    # a source is in one domain
