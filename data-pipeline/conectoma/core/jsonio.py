"""JSON written the same way everywhere: numpy values made plain, and never half a file on disk.

Two failures motivate this module. A report assembled from engine objects carries numpy scalars (a stimulus
speed is a `numpy.float64`, an angle a `numpy.int64`), which the standard encoder refuses, and the refusal
came after forty minutes of simulation whose results were only in memory. And a process killed while
writing leaves a truncated file that later reads as corrupt. Every report and every run log goes through
`write_json`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def plain(value):
    """The JSON-native equivalent of a numpy scalar or array, a path, or a set."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is part of every lane that writes reports
        np = None
    if np is not None:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def dumps(value, indent: int | None = 1) -> str:
    return json.dumps(value, indent=indent, default=plain)


def write_json(path: Path, value, indent: int | None = 1) -> Path:
    """Serialise first, then replace the file in one step, so a failure leaves the previous file intact."""
    path = Path(path)
    text = dumps(value, indent=indent) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    return path
