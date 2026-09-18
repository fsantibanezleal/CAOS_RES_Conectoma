"""Stage: render every fetched clip onto the lattice, check it against contract 1, and list it in a manifest.

Parallel over clips (one process per clip at a time), resumable: a clip whose rendering exists with the
current render version and whose source archive has not changed is not rendered again. Each rendering is a
compressed array file next to the fetched data; the manifest is one row per clip with its statistics and the
SHA-256 of the rendering, and rejected clips are listed with their reasons instead of rows.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from conectoma.core.jsonio import write_json
from conectoma.vision.contract import clip_problems, clip_statistics
from conectoma.vision.render import RENDER_VERSION, render_tartanair_clip


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def rendered_path(base: Path, clip_zip: Path) -> Path:
    relative = clip_zip.relative_to(base / "data")
    return (base / "rendered" / relative).with_suffix(".npz")


def _render_one(base: str, clip_zip: str) -> dict:
    base_path, source = Path(base), Path(clip_zip)
    out = rendered_path(base_path, source)
    stamp = {"render_version": RENDER_VERSION, "source_bytes": source.stat().st_size}
    if out.exists():
        with np.load(out) as existing:
            if json.loads(str(existing["stamp"])) == stamp:
                clip = {k: existing[k] for k in existing.files if k != "stamp"}
                return {"clip": str(source.relative_to(base_path / "data")), "status": "kept",
                        "problems": clip_problems(clip), "statistics": clip_statistics(clip),
                        "sha256": _sha256(out)}
    clip = render_tartanair_clip(source)
    problems = clip_problems(clip)
    if not problems:
        out.parent.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(out.stem + ".partial.npz")
        np.savez_compressed(partial, stamp=json.dumps(stamp), **clip)
        os.replace(partial, out)
    return {"clip": str(source.relative_to(base_path / "data")), "status": "rendered", "problems": problems,
            "statistics": clip_statistics(clip), "sha256": _sha256(out) if not problems else None}


def render_tartanair(root: Path, workers: int = 4) -> dict:
    """Render every clip the fetch log lists as complete."""
    base = root / "vision" / "tartanair"
    done = set()
    with open(base / "fetch-log.jsonl", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                try:
                    done.add(json.loads(line)["clip"])
                except (json.JSONDecodeError, KeyError):
                    continue
    clips = []
    for key in sorted(done):
        environment, difficulty, trajectory, start = key.split("/")
        path = base / "data" / environment / difficulty / trajectory / f"clip_{start}.zip"
        if path.exists():
            clips.append(path)
    started = time.time()
    rows, rejected, failed = [], [], {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_render_one, str(base), str(path)): path for path in clips}
        for i, future in enumerate(as_completed(futures), 1):
            path = futures[future]
            try:
                result = future.result()
            except Exception as error:  # one unreadable clip does not stop the others; it is listed
                failed[str(path.relative_to(base / "data"))] = str(error)
                continue
            (rejected if result["problems"] else rows).append(result)
            if i % 100 == 0:
                print(f"  {i}/{len(clips)} clips, {(time.time() - started) / 60:.1f} min", flush=True)
    rows.sort(key=lambda r: r["clip"])
    summary = {
        "render_version": RENDER_VERSION, "clips": len(clips), "accepted": len(rows),
        "rejected": len(rejected), "failed": len(failed), "elapsed_seconds": round(time.time() - started, 1),
    }
    write_json(base / "rendered" / "manifest.json",
               {"summary": summary, "clips": rows, "rejected": rejected, "failed": failed})
    return summary
