import { countProblems, explorerProblems, manifestProblems } from '../lib/contract';
import { sha256Hex } from '../lib/sha256';
import type { Explorer, ExplorerManifest } from '../lib/contract.types';
import { brainProblems, type BrainClip, type BrainManifest } from '../lib/brain';
import { eyeClipProblems, eyeManifestProblems, type EyeClip, type EyeManifest } from '../lib/eye';

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

/** SHA-256 of the bytes: WebCrypto where the page is a secure context, the plain implementation elsewhere. */
async function sha256(buffer: ArrayBuffer): Promise<string> {
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
    return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  return sha256Hex(new Uint8Array(buffer));
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
  const verified = (await sha256(buffer)) === manifest.sha256;
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

/** The eye artifact's manifest: which case files exist, their digests, and the lattice's sampling positions. */
export async function loadEyeManifest(): Promise<EyeManifest> {
  const raw = await getJson<unknown>('manifests/eyeclips.json');
  const problems = eyeManifestProblems(raw);
  if (problems.length) refuse('The eye manifest', problems);
  return raw as EyeManifest;
}

export interface VerifiedClip {
  clip: EyeClip;
  /** true when the bytes received hash to the manifest's SHA-256 */
  verified: boolean;
}

const clipCache = new Map<string, Promise<VerifiedClip>>();

/** One case's clip at all six levels, read once, checked against the contract and its declared digest. */
export function loadEyeClip(manifest: EyeManifest, caseId: string): Promise<VerifiedClip> {
  const entry = manifest.cases[caseId];
  if (!entry) return Promise.reject(new Error(`the eye manifest has no case ${caseId}`));
  const cached = clipCache.get(caseId);
  if (cached) return cached;
  const promise = (async () => {
    const response = await fetch(DATA + entry.path, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`${entry.path}: HTTP ${response.status}`);
    const buffer = await response.arrayBuffer();
    const verified = (await sha256(buffer)) === entry.sha256;
    const parsed: unknown = JSON.parse(new TextDecoder().decode(buffer));
    const problems = eyeClipProblems(parsed, caseId);
    if (problems.length) refuse(`The eye clip of ${caseId}`, problems);
    return { clip: parsed as EyeClip, verified };
  })();
  promise.catch(() => clipCache.delete(caseId));
  clipCache.set(caseId, promise);
  return promise;
}

/** The brain artifact's manifest: which cases have a response, their digests, and the pathway's types. */
export async function loadBrainManifest(): Promise<BrainManifest> {
  const raw = await getJson<BrainManifest>('manifests/brainclips.json');
  if (raw?.artifact !== 'brainclips') refuse('The brain manifest', ['it is not a brainclips manifest']);
  if (!Array.isArray(raw.types) || !raw.types.length) refuse('The brain manifest', ['it names no cell types']);
  return raw;
}

export interface VerifiedBrainClip {
  clip: BrainClip;
  /** true when the bytes received hash to the manifest's SHA-256 */
  verified: boolean;
}

const brainCache = new Map<string, Promise<VerifiedBrainClip>>();

/** What the connectome did with one case, read once, checked against the contract and its digest. */
export function loadBrainClip(manifest: BrainManifest, caseId: string): Promise<VerifiedBrainClip> {
  const entry = manifest.cases[caseId];
  if (!entry) return Promise.reject(new Error(`the brain manifest has no case ${caseId}`));
  const cached = brainCache.get(caseId);
  if (cached) return cached;
  const promise = (async () => {
    const response = await fetch(DATA + entry.path, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`${entry.path}: HTTP ${response.status}`);
    const buffer = await response.arrayBuffer();
    const verified = (await sha256(buffer)) === entry.sha256;
    const parsed = JSON.parse(new TextDecoder().decode(buffer)) as BrainClip;
    const problems = brainProblems(parsed, entry);
    if (problems.length) refuse(`The brain clip of ${caseId}`, problems);
    return { clip: parsed, verified };
  })();
  promise.catch(() => brainCache.delete(caseId));
  brainCache.set(caseId, promise);
  return promise;
}
