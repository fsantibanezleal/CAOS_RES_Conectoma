"""The readout head: the only part of a connectome row that knows what depth is.

Everything before it is measured biology, frozen. The head sees the rectified voltage of the cell types
the connectome declares as its outputs (`T4a` to `T5d` for the MaleCNS optic lobe), on the 721 columns,
over a short temporal window, and produces three channels per column:

    log depth      what the column is looking at, in log metres
    log sigma      how sure it is, in the same log units, trained rather than assumed
    boundary       the logit that the column's box straddles more than one surface

The uncertainty channel is what lets a trained row REFUSE. A method that must answer everywhere cannot be
graded on the cases where nothing is observable (C13, pure rotation; C14, a static camera), and those
cases are graded by what was refused. Training it is a Gaussian likelihood in log depth,

    L = mean( 0.5 exp(-2 s) e^2 + s ),   e = log z - log d,  s = log sigma

which is the negative log likelihood of a Gaussian whose spread the head also predicts: a column it cannot
read is cheaper to mark wide than to guess. The scale-invariant error of Eigen, Puhrsch and Fergus (2014)
is reported beside it at every evaluation, not optimised, so the number in the report and the number in
the loss are never confused.

The architecture is the published decoder's form (dossier 06 section 1.4): the columns are laid on the
hexagonal lattice as a square map, a small convolution stack runs over it, and the answer is gathered back
to the columns. Every arm of the comparison, the connectome and its three nulls, gets exactly this head,
this optimiser and these seeds; only the network in front of it differs.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from conectoma.vision import eye

COLUMNS = 721


def hex_map_indices(extent: int = eye.EXTENT) -> tuple[np.ndarray, np.ndarray, int, int]:
    """(u, v) of every column shifted to non-negative, and the size of the square map that holds them."""
    coordinates = eye.lattice_coordinates(extent)
    u = coordinates[:, 0] - coordinates[:, 0].min()
    v = coordinates[:, 1] - coordinates[:, 1].min()
    return u, v, int(u.max()) + 1, int(v.max()) + 1


class Readout(nn.Module):
    """A small hex-space convolution stack from output-unit activity to depth, spread and boundary."""

    def __init__(self, types: int = 8, window: int = 2, width: int = 16, kernel: int = 5,
                 extent: int = eye.EXTENT, mean: list[float] | None = None,
                 std: list[float] | None = None, log_depth_offset: float = 0.0):
        super().__init__()
        u, v, height, span = hex_map_indices(extent)
        self.register_buffer("u", torch.as_tensor(u, dtype=torch.long))
        self.register_buffer("v", torch.as_tensor(v, dtype=torch.long))
        # the training split's own statistics, carried with the head: activity in, log depth out
        self.register_buffer("mean", torch.as_tensor(mean if mean is not None else [0.0] * types,
                                                     dtype=torch.float32).view(1, 1, types, 1))
        self.register_buffer("std", torch.as_tensor(std if std is not None else [1.0] * types,
                                                    dtype=torch.float32).view(1, 1, types, 1))
        self.register_buffer("log_depth_offset", torch.as_tensor(float(log_depth_offset)))
        self.height, self.span = height, span
        self.window = window
        self.types = types
        padding = kernel // 2
        self.stack = nn.Sequential(
            nn.Conv2d(types * window, width, kernel, padding=padding),
            nn.ReLU(),
            nn.Conv2d(width, width, kernel, padding=padding),
            nn.ReLU(),
            nn.Conv2d(width, 3, 1),
        )

    @property
    def parameter_count(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def forward(self, activity: torch.Tensor) -> torch.Tensor:
        """(batch, window, types, columns) activity to (batch, 3, columns).

        The activity is standardised by the training split's per-type statistics and rectified, as the
        published decoder rectifies its input, and the depth channel is an offset from the training
        split's median log depth: a head that starts at zero then starts at the middle of the corpus
        rather than at one metre.
        """
        batch = activity.shape[0]
        scaled = torch.relu((activity - self.mean) / self.std)
        flat = scaled.reshape(batch, self.window * self.types, COLUMNS)
        grid = activity.new_zeros((batch, self.window * self.types, self.height, self.span))
        grid[:, :, self.u, self.v] = flat
        out = self.stack(grid)[:, :, self.u, self.v]
        return torch.stack([out[:, 0] + self.log_depth_offset, out[:, 1], out[:, 2]], dim=1)


def windows(activity: torch.Tensor, window: int) -> torch.Tensor:
    """(frames, types, columns) to (frames, window, types, columns), the frame and what came before it.

    The first frames have nothing behind them, so they repeat the first frame: a clip never borrows a
    frame from another clip, and the head always sees the same shape.
    """
    frames = activity.shape[0]
    index = torch.arange(frames, device=activity.device)[:, None] - torch.arange(window - 1, -1, -1,
                                                                                device=activity.device)
    return activity[index.clamp(min=0)]


def depth_loss(prediction: torch.Tensor, truth: torch.Tensor) -> tuple[torch.Tensor, dict]:
    """Gaussian negative log likelihood in log depth, over the columns whose truth is finite."""
    log_depth, log_sigma = prediction[:, 0], prediction[:, 1]
    known = torch.isfinite(truth) & (truth > 0)
    if not known.any():
        zero = prediction.sum() * 0.0
        return zero, {"columns": 0}
    error = log_depth[known] - torch.log(truth[known])
    spread = log_sigma[known].clamp(-6.0, 6.0)
    loss = (0.5 * torch.exp(-2 * spread) * error**2 + spread).mean()
    with torch.no_grad():
        silog = (error**2).mean() - error.mean() ** 2
        absrel = ((torch.exp(log_depth[known]) - truth[known]).abs() / truth[known]).mean()
    return loss, {"columns": int(known.sum()), "silog": float(silog), "abs_rel": float(absrel)}


def boundary_loss(prediction: torch.Tensor, truth: torch.Tensor) -> tuple[torch.Tensor, dict]:
    """Binary cross entropy on the boundary channel, where the clip carries one."""
    logit = prediction[:, 2]
    target = truth.to(logit.dtype)
    loss = nn.functional.binary_cross_entropy_with_logits(logit, target)
    with torch.no_grad():
        correct = ((logit > 0) == (target > 0.5)).float().mean()
    return loss, {"boundary_accuracy": float(correct), "boundary_share": float(target.mean())}


def predictions(prediction: torch.Tensor) -> dict[str, np.ndarray]:
    """The head's three channels as what the scoring stage reads: metres, a relative spread, a mask."""
    log_depth = prediction[:, 0].detach().cpu().numpy()
    log_sigma = prediction[:, 1].detach().cpu().numpy().clip(-6.0, 6.0)
    boundary = prediction[:, 2].detach().cpu().numpy()
    return {
        "distance_m": np.exp(log_depth).astype(np.float32),
        # sigma is a spread in log depth, which IS a relative uncertainty in depth
        "uncertainty": np.exp(log_sigma).astype(np.float32),
        "boundary": (boundary > 0),
    }
