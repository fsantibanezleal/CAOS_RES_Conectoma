import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { decodeLevel, type BrainClip, type BrainManifest } from '../lib/brain';
import {
  chainProblems, circuitProblems, decodeChainLevel, decodeDepth, decodeMask, decodeSpread, driveOf,
  frameOfRow, liveliestStep, motionFieldAllowed, rowOfFrame, MOTION_FIELD_DSI,
  type ChainClip, type ChainManifest, type Circuit,
} from '../lib/chain';

// Contract 2 for what the network concludes from each case, against the committed artifacts, read in place,
// and the behaviour the chain view depends on (docs/design/features/chain-animated/requirements.md).

const DERIVED = new URL('../../../data/derived/', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, DERIVED));
const json = (path: string): unknown => JSON.parse(read(path).toString('utf-8'));
const fixture = JSON.parse(readFileSync(new URL('./fixtures/chain-decoder.json', import.meta.url), 'utf-8'));

const manifest = json('manifests/chain.json') as ChainManifest;
const caseIds = Object.keys(manifest.cases).sort();

describe('the chain decoder', () => {
  it('decodes the readout the pipeline encoded', () => {
    // the same bytes the pipeline's own decoder is checked against in tests/test_export_chain.py
    const depth = decodeDepth(fixture.depth.bytes, { lo_m: fixture.encoding.lo_m, hi_m: fixture.encoding.hi_m, zero: '' });
    fixture.depth.metres.forEach((metres: number | null, i: number) => {
      if (metres === null) expect(Number.isNaN(depth[i])).toBe(true);
      else expect(depth[i]).toBeCloseTo(metres, 3);
    });
    const spread = decodeSpread(fixture.spread.bytes, fixture.encoding.spread_hi);
    fixture.spread.values.forEach((value: number, i: number) => expect(spread[i]).toBeCloseTo(value, 6));
    const mask = decodeMask(fixture.mask.bytes, fixture.mask.rows);
    fixture.mask.set.forEach((columns: number[], row: number) => {
      const set = [];
      for (let c = 0; c < 721; c++) if (mask[row * 721 + c]) set.push(c);
      expect(set).toEqual(columns);
    });
  });

  it('maps a frame to the step row it begins at, and back', () => {
    // five simulated steps a frame, every third one kept: frame 3 begins at step 15, which is row 5
    expect(rowOfFrame(3, 5, 3, 54)).toBe(5);
    expect(frameOfRow(5, 5, 3, 32)).toBe(3);
    expect(rowOfFrame(1000, 5, 3, 54)).toBe(53);
    expect(frameOfRow(0, 5, 3, 32)).toBe(0);
  });
});

describe('the committed chain', () => {
  it('lists every case the registry renders, and names what is missing', () => {
    expect(caseIds.length).toBe(16);
    expect(typeof manifest.missing).toBe('object');
  });

  it('matches its manifest, byte for byte, and holds the contract', () => {
    for (const caseId of caseIds) {
      const entry = manifest.cases[caseId];
      const bytes = read(entry.path);
      expect(bytes.length).toBe(entry.bytes);
      expect(createHash('sha256').update(bytes).digest('hex')).toBe(entry.sha256);
      const clip = JSON.parse(bytes.toString('utf-8')) as ChainClip;
      expect(chainProblems(clip, entry)).toEqual([]);
    }
  });

  it('carries both networks, decodable, for the first case', () => {
    const clip = json(manifest.cases[caseIds[0]].path) as ChainClip;
    const level = Object.keys(clip.levels)[0];
    const decoded = decodeChainLevel(clip, level, manifest);
    for (const row of ['M05', 'M06'] as const) {
      const data = decoded.rows[row];
      expect(data, `${row} is in the chain`).toBeTruthy();
      expect(data!.depth.length).toBe(decoded.steps * 721);
      let finite = 0;
      for (const v of data!.depth) if (v > 0) finite += 1;
      expect(finite).toBeGreaterThan(0);
    }
  });
});

describe('the circuit', () => {
  const circuit = json(manifest.circuit.path) as Circuit;

  it('matches its manifest and holds the contract', () => {
    const bytes = read(manifest.circuit.path);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(manifest.circuit.sha256);
    expect(circuitProblems(circuit)).toEqual([]);
    expect(circuit.edges.length).toBeGreaterThan(20);
  });

  it("a connection's drive is its source's deviation times its signed weight", () => {
    const inhibitory = { source: 'Mi9', target: 'T4a', synapses: 12, sign: -1 };
    const excitatory = { source: 'Mi1', target: 'T4a', synapses: 30, sign: 1 };
    expect(driveOf(inhibitory, 0.5)).toBeCloseTo(-6);
    expect(driveOf(excitatory, 0.5)).toBeCloseTo(15);
    expect(driveOf(excitatory, -0.5)).toBeCloseTo(-15);
    expect(driveOf(excitatory, 0)).toBe(0);
  });

  it('a motion field is refused for a network that is not direction selective', () => {
    // the frozen network's measured selectivity is carried with the circuit, and it is far below the bar
    expect(circuit.direction_selectivity.largest).toBeLessThan(MOTION_FIELD_DSI);
    expect(motionFieldAllowed(circuit.direction_selectivity.largest)).toBe(false);
    expect(motionFieldAllowed(null)).toBe(false);
    expect(motionFieldAllowed(0.3)).toBe(true);
  });
});

describe('where the view opens', () => {
  it('the view opens on the liveliest step, not the first', () => {
    // a synthetic pathway at rest everywhere but step 7
    const steps = 12;
    const values: Record<string, Float32Array> = { A: new Float32Array(steps * 721), B: new Float32Array(steps * 721) };
    for (let c = 0; c < 721; c++) { values.A[7 * 721 + c] = 3; values.B[7 * 721 + c] = -2; }
    expect(liveliestStep(values, { A: 0, B: 0 }, { A: 1, B: 1 }, steps)).toBe(7);

    // and on a committed clip, the network is not liveliest while it is still at rest
    const brainManifest = json('manifests/brainclips.json') as BrainManifest;
    const first = Object.keys(brainManifest.cases).sort()[0];
    const brain = json(brainManifest.cases[first].path) as BrainClip;
    const level = Object.keys(brain.levels)[0];
    const decoded = decodeLevel(brain, level);
    expect(liveliestStep(decoded.values, decoded.centre, decoded.spread, decoded.steps)).toBeGreaterThan(0);
  });
});
