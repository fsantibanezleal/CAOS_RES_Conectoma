"""The SDD gate refuses a requirement whose gate is imaginary, in either language the gates are written in.

A gate that only checked that a `Gate:` line exists would itself be the failure the rule was written for:
a check that is believed and measures nothing. These cases prove the check is not vacuous.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "check_sdd.py"


def run_gate(tmp_path: Path, gate: str) -> int:
    (tmp_path / "docs" / "design").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_a.py").write_text("def test_real():\n    pass\n", encoding="utf-8")
    (tmp_path / "web.test.ts").write_text("it('a titled check', () => {});\n", encoding="utf-8")
    (tmp_path / "docs" / "design" / "SDD.md").write_text(
        f"```\nR-001 THE thing SHALL work.\n      Gate: {gate}\n```\n", encoding="utf-8")
    return subprocess.run([sys.executable, str(GATE), str(tmp_path)], capture_output=True).returncode


@pytest.mark.parametrize(("gate", "expected"), [
    ("tests/test_a.py::test_real", 0),
    ("tests/test_a.py::test_imaginary", 1),
    ("tests/test_missing.py::test_real", 1),
    ("web.test.ts::a titled check", 0),
    ("web.test.ts::no such check", 1),
    ("manual: someone looks", 1),
])
def test_a_requirement_passes_only_when_its_gate_exists(tmp_path, gate, expected):
    assert run_gate(tmp_path, gate) == expected


def test_code_without_a_design_document_is_refused(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    code = subprocess.run([sys.executable, str(GATE), str(tmp_path)], capture_output=True).returncode
    assert code == 1


def test_this_repository_passes_its_own_gate():
    code = subprocess.run([sys.executable, str(GATE), str(ROOT)], capture_output=True, text=True)
    assert code.returncode == 0, code.stdout
