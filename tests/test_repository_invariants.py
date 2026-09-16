"""Repository invariants that must hold at every version of this product.

These are cheap, real checks: the archetype layout exists, nothing heavy or private is tracked, and the
version sources agree. They run in CI on every push and they are the first gate a new unit must keep green.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HEAVY_SUFFIXES = {
    ".parquet", ".h5", ".hdf5", ".nc", ".mat", ".npy", ".feather",
    ".pt", ".pth", ".onnx", ".safetensors", ".bin",
    ".dll", ".so", ".dylib",
}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def test_archetype_layout_exists() -> None:
    """The uniform folder set of the product archetype is present."""
    for relative in ("data-pipeline", "data", "app", "deploy", "docs", "scripts", "models", "manifests"):
        assert (ROOT / relative).is_dir(), f"missing archetype directory: {relative}"


def test_community_and_versioning_files_exist() -> None:
    for relative in (
        "README.md", "LICENSE", "CHANGELOG.md", "VERSION",
        "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md",
        ".gitignore", ".env.example",
    ):
        assert (ROOT / relative).is_file(), f"missing required file: {relative}"


def test_version_file_is_display_form_and_matches_changelog() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d{2}\.\d{3}", version), f"VERSION is not X.XX.XXX: {version!r}"
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog, f"CHANGELOG has no entry for {version}"


def test_no_heavy_or_private_artifacts_are_tracked() -> None:
    offenders = [
        path for path in tracked_files()
        if Path(path).suffix.lower() in HEAVY_SUFFIXES
        or Path(path).name == ".env"
        or ".venv" in path
        or "node_modules" in path
    ]
    assert not offenders, f"heavy or private files are tracked: {offenders}"


def test_raw_data_directory_is_not_tracked() -> None:
    """data/raw is a local cache for the connectome tables and datasets; only its placeholder is tracked."""
    tracked_raw = [p for p in tracked_files() if p.startswith("data/raw/") and not p.endswith(".gitkeep")]
    assert not tracked_raw, f"raw data is tracked: {tracked_raw}"
