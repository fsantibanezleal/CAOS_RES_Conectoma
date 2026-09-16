"""Synapse sign from the neurotransmitter prediction.

The connectome measures who connects to whom and how strongly. Whether a connection excites or inhibits is
a separate prediction, made from the electron-microscopy image at each presynaptic site (Eckstein et al.,
"Neurotransmitter classification from electron microscopy images at synaptic sites in Drosophila
melanogaster", Cell, 2024, doi:10.1016/j.cell.2024.03.016; reported accuracy 87 percent per synapse, 94
percent per neuron, 91 percent per known cell type).

This module maps that prediction to a sign, keeps the confidence, and never hides an uncertain call: a
sign below the contract's confidence threshold is flagged, and the sign-shuffled control exists precisely
to measure how much a result depends on these calls.
"""

from __future__ import annotations

from dataclasses import dataclass

# Fast-acting transmitters in the fly, and the sign each implies at its usual receptor.
#
# Acetylcholine is the main excitatory transmitter. GABA is inhibitory. Glutamate is inhibitory at the
# glutamate-gated chloride channel GluClalpha, which is the common case in the optic lobe, and this is the
# same assumption the published connectome-constrained model makes. Histamine is the photoreceptor
# transmitter and is inhibitory at the histamine-gated chloride channel ort. The aminergic transmitters are
# modulatory rather than fast; they are treated as excitatory here and the choice is recorded, because a
# modulator is not a current source in a threshold-linear model.
SIGN_BY_TRANSMITTER: dict[str, int] = {
    "acetylcholine": +1,
    "glutamate": -1,
    "gaba": -1,
    "histamine": -1,
    "dopamine": +1,
    "octopamine": +1,
    "serotonin": +1,
}

MODULATORY = frozenset({"dopamine", "octopamine", "serotonin"})

# Values the release uses when it has no usable call.
UNKNOWN_VALUES = frozenset({None, "", "unclear", "unknown", "none"})


@dataclass(frozen=True)
class SignCall:
    """The sign assigned to a neuron, with everything needed to audit it later."""

    body_id: int
    transmitter: str | None
    sign: int
    confidence: float | None
    source: str  # "body", "cell_type", or "default"
    low_confidence: bool
    modulatory: bool

    def as_dict(self) -> dict:
        return {
            "body_id": self.body_id,
            "transmitter": self.transmitter,
            "sign": self.sign,
            "confidence": self.confidence,
            "source": self.source,
            "low_confidence": self.low_confidence,
            "modulatory": self.modulatory,
        }


def normalize(transmitter: str | None) -> str | None:
    if transmitter is None:
        return None
    value = transmitter.strip().lower()
    return None if value in UNKNOWN_VALUES else value


def call_sign(
    body_id: int,
    consensus_nt: str | None,
    celltype_nt: str | None,
    celltype_confidence: float | None,
    confidence_threshold: float,
    default_sign: int = +1,
) -> SignCall:
    """Assign a sign to one neuron.

    The per-body consensus call is preferred. When the release has none, the cell-type call is used, which
    is the more accurate of the two per the source paper (91 percent per known cell type). When neither
    exists the default sign is applied and the call is marked low confidence, so it can be excluded or
    varied in an ablation instead of silently becoming excitatory.
    """
    body_call = normalize(consensus_nt)
    type_call = normalize(celltype_nt)

    if body_call is not None and body_call in SIGN_BY_TRANSMITTER:
        transmitter, source = body_call, "body"
    elif type_call is not None and type_call in SIGN_BY_TRANSMITTER:
        transmitter, source = type_call, "cell_type"
    else:
        return SignCall(
            body_id=body_id,
            transmitter=None,
            sign=default_sign,
            confidence=celltype_confidence,
            source="default",
            low_confidence=True,
            modulatory=False,
        )

    confidence = celltype_confidence
    low = confidence is not None and confidence < confidence_threshold
    return SignCall(
        body_id=body_id,
        transmitter=transmitter,
        sign=SIGN_BY_TRANSMITTER[transmitter],
        confidence=confidence,
        source=source,
        low_confidence=low,
        modulatory=transmitter in MODULATORY,
    )


def majority_sign(signs: list[int]) -> int:
    """The sign of a cell-type connection, from the signs of its presynaptic neurons.

    A cell type releases one fast transmitter in the overwhelming majority of cases, so disagreement inside
    a type is a signal that the calls are noisy, not that the biology is mixed. The majority wins and the
    caller records the disagreement rate.
    """
    if not signs:
        return +1
    positive = sum(1 for s in signs if s > 0)
    return +1 if positive * 2 >= len(signs) else -1
