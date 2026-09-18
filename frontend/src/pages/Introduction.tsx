import { Callout, Equation, InlineMath } from '@fasl-work/caos-app-shell';
import SectionRefs from '../components/SectionRefs';
import InlineSvg from '../components/InlineSvg';
import { useT } from '../lib/i18n';

export default function Introduction() {
  const t = useT();
  return (
    <div className="page-body wide prose">
      <div className="page-head">
        <h1>{t('Introduction', 'Introducción')}</h1>
        <p className="lede">
          {t(
            'Conectoma takes the measured wiring of the visual system of a male fruit fly and uses it, frozen, as the architecture of a network for computer vision: depth from a moving camera and fast segmentation. What the connectome measures, which cells connect, through how many synapses and with which sign, never changes; only what it cannot measure may learn. It is not a claim that flies compute depth or segment scenes the way a camera pipeline does, and every result is compared with networks that keep the size of the wiring but not its biology, where the effective weight of a connection is ',
            'Conectoma toma el cableado medido del sistema visual de una mosca de la fruta macho y lo usa, congelado, como la arquitectura de una red para visión por computador: profundidad desde una cámara en movimiento y segmentación rápida. Lo que el conectoma mide, qué células se conectan, a través de cuántas sinapsis y con qué signo, nunca cambia; solo aprende lo que no puede medir. No afirma que las moscas calculen profundidad o segmenten escenas como lo hace una cadena de cámara, y cada resultado se compara con redes que conservan el tamaño del cableado pero no su biología, donde el peso efectivo de una conexión es ',
          )}
          <InlineMath tex="w_{ij} = \sigma_{t_j}\,\alpha_{t_i t_j}\,N_{ij}" />.
        </p>
      </div>

      <section>
        <h2>{t('The question', 'La pregunta')}</h2>
        <p>
          {t(
            'Deep networks for vision are designed: someone chooses the layers, the connections and the width, then training sets every weight. A connectome is the opposite kind of object. It is a wiring diagram measured in an animal, down to the synapse, that evolution shaped for the animal’s own visual tasks. The question here is whether that measured wiring, used as it is, is a good prior for machine vision: whether a network whose connectivity is fixed by the fly’s nervous system learns depth or segmentation better, faster or more robustly than networks of the same size whose connectivity is arbitrary.',
            'Las redes profundas para visión se diseñan: alguien elige las capas, las conexiones y el ancho, y luego el entrenamiento fija cada peso. Un conectoma es el tipo opuesto de objeto. Es un diagrama de cableado medido en un animal, hasta la sinapsis, que la evolución moldeó para las tareas visuales del propio animal. La pregunta aquí es si ese cableado medido, usado tal cual, es un buen prior para la visión artificial: si una red cuya conectividad está fijada por el sistema nervioso de la mosca aprende profundidad o segmentación mejor, más rápido o de forma más robusta que redes del mismo tamaño con conectividad arbitraria.',
          )}
        </p>
        <p>
          {t(
            'The task is chosen to fit the animal. Flies judge distance from motion: when the eye moves, near objects slide across the retina faster than far ones, and gap-climbing flies adapt their behaviour to distances estimated that way. Separating a figure from its background by its relative motion is an equally old fly computation. So the primary task is video from a moving camera: depth from parallax and figure-ground segmentation by relative motion. Single-image depth and semantic segmentation are evaluated too, as conditions the fly was not built for.',
            'La tarea se elige para que calce con el animal. Las moscas juzgan la distancia por el movimiento: cuando el ojo se mueve, los objetos cercanos se desplazan por la retina más rápido que los lejanos, y las moscas que trepan huecos adaptan su conducta a distancias estimadas así. Separar una figura de su fondo por su movimiento relativo es un cómputo igual de antiguo en la mosca. Por eso la tarea principal es video desde una cámara en movimiento: profundidad desde paralaje y segmentación figura-fondo por movimiento relativo. La profundidad desde una sola imagen y la segmentación semántica también se evalúan, como condiciones para las que la mosca no fue construida.',
          )}
        </p>
        <p>
          {t(
            'A positive answer is not assumed. The product is built so that a negative answer is visible and reportable: if the measured wiring does no better than its controls, that is the result.',
            'No se supone una respuesta positiva. El producto está construido para que una respuesta negativa sea visible y reportable: si el cableado medido no lo hace mejor que sus controles, ese es el resultado.',
          )}
        </p>
        <SectionRefs ids={['pick2005', 'reichardt1983']} />
      </section>

      <section>
        <h2>{t('The fly’s visual system', 'El sistema visual de la mosca')}</h2>
        <p>
          {t(
            'The compound eye of Drosophila is a hexagonal array of facets, each looking in a slightly different direction. Behind each facet sit photoreceptors: six outer ones (R1 to R6) that carry luminance and two inner ones (R7 and R8) that carry colour. Their signals enter the optic lobe, a stack of neuropils in which the hexagonal array is preserved as columns, one column per point of the visual field. Each column holds the same repertoire of cell types, which is why a cell type can be described as a filter repeated across the eye.',
            'El ojo compuesto de Drosophila es un arreglo hexagonal de facetas, cada una mirando en una dirección ligeramente distinta. Detrás de cada faceta hay fotorreceptores: seis externos (R1 a R6) que llevan luminancia y dos internos (R7 y R8) que llevan color. Sus señales entran al lóbulo óptico, una pila de neurópilos en que el arreglo hexagonal se preserva como columnas, una columna por punto del campo visual. Cada columna contiene el mismo repertorio de tipos celulares, y por eso un tipo celular puede describirse como un filtro repetido a lo largo del ojo.',
          )}
        </p>
        <p>
          {t(
            'The lamina receives the photoreceptors; the medulla combines signals across neighbouring columns; the lobula and lobula plate extract features and motion. The best understood computation is local motion: four subtypes of T4 cells respond to bright edges and four of T5 to dark edges, each subtype preferring one of the four cardinal directions. From the lobula, projection neurons (the lobula columnar and lobula plate-lobula columnar types) carry visual features to the central brain.',
            'La lámina recibe a los fotorreceptores; la médula combina señales entre columnas vecinas; la lóbula y la placa lobular extraen rasgos y movimiento. El cómputo mejor entendido es el movimiento local: cuatro subtipos de células T4 responden a bordes claros y cuatro de T5 a bordes oscuros, cada subtipo prefiriendo una de las cuatro direcciones cardinales. Desde la lóbula, neuronas de proyección (los tipos columnares de la lóbula y los columnares placa lobular-lóbula) llevan rasgos visuales al cerebro central.',
          )}
        </p>
        <SectionRefs ids={['maisak2013', 'nern2025']} />
      </section>

      <section>
        <h2>{t('The connectome', 'El conectoma')}</h2>
        <p>
          {t(
            'The source is the complete connectome of the central nervous system of a male Drosophila, released by Janelia as MaleCNS v1.0 under a CC-BY license. It lists every neuron with its cell type, class and side, a neurotransmitter prediction per neuron, and the number of synapses between every ordered pair of neurons: 151,856,684 connected pairs. The right optic lobe alone contributes 48,415 typed neurons in 253 cell types to this product.',
            'La fuente es el conectoma completo del sistema nervioso central de una Drosophila macho, liberado por Janelia como MaleCNS v1.0 con licencia CC-BY. Lista cada neurona con su tipo celular, clase y lado, una predicción de neurotransmisor por neurona, y el número de sinapsis entre cada par ordenado de neuronas: 151.856.684 pares conectados. Solo el lóbulo óptico derecho aporta 48.415 neuronas tipificadas en 253 tipos celulares a este producto.',
          )}
        </p>
        <p>
          {t(
            'The sign of a connection is not measured directly. It comes from a classifier that predicts each synapse’s transmitter from electron microscopy images, reported at 87 percent accuracy per synapse and 94 percent per neuron. Acetylcholine is taken as excitatory; glutamate, GABA and histamine as inhibitory. That makes the sign an input with a known error rate, which is why one of the controls shuffles it.',
            'El signo de una conexión no se mide directamente. Viene de un clasificador que predice el transmisor de cada sinapsis a partir de imágenes de microscopía electrónica, reportado con 87 por ciento de exactitud por sinapsis y 94 por ciento por neurona. La acetilcolina se toma como excitatoria; glutamato, GABA e histamina como inhibitorios. Eso hace del signo una entrada con una tasa de error conocida, y por eso uno de los controles lo permuta.',
          )}
        </p>
        <SectionRefs ids={['berg2026', 'eckstein2024']} />
      </section>

      <section>
        <h2>{t('From wiring to a network', 'Del cableado a una red')}</h2>
        <p>
          {t(
            'Every neuron is a passive point neuron with graded synapses, the model of the published connectome-constrained network of the fly visual system. Its voltage relaxes to a resting potential with a time constant and is driven by the rectified voltages of its presynaptic partners:',
            'Cada neurona es una neurona puntual pasiva con sinapsis graduadas, el modelo de la red restringida por conectoma publicada del sistema visual de la mosca. Su voltaje relaja a un potencial de reposo con una constante de tiempo y es impulsado por los voltajes rectificados de sus socios presinápticos:',
          )}
        </p>
        <Equation
          tex="\tau_{t_i}\,\frac{dV_i}{dt} = -V_i + \sum_j \alpha_{t_i t_j}\,\sigma_{t_j}\,N_{ij}\,\operatorname{ReLU}(V_j) + V^{\mathrm{rest}}_{t_i} + e_i"
          caption={t(
            'The network dynamics: the synapse count N and the sign sigma come from the connectome and are frozen; the strength alpha, the time constant tau and the resting potential are what a regime may train; e is the visual input, non-zero only at the photoreceptors.',
            'La dinámica de la red: el conteo de sinapsis N y el signo sigma vienen del conectoma y están congelados; la intensidad alfa, la constante de tiempo tau y el potencial de reposo son lo que un régimen puede entrenar; e es la entrada visual, distinta de cero solo en los fotorreceptores.',
          )}
        />
        <p>
          {t(
            'On the lattice network, a cell type is placed on a hexagonal lattice of 721 columns and its connections are filters: the average number of synapses a cell receives from each column offset, measured over the whole optic lobe.',
            'En la red en retícula, un tipo celular se ubica en una retícula hexagonal de 721 columnas y sus conexiones son filtros: el número medio de sinapsis que una célula recibe desde cada desplazamiento de columna, medido sobre todo el lóbulo óptico.',
          )}
        </p>
        <Equation
          tex="F_{t_i t_j}(\Delta u, \Delta v) = \frac{1}{|t_i|}\sum_{i \in t_i}\ \sum_{j \in t_j,\ c(i) - c(j) = (\Delta u, \Delta v)} N_{ij}"
          caption={t(
            'The average filter from type t_j onto type t_i: the synapses between cells whose columns differ by the offset, divided by the number of placed cells of the target type.',
            'El filtro medio desde el tipo t_j sobre el tipo t_i: las sinapsis entre células cuyas columnas difieren en el desplazamiento, divididas por el número de células ubicadas del tipo destino.',
          )}
        />
        <p>
          {t(
            'Three regimes decide what "frozen" means. In R0, the reservoir, nothing in the network trains and only a readout outside it learns. In R1, the published model’s regime, one strength per connected pair of types and one time constant and resting potential per type train. In R2, every connection and every neuron has its own. The wiring, the counts and the signs are the same measurement in all three.',
            'Tres regímenes deciden qué significa "congelado". En R0, el reservorio, nada en la red entrena y solo aprende un lector fuera de ella. En R1, el régimen del modelo publicado, entrenan una intensidad por par de tipos conectados y una constante de tiempo y un potencial de reposo por tipo. En R2, cada conexión y cada neurona tiene los suyos. El cableado, los conteos y los signos son la misma medición en los tres.',
          )}
        </p>
        <InlineSvg src="svg/docs/frozen-regimes.svg" label={t('What each regime may change', 'Lo que cada régimen puede cambiar')} />
        <Equation
          tex="\rho\big(|W|\big) < 1 \;\Longrightarrow\; \text{stable at every operating point}"
          caption={t(
            'The loop-gain bound: when the spectral radius of the absolute weight matrix is below one, the threshold-linear network is stable wherever it operates. The whole visual system, frozen, needs it; the lattice settles without it.',
            'La cota de ganancia de lazo: cuando el radio espectral de la matriz de pesos absolutos es menor que uno, la red lineal por umbral es estable donde sea que opere. El sistema visual completo, congelado, la necesita; la retícula se estabiliza sin ella.',
          )}
        />
        <SectionRefs ids={['lappalainen2024', 'lukosevicius2009']} />
      </section>

      <section>
        <h2>{t('What is built so far', 'Lo construido hasta ahora')}</h2>
        <ol>
          <li>{t('The consensus connectome of the right optic lobe, built from the release tables in about half a minute, with its retinotopic columns inferred and validated by holdout.', 'El conectoma de consenso del lóbulo óptico derecho, construido desde las tablas de la liberación en cerca de medio minuto, con sus columnas retinotópicas inferidas y validadas por exclusión.')}</li>
          <li>{t('Its comparison with the published consensus of the earlier medulla reconstructions: shared types, recovered connections, sign agreement, filter orientation.', 'Su comparación con el consenso publicado de las reconstrucciones anteriores de la médula: tipos compartidos, conexiones recuperadas, acuerdo de signo, orientación de los filtros.')}</li>
          <li>{t('The lattice network: every cell type placed at its measured density, every filter expanded so each target cell receives its full input, compiled in memory in about three seconds.', 'La red en retícula: cada tipo celular ubicado según su densidad medida, cada filtro expandido para que cada célula destino reciba su entrada completa, compilada en memoria en unos tres segundos.')}</li>
          <li>{t('The three regimes and three null controls matched in size at the level of cells.', 'Los tres regímenes y tres controles nulos igualados en tamaño a nivel de células.')}</li>
          <li>{t('Parity with the published model, voltage for voltage, and a reproduction of its ensemble’s motion tuning.', 'Paridad con el modelo publicado, voltaje por voltaje, y una reproducción del ajuste al movimiento de su ensamble.')}</li>
          <li>{t('The frozen networks characterised: stability, cost, and what they do with moving edges before any training.', 'Las redes congeladas caracterizadas: estabilidad, costo, y lo que hacen con bordes en movimiento antes de cualquier entrenamiento.')}</li>
          <li>{t('The whole visual system, neuron by neuron: both optic lobes and their projections to the central brain.', 'El sistema visual completo, neurona por neurona: ambos lóbulos ópticos y sus proyecciones al cerebro central.')}</li>
          <li>{t('The vision data: TartanAir, Sintel, Spring, Hypersim and scenes rendered through the fly’s own compound eye, all on the engine’s 721-column lattice, checked by contract, and split by geometry so that no scene is seen in training and in test.', 'Los datos de visión: TartanAir, Sintel, Spring, Hypersim y escenas renderizadas a través del propio ojo compuesto de la mosca, todo sobre la retícula de 721 columnas del motor, verificado por contrato, y particionado por geometría para que ninguna escena se vea en entrenamiento y en prueba.')}</li>
          <li>{t('Sixteen validation cases, each one physical quantity over six levels, from ego speed and fog to a looming disk and a camera that only turns.', 'Dieciséis casos de validación, cada uno una cantidad física en seis niveles, desde la velocidad propia y la niebla hasta un disco que se aproxima y una cámara que solo gira.')}</li>
        </ol>
        <p>
          {t(
            'The method ladder for depth and segmentation, and the benchmark against learned and foundation models, arrive in the next units. The App shows the connectome they are built on, and what its eye receives in every case.',
            'La escalera de métodos para profundidad y segmentación, y el benchmark contra modelos aprendidos y fundacionales, llegan en las próximas unidades. La App muestra el conectoma sobre el que se construyen, y lo que recibe su ojo en cada caso.',
          )}
        </p>
        <SectionRefs ids={['takemura2015', 'takemura2017', 'flyvis']} />
      </section>

      <section>
        <h2>{t('What this is, and what it is not', 'Lo que esto es, y lo que no es')}</h2>
        <Callout variant="honest" title={t('Scope', 'Alcance')}>
          {t(
            'It is a test of one idea, a measured wiring diagram used as a frozen architecture, run so that it can fail. It is not a model of how a fly sees, not a whole-brain emulation, and not a competitor to foundation models for depth. Where the product has to approximate the animal (a type sparser than one cell per twenty columns becomes one population node; the retina of the release is incomplete at its edges), the pages say so where the approximation is made.',
            'Es una prueba de una idea, un diagrama de cableado medido usado como arquitectura congelada, ejecutada de modo que pueda fallar. No es un modelo de cómo ve una mosca, ni una emulación de cerebro completo, ni un competidor de los modelos fundacionales de profundidad. Donde el producto debe aproximar al animal (un tipo más escaso que una célula cada veinte columnas se vuelve un nodo de población; la retina de la liberación está incompleta en sus bordes), las páginas lo dicen donde se hace la aproximación.',
          )}
        </Callout>
        <SectionRefs ids={['wang2026', 'lappalainen2024']} />
      </section>
    </div>
  );
}
