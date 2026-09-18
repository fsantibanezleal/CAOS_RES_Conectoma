# Architecture, overview

Conectoma is an offline-pipeline-heavy product with a companion static web surface. The repository is
useful without the website: it ingests a connectome and vision datasets, builds and trains the networks,
runs the full method ladder, evaluates on a leakage-safe matrix and exports compact artifacts.

## The lanes, and what runs where

| Lane | Where | Dependencies | What runs |
|---|---|---|---|
| Offline (canonical) | `data-pipeline/`, `.venv-pipeline` (Python 3.12) | `requirements-precompute.txt`, `requirements-gpu.txt` | connectome ingestion, network construction, training, batch inference, evaluation, export |
| Live (client-side) | the web app | browser runtime | the validated lightweight subset: classical flow-parallax, the elementary-motion-detector baseline, and the frozen connectome network at the ethological lattice, after parity and latency gates pass |
| Replay | the web app | none | committed artifacts for every showcased case; always the first paint |
| API | `app/` | `requirements-api.txt` | dormant; this product is static replay and does not need request-time compute |

Python 3.12 is not a preference: `flyvis` 1.2.0 declares `requires-python <3.13`, and the offline lane
depends on it.

## The flow

```
data/raw (git-ignored cache)
  -> ingestion contract (schema, units, ranges, outlier policy)
  -> staged pipeline: preprocess, dataset and splits, features, train, infer, evaluate, export, validate
  -> artifact contract (compact artifact + manifest per case)
  -> data/derived (committed)  ->  the web app replays it
```

## What is frozen and what is learned

The connectome supplies the graph: which cell types connect, how many synapses at which retinotopic offset,
and the sign of each connection. Those are measurements and they never change during training. Three
regimes differ only in what the optimizer is allowed to touch:

| Regime | Frozen | Learned | Trainable in the network, right optic lobe |
|---|---|---|---|
| R0 reservoir | wiring, counts, signs, synaptic strengths, time constants, resting potentials | the readout head only | 0 |
| R1 biophysical | wiring, counts, signs | synaptic strength per type pair, time constant and resting potential per cell type, plus the head | 8,409 |
| R2 edge gain | wiring, counts, signs | synaptic strength per connection, time constant and resting potential per neuron, plus the head | 3,003,002 |

Every regime is reported against the same null controls: a degree-preserving rewiring, a size-matched
random sparse graph, and a sign-shuffled connectome. A result that does not separate from those controls is
reported as such. How the network is compiled, what each regime trains and how the construction is checked
against the published model: [03, the network](03_network-and-regimes.md).

## Boundaries

This product does not claim that flies perform semantic segmentation or single-image depth estimation. It
does not emulate a whole brain. It does not present a browser export as the offline engine: a reduced live
model is named separately and reports its quality gap.
