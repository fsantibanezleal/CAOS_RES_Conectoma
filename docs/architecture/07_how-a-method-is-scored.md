# How a method is scored

Every method in this product is scored the same way, on the same clips, by one stage:
`data-pipeline/conectoma/stages/evaluate.py`, run with `python data-pipeline/run.py evaluate <method>`.
The clips are the ones `build-cases` rendered and `cases.json` records, drawn from geometry families that
are always in the test split, so no method is ever scored on anything it could have been tuned on.

## 1. The metrics, and the conventions behind them

Over the columns where the ground truth is finite and the method claimed a value, with `d` the ground
truth planar depth and `z` the estimate:

```
AbsRel  = (1/N) sum |d - z| / d
RMSE    = sqrt((1/N) sum (d - z)^2)                    metres, metric sources only
delta_k = share with max(d/z, z/d) < 1.25^k,  k = 1, 2, 3
SILog   = (1/N) sum e_i^2 - (1/N^2) (sum e_i)^2        e_i = log z_i - log d_i
```

`SILog` is the scale-invariant error of Eigen, Puhrsch and Fergus (2014), transcribed from section 3.2 of
the paper: their equation 3, with the training loss's `lambda` set to 1, which the paper states is the
scale-invariant error exactly. It is reported in log units squared, not in the KITTI leaderboard's
percentage form, because one name for two conventions is how a number stops being readable.

**Coverage is reported beside every one of them**, always. A method that answers one column in twenty can
look excellent by AbsRel alone, and a method that answers everywhere can look poor for the opposite
reason. Nothing is filled in: a refused column is counted, never guessed.

**Units gate.** RMSE in metres is filled only where the source's depth is metric. Sintel is a
relative-depth source, so a comparison there happens after a least-squares scale and shift in inverse
depth, and the alignment is named wherever the number appears.

**Segmentation and boundaries.** Figure-ground and independent motion are scored by intersection over
union with its precision and recall. The boundary F-score follows Martin, Fowlkes and Malik (2004) in
form, with a tolerance of one lattice step, stated with the metric because a tolerance in pixels means
nothing on a hexagonal lattice.

**Cases where nothing can be measured.** C13 (the camera turns in place) and C14 (nothing moves) have no
parallax by construction. Their grade is not an error: it is the share of columns the method refused. A
method that reports depth everywhere on a pure rotation fails those cases whatever its other numbers look
like. The registry decides which cases those are, through each case's `grades` list.

## 2. The floor, and why every flow-based row is read against it

The stage scores one row that is not a method: `floor`, the readout applied to the flow the corpus
committed. It answers what the arithmetic after the flow costs, and the answer is: almost nothing.
Measured over the first level of every case, eight clips each:

| Case | Coverage | AbsRel |
|---|---|---|
| C01 forest flight | 0.73 | 0.109 |
| C02 urban street | 0.83 | 0.025 |
| C03 hospital corridor | 0.96 | 0.017 |
| C05 city at night | 0.89 | 0.013 |
| C06 motion blur | 0.86 | 0.021 |
| C07 marsh in fog | 0.38 | 0.047 |
| C13 pure rotation | refused 1.00 | not applicable |
| C14 static camera | refused 1.00 | not applicable |
| C15 textured planes | 1.00 | 0.025 |
| C16 textureless surfaces | 1.00 | 0.022 |

So a motion method's error is its flow's error, and a row's distance from this floor is the part of the
error the method owns. The two negative controls are refused completely, which is the answer they grade.

**Where a method cannot run, the report says so instead of leaving a gap.** At the time of writing, of the
sixteen cases: C04 and C09 commit no flow, C10 to C12 (the fly's own eye) commit neither flow nor a camera
motion, and C08 (Sintel) commits flow but no camera pose. Those rows read `skipped`, with the reason, and
the later units that add those inputs will fill them.

## 3. The camera motion, recorded or declared

A TartanAir clip carries the poses the release recorded. A synthetic or panorama clip carries none,
because its camera motion is not measured: it IS the case, and the registry states it
(`cases.step_motion`: the planes slide sideways at a stated speed, the panorama turns at a stated rate,
the static camera does not move at all). A test checks each declared motion against the flow that case's
own rendering committed, so a sign error cannot survive into a published number.

## 4. Comparing two methods

A comparison is **paired on the clip**: the difference is computed per clip and then resampled over clips
(10,000 bootstrap resamples, seed recorded). Pooling two unpaired distributions and comparing their
intervals answers a different question, and on data like this it can invert the sign of the one being
asked.

```bash
python data-pipeline/run.py evaluate M01 --against floor --key abs_rel
```

## 5. What is written

```
data/derived/evaluation/<method>.json        per case and level, the median over clips of every metric,
                                             plus one row per clip so a later comparison can be paired
data/derived/manifests/evaluation.json       which methods were run, over which cases.json, with which
                                             thresholds and which code, and the digest of each report
```

Every threshold a method uses is recorded in the report that used it. The stage reads the clips and
writes its own report: it never re-renders the corpus, so a rerun with a different threshold costs one run
and changes nothing else.

## References

- Eigen, D., Puhrsch, C. and Fergus, R. (2014). Depth map prediction from a single image using a
  multi-scale deep network. NeurIPS 2014. [arXiv:1406.2283](https://arxiv.org/abs/1406.2283)
- Martin, D. R., Fowlkes, C. C. and Malik, J. (2004). Learning to detect natural image boundaries using
  local brightness, color, and texture cues. *IEEE TPAMI* 26(5):530-549.
  [doi:10.1109/TPAMI.2004.1273918](https://doi.org/10.1109/TPAMI.2004.1273918)
