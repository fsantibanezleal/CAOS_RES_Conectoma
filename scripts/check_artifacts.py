"""CONTRACT 2 on disk: every artifact the web reads matches the manifest that describes it.

The site serves the committed files under data/derived as they are, so the manifest is the only
record of what they contain. This check reads both manifests and, for every file they declare,
compares the bytes and the SHA-256 on disk against the manifest, plus the provenance digests that
tie an artifact to the input it was built from (the explorer to its connectome specification, the
eye clips to cases.json). It then re-reads the committed split table and re-derives the leakage
conditions from it: one split per geometry family, one family per environment, and per-split clip,
frame, environment and family counts that match the table row by row.

Stdlib only: CI runs it without installing anything (ADR-0074).

Usage: python scripts/check_artifacts.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
MANIFESTS = DERIVED / "manifests"


def load(path: Path, errs: list[str]) -> dict | None:
    if not path.exists():
        errs.append(f"missing manifest: {path.relative_to(ROOT).as_posix()}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errs.append(f"unreadable manifest {path.relative_to(ROOT).as_posix()}: {exc}")
        return None


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_file(entry: dict, base: Path, label: str, errs: list[str]) -> None:
    """The file `entry` declares: it exists, it is not empty, its size and digest are the recorded ones."""
    path = base / entry["path"]
    if not path.exists():
        errs.append(f"{label}: missing artifact {entry['path']}")
        return
    size = path.stat().st_size
    if size == 0:
        errs.append(f"{label}: empty artifact {entry['path']}")
        return
    if size != entry["bytes"]:
        errs.append(f"{label}: byte drift on {entry['path']}: manifest={entry['bytes']} disk={size}")
    found = digest(path)
    if found != entry["sha256"]:
        errs.append(
            f"{label}: digest drift on {entry['path']}: "
            f"manifest={entry['sha256'][:12]} disk={found[:12]}"
        )


def check_explorer(errs: list[str]) -> int:
    manifest = load(MANIFESTS / "explorer.json", errs)
    if manifest is None:
        return 0
    check_file(manifest, DERIVED, "explorer", errs)
    # the explorer is a projection of one connectome specification: the digest says which one
    spec = DERIVED / "connectome" / manifest["source"]["specification"]
    if not spec.exists():
        errs.append(f"explorer: missing specification {spec.relative_to(ROOT).as_posix()}")
    elif digest(spec) != manifest["source"]["specification_sha256"]:
        errs.append("explorer: the specification on disk is not the one the explorer was built from")
    if not manifest["reference"].get("sha256"):
        errs.append("explorer: the reference connectome carries no digest")
    return 1


def check_eyeclips(errs: list[str]) -> int:
    manifest = load(MANIFESTS / "eyeclips.json", errs)
    if manifest is None:
        return 0
    cases_path = DERIVED / "vision" / manifest["source"]["cases"]
    if not cases_path.exists():
        errs.append(f"eyeclips: missing {cases_path.relative_to(ROOT).as_posix()}")
        return 0
    if digest(cases_path) != manifest["source"]["cases_sha256"]:
        errs.append("eyeclips: cases.json on disk is not the one the clips were exported from")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if cases["render_version"] != manifest["source"]["render_version"]:
        errs.append(
            f"eyeclips: render version {manifest['source']['render_version']} in the manifest, "
            f"{cases['render_version']} in cases.json"
        )
    declared = set(manifest["cases"])
    rendered = set(cases["cases"])
    for case_id in sorted(rendered - declared):
        errs.append(f"eyeclips: case {case_id} is rendered but the manifest declares no clip for it")
    for case_id in sorted(declared - rendered):
        errs.append(f"eyeclips: the manifest declares {case_id}, which cases.json does not have")
    lattice = manifest["lattice"]
    for key in ("row_px", "col_px", "u", "v"):
        if len(lattice[key]) != 721:
            errs.append(f"eyeclips: the lattice gives {len(lattice[key])} values for {key}, not 721 columns")
    for case_id in sorted(declared):
        check_file(manifest["cases"][case_id], DERIVED, f"eyeclips/{case_id}", errs)
    return len(declared)


def check_splits(errs: list[str]) -> int:
    """The split table: one split per family, one family per environment, counts that add up row by row."""
    splits_path = DERIVED / "vision" / "splits.json"
    table_path = DERIVED / "vision" / "tartanair-clips.csv"
    if not splits_path.exists() or not table_path.exists():
        errs.append("splits: the committed split of the corpus is missing")
        return 0
    splits = json.loads(splits_path.read_text(encoding="utf-8"))
    if splits["leakage"]["problems"]:
        errs.append(f"splits: the recorded leakage test has {len(splits['leakage']['problems'])} problems")
    of_family = {name: entry["split"] for name, entry in splits["families"].items()}
    seen: dict[str, str] = {}
    for name, entry in splits["families"].items():
        if entry["split"] not in splits["counts"]:
            errs.append(f"splits: family {name} is in split {entry['split']}, which the counts do not list")
        for environment in entry["members"]:
            if environment in seen:
                errs.append(
                    f"splits: environment {environment} is in families {seen[environment]} and {name}"
                )
            seen[environment] = name

    counted: dict[str, dict[str, int]] = {
        split: {"clips": 0, "frames": 0} for split in splits["counts"]
    }
    environments: dict[str, set[str]] = {split: set() for split in splits["counts"]}
    families: dict[str, set[str]] = {split: set() for split in splits["counts"]}
    with table_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            split, family = row["split"], row["family"]
            if split not in counted:
                errs.append(f"splits: clip {row['key']} is in split {split}, which the counts do not list")
                continue
            if of_family.get(family) != split:
                errs.append(
                    f"splits: clip {row['key']} is in {split} but its family {family} "
                    f"is in {of_family.get(family)}"
                )
            counted[split]["clips"] += 1
            counted[split]["frames"] += int(row["frames"])
            environments[split].add(row["environment"])
            families[split].add(family)
    for split, recorded in splits["counts"].items():
        found = {
            "clips": counted[split]["clips"],
            "frames": counted[split]["frames"],
            "environments": len(environments[split]),
            "families": len(families[split]),
        }
        for key, value in found.items():
            if recorded[key] != value:
                errs.append(f"splits: {split} records {recorded[key]} {key}, the table has {value}")
    return sum(entry["clips"] for entry in splits["counts"].values())


def check_evaluation(errs: list[str]) -> int:
    """The scored methods, when any have been committed: each report matches its manifest entry."""
    path = MANIFESTS / "evaluation.json"
    if not path.exists():
        return 0                      # no method has been scored yet, which is not drift
    manifest = load(path, errs)
    if manifest is None:
        return 0
    cases_path = DERIVED / "vision" / "cases.json"
    if cases_path.exists() and digest(cases_path) != manifest["source"]["cases_sha256"]:
        errs.append("evaluation: the reports were scored on a different cases.json than the one on disk")
    for method, entry in sorted(manifest["methods"].items()):
        check_file(entry, DERIVED, f"evaluation/{method}", errs)
    return len(manifest["methods"])


def main() -> int:
    errs: list[str] = []
    explorer = check_explorer(errs)
    clips = check_eyeclips(errs)
    rendered = check_splits(errs)
    scored = check_evaluation(errs)
    if errs:
        print("CONTRACT 2 DRIFT:")
        for err in errs:
            print(f"::error::{err}")
        return 1
    print(
        f"CONTRACT 2 OK: {explorer} explorer artifact, {clips} eye clips, {rendered} split clips, "
        f"{scored} scored methods; manifests, digests and the split table all agree with the files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
