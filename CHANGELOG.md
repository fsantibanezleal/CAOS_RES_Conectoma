# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog, newest on top.
Versions use the `X.XX.XXX` display form; the semver form (zeros dropped) appears in manifests.

## [0.06.000] - 2026-09-22

### Added

- The first four methods (U5), each consuming what the eye receives unless it says otherwise, and each
  scored by one stage on the same clips. **M01**, depth from motion parallax: a sweep along each column's
  epipolar line, because the corpus's columns move 39 pixels between frames at the median and 96 at the
  ninth decile, three and seven lattice steps, far beyond a differential estimator's capture range; then a
  two-dimensional refinement whose deviation from that line finds independently moving objects without
  knowing any depth. **M02**, semi-global matching on the TartanAir stereo pair (baseline 0.25 m, verified
  at the source), labelled an upper bound everywhere because it consumes a full pixel grid from two
  cameras. **M03**, the Hassenstein-Reichardt correlator on the lattice, pooled over neighbours and
  calibrated on a synthetic set of its own. **M04**, the published fifty-model ensemble, frozen, with the
  flow decoder it was trained with, read through the same inversion as M01.
- The readout every motion method shares: the exact decomposition of Longuet-Higgins and Prazdny (1980)
  from the committed poses, the baseline each column has across its line of sight (which makes the
  uncertainty grow with the square of depth and makes pure rotation and the focus of expansion
  unanswerable), and the epipolar deviation that tests rigidity without a depth.
- The stage that scores a method, with the metrics defined in one place and their conventions stated:
  coverage beside every number, RMSE in metres only where the source is metric, the scale-invariant error
  transcribed from section 3.2 of Eigen et al. 2014 with lambda 1 in log units. A case where depth cannot
  be observed is graded by what the method REFUSED. Comparisons are paired on the clip and bootstrapped
  over clips. A clip a method cannot run on is reported as skipped with the reason.
- The floor: the flow the corpus committed, put through the same readout. It recovers the committed depth
  to 0.9 percent over 88 percent of columns, so the arithmetic after the flow costs almost nothing and a
  method's distance from the floor is the part of the error it owns.
- A Methods tab on Experiments reading a compact projection of the reports, stating what each row IS
  beside every number, and the case pages for the four methods in `docs/methods/`.

### Found

- **Paired against the floor in AbsRel**, over every case and level: M02 +0.004 [0.000, 0.008], M01 +0.265
  [0.239, 0.280], M04 +0.894 [0.865, 0.957], M03 +0.898 [0.852, 0.982]. The published network, used as a
  metric flow source outside the frame rate and scene statistics it was trained on, lands inside the
  interval of an untrained correlator with one fitted gain.
- The corpus records PLANAR depth while the readout was first written to solve for distance along the ray,
  which inflates every off-axis column by up to 1.41 at the corner of the lattice. The synthetic control
  caught it before any number was published.
- A gradient read over a 13-pixel lattice step under-reads the slope: one linear solve returned a velocity
  12 to 24 percent too large. The estimator refines by warping with the interpolant's own gradient, and
  interpolates at the columns' real (truncated) pixel positions, where a column now returns its own value
  to 1e-16 rather than to 2.3e-2.
- A single column's correlator response fits nothing: one gain from it explains less than the mean does
  (r2 -0.14). Pooled over neighbours it fits (r2 0.33, 0.50, 0.60 after one, two and three rings), which
  is what the fly's wide-field cells do, at the cost of a depth smoothed over that neighbourhood. The gain
  fitted at one contrast is more than three times wrong at another.
- Below about a fifth of a lattice step a displacement is read too small and its depth too large: a plane
  at 8 m with a 0.1 m baseline moves 2.7 pixels and comes back at 10.9 m. The reported uncertainty uses a
  flow noise of 0.8 pixels and predicts that error.

### Changed

- The right camera of the 48 TartanAir clips the cases draw is fetched by `run.py fetch-stereo` (0.87 GB,
  nothing committed), and a synthetic or panorama case now declares its camera motion in the registry
  rather than carrying poses, with a test that checks each declaration against the flow that case's own
  rendering committed.

## [0.05.000] - 2026-09-22

### Added

- The vision data (U4). Six sources, each used only for what it can grade: TartanAir V2 (2,244 clips of 32
  frames from all 74 environments and both difficulties, 114.5 GB, fetched member by member over HTTP
  ranges with every member checked by its CRC32), its 360 degree panoramas, MPI Sintel through the engine's
  own downloader, Spring, Hypersim's official test partition, and FlyGym 2.1.0 for the fly's own compound
  eye. `fetch-vision`, `render-vision`, `build-splits`, `build-cases`, `export-eyeclips`,
  `summarize-vision` and `case-docs`.
- One geometry for every planar source: frames resized to 436 rows and the lattice on the central 391 x 391
  pixels, the engine's box rules, checked against its box eye and, on the held-out Sintel sequences, against
  its own rendering (luminance 1e-6, depth 1e-6 relative, flow 1e-4). FlyGym's 721 ommatidia placed on the
  engine's lattice by a measured symmetry, with depth as range and figure per ommatidium.
- Contract 1 for vision clips: what each source must carry, shapes, ranges and units, masked depth counted
  and never dropped; every rendering checked, rejections listed with their reasons.
- Splits by geometry family, not by name, with the leakage gate on families, environments and identical
  frames: 2,239 of the 2,244 TartanAir clips accepted and 5 rejected (every column the same luminance: the camera saw nothing), 60 families over the 74 environments split 38 / 6 / 6 / 10 into train, validation, calibration and test (1,437 / 196 / 227 / 379 clips), 71,648 frames hashed, no leakage.
- Sixteen cases in six categories, each one physical quantity over six levels with units, the same clips at
  every level, test data only: ego speed, illumination, field of view, photon noise per column, exposure
  blur, fog with its visibility, contrast, sampling, a gap between catwalks, a looming disk, a small target,
  pure rotation from panoramas, a still camera, textured planes and textureless surfaces. 126 distinct clips, 756 renderings, every one accepted. One
  page per case, its measured table generated from the committed summary and held to it by a test.
- The App's second mode, the eye's input: what the 721 columns receive in every case, level by level and
  frame by frame, beside the ground truth the case grades; all six levels side by side; the time course
  (uPlot). One compact file per case (contract 2), verified against its manifest before it is drawn.
- Experiments: the vision data (sources, the angle a column spans per source, the splits and the leakage
  gate) and the cases. Methodology: the vision data and the cases. The Implementation page, the
  Introduction and the architecture modal describe the vision lane. Seven citations checked on Crossref.
- Documentation: architecture 05 (the vision data), guide 05, the OpenCV and FlyGym framework cards, the
  case index and sixteen case pages, contract 1 as enforced, two diagrams.
- The fit gate covers the eye mode at every size, theme and language (every lattice canvas must hold a
  picture), and loads all sixteen cases.

### Found

- The published model learned at 0.23 to 1.29 degrees per column (Sintel, median 0.83), 3 to 18 times finer
  than FlyGym's model of the fly's eye (4.24); TartanAir's wide lens (3.42) is the planar source closest to
  it. Every case records its column spacing.
- TartanAir's depth saturates at float16's maximum (masked); some of its skies are domes kilometres away
  (kept, so depth metrics cap their range). Hypersim's semantic labels are incomplete in 20 of its 46 test
  scenes, so C04 draws only annotated, cluttered rooms. Spring's frame rate is not published anywhere
  reachable, and no case depends on it.

### Changed

- CI and CD are cheap checks on the committed files (ADR-0074). CI installed torch and the offline lane
  and ran the full test suite on every push and every pull request, and the fit gate ran twice, in CI and
  again in the deploy. The suite now runs locally, where the data and the GPU are, and is the validation
  of record; CI runs ruff, the contract 2 check, the base-integrity guards and the web build with the fit
  gate once, on pushes to develop and main only, every workflow with a concurrency group and every job
  with a timeout.
- `scripts/check_artifacts.py` (standard library only) checks the bytes and the SHA-256 of every file the
  two manifests declare, the digests that tie the explorer to its connectome specification and the eye
  clips to cases.json, and re-derives the split conditions from the committed table row by row.
  `scripts/check_ci_budget.py` holds the workflows to ADR-0074, and the repository invariants run both
  locally, so a workflow that regresses fails before the push.

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
