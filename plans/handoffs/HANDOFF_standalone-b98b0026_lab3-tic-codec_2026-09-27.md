# Lab 3 Teoría de la Información — I(X;Y) implementado, 3 diagramas Archify completos; IA y 5G/6G en pausa por decisión del usuario

**Date:** 2026-09-27
**Status:** IN PROGRESS
**Bead(s):** none
**Epic:** none
**Chain:** `standalone-b98b0026` seq `2`
**Parent:** `HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-26.md` (eliminado en este mismo commit, a pedido explícito del usuario — la referencia queda solo como lineage histórico; el contenido relevante que seguía vigente ya está incorporado abajo)
**Prior chain:** `HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-26.md` > this

---

## Since Last Handoff

El handoff anterior (seq 1) dejaba planteado un plan de 3 fases (`PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-26.md`, también eliminado en este commit): Fase 1 ($I(X;Y)$), Fase 2 (componente de IA real), Fase 3 (interpretación 5G/6G). Desde entonces:

- **Fase 1: completada y pusheada** (commit `cf1229f`). Se implementó exactamente como estaba diseñada: `Informacion.informacion_mutua()` vectorizado, campo `I_XY` en todos los reportes JSON, ejemplo real no trivial con `--perdida 3` sobre la imagen BMP cruda. Verificado sin regresión en las 7 corridas existentes.
- **El usuario decidió detenerse ahí explícitamente**, en vez de continuar directo a la Fase 2: quiere estudiar todo el proyecto por su cuenta primero y definir él mismo el enfoque del componente de IA antes de que se implemente nada. La Fase 3 (5G/6G) quedó pospuesta sin fecha ("olvídalo por el momento"). El plan seq-1 se actualizó in-place (commit `4817c81`) marcando esto, pero ese archivo ya no existe tras este handoff — el estado queda documentado aquí en su lugar.
- **Trabajo nuevo no anticipado por el plan seq-1:** el usuario pidió un tercer diagrama Archify (no estaba en el plan de 3 fases, es un pedido de documentación aparte) — un mapa conceptual "de la matemática teórica a conceptos sencillos", conectando cada concepto de teoría de la información con su fórmula, su intuición y la clase del código que lo implementa. Se construyó, validó y entregó (`tic_codec.teoria.json`/`.html`, commit `41d7aa1`).
- **Trayectoria:** el proyecto está en un punto de "pausa deliberada" — todo lo medible/documentable sin decisiones de diseño pendientes está hecho (I(X;Y), los 3 diagramas). Lo que falta (componente de IA, 5G/6G) depende de que el usuario vuelva con una dirección definida, no de investigación técnica adicional de este lado.

## Reference Documents

- `docs/Codec_adaptable_documentacion_tecnica.pdf`, `docs/Codec_adaptable_para_principiantes.pdf` — documentación técnica original del códec (leída en sesiones previas).
- `diagrams/tic_codec.architecture.html` — arquitectura de las 14 clases de `tic_codec.py`.
- `diagrams/tic_codec.dataflow.html` — pipeline antes/durante/después como flujo de datos.
- `diagrams/tic_codec.teoria.html` — **nuevo esta sesión**: mapa conceptual teoría↔código↔fórmula.
- README.md del repo — única fuente de verdad del alcance, supuestos y checklist del proyecto.
- Repo remoto: `https://github.com/J4F3ET/UD.Lab3.TeoriaInformacion` (privado), rama `main` únicamente, sin otras ramas locales ni remotas a la fecha de este handoff.

## The Goal

Cumplir el Lab 3 de Teoría de la Información (Ingeniería en Telemática, Universidad Distrital): sistema adaptable de codificación/decodificación/compresión para N ∈ {8,...,2048} bits/símbolo sobre audio/video/texto/imagen, comparando codificación uniforme vs. no uniforme, usando IA en algún punto, eliminando redundancia de forma controlada, midiendo H, I, I(X;Y) y KL, y contextualizando en 5G/6G — todo con solo la página 1/7 del enunciado disponible, así que cada supuesto se declara explícitamente en el README en vez de asumirse en silencio. El usuario (jafetdc16@gmail.com) exige que el código viva únicamente en `D:\Proyectos\UD.Lab3.TeoriaInformacion` (repo Git separado), nunca dentro de su vault de Obsidian.

De los 7 requisitos del enunciado, a la fecha de este handoff quedan cubiertos: volumen grande, k adaptable, las 4 fuentes, uniforme/no-uniforme, redundancia controlada, y **medir H, I, I(X;Y), KL** (recién cerrado esta sesión). Quedan sin cubrir: **usar IA** (regla fija, no modelo — en pausa deliberada) y **contexto 5G/6G** (no iniciado — en pausa deliberada).

### Texto exacto del enunciado confirmado (README, página 1/7 — única fuente del alcance real, cítese literal)

```
Diseñar un sistema adaptable para N ∈ {8, 16, 32, 64, 128, 256, 512, 1024, 2048} bits/símbolo que:
- Codifique y decodifique, comprima y descomprima fuentes de gran volumen: audio (1-2 min),
  video (5 min), texto, imagen (varias distintas).
- Muestre las 4 secuencias del proceso (codificada, comprimida, descomprimida, decodificada).
- Compare codificación uniforme vs. no uniforme, buscando eficiencia y confiabilidad.
- Use IA en algún punto del proceso.
- Identifique y elimine redundancia de forma controlada, y reconstruya la información
  verificando el resultado.
- Mida cantidad de información I, entropía H, información mutua I(X;Y) y divergencia KL,
  interpretando los resultados.
- Contextualice todo en redes 5G/6G.
```

### Supuestos declarados exactos (README, sección "Supuestos declarados" — vigentes sin cambios desde el handoff seq-1)

```
- "N bits/símbolo" se interpreta como la profundidad de codificación por símbolo de la fuente
  (cuántos bits representan cada símbolo antes de comprimir), igual que en el ejercicio de
  cuantificación PCM visto en clase.
- "IA en el proceso" se interpreta como un componente que ayuda a decidir la codificación
  (ej. recomendar k o el tipo de codificación), no como un modelo generativo que reemplace
  la codificación.
- "Confiable" se interpreta como reconstrucción verificable con una métrica objetiva:
  bit-exacta (SHA-256) sin pérdida, o error medible (MSE/PSNR) con pérdida.
```

## Where We Are

- `src/tic_codec.py` (908 líneas tras esta sesión, antes 877): además de las 14 clases documentadas en el handoff anterior, `Informacion` ahora tiene un método adicional `informacion_mutua(indices_x, indices_y)` — staticmethod vectorizado que calcula $I(X;Y)$ desde una distribución conjunta de símbolos emparejados.
- `MetricasDespues` (dataclass) tiene un campo nuevo `informacion_mutua_XY: float`, insertado entre `KL_flujo_vs_uniforme_256` y `verificacion_sha256` (antes de los campos opcionales con default, por la regla de dataclasses de Python de que los campos sin default van primero). Se serializa a la clave JSON `"I_XY"`.
- `ReporteCodificacion.imprimir()` agrega una nota condicional de dos líneas cuando `sin_perdida_exacta` es verdadero, explicando por qué `I_XY == H` no es un bug.
- Los 7 ejemplos curados en `examples/` (imagen_jpeg, imagen_bmp, texto, audio_mp3, audio_wav, video_mp4, video_rgb) fueron **regenerados** con el campo `I_XY` nuevo — confirmado por diff que ningún otro valor cambió salvo los tiempos de ejecución no determinísticos.
- **Nuevo ejemplo curado:** `examples/imagen_bmp_perdida3/imagen_bmp_perdida3.json` + `.png` — primera corrida real con `--perdida 3` sobre datos reales (la imagen BMP cruda), con $I(X;Y)$ no trivial: $H=7,611$, $I(X;Y)=4,621$ bits/símbolo, razón 1,7195:1, ahorro 41,84%, PSNR 35,67 dB.
- README.md actualizado: fila de requisitos menciona $I(X;Y)$ explícitamente, sección "Resultados experimentales de referencia" tiene el nuevo ejemplo real con nota aclaratoria de por qué el número sintético anterior (razón 3,44:1) no se pudo reproducir exactamente (no se tenía registrado el archivo de origen de esa corrida, de antes de esta sesión), checklist "Próximos pasos" con el ítem de $I(X;Y)$ marcado `[x]`, y tabla de clases POO menciona que `Informacion` ahora también calcula $I(X;Y)$.
- **Tercer diagrama Archify completo:** `diagrams/tic_codec.teoria.json`/`.html` — 11 nodos (`fuente_real`, `entropia`, `perfil_bits`, `redundancia`, `autoinformacion`, `kl_uniforme`, `huffman`, `seleccion_modo`, `confiabilidad`, `info_mutua`, `veredicto`), 3 boundaries (ANTES/DURANTE/DESPUÉS, mismo lenguaje que el diagrama de dataflow), 10 conexiones (2 se dejaron sin label explícito porque su fórmula ya está en las cards y la geometría no daba espacio limpio para el texto), 3 cards con las fórmulas completas de H/I(x)/R/KL/I(X;Y) y notas de "cómo se implementa". Pasa `validate --quality showcase` (9/9, 0 errores) y `visual-check` en 1440×900/1600×1000/1920×1080/2048×1320 × claro/oscuro.
- El repo tiene ahora 13 commits en `main`, working tree limpio, sincronizado con `origin/main`.
- `bd` (beads) sigue sin estar disponible en este entorno.
- `plans/handoffs/` contenía `HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-26.md` y `PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-26.md` — **ambos eliminados en el commit de este handoff**, a pedido explícito del usuario ("elimina los anteriores handoffs y plan y crea uno con las actualizaciones"); este archivo y su PLAN hermano (seq 2) los reemplazan por completo.

## What We Tried (Chronological)

1. **Diseño de `Informacion.informacion_mutua()`:** se evaluaron dos formas de calcular $I(X;Y)$. La opción descartada fue construir siempre el histograma conjunto completo (X original vs. Y reconstruido) para los millones de símbolos de cada corrida — se decidió NO hacerlo en el caso sin pérdida porque ahí $Y=X$ exactamente (verificado por SHA-256) y $I(X;Y)=H(X)$ es una identidad matemática, no algo que valga la pena recalcular con un histograma conjunto costoso. Implementación final: rama `if perdida: ... else: info_mutua_XY = Informacion.entropia(alfabeto_orig.frecuencias)`.
2. **Construcción del histograma conjunto (caso con pérdida):** usa la misma técnica de "clave combinada" que el resto del código (similar a `Alfabeto.desde_filas`, que usa vistas de NumPy para hashear filas): `clave = x * Uy + y`, luego `np.unique(clave, return_counts=True)` da la distribución conjunta, y `np.bincount` da las marginales — todo vectorizado, cero loops por símbolo, consistente con la restricción de rendimiento ya establecida en el proyecto.
3. **Regresión de los 7 ejemplos:** se regeneraron todos corriendo `codificar` de nuevo con los mismos `k` que el README ya documentaba (verificado leyendo `antes.k_bits` de cada JSON antes de tocar nada). Se revisó el diff de cada uno con `git diff examples/` explícitamente — confirmado que solo cambiaron `I_XY` y los dos campos de tiempo.
4. **Búsqueda del ejemplo "no trivial" de $I(X;Y)$:** el README ya tenía una frase histórica ("con `--perdida 3` y k=8: razón 3,44:1, PSNR 38,4 dB") de una sesión anterior a este cambio. Se intentó reproducirla generando una fuente sintética estructurada de 2 MB con semilla por defecto (`GeneradorFuentes.estructurado`, semilla=0) — dio razón 1,5997, PSNR no calculado en ese intento pero claramente distinto. **No se pudo reproducir el número original** porque no había registro de qué archivo exacto se usó en esa corrida histórica. Decisión: no fabricar ni forzar ese número — se corrió `--perdida 3 -k 8` sobre datos reales (`data/imagen_prueba.bmp`, la misma imagen ya usada en los ejemplos comprimidos) y se documentó el resultado real y reproducible (razón 1,7195:1, PSNR 35,67 dB), dejando explícita en el README la razón de por qué el número viejo no se repite.
5. **Diseño del tercer diagrama (teoría):** se decidió el tipo `architecture` (no `dataflow` ni ningún otro) para modelar conceptos teóricos como si fueran "componentes", con boundaries ANTES/DURANTE/DESPUÉS — reutilizando el mismo lenguaje temporal que ya usa el dataflow diagram y el propio código, para que los tres diagramas del repo cuenten la misma historia desde tres ángulos (clases, datos, teoría).
6. **Primera pasada de validación del diagrama de teoría:** errores de ancho de label (`"I(x) — Autoinformación"` ~145px vs. 120px del nodo) y de solapamiento — igual que en los dos diagramas anteriores, la primera pasada de un diagrama nuevo casi siempre falla por overlaps de labels con nodos vecinos cuando hay abanicos de 3+ conexiones desde un mismo nodo.
7. **Problema estructural del abanico de `entropia`:** `entropia` tenía 3 conexiones salientes (a `redundancia`, `autoinformacion`, `kl_uniforme`) en la misma columna de destino pero filas distintas. La conexión a `redundancia` (fila 0) generaba una ruta en L (horizontal luego vertical) cuyo segmento vertical coincidía en x con la posición por defecto del label de `entropia→autoinformacion` (fila 1, misma fila que `entropia`) — un error `composition/label-route-clearance` de "0px de separación" que sobrevivió varios intentos de `labelDy`. Se resolvió **eliminando las etiquetas de texto de `entropia→redundancia` y `entropia→kl_uniforme`** (sus fórmulas $R=1-H/k$ y $KL=\log_2(U)-H$ ya estaban completas en la Card 1), dejando solo `entropia→autoinformacion` etiquetada con `labelAt` explícito — mismo principio de "quitar la etiqueta de bajo valor antes de seguir peleando con la geometría" que ya se había usado en el diagrama de arquitectura de la sesión anterior.
8. **Overflow vertical en `visual-check`:** el primer `deliver` pasó `validate` limpio pero `visual-check` reportó overflow en las 4 resoluciones (scrollHeight hasta 1449 vs. 1320 disponibles en el peor caso). Se redujo `layout.cellH` de 125→100→88→82 y `gapY` de 18→12→8→4 en 4 iteraciones, revalidando geometría (labels que ya estaban bien posicionados se rompían con cada reducción y había que reajustar sus `labelAt`) hasta que las 4 resoluciones × 2 temas pasaron `visual-check` limpio.
9. **Inspección visual manual post-checks-automáticos:** exactamente como pasó con el primer diagrama de esta serie, los checks automáticos pasaron pero la inspección visual de la captura reveló un defecto real: la etiqueta "bits variables a codificar" (de `redundancia→huffman`, con `labelDy: 54` heredado de una geometría más holgada) quedaba visualmente pegada/mezclada con "tamaño Huffman vs. bitstrip" (de `huffman→seleccion_modo`) — ambas leían casi como un solo texto ilegible ("bits v[...]tamaño Huffman vs. bitstrip"), aunque el validador automático las consideraba técnicamente separadas. Se investigaron las coordenadas reales de las cajas vecinas (`redundancia` y `huffman`, 30px de separación entre ellas) y se determinó que **no había espacio vertical limpio** para esa etiqueta en la geometría comprimida final (arriba chocaba con el título del boundary DURANTE, abajo con la otra etiqueta) — se eliminó la etiqueta de `redundancia→huffman` por completo (la relación ya es evidente por la flecha y por la Card 2), y se re-verificó con una nueva captura que el texto quedara limpio.

## Key Decisions

- **$I(X;Y)$ se reporta siempre, no solo con `--perdida`:** en vez de dejar el campo como `null` en el caso sin pérdida (como se hace con `MSE_por_byte`/`PSNR_dB`, que sí son `None` sin pérdida), se decidió calcular y mostrar $I(X;Y)=H$ explícitamente siempre, con una nota aclaratoria impresa, porque el enunciado pide medir $I(X;Y)$ como requisito y dejarlo en `null` habría parecido que el requisito no se cumple en el caso más común (todas las 7 corridas curadas son sin pérdida).
- **No fabricar el número histórico de `--perdida 3` (razón 3,44:1, PSNR 38,4 dB):** al no poder reproducirlo exactamente, se optó por generar y documentar un ejemplo nuevo, real y reproducible, en vez de inventar un $I(X;Y)$ para el número viejo o forzar parámetros hasta que coincidiera — consistente con el patrón ya establecido en el proyecto de preferir datos reales verificables sobre resultados convenientes.
- **Tipo `architecture` (no `dataflow`) para el diagrama de teoría:** aunque el pedido del usuario ("de la matemática teórica a conceptos sencillos... cómo se relacionan") tiene forma de pipeline/lineage (que sugeriría `dataflow`), se prefirió `architecture` porque permite boundaries + cards + conexiones con fórmulas como texto largo, y porque ya se tenía experiencia reciente y probada resolviendo sus patrones de fallo (a diferencia de forzar 3-4 etapas por concepto en `dataflow`, que con 8+ conceptos hubiera excedido ampliamente el límite recomendado de ~12 nodos primarios).
- **Eliminar 3 etiquetas de conexión en vez de seguir ajustando geometría:** (`entropia→redundancia`, `entropia→kl_uniforme`, `redundancia→huffman`) — las tres fórmulas/relaciones afectadas ya estaban documentadas en las cards, así que quitar el texto de la conexión no pierde información, solo reduce ruido visual y evita pelear indefinidamente contra restricciones de espacio genuinas.
- **Usuario decide pausar el plan de 3 fases después de solo la Fase 1:** decisión explícita y deliberada, no un olvido — quiere estudiar el proyecto y definir el enfoque de IA él mismo antes de que se le implemente nada. Esto invalida parcialmente el diseño de la Fase 2 documentado en el plan seq-1 (árbol de decisión sobre fuentes sintéticas) — **no debe asumirse que ese diseño sigue vigente** cuando el usuario retome el tema.
- **Eliminar los archivos de handoff/plan seq-1 en vez de archivarlos:** a diferencia de la guía por defecto del skill (`archive/`, no borrar), el usuario pidió explícitamente eliminarlos ("elimina los anteriores"). Se seguirá esa instrucción explícita en vez del comportamiento por defecto de archivado, ya que este handoff (seq 2) incorpora todo el contenido que seguía siendo relevante del seq-1.

## Evidence & Data

### Commits de esta sesión (4 nuevos, de un total de 13 en el repo)

| Hash | Mensaje |
|---|---|
| `cf1229f` | Agrega información mutua I(X;Y) explícita entre fuente y reconstrucción |
| `4817c81` | Marca la Fase 1 del plan como completada y pausa las Fases 2-3 |
| `41d7aa1` | Agrega diagrama Archify de teoría: de la fórmula a la práctica |

(El commit `056487a`, con el handoff/plan seq-1 originales, queda en el historial de git aunque los archivos se eliminen del working tree en el commit de este handoff — recuperable con `git show 056487a` si hiciera falta releer el seq-1 completo.)

### Verificación numérica de $I(X;Y)$ (ejecutada explícitamente esta sesión, no solo teórica)

| Caso | H(X) | I(X;Y) | Relación verificada |
|---|---:|---:|---|
| Sin pérdida (fuente sintética estructurada, k=8) | 7,951076649585469 | 7,951076649585469 | Igualdad exacta (`==` en Python, no solo aproximada) |
| Con `--perdida 3`, k=8 (misma fuente sintética) | 7,951076649585469 | 4,994187582178796 | $I(X;Y) < H$ estrictamente |
| Con `--perdida 3`, k=8, `data/imagen_prueba.bmp` (real, curado) | 7,610515215630953 | 4,620882497866045 | $I(X;Y) < H$ estrictamente; razón 1,7195, PSNR 35,67 dB |

### $I(X;Y)$ final de las 8 corridas curadas en `examples/` (valor exacto de cada JSON, no redondeado a mano)

| Fuente | H (bits/símb.) | I(X;Y) | Razón | ¿I(X;Y)=H? |
|---|---:|---:|---:|---|
| Imagen JPEG | 7,9479 | 7,9479 | 1,0022 | Sí (sin pérdida) |
| Imagen BMP | 15,5333 | 15,5333 | 1,7135 | Sí (sin pérdida) |
| Texto | 10,4417 | 10,4417 | 1,4278 | Sí (sin pérdida) |
| Audio MP3 | 7,9644 | 7,9644 | 1,0017 | Sí (sin pérdida) |
| Audio WAV | 13,6279 | 13,6279 | 1,1356 | Sí (sin pérdida) |
| Video MP4 | 7,8261 | 7,8261 | 1,0184 | Sí (sin pérdida) |
| Video RGB | 8,1192 | 8,1192 | 43,5650 | Sí (sin pérdida) |
| **Imagen BMP, `--perdida 3`** | **7,6105** | **4,6209** | **1,7195** | **No — único caso con pérdida real** |

Nótese que la razón de compresión de "Imagen BMP" sin pérdida (1,7135) y con `--perdida 3` (1,7195) son casi idénticas — la pérdida controlada de 3 bits por byte casi no mejora la razón en este caso porque el modo elegido ya era `huffman` en ambos, y el ahorro real vino de la reducción de $H$ (15,53→7,61) más que de la compresión adicional; el punto pedagógico no es "más pérdida = mucha mejor razón" sino que $I(X;Y)$ cae proporcionalmente a cuánta información real se descartó.

### Diff de los 7 JSON regenerados (patrón idéntico en los 7 archivos, confirmado con `git diff`)

```diff
     "H_flujo_codificado_bits_por_byte": 7.995014924987819,
     "KL_flujo_vs_uniforme_256": 0.004985075012180928,
+    "I_XY": 7.947935160012834,
     "verificacion_sha256": true,
     "sin_perdida_exacta": true,
-    "tiempo_codificacion_s": 2.755091905593872,
-    "tiempo_decodificacion_s": 2.523913621902466,
+    "tiempo_codificacion_s": 3.271451473236084,
+    "tiempo_decodificacion_s": 3.2444095611572266,
     "KL_original_vs_reconstruido": 0.0
```

### Iteraciones de validación del diagrama de teoría (esta sesión, hasta 0 errores + visual-check limpio)

| Ronda | Problema | Fix |
|---|---|---|
| 1 | Label "I(x) — Autoinformación" ~145px > 120px del nodo; varios labels solapando nodos vecinos | Acortar a "I(x) — Autoinfo"; `labelDy` en 6 conexiones |
| 2 | `entropia→autoinfo` label choca con el segmento vertical de `entropia→redundancia` (corredor compartido, error de 0px) | Intentos con `labelDy`/`labelDx` variados; boundary title rail empieza a chocar con labels empujados hacia arriba |
| 3 | Persistían los mismos choques tras varios ajustes de `labelDy`/`labelAt` | **Fix estructural**: eliminar labels de `entropia→redundancia` y `entropia→kl_uniforme` (fórmulas ya en Card 1); solo `entropia→autoinfo` queda etiquetada, con `labelAt` explícito |
| 4 | `deliver` y `validate` limpios, pero `visual-check` reporta overflow vertical en las 4 resoluciones (scrollHeight hasta 1449) | Reducir `cellH` 125→100→88→82 y `gapY` 18→12→8→4 en pasos, re-fijando `labelAt` de `entropia→autoinfo` y `huffman→seleccion_modo` en cada paso |
| 5 | `visual-check` limpio (0 errores, 4 resoluciones × 2 temas) | — |
| 6 | Inspección visual manual: "bits variables a codificar" y "tamaño Huffman vs. bitstrip" se leen como un solo texto ilegible pese a 0 errores automáticos | Eliminar el label de `redundancia→huffman` por completo (espacio vertical genuinamente insuficiente en la geometría final) |
| 7 | Nueva captura confirma ambas etiquetas legibles y separadas | Diagrama final, entregado |

### Recibo de entrega final (`deliver`) del diagrama de teoría

`specification.sha256` y `artifact.sha256` generados; `checksPassed: 9, checkCount: 9, compositionStatus: "pass", errors: 0, warnings: 0`. `visual-check`: `"ok": true, "status": "pass"` en 1440×900, 1600×1000, 1920×1080, 2048×1320, claro y oscuro.

### Inventario completo de los 11 nodos del diagrama de teoría (`diagrams/tic_codec.teoria.json`)

| id | Label | Sublabel (idea simple) | Boundary |
|---|---|---|---|
| `fuente_real` | Fuente real | imagen · audio · texto · video | (sin boundary, bookend) |
| `entropia` | H — Entropía | bits promedio por símbolo | ANTES |
| `autoinformacion` | I(x) — Autoinfo | sorpresa de un símbolo | ANTES |
| `redundancia` | R — Redundancia | bits de k que sobran | ANTES |
| `kl_uniforme` | KL(P‖U) | qué tan lejos de lo uniforme | ANTES |
| `perfil_bits` | Perfil de bits | posiciones que nunca cambian | ANTES |
| `huffman` | Huffman canónico | código corto para lo frecuente | DURANTE |
| `seleccion_modo` | Selección de modo | el resultado más chico gana | DURANTE |
| `confiabilidad` | Confiabilidad | SHA-256 exacto, o MSE/PSNR | DESPUÉS |
| `info_mutua` | I(X;Y) | info que sobrevive el viaje | DESPUÉS |
| `veredicto` | Veredicto | razón, ahorro, ¿uniforme? | (sin boundary, bookend) |

`confiabilidad` usa `type: "security"` (icono de candado) en vez de `"backend"` como el resto — única excepción deliberada, para que el ícono refuerce visualmente el concepto de verificación. `fuente_real` usa `type: "external"` y `veredicto` usa `type: "frontend"` — los mismos dos tipos "bookend" que ya usaban `cli`/`generador`/`reporte` en el diagrama de arquitectura, por consistencia visual entre los tres diagramas del repo.

Las 4 vistas guiadas (`meta.views`) del diagrama de teoría: `antes` (foco en fuente_real/entropia/redundancia/autoinformacion/kl_uniforme/perfil_bits — "todo lo que se calcula sobre la fuente cruda"), `durante` (perfil_bits/redundancia/huffman/seleccion_modo — "cómo se elimina redundancia de forma controlada, sin adivinar"), `despues` (seleccion_modo/confiabilidad/info_mutua/veredicto — "por qué 'confiable' aquí significa una prueba, no una promesa") y `principal` (entropia/redundancia/huffman/confiabilidad/info_mutua/veredicto — el camino completo de H al veredicto final).

### Las 10 conexiones finales (2 relaciones — `entropia→redundancia`, `entropia→kl_uniforme` — quedaron como flechas sin texto; sus fórmulas viven solo en la Card 1, ver "Key Decisions")

`fuente_real→entropia` ("símbolos de k bits"), `fuente_real→perfil_bits` ("mismos símbolos, por bit"), `entropia→redundancia` (sin label), `entropia→autoinformacion` ("H = promedio de I(x)"), `entropia→kl_uniforme` (sin label), `perfil_bits→seleccion_modo` ("bits fijos no se comparan"), `redundancia→huffman` (sin label, eliminado en la ronda 6 de validación), `huffman→seleccion_modo` ("tamaño Huffman vs. bitstrip"), `seleccion_modo→confiabilidad` ("decodifica y verifica"), `confiabilidad→info_mutua` ("exacta ⇒ I(X;Y)=H"), `info_mutua→veredicto` (sin label), `confiabilidad→veredicto` ("SHA-256 o PSNR").

### Texto completo de las 3 cards del diagrama de teoría

1. **Antes: la fórmula detrás de cada caja** (punto cyan) — "H = −Σ p(x)·log2 p(x); I(x) = −log2 p(x)" / "R = 1 − H/k; KL(P‖U) = log2(U) − H"
2. **Durante: compresión controlada, no a ciegas** (punto emerald) — "HuffmanCanonico: código corto para lo frecuente" / "CodecTIC compara tamaños reales y escribe el más chico"
3. **Después: la prueba, no la promesa** (punto violet) — "I(X;Y) = Σ p(x,y)·log2(p(x,y)/(p(x)·p(y)))" / "SHA-256 exacto, o MSE/PSNR si hay pérdida"

### Estadísticas exactas de los 3 commits de esta sesión

- `cf1229f`: 11 archivos, +476/−21 líneas (incluye el nuevo `examples/imagen_bmp_perdida3/` de 409 líneas de JSON + PNG).
- `4817c81`: 1 archivo (el PLAN seq-1, ahora eliminado), +6/−4 líneas.
- `41d7aa1`: 9 archivos, +15701/−1 líneas (el HTML autocontenido del diagrama pesa 15026 líneas por sí solo; el JSON fuente real son 93 líneas).

## Code Analysis

- `Informacion.informacion_mutua(indices_x, indices_y)` (nuevo, `src/tic_codec.py`): recibe dos arrays de índices de símbolo alineados fila a fila (típicamente `alfabeto_orig.indices` y `alfabeto_rec.indices`, ambos de `Alfabeto.desde_filas()`). Construye `clave = x*Uy + y`, usa `np.unique(clave, return_counts=True)` para la conjunta y `np.bincount` para las marginales, devuelve $\sum p(x,y)\log_2\frac{p(x,y)}{p(x)p(y)}$. Cero loops por símbolo — mismo patrón vectorizado que el resto de la clase.
- En `CodecTIC.codificar()`, el cálculo de `info_mutua_XY` ocurre **antes** de construir `MetricasDespues` (a diferencia del cálculo de `KL_original_vs_reconstruido`/`MSE_por_byte`, que sigue ocurriendo después, en el bloque `if perdida:` posterior) — esto obligó a mover `fuente_rec = Fuente.desde_bytes(rec, k)` y `alfabeto_rec = Alfabeto.desde_filas(...)` más arriba en la función y reutilizarlos después (antes se recalculaban dos veces).
- `MetricasDespues.a_dict()` mapea `informacion_mutua_XY` → clave JSON `"I_XY"`, insertada justo antes de `"verificacion_sha256"` en el orden de serialización (el orden de las claves en el JSON importa para la legibilidad del reporte, se mantuvo el mismo orden lógico que las demás métricas "durante/después").
- El diagrama de teoría usa `layout.mode: "grid"` con `cols: 6`, `cellW: 100`, `cellH: 82`, `gapX: 50`, `gapY: 4` — geometría final tras 4 rondas de reducción; notablemente más comprimida verticalmente que el diagrama de arquitectura original (`cellH: 125, gapY: 18`) porque tiene 4 filas de contenido (0-3) más 3 boundaries apiladas con sus title rails, sin margen para la altura por defecto.
- `ReporteCodificacion.imprimir()` sigue con la misma firma y el mismo bucle genérico sobre `self.despues.a_dict().items()` de antes — la nota de `I_XY = H` se agregó como un `if` condicional **después** de ese bucle, no dentro de él, precisamente para no tener que darle un caso especial al formateador genérico `f = lambda x: ...` que ya maneja bool/float/int/str.
- El comando exacto usado para intentar reproducir el número histórico fue `python src/tic_codec.py generar estructurado <tmp>.bin --mb 2` seguido de `codificar <tmp>.bin <tmp>.tic -k 8 --perdida 3` — ambos con los valores por defecto de `GeneradorFuentes.estructurado` (semilla 0), que es la única combinación de parámetros que el CLI permite sin especificar más flags; si la corrida histórica usó una semilla distinta o un tamaño distinto, no queda forma de saberlo por el CLI solo.

## Files Changed

### Código fuente
- `src/tic_codec.py` — método `Informacion.informacion_mutua()` nuevo; campo `informacion_mutua_XY` en `MetricasDespues` (dataclass + `a_dict()`); nota explicativa en `ReporteCodificacion.imprimir()`; reordenamiento menor en `CodecTIC.codificar()` para computar `info_mutua_XY` antes de construir el reporte y reutilizar `alfabeto_rec`.

### Datos y resultados
- `examples/audio_mp3/audio_mp3.json`, `examples/audio_wav/audio_wav.json`, `examples/imagen_bmp/imagen_prueba_bmp.json`, `examples/imagen_jpeg/imagen_prueba.json`, `examples/texto/texto_prueba.json`, `examples/video_mp4/video_mp4.json`, `examples/video_rgb/video_rgb.json` — regenerados, solo cambia `I_XY` y timings.
- `examples/imagen_bmp_perdida3/imagen_bmp_perdida3.json` + `.png` — **nuevo**, primer ejemplo curado con `--perdida` sobre datos reales.

### Documentación
- `README.md` — fila de requisitos, sección de resultados de referencia, checklist de próximos pasos, tabla de clases POO, sección "Diagramas" (ahora menciona los 3 diagramas).
- `diagrams/tic_codec.teoria.json` + `.html` + 4 capturas de `visual-check` (1440×900 y 2048×1320, claro y oscuro) + `tic_codec.teoria.visual-check.json`/`.html` de recibo — **nuevo**, tercer diagrama Archify. Mismo patrón de archivos que ya existía para `tic_codec.architecture.*` y `tic_codec.dataflow.*`, así que `diagrams/` ahora tiene 3 diagramas completos con la misma estructura de evidencia cada uno.

### Planeación (eliminados en este commit)
- `plans/handoffs/HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-26.md` — eliminado.
- `plans/handoffs/PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-26.md` — eliminado.
- Reemplazados por este archivo y su `PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-27.md` hermano.

### Sin cambios esta sesión (para que quede explícito qué NO se tocó)
- `data/` (los 7 archivos de prueba reales, gitignored) — sin cambios, se reutilizaron tal cual para regenerar los ejemplos.
- `diagrams/tic_codec.architecture.{json,html}` y `diagrams/tic_codec.dataflow.{json,html}` — sin cambios, siguen siendo los de la sesión anterior.
- `.gitignore` — sin cambios.
- La estructura de clases de `tic_codec.py` (las 14 clases del handoff seq-1) — sin cambios salvo la extensión de `Informacion` ya descrita; ninguna clase se eliminó ni se renombró.

## User Feedback & Preferences

- "empecemos con la fase 1" — aprobación explícita y acotada: solo Fase 1, no todo el plan de una vez.
- "luego comenzo a estudiar todo el proyecto y definir el tema de la ia con el componente o interpretaciones 5g y 6g olvidalo por el momento" — instrucción explícita de pausar, no de cancelar: el usuario planea volver a esto después de estudiar el proyecto por su cuenta, no lo está descartando. Señal clara de que **no hay que asumir ningún diseño de IA por él** en el futuro — debe ser él quien lo defina.
- "listo, ahora crea con archify la documentación para entender de la matemática teórica a conceptos sencillos cómo se relacionan y gracias a este proyecto cómo abarcamos estos temas en este proyecto y esta documentación en sí misma ya explicará el que hace y cómo hace las cosas el proyecto" — pedido explícito de un documento que sea simultáneamente: (a) puente teoría↔intuición, (b) mapa de relaciones entre conceptos, y (c) explicación de qué hace y cómo el proyecto — un solo artefacto con las tres funciones, no documentos separados.
- "/handoffplan elimina los anteriores handoffs y plan y crea uno con las actualizaciones" — instrucción explícita de reemplazar (borrar + recrear), no de archivar ni de mantener ambos. Señal general: este usuario prefiere que la carpeta `plans/handoffs/` refleje solo el estado vigente, no un historial acumulado de versiones.
- Patrón sostenido a través de toda la sesión (y heredado del handoff seq-1): preferencia fuerte por datos reales y reproducibles sobre números convenientes — se evidenció de nuevo cuando, al no poder reproducir el número histórico de `--perdida 3`, la respuesta fue generar un ejemplo nuevo real en vez de forzar el viejo.

## Where We're Going

1. **Nada de código está pendiente de forma activa.** El próximo paso funcional depende enteramente de que el usuario vuelva con una dirección definida para el componente de IA (Fase 2 del plan seq-1, ahora en pausa) — no iniciar esa fase sin que él la pida de nuevo explícitamente, y no asumir que el diseño anterior (árbol de decisión sobre fuentes sintéticas) sigue siendo lo que quiere.
2. Fase 3 (interpretación 5G/6G) sigue en el backlog, sin fecha, pospuesta junto con la Fase 2.
3. Ítems de backlog sin cambios desde el handoff anterior: confirmar con el profesor el significado de "N bits/símbolo" y el alcance de "IA"; conseguir las páginas 2-7 del enunciado.
4. Si el usuario pide "sigamos con el plan" sin más contexto, la acción correcta es preguntar primero qué definió al estudiar el proyecto, no retomar ciegamente el diseño de árbol de decisión del plan seq-1 (ver Key Decisions).
5. Si el usuario pide un cuarto diagrama Archify en el futuro, seguir el mismo patrón ya probado tres veces en este repo: escribir el `.json`, `validate --quality showcase` iterando hasta 0 errores, `deliver`, `visual-check` en las 4 resoluciones × 2 temas, y **siempre** inspeccionar la captura a mano al final — las tres veces que se hizo esto en este proyecto, la inspección manual encontró al menos un defecto real que los checks automáticos no habían señalado.

## Risks & Blockers

- El repo no tiene ningún archivo `CLAUDE.md` ni "BIBLE" de proyecto — toda convención de trabajo (dónde van los diagramas, cómo se nombran, el patrón commit→push por cada bloque de trabajo) vive solo en el historial de commits y en este handoff; una sesión que no lea este archivo completo no tiene otra forma de descubrir esas convenciones.

- Igual que en el handoff anterior: solo se tiene la página 1/7 del enunciado — cualquier trabajo futuro sobre IA o 5G/6G corre el riesgo de no alinear con el alcance real de las páginas faltantes.
- El número histórico "razón 3,44:1, PSNR 38,4 dB" mencionado en versiones anteriores del README ya no es reproducible (no se registró el archivo de origen) — si el profesor pregunta específicamente por ese número, la respuesta honesta es que corresponde a una corrida anterior no trazable, y que el README ahora documenta un ejemplo real y reproducible en su lugar.
- `bd` (beads) sigue sin estar disponible en este entorno — sin tracking de tareas fuera de este handoff/plan y el checklist del README.
- Los diagramas Archify (`.html`) son artefactos generados y comprometidos como binarios de texto grandes (el de teoría por sí solo son 15026 líneas) — si el `.json` fuente se vuelve a editar en el futuro, hay que volver a correr `validate`→`deliver`→`visual-check` completo; el `.html` no se edita nunca a mano.
- El repo no tiene ningún test automatizado (`pytest` u otro) — toda la verificación de regresión de esta sesión se hizo manualmente comparando JSON con `git diff` y corriendo el CLI a mano; si se retoma el proyecto en otra máquina, no hay un comando único de "correr todo y confirmar que nada se rompió".

## Open Questions

Nada de lo enunciado a continuación requiere más investigación de código — ambos puntos dependen de información externa (el profesor) o de una decisión del usuario todavía no tomada.

- Sin cambios respecto al handoff anterior: ¿qué significa exactamente "N bits/símbolo" para el profesor? ¿qué tan literal debe ser el "uso de IA"? — ambas requieren confirmación externa, no investigación de código.
- Nueva: cuando el usuario retome el tema de IA tras estudiar el proyecto, ¿seguirá queriendo un árbol de decisión entrenado sobre fuentes sintéticas (diseño del plan seq-1), o preferirá un enfoque distinto? — no asumir, preguntar.
- Nueva: ¿el usuario querrá un cuarto diagrama Archify en algún momento (por ejemplo, uno específico del futuro componente de IA una vez que exista), o los 3 actuales (arquitectura, dataflow, teoría) cubren toda la documentación visual que quiere para la entrega? — no se ha preguntado explícitamente.

## Cierre de esta sección de trabajo

Con el diagrama de teoría entregado, la sesión llega a un punto de cierre natural: no queda ningún ítem de código pendiente que no dependa de una decisión del usuario. El pedido de este mismo turno (`/handoffplan elimina los anteriores handoffs y plan y crea uno con las actualizaciones`) es exactamente la señal de que el usuario también considera este un buen punto de corte — de ahí que este handoff (seq 2) y su plan hermano reemplacen al par seq-1 en vez de simplemente añadirse a la carpeta.

## Quick Start for Next Session

```bash
# Restore full context
cat "D:\Proyectos\UD.Lab3.TeoriaInformacion\plans\handoffs\HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-27.md"
cat "D:\Proyectos\UD.Lab3.TeoriaInformacion\plans\handoffs\PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-27.md"

# Key files to read first
D:\Proyectos\UD.Lab3.TeoriaInformacion\README.md                      # estado completo, checklist "Próximos pasos"
D:\Proyectos\UD.Lab3.TeoriaInformacion\src\tic_codec.py                # códec completo, incluye informacion_mutua()
D:\Proyectos\UD.Lab3.TeoriaInformacion\diagrams\tic_codec.teoria.html  # mapa conceptual teoría↔código

# Evidence / data files
D:\Proyectos\UD.Lab3.TeoriaInformacion\examples\imagen_bmp_perdida3\imagen_bmp_perdida3.json  # ejemplo real con I(X;Y) no trivial

# Verify current state
cd "D:\Proyectos\UD.Lab3.TeoriaInformacion" && git status && git log --oneline -5

# Si hace falta re-validar/re-entregar un diagrama Archify existente (no crear uno nuevo)
cd "C:\Users\jafet\.claude\skills\archify"
node bin/archify.mjs validate architecture "D:\Proyectos\UD.Lab3.TeoriaInformacion\diagrams\tic_codec.teoria.json" --quality showcase --json
node bin/archify.mjs deliver architecture "D:\Proyectos\UD.Lab3.TeoriaInformacion\diagrams\tic_codec.teoria.json" "D:\Proyectos\UD.Lab3.TeoriaInformacion\diagrams\tic_codec.teoria.html" --quality showcase --json
node bin/archify.mjs visual-check "D:\Proyectos\UD.Lab3.TeoriaInformacion\diagrams\tic_codec.teoria.html" --json

# Next action
No hay acción de código pendiente. Esperar a que el usuario defina el enfoque de IA
(Fase 2) tras estudiar el proyecto, o confirme que retoma la interpretación 5G/6G (Fase 3).
```
