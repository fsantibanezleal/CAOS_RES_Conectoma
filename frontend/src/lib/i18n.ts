import { useCallback } from 'react';
import { useShellLang } from '@fasl-work/caos-app-shell';

// Bilingual helper bound to the shell's language store: English is canonical, Spanish is a full translation.
// Usage: const t = useT(); ... t('recovery', 'recuperación').
//
// Both helpers keep their identity until the language changes. They are listed as dependencies by the
// charts, and a helper that is a new function on every render made every chart tear itself down and build
// itself again on every render: while the chain played, a uPlot instance was destroyed and rebuilt many times
// a second, and the one on screen was often one whose frame axis had never ranged, so it drew no line.
export function useT() {
  const lang = useShellLang();
  return useCallback((en: string, es: string) => (lang === 'es' ? es : en), [lang]);
}

/** Numbers in the reader's language: a thousands separator and a decimal mark that match the text. */
export function useNumber() {
  const lang = useShellLang();
  return useCallback((value: number, digits = 0) => {
    const locale = lang === 'es' ? 'es-CL' : 'en-US';
    return value.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }, [lang]);
}
