# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog, newest on top.
Versions use the `X.XX.XXX` display form; the semver form (zeros dropped) appears in manifests.

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
