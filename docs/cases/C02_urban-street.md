# C02, urban street

**Category** nominal-outdoor. **Source** TartanAir V2, environment VictorianStreet (its own geometry
family). **Varies** ego speed, 0.5 to 16 times the recorded speed. **Grades** depth, segment boundaries, flow.

## Why this case

A street is the opposite texture statistics to a forest: large planar facades, long straight edges, and
occlusion boundaries where one building ends in front of the next. Planes are where motion is ambiguous
along their edges and informative at their corners, and occlusion edges are where depth jumps. The case asks
the same question as [C01](C01_forest-flight.md), how depth from motion depends on ego speed, in a scene
whose structure is built rather than grown, so that a method's speed limit can be separated from the scene it
was measured in.

## The clips

VictorianStreet is a geometry family of one environment, always in the test split. Eight clips of 32
consecutive frames are drawn with the registry's seed from its trajectories (both difficulties), and the
same eight are rendered at every level.

## The variant

As in C01: the frame interval is scaled, $\Delta t / k$ with $\Delta t = 0.1$ s and $k$ from 0.5 to 16, every
frame kept, so each level is exactly the same path flown $k$ times faster. The speed in m/s is the median
camera step from the poses over the interval.

## What it grades

Metric depth, segment boundaries and flow. Not figure-ground (TartanAir's segments are unnamed and its scenes
static).

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
| level | clips | frame interval (ms) | speed (m/s) | frame rate (Hz) | median depth (m) | flow per frame (engine units) |
|---|---|---|---|---|---|---|
| 0.5 times the recorded speed | 8 of 8 | 200 | 1.08 | 5.00 | 3.81 | 8.15 |
| 1.00 times the recorded speed | 8 of 8 | 100 | 2.16 | 10.0 | 3.81 | 8.15 |
| 2.00 times the recorded speed | 8 of 8 | 50.0 | 4.31 | 20.0 | 3.81 | 8.15 |
| 4.00 times the recorded speed | 8 of 8 | 25.0 | 8.63 | 40.0 | 3.81 | 8.15 |
| 8.00 times the recorded speed | 8 of 8 | 12.5 | 17.3 | 80.0 | 3.81 | 8.15 |
| 16.0 times the recorded speed | 8 of 8 | 6.25 | 34.5 | 160 | 3.81 | 8.15 |

Medians over the clips of each level. Drawn: `VictorianStreet/easy/P003/000477`, `VictorianStreet/easy/P000/000616`, `VictorianStreet/easy/P004/000097`, `VictorianStreet/easy/P005/000101`, `VictorianStreet/hard/P001/000087`, `VictorianStreet/easy/P006/000489`, `VictorianStreet/hard/P000/000118`, `VictorianStreet/hard/P005/000202`.
<!-- /measured -->

## Caveats

- Mean luminance varies widely between the street's clips (from 0.09 to 0.52 in sampled frames); light
  level as a controlled variable is C03's and C05's.
- As in C01, the sky is masked where beyond range and kept where modelled as a distant dome.
