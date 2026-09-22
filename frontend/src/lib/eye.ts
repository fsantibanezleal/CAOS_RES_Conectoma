// Contract 2 for the eye's input (data-pipeline/conectoma/stages/export_eyeclips.py): the types the App reads,
// the runtime checks that bind the data to them, and the decoders. Every array is base64 bytes in the
// engine's column order; src/test/eye.test.ts runs the checks on the committed artifacts.

export const EYECLIP_VERSION = 1;
export const COLUMNS = 721;
export const LAYERS = ['lum', 'depth', 'figure', 'boundary', 'flow', 'sky', 'labelled', 'flow_valid'] as const;
export type Layer = (typeof LAYERS)[number];

export interface EyeCaseEntry {
  path: string;
  bytes: number;
  sha256: string;
  name: string;
  category: string;
  source: string;
}

export interface EyeManifest {
  artifact: 'eyeclips';
  version: number;
  source: { cases: string; cases_sha256: string; render_version: number; clip: number };
  lattice: { extent: number; kernel_px: number; rows_px: number; row_px: number[]; col_px: number[]; u: number[]; v: number[] };
  cases: Record<string, EyeCaseEntry>;
}

export interface EyeLevel {
  value: number | string | null;
  interval_s: number | null;
  measured: Record<string, number | number[] | string | null>;
  frames: number[];
  arrays: Partial<Record<Layer, string>>;
}

export interface EyeClip {
  artifact: 'eyeclip';
  version: number;
  case: string;
  name: string;
  category: string;
  source: string;
  family: string | null;
  grades: string[];
  variant: { quantity: string; unit: string; levels: (number | string | null)[]; transform?: string };
  item: string;
  columns: number;
  frames: number;
  depth: { near_m: number; far_m: number; encoding: 'log'; masked: number; units: 'metres' | 'relative' };
  flow: { scale: number; units: string } | null;
  shared: Partial<Record<Layer, string>>;
  levels: EyeLevel[];
  license: string;
}

type Rec = Record<string, unknown>;
const isRec = (x: unknown): x is Rec => typeof x === 'object' && x !== null && !Array.isArray(x);
const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const isStr = (x: unknown): x is string => typeof x === 'string' && x.length > 0;
const isHex64 = (x: unknown) => typeof x === 'string' && /^[0-9a-f]{64}$/.test(x);

/** Bytes a base64 string decodes to, without decoding it. */
export function base64Bytes(s: string): number {
  const padding = s.endsWith('==') ? 2 : s.endsWith('=') ? 1 : 0;
  return (s.length / 4) * 3 - padding;
}

export function decodeBytes(s: string): Uint8Array {
  const binary = atob(s);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

export function decodeSigned(s: string): Int8Array {
  const bytes = decodeBytes(s);
  return new Int8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

/** Metres (or scene units) from the log code; NaN where masked. The inverse of the pipeline's encode_depth. */
export function depthOf(code: number, near: number, far: number): number {
  if (code === 255) return NaN;
  return Math.exp(Math.log(near) + (code / 254) * (Math.log(far) - Math.log(near)));
}

/** Every way the object differs from the eye manifest the web reads (empty when none). */
export function eyeManifestProblems(x: unknown): string[] {
  const out: string[] = [];
  if (!isRec(x)) return ['the manifest is not an object'];
  if (x.artifact !== 'eyeclips') out.push(`artifact is ${String(x.artifact)}, expected eyeclips`);
  if (x.version !== EYECLIP_VERSION) out.push(`version is ${String(x.version)}, the web reads ${EYECLIP_VERSION}`);
  const lattice = x.lattice;
  if (!isRec(lattice)) out.push('lattice is missing');
  else {
    for (const key of ['row_px', 'col_px', 'u', 'v']) {
      const a = lattice[key];
      if (!Array.isArray(a) || a.length !== COLUMNS || !a.every(Number.isInteger)) {
        out.push(`lattice.${key} is not ${COLUMNS} integers`);
      }
    }
  }
  const cases = x.cases;
  if (!isRec(cases) || Object.keys(cases).length === 0) out.push('cases is missing or empty');
  else {
    for (const [id, entry] of Object.entries(cases)) {
      if (!/^C\d\d$/.test(id)) out.push(`case id ${id} is not Cnn`);
      if (!isRec(entry)) { out.push(`cases.${id} is not an object`); continue; }
      if (!isStr(entry.path) || !entry.path.startsWith('eyeclips/')) out.push(`cases.${id}.path is not under eyeclips/`);
      if (!isHex64(entry.sha256)) out.push(`cases.${id}.sha256 is not a SHA-256`);
      if (!isNum(entry.bytes) || entry.bytes <= 0) out.push(`cases.${id}.bytes is not a size`);
    }
  }
  return out;
}

/** Every way the object differs from a case file of the eye artifact (empty when none). */
export function eyeClipProblems(x: unknown, expectedCase?: string): string[] {
  const out: string[] = [];
  if (!isRec(x)) return ['the case file is not an object'];
  if (x.artifact !== 'eyeclip') out.push(`artifact is ${String(x.artifact)}, expected eyeclip`);
  if (x.version !== EYECLIP_VERSION) out.push(`version is ${String(x.version)}, the web reads ${EYECLIP_VERSION}`);
  if (expectedCase && x.case !== expectedCase) out.push(`case is ${String(x.case)}, expected ${expectedCase}`);
  if (x.columns !== COLUMNS) out.push(`columns is ${String(x.columns)}, expected ${COLUMNS}`);
  const frames = x.frames;
  if (!Number.isInteger(frames) || (frames as number) < 1) out.push('frames is not a count');
  const depth = x.depth;
  if (!isRec(depth) || !isNum(depth.near_m) || !isNum(depth.far_m) || depth.near_m <= 0 || depth.far_m < depth.near_m) {
    out.push('depth range is not a positive interval');
  }
  const variant = x.variant;
  if (!isRec(variant) || !Array.isArray(variant.levels) || variant.levels.length !== 6) out.push('variant does not declare six levels');
  const levels = x.levels;
  if (!Array.isArray(levels) || levels.length !== 6) return [...out, 'levels is not six levels'];
  const shared = isRec(x.shared) ? x.shared : {};
  const n = frames as number;
  const expected: Record<string, number> = {
    lum: n * COLUMNS, depth: n * COLUMNS, figure: n * COLUMNS, boundary: n * COLUMNS, sky: n * COLUMNS,
    labelled: n * COLUMNS, flow: (n - 1) * 2 * COLUMNS, flow_valid: (n - 1) * COLUMNS,
  };
  levels.forEach((level, i) => {
    if (!isRec(level)) { out.push(`levels[${i}] is not an object`); return; }
    const arrays = isRec(level.arrays) ? level.arrays : {};
    if (!('lum' in arrays)) out.push(`levels[${i}] has no luminance`);
    if (!('depth' in arrays) && !('depth' in shared)) out.push(`levels[${i}] has no depth`);
    for (const [key, value] of Object.entries({ ...shared, ...arrays })) {
      if (!(key in expected)) { out.push(`levels[${i}].${key} is not a known layer`); continue; }
      if (typeof value !== 'string' || base64Bytes(value) !== expected[key]) {
        out.push(`levels[${i}].${key} does not hold ${expected[key]} bytes`);
      }
    }
    if (!Array.isArray(level.frames) || level.frames.length !== n) out.push(`levels[${i}].frames is not ${n} frame ids`);
    if (!(level.interval_s === null || (isNum(level.interval_s) && level.interval_s > 0))) {
      out.push(`levels[${i}].interval_s is not a positive interval or null`);
    }
  });
  if (!isStr(x.license)) out.push('license is missing');
  return out;
}

/** One level's layers, decoded; shared layers come from the file's shared block. */
export interface DecodedLevel {
  lum: Uint8Array;
  depth: Uint8Array;
  figure?: Uint8Array;
  boundary?: Uint8Array;
  sky?: Uint8Array;
  labelled?: Uint8Array;
  flow?: Int8Array;
  flow_valid?: Uint8Array;
}

export function decodeLevel(clip: EyeClip, index: number): DecodedLevel {
  const merged: Partial<Record<Layer, string>> = { ...clip.shared, ...clip.levels[index].arrays };
  const out: Partial<DecodedLevel> = {};
  for (const [key, value] of Object.entries(merged) as [Layer, string][]) {
    if (key === 'flow') out.flow = decodeSigned(value);
    else (out as Record<string, Uint8Array>)[key] = decodeBytes(value);
  }
  return out as DecodedLevel;
}
