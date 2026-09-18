"""A resumable record of a long run: every finished step is on disk before the next one starts.

A run that simulates fifty models or fifteen null controls takes most of an hour. Its steps are independent,
so a crash, a killed process or a reboot should cost the step in progress, not the run. Each step is stored
under a key as soon as it finishes; running the same command again reuses the steps whose key is present
and computes the rest.

A log is only valid for the inputs it was computed from. Its `signature` (the specification digest, the
stimulus configuration, anything that changes a result) is stored with it, and a log whose signature
differs is set aside rather than reused, so a stale step can never enter a new report.
"""

from __future__ import annotations

import json
from pathlib import Path

from conectoma.core.jsonio import dumps, write_json


class RunLog:
    def __init__(self, path: Path, signature: dict):
        self.path = Path(path)
        self.signature = json.loads(dumps(signature, indent=None))
        self.steps: dict = {}
        self.reused: list[str] = []
        if self.path.is_file():
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            if stored.get("signature") == self.signature:
                self.steps = stored.get("steps", {})
            else:
                self.path.replace(self.path.with_name(self.path.name + ".stale"))

    def __contains__(self, key: str) -> bool:
        return key in self.steps

    def get(self, key: str):
        self.reused.append(key)
        return self.steps[key]

    def put(self, key: str, value) -> None:
        self.steps[key] = json.loads(dumps(value, indent=None))
        write_json(self.path, {"signature": self.signature, "steps": self.steps}, indent=None)

    def step(self, key: str, compute):
        """The stored result of `key`, or `compute()` stored under it."""
        if key in self:
            return self.get(key)
        value = compute()
        self.put(key, value)
        return self.steps[key]
