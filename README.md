# Conectoma

[![CI](https://img.shields.io/github/actions/workflow/status/fsantibanezleal/CAOS_RES_Conectoma/ci.yml?branch=main&label=CI)](https://github.com/fsantibanezleal/CAOS_RES_Conectoma/actions)
[![License](https://img.shields.io/github/license/fsantibanezleal/CAOS_RES_Conectoma)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/fsantibanezleal/CAOS_RES_Conectoma?label=version&sort=semver)](https://github.com/fsantibanezleal/CAOS_RES_Conectoma/tags)

**The connectome of a fly, used as the architecture of a computer-vision network.** Conectoma takes the
wiring diagram of the *Drosophila melanogaster* male central nervous system, freezes it, and asks what a
network built from measured biology can compute: depth from a moving camera, and figure-ground
segmentation. Everything the connectome measures stays fixed. Only what it cannot measure is learned.

> Status: **building**. This repository is at version 0.06.000; the units listed in *Build order* below land
> one at a time, each with its code, tests and documentation in the same commit. Nothing here is a
> placeholder for work that is not done: what is absent is absent.
>
> Site: **[conectoma.fasl-work.com](https://conectoma.fasl-work.com)**. Today it holds the connectome
> explorer (every cell type's filters on the hexagonal lattice, side by side with the published consensus,
> and the rule that placed each type), the eye's input (what the 721 columns receive in each of the sixteen
> validation cases, level by level and frame by frame, beside the ground truth each case grades) and the six
> pages, with every number read from the committed reports. The vision methods and their benchmark arrive
> with the units that build them.

## Motivation and problem

Connectomics can now measure every neuron and synapse of a small brain, but a wiring diagram is not a
function: the diagram says who talks to whom, not what the circuit computes. Lappalainen et al. (Nature,
2024) showed that for the fly optic lobe, connectivity plus a task is enough to predict single-neuron
activity, freezing synapse counts and signs and learning only per-cell-type dynamics. That work targeted
optic flow, which is what fly vision evolved for.

Conectoma asks the next question, and asks it with controls: can the same frozen wiring serve as the
backbone of a **dense prediction** network for tasks the fly did not evolve to solve in this form, and is
any measured advantage attributable to **biology** rather than to sparsity or recurrence? The honest answer
may be no. The product is the rigorous comparison, not a win.

## KPIs, impact and value

- A reusable, evidence-first answer to "is a measured connectome a useful prior for machine vision", with
  effect sizes against rewired and random-graph controls rather than a single headline number.
- An interpretability surface no conventional backbone offers: per-cell-type probes that name which
  biological cell types carry depth and figure-ground information.
- A public, reproducible bridge between a CC-BY connectome release and standard computer-vision benchmarks.

## Solution overview

The offline repository is the product. It ingests the Janelia MaleCNS v1.0 connectome tables, assigns
retinotopic coordinates, builds type-level consensus filters, compiles them into a differentiable network,
trains only the permitted parameters, runs a complete method ladder over a leakage-safe case matrix, and
exports compact audited artifacts. A companion web workbench replays those artifacts and runs the
validated lightweight lane in the browser.

## How the problem is modelled

Each neuron is a point neuron with threshold-linear dynamics. For a postsynaptic neuron `i` of cell type
`t_i`, with voltage `V_i`, membrane time constant `tau`, resting potential `V_rest` and external input
`e_i` (nonzero only for photoreceptors):

```
tau_{t_i} dV_i/dt = -V_i + sum_j s_ij + V_rest_{t_i} + e_i
s_ij = alpha_{t_i t_j} * sigma_{t_i t_j} * N_{t_i t_j}(du, dv) * ReLU(V_j)
```

`N` is the measured synapse count at hexagonal offset `(du, dv)` between two cell types, and `sigma` is the
measured sign (excitatory or inhibitory). Both come from the connectome and are **frozen**. Three regimes
decide what else may learn, measured on the right optic lobe (253 cell types, 40,051 cells, 2,922,900
connections):

| Regime | Trainable inside the network | Count |
|---|---|---|
| R0 reservoir | nothing; only a readout outside the network | 0 |
| R1 biophysical | `alpha` per type pair, `tau` and `V_rest` per cell type (the published model's regime) | 8,409 |
| R2 edge gain | `alpha` per connection, `tau` and `V_rest` per neuron | 3,003,002 |

Every regime is compared against three null controls (degree-preserving rewiring, a size-matched random
graph, a sign shuffle), and the construction is checked against the published connectome-constrained
model, voltage for voltage. The equations, their symbols and their sources are in
[docs/architecture/03](docs/architecture/03_network-and-regimes.md).

Next to the lattice, the whole visual system runs neuron by neuron: both optic lobes and their projections
to the central brain, 105,011 neurons and 12,450,379 measured connections, with the photoreceptors as input
and the LC and LPLC projection neurons as readouts. It is one recurrent component whose loop gain has to be
bounded before it is stable as a frozen network ([docs/architecture/04](docs/architecture/04_the-whole-visual-system.md)).

## Data and engines

- Connectome: Janelia **MaleCNS v1.0** (`male-cns:v1.0`), CC-BY. 166,691 neurons, 11,691 cell types.
- Simulation and training of connectome-constrained networks: **flyvis** (MIT).
- Vision data ([docs/architecture/05](docs/architecture/05_vision-data.md)): **TartanAir V2** (CC BY 4.0;
  2,244 clips from all 74 environments, fetched member by member, and its panoramas), **MPI Sintel** (film
  content CC BY 3.0; the published model's domain), **Spring** (CC BY 4.0), **Hypersim** (CC BY-SA 3.0,
  official test partition) and **FlyGym** (Apache-2.0; the fly's own compound eye), all rendered onto the
  engine's 721-column lattice, split by geometry family with a leakage gate, and sixteen cases of six
  physical levels each.
- Reference engines across the method ladder, each carrying its own license, recorded per checkpoint in the
  model registry and shown in the app.

## Build order

`U0` repository base · `U1` MaleCNS to consensus connectome · `U2` frozen regimes and null controls ·
`U3` frontend base · `U4` data ingestion and leakage-safe splits · `U5` to `U13` the method ladder ·
`U14` exports and parity gates · `U15` the web workbench · `U16` canonical bake, benchmark and deploy.

## Repository map

| Path | What |
|---|---|
| `data-pipeline/` | the offline engine: connectome construction (`conectoma/connectome/`), the network compiler, regimes, null controls and parity checks (`conectoma/network/`), and the command line (`run.py`) |
| `data/` | `raw/` git-ignored source cache, `derived/` committed compact artifacts, `derived/manifests/` the contract 2 manifests |
| `models/` | small exported models; heavy checkpoints stay outside git |
| `frontend/` | the static site: the connectome explorer, the six pages, the contract tests and the fit gate ([guide](docs/guides/04_the-web.md)) |
| `app/` | dormant FastAPI module (this product is static replay) |
| `deploy/` | deployment notes for the chosen target |
| `docs/` | the wiki: architecture, frameworks, cases, guides |
| `scripts/` | setup, the local run scripts and the CI guards (artifacts, content standards, CI budget) |

## Quick start

```bash
./scripts/setup.sh          # or scripts/setup.ps1 on Windows PowerShell
python -m pytest            # repository invariants
ruff check .                # lint
```

The offline pipeline has its own environment and data roots:

```bash
python data-pipeline/run.py build-connectome          # the MaleCNS tables to the connectome specification
python data-pipeline/run.py compare-consensus         # against the published consensus
python data-pipeline/run.py parity-published          # the published model rebuilt through this path
python data-pipeline/run.py characterize-connectome   # the MaleCNS connectome as a frozen network
```

Setup, data roots and expected run times: [fetch the connectome](docs/guides/02_fetch-the-connectome.md) and
[the network engine](docs/guides/03_network-engine.md).

## License and attribution

MIT, see [LICENSE](LICENSE). The MaleCNS connectome is CC-BY and must be cited when this work is reused;
each dataset and model carries its own terms, listed in the documentation of the unit that uses it.

Developed by Felipe Santibanez-Leal.
