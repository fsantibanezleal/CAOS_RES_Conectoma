import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// react-router, not react-router-dom: the shell peer-depends on react-router, and two router packages of
// different majors would give the app and the shell two separate contexts, so nothing would render.
import { BrowserRouter, Route, Routes } from 'react-router';
import { Hexagon } from 'lucide-react';
import { AppShell, applyTheme, CitationsProvider, readTheme, type ShellConfig } from '@fasl-work/caos-app-shell';
import '@fasl-work/caos-app-shell/styles.css';
import 'katex/dist/katex.min.css';
import './conectoma.css';
import { CITATIONS } from './data/citations';
import { EXTERNAL_LINKS } from './lib/links';
import pkg from '../package.json';

import AppPage from './pages/AppPage';
import Introduction from './pages/Introduction';
import Methodology from './pages/Methodology';
import Implementation from './pages/Implementation';
import Experiments from './pages/Experiments';
import Benchmark from './pages/Benchmark';

// Display version X.XX.XXX from the package manifest, the single source.
const displayVersion = pkg.version
  .split('.')
  .map((part, i) => (i === 0 ? part : part.padStart(i === 1 ? 2 : 3, '0')))
  .join('.');

applyTheme(readTheme());

// ADR-0058: the in-app Architecture modal, five themed bilingual diagrams in public/svg/tech/.
const architecture: ShellConfig['architecture'] = {
  tabs: [
    {
      id: 'app',
      en: 'The product',
      es: 'El producto',
      svg: 'svg/tech/01-the-product.svg',
      body_en:
        'Conectoma asks whether the measured wiring of a fly’s visual system is a useful architecture for machine vision when it is frozen. The connectome of the male Drosophila (MaleCNS v1.0) is turned into a network whose wiring, synapse counts and signs are measurements and never change; only what the connectome cannot measure may learn, in three regimes that differ in how much.\n\nEvery claim is tested against null controls that keep the size of the wiring but not its biology, because a sparse recurrent network of the right size might help on its own. A negative answer is a valid outcome and is reported as one.',
      body_es:
        'Conectoma pregunta si el cableado medido del sistema visual de una mosca es una arquitectura útil para visión artificial cuando se congela. El conectoma de la Drosophila macho (MaleCNS v1.0) se convierte en una red cuyo cableado, conteos de sinapsis y signos son mediciones y nunca cambian; solo aprende lo que el conectoma no puede medir, en tres regímenes que difieren en cuánto.\n\nCada afirmación se contrasta con controles nulos que conservan el tamaño del cableado pero no su biología, porque una red recurrente dispersa del tamaño correcto podría ayudar por sí sola. Una respuesta negativa es un resultado válido y se informa como tal.',
    },
    {
      id: 'lanes',
      en: 'Offline and in the browser',
      es: 'Offline y en el navegador',
      svg: 'svg/tech/02-lanes.svg',
      body_en:
        'The heavy work runs offline in the pipeline: building the connectome from 151 million connection rows, compiling it into a network of forty thousand cells and three million connections, simulating it on a GPU, and checking it against the published model. The vision data is fetched member by member and rendered onto the fly’s lattice offline too. What reaches the browser is compact artifacts with manifests: the explorer reads a 1.2 MB file, the eye’s input one file per case, and each verifies its SHA-256 before it is shown.\n\nThe browser lane grows unit by unit: methods that pass a parity and latency gate will run client-side; everything else replays committed results.',
      body_es:
        'El trabajo pesado corre offline en el pipeline: construir el conectoma desde 151 millones de filas de conexiones, compilarlo en una red de cuarenta mil células y tres millones de conexiones, simularla en una GPU y contrastarla con el modelo publicado. Los datos de visión se descargan miembro por miembro y se renderizan sobre la retícula de la mosca también offline. Lo que llega al navegador son artefactos compactos con manifiestos: el explorador lee un archivo de 1,2 MB, la entrada del ojo un archivo por caso, y cada uno verifica su SHA-256 antes de mostrarse.\n\nEl carril del navegador crece unidad por unidad: los métodos que superen una compuerta de paridad y latencia correrán en el cliente; el resto reproduce resultados versionados.',
    },
    {
      id: 'webflow',
      en: 'The web flow',
      es: 'El flujo web',
      svg: 'svg/tech/03-web-flow.svg',
      body_en:
        'The site is static. The build copies the committed artifacts and reports into the page, every route gets its own document so a deep link answers with the app, and every number on the Experiments and Benchmark pages is read from a committed report rather than typed into the page.\n\nThe App has two instruments. The explorer: choose a cell type, read what it receives or sends through each partner, laid out on the hexagonal lattice by column offset, and compare it with the published consensus where the types match. The eye’s input: choose a case and a level, and see what the 721 columns receive frame by frame, beside the ground truth the case grades.',
      body_es:
        'El sitio es estático. El build copia los artefactos y reportes versionados en la página, cada ruta tiene su propio documento para que un enlace profundo responda con la app, y cada número de las páginas Experimentos y Benchmark se lee de un reporte versionado en vez de escribirse en la página.\n\nLa App tiene dos instrumentos. El explorador: elegir un tipo celular, leer lo que recibe o envía por cada socio, dispuesto en la retícula hexagonal por desplazamiento de columna, y compararlo con el consenso publicado donde los tipos coinciden. La entrada del ojo: elegir un caso y un nivel, y ver lo que reciben las 721 columnas cuadro a cuadro, junto a la verdad de terreno que el caso evalúa.',
    },
    {
      id: 'science',
      en: 'From wiring to a network',
      es: 'Del cableado a una red',
      svg: 'svg/tech/04-the-science.svg',
      body_en:
        'Each neuron is a passive point neuron: its voltage relaxes to rest with a time constant and is driven by the rectified voltages of its presynaptic partners, each through a weight that is the product of a sign, a synapse count and a strength. The sign and the count come from the connectome; the strength, the time constant and the resting potential are what the three regimes may or may not train.\n\nOn the lattice network a cell type is a filter repeated across the eye: the average number of synapses a cell receives from each column offset. On the whole-visual-system network every cell and every connection is its own.',
      body_es:
        'Cada neurona es una neurona puntual pasiva: su voltaje relaja al reposo con una constante de tiempo y es impulsado por los voltajes rectificados de sus socios presinápticos, cada uno a través de un peso que es el producto de un signo, un conteo de sinapsis y una intensidad. El signo y el conteo vienen del conectoma; la intensidad, la constante de tiempo y el potencial de reposo son lo que los tres regímenes pueden o no entrenar.\n\nEn la red en retícula un tipo celular es un filtro repetido a lo largo del ojo: el número medio de sinapsis que una célula recibe desde cada desplazamiento de columna. En la red del sistema visual completo cada célula y cada conexión es propia.',
    },
    {
      id: 'contracts',
      en: 'Contracts and controls',
      es: 'Contratos y controles',
      svg: 'svg/tech/05-contracts.svg',
      body_en:
        'Two contracts bind the product. The ingestion contract rejects malformed rows of the release with a reason and flags doubtful ones, such as neurotransmitter calls below a confidence threshold; for vision, it rejects any rendered clip that breaks what its source must carry, and masked depth is counted, never dropped. The artifact contract is the compact file plus a manifest recording its source, its digest and its terms; a TypeScript mirror of it fails the build when the two drift.\n\nThe controls are part of the contract too: a degree-preserving rewiring, a size-matched random graph and a sign shuffle, each compiled to exactly the size of the measured network, with the version of the algorithm that drew them.',
      body_es:
        'Dos contratos rigen el producto. El contrato de ingesta rechaza filas malformadas de la liberación con un motivo y marca las dudosas, como llamadas de neurotransmisor bajo un umbral de confianza; para visión, rechaza todo clip renderizado que rompa lo que su fuente debe traer, y la profundidad enmascarada se cuenta, nunca se descarta. El contrato de artefactos es el archivo compacto más un manifiesto que registra su origen, su digest y sus términos; un espejo TypeScript de él rompe el build cuando ambos divergen.\n\nLos controles también son parte del contrato: un recableado que preserva grados, un grafo aleatorio del mismo tamaño y una permutación de signos, cada uno compilado exactamente al tamaño de la red medida, con la versión del algoritmo que los generó.',
    },
  ],
};

const config: ShellConfig = {
  product: { name: 'Conectoma', mark: <Hexagon size={18} aria-hidden="true" /> },
  routes: [
    { path: '/', en: 'App', es: 'App' },
    { path: '/introduction', en: 'Introduction', es: 'Introducción' },
    { path: '/methodology', en: 'Methodology', es: 'Metodología' },
    { path: '/implementation', en: 'Implementation', es: 'Implementación' },
    { path: '/experiments', en: 'Experiments', es: 'Experimentos' },
    { path: '/benchmark', en: 'Benchmark', es: 'Benchmark' },
  ],
  links: {
    github: EXTERNAL_LINKS.github,
    personal: EXTERNAL_LINKS.personal,
    portfolio: EXTERNAL_LINKS.portfolio,
  },
  version: displayVersion,
  // ADR-0071: the App route is the viewport; its panels scroll inside themselves and the document never does.
  fixedRoutes: ['/'],
  architecture,
  footer: {
    license: { en: 'MIT license', es: 'Licencia MIT' },
    provenance: {
      en: 'Connectome: Janelia MaleCNS v1.0 (CC-BY, Berg et al., Cell 2026). Engine: flyvis (MIT). Published consensus for comparison: Lappalainen et al., Nature 2024.',
      es: 'Conectoma: Janelia MaleCNS v1.0 (CC-BY, Berg et al., Cell 2026). Motor: flyvis (MIT). Consenso publicado para comparar: Lappalainen et al., Nature 2024.',
    },
    disclaimer: {
      en: 'A research product. It does not claim that flies compute depth or segmentation the way it is asked here.',
      es: 'Un producto de investigación. No afirma que las moscas calculen profundidad o segmentación como aquí se pregunta.',
    },
  },
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <CitationsProvider items={CITATIONS}>
        <AppShell config={config}>
          <Routes>
            <Route path="/" element={<AppPage />} />
            <Route path="/introduction" element={<Introduction />} />
            <Route path="/methodology" element={<Methodology />} />
            <Route path="/implementation" element={<Implementation />} />
            <Route path="/experiments" element={<Experiments />} />
            <Route path="/benchmark" element={<Benchmark />} />
            <Route path="*" element={<AppPage />} />
          </Routes>
        </AppShell>
      </CitationsProvider>
    </BrowserRouter>
  </StrictMode>,
);
