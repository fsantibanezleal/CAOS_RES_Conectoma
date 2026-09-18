# C14, static camera

**Category** negative control. **Source** TartanAir V2, environment GreatMarsh (its own geometry family).
**Varies** photon noise, from none down to 1 photon per column per frame. **Grades** uncertainty.

## Why this case

With nothing moving there is no motion signal at all: every frame is the same image, and whatever changes
between frames is noise. Depth from motion is unobservable, as in [C13](C13_pure-rotation.md), but for the
opposite reason: C13 moves without parallax, C14 does not move. Adding photon noise makes the frames differ
without any motion, which is the input a motion detector is most likely to mistake for motion. The case asks
whether a method's uncertainty stays high, and its motion output near zero, as the noise grows.

## The clips

Eight clips of GreatMarsh (in the test split), drawn with this case's own seed. Each clip's first frame is
held for 32 frames at 10 Hz: the same image, the same depth, zero flow everywhere and valid everywhere.

## The variant

Photon noise on each column, as in [C05](C05_city-at-night.md): each column's luminance becomes
$\operatorname{Poisson}(N I) / N$ with $N$ from none to $10^4$, $10^3$, $10^2$, $10$ and $1$ photons per column
per frame at luminance 1, with its own seeded noise in every frame. The signal to noise ratio at the mean
luminance is $\sqrt{N \bar I}$.

## What it grades

The calibration of a method's uncertainty on depth; and, as a check, that the flow it reports stays near the
true zero.

## Measured per level

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Caveats

- Depth is known here (it is the frame's own), but it cannot be seen from motion; a method may still carry
  a depth prior from the image's appearance, and that is what this case exposes.
