# C07, marsh in fog

**Category** degradation. **Source** TartanAir V2, environment GreatMarsh (its own geometry family).
**Varies** fog attenuation, 0 to 0.2 per metre. **Grades** depth, segment boundaries, flow.

## Why this case

Fog takes contrast away in proportion to distance: near things keep theirs, far things fade into the
airlight. A motion detector needs contrast to see motion, so fog removes the parallax of exactly the far
structure whose depth is hardest to estimate. It is also a depth cue in its own right (aerial perspective),
which a method may learn to read. The case asks how depth degrades as visibility falls from unlimited to
about 20 metres, in an open marsh where the depth range runs to the horizon.

## The clips

GreatMarsh is a geometry family of one environment, always in the test split. Eight clips of 32 consecutive
frames are drawn with the registry's seed, and the same eight are rendered at every level.

## The variant

Each pixel's light is attenuated by its own metric depth $d$ and replaced by airlight:

$$I' = I\,e^{-b d} + A\,(1 - e^{-b d}),$$

with $b$ the attenuation per metre and airlight $A = 0.7$. Depth masked as beyond range (the open sky) is
taken as infinitely far and becomes pure airlight. The meteorological visibility is the distance at which an
object keeps 2 percent of its contrast, $V = -\ln(0.02) / b = 3.912 / b$ (Koschmieder): from unlimited at
$b = 0$ to about 20 m at $b = 0.2$. The fog acts on the image before the lattice; depth, boundaries and flow
are the recorded ones.

## What it grades

Metric depth, segment boundaries and flow.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | visibility (m) | RMS contrast | mean luminance | median depth (m) |
|---|---|---|---|---|---|---|
| 0 1/m | 8 of 8 | 100 | n/a | 0.0725 | 0.661 | 21.6 |
| 0.01 1/m | 8 of 8 | 100 | 391 | 0.0616 | 0.66 | 21.6 |
| 0.02 1/m | 8 of 8 | 100 | 196 | 0.0576 | 0.664 | 21.6 |
| 0.05 1/m | 8 of 8 | 100 | 78.2 | 0.0476 | 0.672 | 21.6 |
| 0.1 1/m | 8 of 8 | 100 | 39.1 | 0.0353 | 0.68 | 21.6 |
| 0.2 1/m | 8 of 8 | 100 | 19.6 | 0.0166 | 0.69 | 21.6 |

Medians over the clips of each level. Drawn: `GreatMarsh/easy/P009/001208`, `GreatMarsh/easy/P006/000790`, `GreatMarsh/hard/P009/001927`, `GreatMarsh/hard/P005/001678`, `GreatMarsh/easy/P008/003658`, `GreatMarsh/hard/P007/000826`, `GreatMarsh/easy/P007/001461`, `GreatMarsh/hard/P002/000877`.
<!-- /measured -->

## Caveats

- Fog is homogeneous and the airlight constant; real fog varies with height and with the sun.
- The same GreatMarsh environment gives the still frames of [C14](C14_static-camera.md), drawn with that
  case's own seed.
