// Contract 2 for what the network CONCLUDES (data-pipeline/conectoma/stages/export_chain.py): per case and
// both ends of its sweep, the depth the connectome rows read out of the same clip the eye and the response
// artifacts show, frame by frame, with the truth it is graded against; and the measured circuit between the
// pathway's cell types. src/test/chain.test.ts runs these checks on the committed artifacts.

import { COLUMNS } from './eye';

export const CHAIN_VERSION = 1;
export const ROWS = ['M05', 'M06'] as const;
export type Row = (typeof ROWS)[number];
// Below this direction selectivity a T4 or T5 cell carries no direction a reader could be shown as an
// arrow. The frozen network measures at most 0.012 (moving edges, twelve directions, six speeds).
export const MOTION_FIELD_DSI = 0.1;

export interface ChainCaseEntry { path: string; bytes: number; sha256: string; levels: number }

export interface ChainManifest {
  artifact: 'chain';
  version: number;
  source: { cases: string; cases_sha256: string; clip: number };
  rows: Record<Row, { thresholds?: { tolerance: number; window: number }; unscored?: string }>;
  encoding: { depth: { lo_m: number; hi_m: number; zero: string }; spread: { hi: number }; refused: string };
  cases: Record<string, ChainCaseEntry>;
  missing: Record<string, string>;
  circuit: { path: string; bytes: number; sha256: string };
}

export interface ChainRowData { depth?: string; spread?: string; refused?: string; seeds?: number; missing?: string }

export interface ChainLevel {
  frames: number;
  steps: number;
  value: number | string | null;
  truth: string | null;
  rows: Partial<Record<Row, ChainRowData>>;
}

export interface ChainClip {
  artifact: 'chainclip';
  version: number;
  case: string;
  name: string;
  quantity: string;
  unit: string;
  grades: string[];
  columns: number;
  clip: number;
  levels: Record<string, ChainLevel>;
}

export interface CircuitNode { type: string; layer: 'retina' | 'lamina' | 'medulla' | 'output' }
export interface CircuitEdge { source: string; target: string; synapses: number; sign: number }
export interface Circuit {
  artifact: 'circuit';
  version: number;
  nodes: CircuitNode[];
  edges: CircuitEdge[];
  source: string;
  direction_selectivity: { per_type: Record<string, number>; largest: number; protocol: string; network: string };
}

// ------------------------------------------------------------------ decoding

function bytesOf(encoded: string): Uint8Array {
  const binary = atob(encoded);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

/** Log-spaced metres from one byte each; 0 is 'no value' and decodes to NaN. */
export function decodeDepth(encoded: string, encoding: ChainManifest['encoding']['depth']): Float32Array {
  const raw = bytesOf(encoded);
  const lo = Math.log(encoding.lo_m);
  const hi = Math.log(encoding.hi_m);
  const out = new Float32Array(raw.length);
  for (let i = 0; i < raw.length; i++) {
    out[i] = raw[i] === 0 ? Number.NaN : Math.exp(lo + ((raw[i] - 1) * (hi - lo)) / 254);
  }
  return out;
}

/** The head's own spread in log depth, 0 to `hi` on one byte. */
export function decodeSpread(encoded: string, hi: number): Float32Array {
  const raw = bytesOf(encoded);
  const out = new Float32Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = (raw[i] * hi) / 255;
  return out;
}

/** One bit per column per frame, rows padded to whole bytes, big-endian within a byte (numpy packbits). */
export function decodeMask(encoded: string, steps: number, columns = COLUMNS): Uint8Array {
  const raw = bytesOf(encoded);
  const perRow = Math.ceil(columns / 8);
  const out = new Uint8Array(steps * columns);
  for (let s = 0; s < steps; s++) {
    for (let c = 0; c < columns; c++) {
      const byte = raw[s * perRow + (c >> 3)];
      out[s * columns + c] = (byte >> (7 - (c & 7))) & 1;
    }
  }
  return out;
}

export interface DecodedRow { depth: Float32Array; spread: Float32Array; refused: Uint8Array; seeds: number }
export interface DecodedChain {
  steps: number;
  truth: Float32Array | null;
  rows: Partial<Record<Row, DecodedRow>>;
  missing: Partial<Record<Row, string>>;
}

export function decodeChainLevel(clip: ChainClip, level: string, manifest: ChainManifest): DecodedChain {
  const found = clip.levels[level];
  if (!found) throw new Error(`the chain of ${clip.case} has no level ${level}`);
  const rows: DecodedChain['rows'] = {};
  const missing: DecodedChain['missing'] = {};
  for (const row of ROWS) {
    const data = found.rows[row];
    if (!data || data.missing || !data.depth || !data.spread || !data.refused) {
      missing[row] = data?.missing ?? 'not in the artifact';
      continue;
    }
    rows[row] = {
      depth: decodeDepth(data.depth, manifest.encoding.depth),
      spread: decodeSpread(data.spread, manifest.encoding.spread.hi),
      refused: decodeMask(data.refused, found.steps, clip.columns),
      seeds: data.seeds ?? 0,
    };
  }
  return {
    steps: found.steps,
    truth: found.truth ? decodeDepth(found.truth, manifest.encoding.depth) : null,
    rows,
    missing,
  };
}

// ------------------------------------------------------------------ what the view reads off it

/** The readout frame shown at an eye frame: the readout has one row per frame but the last. */
export function readoutIndex(frame: number, steps: number): number {
  return Math.min(Math.max(frame, 0), Math.max(steps - 1, 0));
}

/** Per frame, the mean relative error of the readout over the columns with a truth. */
export function errorOverTime(row: DecodedRow, truth: Float32Array, steps: number, columns = COLUMNS,
  claimedOnly = false): number[] {
  const out: number[] = [];
  for (let s = 0; s < steps; s++) {
    let sum = 0;
    let count = 0;
    for (let c = 0; c < columns; c++) {
      const i = s * columns + c;
      const d = truth[i];
      const z = row.depth[i];
      if (!(d > 0) || !(z > 0) || (claimedOnly && row.refused[i])) continue;
      sum += Math.abs(z - d) / d;
      count += 1;
    }
    out.push(count ? sum / count : Number.NaN);
  }
  return out;
}

/**
 * A shared log-depth ruler for the readout and the truth of one clip, from the truth's 2nd to 98th
 * percentiles (or the readout's, where the clip has no truth), so the two are read on one scale.
 */
export function depthRange(truth: Float32Array | null, readout: Float32Array | undefined): { lo: number; hi: number } {
  const source = truth ?? readout;
  const logs: number[] = [];
  if (source) {
    const stride = Math.max(1, Math.floor(source.length / 8000));
    for (let i = 0; i < source.length; i += stride) if (source[i] > 0) logs.push(Math.log(source[i]));
  }
  if (logs.length < 10) return { lo: Math.log(0.5), hi: Math.log(200) };
  logs.sort((a, b) => a - b);
  const lo = logs[Math.floor(logs.length * 0.02)];
  const hi = logs[Math.floor(logs.length * 0.98)];
  return hi - lo > 0.2 ? { lo, hi } : { lo: lo - 0.5, hi: hi + 0.5 };
}

/** A depth as a code 0 to 254 on a ruler, which is what the depth colour map takes. */
export function depthCode(metres: number, range: { lo: number; hi: number }): number {
  return Math.round(254 * Math.min(Math.max((Math.log(metres) - range.lo) / (range.hi - range.lo), 0), 1));
}

/** The signed log error of one column, ln(readout / truth): negative too near, positive too far. */
export function logError(readout: number, truth: number): number {
  return readout > 0 && truth > 0 ? Math.log(readout / truth) : Number.NaN;
}

/**
 * How far the pathway is from rest at each step: the mean over cell types of the mean distance from each
 * type's own resting level, in units of that type's own spread.
 */
export function livelinessOverSteps(values: Record<string, Float32Array>, centre: Record<string, number>,
  spread: Record<string, number>, steps: number, columns = COLUMNS): number[] {
  const types = Object.keys(values);
  const out: number[] = [];
  for (let s = 0; s < steps; s++) {
    let score = 0;
    for (const type of types) {
      const v = values[type];
      const c0 = centre[type] ?? 0;
      const sp = Math.max(spread[type] ?? 1, 1e-9);
      let sum = 0;
      for (let c = 0; c < columns; c++) sum += Math.abs(v[s * columns + c] - c0);
      score += sum / columns / sp;
    }
    out.push(types.length ? score / types.length : 0);
  }
  return out;
}

/**
 * The step where the pathway moves most, which is where the view opens.
 *
 * The first step is the WORST place to open: the network starts from its grey steady state, every map is
 * flat and a reader concludes nothing happens.
 */
export function liveliestStep(values: Record<string, Float32Array>, centre: Record<string, number>,
  spread: Record<string, number>, steps: number, columns = COLUMNS): number {
  const scores = livelinessOverSteps(values, centre, spread, steps, columns);
  let best = 0;
  for (let s = 1; s < scores.length; s++) if (scores[s] > scores[best]) best = s;
  return best;
}

/** The simulated-step row a frame of the eye begins at, and the frame a row belongs to. */
export function rowOfFrame(frame: number, stepsPerFrame: number, stride: number, rows: number): number {
  return Math.min(Math.max(Math.ceil((frame * stepsPerFrame) / Math.max(stride, 1)), 0), Math.max(rows - 1, 0));
}

export function frameOfRow(row: number, stepsPerFrame: number, stride: number, frames: number): number {
  return Math.min(Math.floor((row * stride) / Math.max(stepsPerFrame, 1)), Math.max(frames - 1, 0));
}

/** A cell type's population deviation from rest at one step, in units of its own spread, signed. */
export function deviation(values: Float32Array, centre: number, spread: number, step: number,
  columns = COLUMNS): number {
  let sum = 0;
  for (let c = 0; c < columns; c++) sum += values[step * columns + c] - centre;
  return sum / columns / Math.max(spread, 1e-9);
}

/**
 * A connection's drive at one step: the source's deviation from rest times the connection's signed weight.
 * The weight is the specification's own synapse count onto one target cell, so what pulses is the wiring.
 */
export function driveOf(edge: CircuitEdge, sourceDeviation: number): number {
  return sourceDeviation * edge.sign * edge.synapses;
}

/** Whether a motion field may be drawn from a network's T4 and T5 at all. */
export function motionFieldAllowed(largestDsi: number | null | undefined): boolean {
  return typeof largestDsi === 'number' && Number.isFinite(largestDsi) && largestDsi >= MOTION_FIELD_DSI;
}

// ------------------------------------------------------------------ the contract

export function chainProblems(clip: ChainClip, entry?: ChainCaseEntry): string[] {
  const problems: string[] = [];
  if (clip.artifact !== 'chainclip') problems.push(`artifact is ${clip.artifact}, not chainclip`);
  if (clip.version !== CHAIN_VERSION) problems.push(`version ${clip.version} is not ${CHAIN_VERSION}`);
  if (clip.columns !== COLUMNS) problems.push(`${clip.columns} columns, not ${COLUMNS}`);
  const levels = Object.entries(clip.levels ?? {});
  if (!levels.length) problems.push('no levels');
  if (entry && levels.length !== entry.levels) problems.push(`${levels.length} levels, the manifest says ${entry.levels}`);
  for (const [name, level] of levels) {
    const expected = level.steps * COLUMNS;
    if (level.truth && bytesOf(level.truth).length !== expected) problems.push(`level ${name}: truth is not ${expected} bytes`);
    for (const row of ROWS) {
      const data = level.rows?.[row];
      if (!data) { problems.push(`level ${name} has no entry for ${row}`); continue; }
      if (data.missing) continue;
      if (!data.depth || bytesOf(data.depth).length !== expected) problems.push(`level ${name}, ${row}: depth is not ${expected} bytes`);
      if (!data.spread || bytesOf(data.spread).length !== expected) problems.push(`level ${name}, ${row}: spread is not ${expected} bytes`);
      if (!data.refused || bytesOf(data.refused).length !== level.steps * Math.ceil(COLUMNS / 8)) {
        problems.push(`level ${name}, ${row}: the refusal mask is the wrong size`);
      }
    }
  }
  return problems;
}

export function circuitProblems(circuit: Circuit): string[] {
  const problems: string[] = [];
  if (circuit.artifact !== 'circuit') problems.push(`artifact is ${circuit.artifact}, not circuit`);
  const names = new Set(circuit.nodes.map((n) => n.type));
  for (const edge of circuit.edges) {
    if (!names.has(edge.source) || !names.has(edge.target)) problems.push(`an edge ${edge.source} to ${edge.target} leaves the circuit`);
    if (!(edge.synapses > 0)) problems.push(`the edge ${edge.source} to ${edge.target} has no synapses`);
    if (edge.sign !== 1 && edge.sign !== -1) problems.push(`the edge ${edge.source} to ${edge.target} has no sign`);
  }
  if (!Number.isFinite(circuit.direction_selectivity?.largest)) problems.push('no direction selectivity measurement');
  return problems;
}
