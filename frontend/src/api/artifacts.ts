import { countProblems, explorerProblems, manifestProblems } from '../lib/contract';
import type { Explorer, ExplorerManifest } from '../lib/contract.types';

// Every artifact is read from the site root (the build copies data/derived into public/data), with an
// absolute path so a deep route never resolves it against itself.
const DATA = `${import.meta.env.BASE_URL}data/`;

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(DATA + path, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  const type = response.headers.get('content-type') ?? '';
  // a static host that falls back to the app shell answers 200 with HTML; that is not the artifact
  if (type.includes('text/html')) throw new Error(`${path}: the server returned a page, not the artifact`);
  return (await response.json()) as T;
}

async function sha256(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export interface Verified<T> {
  data: T;
  manifest: ExplorerManifest;
  /** true when the bytes received hash to the manifest's SHA-256 */
  verified: boolean;
}

function refuse(what: string, problems: string[]): never {
  throw new Error(`${what} does not match the contract this page was built for: ${problems.slice(0, 3).join('; ')}`);
}

/** The explorer artifact, checked against the contract and against the digest its manifest declares. */
export async function loadExplorer(): Promise<Verified<Explorer>> {
  const raw = await getJson<unknown>('manifests/explorer.json');
  const mp = manifestProblems(raw);
  if (mp.length) refuse('The explorer manifest', mp);
  const manifest = raw as ExplorerManifest;
  const response = await fetch(DATA + manifest.path, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`${manifest.path}: HTTP ${response.status}`);
  const buffer = await response.arrayBuffer();
  const verified = typeof crypto !== 'undefined' && crypto.subtle
    ? (await sha256(buffer)) === manifest.sha256
    : false;
  const parsed: unknown = JSON.parse(new TextDecoder().decode(buffer));
  const ep = explorerProblems(parsed);
  if (ep.length) refuse('The explorer artifact', ep);
  const data = parsed as Explorer;
  const cp = countProblems(data, manifest);
  if (cp.length) refuse('The explorer artifact', cp);
  return { data, manifest, verified };
}

/** A committed report, read as it is (the Experiments and Benchmark pages take their numbers from these). */
export function loadReport<T>(path: string): Promise<T> {
  return getJson<T>(path);
}
