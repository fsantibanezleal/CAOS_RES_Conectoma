import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { brainProblems, decodeDelta, decodeLevel, STAGES, type BrainClip, type BrainManifest } from '../lib/brain';

// Contract 2 for what the connectome does with a case, against the committed artifacts, read in place.

const DERIVED = new URL('../../../data/derived/', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, DERIVED));
const json = (path: string): unknown => JSON.parse(read(path).toString('utf-8'));

const manifest = json('manifests/brainclips.json') as BrainManifest;
const firstCase = Object.keys(manifest.cases).sort()[0];
const bytes = read(manifest.cases[firstCase].path);
const clip = JSON.parse(bytes.toString('utf-8')) as BrainClip;

describe('the committed brain clips', () => {
  it('declare the pathway in the order the signal travels', () => {
    expect(manifest.types.length).toBeGreaterThan(8);
    expect(manifest.types.slice(0, 3)).toEqual(['L1', 'L2', 'L3']);
    expect(manifest.types).toContain('T4a');
    expect(manifest.types).toContain('T5d');
    // every type drawn has an explanation, so no reader meets a bare four-letter name
    for (const type of manifest.types) expect(STAGES[type]).toBeTruthy();
  });

  it('name the wide-field cells they cannot draw instead of dropping them', () => {
    expect(manifest.wide_field).toContain('CT1');
    expect(manifest.types).not.toContain('CT1');
  });

  it('match their manifest, byte for byte', () => {
    expect(bytes.length).toBe(manifest.cases[firstCase].bytes);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(manifest.cases[firstCase].sha256);
  });

  it('hold what the contract requires', () => {
    expect(brainProblems(clip, manifest.cases[firstCase])).toEqual([]);
  });

  it('decode to the engine units the hover readout shows', () => {
    const level = Object.keys(clip.levels)[0];
    const decoded = decodeLevel(clip, level);
    const type = clip.types[0];
    const values = decoded.values[type];
    expect(values.length).toBe(decoded.steps * clip.columns);
    const scale = decoded.range[type];
    // every value is inside the symmetric scale it was quantised on, and not all of them are the same
    let min = Infinity;
    let max = -Infinity;
    for (const value of values) {
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
    expect(min).toBeGreaterThanOrEqual(-scale * 1.001);
    expect(max).toBeLessThanOrEqual(scale * 1.001);
    expect(max - min).toBeGreaterThan(0);
  });

  it('carry the two ends of each case sweep, at a stated step', () => {
    for (const [, entry] of Object.entries(manifest.cases)) {
      expect(entry.levels).toBeGreaterThanOrEqual(1);
      expect(entry.steps).toBeGreaterThan(10);
    }
    expect(manifest.stride).toBeGreaterThanOrEqual(1);
    expect(manifest.encoding).toBe('delta-int8');
  });
});

describe('the delta decoder', () => {
  it('undoes a difference chain', () => {
    // a first row of 2 columns, then two rows of differences: +1, -3 and then 0, +2
    const bytes = Uint8Array.from([10, 20, 1, 253, 0, 2]);
    const encoded = Buffer.from(bytes).toString('base64');
    const out = decodeDelta(encoded, 3, 2);
    expect(Array.from(out)).toEqual([10, 20, 11, 17, 11, 19]);
  });
});
