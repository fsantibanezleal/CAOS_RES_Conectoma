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

Recorded when the unit closes, one line per requirement: its gate and the gate's result.
