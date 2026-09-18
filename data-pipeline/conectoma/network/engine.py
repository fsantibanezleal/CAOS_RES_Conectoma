"""One door to the network engine.

The engine resolves its storage root once, when it is first imported, from `FLYVIS_ROOT_DIR`; without it the
root falls inside the installed package, where downloaded models would be lost with the environment. This
module points it at the product's models root before that first import, registers the product's connectome
classes, and fails loudly if the engine was imported earlier with a different root, because every later
path (pretrained models, compiled references) would silently resolve elsewhere.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MODELS_ROOT_ENV = "CONECTOMA_MODELS_ROOT"
ENGINE_ROOT_ENV = "FLYVIS_ROOT_DIR"
ENGINE_SUBDIR = "flyvis"

# The ensemble of the connectome-constrained model trained on optic flow, as published with the engine.
# Models inside it are ranked by task error, so "000" is the best of the fifty.
PUBLISHED_ENSEMBLE = "flow/0000"


def engine_root() -> Path | None:
    """Where the engine keeps models and compiled references, from the product's models root."""
    root = os.environ.get(MODELS_ROOT_ENV)
    return Path(root) / ENGINE_SUBDIR if root else None


def load_engine():
    """Import the engine with its root set, and register the product's connectome classes."""
    wanted = engine_root()
    if "flyvis" not in sys.modules and wanted is not None:
        os.environ.setdefault(ENGINE_ROOT_ENV, str(wanted))
    import flyvis

    if wanted is not None and Path(flyvis.root_dir).resolve() != wanted.resolve():
        raise RuntimeError(
            f"the engine was imported with root {flyvis.root_dir}, not {wanted}; set {MODELS_ROOT_ENV} "
            "before anything imports it"
        )

    from conectoma.network import lattice, neurons

    lattice.register()
    neurons.register()
    install_vectorised_grouping()
    return flyvis


def vectorised_scatter_indices(dataframe, grouped_dataframe, groupby):
    """The engine's parameter-sharing index, computed with a hash join instead of a Python loop.

    For every element (a neuron or a connection) it returns the position of the element's group in the
    grouped table, exactly as `flyvis.network.initialization.get_scatter_indices` does. The engine builds a
    dictionary and walks every element in Python, which at three million connections is most of the time
    it takes to construct a network. The result is compared with the engine's own function in the tests.
    """
    import pandas as pd
    import torch

    columns = list(groupby)
    groups = pd.MultiIndex.from_frame(grouped_dataframe[columns].reset_index(drop=True))
    elements = pd.MultiIndex.from_frame(dataframe[columns].reset_index(drop=True))
    positions = groups.get_indexer(elements)
    if (positions < 0).any():
        raise KeyError("an element has no group; the grouped table does not come from this table")
    return torch.tensor(positions)


def install_vectorised_grouping() -> None:
    """Route the engine's parameter constructors through `vectorised_scatter_indices`. Idempotent."""
    from flyvis.network import initialization

    if getattr(initialization.get_scatter_indices, "__name__", "") != vectorised_scatter_indices.__name__:
        initialization.reference_scatter_indices = initialization.get_scatter_indices
        initialization.get_scatter_indices = vectorised_scatter_indices


def published_model_dir(model: str = "000") -> Path:
    """Directory of one model of the published ensemble; raises if it has not been downloaded."""
    flyvis = load_engine()
    path = Path(flyvis.results_dir) / PUBLISHED_ENSEMBLE / model
    if not (path / "best_chkpt").exists():
        raise FileNotFoundError(
            f"published model {PUBLISHED_ENSEMBLE}/{model} not found under {flyvis.results_dir}; "
            "run the download described in docs/guides/03_network-engine.md"
        )
    return path


def run_log(name: str, signature: dict):
    """The resumable log of a long run, kept next to the engine's data (see `conectoma.core.runlog`)."""
    from conectoma.core.runlog import RunLog

    base = engine_root()
    folder = (base.parent if base is not None else Path.cwd()) / "runs"
    return RunLog(folder / f"{name}.json", signature)


def device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"
