import { Callout, Equation, SubTabs } from '@fasl-work/caos-app-shell';
import SectionRefs from '../components/SectionRefs';
import InlineSvg from '../components/InlineSvg';
import { useT } from '../lib/i18n';

function Commands({ lines }: { lines: string[] }) {
  return (
    <pre className="cx-code">
      <code>{lines.join('\n')}</code>
    </pre>
  );
}

export default function Implementation() {
  const t = useT();

  const architecture = (
    <section>
      <h2>{t('Architecture', 'Arquitectura')}</h2>
      <p>
        {t(
          'The offline repository is the product; this site is a projection of an audited subset of it. Heavy inputs (the 14 GB of release tables, the published models, the compiled graphs, the null-control specifications and the run logs) live in two local roots outside git. The pipeline turns them into compact artifacts that are committed, each with a manifest, and the site replays only those.',
          'El repositorio offline es el producto; este sitio es una proyección de un subconjunto auditado de él. Las entradas pesadas (los 14 GB de tablas de la liberación, los modelos publicados, los grafos compilados, las especificaciones de controles nulos y los registros de ejecución) viven en dos raíces locales fuera de git. El pipeline las convierte en artefactos compactos que se versionan, cada uno con un manifiesto, y el sitio reproduce solo esos.',
        )}
      </p>
      <InlineSvg src="svg/tech/02-lanes.svg" label={t('Offline and in the browser', 'Offline y en el navegador')} />
      <p>
        {t(
          'Two environments keep the lanes apart: a pipeline environment on Python 3.12 (the engine requires Python below 3.13) with the network engine, torch and the Arrow readers, and a light environment for linting and repository checks. The web is a static React application built on the shared CAOS shell; it reads JSON artifacts and never calls a server.',
          'Dos entornos mantienen separados los carriles: un entorno de pipeline en Python 3.12 (el motor requiere Python bajo 3.13) con el motor de red, torch y los lectores Arrow, y un entorno liviano para lint y verificaciones del repositorio. La web es una aplicación React estática construida sobre el shell CAOS compartido; lee artefactos JSON y nunca llama a un servidor.',
        )}
      </p>
      <Callout variant="honest" title={t('Where it works, where it does not', 'Dónde funciona, dónde no')}>
        {t(
          'Everything on this site is reproducible from a clone plus the public release. What cannot be reproduced without a GPU is the timing of the network runs; their results are committed, and the commands that produced them are listed under Pipeline.',
          'Todo en este sitio es reproducible desde un clon más la liberación pública. Lo que no puede reproducirse sin una GPU son los tiempos de las ejecuciones de la red; sus resultados están versionados, y los comandos que los produjeron se listan en Pipeline.',
        )}
      </Callout>
      <SectionRefs ids={['flyvis', 'berg2026']} />
    </section>
  );

  const pipeline = (
    <section>
      <h2>{t('The pipeline commands', 'Los comandos del pipeline')}</h2>
      <p>
        {t(
          'One command line drives the offline lane. Each command reads the local roots, writes a compact committed result or report, and prints what it measured. The long ones keep every finished step in a run log, so an interrupted run resumes where it stopped.',
          'Una línea de comandos maneja el carril offline. Cada comando lee las raíces locales, escribe un resultado o reporte compacto versionado, e imprime lo que midió. Los largos guardan cada paso terminado en un registro de ejecución, así que una ejecución interrumpida continúa donde se detuvo.',
        )}
      </p>
      <Commands
        lines={[
          'python data-pipeline/run.py build-connectome          # release tables -> connectome (about 30 s)',
          'python data-pipeline/run.py compare-consensus         # against the published consensus',
          'python data-pipeline/run.py export-web                # the explorer artifact and its manifest',
          'python data-pipeline/run.py parity-published          # the published model through this path (about 40 min)',
          'python data-pipeline/run.py characterize-connectome   # the frozen lattice and its controls (about 40 min)',
          'python data-pipeline/run.py build-visual-cns          # the whole visual system, neuron level (about 1 min)',
          'python data-pipeline/run.py characterize-visual-cns   # its stability, gain and cost (about 6 min)',
        ]}
      />
      <p>
        {t(
          'The connectome build runs six stages: select the neurons, assign their signs, scan the connection table, assign retinotopic columns, accumulate the filters, and write the specification. It finishes in about half a minute on 151 million rows because the scan is batched Arrow and the column inference runs on compressed sparse arrays.',
          'La construcción del conectoma corre seis etapas: seleccionar las neuronas, asignar sus signos, recorrer la tabla de conexiones, asignar columnas retinotópicas, acumular los filtros y escribir la especificación. Termina en cerca de medio minuto sobre 151 millones de filas porque el recorrido es Arrow por lotes y la inferencia de columnas corre sobre arreglos dispersos comprimidos.',
        )}
      </p>
      <SectionRefs ids={['berg2026']} />
    </section>
  );

  const compiler = (
    <section>
      <h2>{t('The compiler', 'El compilador')}</h2>
      <p>
        {t(
          'The engine ships a compiler for the average-filter format, and it is the reference this product’s compiler is tested against, table for table: on the published connectome both produce the same 45,669 cells and 1,513,231 connections, every field equal. It is not used directly because it caches compiled graphs by file path rather than content, because every null-control seed would leave a compiled copy on disk, because its expansion is a Python loop, and because it loses filter entries between sublattices.',
          'El motor trae un compilador para el formato de filtros medios, y es la referencia contra la que se prueba el compilador de este producto, tabla por tabla: sobre el conectoma publicado ambos producen las mismas 45.669 células y 1.513.231 conexiones, cada campo igual. No se usa directamente porque guarda grafos compilados por ruta de archivo en vez de contenido, porque cada semilla de control nulo dejaría una copia compilada en disco, porque su expansión es un bucle en Python, y porque pierde entradas de filtro entre subretículas.',
        )}
      </p>
      <p>
        {t(
          'The lattice compiler keeps the graph in memory, expands every filter entry as one vectorised operation over the cells of the target type, and records the SHA-256 of the specification in the network’s configuration, so a checkpoint names the exact graph it was trained on and loading it against a changed file fails. The neuron-level compiler does the same for the whole visual system, from a compressed graph of twelve million connections.',
          'El compilador en retícula mantiene el grafo en memoria, expande cada entrada de filtro como una operación vectorizada sobre las células del tipo destino, y registra el SHA-256 de la especificación en la configuración de la red, así un punto de control nombra el grafo exacto con que se entrenó y cargarlo contra un archivo cambiado falla. El compilador a nivel de neurona hace lo mismo para el sistema visual completo, desde un grafo comprimido de doce millones de conexiones.',
        )}
      </p>
      <Equation
        tex="\sum_j N_{ij} = \sum_{(\Delta u, \Delta v)} F_{t_i t_j}(\Delta u, \Delta v)\quad\text{for every target cell } i \text{ whose filter fits the lattice}"
        caption={t(
          'The property the target-centric expansion guarantees and the tests assert: each target receives its full measured filter.',
          'La propiedad que garantiza la expansión centrada en el destino y que verifican las pruebas: cada destino recibe su filtro medido completo.',
        )}
      />
      <SectionRefs ids={['lappalainen2024', 'flyvis']} />
    </section>
  );

  const engine = (
    <section>
      <h2>{t('The network engine', 'El motor de red')}</h2>
      <p>
        {t(
          'The network engine is flyvis, the reference implementation of the published connectome-constrained model (MIT). It provides the dynamics, the parameter classes, the published ensemble of fifty trained models, the moving-edge stimulus and the tuning analysis. This product adds its compilers, its regimes as parameter configurations, and its checks.',
          'El motor de red es flyvis, la implementación de referencia del modelo restringido por conectoma publicado (MIT). Aporta la dinámica, las clases de parámetros, el ensamble publicado de cincuenta modelos entrenados, el estímulo de bordes en movimiento y el análisis de ajuste. Este producto agrega sus compiladores, sus regímenes como configuraciones de parámetros, y sus verificaciones.',
        )}
      </p>
      <p>
        {t(
          'Several behaviours of the engine were found while building and are handled rather than left to chance: its storage root is fixed when it is first imported; importing it sets the default device of torch; its compiled connectomes are cached by path; its parameter sharing is built with a Python loop, replaced here by a hash join that returns identical indices twenty to thirty-six times faster; and its storage layer’s last release cannot compile a connectome on Windows, so it is pinned to the upstream fix.',
          'Varios comportamientos del motor se encontraron al construir y se manejan en vez de dejarse al azar: su raíz de almacenamiento queda fija la primera vez que se importa; importarlo fija el dispositivo por defecto de torch; sus conectomas compilados se guardan por ruta; su compartición de parámetros se construye con un bucle en Python, reemplazado aquí por un join por hash que devuelve índices idénticos de veinte a treinta y seis veces más rápido; y la última versión de su capa de almacenamiento no puede compilar un conectoma en Windows, así que se fija al commit que lo corrige.',
        )}
      </p>
      <Callout variant="note" title={t('Pins', 'Versiones fijadas')}>
        {t(
          'flyvis 1.2.0; torch 2.14.0 and torchvision 0.29.0 without a build tag, so the CPU wheel in CI and the CUDA 12.6 wheel on the GPU satisfy the same pin; datamate at the upstream commit that fixes compiling on Windows.',
          'flyvis 1.2.0; torch 2.14.0 y torchvision 0.29.0 sin etiqueta de build, así la rueda CPU en CI y la rueda CUDA 12.6 en la GPU satisfacen la misma versión; datamate en el commit que corrige la compilación en Windows.',
        )}
      </Callout>
      <SectionRefs ids={['flyvis', 'lappalainen2024']} />
    </section>
  );

  const reproducibility = (
    <section>
      <h2>{t('Reproducibility', 'Reproducibilidad')}</h2>
      <p>
        {t(
          'Every artifact is bound to what it came from. The connectome specification records its configuration, the frame its offsets are written in, the placement summary and the rules it is meant to be compiled with. Every network records the SHA-256 of its graph. The explorer artifact is written without a timestamp, so the same inputs give the same bytes, and its manifest records its digest, which the browser checks before showing it.',
          'Cada artefacto está ligado a su origen. La especificación del conectoma registra su configuración, el marco en que se escriben sus desplazamientos, el resumen de ubicación y las reglas con que debe compilarse. Cada red registra el SHA-256 de su grafo. El artefacto del explorador se escribe sin marca de tiempo, así las mismas entradas dan los mismos bytes, y su manifiesto registra su digest, que el navegador verifica antes de mostrarlo.',
        )}
      </p>
      <p>
        {t(
          'The long runs keep a run log: every finished model, comparison and stage is written before the next one starts, under a signature of the inputs it depends on (specification digest, stimulus, device, algorithm version). A rerun reuses finished steps, and a log computed from other inputs is set aside rather than reused. Reports are written through one writer that makes numpy values plain and replaces the file in one step, after a forty-minute run once lost its results to a serialisation error at its very end.',
          'Las ejecuciones largas llevan un registro: cada modelo, comparación y etapa terminados se escriben antes de que empiece el siguiente, bajo una firma de las entradas de que dependen (digest de la especificación, estímulo, dispositivo, versión del algoritmo). Una nueva ejecución reutiliza los pasos terminados, y un registro calculado desde otras entradas se aparta en vez de reutilizarse. Los reportes se escriben con un solo escritor que vuelve simples los valores numpy y reemplaza el archivo en un paso, después de que una ejecución de cuarenta minutos perdiera una vez sus resultados por un error de serialización justo al final.',
        )}
      </p>
      <Callout variant="honest" title={t('A tolerance, not a hash', 'Una tolerancia, no un hash')}>
        {t(
          'Simulations are compared within a numerical tolerance, not bit for bit: the same network on another device sums in another order. The parity check allows 1e-5 and measures differences below 4e-6.',
          'Las simulaciones se comparan dentro de una tolerancia numérica, no bit a bit: la misma red en otro dispositivo suma en otro orden. La verificación de paridad permite 1e-5 y mide diferencias bajo 4e-6.',
        )}
      </Callout>
      <SectionRefs ids={['lappalainen2024']} />
    </section>
  );

  const contracts = (
    <section>
      <h2>{t('Contracts', 'Contratos')}</h2>
      <p>
        {t(
          'The ingestion contract declares the columns each release table must carry, requires positive synapse counts and column coordinates within range, rejects malformed rows with a reason and flags doubtful ones, such as transmitter calls below a confidence threshold. A truncated download is rejected as an unreadable Arrow file, which is the failure this product hit while fetching the connection table.',
          'El contrato de ingesta declara las columnas que debe traer cada tabla de la liberación, exige conteos de sinapsis positivos y coordenadas de columna dentro de rango, rechaza filas malformadas con un motivo y marca las dudosas, como llamadas de transmisor bajo un umbral de confianza. Una descarga truncada se rechaza como un archivo Arrow ilegible, que es la falla que este producto tuvo al descargar la tabla de conexiones.',
        )}
      </p>
      <p>
        {t(
          'The connectome specification is the engine’s average-filter format plus a few fields: each node’s placement and measured density, and a compile block stating that filters are expanded from their targets and that population nodes drive every cell of their targets. The explorer artifact is a compact form of the same facts: one row per cell type, one row per connection whose filter is three parallel arrays, and the published filters that match. Three checks bind it: the pipeline’s tests rebuild it from the committed specification and require the same bytes; the web’s build validates it field by field against a TypeScript mirror and against the counts and digest its manifest declares; and the page validates it again before showing anything, refusing an artifact that does not match with the field that drifted.',
          'La especificación del conectoma es el formato de filtros medios del motor más algunos campos: la ubicación y la densidad medida de cada nodo, y un bloque de compilación que declara que los filtros se expanden desde sus destinos y que los nodos de población excitan o inhiben a cada célula de sus destinos. El artefacto del explorador es una forma compacta de los mismos hechos: una fila por tipo celular, una fila por conexión cuyo filtro son tres arreglos paralelos, y los filtros publicados que coinciden. Tres verificaciones lo atan: las pruebas del pipeline lo reconstruyen desde la especificación versionada y exigen los mismos bytes; el build de la web lo valida campo por campo contra un espejo TypeScript y contra los conteos y el digest que declara su manifiesto; y la página lo valida otra vez antes de mostrar nada, rechazando un artefacto que no coincide con el campo que divergió.',
        )}
      </p>
      <SectionRefs ids={['eckstein2024', 'berg2026']} />
    </section>
  );

  const gates = (
    <section>
      <h2>{t('Tests and gates', 'Pruebas y compuertas')}</h2>
      <p>
        {t(
          'The suite runs in continuous integration on every push: the build contract, the column inference and its holdout, the comparison and its orientation measure, the placement rule, the compiler against the engine’s own on the published connectome, the target-centric totals, the regimes and their gradients, the size-matched controls, the neuron-level classes and the loop-gain estimate. Tests that need the local release cache or the downloaded ensemble skip in CI and run locally.',
          'La suite corre en integración continua en cada push: el contrato de construcción, la inferencia de columnas y su exclusión, la comparación y su medida de orientación, la regla de ubicación, el compilador contra el del motor sobre el conectoma publicado, los totales centrados en el destino, los regímenes y sus gradientes, los controles igualados en tamaño, las clases a nivel de neurona y la estimación de ganancia de lazo. Las pruebas que necesitan la caché local de la liberación o el ensamble descargado se omiten en CI y corren localmente.',
        )}
      </p>
      <p>
        {t(
          'The web has its own gate, run on the built site in a real browser at 1280x800, 1600x900 and 2560x1440, in both themes and both languages. It first proves it is looking at this product: the brand reads Conectoma and the explorer artifact verified against its manifest. Then, on the App, the page is exactly the viewport, the control rail shows every control without scrolling, every tab bar is one row, and what is actually drawn (the union of the painted hexagons and the chart’s plot, not the size of the svg element) covers at least half the screen. Every documentation route must answer 200 with its own heading, take the full width, and, on Experiments and Benchmark, fill its tables from the reports. Each architecture diagram must be the one its tab names, in the reader’s language and drawn in the theme’s colours. The deploy runs the same gate and uploads nothing that fails it.',
          'La web tiene su propia compuerta, corrida sobre el sitio construido en un navegador real en 1280x800, 1600x900 y 2560x1440, en ambos temas y ambos idiomas. Primero prueba que mira este producto: la marca dice Conectoma y el artefacto del explorador se verificó contra su manifiesto. Luego, en la App, la página es exactamente la ventana, el riel de controles muestra cada control sin desplazarse, cada barra de pestañas ocupa una fila, y lo que efectivamente se dibuja (la unión de los hexágonos pintados y el área del gráfico, no el tamaño del elemento svg) cubre al menos la mitad de la pantalla. Cada ruta de documentación debe responder 200 con su propio título, ocupar todo el ancho y, en Experimentos y Benchmark, llenar sus tablas desde los reportes. Cada diagrama de arquitectura debe ser el que nombra su pestaña, en el idioma del lector y dibujado con los colores del tema. El despliegue corre la misma compuerta y no sube nada que la falle.',
        )}
      </p>
      <SectionRefs ids={['flyvis']} />
    </section>
  );

  const deploy = (
    <section>
      <h2>{t('Deploy', 'Despliegue')}</h2>
      <p>
        {t(
          'The site is published on GitHub Pages at its own domain. The build copies the committed artifacts into the page, gives every route its own document so a deep link answers with the app rather than with a 404 page that happens to render it, and uses absolute asset paths so a deep route never resolves them against itself.',
          'El sitio se publica en GitHub Pages en su propio dominio. El build copia los artefactos versionados en la página, da a cada ruta su propio documento para que un enlace profundo responda con la app y no con una página 404 que casualmente la muestra, y usa rutas absolutas de recursos para que una ruta profunda nunca las resuelva contra sí misma.',
        )}
      </p>
      <p>
        {t(
          'A deploy is verified on the live address, not on the build: every route must answer 200 with this product mounted, and the explorer artifact must load and match its manifest. A response of 200 alone is not evidence that the application mounted.',
          'Un despliegue se verifica en la dirección en vivo, no en el build: cada ruta debe responder 200 con este producto montado, y el artefacto del explorador debe cargar y coincidir con su manifiesto. Una respuesta 200 por sí sola no es evidencia de que la aplicación se montó.',
        )}
      </p>
      <SectionRefs ids={['flyvis']} />
    </section>
  );

  return (
    <div className="page-body wide prose">
      <div className="page-head">
        <h1>{t('Implementation', 'Implementación')}</h1>
        <p className="lede">
          {t(
            'How the product is built and how it can be rebuilt: the offline pipeline and its commands, the compilers that turn a specification into a network, the engine and what had to be worked around in it, the rules that make every result reproducible and bound to its inputs, the two data contracts, the tests and the browser gate, and the deploy. It is not a list of frameworks; each section states the exact behaviour and where it stops working.',
            'Cómo se construye el producto y cómo puede reconstruirse: el pipeline offline y sus comandos, los compiladores que convierten una especificación en una red, el motor y lo que hubo que resolver en él, las reglas que hacen cada resultado reproducible y ligado a sus entradas, los dos contratos de datos, las pruebas y la compuerta del navegador, y el despliegue. No es una lista de frameworks; cada sección declara el comportamiento exacto y dónde deja de funcionar.',
          )}
        </p>
      </div>
      <SubTabs
        orientation="vertical"
        ariaLabel={t('Implementation sections', 'Secciones de implementación')}
        tabs={[
          { id: 'architecture', label: t('Architecture', 'Arquitectura'), content: architecture },
          { id: 'pipeline', label: t('Pipeline', 'Pipeline'), content: pipeline },
          { id: 'compiler', label: t('Compiler', 'Compilador'), content: compiler },
          { id: 'engine', label: t('Engine', 'Motor'), content: engine },
          { id: 'reproducibility', label: t('Reproducibility', 'Reproducibilidad'), content: reproducibility },
          { id: 'contracts', label: t('Contracts', 'Contratos'), content: contracts },
          { id: 'gates', label: t('Tests and gates', 'Pruebas y compuertas'), content: gates },
          { id: 'deploy', label: t('Deploy', 'Despliegue'), content: deploy },
        ]}
      />
    </div>
  );
}
