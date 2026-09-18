# Cases

The case registry is the validation design of this product: sixteen cases in six categories, each varying
one physical quantity over six levels with units, so that every method is measured along an axis whose
meaning is physical, not a difficulty knob. The registry is `data-pipeline/config/cases.yaml`; the design,
the variants' physics and the per-source geometry are in [architecture/05](architecture/05_vision-data.md),
and the commands in [guide 05](guides/05_vision-data.md).

## How the registry is built

- **Test data only.** A TartanAir case draws from a geometry family that the split assigns to test, and
  every other source is test-only (Sintel's six sequences held out from the published models, Spring,
  Hypersim's official test partition, FlyGym, the synthetic scenes).
- **The same clips at every level.** A case draws its clips once (eight, or all its source has), and renders
  them at all six levels, so the levels differ only in the quantity the case varies.
- **Physics where it happens.** Light and optics act on the image at source resolution (fog with metric
  depth, blur along each pixel's motion, a crop as a longer lens), photon noise acts on each column's
  photoreceptor, speed acts on time. Ground truth changes only where the physics changes it.
- **Every level measured.** Each rendering records what its level means in the image (the speed in m/s, the
  visibility in metres, the blur in pixels, the column spacing in degrees), and every rendering passes
  contract 1. The tables on each page are generated from the committed `data/derived/vision/cases.json`.

## Taxonomy

| Category | Cases | What it asks |
|---|---|---|
| nominal-outdoor | C01, C02 | how depth from motion degrades with ego speed, in the conditions it is made for |
| nominal-indoor | C03, C04 | long corridors under less light; single indoor images, the non-native condition |
| extreme-lighting | C05 | the photon-noise regime of a night city |
| degradation | C06, C07 | the limits of temporal integration; contrast lost with distance |
| transfer | C08, C09 | the published model's own domain; fine structure at finer sampling |
| ethological | C10, C11, C12 | the fly's own tasks, seen through its own eye |
| controls | C13, C14, C15, C16 | depth unobservable by construction (C13, C14), exact ground truth (C15), the aperture problem (C16) |

## The registry

<!-- measured: generated from data/derived/vision/cases.json by `run.py case-docs`; do not edit -->
<!-- /measured -->

## Reading a case

Each page states why the case exists and which result would count against a method, where its clips come
from and how they were drawn, the physics of its variant with its units, which targets it grades and why
those, what each level measured, and its caveats. Two controls are negative by design: a method that reports
confident depth on C13 or C14 is reporting a prior, not a measurement.
