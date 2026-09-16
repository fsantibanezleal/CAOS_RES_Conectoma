# Fetch the connectome

The MaleCNS tables are public and need no credentials. They are large, so they live in a local cache
outside the repository and are never committed.

## Where the cache lives

Set `CONECTOMA_DATA_ROOT` to a directory on a disk with room to spare, for example a dedicated data volume.
The pipeline reads `$CONECTOMA_DATA_ROOT/malecns/`.

## What to fetch, and why

| File | Size | Needed for |
|---|---|---|
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 14 MB | cell type, side, superclass, and the annotated column coordinates |
| `body-neurotransmitters-male-cns-v1.0.feather` | 43 MB | the neurotransmitter call per neuron and per cell type, with confidence |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 1.1 GB | the synapse count of every ordered pair of neurons |
| `syn-points-male-cns-v1.0-minconf-0.5.feather` | 12.7 GB | optional: synapse positions, used by the geometric cross-check of column assignment |

```bash
./scripts/fetch-data.sh              # or scripts/fetch-data.ps1 on Windows PowerShell
./scripts/fetch-data.sh --with-synapse-points   # adds the 12.7 GB positions file
```

The script resumes a partial download and verifies the size against the server before reporting success. A
truncated file is the failure this product has already hit once: the ingestion contract rejects it with
"not a readable Arrow file" rather than building a connectome from half a table.

## Build the connectome

```bash
python data-pipeline/run.py build-connectome            # right optic lobe, the default
python data-pipeline/run.py build-connectome --side L   # the left one
```

The run prints its stages, writes the connectome and its report under `data/derived/connectome/`, and takes
a few minutes, most of it in the holdout validation of the column assignment.

## Terms

The dataset is CC-BY. Cite the Cell 2026 paper of Berg and colleagues when reusing anything derived from
it; the citation travels inside the artifact's provenance block so it cannot be separated from the data.
