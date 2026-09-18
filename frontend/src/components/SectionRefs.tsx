import { Refs } from '@fasl-work/caos-app-shell';
import { useT } from '../lib/i18n';

/**
 * The per-section reference row (ADR-0017, section 4.4), with its label localized once. It is the only
 * reference component used here: a whole-registry bibliography at the bottom of a page detaches each
 * citation from the claim it supports, and is banned.
 */
export default function SectionRefs({ ids }: { ids: string[] }) {
  const t = useT();
  return <Refs ids={ids} label={t('Refs', 'Referencias')} />;
}
