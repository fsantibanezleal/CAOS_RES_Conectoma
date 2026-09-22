# The methods

One page per method the product runs, added by the unit that builds it. Each page states what the method
consumes, what it computes, what it refuses to answer, and what it measured, with the reference it comes
from. The two pages every method rests on are
[architecture 06](architecture/06_from-flow-to-distance.md), the readout from motion to depth, and
[architecture 07](architecture/07_how-a-method-is-scored.md), how a method is scored.

Classical:

- [M01, motion parallax](methods/m01.md): flow on the lattice, inverted with the camera motion the corpus
  commits. The first native row of the ladder.
- [M02, stereo by semi-global matching](methods/m02.md): two cameras 0.25 m apart and a full pixel grid.
  An UPPER BOUND, not a native row: it sees far more than the eye does, and it is here to bound what a
  classical geometric method gets from these scenes.

Biological, untrained:

- [M03, the Hassenstein-Reichardt array](methods/m03.md): the fly's own elementary motion detector, pooled
  and calibrated, read through the same inversion as M01.
- [M04, the published network with its own decoder](methods/m04.md): the frozen fifty-model ensemble and
  the flow head it was trained with, read through that same inversion, so it differs from M01 only in
  where the flow came from.

Every row above these is added by the unit that builds it.

## What they share

Each of M01, M03 and M04 produces a displacement per column and hands it to the same readout, so a
difference between them is a difference in the displacement and not in the arithmetic. M02 needs no
motion at all, which is why it is an upper bound rather than a competitor. All four are scored by the
same stage, on the same clips, against the same floor.
