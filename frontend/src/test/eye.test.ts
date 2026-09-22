import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { base64Bytes, COLUMNS, decodeLevel, depthOf, eyeClipProblems, eyeManifestProblems, type EyeClip, type EyeManifest } from '../lib/eye';
import { statistic } from '../eye/TimeCourse';

// Contract 2 for the eye's input against the committed artifacts, read in place from data/derived. Every case
// file must be the bytes its manifest declares, hold six levels of 721 columns, and decode to values in range.

const DERIVED = new URL('../../../data/derived/', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, DERIVED));
const json = (path: string): unknown => JSON.parse(read(path).toString('utf-8'));

const manifest = json('manifests/eyeclips.json') as EyeManifest;
const clone = <T>(x: T): T => structuredClone(x);

describe('the committed eye manifest', () => {
  it('matches its contract', () => {
    expect(eyeManifestProblems(manifest)).toEqual([]);
  });

  it('lists all sixteen cases', () => {
    expect(Object.keys(manifest.cases).sort()).toEqual(Array.from({ length: 16 }, (_, i) => `C${String(i + 1).padStart(2, '0')}`));
  });

  it('places every column where the engine samples it: 13 pixels apart, within the 391 pixel window', () => {
    const { row_px: rows, col_px: cols, u, v } = manifest.lattice;
    for (let c = 0; c < COLUMNS; c++) {
      expect(cols[c]).toBe(Math.trunc(13 * v[c]));
      expect(rows[c]).toBe(Math.trunc(13 * (u[c] + v[c] / 2)));
      expect(Math.abs(rows[c])).toBeLessThanOrEqual(195);
      expect(Math.abs(cols[c])).toBeLessThanOrEqual(195);
    }
  });
});

describe('every committed eye clip', () => {
  for (const [id, entry] of Object.entries(manifest.cases)) {
    it(`${id} is its manifest's bytes, matches the contract and decodes in range`, () => {
      const bytes = read(entry.path);
      expect(bytes.length).toBe(entry.bytes);
      expect(createHash('sha256').update(bytes).digest('hex')).toBe(entry.sha256);
      const clip = JSON.parse(bytes.toString('utf-8')) as EyeClip;
      expect(eyeClipProblems(clip, id)).toEqual([]);
      const levels = clip.levels.map((_, i) => decodeLevel(clip, i));
      for (const level of levels) {
        expect(level.lum.length).toBe(clip.frames * COLUMNS);
        expect(level.depth.length).toBe(clip.frames * COLUMNS);
        const codes = new Set(level.depth);
        // at least some columns carry a depth, and every coded depth decodes inside the declared range
        expect([...codes].some((c) => c !== 255)).toBe(true);
        for (const code of codes) {
          const d = depthOf(code, clip.depth.near_m, clip.depth.far_m);
          if (code === 255) expect(Number.isNaN(d)).toBe(true);
          else {
            expect(d).toBeGreaterThanOrEqual(clip.depth.near_m * (1 - 1e-9));
            expect(d).toBeLessThanOrEqual(clip.depth.far_m * (1 + 1e-9));
          }
        }
        const mean = statistic('lum', clip, level, 0);
        expect(mean).not.toBeNull();
        expect(mean!).toBeGreaterThanOrEqual(0);
        expect(mean!).toBeLessThanOrEqual(1);
      }
    });
  }
});

describe('the eye contract refuses', () => {
  const [id, entry] = Object.entries(manifest.cases)[0];
  const clip = JSON.parse(read(entry.path).toString('utf-8')) as EyeClip;

  it('a case file of another case', () => {
    expect(eyeClipProblems(clip, 'C99').join()).toMatch(/case/);
  });

  it('a level missing its luminance', () => {
    const c = clone(clip);
    delete c.levels[2].arrays.lum;
    expect(eyeClipProblems(c, id).join()).toMatch(/luminance/);
  });

  it('an array of the wrong length', () => {
    const c = clone(clip);
    c.levels[1].arrays.lum = c.levels[1].arrays.lum!.slice(0, -8);
    expect(eyeClipProblems(c, id).join()).toMatch(/bytes/);
  });

  it('a newer artifact version', () => {
    const c = clone(clip);
    c.version = 2;
    expect(eyeClipProblems(c, id).join()).toMatch(/version/);
  });

  it('a manifest path outside the artifact', () => {
    const m = clone(manifest);
    m.cases[id].path = '../secrets.json';
    expect(eyeManifestProblems(m).join()).toMatch(/path/);
  });

  it('counts base64 bytes without decoding', () => {
    expect(base64Bytes(btoa('abcde'))).toBe(5);
    expect(base64Bytes(btoa('abcdef'))).toBe(6);
  });
});
