"""The generated parts of the case pages: what each level measured, from data/derived/vision/cases.json.

Every case page under docs/cases/ is written by hand, except one table between two markers, which this
module writes from the committed case summary; so is the registry table of docs/cases.md. A test fails when
a page's table differs from what the summary gives, so the numbers on a page are always the committed ones.
"""

from __future__ import annotations

import re
from pathlib import Path

BEGIN = "<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->"
END = "<!-- /measured -->"

# per case: the measured quantities and the rendering statistics its table shows, in order
COLUMNS = {
    "C01": ["speed_m_s", "frame_rate_hz", "depth_median_m", "engine_flow_per_frame"],
    "C02": ["speed_m_s", "frame_rate_hz", "depth_median_m", "engine_flow_per_frame"],
    "C03": ["lum_mean", "lum_std", "depth_median_m"],
    "C04": ["vertical_fov_deg", "column_spacing_deg", "figure_share", "depth_median_m"],
    "C05": ["snr_at_mean", "photons_per_column_per_s", "lum_mean", "lum_std"],
    "C06": ["blur_length_px", "lum_std", "engine_flow_per_frame"],
    "C07": ["visibility_m", "rms_contrast", "lum_mean", "depth_median_m"],
    "C08": ["rms_contrast", "column_spacing_deg", "engine_flow_per_frame"],
    "C09": ["column_spacing_deg", "focal_px_at_436_rows", "depth_median_m", "sky_share"],
    "C10": ["eye_to_near_edge_mm", "figure_share", "depth_median_m", "column_spacing_deg"],
    "C11": ["speed_mm_s", "angular_size_deg", "figure_share", "depth_min_m"],
    "C12": ["radius_mm", "figure_share", "depth_min_m"],
    "C13": ["rotation_deg_per_frame", "engine_flow_per_frame", "depth_median_m"],
    "C14": ["snr_at_mean", "lum_mean", "lum_std"],
    "C15": ["plane_depths_m", "engine_flow_per_frame", "figure_share"],
    "C16": ["texture_contrast", "rms_contrast", "engine_flow_per_frame", "figure_share"],
}
LABELS = {
    "speed_m_s": "speed (m/s)",
    "frame_rate_hz": "frame rate (Hz)",
    "lum_mean": "mean luminance",
    "lum_std": "luminance SD",
    "snr_at_mean": "SNR at mean luminance",
    "photons_per_column_per_s": "photons per column per s",
    "blur_length_px": "blur (px, median)",
    "visibility_m": "visibility (m)",
    "rms_contrast": "RMS contrast",
    "vertical_fov_deg": "vertical field (deg)",
    "column_spacing_deg": "column spacing (deg)",
    "focal_px_at_436_rows": "focal at 436 rows (px)",
    "rotation_deg_per_frame": "turn per frame (deg)",
    "engine_flow_per_frame": "flow per frame (engine units)",
    "plane_depths_m": "nearest to farthest plane (m)",
    "texture_contrast": "texture contrast",
    "eye_to_near_edge_mm": "eye to near edge, first to last frame (mm)",
    "speed_mm_s": "approach speed (mm/s)",
    "angular_size_deg": "angular size, first to last frame (deg)",
    "radius_mm": "target radius (mm)",
    "figure_share": "figure share",
    "depth_median_m": "median depth (m)",
    "depth_min_m": "nearest depth (m)",
    "sky_share": "sky share",
}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def page_name(case_id: str, case: dict) -> str:
    return f"{case_id}_{slug(case['name'])}.md"


def _number(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, list):
        return f"{_number(value[0])} to {_number(value[-1])}"
    if isinstance(value, str):
        return value
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 100:
        return f"{value:.0f}"
    if magnitude >= 10:
        return f"{value:.1f}"
    if magnitude >= 1:
        return f"{value:.2f}"
    return f"{value:.3g}"


def _level(value, unit: str) -> str:
    if value is None:
        return "none (no noise)"
    return f"{_number(value)} {unit}" if not isinstance(value, str) else value


def table(case_id: str, case: dict) -> str:
    unit = case["variant"]["unit"]
    columns = COLUMNS[case_id]
    head = ["level", "clips", "frame interval (ms)"] + [LABELS[c] for c in columns]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for level in case["levels"]:
        interval = level.get("interval_s")
        values = {**level.get("statistics", {}), **level.get("measured", {})}
        cells = [_level(level["value"], unit), f"{level['accepted']} of {level['clips']}",
                 _number(interval * 1000) if interval else "n/a (single images)"]
        cells += [_number(values.get(c)) for c in columns]
        rows.append("| " + " | ".join(cells) + " |")
    drawn = ", ".join(f"`{item}`" for item in case["items"])
    return "\n".join(rows) + f"\n\nMedians over the clips of each level. Drawn: {drawn}."


def registry_table(summary: dict) -> str:
    head = ["case", "category", "source", "varies", "levels", "grades", "clips"]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for case_id, case in summary["cases"].items():
        variant = case["variant"]
        levels = ", ".join(_level(v, "").strip() for v in variant["levels"])
        rows.append("| " + " | ".join([
            f"[{case_id}, {case['name']}](cases/{page_name(case_id, case)})", case["category"],
            case["source"] + (f" ({case['family']})" if case.get("family") else ""),
            f"{variant['quantity']} ({variant['unit']})", levels, ", ".join(case["grades"]),
            str(len(case["items"])),
        ]) + " |")
    return "\n".join(rows)


def replace_block(text: str, block: str, where: str) -> str:
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError(f"{where}: needs exactly one generated block between the markers")
    before, rest = text.split(BEGIN)
    _, after = rest.split(END)
    return f"{before}{BEGIN}\n{block}\n{END}{after}"


def update(summary: dict, docs: Path, write: bool = True) -> list[str]:
    """Rewrite every generated block; returns the pages whose block changed (written only if `write`)."""
    changed = []
    targets = [(docs / "cases.md", registry_table(summary))]
    targets += [(docs / "cases" / page_name(c, case), table(c, case)) for c, case in summary["cases"].items()]
    for path, block in targets:
        text = path.read_text(encoding="utf-8")
        new = replace_block(text, block, str(path))
        if new != text:
            changed.append(path.name)
            if write:
                path.write_text(new, encoding="utf-8", newline="\n")
    return changed
