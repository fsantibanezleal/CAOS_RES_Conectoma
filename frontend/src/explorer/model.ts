import type { CellType, Connection, Explorer, PublishedFilter } from '../lib/contract.types';

/** One filter: parallel arrays of column offsets (engine frame) and synapses per target cell. */
export interface Filter {
  du: number[];
  dv: number[];
  n: number[];
}

export interface Partner {
  /** index into the explorer's connections */
  connection: number;
  /** the other type's index */
  type: number;
  sign: number;
  certainty: number;
  /** synapses a target cell receives through this connection, summed over offsets */
  total: number;
  filter: Filter;
}

export type Direction = 'receives' | 'sends';

export interface Model {
  explorer: Explorer;
  byName: Map<string, number>;
  incoming: Partner[][];
  outgoing: Partner[][];
  published: Map<string, PublishedFilter>;
}

function partner(connection: Connection, index: number, other: number): Partner {
  const [, , sign, certainty, du, dv, n] = connection;
  return {
    connection: index,
    type: other,
    sign,
    certainty,
    total: n.reduce((a, b) => a + b, 0),
    filter: { du, dv, n },
  };
}

export function buildModel(explorer: Explorer): Model {
  const count = explorer.types.length;
  const incoming: Partner[][] = Array.from({ length: count }, () => []);
  const outgoing: Partner[][] = Array.from({ length: count }, () => []);
  explorer.connections.forEach((c, i) => {
    incoming[c[1]].push(partner(c, i, c[0]));
    outgoing[c[0]].push(partner(c, i, c[1]));
  });
  for (const list of [...incoming, ...outgoing]) list.sort((a, b) => b.total - a.total);
  const published = new Map<string, PublishedFilter>();
  for (const p of explorer.published) {
    for (const [a, b] of p.matches) {
      const key = `${a}>${b}`;
      const current = published.get(key);
      const total = p.n.reduce((x, y) => x + y, 0);
      // a MaleCNS pair can stand for several published ones (R1-R6 for six); keep the strongest, as the
      // consensus comparison does
      if (!current || current.n.reduce((x, y) => x + y, 0) < total) published.set(key, p);
    }
  }
  return {
    explorer,
    byName: new Map(explorer.types.map((t, i) => [t.name, i])),
    incoming,
    outgoing,
    published,
  };
}

export function partnersOf(model: Model, type: number, direction: Direction): Partner[] {
  return direction === 'receives' ? model.incoming[type] : model.outgoing[type];
}

export function publishedFor(model: Model, source: string, target: string): PublishedFilter | undefined {
  return model.published.get(`${source}>${target}`);
}

/** Synapse-weighted mean offset in Cartesian lattice units, the centre entry excluded. */
export function displacement(filter: Filter): [number, number] | null {
  let total = 0;
  let x = 0;
  let y = 0;
  filter.du.forEach((du, i) => {
    const dv = filter.dv[i];
    if (du === 0 && dv === 0) return;
    const n = filter.n[i];
    total += n;
    x += n * Math.sqrt(3) * (du + dv / 2);
    y += n * 1.5 * dv;
  });
  return total > 0 ? [x / total, y / total] : null;
}

/** Cosine similarity between two filters over the union of their offsets. */
export function cosine(a: Filter, b: Filter): number | null {
  const map = new Map<string, [number, number]>();
  a.du.forEach((du, i) => map.set(`${du},${a.dv[i]}`, [a.n[i], 0]));
  b.du.forEach((du, i) => {
    const key = `${du},${b.dv[i]}`;
    const entry = map.get(key) ?? [0, 0];
    entry[1] = b.n[i];
    map.set(key, entry);
  });
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (const [x, y] of map.values()) {
    dot += x * y;
    na += x * x;
    nb += y * y;
  }
  return na > 0 && nb > 0 ? dot / Math.sqrt(na * nb) : null;
}

/** Angle between two displacement directions, in degrees (0 to 180). */
export function angleBetween(a: [number, number], b: [number, number]): number {
  const dot = a[0] * b[0] + a[1] * b[1];
  const norm = Math.hypot(...a) * Math.hypot(...b);
  return (Math.acos(Math.max(-1, Math.min(1, dot / norm))) * 180) / Math.PI;
}

export function centralCount(filter: Filter): number {
  const i = filter.du.findIndex((du, k) => du === 0 && filter.dv[k] === 0);
  return i >= 0 ? filter.n[i] : 0;
}

export function placementLabel(type: CellType, t: (en: string, es: string) => string): string {
  if (type.pattern[0] === 'single') return t('one population node', 'un nodo de población');
  const k = type.pattern[1][0];
  if (k === 1) return t('every column', 'cada columna');
  return t(`every ${ordinal(k)} column (${k}x${k})`, `cada ${k} columnas por eje (${k}x${k})`);
}

function ordinal(k: number): string {
  return ({ 2: 'second', 3: 'third', 4: 'fourth' } as Record<number, string>)[k] ?? `${k}th`;
}
