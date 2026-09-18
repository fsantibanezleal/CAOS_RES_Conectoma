# The network engine: setup, the published models, and the checks

How to get from a fresh clone to a compiled MaleCNS network, the published models downloaded, and the two
checks of this unit reproduced: parity with the published model, and the characterisation of the frozen
connectome. The architecture behind every step is in
[architecture/03](../architecture/03_network-and-regimes.md).

## 1. The environment

The offline lane runs in `.venv-pipeline` on Python 3.12 (the engine requires Python below 3.13). On a
machine with an NVIDIA GPU, install the CUDA build of torch first through the GPU requirements; everywhere
else the CPU build satisfies the same pin.

```bash
py -3.12 -m venv .venv-pipeline                     # Windows; python3.12 -m venv elsewhere
.venv-pipeline/Scripts/python -m pip install -r requirements-gpu.txt -r requirements-dev.txt   # CUDA machine
# or, without a GPU:
.venv-pipeline/Scripts/python -m pip install torch==2.14.0 torchvision==0.29.0 \
    --index-url https://download.pytorch.org/whl/cpu
.venv-pipeline/Scripts/python -m pip install -r requirements-precompute.txt -r requirements-dev.txt
```

The engine's storage layer is pinned to an upstream commit, not to its last release, because the release
fails on Windows the first time a connectome is compiled; the reason is recorded next to the pin in
`data-pipeline/requirements.txt`. Installing it needs `git` on the path.

## 2. Where the engine keeps its data

Two roots, both outside the repository and never committed:

| Variable | Holds | Example |
|---|---|---|
| `CONECTOMA_DATA_ROOT` | the MaleCNS release tables ([guide 02](02_fetch-the-connectome.md)) | `/data/conectoma/raw` |
| `CONECTOMA_MODELS_ROOT` | the engine's root (`flyvis/` inside it: published models, rendered stimuli, reference compilations) and the null-control specifications (`controls/`) | `/data/conectoma/models` |

The engine fixes its root the first time it is imported. The product sets it from `CONECTOMA_MODELS_ROOT`
before that import and refuses to continue if something imported the engine earlier with another root,
because every later path would silently resolve elsewhere. Without the variable the engine falls back to a
folder inside the installed package, which is lost with the environment.

## 3. The published models

The fifty models of the published ensemble (optic flow, ensemble `flow/0000`, about 7 MB unpacked) are
downloaded with the engine's own command, into the engine root:

```bash
export CONECTOMA_MODELS_ROOT=/data/conectoma/models
export FLYVIS_ROOT_DIR="$CONECTOMA_MODELS_ROOT/flyvis"
.venv-pipeline/Scripts/flyvis download-pretrained
```

The command verifies the SHA-256 of each archive before unpacking. The models are ranked by task error, so
`000` is the best of the fifty.

## 4. Build the network

The connectome of [guide 02](02_fetch-the-connectome.md) compiles into a network in any regime:

```python
import sys; sys.path.insert(0, "data-pipeline")
from conectoma.network.engine import published_model_dir
from conectoma.network.regimes import build_network, trainable_report

spec = "data/derived/connectome/malecns-optic-lobe-r.json"
network = build_network(spec, "R0")                                  # frozen, engine initialisation
network = build_network(spec, "R2", transfer_from=published_model_dir("000"))   # edge gain, transferred
print(trainable_report(network)["trainable"])                        # 3,003,002 on the right optic lobe
print(network.connectome.compile_report["connections_unrealised"])  # the four named connections
```

A network records the SHA-256 of its specification; rebuilding the specification and loading an old
checkpoint against it fails with a message naming both digests.

## 5. Reproduce the checks

```bash
# the published model through this product's path: voltages on three models, tuning on all fifty
.venv-pipeline/Scripts/python data-pipeline/run.py parity-published

# the MaleCNS connectome as a frozen network: stability, cost, tuning, and the null controls
.venv-pipeline/Scripts/python data-pipeline/run.py characterize-connectome --seeds 5
```

| Command | Writes | Time on an RTX 4070 Laptop GPU |
|---|---|---|
| `parity-published` | `data/derived/network/parity-published.json` | about 40 minutes (about 48 s per model), plus 3 minutes for the engine-pipeline cross-check |
| `characterize-connectome` | `data/derived/connectome/malecns-optic-lobe-r.characterization.json` | about 40 minutes (two starting points, three regimes timed, five seeds of each control at about 2 minutes each) |

Both commands keep every finished step in a run log under `$CONECTOMA_MODELS_ROOT/runs/`. A rerun reuses
the steps whose inputs (specification digest, stimulus, device) are unchanged, so an interrupted run resumes
where it stopped, and a report can be regenerated in seconds. The parity command exits with a non-zero
status if any voltage comparison exceeds its tolerance or the cross-check with the engine's own pipeline
disagrees.

## 6. On your own connectome

Any specification in the average-filter format compiles the same way. Two things decide whether it compiles
as intended:

- **Placement.** Each node declares `["stride", [k, k]]` or `["single", null]`. Every input type must use
  `["stride", [1, 1]]`.
- **The `compile` block.** Without it the expansion is the engine's own, exact only when every type sits on
  every column. With `{"target_centric": true, "population_broadcast": true}` every target cell receives its
  full filter and single nodes drive every cell of their targets. Read the compile report after building:
  it names every connection the expansion could not realise.

The tests in `tests/test_network_engine.py` build small synthetic connectomes this way and are a working
example of both rules.
