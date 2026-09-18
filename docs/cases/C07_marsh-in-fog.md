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
<!-- /measured -->

## Caveats

- Fog is homogeneous and the airlight constant; real fog varies with height and with the sun.
- The same GreatMarsh environment gives the still frames of [C14](C14_static-camera.md), drawn with that
  case's own seed.
