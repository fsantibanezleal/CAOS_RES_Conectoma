import { useShellLang } from '@fasl-work/caos-app-shell';

// Bilingual helper bound to the shell's language store: English is canonical, Spanish is a full translation.
// Usage: const t = useT(); ... t('recovery', 'recuperación').
export function useT() {
  const lang = useShellLang();
  return (en: string, es: string) => (lang === 'es' ? es : en);
}

/** Numbers in the reader's language: a thousands separator and a decimal mark that match the text. */
export function useNumber() {
  const lang = useShellLang();
  const locale = lang === 'es' ? 'es-CL' : 'en-US';
  return (value: number, digits = 0) =>
    value.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
