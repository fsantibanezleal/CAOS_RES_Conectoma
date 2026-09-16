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
   count. `register_connectome` adds a custom class to the available set, which is how the non-periodic
   whole-visual-system variant is plugged in.
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

The connectome construction step writes `data/derived/connectome/malecns-optic-lobe-<side>.json` in exactly
that format, so the engine consumes this product's output with no adapter. The next unit builds the three
frozen regimes on top of the compiled network and reproduces the published model as a parity check.

## Caveats

- The published consensus connectome shipped with the library comes from earlier volumes of the medulla
  (the FIB-25 and FIB-19 reconstructions) and covers 64 cell types. The connectome built here comes from
  the newer whole-nervous-system release and covers a different, larger set, so the two are compared rather
  than assumed equivalent.
- The library's own parameter initialisation is tuned to its shipped connectome. Any number taken from the
  paper (a time constant, a resting potential, a scale) is recorded where it is used rather than silently
  inherited.
