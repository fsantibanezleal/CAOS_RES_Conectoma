# C05, city at night

**Category** extreme-lighting. **Source** TartanAir V2, environment HongKong (its own geometry family).
**Varies** photon noise, from none down to 1 photon per column per frame at full luminance. **Grades** depth,
segment boundaries, flow.

## Why this case

At night a photoreceptor catches few photons, and the count itself is random: a Poisson process whose
variance equals its mean. Vision in that regime is limited by the photons, not by the optics, and a motion
detector that correlates neighbouring columns over time correlates noise as well. The case asks how depth
from motion degrades as the photon count falls, in a city at night, where the scene is already dark
(measured, the environment's frames average 0.03 to 0.19 in luminance).

## The clips

HongKong is a geometry family of one environment, always in the test split. Eight clips of 32 consecutive
frames are drawn with the registry's seed, and the same eight are rendered at every level.

## The variant

The noise acts on the column, because the photoreceptor under a column counts the photons of its whole
acceptance area. After the lattice rendering, each column's luminance $I$ in each frame becomes

$$\hat I = \frac{\operatorname{Poisson}(N I)}{N},$$

with $N$ the expected photons per column per frame at luminance 1: none, then $10^4$, $10^3$, $10^2$, $10$
and $1$. Each clip and level draws its own seeded noise. The signal to noise ratio at the clip's mean
luminance $\bar I$ is $\sqrt{N \bar I}$; at 10 frames per second, $N$ photons per frame is $10 N$ per second.
Depth, boundaries and flow are the recorded ones: noise changes what is seen, not what is there.

## What it grades

Metric depth, segment boundaries and flow.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- The levels are a physical axis, photons per column, not a calibration to a real light level: no claim is
  made that a given level corresponds to a given hour of the night.
- Only shot noise is modelled; a photoreceptor also has intrinsic noise, which would add to it.
