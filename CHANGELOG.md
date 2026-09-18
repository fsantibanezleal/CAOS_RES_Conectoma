# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog, newest on top.
Versions use the `X.XX.XXX` display form; the semver form (zeros dropped) appears in manifests.

## [0.04.001] - 2026-09-18

### Fixed

- The published site reported its explorer artifact as not verified. Served over plain HTTP (before the
  domain's certificate exists) the page is not a secure context, so WebCrypto is absent and the digest was
  never computed; a check that could not run was shown as a failure. The explorer now falls back to a plain
  SHA-256 (FIPS 180-4, tested against Node's on the standard vectors, every padding length up to 200 bytes
  and the committed artifact), so the check runs in every context. The fit gate removes WebCrypto in one
  run and requires the artifact to verify, because localhost is a secure context and could never show it.

## [0.04.000] - 2026-09-18

### Added

- The web base on the shared shell: six routes (App, Introduction, Methodology, Implementation, Experiments,
  Benchmark), English and Spanish, light and dark, the architecture modal with five bilingual diagrams that
  follow the theme, per-section references, and a document per route so deep links answer 200.
- The connectome explorer (App): every cell type of the right optic lobe, what it receives or sends through
  each partner drawn on the hexagonal lattice in the engine's frame, side by side with the published
  consensus where the pair exists, with the filters' cosine similarity and the angle between their
  directions; and the placement view, the network lattice beside a chart of every type's measured density
  against the placement rule. State lives in the URL.
- Contract 2 for the explorer: `run.py export-web` writes the compact artifact (1.2 MB) and a manifest with
  its size, SHA-256, the digests of its inputs and four counts, deterministic to the byte. A runtime
  validator in the web checks it in the build and again in the page; the pipeline's tests rebuild it and
  require the committed bytes.
- Experiments and Benchmark pages whose every number is read from the committed reports: the column
  holdout, the consensus comparison and its orientation, parity with the published model, the published
  ensemble's tuning by task rank, the frozen lattice and its controls, the whole visual system, the
  training cost; the task benchmark's protocol and metric definitions, stated as not yet run.
- The ADR-0071 fit gate on the built site: three sizes, both themes, both languages, the painted area of
  the instrument rather than its box, the rail, the tab rows, every documentation route and every
  architecture diagram. CI runs it, and the Pages deploy runs it before it uploads anything.
- Documentation: the web guide, contract 2 as built.

### Fixed

- The per-connection certainty was documented as a fraction of column pairs in [0, 1]. It is the number
  of connected cell pairs per placed target cell, averaged over the filter's entries, and exceeds 1 where
  two source cells share a column (118 of 7,907 connections, at most 2.4); the engine stores it and does
  not use it in the dynamics. The pipeline, the data contract, the construction and framework pages, the
  Methodology page and the explorer's readout now say that; no number changed.

## [0.03.000] - 2026-09-18

### Added

- The whole visual system as a neuron-level network (method M08): both optic lobes plus the visual projection
  and visual centrifugal neurons, 105,011 neurons in 695 cell types, 12,450,379 connections, every measured
  connection kept (a synapse cut is a recorded option). Signs per presynaptic neuron; column coordinates
  inferred per eye (holdout 99.89 percent exact on the right, 99.83 on the left). Written outside git (41 MB)
  with a committed summary and SHA-256.
- `NeuronConnectome` and `PhotoreceptorStimulus`, registered with the engine: the input is one value per
  placed photoreceptor, with its eye, column and type exported for the fly-eye renderer.
- The three regimes at neuron granularity (signs and counts per connection in every regime), sharing one
  starting point, with transfer from the published model.
- Loop gain: the spectral radius of the absolute weight matrix, computed per strongly connected component
  (dense for small components, implicitly restarted Arnoldi for large ones). The visual system is one
  recurrent component of 104,058 cells whose gain is 3.07 from the engine's initialisation (4.89 with
  published values); as built it runs away. Neuron-level networks are built with every strength scaled by
  one factor to a gain of 0.9, after which they settle and a flash reaches 92 to 99.7 percent of the LC and
  LPLC readouts, weakly. An R1 training step fits: 0.25 s and 2.8 GB at a batch of one.
- A settled criterion for stability (drift of at most one percent of the voltage scale in the last half
  second), because a finite but runaway network had passed the earlier check; the lattice report now records
  it and its loop gain (1.48, and 2.33 with published values: above one, and stable nonetheless).
- Documentation: the whole visual system page, the guide section for its commands.

## [0.02.000] - 2026-09-18

### Added

- The network: `LatticeConnectome`, an in-memory compiler registered with the network engine, identical to
  the engine's own compiler on the published connectome (45,669 cells, 1,513,231 connections, every table
  equal) and bound to the SHA-256 of its specification. On the MaleCNS right optic lobe: 253 cell types,
  40,051 cells, 2,922,900 connections, compiled in about three seconds.
- Target-centric filter expansion: every target cell receives its full measured filter whatever the
  sublattices of the two types (checked on 2,873 connections, largest relative error 6e-8), and population
  nodes that drive every cell of their targets. The engine's source-centric expansion loses entries between
  sublattices; on the published connectome it drops the Lawf1 self-connection, now reported by name.
- The three frozen regimes as engine configurations with one shared starting point: R0 reservoir (0
  trainable), R1 biophysical (8,409), R2 edge gain (3,003,002). A gradient check through the dynamics
  confirms every frozen parameter receives no gradient and every trainable one does.
- Transfer of the published model's trained parameters onto matching cell types, preserving the total
  drive onto a central cell (53 of 253 types, 388 of 7,903 type pairs).
- Null controls N1 (degree-preserving rewiring), N2 (size-matched random graph) and N3 (sign shuffle), pure
  functions of the specification and a seed, with their invariants tested. Rewiring and the random graph
  move connections only between types of the same placement, so every control compiles to exactly the
  measured 2,922,900 cell connections and 10,281,886 synapses; an unstratified first version produced a
  control with 3.3 times the synapses.
- Numpy-safe, atomic report writing and resumable run logs for the long runs, after a forty-minute run
  lost its results to a serialisation error at the very end.
- `parity-published`: the published model rebuilt through this path against the engine's own loader,
  voltage for voltage (largest difference 3.8e-6 over 113 million finite values per model on three
  models, NaN padding identical in both paths), a cross-check against
  the engine's own end-to-end tuning pipeline (identical on three models), and the motion tuning of the
  whole published ensemble: better-ranked models tune more T4/T5 subtypes as known (34 of 80 in the best
  ten, 14 of 80 in the worst ten, rank correlation -0.45), as published.
- `characterize-connectome`: stability, simulation cost, the cost of one training step per regime, and
  the motion tuning of the frozen MaleCNS network against the three null controls. Every network is stable;
  one training step costs 0.20 s and 2.6 GB in R1 or R2 (0.10 s for the published network), about 14 hours
  of network time at the published schedule; the frozen network has no direction selectivity from either
  starting point (edges barely reach T4 and T5 at the engine's initialisation; with the published values T4
  stays below threshold and T5 is driven but untuned), and neither do the controls.
- The orientation measure in the consensus comparison: filter directions compared under the twelve
  symmetries of the hexagonal lattice.
- Documentation: the network, its regimes and its controls (with two diagrams); the network-engine guide;
  the engine card rewritten around what the product uses and what it had to work around; the connectome
  specification in the data contracts.

### Changed

- The connectome is written in the engine's frame. The release's column axes point the opposite way from
  the engine's: as first built the identity scored -0.42 and the half-turn +0.42 over 98 filters. Offsets are
  now half-turned; the identity scores +0.37 over 108 filters and wins.
- Cell types are placed at their measured density (every column, a 2x2, 3x3 or 4x4 sublattice, or one
  population node below one cell per 20 columns). The earlier rule compared cell counts with the pooled
  outer photoreceptors, collapsed tiling populations of up to 494 cells to one node, and let 3,270 of 6,077
  connections vanish at compile time.
- The inner photoreceptors are pooled into R7 and R8, and placeholder types ("_unclear") are left out (108
  cells). Population nodes send the whole-pair average per target cell.
- The threshold sweep was re-run on the new build; the default is unchanged. Against the published
  consensus: 76.0 percent connection recovery, 97.1 percent sign agreement, rank correlation 0.80.

### Pins

- torch 2.14.0 and torchvision 0.29.0, pinned without a build tag (CPU wheel in CI, CUDA 12.6 on the GPU
  lane), flyvis 1.2.0, and datamate at upstream commit 3b9792c because its last release fails to compile a
  connectome on Windows.

## [0.01.000] - 2026-09-16

### Added

- Ingestion contract for the MaleCNS v1.0 tables: required columns, positive synapse counts, column
  coordinates in range, and an explicit policy that rejects with a reason and flags rather than coercing.
  A truncated download is rejected as an unreadable Arrow file, which is the failure this product hit
  while fetching the 1.1 GB connection table.
- Synapse signs from the neurotransmitter predictions, with the provenance of each call (per body, per cell
  type, or defaulted), the confidence, a flag for low-confidence calls, and a marker for the modulatory
  transmitters whose treatment as excitatory currents is a modelling choice rather than a measurement.
- Retinotopic column assignment by synapse-weighted median over placed partners, on compressed sparse row
  arrays, with holdout validation that re-infers each annotated cell type from the others and reports the
  error in lattice columns. The release annotates columns for 15 of the 282 optic-lobe cell types, so this
  is what makes the rest of the visual system usable.
- Connectome construction: average convolutional filters per ordered cell-type pair and column offset,
  written in the format the connectome-constrained network engine consumes directly, with a provenance
  block naming the dataset, its license, the citation and the exact configuration.
- Cross-platform fetch scripts for the connectome tables, resumable and size-verified.
- Documentation: connectome construction, the engine card for the network library, and the fetch guide.

## [0.00.000] - 2026-09-16

### Added

- Repository base instantiated from the CAOS product archetype: repository layout, both data-contract
  slots, CI guards (base integrity, template residue, content standards), community health files, MIT
  license, versioning from day one.
- Documentation skeleton for the wiki: what the product is, the lanes, the repository map, and the
  contracts the later units fill in.
- Repository-invariant tests: the archetype folder set exists, no heavy or private artifacts are tracked,
  the version sources agree.

### Notes

- The offline pipeline, the method ladder, the case matrix and the companion web are not present at this
  version. They arrive in the units listed in the README, each with code, tests and documentation in the
  same commit.
