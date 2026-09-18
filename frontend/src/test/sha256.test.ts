import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { sha256Hex } from '../lib/sha256';

// The plain SHA-256 the explorer falls back to where WebCrypto is absent (a page served over plain HTTP),
// checked against Node's implementation: the standard vectors, every padding boundary, and the committed
// artifact itself.

const node = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const text = (s: string) => new TextEncoder().encode(s);

describe('sha256Hex', () => {
  it('matches the FIPS 180-4 examples', () => {
    expect(sha256Hex(text(''))).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    expect(sha256Hex(text('abc'))).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
    expect(sha256Hex(text('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'))).toBe(
      '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1',
    );
  });

  it('matches Node across every padding boundary', () => {
    for (let n = 0; n <= 200; n++) {
      const bytes = Uint8Array.from({ length: n }, (_, i) => (i * 31 + n) & 0xff);
      expect(sha256Hex(bytes)).toBe(node(bytes));
    }
  });

  it('gives the committed artifact the digest its manifest declares', () => {
    const derived = new URL('../../../data/derived/', import.meta.url);
    const manifest = JSON.parse(readFileSync(new URL('manifests/explorer.json', derived), 'utf-8'));
    const bytes = new Uint8Array(readFileSync(new URL(manifest.path, derived)));
    expect(sha256Hex(bytes)).toBe(manifest.sha256);
  });
});
