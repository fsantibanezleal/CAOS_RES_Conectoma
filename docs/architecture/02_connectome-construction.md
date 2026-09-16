# Connectome construction

How the MaleCNS release becomes the network architecture. Everything on this page is implemented in
`data-pipeline/conectoma/connectome/` and produces a single JSON file plus a report, both of which are
committed.

## What the release gives, and what it does not

| Fact | In the release | Coverage |
|---|---|---|
| cell type, class, superclass, side, per neuron | yes | 211,577 neurons, of which 95,501 are optic lobe |
| synapse count for an ordered pair of neurons | yes | 151,856,684 ordered pairs |
| neurotransmitter prediction per neuron and per cell type, with confidence | yes | 1,835,518 rows |
| hexagonal column coordinate (`assignedOlHex1`, `assignedOlHex2`) | partly | 23,720 neurons, 15 cell types |

The column coordinate is the gap that matters. A convolutional filter is defined by the offset between the
column of the source and the column of the target, so every columnar neuron needs a coordinate, and the
release annotates only the classic lamina and medulla set: L1 to L5, C2, C3, T1, Mi1, Mi4, Mi9, Tm1, Tm2,
Tm4, Tm9, Tm20. The direction-selective T4 and T5 populations, the Dm and Pm families and most of the
lobula are not annotated.

## Column assignment, and how it is measured

A neuron sits in the column its partners sit in. The coordinate of an unannotated neuron is the
synapse-weighted median of the coordinates of its already-placed partners, repeated for a few rounds so a
neuron two steps from the annotated set can still be placed. A median, not a mean: an arbor that reaches a
few distant columns must not drag the centre, and the result has to be a lattice position.

A neuron is placed only when at least three of its partners are already placed, so one weak contact cannot
decide a position.

The method is measured rather than asserted. Each annotated cell type is held out in turn, re-inferred from
the remaining annotated types, and compared against its annotation with the hexagonal lattice distance. The
report next to the connectome carries, per held-out type, the fraction recovered exactly, the fraction
within one column, the median error and the 95th percentile. Those numbers are the reason to trust or
distrust the inferred coordinates, and they travel with the artifact.

## Average filters

For every ordered pair of cell types and every column offset `(du, dv)`, the synapses of all contributing
neuron pairs are summed and divided by the number of placed neurons of the target type. That average is the
filter entry. The offset convention is taken from the consuming engine: a target sits at
`(u_source + du, v_source + dv)`, so the code computes `du = u_target - u_source`.

Two thresholds keep noise out of the architecture, both recorded in the artifact: a minimum average
synapse count per filter entry, and a minimum fraction of eligible column pairs that must carry the
connection. Their values were chosen by measurement rather than taste, see the sweep below.

The certainty the engine reads as a per-connection multiplier is the fraction of eligible column pairs that
actually carry the connection, so a filter seen across the whole eye is not presented like one seen twice.

## Signs

The sign of a connection comes from the neurotransmitter prediction of the presynaptic neuron:
acetylcholine, dopamine, octopamine and serotonin are taken as excitatory, and glutamate, GABA and
histamine as inhibitory. Glutamate is inhibitory here because the optic-lobe glutamate receptor of interest
is a chloride channel, which is the same assumption the published connectome-constrained model makes;
histamine is the photoreceptor transmitter acting on a chloride channel. The aminergic transmitters are
modulatory rather than fast, and treating them as excitatory currents is a modelling choice that is flagged
per neuron rather than hidden.

A cell type takes the majority sign of its neurons, and the minority fraction is recorded per type, because
disagreement inside a type is evidence about the calls rather than about the biology.

## Output

`data/derived/connectome/malecns-optic-lobe-<side>.json` holds the nodes, the edges with their filters,
signs and certainties, the photoreceptor inputs, the readout types, and a provenance block naming the
dataset, its license, the citation, the sign source and the exact configuration. The sibling
`.report.json` holds the ingestion counts, the rejected and flagged reasons, the column-assignment result
and the holdout validation.

Both are compact and committed. The tables they are built from stay in the local cache and never enter git.


## What the build produces, measured

Right optic lobe, MaleCNS v1.0, at the default settings:

| Quantity | Value |
|---|---|
| neurons selected | 48,523 of 211,577 annotated bodies |
| cell types | 274 |
| connection rows scanned | 151,856,684 |
| edges inside the selection | 4,651,262 |
| column coordinates annotated by the release | 13,267 |
| column coordinates inferred here | 35,131 |
| neurons left without a column | 125 |

### Column assignment, validated by holdout

Each annotated cell type was removed in turn and re-inferred from the remaining ones:

| Measure | Result |
|---|---|
| held-out neurons recovered to the exact annotated column | 99.89 percent |
| recovered within one column | 100 percent |
| worst 95th percentile error across types | 2 columns |

The method is therefore accurate where it can be checked, and the connectome carries these numbers next to
the coordinates they justify.

### Against the published consensus

The reference is the connectome of the Nature 2024 connectome-constrained model: 65 cell types and 605
connections distilled from the FIB-25 and FIB-19 medulla volumes. It comes from different volumes and a
different reconstruction pipeline, so agreement is the question, not identity.

Cross-release renames are mapped explicitly (this release merges the outer photoreceptors into one type,
splits the inner pair by spectral subtype, and carries the wide-field CT1 as one cell where the reference
splits its two compartments). Five reference types have no counterpart in this release at all and are
reported as unmatched rather than mapped onto something similar.

| Measure | Result |
|---|---|
| reference cell types matched | 59 of 65 |
| comparable reference connections recovered | 75.8 percent |
| sign agreement on recovered connections | 97.1 percent |
| rank correlation of central synapse counts | 0.79 |

The sign disagreements are evidence conflicts rather than defects. The reference derives the sign of a
connection from receptor expression per cell-type pair; this build derives it from the per-synapse
neurotransmitter classifier of the release. Where they differ, the classifier's call and its confidence are
recorded, and the sign-shuffled control measures how much any downstream result depends on them.

### The threshold sweep

| Minimum mean synapses, minimum certainty | Reference connections recovered | Sign agreement | Rank correlation | Edges | Artifact |
|---|---|---|---|---|---|
| 1.0, 0.05 | 66.2 percent | 96.9 percent | 0.81 | 4,565 | 5.2 MB |
| **0.5, 0.02 (default)** | **75.8 percent** | **97.1 percent** | **0.79** | **6,140** | **7.7 MB** |
| 0.2, 0.01 | 84.8 percent | 96.5 percent | 0.77 | 8,881 | 12.1 MB |

The default is the middle row: it recovers nine points more of the published connectome than the strict
setting at the best sign agreement of the three, while the loose setting buys further recovery with weaker
connections that cost rank correlation and double the artifact. The sweep is reproducible from the command
line arguments of the build, and any future change to the default is expected to come with its own sweep.
