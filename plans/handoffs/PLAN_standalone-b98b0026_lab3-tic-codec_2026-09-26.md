# Cerrar los 3 requisitos pendientes del enunciado del Lab 3: I(X;Y) explícito, componente de IA real, e interpretación 5G/6G

**Date:** 2026-09-26
**Status:** PLANNED
**Bead(s):** none
**Epic:** none
**Chain:** `standalone-b98b0026` seq `1`
**Context:** See `HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-26.md` for session data, test results, and prior approaches.

---

## Problem Statement

El códec `tic_codec.py` está completo, refactorizado a POO, corrido sobre las 4 fuentes reales que pide el enunciado (imagen, audio, texto, video, cada una comprimida y cruda = 7 corridas, todas bit-exactas por SHA-256), y documentado con dos diagramas Archify validados. Sin embargo, el enunciado (página 1/7, único texto confirmado) pide explícitamente tres cosas que el código y el README todavía no cubren: (1) medir información mutua $I(X;Y)$ entre la fuente original y la reconstruida — hoy solo se mide $D_{KL}$ y se verifica SHA-256; (2) "usar IA en algún punto del proceso" — hoy la selección de modo Huffman-vs-bitstrip es una regla fija de comparación de tamaños, no un modelo; (3) "contextualizar todo en redes 5G/6G" — no existe ninguna sección al respecto. Ver el texto exacto del enunciado y de los supuestos declarados en la sección "Evidence & Data" del handoff.

## Key Findings

- El pipeline ya reporta `MetricasAntes`/`MetricasDespues`/`ReporteBloque` con H, KL, autoinformación y SHA-256 — falta únicamente el campo $I(X;Y)$ → impulsa la Fase 1.
- La comparación de tamaños Huffman-vs-bitstrip en `CodecTIC` (que decide el campo `modo` de `CabeceraTIC`) es exactamente el punto donde el enunciado espera "IA" — hoy es una regla fija de una línea, no un modelo → impulsa la Fase 2.
- `GeneradorFuentes` ya genera fuentes sintéticas uniformes/no-uniformes/estructuradas bajo demanda — es suficiente para producir un dataset de entrenamiento pequeño sin depender de datos externos → impulsa la Fase 2.
- La tabla comparativa de 7 fuentes ya tiene todos los números (k, razón, ahorro) que hacen falta para una interpretación 5G/6G; solo falta la prosa interpretativa → impulsa la Fase 3.
- Los tiempos de ejecución reales del barrido de video (2m21s para k=8..256, 44s para k=512..4096, ver Evidence & Data del handoff) son evidencia concreta de latencia de codificación por tamaño de símbolo, directamente relevante para el argumento de latencia vs. ancho de banda de la Fase 3.
- El video de prueba real (28,1s, 160×90) tiene k=512 óptimo con razón 43,565 — el caso más extremo de las 7 fuentes — es el ejemplo más ilustrativo para el argumento eMBB (ancho de banda) de la Fase 3.
- El repo no tiene `bd` (beads) disponible en este entorno; las 3 fases de este plan se trackean solo por este archivo y el checklist del README, no por tareas externas.
- El enunciado solo se conoce en su página 1/7 — cualquier fase de este plan debe declarar sus supuestos explícitamente, seguir el patrón ya establecido en la sección "Supuestos declarados" del README, no asumir en silencio.

## Anti-Goals (What NOT To Do)

- **No modelar símbolos individuales como objetos Python** en ninguna fase nueva — el códec ya evitó esto deliberadamente por rendimiento (ver Key Decisions del handoff); cualquier cómputo de $I(X;Y)$ o de features para el modelo de IA debe usar arrays NumPy vectorizados (`np.unique`, histogramas conjuntos), no loops por símbolo.
- **No intentar correr el video de prueba a los 5 minutos/resolución original del enunciado** — ya se determinó que el decodificador Huffman puro-Python es impracticablemente lento a esa escala (~1µs/símbolo); si se necesita más evidencia de video, generar un segundo clip corto adicional, no forzar el original.
- **No crear ningún repositorio git dentro del vault de Obsidian del usuario**, bajo ninguna circunstancia, incluso si alguna fase genera un apunte o nota de análisis — esa restricción es explícita y no negociable (ver Goal del handoff).
- **No presentar el componente de IA de la Fase 2 como más sofisticado de lo que es** — es un árbol de decisión pequeño entrenado sobre fuentes sintéticas generadas localmente, no un modelo con datos reales de producción; el README debe decir esto explícitamente, seguir el mismo patrón honesto ya usado para la reducción del video.
- **No sobrescribir los 7 JSON de `examples/` sin revisar el diff** — al agregar el campo $I(X;Y)$ en la Fase 1 se regeneran, pero deben committearse como un paso propio y revisable, no mezclados silenciosamente con otro cambio.

## Plan

### Phase 1: Información mutua $I(X;Y)$ explícita

**Goal:** Agregar la métrica de información mutua entre la fuente original y la reconstruida que el enunciado pide explícitamente y que hoy falta.

**Why this approach:** El enunciado dice literalmente "Mida cantidad de información I, entropía H, información mutua I(X;Y) y divergencia KL" (ver cita exacta en el handoff) — hoy el código mide todo excepto $I(X;Y)$. Es la brecha más barata de cerrar porque el pipeline de análisis (`Informacion`, `MetricasDespues`) ya existe; solo falta un método y un campo nuevo.

- Agregar `Informacion.informacion_mutua(conjunta)` (staticmethod, consistente con el resto de la clase): recibe un histograma conjunto vectorizado de pares (símbolo original, símbolo reconstruido) — construido con `np.unique` sobre arrays combinados, igual patrón que `Alfabeto.desde_filas` — y devuelve $I(X;Y) = \sum p(x,y)\log_2\frac{p(x,y)}{p(x)p(y)}$.
- **Caso sin pérdida (todas las 7 corridas actuales):** como $Y=X$ exactamente (verificado por SHA-256), $I(X;Y)=H(X)$ analíticamente — no vale la pena construir el histograma conjunto completo para millones de símbolos solo para reconfirmar esto. Calcular por la vía barata (`I_XY = H`) y **documentar explícitamente en el reporte impreso y el README por qué**, para que no se lea como un bug cuando el profesor vea `I_XY == H` en los 7 JSON existentes.
- **Caso con pérdida (`--perdida n`):** aquí $Y \neq X$ de verdad — construir el histograma conjunto real y calcular $I(X;Y) < H(X)$. Usar el caso ya documentado en el README (`--perdida 3`, k=8, razón 3,44:1, PSNR 38,4 dB) como el primer caso real no trivial.
- Agregar campo `informacion_mutua: float` a `MetricasDespues` (dataclass), mapeado a la clave JSON `"I_XY"` en `.a_dict()`, siguiendo el mismo patrón que `ahorro_pct` → `"ahorro_%"`.
- Regenerar los 7 JSON de `examples/*/` corriendo `codificar` de nuevo para cada uno (todos son lossless, así que solo cambia el nuevo campo `I_XY = H`, no ningún otro valor) y el ejemplo `--perdida 3` para tener al menos un caso no trivial documentado.
- Actualizar el README: nueva fila "$I(X;Y)$" en la tabla de "Resultados experimentales de referencia" para el caso con pérdida, y una nota en "Cómo se cumple cada requisito" marcando esta fila como cubierta.

**Files:** `src/tic_codec.py` (clase `Informacion`, dataclass `MetricasDespues`, método que arma el reporte "después"); `examples/*/*.json` (7 archivos regenerados); `README.md` (tabla de referencia + tabla de requisitos).
**Validates with:** `python src/tic_codec.py codificar ... --reporte` sobre el caso `--perdida 3 -k 8` ya documentado — verificar numéricamente que `I_XY <= H` (nunca puede ser mayor); confirmar que los 7 casos lossless siguen dando SHA-256 idéntico (ninguna regresión en la verificación de integridad).
**Rollback:** revertir el campo `informacion_mutua`/`I_XY` en `MetricasDespues` y el método `informacion_mutua`; los 7 JSON de `examples/` vuelven a su versión anterior con `git checkout`.

### Phase 2: Componente de IA real para selección de modo/k

**Goal:** Reemplazar (o complementar) la regla fija de comparación de tamaños Huffman-vs-bitstrip con un modelo entrenado real que recomiende k y modo, cubriendo el punto "use IA en algún punto del proceso" del enunciado con algo más defendible que una comparación de tamaños.

**Why this approach:** `GeneradorFuentes` ya sabe producir fuentes sintéticas uniformes/no-uniformes/estructuradas bajo demanda (ver Code Analysis del handoff) — es suficiente para generar un dataset de entrenamiento pequeño sin depender de datos externos ni de anotación manual. Un árbol de decisión pequeño es defendible académicamente como "IA" y mantiene la filosofía del proyecto de ser interpretable (nada de cajas negras que no se puedan explicar en la entrega).

- Generar ~30-50 fuentes sintéticas con `GeneradorFuentes` (mezcla de `uniforme`/`no_uniforme`/`estructurado`, variando tamaño y nivel de redundancia).
- Para cada una, correr `CodecTIC.barrido()` sobre la grilla estándar de k, y registrar como features un pre-escaneo barato a k=8 (H, H/k, tamaño del archivo) y como etiqueta el k/modo que realmente ganó por tamaño final real (no estimado).
- Entrenar un `sklearn.tree.DecisionTreeClassifier` pequeño (`max_depth=3` o `4`, explícitamente poco profundo para que sea interpretable e imprimible en el reporte) que prediga el k/modo recomendado a partir de las features del pre-escaneo barato.
- Agregar un nuevo flag CLI `--recomendar`: corre el pre-escaneo barato, imprime la recomendación del modelo, y (opcionalmente) la compara contra el resultado real de `barrido()` si también se pidió.
- Persistir el árbol entrenado como JSON de umbrales simple en `src/modelo_recomendacion.json` (evitar dependencia de pickle/versión de sklearn en tiempo de inferencia — reimplementar la evaluación del árbol como una función pequeña que lea esos umbrales, consistente con el estilo "sin dependencias más allá de NumPy" que ya tiene el proyecto).
- Documentar en el README, en una subsección nueva bajo "Qué hay implementado", el alcance honesto: entrenado sobre ~30-50 fuentes sintéticas generadas localmente, no un corpus grande ni datos de producción — mismo patrón de honestidad ya usado para la reducción del video.

**Files:** `src/tic_codec.py` (nueva clase, p. ej. `RecomendadorModo`, nuevo flag `--recomendar` en `main()`); nuevo `src/modelo_recomendacion.json`; `README.md` (nueva subsección + fila en la tabla de requisitos).
**Validates with:** correr `--recomendar` sobre los 7 ejemplos reales curados y reportar honestamente si la recomendación coincidió con el k/modo óptimo real encontrado por `barrido()` (no se espera 100% — documentar la tasa de acierto tal cual salga, sin inflarla).
**Rollback:** eliminar el flag `--recomendar`, la clase nueva y `src/modelo_recomendacion.json`; los comandos `codificar`/`decodificar`/`barrido` existentes no se tocan, por lo que no hay riesgo de regresión en ellos.

### Phase 3: Interpretación explícita en contexto 5G/6G

**Goal:** Agregar la sección interpretativa que conecta los números ya medidos (k, razón, ahorro, tiempos) con el trade-off de latencia vs. ancho de banda relevante en redes 5G/6G, cerrando el último punto puramente documental del enunciado.

**Why this approach:** Es documentación pura sobre datos que ya existen — no requiere tocar el código, es la fase de menor riesgo, y puede hacerse en paralelo con las Fases 1 y 2.

- Agregar sección "Contexto 5G/6G" al README, después de "Comparación entre las cinco fuentes probadas".
- Para cada fuente de la tabla comparativa, caracterizar el k elegido como favorable a baja latencia (k pequeño, 8-16, casi sin ahorro pero procesamiento mínimo — el caso de los formatos ya comprimidos) o favorable a ahorro de ancho de banda (k grande, hasta 512, gran compresión pero más cómputo por símbolo — el caso del video RGB crudo).
- Usar los tiempos de pared reales capturados en esta sesión (2m21,711s para el barrido k=8..256 del video, 0m44,169s para k=512..4096 — ver Evidence & Data del handoff) como evidencia concreta de que k grande cuesta más tiempo de codificación, no solo en teoría.
- Conectar explícitamente con casos de uso de red: k pequeño/latencia baja se relaciona con **URLLC** (comunicación ultra-confiable de baja latencia); k grande/mayor compresión se relaciona con **eMBB** (banda ancha móvil mejorada, transferencias masivas donde la latencia de codificación importa menos que el ahorro de espectro).

**Files:** `README.md` únicamente.
**Validates with:** revisión de coherencia manual — que la prosa nueva no contradiga ningún número ya presente en la tabla comparativa ni en los tiempos de barrido citados.
**Rollback:** revertir la sección "Contexto 5G/6G" del README; no afecta ningún otro archivo.

## Dependencies & Order

- Las 3 fases son independientes entre sí — ninguna depende del código que produce otra. Pueden ejecutarse en paralelo en worktrees separados si se usa el Agent tool.
- Dentro de la Fase 2, el pre-escaneo barato y el entrenamiento del árbol deben completarse antes de escribir el flag `--recomendar` (el flag consume el modelo ya entrenado).
- La Fase 3 no tiene ninguna dependencia de código — puede escribirse primero si se quiere una victoria rápida antes de las fases con código.

## Risks & Mitigations

- **Riesgo:** $I(X;Y) = H$ en los 7 casos lossless puede parecer un error de cálculo al profesor. **Mitigación:** documentar explícitamente en el reporte impreso y el README que esto es matemáticamente correcto cuando $Y=X$ exactamente (verificado por SHA-256), no un bug.
- **Riesgo:** el árbol de decisión de la Fase 2, entrenado solo con datos sintéticos, puede no generalizar bien y el profesor puede considerarlo un "IA" demasiado simple. **Mitigación:** declarar el alcance honestamente (mismo patrón que la reducción del video), y enmarcarlo como prueba de concepto de usar ML para guiar la elección de parámetros de codificación, no como un sistema de producción.
- **Riesgo:** cualquier interpretación de las 3 fases puede contradecir las páginas 2-7 del enunciado, que siguen sin conseguirse. **Mitigación:** mantener todas las interpretaciones claramente marcadas como basadas solo en la página 1/7, siguiendo el patrón ya establecido en "⚠️ Estado del enunciado" del README.
- **Riesgo:** regenerar los 7 JSON de `examples/` en la Fase 1 podría introducir un cambio no intencional en otro campo si el código de reporte tiene algún efecto secundario no detectado. **Mitigación:** revisar el diff de cada JSON regenerado antes de comitear — solo debe cambiar el campo nuevo `I_XY`, nada más.

## Success Criteria

- El campo `I_XY` (información mutua) aparece en los 7 JSON de `examples/` y en al menos un caso con pérdida real (`--perdida 3`, k=8) con un valor estrictamente menor a $H$, documentado en el README.
- El flag `--recomendar` existe, funciona sobre los 7 ejemplos reales, y su tasa de acierto contra el óptimo real está documentada en el README sin inflar el resultado.
- El README tiene una sección "Contexto 5G/6G" que cita al menos los tiempos de barrido reales (2m21,711s / 0m44,169s) y la tabla comparativa de 7 fuentes ya existente.
- Las 7 verificaciones SHA-256 existentes siguen pasando sin cambios — ninguna fase debe introducir una regresión en la integridad del códec.
- El checklist "Próximos pasos" del README pasa de 4 ítems pendientes (I(X;Y), IA, 5G/6G, confirmar con el profesor) a 1 solo ítem pendiente real (confirmar con el profesor / conseguir páginas 2-7, que no es accionable por código).

## Quick Start

```bash
# Restore full context
cat "D:\Proyectos\UD.Lab3.TeoriaInformacion\plans\handoffs\HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-26.md"

# Key source files for Phase 1
D:\Proyectos\UD.Lab3.TeoriaInformacion\src\tic_codec.py       # clases Informacion, MetricasDespues
D:\Proyectos\UD.Lab3.TeoriaInformacion\README.md              # tabla "Resultados experimentales de referencia"
D:\Proyectos\UD.Lab3.TeoriaInformacion\examples\*\*.json      # 7 reportes a regenerar

# Baseline data to reference
D:\Proyectos\UD.Lab3.TeoriaInformacion\examples\video_rgb\*.json   # el caso con mayor razón de compresión (43,565)

# Verify starting state
cd "D:\Proyectos\UD.Lab3.TeoriaInformacion" && git status && git log --oneline -3
python src/tic_codec.py --help

# First concrete action
Abrir src/tic_codec.py, ubicar la clase `Informacion`, y agregar el staticmethod
`informacion_mutua(conjunta)` siguiendo el mismo patrón vectorizado de `entropia()`.
```
