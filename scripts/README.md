# scripts/

Cross-platform helpers, always in both shells, and the guards CI runs.

| Script | What it does |
|---|---|
| `setup.sh` / `setup.ps1` | create the environments and install the pinned requirements; idempotent |
| `dev.sh` / `dev.ps1` | run the local development surface once the frontend exists |
| `fetch-data.sh` / `fetch-data.ps1` | fetch the vision sources into the git-ignored data root |

## Guards

| Script | What it enforces |
|---|---|
| `check_template_residue.py` | no archetype example code or placeholder text survives in this product |
| `check_content_standards.py` | no em-dash and no pictographic emoji in tracked content |
| `check_artifacts.py` | contract 2: every manifest matches the bytes and the digest of the artifact it describes, and the provenance digests match the inputs on disk (stdlib) |
| `check_ci_budget.py` | ADR-0074: no workflow trains, installs the training stack or runs the test suite; triggers are trunk only; every workflow has a concurrency group and every job a timeout |

Every script here runs against something that exists: the guards read the committed artifacts and the
workflows, and the fetch script drives the pipeline command of the unit that introduced it.
