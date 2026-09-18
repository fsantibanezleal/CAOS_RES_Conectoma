"""Stage: render every fetched clip onto the lattice, check it against contract 1, and list it in a manifest.

One command per source (TartanAir, Spring, Hypersim), parallel over clips, resumable: a clip whose rendering
exists with the current render version and whose source archive has not changed is not rendered again. Each
rendering is a compressed array file under the source's `rendered/`; the manifest is one row per clip with
its statistics and the SHA-256 of the rendering, and rejected clips are listed with their reasons.
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
from conectoma.vision import render
from conectoma.vision.contract import clip_problems, clip_statistics
from conectoma.vision.render import RENDER_VERSION

SOURCES = ("tartanair", "spring", "hypersim")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _render(source: str, clip_zip: Path) -> dict:
    if source == "tartanair":
        return render.render_tartanair_clip(clip_zip)
    if source == "spring":
        return render.render_spring_clip(clip_zip)
    from conectoma.vision.hypersim import cameras

    return render.render_hypersim_clip(clip_zip, cameras()[clip_zip.parent.name])


def _render_one(source: str, base: str, clip_zip: str) -> dict:
    base_path, archive = Path(base), Path(clip_zip)
    out = (base_path / "rendered" / archive.relative_to(base_path / "data")).with_suffix(".npz")
    stamp = {"render_version": RENDER_VERSION, "source_bytes": archive.stat().st_size}
    name = str(archive.relative_to(base_path / "data"))
    if out.exists():
        with np.load(out) as existing:
            if json.loads(str(existing["stamp"])) == stamp:
                clip = {k: existing[k] for k in existing.files if k != "stamp"}
                return {"clip": name, "status": "kept", "problems": clip_problems(clip, source),
                        "statistics": clip_statistics(clip), "sha256": _sha256(out)}
    clip = _render(source, archive)
    problems = clip_problems(clip, source)
    if not problems:
        out.parent.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(out.stem + ".partial.npz")
        np.savez_compressed(partial, stamp=json.dumps(stamp), **clip)
        os.replace(partial, out)
    return {"clip": name, "status": "rendered", "problems": problems, "statistics": clip_statistics(clip),
            "sha256": _sha256(out) if not problems else None}


def _logged_archives(base: Path) -> list[Path]:
    """The clip archives the fetch log lists as complete and that exist on disk."""
    archives = []
    with open(base / "fetch-log.jsonl", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                key = json.loads(line)["clip"]
            except (json.JSONDecodeError, KeyError):
                continue
            parts = key.split("/")
            if parts[0] == "spring":
                path = base / "data" / parts[1] / f"clip_{parts[2]}.zip"
            elif parts[0] == "hypersim":
                path = base / "data" / parts[1] / f"{parts[2]}.zip"
            else:
                environment, difficulty, trajectory, start = parts
                path = base / "data" / environment / difficulty / trajectory / f"clip_{start}.zip"
            if path.exists():
                archives.append(path)
    return sorted(set(archives))


def render_source(root: Path, source: str, workers: int = 4) -> dict:
    """Render every complete clip of one source."""
    base = root / "vision" / source
    archives = _logged_archives(base)
    started = time.time()
    rows, rejected, failed = [], [], {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_render_one, source, str(base), str(path)): path for path in archives}
        for i, future in enumerate(as_completed(futures), 1):
            path = futures[future]
            try:
                result = future.result()
            except Exception as error:  # one unreadable clip does not stop the others; it is listed
                failed[str(path.relative_to(base / "data"))] = str(error)
                continue
            (rejected if result["problems"] else rows).append(result)
            if i % 100 == 0:
                print(f"  {i}/{len(archives)} clips, {(time.time() - started) / 60:.1f} min", flush=True)
    rows.sort(key=lambda r: r["clip"])
    summary = {"source": source, "render_version": RENDER_VERSION, "clips": len(archives),
               "accepted": len(rows), "rejected": len(rejected), "failed": len(failed),
               "elapsed_seconds": round(time.time() - started, 1)}
    write_json(base / "rendered" / "manifest.json",
               {"summary": summary, "clips": rows, "rejected": rejected, "failed": failed})
    return summary


def render_tartanair(root: Path, workers: int = 4) -> dict:
    return render_source(root, "tartanair", workers)
