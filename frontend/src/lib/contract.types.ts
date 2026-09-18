// TypeScript mirror of contract 2, the artifacts the pipeline writes for the web
// (data-pipeline/conectoma/stages/export_web.py). src/test/contract.test.ts checks the committed artifacts
// against it, so a change on either side that the other did not follow fails the build.

export type Pattern = ['stride', [number, number]] | ['single', null];

export type TypeGroup = 'input' | 'output' | 'stride1' | 'stride2' | 'stride3' | 'stride4' | 'population';

export interface CellType {
  name: string;
  pattern: Pattern;
  group: TypeGroup;
  density: number | null;
  cells: number | null;
  cells_placed: number | null;
  /** +1 excitatory, -1 inhibitory, 0 when the type sends nothing in this build. */
  sign: number;
  photoreceptor: boolean;
}

/**
 * [source, target, sign, certainty, du[], dv[], synapses[]]. The certainty is the connection's support:
 * connected cell pairs per target cell averaged over its entries (for a population source, the share of
 * target cells reached). It exceeds 1 where two source cells share a column.
 */
export type Connection = [number, number, number, number, number[], number[], number[]];

export interface PublishedFilter {
  src: string;
  tar: string;
  /** the MaleCNS type pairs this published connection corresponds to, after the cross-release renames */
  matches: [string, string][];
  sign: number;
  du: number[];
  dv: number[];
  n: number[];
}

export interface Explorer {
  version: number;
  types: CellType[];
  connection_fields: string[];
  connections: Connection[];
  published: PublishedFilter[];
  frame: { offsets: string; release_to_engine: number } | null;
  placement: {
    columns: number;
    max_stride: number;
    population_below_density: number;
    types_by_pattern: Record<string, number>;
  } | null;
  compile: { population_broadcast: boolean; target_centric: boolean } | null;
}

export interface ExplorerManifest {
  artifact: 'explorer';
  version: number;
  path: string;
  bytes: number;
  sha256: string;
  source: {
    specification: string;
    specification_sha256: string;
    dataset: string;
    license: string;
    citation: string;
  };
  reference: { file: string; sha256: string; license: string } | null;
  counts: { types: number; connections: number; filter_entries: number; published_connections: number };
}
