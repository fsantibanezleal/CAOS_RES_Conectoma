// Contract 2 for what the connectome does with a case (data-pipeline/conectoma/stages/export_brainclips.py).
// Every type's activity is base64 bytes, delta-coded over simulated steps: the first row is a byte per
// column and every later row is its signed difference from the row before. A value in the engine's units
// is `scale * (byte - 128) / 127`. src/test/brain.test.ts runs these checks on the committed artifacts.

export const BRAINCLIP_VERSION = 1;
export const COLUMNS = 721;

export interface BrainCaseEntry {
  path: string;
  bytes: number;
  sha256: string;
  levels: number;
  steps: number;
}

export interface BrainManifest {
  artifact: 'brainclips';
  version: number;
  source: { cases: string; cases_sha256: string; arm: string; description: string; dt_s: number };
  types: string[];
  wide_field: string[];
  stride: number;
  encoding: 'delta-int8';
  cases: Record<string, BrainCaseEntry>;
}

export interface BrainLevel {
  steps: number;
  frames: number;
  steps_per_frame: number;
  stride: number;
  step_s: number;
  interval_s: number;
  value: number | string | null;
  scales: Record<string, number>;
  activity: Record<string, string>;
}

export interface BrainClip {
  artifact: 'brainclip';
  version: number;
  case: string;
  name: string;
  quantity: string;
  unit: string;
  types: string[];
  columns: number;
  arm: string;
  dt_s: number;
  levels: Record<string, BrainLevel>;
}

// The pathway in the order the signal travels, with what each stage is, so a reader is never shown a
// four-letter cell name with no explanation.
export const STAGES: Record<string, { stage: 'lamina' | 'medulla' | 'output'; en: string; es: string }> = {
  L1: { stage: 'lamina', en: 'lamina, ON pathway input', es: 'lámina, entrada de la vía ON' },
  L2: { stage: 'lamina', en: 'lamina, OFF pathway input', es: 'lámina, entrada de la vía OFF' },
  L3: { stage: 'lamina', en: 'lamina, sustained contrast', es: 'lámina, contraste sostenido' },
  Mi1: { stage: 'medulla', en: 'medulla, ON, fast arm', es: 'médula, ON, brazo rápido' },
  Tm3: { stage: 'medulla', en: 'medulla, ON, slow arm', es: 'médula, ON, brazo lento' },
  Tm1: { stage: 'medulla', en: 'medulla, OFF, delayed', es: 'médula, OFF, retardado' },
  Tm2: { stage: 'medulla', en: 'medulla, OFF, fast', es: 'médula, OFF, rápido' },
  Mi9: { stage: 'medulla', en: 'medulla, ON, inhibitory', es: 'médula, ON, inhibitorio' },
  Mi4: { stage: 'medulla', en: 'medulla, ON, inhibitory', es: 'médula, ON, inhibitorio' },
  T4a: { stage: 'output', en: 'ON motion, front to back', es: 'movimiento ON, de frente a atrás' },
  T4b: { stage: 'output', en: 'ON motion, back to front', es: 'movimiento ON, de atrás a frente' },
  T4c: { stage: 'output', en: 'ON motion, upward', es: 'movimiento ON, hacia arriba' },
  T4d: { stage: 'output', en: 'ON motion, downward', es: 'movimiento ON, hacia abajo' },
  T5a: { stage: 'output', en: 'OFF motion, front to back', es: 'movimiento OFF, de frente a atrás' },
  T5b: { stage: 'output', en: 'OFF motion, back to front', es: 'movimiento OFF, de atrás a frente' },
  T5c: { stage: 'output', en: 'OFF motion, upward', es: 'movimiento OFF, hacia arriba' },
  T5d: { stage: 'output', en: 'OFF motion, downward', es: 'movimiento OFF, hacia abajo' },
};

export function decodeDelta(encoded: string, steps: number, columns = COLUMNS): Int16Array {
  // undo the delta coding: the first row as it is, every later row added to the one before
  const binary = atob(encoded);
  const out = new Int16Array(steps * columns);
  for (let c = 0; c < columns; c++) out[c] = binary.charCodeAt(c);
  for (let s = 1; s < steps; s++) {
    const base = s * columns;
    const before = base - columns;
    for (let c = 0; c < columns; c++) {
      const raw = binary.charCodeAt(base + c);
      const signed = raw > 127 ? raw - 256 : raw;          // a byte holding a signed difference
      out[base + c] = out[before + c] + signed;
    }
  }
  return out;
}

export interface DecodedActivity {
  steps: number;
  values: Record<string, Float32Array>;      // engine units, (steps * columns) per type
  range: Record<string, number>;             // the symmetric scale each type was quantised on
  centre: Record<string, number>;            // this type's resting level over the clip
  spread: Record<string, number>;            // how far it moves from that level, robustly
}

/**
 * A cell type's resting level and how far it moves from it.
 *
 * Drawing a signed map around ZERO is wrong for a neuron: the types sit at very different resting levels
 * (measured on one clip: Mi1 near -2.7, T5a near +2.7), so a map centred on zero paints one cell solid
 * blue and another solid red and hides the thing that actually moves. The centre is the median over the
 * whole clip, which is where the cell rests, and the spread is the 95th percentile of the distance from
 * it, so one transient does not flatten everything else.
 */
export function restingLevel(values: Float32Array): { centre: number; spread: number } {
  const step = Math.max(1, Math.floor(values.length / 20000));     // a sample is enough for a quantile
  const sample: number[] = [];
  for (let i = 0; i < values.length; i += step) sample.push(values[i]);
  sample.sort((a, b) => a - b);
  const centre = sample[Math.floor(sample.length / 2)] ?? 0;
  const distances = sample.map((v) => Math.abs(v - centre)).sort((a, b) => a - b);
  const spread = distances[Math.floor(distances.length * 0.95)] ?? 1;
  return { centre, spread: spread > 1e-6 ? spread : 1 };
}

export function decodeLevel(clip: BrainClip, level: string): DecodedActivity {
  const found = clip.levels[level];
  if (!found) throw new Error(`the brain clip of ${clip.case} has no level ${level}`);
  const values: Record<string, Float32Array> = {};
  const centre: Record<string, number> = {};
  const spread: Record<string, number> = {};
  for (const type of clip.types) {
    const encoded = found.activity[type];
    if (!encoded) continue;
    const scale = found.scales[type] ?? 1;
    const bytes = decodeDelta(encoded, found.steps, clip.columns);
    const out = new Float32Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) out[i] = (scale * (bytes[i] - 128)) / 127;
    values[type] = out;
    const rest = restingLevel(out);
    centre[type] = rest.centre;
    spread[type] = rest.spread;
  }
  return { steps: found.steps, values, range: { ...found.scales }, centre, spread };
}

export function brainProblems(clip: BrainClip, entry?: BrainCaseEntry): string[] {
  const problems: string[] = [];
  if (clip.artifact !== 'brainclip') problems.push(`artifact is ${clip.artifact}, not brainclip`);
  if (clip.version !== BRAINCLIP_VERSION) problems.push(`version ${clip.version} is not ${BRAINCLIP_VERSION}`);
  if (clip.columns !== COLUMNS) problems.push(`${clip.columns} columns, not ${COLUMNS}`);
  if (!clip.types.length) problems.push('no cell types');
  const levels = Object.entries(clip.levels);
  if (!levels.length) problems.push('no levels');
  if (entry && levels.length !== entry.levels) {
    problems.push(`${levels.length} levels, the manifest says ${entry.levels}`);
  }
  for (const [name, level] of levels) {
    if (level.steps <= 0) problems.push(`level ${name} has no steps`);
    for (const type of clip.types) {
      if (!level.activity[type]) {
        problems.push(`level ${name} is missing ${type}`);
        continue;
      }
      // base64 of exactly steps * columns bytes, delta-coded
      const expected = level.steps * clip.columns;
      const got = (level.activity[type].length * 3) / 4 - (level.activity[type].endsWith('==') ? 2 : level.activity[type].endsWith('=') ? 1 : 0);
      if (got !== expected) problems.push(`level ${name}, ${type}: ${got} bytes, expected ${expected}`);
      if (!(level.scales[type] > 0)) problems.push(`level ${name}, ${type} has no scale`);
    }
  }
  return problems;
}
