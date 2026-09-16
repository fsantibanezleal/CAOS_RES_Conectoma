# data/, layout and the ingestion contract

## Layout

| Path | What | Git |
|---|---|---|
| `raw/` | local cache of the connectome tables and the vision datasets | git-ignored, never committed |
| `derived/<case>/` | compact artifacts the web replays | committed |
| `derived/manifests/` | per-case manifest (contract 2) plus the flat index | committed |

Heavy inputs live outside the repository, in a local vault, and are reproduced from the documented fetch
commands rather than stored in git. The connectome tables alone are roughly 14 GB for the subset this
product needs.

## Sources and their terms

| Source | What is used | Terms |
|---|---|---|
| Janelia MaleCNS v1.0 (`male-cns:v1.0`) | body annotations, neurotransmitter predictions, connection weights, synapse positions | CC-BY; cite the Cell 2026 paper |
| TartanAir | RGB, depth, optical flow, semantic segmentation, camera poses | CC BY 4.0 |
| Spring | stereo, disparity, optical flow | CC BY 4.0 |
| Hypersim | photorealistic indoor RGB, depth, semantic and instance labels | CC BY-SA 3.0; derived artifacts inherit ShareAlike |
| MPI Sintel | RGB, optical flow, depth | terms verified before use in the unit that adds it |
| FlyGym renders | fly-eye renderings generated locally | Apache-2.0 tooling, outputs generated here |

Nothing licensed for cite-only is re-hosted. Derived artifacts carry the terms of the source they came
from, recorded in the manifest.

## The ingestion contract

Declared in code with the pipeline, documented here as it lands, and summarized in
`docs/architecture/08_data-contracts.md`. It covers the connectome tables and the vision sequences,
rejects malformed rows with a reason, and flags plausible-but-suspicious ones so the flag reaches the
manifest.
