# Conectoma, the wiki

This wiki is written as the product is built, unit by unit, never afterwards. A page exists when the thing
it documents exists. The offline repository and its evidence are the product; the web workbench is a
projection of an audited subset of it.

## Map

- **[architecture/](architecture/)**, how the repository works: the lanes, the two data contracts, the
  determinism rules, the live-versus-precompute gate, the staged pipeline, evaluation and deploy.
- **[frameworks/](frameworks/)**, one card per engine the product actually runs (what it is, why it was
  chosen, the exact pins, how it is used here, its license). Added as each engine lands.
- **[methods/](methods.md)**, one page per method the product runs: what it consumes, what it refuses,
  and what it measured, with its reference.
- **[cases/](cases/)**, the category taxonomy, the coverage matrix and one page per case.
- **[guides/](guides/)**, runnable how-tos: environments, the pipeline, bringing your own data, the GPU
  lane, the dormant API.

## Where the science comes from

Two published results anchor this work and are transcribed, with their equations and sources, in the pages
that use them:

- The connectome release: Berg, Beckett, Costa, Schlegel, Januszewski and colleagues, "Sexual dimorphism in
  the complete connectome of the Drosophila male central nervous system", Cell, 2026. Dataset
  `male-cns:v1.0`, CC-BY.
- The method this product generalizes: Lappalainen, Tschopp, Prakhya, McGill, Nern, Shinomiya, Takemura,
  Gruntman, Macke and Turaga, "Connectome-constrained networks predict neural activity across the fly
  visual system", Nature, 2024, doi:10.1038/s41586-024-07939-3.

## Honesty policy

- Numbers come from committed, checksummed artifacts, never from prose. If a result is not baked, the page
  says so instead of implying it.
- Synthetic and rendered data are labelled as such wherever they appear.
- Every model records the license of its weights, including the non-commercial ones, and the app shows it.
- Where the product extrapolates beyond the animal (for example instantiating measured filters on a denser
  lattice than a fly eye has), the page says that plainly.
