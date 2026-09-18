# C06, motion blur

**Category** degradation. **Source** TartanAir V2, environment Office (its own geometry family). **Varies**
exposure, 0 to 160 ms. **Grades** depth, segment boundaries, flow.

## Why this case

Every eye integrates light over time, and what moves during the integration is smeared along its motion. The
smear removes exactly the fine detail along the direction of motion that a motion detector compares from one
column to the next, so depth from motion is pulled two ways by a long exposure: more light, less detail.
The case asks where that trade turns against a method, in an office, whose desks, chairs and shelves give
edges at many depths.

## The clips

Office is a geometry family of one environment, always in the test split. Eight clips of 32 consecutive
frames are drawn with the registry's seed, and the same eight are rendered at every level.

## The variant

An exposure of $T_e$ averages each pixel along its own image motion, centred on the frame's instant:

$$\hat I(p) = \frac{1}{T_e} \int_{-T_e/2}^{T_e/2} I\Big(p + \frac{t}{\Delta t}\,\mathbf f(p)\Big)\,dt,$$

with $\mathbf f(p)$ the pixel's flow to the next frame (the last frame uses the flow into it) and
$\Delta t = 0.1$ s the frame interval. A pixel moving $|\mathbf f|$ pixels per frame is smeared over
$|\mathbf f|\,T_e / \Delta t$ pixels, so near things blur more than far ones, as they do in a real exposure.
The integral is sampled densely enough that consecutive samples are at most half a pixel apart. At 160 ms
the exposure spans 1.6 frames of motion. The blur acts on the image before the lattice; depth, boundaries and
flow are the recorded ones.

## What it grades

Metric depth, segment boundaries and flow.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- Motion within the exposure is taken as the frame's own flow, straight and uniform; curved motion and
  occlusion boundaries within the exposure are approximated.
- The level is the exposure; the blur in pixels is its consequence, recorded per level as the median over
  every pixel of the clip.
