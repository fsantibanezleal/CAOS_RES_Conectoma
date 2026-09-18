"""Reports and run logs: what a long run writes must survive numpy values, crashes and changed inputs.

A forty-minute parity run once finished its simulations and then failed while writing its report, because
a stimulus speed was a numpy scalar; the results were only in memory. These tests hold the two pieces that
prevent a repeat: the writer that makes numpy values plain and replaces files in one step, and the run log
that keeps every finished step on disk and refuses to reuse steps computed from other inputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data-pipeline"))

from conectoma.core.jsonio import write_json  # noqa: E402
from conectoma.core.runlog import RunLog  # noqa: E402


def test_numpy_values_are_written_as_plain_json(tmp_path: Path) -> None:
    report = {
        "speed": np.float64(2.4),
        "angle": np.int64(30),
        "angles": np.arange(3),
        "path": tmp_path,
        "flag": np.bool_(True),
    }
    written = json.loads(write_json(tmp_path / "r.json", report).read_text(encoding="utf-8"))
    assert written == {"speed": 2.4, "angle": 30, "angles": [0, 1, 2], "path": str(tmp_path), "flag": True}


def test_a_failed_write_leaves_the_previous_file_intact(tmp_path: Path) -> None:
    path = write_json(tmp_path / "r.json", {"ok": 1})
    with pytest.raises(TypeError):
        write_json(path, {"bad": object()})
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": 1}


def test_finished_steps_are_reused_and_not_recomputed(tmp_path: Path) -> None:
    calls = []

    def compute() -> dict:
        calls.append(1)
        return {"dsi": np.float32(0.5)}

    first = RunLog(tmp_path / "run.json", {"digest": "abc"})
    assert first.step("model/000", compute) == {"dsi": 0.5}
    second = RunLog(tmp_path / "run.json", {"digest": "abc"})
    assert second.step("model/000", compute) == {"dsi": 0.5}
    assert len(calls) == 1
    assert second.reused == ["model/000"]


def test_steps_from_other_inputs_are_set_aside(tmp_path: Path) -> None:
    RunLog(tmp_path / "run.json", {"digest": "abc"}).put("model/000", {"dsi": 0.5})
    changed = RunLog(tmp_path / "run.json", {"digest": "def"})
    assert "model/000" not in changed
    assert (tmp_path / "run.json.stale").is_file()
