"""Moving-edge responses and the motion tuning read from them.

The published model is judged on the property the fly's motion pathway is known for: the T4 cells respond
to bright edges and the T5 cells to dark edges, each of the four subtypes to one of the four cardinal
directions. The protocol here is the one the published model was characterised with, run through the
engine's own stimulus renderer and its own analysis functions, so a number computed here means the same as
the published one:

- edges of both polarities sweep across the eye in twelve directions at six speeds, after a second of grey;
- the peak rectified response of the central cell of each type, inside the window when the edge crosses the
  central columns, is taken per direction;
- the direction selectivity index is the length of the vector sum of those peaks over directions divided by
  their sum (0 for no preference, 1 for a response to one direction only), averaged over speeds;
- the preferred direction is the angle of that vector sum, compared with the known preferred direction of
  each subtype.

Only the network is new here. Everything that decides what a response is, and what tuning means, is the
engine's.
"""

from __future__ import annotations

import numpy as np

T4_TYPES = ("T4a", "T4b", "T4c", "T4d")
T5_TYPES = ("T5a", "T5b", "T5c", "T5d")
MOTION_TYPES = T4_TYPES + T5_TYPES
# Known preferred directions, in the engine's stimulus frame: a and b are the horizontal pair, c and d the
# vertical pair. T4 is read at the bright edge (intensity 1), T5 at the dark edge (intensity 0).
KNOWN_PREFERRED = {"a": np.pi, "b": 0.0, "c": np.pi / 2, "d": 3 * np.pi / 2}
POLARITY = {"T4": 1, "T5": 0}

SPEEDS = (2.4, 4.8, 9.7, 13, 19, 25)
DT = 1 / 200


def moving_edges(dt: float = DT, speeds=SPEEDS, device: str | None = None):
    """The moving-edge stimulus set, configured exactly as the published characterisation."""
    from conectoma.network.engine import load_engine

    flyvis = load_engine()
    from flyvis.datasets.moving_bar import MovingEdge

    return MovingEdge(
        offsets=(-10, 11),
        intensities=[0, 1],
        speeds=list(speeds),
        height=80,
        post_pad_mode="continue",
        dt=dt,
        device=device or str(flyvis.device),
        t_pre=1.0,
        t_post=1.0,
    )


def central_responses(network, dataset, batch_size: int = 4, cell_index: np.ndarray | None = None):
    """Voltages of the central cell of every type (or of `cell_index`) for every stimulus of `dataset`.

    Uses the engine's own protocol: one second of grey to a steady state, no fade-in, then the stimulus.
    """
    index = network.connectome.central_cells_index[:] if cell_index is None else cell_index
    parts = []
    for _, responses in network.stimulus_response(
        dataset, dataset.dt, t_pre=1.0, t_fade_in=0.0, batch_size=batch_size,
    ):
        parts.append(np.take(responses, index, axis=-1))
    return np.concatenate(parts, axis=0)


def response_dataset(responses: np.ndarray, dataset, network, cell_index: np.ndarray | None = None):
    """Wrap responses of shape (network, sample, frame, neuron) in the layout the engine's analysis reads."""
    import xarray as xr

    index = network.connectome.central_cells_index[:] if cell_index is None else cell_index
    cell_types = np.asarray(network.connectome.nodes.type[:]).astype(str)[index]
    config = dataset.config.to_dict()
    config.pop("type", None)
    n_frames = responses.shape[2]
    time = np.arange(n_frames).astype(float) * config["dt"] - config.get("t_pre", 0.0)
    return xr.Dataset(
        {"responses": (["network_id", "sample", "frame", "neuron"], responses)},
        coords={
            "network_id": np.arange(responses.shape[0]),
            "sample": np.arange(responses.shape[1]),
            "frame": np.arange(n_frames),
            "neuron": np.arange(responses.shape[3]),
            "time": ("frame", time),
            "cell_type": ("neuron", cell_types),
            **{column: ("sample", dataset.arg_df[column].values) for column in dataset.arg_df.columns},
        },
        attrs={"config": config},
    )


def _angle_distance(a: float, b: float) -> float:
    return float(np.abs((a - b + np.pi) % (2 * np.pi) - np.pi))


def motion_tuning(data) -> dict:
    """Direction selectivity and preferred direction of every T4 and T5 subtype, per network.

    Each subtype is read at its own polarity (T4 at bright edges, T5 at dark edges). Returns, per subtype,
    one value per network for the DSI, the preferred direction in degrees, and its angular distance to the
    known preferred direction.
    """
    from flyvis.analysis.moving_bar_responses import direction_selectivity_index, preferred_direction

    dsi = direction_selectivity_index(data)
    theta = preferred_direction(data)
    cell_types = data["cell_type"].values
    result = {}
    for cell_type in MOTION_TYPES:
        where = np.nonzero(cell_types == cell_type)[0]
        if where.size == 0:
            continue
        neuron = int(where[0])
        intensity = POLARITY[cell_type[:2]]
        d = dsi.sel(intensity=intensity).isel(neuron=neuron).values.reshape(-1)
        t = theta.sel(intensity=intensity).isel(neuron=neuron).values.reshape(-1)
        known = KNOWN_PREFERRED[cell_type[-1]]
        result[cell_type] = {
            "dsi": [round(float(x), 4) for x in d],
            "preferred_direction_degrees": [round(float(np.degrees(x)) % 360, 1) for x in t],
            "distance_to_known_degrees": [round(float(np.degrees(_angle_distance(x, known))), 1) for x in t],
        }
    return result


def summarise_tuning(tuning: dict, within_degrees: float = 45.0) -> dict:
    """Across networks: median DSI, median distance to the known direction, and the share within tolerance."""
    summary = {}
    for cell_type, rows in tuning.items():
        distances = np.asarray(rows["distance_to_known_degrees"])
        summary[cell_type] = {
            "networks": int(distances.size),
            "median_dsi": round(float(np.median(rows["dsi"])), 4),
            "median_distance_to_known_degrees": round(float(np.median(distances)), 1),
            f"share_within_{int(within_degrees)}_degrees": round(
                float(np.mean(distances <= within_degrees)), 4
            ),
        }
    return summary
