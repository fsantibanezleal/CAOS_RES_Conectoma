# The two data contracts

Both contracts are enforced in code and checked in CI. Without the first, the product cannot be pointed at
new data and is a demo; without the second, the web can drift from what the pipeline produced.

## Contract 1, ingestion (raw to pipeline)

Two families of input cross this boundary, and each declares its schema, units, ranges and an explicit
outlier policy:

1. **Connectome tables** (Janelia MaleCNS v1.0, Apache Arrow Feather, fetched into the git-ignored cache):
   body annotations (type, class, side), per-body neurotransmitter predictions, the segment-to-segment
   connection table, and synapse positions in 8 nm voxel units. Rejected rows are rejected with a reason,
   never silently coerced; low-confidence neurotransmitter calls are flagged and the flag travels into the
   manifest, because the sign of a connection is itself a prediction.
2. **Vision sequences**: frames with camera intrinsics and poses, plus the ground truth a case declares
   (depth in metres, optical flow in pixels, segmentation labels). A sequence is accepted only if the
   declared ground truth is present and finite, and if its units match the declared ones.

The contract lives with the pipeline and is documented in `data/README.md`. It is what lets a third party
run this on their own footage instead of only replaying the baked cases.

## Contract 2, artifact (pipeline to web)

Every canonical run writes a compact artifact plus a manifest recording: the case and variant, the method,
the seeds, the engine and its version, the license of any checkpoint used, the measured lane verdict with
its numbers, the contract-1 flags, the evaluation metrics, and the byte size of the artifact. A flat index
inventories every case. The web loads only these files, and a TypeScript mirror of the manifest schema
makes any drift fail the web build.

## Why the sign is part of the contract

Synapse sign comes from a neurotransmitter classifier, reported at 87 percent accuracy per synapse and 94
percent per neuron (Eckstein et al., Cell, 2024, doi:10.1016/j.cell.2024.03.016). It is therefore an input
with a known error rate, not a ground truth: the manifest records the confidence and the sign-shuffled
control exists to measure how much the result depends on it.
