"""The lattice connectome: an average-filter specification compiled in memory for the network engine.

The engine ships a compiler for the same JSON format (`ConnectomeFromAvgFilters`), and it is the reference
this one is tested against, edge for edge. It is not used directly for three reasons, each of which bit or
would bite:

- it caches every compiled graph on disk under a key made of its arguments, and for a specification file
  that key is the path, not the content: a rebuilt connectome at the same path silently loads the old graph;
- every null-control seed is a different graph, and the disk cache would keep a compiled copy of each one
  (about 50 MB at the measured size) for a network that is used once;
- its edge construction is a Python loop over every source cell of every filter entry, which is the slow
  step at the measured size.

This class builds the same node and edge tables with the edge expansion vectorised per filter entry, keeps
them in memory, and records the SHA-256 of the specification in its configuration, so a checkpoint names
the exact graph it was trained on and loading it against a different file fails.

Node order, edge order and the gap filling are those of the reference compiler; the gap filling calls the
engine's own routine, so the two cannot drift apart there.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

# The engine registers a connectome class under its class name.
REGISTERED_NAME = "LatticeConnectome"


def spec_digest(path: Path) -> str:
    """SHA-256 of the specification bytes, the identity a checkpoint is bound to."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hex_positions(extent: int, u_stride: int = 1, v_stride: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Columns of a hexagonal array of radius `extent`, in the reference compiler's order."""
    us: list[int] = []
    vs: list[int] = []
    for u in range(-extent, extent + 1):
        for v in range(max(-extent, -extent - u), min(extent, extent - u) + 1):
            if u % u_stride == 0 and v % v_stride == 0:
                us.append(u)
                vs.append(v)
    return np.asarray(us, dtype=np.int32), np.asarray(vs, dtype=np.int32)


def _placement(pattern: list, extent: int) -> tuple[np.ndarray, np.ndarray]:
    kind, args = pattern
    if kind == "stride":
        return hex_positions(extent, int(args[0]), int(args[1]))
    if kind == "tile":
        return hex_positions(extent, int(args), int(args))
    if kind == "single":
        return hex_positions(0)
    raise ValueError(f"unknown placement pattern {kind!r}")


class _Table(dict):
    """A dict with attribute access, the shape the engine reads node and edge tables in."""

    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError as error:
            raise AttributeError(key) from error

    def __setattr__(self, key: str, value) -> None:
        self[key] = value


def _snap(values: np.ndarray, stride: int) -> np.ndarray:
    """Nearest multiple of `stride`, halves rounded up, so the rule does not depend on the sign."""
    return (np.floor(values / stride + 0.5) * stride).astype(np.int64)


def compile_spec(spec: dict, extent: int, n_syn_fill: float) -> tuple[_Table, _Table, dict]:
    """Node and edge tables of an average-filter specification, and a report of what was realised.

    Without a `compile` block the tables are identical to the reference compiler's, which expands each
    filter from its sources: a source cell at a column connects to the target cell at the column plus the
    offset, if there is one. That is exact when every type sits on every column, and it loses entries when
    types sit on sublattices, because two sublattices that share the origin only meet at offsets that are
    multiples of their strides. The block switches on the two rules a whole-lobe specification needs (see
    `connectome.malecns.to_flyvis_spec`):

    - `target_centric`: each filter is expanded from its targets instead. Every target cell receives every
      entry of its measured filter; the source position an entry points at is served by the nearest cell
      of the source type's sublattice, and entries that land on the same source cell are summed. Each
      target cell therefore receives its full measured input, whatever the two strides are.
    - `population_broadcast`: an edge from a type placed once (a population node) connects that node to
      every cell of the target type, with the synapse count its single filter entry states.
    """
    from flyvis.connectome.connectome import fill_hull

    rules = spec.get("compile", {})
    broadcast = bool(rules.get("population_broadcast", False))
    target_centric = bool(rules.get("target_centric", False))

    # nodes, in specification order, each type laid out over its placement
    types: list[str] = []
    us: list[np.ndarray] = []
    vs: list[np.ndarray] = []
    patterns: dict[str, list] = {}
    for node in spec["nodes"]:
        if node["name"] in patterns:
            raise ValueError(f"cell type {node['name']!r} is declared twice")
        patterns[node["name"]] = node["pattern"]
        u, v = _placement(node["pattern"], extent)
        types.append(node["name"])
        us.append(u)
        vs.append(v)
    sizes = np.asarray([u.size for u in us], dtype=np.int64)
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    first = {name: (int(start), int(size)) for name, start, size in zip(types, starts, sizes, strict=True)}
    node_u = np.concatenate(us)
    node_v = np.concatenate(vs)
    node_type = np.repeat(np.asarray(types, dtype=object), sizes)
    n_nodes = int(node_u.size)

    # per type, a dense lookup from column to node index
    span = 2 * extent + 1
    lookup: dict[str, np.ndarray] = {}
    for name, (start, size) in first.items():
        grid = np.full((span, span), -1, dtype=np.int64)
        grid[node_u[start:start + size] + extent, node_v[start:start + size] + extent] = np.arange(
            start, start + size
        )
        lookup[name] = grid

    def find(grid: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        found = np.full(u.shape, -1, dtype=np.int64)
        inside = (u >= -extent) & (u <= extent) & (v >= -extent) & (v <= extent)
        found[inside] = grid[u[inside] + extent, v[inside] + extent]
        return found

    source_parts: list[np.ndarray] = []
    target_parts: list[np.ndarray] = []
    sign_parts: list[np.ndarray] = []
    count_parts: list[np.ndarray] = []
    certainty_parts: list[np.ndarray] = []
    unrealised: list[list[str]] = []

    def emit(sources: np.ndarray, targets: np.ndarray, counts: np.ndarray, edge: dict) -> None:
        n = int(sources.size)
        source_parts.append(sources)
        target_parts.append(targets)
        sign_parts.append(np.full(n, edge["alpha"], dtype=np.float32))
        count_parts.append(counts.astype(np.float32))
        certainty_parts.append(np.full(n, edge["lambda_mult"], dtype=np.float32))

    for edge in spec["edges"]:
        offsets = edge["offsets"]
        if n_syn_fill > 0 and len(offsets) >= 3:
            offsets = fill_hull(offsets, n_syn_fill)
        if edge["src"] not in first or edge["tar"] not in first:
            continue
        s_start, s_size = first[edge["src"]]
        t_start, t_size = first[edge["tar"]]
        kind, args = patterns[edge["src"]]
        before = len(source_parts)

        if broadcast and kind == "single":
            total = float(sum(count for _, count in offsets))
            emit(np.full(t_size, s_start, dtype=np.int64), np.arange(t_start, t_start + t_size),
                 np.full(t_size, total), edge)
        elif target_centric:
            if kind == "single":
                raise ValueError("a target-centric specification needs population_broadcast for single types")
            stride_u, stride_v = (args, args) if kind == "tile" else (int(args[0]), int(args[1]))
            t_index = np.arange(t_start, t_start + t_size, dtype=np.int64)
            t_u = node_u[t_start:t_start + t_size].astype(np.int64)
            t_v = node_v[t_start:t_start + t_size].astype(np.int64)
            s_grid = lookup[edge["src"]]
            found_s: list[np.ndarray] = []
            found_t: list[np.ndarray] = []
            found_n: list[np.ndarray] = []
            for (du, dv), n_syn in offsets:
                sources = find(s_grid, _snap(t_u - int(du), stride_u), _snap(t_v - int(dv), stride_v))
                hit = sources >= 0
                if hit.any():
                    found_s.append(sources[hit])
                    found_t.append(t_index[hit])
                    found_n.append(np.full(int(hit.sum()), float(n_syn)))
            if found_s:
                pair = np.concatenate(found_s) * n_nodes + np.concatenate(found_t)
                unique, inverse = np.unique(pair, return_inverse=True)
                summed = np.zeros(unique.size, dtype=np.float64)
                np.add.at(summed, inverse, np.concatenate(found_n))
                emit(unique // n_nodes, unique % n_nodes, summed, edge)
        else:
            s_index = np.arange(s_start, s_start + s_size)
            s_u = node_u[s_start:s_start + s_size].astype(np.int64)
            s_v = node_v[s_start:s_start + s_size].astype(np.int64)
            t_grid = lookup[edge["tar"]]
            for (du, dv), n_syn in offsets:
                targets = find(t_grid, s_u + int(du), s_v + int(dv))
                hit = targets >= 0
                if hit.any():
                    emit(s_index[hit], targets[hit], np.full(int(hit.sum()), float(n_syn)), edge)

        if len(source_parts) == before:
            unrealised.append([edge["src"], edge["tar"]])

    def cat(parts: list[np.ndarray], dtype) -> np.ndarray:
        return np.concatenate(parts).astype(dtype) if parts else np.zeros(0, dtype=dtype)

    source = cat(source_parts, np.int64)
    target = cat(target_parts, np.int64)

    input_units = set(spec["input_units"])
    output_units = set(spec["output_units"])
    role = {
        name: "input" if name in input_units else "output" if name in output_units else "intermediate"
        for name in types
    }

    nodes = _Table(
        index=np.arange(node_u.size, dtype=np.int64),
        type=node_type.astype(str).astype("S"),
        u=node_u,
        v=node_v,
        role=np.asarray([role[name] for name in node_type]).astype("S"),
    )
    nodes.layer_index = {
        name: np.arange(start, start + size, dtype=np.int64) for name, (start, size) in first.items()
    }
    edges = _Table(
        source_index=source,
        target_index=target,
        sign=cat(sign_parts, np.float32),
        n_syn=cat(count_parts, np.float32),
        source_type=nodes.type[source],
        target_type=nodes.type[target],
        source_u=node_u[source],
        target_u=node_u[target],
        source_v=node_v[source],
        target_v=node_v[target],
        du=(node_u[target] - node_u[source]).astype(np.int32),
        dv=(node_v[target] - node_v[source]).astype(np.int32),
        n_syn_certainty=cat(certainty_parts, np.float32),
    )
    report = {
        "rules": {"target_centric": target_centric, "population_broadcast": broadcast},
        "nodes": n_nodes,
        "edges": int(source.size),
        "connections_in_spec": len(spec["edges"]),
        "connections_unrealised": unrealised,
    }
    return nodes, edges, report


class LatticeConnectome:
    """A connectome the engine accepts, compiled in memory from an average-filter specification.

    Args:
        file: Path of the specification JSON.
        extent: Radius of the hexagonal array, in columns.
        n_syn_fill: Synapses assumed inside the convex hull of each filter where the data report none.
            The reference consensus was measured on a few columns and fills its gaps with one synapse; a
            specification measured on the whole optic lobe has no such gaps, and a missing offset there is
            an absent connection, so it is built with zero.
        digest: Expected SHA-256 of the file. When given, a file with other content is refused.
    """

    def __init__(self, file: str, extent: int = 15, n_syn_fill: float = 0, digest: str | None = None):
        from flyvis.utils import nodes_edges_utils

        path = Path(file)
        actual = spec_digest(path)
        if digest is not None and digest != actual:
            raise ValueError(
                f"{path.name} does not match the graph this network was built on "
                f"(expected {digest[:12]}, found {actual[:12]})"
            )
        self.file = str(path)
        self.digest = actual
        spec = json.loads(path.read_text(encoding="utf-8"))

        self.unique_cell_types = np.bytes_([n["name"] for n in spec["nodes"]])
        self.input_cell_types = np.bytes_(spec["input_units"])
        self.output_cell_types = np.bytes_(spec["output_units"])
        intermediate, _ = nodes_edges_utils.order_node_type_list(
            np.array(
                list(set(self.unique_cell_types) - set(self.input_cell_types) - set(self.output_cell_types))
            ).astype(str)
        )
        self.intermediate_cell_types = np.array(intermediate).astype("S")
        self.layout = np.bytes_(
            [(t, b"retina") for t in self.input_cell_types]
            + [(t, b"intermediate") for t in self.intermediate_cell_types]
            + [(t, b"output") for t in self.output_cell_types]
        )

        self.nodes, self.edges, self.compile_report = compile_spec(spec, extent, n_syn_fill)
        self.central_cells_index = np.int64(np.nonzero((self.nodes.u == 0) & (self.nodes.v == 0))[0])
        if self.central_cells_index.size != self.unique_cell_types.size:
            raise ValueError("every cell type needs exactly one cell at the central column")


def register() -> None:
    """Make the class available to the engine under its registered name. Idempotent."""
    from flyvis.connectome.connectome import AVAILABLE_CONNECTOMES, register_connectome

    if REGISTERED_NAME not in AVAILABLE_CONNECTOMES:
        register_connectome(LatticeConnectome)
    if AVAILABLE_CONNECTOMES.get(REGISTERED_NAME) is not LatticeConnectome:
        raise RuntimeError(f"{REGISTERED_NAME} is registered to another class")
