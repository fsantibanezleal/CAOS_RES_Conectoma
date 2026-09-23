"""The chain artifact: what the network concludes from each case, and the circuit it concludes it with.

Half of these read the committed artifact in place (what the web is actually served), half run the export
on a registry and readouts built in the test's own directory, so the machinery is checked without the
corpus, the GPU or the engine. Requirements: docs/design/features/chain-animated/requirements.md.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.stages import export_chain  # noqa: E402

DERIVED = ROOT / "data" / "derived"
MANIFEST = DERIVED / "manifests" / "chain.json"
FIXTURE = ROOT / "frontend" / "src" / "test" / "fixtures" / "chain-decoder.json"
COLUMNS = 721


def committed() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the committed artifact


def test_the_chain_carries_every_case_at_both_ends():
    manifest = committed()
    registry = json.loads((DERIVED / "vision" / "cases.json").read_text(encoding="utf-8"))
    for case_id, case in registry["cases"].items():
        ends = [i for i in export_chain.ENDS if i < len(case["variant"]["levels"])]
        named = [f"{case_id}/L{level}" for level in ends if f"{case_id}/L{level}" in manifest["missing"]]
        if len(named) == len(ends):
            continue
        assert case_id in manifest["cases"], f"{case_id} is neither exported nor named as missing"
        clip = json.loads((DERIVED / manifest["cases"][case_id]["path"]).read_text(encoding="utf-8"))
        for level in ends:
            assert str(level) in clip["levels"] or f"{case_id}/L{level}" in manifest["missing"], (
                f"{case_id} level {level} is neither exported nor named")


def test_both_regimes_are_carried():
    manifest = committed()
    for case_id, entry in manifest["cases"].items():
        clip = json.loads((DERIVED / entry["path"]).read_text(encoding="utf-8"))
        for level, data in clip["levels"].items():
            for row in export_chain.ROWS:
                assert row in data["rows"], f"{case_id} L{level} has no entry for {row}"
                carried = data["rows"][row]
                assert "depth" in carried or "missing" in carried


def test_the_chain_stays_within_its_budget():
    manifest = committed()
    total = sum(entry["bytes"] for entry in manifest["cases"].values()) + manifest["circuit"]["bytes"]
    assert total <= 6_000_000, f"the chain is {total / 1e6:.2f} MB, over its 6 MB budget"
    for entry in list(manifest["cases"].values()) + [manifest["circuit"]]:
        path = DERIVED / entry["path"]
        assert path.stat().st_size == entry["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def test_the_circuit_is_the_specifications_own():
    manifest = committed()
    circuit = json.loads((DERIVED / manifest["circuit"]["path"]).read_text(encoding="utf-8"))
    spec = json.loads((DERIVED / "connectome" / "malecns-optic-lobe-r.json").read_text(encoding="utf-8"))
    names = set(export_chain.CIRCUIT_LAYERS)
    expected = {}
    for edge in spec["edges"]:
        if edge["src"] in names and edge["tar"] in names:
            synapses = float(sum(count for _, count in edge["offsets"]))
            if synapses > 0:
                expected[(edge["src"], edge["tar"])] = (round(synapses, 3), int(np.sign(edge["alpha"])))
    drawn = {(e["source"], e["target"]): (e["synapses"], e["sign"]) for e in circuit["edges"]}
    assert drawn == expected, "the circuit draws a connection the specification does not have, or misses one"
    assert circuit["direction_selectivity"]["largest"] < 0.1


def test_the_browser_decoder_fixture_is_the_pipelines():
    """The fixture src/test/chain.test.ts checks the browser against is what THIS decoder says."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw = base64.b64decode(fixture["depth"]["bytes"])
    decoded = export_chain.decode_depth(fixture["depth"]["bytes"], (1, len(raw)))[0]
    for got, want in zip(decoded, fixture["depth"]["metres"], strict=True):
        assert (want is None and not np.isfinite(got)) or got == pytest.approx(want, rel=1e-9)
    mask = export_chain.decode_mask(fixture["mask"]["bytes"], (fixture["mask"]["rows"], COLUMNS))
    assert [list(np.flatnonzero(row)) for row in mask] == fixture["mask"]["set"]


# ---------------------------------------------------------------- the export, on a registry of its own


def a_registry(tmp_path: Path, monkeypatch, frames: int = 5):
    """One case, one clip at both ends of its sweep, with a depth the readout can be compared with."""
    case = {"name": "a case", "category": "nominal-outdoor", "grades": ["depth"], "source": "tartanair",
            "variant": {"quantity": "ego speed", "unit": "x", "transform": "speed",
                        "levels": [0.5, 1, 2, 4, 8, 16]}}
    monkeypatch.setattr(export_chain.cases, "load_cases", lambda: ({"cases": {"C99": case}}, "digest"))
    truth = np.full((frames, COLUMNS), 6.0)
    for level in export_chain.ENDS:
        path = export_chain.case_clip_path(tmp_path, "C99", level)
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = {"measured": {"column_spacing_deg": 4.6}, "interval_s": 0.1}
        np.savez(path, stamp=json.dumps(stamp), lum=np.zeros((frames, COLUMNS), np.float32), depth=truth)
    reports = tmp_path / "reports"
    reports.mkdir()
    for row, tolerance in (("M05", 2.0), ("M06", 1.5)):
        (reports / f"{row}.json").write_text(json.dumps({"thresholds": {"tolerance": tolerance, "window": 2}}))
    monkeypatch.setattr(export_chain, "circuit", lambda: {"nodes": [], "edges": [], "source": "test"})
    monkeypatch.setattr(export_chain, "direction_selectivity", lambda: {"largest": 0.0})
    return reports, truth


def test_the_readout_is_the_scored_readout(tmp_path, monkeypatch):
    """The call is the scoring stage's call, with the tolerance the committed report was scored with."""
    reports, truth = a_registry(tmp_path, monkeypatch)
    seen = []

    def readout(row, clip, spacing, root, key, thresholds):
        seen.append((row, thresholds["tolerance"], thresholds["window"], key))
        steps = len(clip["lum"]) - 1
        return {"distance_m": np.full((steps, COLUMNS), np.nan), "distance_all_m": np.full((steps, COLUMNS), 3.0),
                "unknown": np.ones((steps, COLUMNS), bool), "uncertainty": np.full((steps, COLUMNS), 2.5),
                "seeds": 5}

    monkeypatch.setattr(export_chain, "readout", readout)
    out = tmp_path / "chain"
    manifest = export_chain.run(tmp_path, reports=reports, out_dir=out, manifests=tmp_path / "manifests")
    assert ("M05", 2.0, 2, "case_C99_L0_00") in seen
    assert ("M06", 1.5, 2, "case_C99_L5_00") in seen
    clip = json.loads((out / "C99.json").read_text(encoding="utf-8"))
    level = clip["levels"]["0"]
    steps = level["steps"]
    # the answer everywhere is carried, with the refusal as its own layer, not the answer after refusal
    depth = export_chain.decode_depth(level["rows"]["M05"]["depth"], (steps, COLUMNS))
    assert np.allclose(depth, 3.0, rtol=0.05)
    assert export_chain.decode_mask(level["rows"]["M05"]["refused"], (steps, COLUMNS)).all()
    assert np.allclose(export_chain.decode_depth(level["truth"], (steps, COLUMNS)), truth[:steps], rtol=0.05)
    assert manifest["rows"]["M05"]["thresholds"]["tolerance"] == 2.0


def test_a_missing_readout_is_named(tmp_path, monkeypatch):
    reports, _ = a_registry(tmp_path, monkeypatch)

    def readout(row, *args, **kwargs):
        if row == "M06":
            raise FileNotFoundError("no trained R1 network for arm connectome at window 2")
        steps = 4
        return {"distance_m": np.full((steps, COLUMNS), 3.0), "unknown": np.zeros((steps, COLUMNS), bool),
                "uncertainty": np.ones((steps, COLUMNS)), "seeds": 5}

    monkeypatch.setattr(export_chain, "readout", readout)
    out = tmp_path / "chain"
    manifest = export_chain.run(tmp_path, reports=reports, out_dir=out, manifests=tmp_path / "manifests")
    assert "C99/L0/M06" in manifest["missing"]
    assert "no trained R1 network" in manifest["missing"]["C99/L0/M06"]
    clip = json.loads((out / "C99.json").read_text(encoding="utf-8"))
    carried = clip["levels"]["0"]["rows"]["M06"]
    assert "missing" in carried and "depth" not in carried       # named, never drawn as an empty map


def test_depth_survives_its_encoding_within_one_step():
    depth = np.array([[0.1, 1.0, 7.3, 250.0, 5000.0, np.nan, 0.0]])
    back = export_chain.decode_depth(export_chain.encode_depth(depth), depth.shape)
    step = np.exp((np.log(export_chain.DEPTH_HI_M) - np.log(export_chain.DEPTH_LO_M)) / 254)
    finite = np.isfinite(depth) & (depth > 0)
    assert np.all(np.abs(np.log(back[finite] / depth[finite])) <= np.log(step) / 2 + 1e-9)
    assert np.isnan(back[~finite]).all()
