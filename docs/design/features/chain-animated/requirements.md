# The chain, animated: requirements

The App shows what the fly's eye receives and what the pathway's cells do, but never what the network
CONCLUDES, and it opens on the first simulated step, where the network is still resting and every map is
flat. This unit adds the rest of the chain and makes it play: the eye's input, the network's depth
readout, the truth it is graded against, the error between them, and the measured circuit carrying the
signal, all on one clock.

Every requirement names the check that fails when it is violated. The gates in `frontend/e2e/fit.mjs` are
labelled with the strings named here, and `scripts/check_sdd.py` refuses a label that does not exist.

## The artifact

```
R-001 THE pipeline SHALL export, for every case and for both ends of its sweep, the depth the connectome
      rows read out of the same clip the eye and response artifacts show, per frame, with that clip's
      ground truth.
      Gate: tests/test_export_chain.py::test_the_chain_carries_every_case_at_both_ends

R-002 THE readout in the chain SHALL be the one the Experiments page scores: the median over the row's
      seeds, refused where the calibrated tolerance in the row's evaluation report refuses it.
      Gate: tests/test_export_chain.py::test_the_readout_is_the_scored_readout

R-003 THE chain SHALL carry both connectome rows, the frozen network (M05) and the network with its
      biophysics trained (M06), so a reader can see on the same clip what training changed.
      Gate: tests/test_export_chain.py::test_both_regimes_are_carried

R-004 IF a readout cannot be produced for a case, THEN THE export SHALL name the case, the row and the
      reason in the artifact, and SHALL NOT write an empty map in its place.
      Gate: tests/test_export_chain.py::test_a_missing_readout_is_named

R-005 THE chain artifact SHALL be listed in its manifest with its size and SHA-256, and the CI SHALL
      re-derive every digest on each push.
      Gate: scripts/check_artifacts.py

R-006 THE chain artifact SHALL stay within 6 MB on disk for all sixteen cases.
      Gate: tests/test_export_chain.py::test_the_chain_stays_within_its_budget
```

## The circuit

```
R-010 THE circuit SHALL draw only connections that exist in the committed connectome specification,
      between the pathway's cell types, with their measured synapse counts and signs.
      Gate: tests/test_export_chain.py::test_the_circuit_is_the_specifications_own

R-011 WHILE the chain plays, THE circuit SHALL show each cell type's activity at the current step as its
      deviation from that type's own resting level, and each connection's drive as the presynaptic
      deviation times the connection's signed weight.
      Gate: frontend/src/test/chain.test.ts::a connection's drive is its source's deviation times its signed weight

R-012 THE App SHALL NOT draw a motion field from T4 and T5 for a network whose measured direction
      selectivity is below 0.1, and the chain SHALL carry that measurement.
      Gate: frontend/src/test/chain.test.ts::a motion field is refused for a network that is not direction selective
```

## The view

```
R-020 THE App SHALL show, in one view and on one clock, the eye's input, the network's depth readout, the
      ground truth and the error between them.
      Gate: frontend/e2e/fit.mjs::chain: the four maps paint 721 columns each

R-021 WHILE the chain plays, THE maps SHALL change, and WHEN it is paused they SHALL stop changing.
      Gate: frontend/e2e/fit.mjs::chain: pressing play changes what is drawn

R-022 WHEN a reader points at a column in any map of the chain, THE App SHALL mark that column in every
      map and read out its input, readout, truth and error.
      Gate: frontend/e2e/fit.mjs::chain: a pointed column is read out in every map

R-023 WHEN the chain opens, THE view SHALL open paused on the step where the pathway moves most, not on
      the first step, where the network is still at rest.
      Gate: frontend/src/test/chain.test.ts::the view opens on the liveliest step, not the first

R-024 THE chain SHALL never start playing by itself, and SHALL stop when the tab is hidden.
      Gate: frontend/e2e/fit.mjs::chain: opens paused

R-025 THE view SHALL let a reader switch the readout between the frozen and the trained network without
      losing the current step.
      Gate: frontend/e2e/fit.mjs::chain: switching the regime keeps the step

R-026 THE chain's readout, truth and error SHALL be decoded from the artifact exactly as the pipeline
      encoded them.
      Gate: frontend/src/test/chain.test.ts::decodes the readout the pipeline encoded
```
