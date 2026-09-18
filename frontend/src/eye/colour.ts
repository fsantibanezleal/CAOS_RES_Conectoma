// Colour maps for the eye's layers. Value maps are fixed perceptual scales that read on both themes; the
// canvas background and outlines come from the shell's variables at draw time.

type RGB = [number, number, number];

// A sequential map from near (warm, bright) to far (cool, dark), sampled from the magma-like family: depth
// reads as "near things glow". Masked depth is drawn separately, never with a value colour.
const DEPTH_STOPS: RGB[] = [
  [252, 253, 191], [254, 176, 120], [241, 96, 93], [183, 55, 121], [114, 31, 129], [44, 17, 95], [11, 9, 36],
];

function lerp(stops: RGB[], t: number): RGB {
  const x = Math.min(Math.max(t, 0), 1) * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  const f = x - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

const css = ([r, g, b]: RGB) => `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`;

/** Luminance code 0..255 as grey. */
export function grey(code: number): string {
  return `rgb(${code},${code},${code})`;
}

/** Depth code 0..254 (log between near and far) as colour; 255 (masked) returns null. */
export function depthColour(code: number): string | null {
  if (code === 255) return null;
  return css(lerp(DEPTH_STOPS, code / 254));
}

/** A share 0..255 over a luminance grey: the accent tinted in proportion. */
export function shareColour(share: number, lum: number, accent: RGB): string {
  const s = share / 255;
  return css([lum + (accent[0] - lum) * s, lum + (accent[1] - lum) * s, lum + (accent[2] - lum) * s]);
}

/** Flow direction as hue and magnitude as saturation (the usual optical-flow wheel). */
export function flowColour(dx: number, dy: number, scale: number): string {
  const magnitude = Math.min(Math.hypot(dx, dy) / Math.max(scale, 1e-9), 1);
  const hue = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360;
  return `hsl(${hue.toFixed(0)}, ${(magnitude * 90).toFixed(0)}%, ${(70 - magnitude * 25).toFixed(0)}%)`;
}

export function parseRgb(value: string, fallback: RGB): RGB {
  const hex = value.trim().match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const rgb = value.match(/rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+)/i);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  return fallback;
}

export const DEPTH_LEGEND = DEPTH_STOPS.map(css);
