"""Splits by geometry, and the test that they do not leak.

TartanAir V2 renders one geometry under several names (a house by day and by night, a town in four seasons),
so the unit a split assigns is the geometry family declared in `config/vision.yaml`, never the environment
name. Families that the cases draw test clips from are always test; the remaining families are drawn with a
fixed seed into validation, calibration and test, and the rest train. Transfer and synthetic sources are
test only.

The leakage test is the gate of unit U4. It fails when a family or an environment appears in two splits, or
when the same image bytes (the CRC32 and size the archives record for a frame) appear in two splits, which
catches a duplicated scene that the family table missed.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

SPLITS = ("train", "validation", "calibration", "test")


def family_of(config: dict, environments: list[str]) -> dict[str, str]:
    """Environment to geometry family; an environment in no declared family is its own."""
    declared = {}
    for family, spec in config["families"].items():
        for member in spec["members"]:
            if member in declared:
                raise ValueError(f"{member} is declared in two families: {declared[member]} and {family}")
            declared[member] = family
    unknown = sorted(set(declared) - set(environments))
    if unknown:
        raise ValueError(f"families name environments that do not exist: {unknown}")
    return {env: declared.get(env, env) for env in environments}


def assign(config: dict, environments: list[str]) -> dict[str, str]:
    """Family to split, by the declared rule."""
    families = sorted(set(family_of(config, environments).values()))
    rule = config["splits"]
    cases = set(rule["case_families"])
    missing = sorted(cases - set(families))
    if missing:
        raise ValueError(f"case families that are not families: {missing}")
    rest = [f for f in families if f not in cases]
    order = np.random.default_rng(rule["seed"]).permutation(len(rest))
    rest = [rest[i] for i in order]
    counts = {name: round(rule[f"{name}_fraction"] * len(families)) for name in ("validation", "calibration")}
    counts["test"] = max(0, round(rule["test_fraction"] * len(families)))
    split = {f: "test" for f in cases}
    cursor = 0
    for name in ("validation", "calibration", "test"):
        for family in rest[cursor: cursor + counts[name]]:
            split[family] = name
        cursor += counts[name]
    for family in rest[cursor:]:
        split[family] = "train"
    return split


def leakage_problems(clips: list[dict], families: dict[str, str], split_of_family: dict[str, str],
                     frame_digests: dict[str, list[tuple[str, int]]] | None = None) -> list[str]:
    """Every way the split leaks (empty when it does not).

    `clips` rows carry `environment` and `split`; `frame_digests` maps a clip key to the (CRC32, bytes) of its
    image frames, from the fetch log.
    """
    problems = []
    seen: dict[str, set[str]] = defaultdict(set)
    for clip in clips:
        seen[("family", families[clip["environment"]])].add(clip["split"])
        seen[("environment", clip["environment"])].add(clip["split"])
        expected = split_of_family[families[clip["environment"]]]
        if clip["split"] != expected:
            problems.append(f"{clip['key']} is in {clip['split']}, its family is assigned to {expected}")
    for (kind, name), splits in sorted(seen.items()):
        if len(splits) > 1:
            problems.append(f"{kind} {name} appears in {sorted(splits)}")
    if frame_digests:
        where: dict[tuple[str, int], set[str]] = defaultdict(set)
        split_of_clip = {clip["key"]: clip["split"] for clip in clips}
        for key, digests in frame_digests.items():
            if key not in split_of_clip:
                continue
            for digest in digests:
                where[digest].add(split_of_clip[key])
        shared = [d for d, s in where.items() if len(s) > 1]
        if shared:
            problems.append(f"{len(shared)} identical frames appear in more than one split")
    return problems
