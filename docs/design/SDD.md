# Conectoma, software design document

The product's design, in the eight sections the account's spec-driven rule requires. The research behind
it is in the management repository (`wip/connectome-vision/`, dossiers 01 to 12) and the plan and its
state in `plans/connectome-vision/`. This document says how the product is built and what proves each
part works. Every requirement below names the gate that fails when it is violated, and
`scripts/check_sdd.py` refuses a requirement whose gate does not exist.

This SDD was written after U7, not before U0: the rule that requires it arrived when six units were already
built. It records the design those units implement, the gates that already hold it, and the criteria the
remaining units are built against. A requirement below is binding from now on, and the remaining units
write their gates before their code.

## 1. Problem and non-goals

**The problem.** The Janelia MaleCNS v1.0 connectome measures the fly's visual system cell by cell: which
cells connect, with how many synapses, and with which sign. Conectoma uses that measured wiring as the
architecture of a network, keeps the wiring, the synapse counts and the signs frozen, learns only what the
connectome cannot measure, and asks two questions with controls: does such a backbone recover depth from
the moving images a fly receives, and does any effect come from the biology rather than from the size and
sparsity of the graph?

The primary task is depth from a moving camera, because the fly's visual system is a motion machine and
flies judge distance from parallax. Figure and ground by relative motion is the second native task.
Single-image depth and semantic labels are evaluated as non-native conditions.

**Non-goals.** Each of these is something a reader would reasonably assume, and none of them is in scope:

- A claim that flies compute depth, or segmentation, the way this product asks the network to. The footer
  of every page says so.
- A competitor to depth foundation models. They appear as references, never as the target.
- A whole-brain emulation. The network is the right optic lobe on a 721-column lattice, plus, in M08, the
  neuron-level visual system.
- Simulating the network in the browser. 40,051 cells and 2.9 million connections cannot be simulated
  honestly client-side; every activity the web shows was computed in the pipeline and committed (section 3).
- A motion estimate read off the frozen network's T4 and T5 cells. Measured on moving edges, the frozen
  MaleCNS network's T4 and T5 are not direction selective (direction selectivity index at most 0.012), so
  no page draws them as if they were.

## 2. Contracts

Two contracts, both enforced in code, both checked on every push.

**Contract 1, ingestion (raw to pipeline).** The MaleCNS release tables (Apache Arrow Feather) are read with
their required columns declared, and a table missing one is refused, as is a connection with a
non-positive weight or a self-loop. A vision clip carries 32 frames, luminance on the 721 columns, depth
in metres (or relative, for Sintel, stated), and, where the source provides them, flow, boundaries and
poses; a clip that breaks any of that is rejected with its reason. Outliers are not clipped silently: a
depth beyond the source's valid range is masked and counted.

**Between the two, the connectome specification.** `data/derived/connectome/malecns-optic-lobe-r.json`,
in the engine's own format, carrying its provenance, its column assignment report and its licence.

**Contract 2, artifact (pipeline to web).** Every file the web reads has a manifest entry with its size and
its SHA-256, and the web verifies the digest before drawing. The artifacts are the connectome explorer,
the eye clips (what the columns receive per case), the brain clips (what the pathway does per case), the
chain (what the network concludes per case, U-chain), and the evaluation reports with their summary.

```
R-001 THE pipeline SHALL refuse a MaleCNS release table that is missing a column the build requires.
      Gate: tests/test_connectome_build.py::test_read_feather_rejects_a_table_missing_a_required_column

R-002 IF a vision clip breaks the ingestion contract, THEN THE pipeline SHALL reject it and name the
      reason.
      Gate: tests/test_vision_data.py::test_each_breakage_is_rejected_with_its_reason

R-003 THE committed connectome specification SHALL be the one the committed build produces, with its
      provenance and licence.
      Gate: tests/test_connectome_integration.py::test_artifact_carries_its_provenance_and_licence

R-004 THE web SHALL refuse an artifact whose bytes differ from its manifest's digest.
      Gate: frontend/src/test/contract.test.ts::is the file the manifest describes, byte for byte

R-005 THE CI SHALL re-derive every committed artifact's digest, the split table's leakage test and every
      corpus clip's cache key on each push, and fail on any disagreement.
      Gate: scripts/check_artifacts.py
```

## 3. Lanes

| Lane | What runs there | Measured basis |
|---|---|---|
| Offline pipeline (local GPU, RTX 4070 8 GB) | building the connectome, rendering the corpus, simulating the networks, training heads and regimes, scoring | a forward pass over a 32-frame clip is 0.12 s at batch 4; a training step of the biophysical regime is 0.59 s at batch 2 and peaks at 4.36 GB |
| Committed artifacts, replayed on the web | the eye's input, the pathway's response, the network's readout, every score | the network is 40,051 cells and 2.9 million connections; a browser simulation would be both slow and a different network from the one the numbers come from |
| Live in the browser | nothing yet; U14 decides with a parity and latency gate whether M05 or M06 can run in a Web Worker | U14's gate, not a preference |
| CI | cheap checks only: lint, guards, the artifact contract, the SDD gate, the front-end build and its tests, the fit gate | ADR-0074: no training, no torch, no pipeline test suite in any workflow |

```
R-006 THE CI SHALL never install the training stack or train anything.
      Gate: scripts/check_ci_budget.py

R-007 THE pipeline SHALL train every regime exactly on the parameters that regime declares, and a frozen
      parameter SHALL receive no gradient.
      Gate: tests/test_network_engine.py::test_gradients_respect_the_regime
```

## 4. The method ladder, one acceptance criterion per method

Built methods carry their criterion as a requirement with a gate. Methods not yet built carry the sentence
that will decide whether they are implemented; each becomes a requirement when its unit writes the gate,
before its code.

```
R-010 M01, motion parallax on the lattice, SHALL refuse every column under pure rotation, where depth is
      not observable.
      Gate: tests/test_methods_m01.py::test_pure_rotation_is_refused_everywhere

R-011 M01 SHALL recover the distance of textured planes from a known translation.
      Gate: tests/test_methods_m01.py::test_the_sweep_finds_the_distance_of_a_plane

R-012 M02, stereo by semi-global matching, SHALL recover planes at their depths and refuse an invalid
      disparity rather than fill it.
      Gate: tests/test_methods_m02.py::test_an_invalid_disparity_is_refused_not_filled

R-013 M03, the Hassenstein-Reichardt array, SHALL give a depth on a scene it was not calibrated on.
      Gate: tests/test_methods_m03.py::test_a_calibrated_correlator_gives_a_depth_on_a_scene_it_was_not_fitted_to

R-014 M04, the published network with its own decoder, SHALL produce its depth through the same inversion
      every motion row shares.
      Gate: tests/test_methods_m04.py::test_it_produces_a_depth_through_the_shared_inversion

R-015 M05, the connectome as a reservoir, SHALL read a cached clip and refuse the columns its own
      predicted spread says it cannot read.
      Gate: tests/test_readout.py::test_m05_reads_a_cached_clip_and_refuses_where_it_is_unsure

R-016 M06, the connectome with its biophysics trained, SHALL read each seed's own trained network and name
      a seed whose activity is missing rather than average it away.
      Gate: tests/test_train_network.py::test_m06_names_the_seed_whose_cache_is_missing
```

Not yet built, with the criterion each unit is built against:

| Method | Criterion |
|---|---|
| M07, regime R2 (edge gain) | trains 3,003,002 per-connection parameters with the M06 protocol, and is compared with M06 at matched coverage on the same clips |
| M08, the whole visual system | the neuron-level network, both optic lobes and the visual projection neurons, read through the same head family, with its loop gain held below 1 |
| M09, the dense lattice | the M05 and M06 type filters instantiated on a denser hexagonal lattice, labelled as an engineering extrapolation |
| M10 to M12, learned matched | a matched recurrent CNN and a frozen DINOv2 ViT-S/14 with the same head, three seeds each |
| M13 to M17, foundation references | each with its pinned revision and its licence shown per checkpoint |
| M18 to M22, frontier | distillation and hybrids, each against the row it is distilled from |

## 5. Case taxonomy and coverage matrix

Sixteen cases in the categories below, each rendered at six levels of one physical quantity. Every case
exists to test one thing, and says which grades it carries.

| Case | Name | Category | Varies | Grades | Source |
|---|---|---|---|---|---|
| C01 | forest flight | nominal outdoor | ego speed | depth, boundary, flow | TartanAir |
| C02 | urban street | nominal outdoor | ego speed | depth, boundary, flow | TartanAir |
| C03 | hospital corridor | nominal indoor | illumination | depth, boundary, flow | TartanAir |
| C04 | cluttered room, single image | nominal indoor | field of view | depth, boundary, figure, semantic | Hypersim |
| C05 | city at night | extreme lighting | photon noise | depth, boundary, flow | TartanAir |
| C06 | motion blur | degradation | exposure | depth, boundary, flow | TartanAir |
| C07 | marsh in fog | degradation | fog attenuation | depth, boundary, flow | TartanAir |
| C08 | Sintel, the published model's domain | transfer | contrast | relative depth, flow | Sintel |
| C09 | Spring, fine structure | transfer | sampling | depth, sky | Spring |
| C10 | gap crossing | ethological | gap width | depth, figure | FlyGym |
| C11 | looming object | ethological | approach | depth, figure | FlyGym |
| C12 | small moving target | ethological | target size | depth, figure | FlyGym |
| C13 | pure rotation | negative control | rotation rate | flow, uncertainty | panorama |
| C14 | static camera | negative control | photon noise | uncertainty | TartanAir |
| C15 | textured planes at known depths | positive control | nearest plane depth | depth, flow, figure | synthetic |
| C16 | textureless surfaces | boundary | texture contrast | depth, flow, figure | synthetic |

C13 and C14 exist because a method can be confidently wrong where nothing is observable; they are graded
by what the method refused. C15 exists so that the geometry itself is checked against a scene whose answer
is known exactly, and C16 so that the absence of texture is tested separately from the absence of motion.

```
R-020 THE corpus SHALL be split by geometry family, with no family in more than one split.
      Gate: scripts/check_artifacts.py

R-021 WHERE a case is not observable, THE evaluation SHALL grade a method by what it refused, not by an
      error.
      Gate: tests/test_evaluation.py::test_refusing_everything_is_the_right_answer_where_nothing_is_observable

R-022 THE positive control SHALL render its textured planes exactly at their declared depths.
      Gate: tests/test_vision_cases.py::test_textured_planes_are_exact
```

## 6. The evaluation oracle

Correctness is decided by ground truth the sources render, not by a model: TartanAir, Hypersim, Spring and
FlyGym carry metric depth, Sintel relative depth (scored after alignment, stated), the synthetic cases their
exact planes. The metrics are the depth literature's (AbsRel, RMSE in metres where the depth is metric,
the delta thresholds, and the scale-invariant error of Eigen, Puhrsch and Fergus 2014, equation 3), each
checked against its own arithmetic.

Every flow-based row is read against the **floor**, the committed flow through the same readout, so a
row's error is read against the representation's own limit. A connectome row's claim is never its own
number: it is the paired difference per clip against its nulls built from the same wiring (N1
degree-preserving rewiring, N2 size-matched random sparse, N3 sign shuffle), with the same head and seeds,
aggregated by a bootstrap over clips. Two trained rows are compared at **matched coverage**, over the same
share of the lattice ranked by each row's own predicted uncertainty, because their calibrated refusal
thresholds differ (measured coverage 0.40 to 0.72) and the error of what a row chose to keep is not
comparable.

```
R-030 THE scale-invariant error SHALL be the paper's equation 3.
      Gate: tests/test_methods_metrics.py::test_silog_is_the_papers_equation_three

R-031 A comparison between two rows SHALL be paired on the clip.
      Gate: tests/test_methods_metrics.py::test_the_paired_difference_is_paired

R-032 A comparison between two trained rows SHALL be read at matched coverage.
      Gate: tests/test_train_network.py::test_a_comparison_between_trained_rows_is_read_at_matched_coverage

R-033 Every null control SHALL hold its invariants on the measured connectome.
      Gate: tests/test_null_controls.py::test_controls_hold_their_invariants_on_the_measured_connectome

R-034 THE product SHALL rebuild the published model through its own compiler and match the engine voltage
      for voltage, before any claim rests on that compiler.
      Gate: tests/test_network_engine.py::test_the_published_model_rebuilt_here_matches_the_engine_voltage_for_voltage
```

## 7. The deploy driver

GitHub Pages at `conectoma.fasl-work.com`, because the repository is public and the product is static
replay. The driver is the measured size of what is served: 32 MB for the built site today (eye clips
7.4 MB, brain clips 20 MB, evaluation 6.4 MB, explorer 1.2 MB), against Pages limits of 1 GB per site and
100 MB per file. The fallback, a static host on the ML box, is taken only if a measured bake exceeds a
quarter of the Pages site limit or any single artifact exceeds 50 MB; neither holds.

```
R-040 THE App SHALL fit its containers, keep its chrome on one row and keep every surface reachable at
      every viewport, theme and language the gate measures.
      Gate: frontend/e2e/fit.mjs

R-041 THE product content SHALL carry no em-dash and no emoji.
      Gate: scripts/check_content_standards.py
```

## 8. Risks and kill criteria

| Risk | What would show it | Response |
|---|---|---|
| The measured wiring does no better than its controls | a paired interval at matched coverage that crosses zero or favours the control, in every regime | reported first on the Experiments page; a negative answer is a result, stated since the plan was validated. It already holds against N2 in R0 and R1 |
| A regime cannot be trained on the local GPU | R2's memory at batch 2 above 7 GB, measured before its run | escalate to the cloud path in the plan, never shrink the protocol |
| A number is right on the page and wrong in the engine | an audit against the call graph, not against the other pages | the U7 audit found two such defects (a cache key, a coverage confound) and both are gated now |
| A gate is green while measuring the wrong thing | a rendered defect found in a screenshot the gate passed | fix the gate first, then the defect, then look again |

**Kill criterion for the product's central claim:** if, after M05 to M09, no regime's measured wiring beats
its degree-preserving control at matched coverage with an interval excluding zero, the claim that the
specific wiring carries the result is withdrawn, and the product is reframed as what it then shows: a
measurement of how much of the result the degree structure and the graph's size carry.
