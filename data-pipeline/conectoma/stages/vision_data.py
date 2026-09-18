"""Stage: fetch the vision sources into the data root, one environment at a time, resumably.

Everything lands under `<CONECTOMA_DATA_ROOT>/vision/<source>/`, which is never committed. Each environment
leaves a report (planned clips, members missing from an archive, members that failed their CRC32 check,
bytes written), and the whole run leaves a summary with the digest of the configuration it followed.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import yaml

from conectoma.core.jsonio import write_json
from conectoma.vision import tartanair

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
VISION_CONFIG = CONFIG_DIR / "vision.yaml"


def load_config(path: Path = VISION_CONFIG) -> tuple[dict, str]:
    """The vision configuration and the SHA-256 of its bytes."""
    data = path.read_bytes()
    return yaml.safe_load(data), hashlib.sha256(data).hexdigest()


def fetch_tartanair(root: Path, environments: list[str] | None = None, workers: int = 12) -> dict:
    config, digest = load_config()
    source = config["tartanair"]
    index = tartanair.read_index(CONFIG_DIR / source["index"])
    pairs = sorted({(env, diff) for env, diff, _, _ in index if diff in source["difficulties"]})
    if environments:
        pairs = [p for p in pairs if p[0] in set(environments)]
    base = root / "vision" / "tartanair"
    log = tartanair.FetchLog(base / "fetch-log.jsonl")
    started = time.time()
    summary = {"config_sha256": digest, "environments": len({e for e, _ in pairs}), "pairs": len(pairs),
               "clips": 0, "bytes": 0, "failed": 0, "missing": 0, "reports": []}
    for environment, difficulty in pairs:
        report_path = base / "reports" / f"{environment}_{difficulty}.json"
        report = tartanair.fetch_environment(source, environment, difficulty, base / "data", log, workers)
        write_json(report_path, report)
        summary["clips"] += len(report["clips"])
        summary["bytes"] += report["bytes"]
        summary["failed"] += len(report["failed"])
        summary["missing"] += len(report["missing"])
        summary["reports"].append(str(report_path.relative_to(base)))
        print(f"{environment} {difficulty}: {len(report['clips'])} clips ({report['skipped']} already done), "
              f"{report['bytes'] / 1e9:.2f} GB, "
              f"{len(report['failed'])} failed, elapsed {(time.time() - started) / 60:.1f} min", flush=True)
    log.close()
    summary["elapsed_seconds"] = round(time.time() - started, 1)
    write_json(base / "fetch-summary.json", summary)
    return summary


def fetch_sintel() -> dict:
    """Sintel through the engine's own downloader (training frames, flow, and the separate depth archive),
    then the engine's own lattice rendering of it, which is the reference the product's renderer must match.
    """
    from conectoma.network.engine import load_engine

    flyvis = load_engine()
    from flyvis.datasets.sintel import RenderedSintel
    from flyvis.datasets.sintel_utils import download_sintel

    started = time.time()
    path = download_sintel(depth=True)
    rendered = RenderedSintel(tasks=["flow", "depth"])
    sequences = sorted(rendered)
    summary = {"sintel_dir": str(path), "rendered_dir": str(rendered.path),
               "rendered_sequences": len(sequences), "engine": flyvis.__version__,
               "elapsed_seconds": round(time.time() - started, 1)}
    write_json(Path(flyvis.renderings_dir) / "conectoma-sintel-summary.json", summary)
    return summary

