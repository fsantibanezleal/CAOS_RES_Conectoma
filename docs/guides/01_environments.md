# Environments

Two isolated environments, never a global interpreter.

| Environment | Purpose | Installed from |
|---|---|---|
| `.venv` | linting, tests, repository tooling | `requirements-dev.txt` |
| `.venv-pipeline` | the offline lane: connectome ingestion, network construction, training, inference, evaluation | `requirements-precompute.txt`, plus `requirements-gpu.txt` on a CUDA machine |

## Python 3.12, deliberately

The offline lane depends on `flyvis`, whose published metadata declares `requires-python >=3.9,<3.13`. The
pipeline environment therefore pins Python 3.12 even though 3.13 is the newer default elsewhere.

## A fresh clone

```bash
./scripts/setup.sh          # or scripts/setup.ps1 on Windows PowerShell
python -m pytest            # repository invariants
ruff check .
```

The pipeline commands are documented by the units that add them, alongside the stages they run.

## What runs where

The test suite runs locally and is the validation of record: CI installs no offline lane, runs no test
suite and regenerates no artifact (ADR-0074). Run `python -m pytest` before every push. CI then repeats
only the cheap checks on what was committed: `ruff`, `scripts/check_artifacts.py` (the manifests, the
digests and the split table), the base-integrity guards, and the web build with the ADR-0071 fit gate,
which runs there and not again in the deploy.
