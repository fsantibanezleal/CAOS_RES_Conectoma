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
2. **Vision clips** (`data-pipeline/conectoma/vision/contract.py`, design in
   [05](05_vision-data.md)): every clip rendered onto the 721-column lattice is checked before anything
   reads it, and a clip that fails is rejected with its reasons, never repaired.

### Vision clips, as enforced

Every source must carry luminance, depth and frame numbers; each declares what else it must carry:

| Source | Required beyond luminance, depth and frames |
|---|---|
| TartanAir | flow, flow validity, segment boundaries, camera poses |
| Spring | sky share, independent-motion share |
| Hypersim | segment boundaries, figure share, labelled share, NYU40 label |
| Sintel | flow |
| FlyGym | figure share |
| synthetic (and the panorama and still-camera cases) | flow, flow validity |

| Array | Shape | Rule |
|---|---|---|
| `lum` | (frames, 721) | finite, in [0, 1] |
| `depth` | (frames, 721) | positive where known; NaN where masked (counted, never dropped); never zero, negative or infinite |
| `flow` | (frames - 1, 2, 721) | finite; the engine's unit (per image height, y up, summed over the box); row t is the motion from frame t to t + 1 |
| `flow_valid`, `moving` | (frames - 1, 721) | shares in [0, 1] |
| `sky`, `figure`, `labelled` | (frames, 721) | shares in [0, 1] |
| `boundary` | (frames, 721) | 0 or 1 |
| `semantic` | (frames, 721) | NYU40 ids, 0 for unlabelled |
| `poses` | (frames, 7) | finite; rotations are unit quaternions |
| `frames` | (frames,) | consecutive for video sources, never repeated |

Optional arrays that are present are checked all the same. Each rendering is listed in its source's
manifest with its statistics and SHA-256, and each rejection with its reasons; `tests/test_vision_data.py`
builds clips that break each rule.

The connectome part of the contract is documented in `data/README.md`. The whole contract is what lets a
third party run this on their own footage instead of only replaying the baked cases.

## Between the two: the connectome specification

The connectome the build writes (`data/derived/connectome/malecns-optic-lobe-<side>.json`) is the input of
every network, so its format is fixed and checked (`tests/test_connectome_integration.py`,
`tests/test_placement.py`). It is the engine's average-filter format with a few fields added:

| Field | Type | Meaning |
|---|---|---|
| `nodes[].name` | string | cell type, unique |
| `nodes[].pattern` | `["stride", [k, k]]` or `["single", null]` | placement on the hexagonal lattice: every k-th column along both axes, or one population node at the centre |
| `nodes[].n_cells`, `n_cells_placed`, `density` | integers, float | cells of the type in the selection, those with a column, and placed cells per column |
| `edges[].src`, `tar` | string | presynaptic and postsynaptic cell type |
| `edges[].offsets` | list of `[[du, dv], synapses]` | the average filter: synapses a target cell receives from source cells at column offset `(du, dv)`; for a population source, one entry at `[0, 0]` holding the whole-pair average per target cell |
| `edges[].alpha` | -1 or 1 | sign of the presynaptic type |
| `edges[].lambda_mult` | positive float | support: connected source-target cell pairs per placed target cell, averaged over the filter entries (for a population source, the share of target cells reached); above 1 where two source cells share a column; stored by the engine, not used in the dynamics |
| `input_units`, `output_units` | lists of types | photoreceptor inputs (each must be placed on every column) and the readout types |
| `compile.target_centric` | boolean | expand each filter from its targets, so every target cell receives its full filter |
| `compile.population_broadcast` | boolean | a population node drives every cell of each target type |
| `provenance` | object | dataset, license, citation, sign source, configuration, column assignment and its holdout, placement summary |

A reader that ignores the `compile` block (the engine's own compiler, for example) still accepts the file
and builds a network from it, but a different one: exact between types placed on every column, missing the
entries between sublattices, and reaching only one target cell from each population node. The product's
compiler reads the block, and every network it builds records the SHA-256 of the file.

Synapse counts are averages, so they are positive reals, not integers. A zero or negative count never
appears: an entry below the threshold is dropped, not written as zero.

## Contract 2, artifact (pipeline to web)

The web loads only artifacts with a manifest, and every field it reads is checked three times: by the
pipeline's tests, which rebuild the artifact from its committed inputs and require the same bytes; by the
web build, which validates the committed files against a TypeScript mirror (`frontend/src/lib/contract.ts`)
and fails on the first field that drifted; and by the page, which validates what it received before showing
it and compares its SHA-256 with the manifest's.

### The explorer artifact (today)

Written by `run.py export-web` (`data-pipeline/conectoma/stages/export_web.py`), version 1.

| Field | Type | Meaning |
|---|---|---|
| `types[]` | object | `name` (unique), `pattern` (as in the specification), `group` (input, output, stride1 to stride4, population), `density`, `cells`, `cells_placed`, `sign` (+1, -1, or 0 for a type that sends nothing here), `photoreceptor` |
| `connection_fields` | list | exactly `source, target, sign, certainty, du, dv, synapses`, the order of each row below |
| `connections[]` | 7-field row | type indices of source and target, the sign, the support (`lambda_mult` of the specification: positive, above 1 where two source cells share a column), and the filter as three parallel arrays of equal length: integer offsets `du`, `dv` in the engine frame and positive synapses per target cell |
| `published[]` | object | a filter of the published consensus whose pair exists here after the cross-release renames: `src`, `tar`, `matches` (the MaleCNS pairs it corresponds to), `sign`, `du`, `dv`, `n` |
| `frame`, `placement`, `compile` | object or null | copied from the specification: the offset frame (`release_to_engine`), the placement summary, the compile rules |

The manifest (`data/derived/manifests/explorer.json`) records the artifact's relative path, byte size and
SHA-256; the file name and SHA-256 of the specification it came from, with the dataset, license and
citation; the file, SHA-256 and license of the published reference; and four counts (types, connections,
filter entries, published connections), which the web compares with what it received. It has no timestamp,
so the same inputs give the same bytes.

### The per-case artifacts (with the method units)

Every canonical run of a vision method will write a compact artifact plus a manifest recording: the case
and variant, the method, the seeds, the engine and its version, the license of any checkpoint used, the
measured lane verdict with its numbers, the contract-1 flags, the evaluation metrics, and the byte size of
the artifact. A flat index will inventory every case, under the same three checks.

## Why the sign is part of the contract

Synapse sign comes from a neurotransmitter classifier, reported at 87 percent accuracy per synapse and 94
percent per neuron (Eckstein et al., Cell, 2024, doi:10.1016/j.cell.2024.03.016). It is therefore an input
with a known error rate, not a ground truth: the manifest records the confidence and the sign-shuffled
control exists to measure how much the result depends on it.
