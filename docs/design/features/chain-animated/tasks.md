# The chain, animated: tasks

In dependency order, each linked to the requirement it satisfies. The convergence check at the end is the
verdict: every requirement, its gate, and the gate's result.

| # | Task | Satisfies |
|---|---|---|
| 1 | Score the connectome rows on every case they can be scored on. The scoring stage refused M05 and M06 on six cases (C04, C08 to C12, 276 clips) with "the clip carries no poses", a requirement only the geometric rows have, and never aligned Sintel's relative depth although its metrics module documents that it does. Fix both, test both, re-score the eight connectome rows. | R-002 (the readout exported is the scored one, so it must be scored) |
| 2 | `stages/export_chain.py`: per case and both ends of the sweep, the scoring stage's own `m05.run` and `m06.run` at the committed reports' tolerances; depth everywhere, the head's spread, the refusal, the truth; a case or row that cannot be produced is named. | R-001, R-002, R-003, R-004 |
| 3 | The circuit from the committed specification, with the measured direction selectivity. | R-010, R-012 |
| 4 | `run.py export-chain`, the manifest with sizes and digests, and the chain in `scripts/check_artifacts.py` with its budget and its tolerance cross-check. | R-005, R-006 |
| 5 | `frontend/src/lib/chain.ts`: the decoders, the contract, liveliness, drive, the motion-field refusal; the cross-language decoder fixture checked from both sides. | R-011, R-012, R-023, R-026 |
| 6 | `HexMap`, `ChainView`, `CircuitView`; the Response mode opens on the chain, on the liveliest step, with a network switch that keeps the step. | R-020, R-022, R-023, R-025 |
| 7 | The fit gate: four maps painted, opens paused, a pointed column read out everywhere, the switch keeps the step, play changes the drawing and pause stops it; the circuit draws its edges and pulses only while playing. | R-020, R-021, R-022, R-024, R-025 |
| 8 | Screenshots of every new view, both themes, read, not only gated. | the lesson of U-response: a green gate is not a rendered product |

## Convergence

The verdict, one line per requirement, recorded when the unit closed (local gates; CI and the live gate
are recorded in the pull request).

| Requirement | Gate | Result |
|---|---|---|
| R-001 every case at both ends | `tests/test_export_chain.py::test_the_chain_carries_every_case_at_both_ends` | pass, 16 cases, 0 missing |
| R-002 the scored readout | `tests/test_export_chain.py::test_the_readout_is_the_scored_readout` | pass |
| R-003 both regimes | `tests/test_export_chain.py::test_both_regimes_are_carried` | pass |
| R-004 a missing readout is named | `tests/test_export_chain.py::test_a_missing_readout_is_named` | pass |
| R-005 manifest and digests | `scripts/check_artifacts.py` | pass, 16 chain clips |
| R-006 within 6 MB | `tests/test_export_chain.py::test_the_chain_stays_within_its_budget` | pass, 4.8 MB |
| R-010 the specification's own circuit | `tests/test_export_chain.py::test_the_circuit_is_the_specifications_own` | pass, 90 connections |
| R-011 drive | `frontend/src/test/chain.test.ts` | pass |
| R-012 no motion field below 0.1 | `frontend/src/test/chain.test.ts` | pass, measured 0.012 |
| R-020 four maps | `frontend/e2e/fit.mjs` | pass at every size, theme and language |
| R-021 play changes, pause stops | `frontend/e2e/fit.mjs` | pass |
| R-022 a pointed column everywhere | `frontend/e2e/fit.mjs` | pass |
| R-023 opens on the liveliest step | `frontend/src/test/chain.test.ts` | pass |
| R-024 opens paused | `frontend/e2e/fit.mjs` | pass |
| R-025 the switch keeps the step | `frontend/e2e/fit.mjs` | pass |
| R-026 decodes what the pipeline encoded | `frontend/src/test/chain.test.ts` with the shared fixture | pass |

The local fit gate: 1,747 checks passed, 0 failed. Nothing is unmet.
