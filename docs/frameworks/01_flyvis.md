# flyvis

## What it is

`flyvis` is the reference implementation of a connectome-constrained deep mechanistic network of the fly
visual system, published with Lappalainen, Tschopp, Prakhya, McGill, Nern, Shinomiya, Takemura, Gruntman,
Macke and Turaga, "Connectome-constrained networks predict neural activity across the fly visual system",
Nature, 2024, doi:10.1038/s41586-024-07939-3.

It supplies what this product would otherwise have to write: a connectome abstraction with a registration
hook for custom wiring, a compiler from average convolutional filters to a hexagonal lattice of neurons, a
threshold-linear simulator with the trainable biophysical parameters, ensembles, and the published trained
models.

- Repository: github.com/TuragaLab/flyvis, MIT.
- Distribution: `flyvis` on the Python package index, version 1.2.0 at the time of writing.
- Requires Python below 3.13, which is why the offline environment pins 3.12.

## Why it was chosen over writing one

The alternative was a product-specific engine. It was rejected deliberately: the published library already
carries the exact contract this product needs, it is maintained by the group that produced the method, and
re-implementing it would mean re-deriving a simulator whose numerical choices are part of the published
result. The decision and its reasoning are recorded in the management repository next to the plan.

## The contract this product uses

Three pieces of the library's public surface matter here.

1. **The connectome protocol.** `flyvis.connectome.Connectome` declares what a connectome must expose to
   the network: node indices, edge source and target indices, and per-edge attributes such as the synapse
   count. `register_connectome` adds a custom class to the available set, which is how the product's own
   compiler is plugged in.
2. **The average-filter format.** `ConnectomeFromAvgFilters(file, extent, n_syn_fill)` builds the lattice
   from a JSON specification of cell types and their filters. Each node declares a placement pattern; each
   edge declares `src`, `tar`, a sign, and `offsets`, a list pairing a column offset with a synapse count.
   The `extent` argument sets the radius of the lattice in columns, which is what lets the same measured
   filters be instantiated at the ethological size or at a denser one.
3. **The offset convention.** An offset is applied from the source: a target sits at
   `(u_source + du, v_source + dv)`. The construction code here computes `du = u_target - u_source` to
   match, and the per-connection `lambda_mult` field is the synapse-count certainty the engine carries
   through to the edge.

## How it is used here

The connectome construction step writes `data/derived/connectome/malecns-optic-lobe-<side>.json` in the
average-filter format. From there the product uses the engine as follows (details in
[architecture/03](../architecture/03_network-and-regimes.md)):

| Engine piece | Used for | What the product adds or changes |
|---|---|---|
| `register_connectome` and the connectome protocol | plugging in the product's compiler, `LatticeConnectome` | an in-memory compiler, content-addressed by SHA-256, with target-centric expansion and population nodes; identical to the engine's compiler on the published connectome |
| `Network`, `PPNeuronIGRSynapses` | the dynamics, unchanged | the three regimes are expressed purely as parameter configurations (grouping and `requires_grad`) |
| `RestingPotential`, `TimeConstant`, `SynapseSign`, `SynapseCount`, `SynapseCountScaling` | every parameter of every regime | synapse counts grouped per connection by default (see below) |
| `NetworkView`, `recover_network` | loading the published ensemble | the published checkpoint is also loaded through the product's own builder, for the parity check |
| `MovingEdge`, `direction_selectivity_index`, `preferred_direction` | the motion-tuning characterisation | nothing: the stimulus and the analysis are the engine's, so the numbers mean what the published ones mean |

## Pins, and why each one

| Package | Pin | Why |
|---|---|---|
| `flyvis` | 1.2.0 | the published engine |
| `torch`, `torchvision` | 2.14.0, 0.29.0 (the CUDA 12.6 build on a GPU machine, the CPU build elsewhere) | pinned without a build tag so both builds satisfy the same requirement |
| `datamate` | upstream commit `3b9792c` (2026-02-27) | the engine's storage layer. Its last release, 1.0.0, deletes an HDF5 file while its own handle is still open, which works on Linux and fails on Windows the first time a connectome is compiled. The fix is on the upstream main branch and unreleased. |

## Behaviour worth knowing before using it

Each of these was found while building this unit, and each is handled in `conectoma/network/engine.py` or
`lattice.py` rather than left to chance:

- **The storage root is fixed at import.** The engine reads `FLYVIS_ROOT_DIR` once, when first imported,
  and otherwise stores downloads inside the installed package. The product sets it from its models root
  before importing and refuses to continue if the engine was imported earlier with another root.
- **Importing the engine sets torch's default device** to the GPU when one is present. Every tensor created
  afterwards lands there unless placed explicitly.
- **Compiled connectomes are cached by path, not content.** A rebuilt specification at the same path loads
  the previous graph from the cache. The product's compiler does not use that cache.
- **Parameter sharing is built with a Python loop** over every neuron or connection
  (`get_scatter_indices`). At three million connections that loop is most of the time a network takes to
  build (15 seconds for one parameter). The product replaces it, at import, with a hash join that returns
  identical indices (checked against the original in the tests, 20 to 36 times faster).
- **The source-centric expansion loses entries between sublattices.** Exact when every type is on every
  column; for the published connectome it drops one connection (Lawf1 onto itself, one synapse). The
  product's target-centric expansion is used for the MaleCNS connectome.
- **One synapse count per type pair and offset** is the engine's default grouping. It is exact for a
  graph where every type is on every column and averages different counts together otherwise; the product
  groups counts per connection and uses the published grouping only to load published checkpoints.
- **A registered connectome class is keyed by its class name**, whatever name is passed; the product's is
  `LatticeConnectome`.

## Caveats

- The published consensus connectome shipped with the library comes from earlier volumes of the medulla
  (the FIB-25 and FIB-19 reconstructions) and covers 64 cell types. The connectome built here comes from
  the newer whole-nervous-system release and covers a different, larger set, so the two are compared rather
  than assumed equivalent.
- The library's own parameter initialisation is tuned to its shipped connectome. On the MaleCNS connectome
  it is used as one of two starting points, next to values transferred from the published model, and the
  stability of both is measured rather than assumed.
