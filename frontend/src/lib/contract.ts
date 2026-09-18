import type { Explorer, ExplorerManifest } from './contract.types';

// Runtime checks for contract 2. The types in contract.types.ts only bind the code at compile time; these
// bind the data. The loader runs them on every artifact it reads, and src/test/contract.test.ts runs them
// on the committed artifacts, so a pipeline change the web did not follow fails the build with the field
// that drifted, instead of rendering a wrong number.

export const EXPLORER_VERSION = 1;
export const CONNECTION_FIELDS = ['source', 'target', 'sign', 'certainty', 'du', 'dv', 'synapses'];
const GROUPS = new Set(['input', 'output', 'stride1', 'stride2', 'stride3', 'stride4', 'population']);
const MAX_PROBLEMS = 20;

type Rec = Record<string, unknown>;
const isRec = (x: unknown): x is Rec => typeof x === 'object' && x !== null && !Array.isArray(x);
const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const isInt = (x: unknown): x is number => Number.isInteger(x);
const isStr = (x: unknown): x is string => typeof x === 'string' && x.length > 0;
const isNumArray = (x: unknown): x is number[] => Array.isArray(x) && x.every(isNum);
const isIntArray = (x: unknown): x is number[] => Array.isArray(x) && x.every(isInt);

class Problems {
  list: string[] = [];
  add(message: string) {
    if (this.list.length < MAX_PROBLEMS) this.list.push(message);
  }
  get full() {
    return this.list.length >= MAX_PROBLEMS;
  }
}

function checkPattern(p: unknown): boolean {
  if (!Array.isArray(p) || p.length !== 2) return false;
  if (p[0] === 'single') return p[1] === null;
  if (p[0] === 'stride') return Array.isArray(p[1]) && p[1].length === 2 && p[1].every((k) => isInt(k) && k >= 1);
  return false;
}

/** Every way the object differs from the explorer artifact the web was written against (empty when none). */
export function explorerProblems(x: unknown): string[] {
  const out = new Problems();
  if (!isRec(x)) return ['the artifact is not an object'];
  if (x.version !== EXPLORER_VERSION) out.add(`version is ${String(x.version)}, the web reads ${EXPLORER_VERSION}`);
  if (JSON.stringify(x.connection_fields) !== JSON.stringify(CONNECTION_FIELDS)) {
    out.add(`connection_fields are ${JSON.stringify(x.connection_fields)}, expected ${JSON.stringify(CONNECTION_FIELDS)}`);
  }

  const types = Array.isArray(x.types) ? x.types : null;
  if (!types || types.length === 0) out.add('types is missing or empty');
  const names = new Set<string>();
  types?.forEach((t, i) => {
    if (out.full) return;
    const where = `types[${i}]`;
    if (!isRec(t)) return out.add(`${where} is not an object`);
    if (!isStr(t.name)) out.add(`${where}.name is not a name`);
    else if (names.has(t.name)) out.add(`${where}.name ${t.name} is repeated`);
    else names.add(t.name);
    if (!checkPattern(t.pattern)) out.add(`${where}.pattern ${JSON.stringify(t.pattern)} is not a placement pattern`);
    if (!GROUPS.has(t.group as string)) out.add(`${where}.group ${String(t.group)} is not a known group`);
    if (!(t.density === null || (isNum(t.density) && t.density >= 0))) out.add(`${where}.density is not a density`);
    for (const key of ['cells', 'cells_placed'] as const) {
      if (!(t[key] === null || (isInt(t[key]) && (t[key] as number) >= 0))) out.add(`${where}.${key} is not a count`);
    }
    if (![1, -1, 0].includes(t.sign as number)) out.add(`${where}.sign ${String(t.sign)} is not +1, -1 or 0`);
    if (typeof t.photoreceptor !== 'boolean') out.add(`${where}.photoreceptor is not a boolean`);
  });

  const n = types?.length ?? 0;
  if (!Array.isArray(x.connections)) out.add('connections is missing');
  else {
    x.connections.forEach((c, i) => {
      if (out.full) return;
      const where = `connections[${i}]`;
      if (!Array.isArray(c) || c.length !== CONNECTION_FIELDS.length) return out.add(`${where} is not a ${CONNECTION_FIELDS.length}-field row`);
      const [source, target, sign, certainty, du, dv, synapses] = c;
      if (!(isInt(source) && source >= 0 && source < n)) out.add(`${where} source ${String(source)} is not a type index`);
      if (!(isInt(target) && target >= 0 && target < n)) out.add(`${where} target ${String(target)} is not a type index`);
      if (sign !== 1 && sign !== -1) out.add(`${where} sign ${String(sign)} is not +1 or -1`);
      // support, not a probability: above 1 where two source cells share a column (docs/architecture/08)
      if (!(isNum(certainty) && certainty > 0)) out.add(`${where} certainty ${String(certainty)} is not a positive support`);
      if (!isIntArray(du) || !isIntArray(dv) || !isNumArray(synapses)) out.add(`${where} filter arrays are not numeric`);
      else if (du.length === 0 || du.length !== dv.length || du.length !== synapses.length) out.add(`${where} filter arrays differ in length`);
      else if (synapses.some((s) => s <= 0)) out.add(`${where} has a filter entry with no synapses`);
    });
  }

  if (!Array.isArray(x.published)) out.add('published is missing');
  else {
    x.published.forEach((p, i) => {
      if (out.full) return;
      const where = `published[${i}]`;
      if (!isRec(p)) return out.add(`${where} is not an object`);
      if (!isStr(p.src) || !isStr(p.tar)) out.add(`${where} lacks src or tar`);
      if (!Array.isArray(p.matches) || !p.matches.every((m) => Array.isArray(m) && m.length === 2 && m.every(isStr))) {
        out.add(`${where}.matches is not a list of type pairs`);
      } else {
        for (const [src, tar] of p.matches as [string, string][]) {
          if (!names.has(src) || !names.has(tar)) out.add(`${where}.matches names ${src} to ${tar}, not in types`);
        }
      }
      if (p.sign !== 1 && p.sign !== -1) out.add(`${where}.sign is not +1 or -1`);
      if (!isIntArray(p.du) || !isIntArray(p.dv) || !isNumArray(p.n)) out.add(`${where} filter arrays are not numeric`);
      else if (p.du.length !== p.dv.length || p.du.length !== p.n.length) out.add(`${where} filter arrays differ in length`);
    });
  }

  if (x.frame !== null) {
    if (!isRec(x.frame) || !isStr(x.frame.offsets) || (x.frame.release_to_engine !== 1 && x.frame.release_to_engine !== -1)) {
      out.add('frame is neither null nor {offsets, release_to_engine: +1 or -1}');
    }
  }
  if (x.placement !== null) {
    const p = x.placement;
    if (!isRec(p) || !isInt(p.columns) || !isInt(p.max_stride) || !isNum(p.population_below_density) || !isRec(p.types_by_pattern)) {
      out.add('placement is neither null nor {columns, max_stride, population_below_density, types_by_pattern}');
    }
  }
  if (x.compile !== null) {
    if (!isRec(x.compile) || typeof x.compile.population_broadcast !== 'boolean' || typeof x.compile.target_centric !== 'boolean') {
      out.add('compile is neither null nor {population_broadcast, target_centric}');
    }
  }
  return out.list;
}

/** Every way the object differs from the explorer manifest (empty when none). */
export function manifestProblems(x: unknown): string[] {
  const out = new Problems();
  if (!isRec(x)) return ['the manifest is not an object'];
  if (x.artifact !== 'explorer') out.add(`artifact is ${String(x.artifact)}, not explorer`);
  if (x.version !== EXPLORER_VERSION) out.add(`version is ${String(x.version)}, the web reads ${EXPLORER_VERSION}`);
  if (!isStr(x.path) || x.path.startsWith('/') || x.path.includes('..')) out.add('path is not a relative artifact path');
  if (!(isInt(x.bytes) && x.bytes > 0)) out.add('bytes is not a size');
  if (typeof x.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(x.sha256)) out.add('sha256 is not a hex digest');
  const s = x.source;
  if (!isRec(s) || !['specification', 'dataset', 'license', 'citation'].every((k) => isStr(s[k]))
    || typeof s.specification_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(s.specification_sha256)) {
    out.add('source does not record specification, its digest, dataset, license and citation');
  }
  const r = x.reference;
  if (r !== null && (!isRec(r) || !isStr(r.file) || !isStr(r.license) || typeof r.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(r.sha256))) {
    out.add('reference is neither null nor {file, sha256, license}');
  }
  const c = x.counts;
  if (!isRec(c) || !['types', 'connections', 'filter_entries', 'published_connections'].every((k) => isInt(c[k]))) {
    out.add('counts does not hold the four counts');
  }
  return out.list;
}

/** Disagreements between an artifact and the counts its manifest declares. */
export function countProblems(e: Explorer, m: ExplorerManifest): string[] {
  const out: string[] = [];
  const entries = e.connections.reduce((sum, c) => sum + c[4].length, 0);
  if (e.types.length !== m.counts.types) out.push(`${e.types.length} types, the manifest says ${m.counts.types}`);
  if (e.connections.length !== m.counts.connections) out.push(`${e.connections.length} connections, the manifest says ${m.counts.connections}`);
  if (entries !== m.counts.filter_entries) out.push(`${entries} filter entries, the manifest says ${m.counts.filter_entries}`);
  if (e.published.length !== m.counts.published_connections) {
    out.push(`${e.published.length} published connections, the manifest says ${m.counts.published_connections}`);
  }
  return out;
}
