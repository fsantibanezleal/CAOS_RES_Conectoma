import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { countProblems, explorerProblems, manifestProblems } from '../lib/contract';
import type { Explorer, ExplorerManifest } from '../lib/contract.types';
import { REPORTS } from '../lib/reports';

// Contract 2 against the committed artifacts, read in place from data/derived (never written). A pipeline
// change the web did not follow, or a web change the pipeline does not produce, fails here and so fails the
// build.

const DERIVED = new URL('../../../data/derived/', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, DERIVED));
const json = (path: string): unknown => JSON.parse(read(path).toString('utf-8'));

const manifest = json('manifests/explorer.json') as ExplorerManifest;
const bytes = read(manifest.path);
const explorer = JSON.parse(bytes.toString('utf-8')) as Explorer;
const clone = <T>(x: T): T => structuredClone(x);

describe('the committed explorer artifact', () => {
  it('matches the manifest contract', () => {
    expect(manifestProblems(manifest)).toEqual([]);
  });

  it('matches the explorer contract', () => {
    expect(explorerProblems(explorer)).toEqual([]);
  });

  it('is the file the manifest describes, byte for byte', () => {
    expect(bytes.length).toBe(manifest.bytes);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(manifest.sha256);
  });

  it('holds the counts the manifest declares', () => {
    expect(countProblems(explorer, manifest)).toEqual([]);
  });

  it('writes offsets in the engine frame', () => {
    expect(explorer.frame?.release_to_engine).toBe(-1);
  });
});

describe('the contract catches drift', () => {
  it('a renamed connection field', () => {
    const e = clone(explorer);
    e.connection_fields = ['source', 'target', 'sign', 'certainty', 'du', 'dv', 'count'];
    expect(explorerProblems(e).join()).toMatch(/connection_fields/);
  });

  it('a connection that points past the types', () => {
    const e = clone(explorer);
    e.connections[0][1] = e.types.length;
    expect(explorerProblems(e).join()).toMatch(/connections\[0\] target/);
  });

  it('a sign that is not a sign', () => {
    const e = clone(explorer);
    e.connections[3][2] = 0;
    expect(explorerProblems(e).join()).toMatch(/connections\[3\] sign/);
  });

  it('filter arrays of different lengths', () => {
    const e = clone(explorer);
    e.connections[5][4] = [...e.connections[5][4], 0];
    expect(explorerProblems(e).join()).toMatch(/differ in length/);
  });

  it('a published match to a type the build does not have', () => {
    const e = clone(explorer);
    e.published[0].matches = [['NotAType', e.published[0].matches[0][1]]];
    expect(explorerProblems(e).join()).toMatch(/not in types/);
  });

  it('a newer artifact version', () => {
    const e = clone(explorer);
    e.version = 2;
    expect(explorerProblems(e).join()).toMatch(/version/);
  });

  it('a manifest whose counts disagree with the artifact', () => {
    const m = clone(manifest);
    m.counts.filter_entries += 1;
    expect(countProblems(explorer, m).join()).toMatch(/filter entries/);
  });

  it('a manifest path that escapes the data root', () => {
    const m = clone(manifest);
    m.path = '../secrets.json';
    expect(manifestProblems(m).join()).toMatch(/path/);
  });
});

// The Experiments and Benchmark pages read these fields; each must exist with the type the page expects.
const MOTION = ['T4a', 'T4b', 'T4c', 'T4d', 'T5a', 'T5b', 'T5c', 'T5d'];
const each = (template: string) => MOTION.map((name) => template.replace('*', name));
const FIELDS: Record<keyof typeof REPORTS, Record<string, 'number' | 'string' | 'boolean' | 'object'>> = {
  build: Object.fromEntries([
    ['column_assignment', 'number'], ['column_inference.inferred', 'number'], ['column_inference.unplaced', 'number'],
    ['column_inference.holdout.per_type', 'object'], ['column_inference.holdout.summary.types_tested', 'number'],
    ['column_inference.holdout.summary.types_recovered', 'number'],
    ['column_inference.holdout.summary.median_exact_fraction', 'number'],
    ['column_inference.holdout.summary.median_within_one_fraction', 'number'],
    ['column_inference.holdout.summary.worst_p95_error_columns', 'number'],
  ]),
  comparison: Object.fromEntries([
    ['orientation.filters_compared', 'number'], ['orientation.best', 'string'], ['orientation.by_symmetry', 'object'],
    ['types.reference', 'number'], ['types.reference_matched', 'number'], ['types.reference_unmatched', 'object'],
    ['connections.reference_comparable', 'number'], ['connections.recovered', 'number'], ['connections.recovered_fraction', 'number'],
    ['signs.compared', 'number'], ['signs.agreeing', 'number'], ['signs.agreement_fraction', 'number'],
    ['central_synapse_counts.spearman', 'number'], ['central_synapse_counts.n', 'number'],
  ]),
  parity: Object.fromEntries([
    ['voltage_parity', 'object'], ['pipeline_crosscheck.models', 'object'],
    ['pipeline_crosscheck.largest_dsi_difference', 'number'], ['pipeline_crosscheck.largest_direction_difference_degrees', 'number'],
    ['tuning.quality.criteria.min_dsi', 'number'], ['tuning.quality.criteria.within_degrees', 'number'],
    ['tuning.quality.criteria.reversed_beyond', 'number'], ['tuning.quality.by_rank', 'object'], ['tuning.quality.rank_correlation', 'number'],
    ...each('tuning.summary.*.median_dsi').map((p) => [p, 'number']),
    ...each('tuning.quality.by_subtype.*.as_known').map((p) => [p, 'number']),
    ...each('tuning.quality.by_subtype.*.reversed').map((p) => [p, 'number']),
    ...each('tuning.quality.by_subtype.*.weak').map((p) => [p, 'number']),
  ]),
  lattice: Object.fromEntries([
    ['device', 'string'], ['controls', 'object'],
    ...['R1', 'R2', 'published_R1'].flatMap((r) => [
      [`training_step.${r}.trainable`, 'number'], [`training_step.${r}.seconds_per_step`, 'number'],
      [`training_step.${r}.peak_memory_gb`, 'number'], [`training_step.${r}.batch_size`, 'number'], [`training_step.${r}.frames`, 'number'],
    ]),
    ...['default', 'transfer'].flatMap((init) => [
      [`frozen.${init}.settled`, 'boolean'], [`frozen.${init}.stability.min`, 'number'], [`frozen.${init}.stability.max`, 'number'],
      [`frozen.${init}.loop_gain.spectral_radius`, 'number'], [`frozen.${init}.compile.nodes`, 'number'], [`frozen.${init}.compile.edges`, 'number'],
      [`frozen.${init}.simulation.simulated_seconds_per_wall_second_per_sample`, 'number'],
      ...each(`frozen.${init}.tuning_summary.*.median_dsi`).map((p) => [p, 'number']),
      ...each(`frozen.${init}.motion_activity.*.resting_voltage`).map((p) => [p, 'number']),
      ...each(`frozen.${init}.motion_activity.*.largest_change_from_rest`).map((p) => [p, 'number']),
    ]),
  ]),
  visualCns: Object.fromEntries([
    ['training_step_R1.seconds_per_step', 'number'], ['training_step_R1.peak_memory_gb', 'number'],
    ['training_step_R1.trainable', 'number'], ['training_step_R1.batch_size', 'number'],
    ...['default', 'transfer'].flatMap((init) => [
      [`unnormalised.${init}.spectral_radius.spectral_radius`, 'number'], [`unnormalised.${init}.settled`, 'boolean'],
      [`frozen.${init}.gain.scale`, 'number'], [`frozen.${init}.gain.largest_component`, 'number'], [`frozen.${init}.settled`, 'boolean'],
      [`frozen.${init}.flash.by_role.output.responding_fraction`, 'number'], [`frozen.${init}.flash.by_role.output.median_change`, 'number'],
      [`frozen.${init}.compile.nodes`, 'number'], [`frozen.${init}.compile.edges`, 'number'],
      [`frozen.${init}.simulation.simulated_seconds_per_wall_second_per_sample`, 'number'],
    ]),
  ]),
  visualCnsSummary: Object.fromEntries([
    ['neurons', 'number'], ['cell_types', 'number'], ['connections', 'number'],
    ['columns.L.holdout.median_exact_fraction', 'number'], ['columns.R.holdout.median_exact_fraction', 'number'],
  ]),
  vision: Object.fromEntries([
    ...['tartanair', 'spring', 'hypersim'].flatMap((s) => [
      [`sources.${s}.clips`, 'number'], [`sources.${s}.frames`, 'number'], [`sources.${s}.accepted`, 'number'],
      [`sources.${s}.rejected`, 'number'], [`sources.${s}.failed`, 'number'], [`sources.${s}.depth_masked_share`, 'number'],
      [`sources.${s}.bytes`, 'number'], [`sources.${s}.license`, 'string'],
    ]),
    ['sources.tartanair.column_spacing_deg', 'number'], ['sources.flygym.column_spacing_deg', 'number'],
    ...['sintel', 'spring', 'hypersim'].flatMap((s) => ['min', 'median', 'max'].map((k) => [`sources.${s}.column_spacing_deg.${k}`, 'number'])),
    ['sources.sintel.sequences', 'number'], ['sources.sintel.frames', 'number'], ['sources.sintel.engine_rendering.strips', 'number'],
    ['sources.sintel.license', 'string'], ['sources.panorama.clips', 'number'], ['sources.panorama.bytes', 'number'],
    ['sources.panorama.license', 'string'],
    ['splits.families', 'number'], ['splits.leakage.frames_hashed', 'number'], ['splits.leakage.problems', 'object'],
    ...['train', 'validation', 'calibration', 'test'].flatMap((s) => ['families', 'environments', 'clips', 'frames'].map((k) => [`splits.counts.${s}.${k}`, 'number'])),
    ['cases.count', 'number'], ['cases.renderings', 'number'], ['cases.accepted', 'number'],
  ]),
  evaluation: Object.fromEntries([
    ['artifact', 'string'], ['version', 'number'], ['methods', 'object'], ['against_floor', 'object'],
    ['kind', 'object'],
    // the floor is the row every flow-based method is read against, so the page needs it present
    ['methods.floor.cases', 'object'], ['methods.floor.clips_scored', 'number'],
    ['methods.floor.cases.C01.name', 'string'], ['methods.floor.cases.C01.observable', 'boolean'],
    ['methods.floor.cases.C01.levels', 'object'],
  ]),
  cases: Object.fromEntries([
    ['cases_sha256', 'string'], ['render_version', 'number'], ['code_sha256', 'string'], ['cases', 'object'],
    ...Array.from({ length: 16 }, (_, i) => `C${String(i + 1).padStart(2, '0')}`).flatMap((c) => [
      [`cases.${c}.name`, 'string'], [`cases.${c}.category`, 'string'], [`cases.${c}.source`, 'string'],
      [`cases.${c}.grades`, 'object'], [`cases.${c}.items`, 'object'], [`cases.${c}.levels`, 'object'],
      [`cases.${c}.variant.quantity`, 'string'], [`cases.${c}.variant.unit`, 'string'],
    ]),
  ]),
};

function at(value: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((node, key) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[key] : undefined), value);
}

describe('the committed reports hold what the pages read', () => {
  for (const [name, fields] of Object.entries(FIELDS) as [keyof typeof REPORTS, Record<string, string>][]) {
    it(name, () => {
      const report = json(REPORTS[name]);
      const wrong = Object.entries(fields)
        .filter(([path, type]) => {
          const v = at(report, path);
          return type === 'number' ? typeof v !== 'number' || !Number.isFinite(v) : typeof v !== type || v === null;
        })
        .map(([path]) => path);
      expect(wrong).toEqual([]);
    });
  }

  it('the controls carry five seeds each, all with a tuning summary', () => {
    const lattice = json(REPORTS.lattice) as { controls: Record<string, { seeds: number[]; settled: boolean[]; tuning_summary: Record<string, unknown> }> };
    expect(Object.keys(lattice.controls).sort()).toEqual(['N1', 'N2', 'N3']);
    for (const control of Object.values(lattice.controls)) {
      expect(control.seeds).toHaveLength(5);
      expect(control.settled).toHaveLength(5);
      expect(Object.keys(control.tuning_summary).sort()).toEqual([...MOTION].sort());
    }
  });
});
