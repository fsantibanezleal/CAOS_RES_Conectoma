# C01, forest flight

**Category** nominal-outdoor. **Source** TartanAir V2, geometry family SeasonalForest. **Varies** ego speed,
0.5 to 16 times the recorded speed. **Grades** depth, segment boundaries, flow.

## Why this case

A forest is the condition depth from motion is made for: dense texture everywhere, and many depth
discontinuities (trunks in front of trunks) that make parallax large and informative. If a method cannot
recover depth here, it will not recover it anywhere; so the question this case asks is not whether depth is
recovered but how that depends on how fast the camera moves. Too slow and the parallax between frames is
below what the motion detectors resolve; too fast and it exceeds their range or aliases. A method whose
error grows at the fast levels while the ground truth is unchanged has hit the limit of its temporal
sampling, not of its depth estimate.

## The clips

The SeasonalForest family is one geometry under five lights and seasons: SeasonalForestAutumn, Spring,
SummerNight, Winter and WinterNight. The family is always in the test split, so no training clip shares its
geometry. Eight clips of 32 consecutive frames are drawn with the registry's seed, spread round robin over
the five environments, and the same eight are rendered at every level.

## The variant

The frame interval is scaled and every frame kept. The camera passes through exactly the same positions and
sees exactly the same images, only sooner, so a level is exactly the same path flown faster: with the
recorded interval $\Delta t = 0.1$ s, the level $k$ shows the clip at $\Delta t / k$, from 5 Hz ($k = 0.5$) to
160 Hz ($k = 16$). The images, the depth, the boundaries and the flow per frame are unchanged; the flow per
second scales by $k$. The speed in m/s is the median camera step, read from the poses, over the interval.

Temporal subsampling would be the other way to speed a clip up, but it also changes how densely the path is
sampled, and a 32-frame clip cannot be slowed down by it. A network that integrates in its own time step sees
at level $k$ the displacement of $k$ recorded frames per $0.1$ s, as a faster fly would.

## What it grades

Metric depth (TartanAir renders depth in metres), segment boundaries (a column whose box holds more than one
segment ID), and flow in the engine's unit. Not figure-ground: TartanAir's segments carry no names and its
scenes are static, so there is no figure to grade.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- TartanAir's open sky is either beyond its depth range (masked) or a dome several kilometres away (kept);
  depth metrics cap their range.
- The speed variant is exact only for a static scene, which TartanAir's are.
