# data-pipeline/, the offline engine

Plain scripts, invoked by path. This product declares no package of its own: the connectome-constrained
network engine it consumes is `flyvis` (PyPI, MIT), and the product-specific stages live here.

Its own environment is `.venv-pipeline` (Python 3.12, see `docs/guides/01_environments.md`).

## Planned layout, added by the units that build each part

- `conectoma/io/`: the ingestion contract for the connectome tables and the vision sequences
- `conectoma/core/`: seeded determinism, the artifact and manifest schemas, the measured live gate
- `conectoma/connectome/`: MaleCNS subgraph selection, retinotopy, consensus filters, sign assignment,
  export to the flyvis connectome format, and the null-model generators
- `conectoma/stages/`: preprocess, dataset and splits, features, train, infer, evaluate, export, validate
- `conectoma/cases/`: one module per case, grouped by category
