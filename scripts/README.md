# scripts/

Cross-platform helpers, always in both shells, and the guards CI runs.

| Script | What it does |
|---|---|
| `setup.sh` / `setup.ps1` | create the environments and install the pinned requirements; idempotent |
| `dev.sh` / `dev.ps1` | run the local development surface once the frontend exists |

## Guards

| Script | What it enforces |
|---|---|
| `check_template_residue.py` | no archetype example code or placeholder text survives in this product |
| `check_content_standards.py` | no em-dash and no pictographic emoji in tracked content |

Fetch, precompute and artifact-validation scripts are added by the units that create the pipeline they
drive, so every script in this folder runs something that exists.
