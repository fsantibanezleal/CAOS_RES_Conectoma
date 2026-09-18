# The whole visual system as a network

The lattice network of [03](03_network-and-regimes.md) is one eye, averaged: each cell type is a filter
repeated across a periodic lattice. This page is its counterpart without averaging: both optic lobes and
the neurons that carry vision to and from the central brain, every cell its own node and every measured
connection its own edge. It is the network of method M08 (CX-VisualCNS) in the method ladder. The build is
`data-pipeline/conectoma/connectome/visual_cns.py`; the network classes are in
`data-pipeline/conectoma/network/neurons.py`.

## What is in it

Four superclasses of the release: optic-lobe intrinsic and optic-lobe sensory neurons (both eyes), and the
visual projection and visual centrifugal neurons that connect the optic lobes with the central brain. The
same rules as the lattice build decide which cells take part: the inner photoreceptors are pooled into R7
and R8, placeholder types ("_unclear") are left out, and every neuron needs a cell type.

| Quantity | Value |
|---|---|
| neurons | 105,011 (51,724 left, 53,287 right) |
| by superclass | 89,270 optic-lobe intrinsic, 6,013 optic-lobe sensory, 9,169 visual projection, 559 visual centrifugal |
| cell types | 695 |
| connections (ordered neuron pairs) | 12,450,379 |
| synapses | 49,664,904 |
| photoreceptors | 3,661 right (3,586 with a column), 2,345 left (2,337 with a column) |
| readout types (LC and LPLC projection neurons) | 50 |
| graph file | 41 MB compressed, outside git; summary committed with its SHA-256 |

The photoreceptor counts are what the release reconstructs, not what an eye has: the right medulla has 893
columns (measured in [02](02_connectome-construction.md)), and six outer plus two inner photoreceptors per
column would be about 7,100. The retina is incomplete at the edges of the imaged volume, and more so on the
left. The network is built on what was measured; its input
is one value per photoreceptor that exists.

### Every connection, not a thresholded subset

A minimum-synapse cut is common in connectome analyses. Here it would change the dynamics, because a
connection's drive is proportional to its synapse count. Measured on this graph:

| Minimum synapses per connection | Connections | Synapses kept |
|---|---|---|
| 1 (default) | 12,489,453 | 100 percent |
| 2 | 7,598,693 | 90.2 percent |
| 3 | 5,154,901 | 80.4 percent |
| 5 | 2,885,364 | 64.9 percent |
| 10 | 1,068,649 | 41.4 percent |

So every measured connection is kept, and the cut is a recorded option (`--min-weight`). (The counts in this
table were taken before placeholder types were removed; the built graph has 12,450,379.)

### Signs per neuron

Each presynaptic neuron carries its own transmitter prediction, so the sign is per connection, from the
neuron, not per cell type. Of 105,011 neurons, 104,448 have their own call, 20 take their cell type's
call, 541 have none and take the excitatory default with a low-confidence flag, and 2 are absent from the
transmitter table. 38,767 neurons are inhibitory.

### Columns per eye

Each optic lobe has its own column frame, so column inference runs on one eye's optic-lobe subgraph at a
time: partners across the midline never vote on a position. The method and its holdout validation are those
of the lattice build ([02](02_connectome-construction.md)):

| Eye | Optic-lobe neurons | Annotated | Inferred | Unplaced | Holdout: exact | Within one column |
|---|---|---|---|---|---|---|
| right | 48,415 | 13,267 | 35,071 | 77 | 99.89 percent | 100 percent |
| left | 46,868 | 10,453 | 36,403 | 12 | 99.83 percent | 100 percent |

The right eye reproduces the lattice build exactly, which is a check that the two builds select and place
the same cells.

## The network classes

- **`NeuronConnectome`**, registered with the engine: loads the graph, verifies its SHA-256 against the
  network's configuration, lays cells out grouped by type, and carries every connection with its synapse
  count and its presynaptic neuron's sign. Column coordinates are carried into the engine's frame with the
  half-turn measured on the right eye ([02](02_connectome-construction.md), orientation). The left eye's
  frame relative to a left-eye renderer has not been measured; the side of every input is exported so the
  renderer can decide per eye.
- **`PhotoreceptorStimulus`**, registered with the engine: the input is one value per placed photoreceptor
  neuron, and `input_layout` lists, in order, each input's eye, column and type. A fly-eye renderer (unit
  U4) produces exactly that vector from a scene; the network does not assume a periodic eye.

### Regimes at neuron granularity

The three regimes of [03](03_network-and-regimes.md), with neuron granularity in place of lattice
granularity. Synapse counts and signs are per connection in every regime.

| Regime | Trainable | Granularity |
|---|---|---|
| R0 reservoir | nothing | - |
| R1 biophysical | synaptic strength, time constant, resting potential | per connected type pair; per cell type |
| R2 edge gain | synaptic strength, time constant, resting potential | per connection; per neuron |

The regimes share one starting point and can take the published model's trained values where cell types
match, exactly as on the lattice. Every neuron-level network starts with its loop gain bounded (below); the
plan runs R0 at this size, and the cost of R1 is measured.

## Measured as a frozen network

Measured by `run.py characterize-visual-cns` (report:
`data/derived/connectome/malecns-visual-cns.characterization.json`), on an RTX 4070 Laptop GPU.

### It runs away unless its loop gain is bounded

The whole visual system is, for the purposes of its dynamics, one recurrent network:
104,058 of its 105,011 cells belong to a single strongly connected component,
so almost every cell can reach almost every other. With threshold-linear dynamics that raises one
question before any other: is the frozen network stable at all?

| Starting point | Loop gain (spectral radius of the absolute weights) | Settled after 2 s of grey | Voltage range |
|---|---|---|---|
| engine initialisation, as built | 3.07 | no (still moving by 15,822 in the last half second) | -1,189 to 17,961 |
| published values transferred, as built | 4.89 | no (still moving by 6,258 in the last half second) | -472 to 7,111 |
| engine initialisation, gain bounded to 0.9 (strengths scaled by 0.293) | 0.90 | yes | -1.02 to 11.49 |
| published values transferred, gain bounded to 0.9 (strengths scaled by 0.184) | 0.90 | yes | -0.97 to 6.30 |

With threshold-linear dynamics, a small perturbation evolves with the weight matrix restricted to the active
cells, and every eigenvalue of that is bounded by the spectral radius of the matrix of absolute weights. A
radius below one therefore guarantees stability at every operating point: the echo-state condition of
reservoir computing, stated for these dynamics. From the engine's initialisation, which gives every
connection a weight of about 0.01, a network whose cells receive about 119 connections each (63 percent of
its neurons excitatory) has a loop gain of 3.07, and the activity runs into the
thousands. Every
neuron-level network is therefore built with its synaptic strengths scaled by one factor, chosen so that the
radius is 0.9 (`network/gain.py`). The factor is measured and recorded with the network, and the relative
strengths of all connections are untouched.

The lattice network of [03](03_network-and-regimes.md) has a loop gain above one as well
(1.48 from the engine's initialisation, 2.33 with the published values)
and settles anyway, as do all fifteen of its controls (about 73 connections per cell there, 119 here): the
bound is sufficient, not necessary, and the lattice stays stable above it. The neuron-level network is where
it becomes necessary, and it is applied there only.

The spectral radius is computed per strongly connected component (the radius of a non-negative matrix is
the largest over its components, and feed-forward chains contribute nothing), exactly for small components
and with the implicitly restarted Arnoldi method for large ones. Long feed-forward chains are the kind of
structure that stalls both power iteration and the Arnoldi method on the whole matrix; the decomposition
removes them. The relative residual of the largest eigenpair here is below 4e-15.

### Does the eye reach the readouts?

A full-field step on every photoreceptor after grey input, with the gain bounded (voltages in the engine's
dimensionless units):

| Population | Cells | Engine initialisation: responding | median change | Transferred: responding | median change |
|---|---|---|---|---|---|
| photoreceptors | 6,006 | 98.9% | 5.0e-01 | 98.9% | 5.0e-01 |
| optic lobe and centrifugal | 94,347 | 84.6% | 8.3e-05 | 98.6% | 1.4e-03 |
| LC and LPLC readouts | 4,658 | 92.4% | 7.5e-05 | 99.7% | 5.1e-04 |

The signal reaches nearly every readout cell, weakly: bounding the loop gain also attenuates what travels
through the network, and a readout head will be working with voltage changes of 1e-4 to 1e-3, against
resting potentials around 0.5. That is the price of a frozen network that is stable by construction, and
it is measured here so the method units start from it rather than discover it.

### Cost

Simulation runs at 2.0 simulated seconds per wall-clock second (batch of one, 5 ms steps),
with a peak of 6.5 GB of GPU memory. An R1 training step (19 frames, batch of one) fits: 0.25 s and
2.8 GB, for 130,827 trainable parameters. The plan expected to run only R0 at this
size; an R1 step fits at a batch of one. R2, with one parameter per connection (about 12.7 million), is not
measured here, and larger batches are bounded by the 6.5 GB peak of the frozen simulation on an 8 GB GPU.

## What this is, and what it is not

- It is the measured visual system of one male fly, both eyes and their projections, as a graph the engine
  can simulate and a head can read out from.
- It is not a periodic eye: nothing is averaged, so a result on it speaks for this animal's wiring, not for
  a type-level consensus.
- Its input is incomplete where the release is incomplete, and its readouts are the cells that project to
  the central brain, not a model of behaviour.
