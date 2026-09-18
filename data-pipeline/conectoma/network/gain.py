"""Loop gain of a frozen network, and the normalisation that keeps a reservoir stable.

With threshold-linear dynamics, tau dV/dt = -V + W ReLU(V) + b, a small perturbation around any operating
point evolves with the matrix W D, where D is diagonal with ones for active cells and zeros for silent ones.
Every eigenvalue of W D has modulus at most the spectral radius of |W| (the entrywise absolute value of W),
because |W D| <= |W| entrywise and the spectral radius is monotone for non-negative matrices. A spectral
radius of |W| below one therefore guarantees that the network is linearly stable at every operating point:
the echo-state condition of reservoir computing, stated for these dynamics.

The engine's initialisation gives every connection a weight around 0.01, which suits type-level filters with
tens of inputs per cell. The neuron-level visual system has about 119 inputs per cell, mostly excitatory and
recurrent, and from that initialisation its activity runs away (measured). `normalise_gain` scales every
synaptic strength by one factor so that the bound holds, and reports the radius before and after. The factor
is a single number, recorded with the network; the relative strengths of all connections are untouched.
"""

from __future__ import annotations


def absolute_weights(network):
    """Source index, target index and |weight| of every connection, on the network's device."""
    import torch

    def expanded(name: str):
        parameter = network.edge_params[name]
        with torch.no_grad():
            return parameter.semantic_values.detach()[parameter.indices]

    weight = (expanded("sign") * expanded("syn_count") * expanded("syn_strength")).abs()
    return network._source_indices, network._target_indices, weight


def radius_of_matrix(matrix) -> dict:
    """Spectral radius of a non-negative sparse matrix, component by strongly connected component.

    Ordered by its strongly connected components, a matrix is block triangular, so its eigenvalues are those
    of the diagonal blocks, and the feed-forward parts between components contribute nothing. That matters
    here: long feed-forward chains are nilpotent Jordan blocks, the kind of non-normal structure that stalls
    both power iteration and the Arnoldi method, and the decomposition removes them from the problem. Each
    irreducible block is solved exactly when small and by ARPACK's implicitly restarted Arnoldi method (four
    eigenvalues of largest magnitude, so a pair of equal modulus from a two-cell loop does not stall it) when
    large. If a block still does not converge, the smaller of its largest row and column sums, a rigorous
    upper bound, stands in and the result says so.
    """
    import numpy as np
    import scipy.sparse.csgraph as csgraph
    import scipy.sparse.linalg as linalg

    matrix = matrix.tocsr()
    n = matrix.shape[0]
    if matrix.nnz == 0:
        return {"spectral_radius": 0.0, "components": 0, "largest_component": 0, "exact": True}
    count, labels = csgraph.connected_components(matrix, directed=True, connection="strong")
    sizes = np.bincount(labels, minlength=count)
    diagonal = matrix.diagonal()
    best = 0.0
    exact = True
    largest = 0
    residual = 0.0
    for component in range(count):
        members = np.nonzero(labels == component)[0]
        if members.size == 1:
            best = max(best, float(abs(diagonal[members[0]])))
            continue
        block = matrix[members][:, members]
        largest = max(largest, int(members.size))
        if members.size <= 64:
            radius = float(np.max(np.abs(np.linalg.eigvals(block.toarray()))))
        else:
            try:
                values, vectors = linalg.eigs(block, k=min(4, members.size - 2), which="LM", tol=1e-10,
                                              maxiter=20 * members.size)
                index = int(np.argmax(np.abs(values)))
                value, vector = values[index], vectors[:, index]
                radius = float(abs(value))
                scale = max(radius * np.linalg.norm(vector), 1e-300)
                residual = max(residual, float(np.linalg.norm(block @ vector - value * vector) / scale))
            except linalg.ArpackNoConvergence:
                radius = min(float(abs(block).sum(axis=1).max()), float(abs(block).sum(axis=0).max()))
                exact = False
        best = max(best, radius)
    return {
        "spectral_radius": best,
        "components": int(count),
        "largest_component": largest,
        "cells_in_recurrent_components": int(sizes[sizes > 1].sum()),
        "relative_residual": residual,
        "exact": exact,
        "cells": int(n),
    }


def spectral_radius(network) -> dict:
    """The spectral radius of |W| for a network (see `radius_of_matrix`)."""
    import numpy as np
    import scipy.sparse as sparse

    source, target, weight = absolute_weights(network)
    n = network.n_nodes
    values = weight.cpu().numpy().astype(np.float64)
    matrix = sparse.csr_matrix((values, (target.cpu().numpy(), source.cpu().numpy())), shape=(n, n))
    return radius_of_matrix(matrix)


def normalise_gain(network, target: float = 0.9) -> dict:
    """Scale every synaptic strength by one factor so that the spectral radius of |W| is `target` or less."""
    import torch

    before = spectral_radius(network)
    radius = before["spectral_radius"]
    scale = min(1.0, target / radius) if radius > 0 else 1.0
    if scale < 1.0:
        with torch.no_grad():
            network.edge_params["syn_strength"].raw_values.mul_(scale)
    after = spectral_radius(network)
    return {
        "target": target,
        "spectral_radius_before": radius,
        "scale": scale,
        "spectral_radius_after": after["spectral_radius"],
        "exact": before["exact"] and after["exact"],
        "relative_residual": max(before["relative_residual"], after["relative_residual"]),
        "components": before["components"],
        "largest_component": before["largest_component"],
        "cells_in_recurrent_components": before["cells_in_recurrent_components"],
    }


def settled(stability: dict, relative: float = 0.01) -> bool:
    """Finite, and still moving by at most `relative` of its voltage scale in the last half second."""
    scale = max(1.0, abs(stability["min"]), abs(stability["max"]))
    return bool(stability["finite"] and stability["drift_last_half_second"] <= relative * scale)
