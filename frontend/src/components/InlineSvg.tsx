import { useEffect, useState } from 'react';
import { useShellLang } from '@fasl-work/caos-app-shell';

/**
 * A documentation figure, fetched and inlined rather than shown through <img>. An SVG inside <img> cannot
 * read the page's colour tokens, so it would follow the operating system's scheme instead of the site's
 * theme toggle; inlined, it follows the toggle. The figures are this product's own files, each carrying both
 * languages (texts classed `l-en` and `l-es`); the wrapper's `data-arch-lang` makes the shell show one.
 */
export default function InlineSvg({ src, label }: { src: string; label: string }) {
  const lang = useShellLang();
  const [markup, setMarkup] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetch(`${import.meta.env.BASE_URL}${src}`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((text) => {
        if (live && text.trimStart().startsWith('<svg')) setMarkup(text);
        else if (live) setFailed(true);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [src]);

  if (failed) return <p className="cx-muted">{label}</p>;
  if (!markup) return <div className="cx-figure-placeholder" aria-busy="true" />;
  return (
    <div
      className="cx-figure"
      role="img"
      aria-label={label}
      data-arch-lang={lang}
      dangerouslySetInnerHTML={{ __html: markup }}
    />
  );
}
