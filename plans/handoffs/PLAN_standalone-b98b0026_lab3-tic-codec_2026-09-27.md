# Componente de IA e interpretación 5G/6G del Lab 3 — ambas fases en pausa hasta que el usuario dé dirección

**Date:** 2026-09-27
**Status:** PLANNED — ambas fases bloqueadas/pausadas, ver nota abajo antes de tocar código
**Bead(s):** none
**Epic:** none
**Chain:** `standalone-b98b0026` seq `2`
**Context:** See `HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-27.md` for session data, test results, and prior approaches.

> **Este plan reemplaza a `PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-26.md`** (eliminado a pedido explícito del usuario). Su Fase 1 ($I(X;Y)$) ya se completó y no aparece aquí — ver el handoff para el detalle completo de esa implementación. Las Fases 2 y 3 de aquel plan se preservan abajo como Fases 1 y 2 de este, **pero con un cambio de estado importante**: el usuario pidió explícitamente pausar ambas después de completar $I(X;Y)$, para estudiar el proyecto por su cuenta y definir él mismo el enfoque de IA. **No iniciar ninguna de las dos fases sin confirmar primero con el usuario** — ver "Antes de empezar" más abajo.

---

## Antes de empezar (leer primero, es más importante que las fases)

La instrucción explícita más reciente del usuario sobre este trabajo fue: *"luego comenzo a estudiar todo el proyecto y definir el tema de la ia con el componente o interpretaciones 5g y 6g olvidalo por el momento"*. Esto significa:

1. **No asumir que el diseño de la Fase 1 de este plan (árbol de decisión sobre fuentes sintéticas) sigue siendo lo que el usuario quiere.** Es el diseño que se había planteado antes de que pidiera la pausa — puede que tras estudiar el proyecto prefiera otra cosa (una regla más simple, un modelo distinto, o algo que ni se ha considerado aquí).
2. **La primera acción de la próxima sesión sobre este tema no es escribir código — es preguntar** si el usuario ya definió su enfoque de IA, y si quiere retomar también la interpretación 5G/6G, o si sigue en pausa.
3. Si el usuario confirma que quiere seguir con el diseño tal como está documentado abajo, entonces sí se ejecuta directamente sin más preguntas — las fases están completamente detalladas para eso.

## Problem Statement

De los 7 requisitos del enunciado del Lab 3 (ver texto exacto en el handoff), 5 están cubiertos y verificados con datos reales, incluyendo la medición explícita de $I(X;Y)$ cerrada en la sesión anterior. Quedan dos sin cubrir: (1) "usar IA en algún punto del proceso" — hoy la selección de modo Huffman-vs-bitstrip es una comparación de tamaños de una línea, no un modelo; y (2) "contextualizar en redes 5G/6G" — no existe ninguna sección al respecto en el README. Ninguna de las dos tiene un bloqueo técnico: ambas se pausaron por decisión explícita del usuario, no porque falte información o porque algo no funcione.

## Key Findings

- $I(X;Y)$, el tercer punto de medición que pedía el enunciado, ya está cerrado (`Informacion.informacion_mutua()`, campo `I_XY` en todos los reportes) — ver Evidence & Data del handoff para los números exactos. → ya no es parte de este plan.
- El repo tiene ahora 3 diagramas Archify completos (arquitectura, dataflow, teoría) que documentan visualmente todo lo ya implementado — cualquier fase nueva de este plan debería considerar si necesita su propio diagrama o si puede documentarse solo en el README.
- `GeneradorFuentes` (uniforme/no_uniforme/estructurado) sigue siendo la única fuente de datos sintéticos disponible sin depender de archivos externos — sigue siendo la base más razonable para entrenar cualquier componente de IA, salvo que el usuario prefiera usar los 8 ejemplos reales curados en `examples/` como dataset (más realista pero mucho más pequeño).
- El patrón "declarar el alcance honestamente en vez de inflar resultados" se ha usado 3 veces en este proyecto (reducción del video, número de `--perdida 3` no reproducible, y se documentó explícitamente como principio) — cualquier componente de IA debe seguir el mismo patrón: si es un modelo de juguete entrenado con pocos datos sintéticos, decirlo así en el README.
- El usuario mencionó explícitamente que quiere "estudiar todo el proyecto" antes de decidir sobre IA — esto sugiere que la próxima interacción sobre este tema probablemente vendrá con preguntas específicas sobre el código existente, no directamente con "implementa la Fase 1".

## Anti-Goals (What NOT To Do)

- **No iniciar la Fase 1 (IA) ni la Fase 2 (5G/6G) sin preguntar primero** si el usuario ya definió su enfoque o sigue queriendo el diseño documentado aquí — ver "Antes de empezar".
- **No modelar símbolos individuales como objetos Python** en ningún código nuevo — restricción de rendimiento ya establecida en todo el proyecto (ver handoff, Key Decisions).
- **No crear ningún repositorio git dentro del vault de Obsidian del usuario**, bajo ninguna circunstancia — restricción explícita y no negociable.
- **No presentar el componente de IA como más sofisticado de lo que es** — si termina siendo un árbol de decisión pequeño entrenado sobre datos sintéticos, decirlo así, sin dar la impresión de que es un sistema robusto de producción.
- **No fabricar ni forzar números de referencia** si algo no es exactamente reproducible (ver el caso de `--perdida 3` en el handoff) — generar y documentar un caso real nuevo en vez de aproximar uno viejo.

## Plan

### Fase 1: Componente de IA real para selección de modo/k — ⏸ BLOQUEADA hasta confirmación del usuario

**Goal:** Reemplazar o complementar la regla fija de comparación de tamaños Huffman-vs-bitstrip con un modelo entrenado real que recomiende k y modo, cubriendo el punto "use IA en algún punto del proceso" del enunciado.

**Why this approach:** `GeneradorFuentes` ya genera fuentes sintéticas variadas bajo demanda, suficiente para un dataset de entrenamiento pequeño sin depender de datos externos ni anotación manual. Un árbol de decisión pequeño es defendible académicamente como "IA" y mantiene la filosofía interpretable del proyecto (nada de cajas negras que no se puedan explicar en la entrega). **Este diseño es el que se planteó antes de la pausa — confirmar con el usuario que sigue siendo lo que quiere antes de construir nada.**

- Generar ~30-50 fuentes sintéticas con `GeneradorFuentes` (mezcla de `uniforme`/`no_uniforme`/`estructurado`, variando tamaño y redundancia).
- Para cada una, correr `CodecTIC.barrido()` sobre la grilla estándar de k, registrando como features un pre-escaneo barato a k=8 (H, H/k, tamaño del archivo) y como etiqueta el k/modo que realmente ganó por tamaño final real.
- Entrenar un `sklearn.tree.DecisionTreeClassifier` pequeño (`max_depth=3-4`, deliberadamente poco profundo para ser interpretable) que prediga el k/modo recomendado desde las features del pre-escaneo.
- Agregar un flag CLI `--recomendar`: corre el pre-escaneo barato, imprime la recomendación del modelo, y opcionalmente la compara contra el resultado real de `barrido()`.
- Persistir el árbol como JSON de umbrales simple en `src/modelo_recomendacion.json` (sin depender de pickle/versión de sklearn en inferencia — reimplementar la evaluación del árbol como función pequeña que lea esos umbrales, consistente con "sin dependencias más allá de NumPy").
- Documentar en el README, en subsección nueva bajo "Qué hay implementado", el alcance honesto: entrenado sobre ~30-50 fuentes sintéticas locales, no un corpus de producción.
- Correr `--recomendar` sobre los 8 ejemplos reales curados (los 7 originales + `imagen_bmp_perdida3`) y documentar honestamente la tasa de acierto contra el óptimo real, sin inflarla.

**Files:** `src/tic_codec.py` (nueva clase `RecomendadorModo` o similar, nuevo flag `--recomendar`); nuevo `src/modelo_recomendacion.json`; `README.md` (nueva subsección + fila de requisitos).
**Validates with:** `--recomendar` sobre los 8 ejemplos curados; comparar contra el k/modo óptimo real ya documentado en cada JSON.
**Rollback:** eliminar el flag, la clase nueva y `src/modelo_recomendacion.json`; `codificar`/`decodificar`/`barrido` no se tocan, cero riesgo de regresión en ellos.

### Fase 2: Interpretación explícita en contexto 5G/6G — ⏸ PAUSADA a pedido explícito ("olvídalo por el momento"), sin bloqueo técnico

**Goal:** Agregar la sección interpretativa que conecta los números ya medidos (k, razón, ahorro, tiempos) con el trade-off latencia vs. ancho de banda en redes 5G/6G.

**Why this approach:** Es documentación pura sobre datos que ya existen — no toca código, es la fase de menor riesgo, independiente de la Fase 1.

- Agregar sección "Contexto 5G/6G" al README, después de "Comparación entre las cinco fuentes probadas" (ahora son 8 filas con el ejemplo de `--perdida 3` incluido, ver handoff).
- Caracterizar cada k elegido como favorable a baja latencia (k pequeño, formatos ya comprimidos) o a ahorro de ancho de banda (k grande, más cómputo, ej. video RGB crudo con k=512).
- Usar los tiempos de pared reales ya medidos (2m21,711s para k=8..256 del video, 0m44,169s para k=512..4096 — ver Evidence & Data del handoff) como evidencia concreta de que k grande cuesta más tiempo de codificación.
- Conectar con casos de uso de red: k pequeño/latencia baja → URLLC; k grande/mayor compresión → eMBB.

**Files:** `README.md` únicamente.
**Validates with:** revisión de coherencia manual contra los números ya presentes en la tabla comparativa y los tiempos citados.
**Rollback:** revertir la sección; no afecta ningún otro archivo.

## Dependencies & Order

- Ambas fases son independientes entre sí y no dependen de código nueva de la otra.
- Ninguna depende de la Fase 1 del plan anterior ($I(X;Y)$, ya completada) más allá de que ambas pueden opcionalmente citar $I(X;Y)$ como ejemplo de métrica ya cubierta.
- Ambas están bloqueadas por la misma condición: confirmación explícita del usuario para empezar (ver "Antes de empezar").

## Risks & Mitigations

- **Riesgo:** empezar la Fase 1 sin confirmar y que el usuario, tras estudiar el proyecto, quiera un enfoque de IA completamente distinto. **Mitigación:** preguntar primero, siempre — es la regla explícita de este plan, no una sugerencia.
- **Riesgo:** el árbol de decisión, entrenado solo con datos sintéticos, puede no generalizar bien y el profesor puede considerarlo un "IA" demasiado simple. **Mitigación:** declarar el alcance honestamente, enmarcarlo como prueba de concepto, no como sistema de producción.
- **Riesgo:** cualquier interpretación puede contradecir las páginas 2-7 del enunciado, aún sin conseguir. **Mitigación:** mantener todo marcado como basado solo en la página 1/7.

## Success Criteria

- Ninguna fase se inicia sin que la próxima sesión haya preguntado primero y recibido confirmación (o nueva dirección) del usuario.
- Si se ejecuta la Fase 1: el flag `--recomendar` existe, funciona sobre los 8 ejemplos reales, y su tasa de acierto está documentada sin inflar el resultado.
- Si se ejecuta la Fase 2: el README tiene una sección "Contexto 5G/6G" citando los tiempos reales de barrido y la tabla comparativa de 8 fuentes.
- En cualquier caso: las 8 verificaciones SHA-256 existentes siguen pasando sin regresión.

## Quick Start

```bash
# Restore full context
cat "D:\Proyectos\UD.Lab3.TeoriaInformacion\plans\handoffs\HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-27.md"

# PRIMERA ACCIÓN — no es código, es preguntar:
# "¿Ya definiste cómo quieres abordar el componente de IA, o seguimos con el árbol
#  de decisión que se había planteado? ¿Retomamos también la interpretación 5G/6G,
#  o sigue en pausa?"

# Si el usuario confirma seguir con el diseño de la Fase 1 tal como está aquí:
D:\Proyectos\UD.Lab3.TeoriaInformacion\src\tic_codec.py        # clase GeneradorFuentes, CodecTIC.barrido()
D:\Proyectos\UD.Lab3.TeoriaInformacion\examples\*\*.json       # 8 ejemplos curados, para validar --recomendar

# Verify starting state
cd "D:\Proyectos\UD.Lab3.TeoriaInformacion" && git status && git log --oneline -5
```
