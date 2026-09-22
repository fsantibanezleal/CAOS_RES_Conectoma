// Bilingual text for the eye view. The artifact carries the registry in English (the canonical language of
// the repository); the Spanish view reads its names, categories and units from here, keyed by case id.

type Pair = [en: string, es: string];

export const CASE_NAMES: Record<string, Pair> = {
  C01: ['forest flight', 'vuelo en el bosque'],
  C02: ['urban street', 'calle urbana'],
  C03: ['hospital corridor', 'pasillo de hospital'],
  C04: ['cluttered room, single image', 'habitación con objetos, imagen única'],
  C05: ['city at night', 'ciudad de noche'],
  C06: ['motion blur', 'desenfoque de movimiento'],
  C07: ['marsh in fog', 'marisma con niebla'],
  C08: ["Sintel, the published model's domain", 'Sintel, el dominio del modelo publicado'],
  C09: ['Spring, fine structure', 'Spring, estructura fina'],
  C10: ['gap crossing', 'cruce de una brecha'],
  C11: ['looming object', 'objeto que se aproxima'],
  C12: ['small moving target', 'objetivo pequeño en movimiento'],
  C13: ['pure rotation', 'rotación pura'],
  C14: ['static camera', 'cámara estática'],
  C15: ['textured planes at known depths', 'planos texturados a profundidades conocidas'],
  C16: ['textureless surfaces', 'superficies sin textura'],
};

export const CATEGORIES: Record<string, Pair> = {
  'nominal-outdoor': ['nominal outdoor', 'nominal exterior'],
  'nominal-indoor': ['nominal indoor', 'nominal interior'],
  'extreme-lighting': ['extreme lighting', 'iluminación extrema'],
  degradation: ['degradation', 'degradación'],
  transfer: ['transfer', 'transferencia'],
  ethological: ['ethological', 'etológico'],
  'negative-control': ['negative control', 'control negativo'],
  'positive-control': ['positive control', 'control positivo'],
  boundary: ['boundary', 'límite'],
};

export const QUANTITIES: Record<string, Pair> = {
  C01: ['ego speed', 'velocidad propia'],
  C02: ['ego speed', 'velocidad propia'],
  C03: ['illumination', 'iluminación'],
  C04: ['vertical field of view', 'campo de visión vertical'],
  C05: ['photon noise', 'ruido de fotones'],
  C06: ['exposure', 'exposición'],
  C07: ['fog attenuation', 'atenuación por niebla'],
  C08: ['contrast', 'contraste'],
  C09: ['sampling', 'muestreo'],
  C10: ['gap width', 'ancho de la brecha'],
  C11: ['approach (l/v)', 'aproximación (l/v)'],
  C12: ['target size', 'tamaño del objetivo'],
  C13: ['rotation rate', 'tasa de rotación'],
  C14: ['photon noise', 'ruido de fotones'],
  C15: ['nearest plane depth', 'profundidad del plano más cercano'],
  C16: ['texture contrast', 'contraste de la textura'],
};

/** The level's value with its unit, in the reader's language. */
export function levelLabel(caseId: string, value: number | string | null, t: (en: string, es: string) => string,
  num: (v: number, d?: number) => string): string {
  if (value === null) return t('no noise', 'sin ruido');
  if (typeof value === 'string') return value === 'full' ? t('full field', 'campo completo') : value;
  const digits = Number.isInteger(value) ? 0 : value < 0.1 ? 3 : value < 1 ? 2 : 1;
  const n = num(value, digits);
  switch (caseId) {
    case 'C01': case 'C02': return t(`${n} x recorded speed`, `${n} x velocidad registrada`);
    case 'C03': return t(`${n} x the light`, `${n} x la luz`);
    case 'C04': return t(`${n} degrees`, `${n} grados`);
    case 'C05': case 'C14': return t(`${n} photons per column`, `${n} fotones por columna`);
    case 'C06': return `${n} ms`;
    case 'C07': return `${n} 1/m`;
    case 'C08': return t(`${n} x contrast`, `${n} x contraste`);
    case 'C09': return t(`${n} rows`, `${n} filas`);
    case 'C10': return `${n} mm`;
    case 'C11': return `l/v ${n} ms`;
    case 'C12': return t(`${n} degrees`, `${n} grados`);
    case 'C13': return t(`${n} degrees/s`, `${n} grados/s`);
    case 'C15': return `${n} m`;
    case 'C16': return t(`contrast ${n}`, `contraste ${n}`);
    default: return n;
  }
}

/** The measured quantities the rail shows for a level, per case, with their labels and decimals. */
export const MEASURED: Record<string, [key: string, label: Pair, digits: number][]> = {
  C01: [['speed_m_s', ['speed (m/s)', 'velocidad (m/s)'], 2], ['frame_rate_hz', ['frame rate (Hz)', 'cuadros por segundo'], 0]],
  C02: [['speed_m_s', ['speed (m/s)', 'velocidad (m/s)'], 2], ['frame_rate_hz', ['frame rate (Hz)', 'cuadros por segundo'], 0]],
  C03: [['lum_mean', ['mean luminance', 'luminancia media'], 3]],
  C04: [['vertical_fov_deg', ['vertical field (deg)', 'campo vertical (grados)'], 1], ['column_spacing_deg', ['column spacing (deg)', 'separación entre columnas (grados)'], 2]],
  C05: [['snr_at_mean', ['SNR at mean luminance', 'SNR a la luminancia media'], 1], ['photons_per_column_per_s', ['photons per column per s', 'fotones por columna por s'], 0]],
  C06: [['blur_length_px', ['blur (px, median)', 'desenfoque (px, mediana)'], 1]],
  C07: [['visibility_m', ['visibility (m)', 'visibilidad (m)'], 0], ['rms_contrast', ['RMS contrast', 'contraste RMS'], 3]],
  C08: [['rms_contrast', ['RMS contrast', 'contraste RMS'], 3], ['column_spacing_deg', ['column spacing (deg)', 'separación entre columnas (grados)'], 2]],
  C09: [['column_spacing_deg', ['column spacing (deg)', 'separación entre columnas (grados)'], 2], ['crop_fraction', ['crop of the frame', 'recorte del cuadro'], 2]],
  C10: [['heading_deg', ['heading (deg)', 'rumbo (grados)'], 1], ['column_spacing_deg', ['column spacing (deg)', 'separación entre columnas (grados)'], 2]],
  C11: [['speed_mm_s', ['approach speed (mm/s)', 'velocidad de aproximación (mm/s)'], 1]],
  C12: [['radius_mm', ['target radius (mm)', 'radio del objetivo (mm)'], 2]],
  C13: [['rotation_deg_per_frame', ['turn per frame (deg)', 'giro por cuadro (grados)'], 1]],
  C14: [['snr_at_mean', ['SNR at mean luminance', 'SNR a la luminancia media'], 1]],
  C15: [['engine_flow_per_frame', ['flow per frame (engine units)', 'flujo por cuadro (unidades del motor)'], 2]],
  C16: [['rms_contrast', ['RMS contrast on the lattice', 'contraste RMS en la retícula'], 3]],
};
