# Lab 3 Teoría de la Información — códec TIC completo, documentado y diagramado; quedan 5 ítems de backlog

**Date:** 2026-09-26
**Status:** IN PROGRESS
**Bead(s):** none
**Epic:** none
**Chain:** `standalone-b98b0026` seq `1`
**Parent:** `none — first in chain`
**Prior chain:** none — first in chain

---

## Reference Documents

- `docs/Codec_adaptable_documentacion_tecnica.pdf` (repo, 7 páginas) — documentación técnica completa del códec original: fórmulas, formato del archivo `.tic`, Huffman canónico, límites del estimador de entropía. Leída íntegra antes de tocar el código.
- `docs/Codec_adaptable_para_principiantes.pdf` (repo) — explicación introductoria del mismo códec, leída íntegra también.
- `2026-09-21 - Teorema de la codificación fuente.md` (Obsidian, fuera del repo) — enunciado del laboratorio transcrito del tablero por el usuario, solo página 1/7, más 8 imágenes anexadas verificadas por fidelidad de transcripción. Es la única fuente del alcance real del laboratorio.
- `Plantilla - Apunte.md` (Obsidian) — plantilla de apuntes del usuario que estructuró el apunte de diseño de este laboratorio.

## The Goal

Cumplir el Lab 3 de Teoría de la Información (Ingeniería en Telemática, Universidad Distrital): diseñar un sistema adaptable de codificación/decodificación/compresión para N ∈ {8,16,...,2048} bits/símbolo que procese audio, video, texto e imagen; compare codificación uniforme vs. no uniforme; use IA en algún punto; identifique y elimine redundancia de forma controlada; mida H, I, I(X;Y) y KL antes/durante/después; y contextualice todo en redes 5G/6G. El enunciado del profesor solo se tiene en su página 1 de 7 (transcrita a mano del tablero), así que buena parte del trabajo ha sido declarar explícitamente los supuestos adoptados en ausencia de las páginas 2-7. El usuario (jafetdc16@gmail.com) pidió explícitamente que el código del laboratorio viva en un repositorio Git separado dentro de `D:\Proyectos`, **nunca** dentro de su vault de Obsidian (que no debe tener repositorios git). El código base (`tic_codec.py`) no lo escribió esta sesión — ya existía en los anexos de Obsidian del usuario y esta sesión lo encontró, lo llevó al repo, lo corrió sobre datos reales y lo refactorizó.

## Where We Are

- Excel `Codificacion_PCM_7bits.xlsx` (ruta: `C:\Users\jafet\OneDrive\...\Teoría de la Información\Codificacion_PCM_7bits.xlsx`) creado vía openpyxl, 100% basado en fórmulas (sin valores fijos): hoja **Parámetros** (rango 0-5V, resolución de 7 bits = 128 niveles, paso de cuantificación calculado por fórmula), **Segmentos** (los 8 segmentos de la ley de compansión, si aplica, o los límites uniformes), **Intervalos** (los límites de cada uno de los 128 intervalos con su fórmula de voltaje), **Tabla completa** (las 128 filas: número de intervalo, bit de signo, 7 bits de magnitud, voltaje mínimo/máximo/central de cada intervalo — TODO por fórmula, ninguna encontrada por Python), **Codificador** (fórmula que dado un voltaje de entrada devuelve el código signo+intervalo de 8 bits), **Decodificador** (la inversa: dado un código de 8 bits, devuelve el voltaje reconstruido). No se tocó más después de crearlo — no forma parte del repo de Git, es un artefacto separado en la carpeta de Obsidian.
- Apunte de Obsidian `2026-09-26 - Lab 3 - Propuesta de diseño del sistema adaptable.md` escrito siguiendo la plantilla `Plantilla - Apunte.md` del usuario (frontmatter tipo/materia/fecha/tema, secciones `## 🧠 Notas de Clase` / `## 📎 Anexos` / `## ❓ Dudas e Investigación`). Se le añadió después un callout `[!info] Implementación real` enlazando al repo de GitHub real, una vez que se encontró la implementación existente.
- Repo GitHub privado creado: `https://github.com/J4F3ET/UD.Lab3.TeoriaInformacion` (vía `gh repo create --private --source=. --remote=origin --push`), ruta local `D:\Proyectos\UD.Lab3.TeoriaInformacion`, siguiendo la nomenclatura de su hermano `UD.Lab2.TeoriaInformacion`. 9 commits, todos en `main`, working tree limpio, sincronizado con `origin/main` (verificado con `git status` justo antes de este handoff).
- Estructura del repo: `src/tic_codec.py` (877 líneas, POO), `docs/*.pdf` (2 PDFs técnicos originales), `data/` (gitignored — archivos de prueba pesados), `reports/` (gitignored — scratch), `examples/<fuente>/[*.json,*.png]` (comprometido — 7 pares de resultados curados), `diagrams/` (nuevo esta sesión — specs Archify + HTML + capturas), `README.md`, `.gitignore`.
- `tic_codec.py` refactorizado completamente de un script funcional de 522 líneas a 877 líneas en 14 clases (ver "Code Analysis"). Verificado por regresión: salidas JSON byte-idénticas al script original (excepto campos de timing) para JPEG/BMP/texto; ruta `--perdida` (lossy) también probada.
- Las 4 fuentes que pide el enunciado (imagen, audio, texto, video) están corridas, cada una en su forma comprimida y sin comprimir = 7 corridas totales, las 7 verificadas bit-exactas por SHA-256. Resultados curados en `examples/{imagen_jpeg,imagen_bmp,texto,audio_mp3,audio_wav,video_mp4,video_rgb}/`.
- README.md creció a 260 líneas: enunciado + estado + supuestos, tabla de clases POO, pipeline, tabla "cómo se cumple cada requisito", uso del CLI, 5 secciones de resultados por fuente (JPEG, BMP, texto, audio, video) cada una con tabla de barrido + antes/después + interpretación en prosa, tabla comparativa de las 7 fuentes, resultados de referencia sintéticos, supuestos declarados, checklist "Próximos pasos", documentación.
- Dos diagramas Archify completos en `diagrams/`: `tic_codec.architecture.{json,html}` (arquitectura de 12 clases, hecho en sesión anterior a este handoff) y `tic_codec.dataflow.{json,html}` (pipeline antes/durante/después de 9 nodos, hecho en esta sesión). Ambos pasan `validate --quality showcase` con 9/9 checks y 0 errores/advertencias, ambos entregados con `deliver`, ambos con `visual-check` en verde (`"ok": true`) en 1440×900, 1600×1000, 1920×1080, 2048×1320, claro y oscuro. Ambos inspeccionados visualmente (captura PNG leída con la herramienta Read) para confirmar que no hay defectos que los checks automáticos no capturen.
- Sección nueva "Diagramas" agregada al README (después de "Organización del código (POO)"), enlazando ambos HTMLs.
- Todo comprometido y pusheado: commit `048a473` "Agrega diagramas Archify de arquitectura y flujo de datos del códec" — 17 archivos, 31 578 inserciones.
- `bd` (beads) no está disponible en este entorno — no hay tracking de tareas fuera de los checklists del README.
- No existe `CLAUDE.md` ni archivo "BIBLE" en el repo — el README es la única fuente de verdad del proyecto.

## What We Tried (Chronological)

1. **Excel con fórmulas para PCM 7 bits (0-5V):** primer intento con openpyxl falló con `SyntaxError: Non-UTF-8 code` por un carácter literal `º` (`N.º`) escrito sin manejo explícito de codificación → se corrigió reescribiendo el script con `encoding="utf-8"` explícito en la apertura del archivo. Resultado: workbook completo con las 128 filas de la tabla de intervalos, todo por fórmula (sin precalcular en Python), como pidió el usuario explícitamente ("dame el excel usa las formulas para evitar calcular todos los segmentos").
2. **Localizar la implementación real:** el usuario reveló que ya existía un códec (`tic_codec.py`) en `99 - Anexos/.../lab 3/` de su Obsidian junto a 2 PDFs de documentación. Se leyeron los 3 archivos completos (script + 7 páginas del PDF técnico) antes de tocar nada.
3. **Crear el repo separado:** siguiendo la instrucción explícita y literal del usuario de nunca meter git en Obsidian, se creó `D:\Proyectos\UD.Lab3.TeoriaInformacion` con `gh repo create --private --source=. --remote=origin --push`, copiando `tic_codec.py` y los PDFs sin modificarlos en ese primer commit.
4. **Primera corrida real (imagen JPEG):** al ejecutar el CLI en PowerShell/cmd de Windows se obtuvo `UnicodeEncodeError` porque la consola usa cp1252 y el script imprime caracteres `─`/`‖` (box-drawing). Fix permanente: bloque `if sys.platform == "win32": sys.stdout.reconfigure(encoding="utf-8")` al inicio del script — no requiere `PYTHONIOENCODING` como variable de entorno después. Resultado: barrido de k sobre la imagen JPEG real (1 486 484 B), k=8 óptimo, razón 1,002 (imagen ya comprimida, casi sin redundancia que explotar) — resultado esperado y usado como control.
5. **Segunda corrida (misma imagen sin comprimir, BMP):** el usuario pidió explícitamente convertir a BMP y comparar. Conversión con Pillow (JPEG→BMP, 36 578 358 B). Resultado: k=32 óptimo, razón 1,714, ahorro 41,64% — contraste claro con el JPEG, confirmando que la compresión de formato ya se come la redundancia que el códec busca.
6. **Tercera corrida (texto real):** 125 notas `.md` del propio vault de Obsidian del usuario concatenadas en `texto_prueba.txt` (435 588 B). k=16 óptimo, razón 1,428, ahorro 29,96%.
7. **Refactor a POO:** el usuario pidió explícitamente "refactorizar el codigo en poo y que sea mas facil de leer" tras confirmar que el script original era monolítico ("no he leido el codigo, pero esta enfocado a poo? o es un archivo monolitico"). Se reescribieron las ~15 responsabilidades del script en 14 clases (dataclasses para estado tipado, utilidades estáticas para funciones sin estado), preservando el CLI, los nombres de flags y el formato JSON exactos. Verificado corriendo los mismos casos de JPEG/BMP/texto contra el script pre-refactor y comparando JSON campo por campo — idénticos salvo timing.
8. **Cuarta corrida (audio real):** voz narrada real, 2 clips MP3 concatenados (`audio_prueba.mp3`, 786 126 B, ~98s) y su decodificación PCM16 vía `soundfile`/libsndfile 1.2.2 a WAV (`audio_prueba.wav`, 4 715 180 B). MP3: k=8, razón 1,002. WAV: k=16, razón 1,136, ahorro 11,94%.
9. **Quinta corrida (video real):** grabación de pantalla real del propio usuario. Intento inicial con el video completo a resolución original resultó demasiado lento — el decodificador Huffman en Python puro tiene un cuello de botella de ~1µs/símbolo, y a resolución/duración completas (5 min pedidos por el enunciado) el tiempo de proceso era impracticable. Decisión: reducir duración a 28,1s y resolución a 160×90 vía OpenCV, **declarando explícitamente esta reducción como supuesto en el README** en vez de ocultarla. MP4 comprimido (1 444 096 B): k=8, razón 1,018. RGB crudo (72 921 600 B, dump de los 1688 frames redimensionados, sin contenedor): k=512 óptimo — el más alto de las 7 fuentes — razón 43,565, ahorro 97,70%. Esta corrida por sí sola tardó ~2m21s (k=8..256) y ~44s (k=512..4096) según los logs de terminal capturados.
10. **Diagrama de arquitectura Archify (sesión previa a este handoff, resumen heredado):** muchas rondas de fallos de validación iterativa — tags demasiado anchos, back-edge `archivo→codec` causando crossings, edge `alfabeto→huffman` atravesando el nodo `informacion`, layout manual por `pos` generando overlaps → se cambió a `layout: {mode:"grid", cols:7, cellW:100, cellH:125, gapX:50, gapY:18}`, luego fallo de `desktop-readability` (viewBox muy ancho) y `viewport-overflow` en visual-check (cards muy altas) → se ajustaron cellH/gapY y se recortaron los bullets de las cards a 2 ítems cortos cada una. **Hallazgo post-checks-automáticos:** tras pasar todos los checks automáticos, la inspección visual manual de la captura reveló 2 `labelAt` obsoletos (coordenadas de una geometría anterior ya cambiada) con etiquetas flotando lejos de sus líneas — se corrigió eliminando todos los `labelAt` y re-derivándolos frescos desde las sugerencias del propio validador bajo la geometría final.
11. **Diagrama de dataflow Archify (esta sesión):** ver detalle completo en "Evidence & Data" — 7 rondas de validación antes de llegar a 0 errores, con un problema estructural de fondo (corredor ambiguo entre dos flujos que compartían el mismo eje vertical) resuelto reubicando el nodo `modo` de `row:2` a `row:1` para evitar que dos aristas cruzaran el mismo corredor en direcciones opuestas — no con parches de `channelX`/`labelAt`, que se probaron primero y no bastaron.

### Texto exacto del enunciado confirmado (README, "Enunciado (lo confirmado, pág. 1/7)") — evidencia primaria, cítese literal en cualquier entrega

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

### Supuestos declarados exactos (README, "Supuestos declarados") — usar este texto literal, no reinterpretar

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

### Metadatos de las fuentes reales usadas (no están en el README de forma tan explícita)

- Audio: ~98 segundos de narración de voz real, 2 clips MP3 concatenados.
- Video: grabación de pantalla real de 28,1 segundos (reducido desde los 5 min del enunciado), 1688 frames extraídos, redimensionados a 160×90 antes del dump RGB crudo.
- Texto: exactamente 125 notas `.md` reales del vault de Obsidian del propio usuario, concatenadas en un solo `.txt`.

### Iteraciones de validación del diagrama de arquitectura (sesión previa a este handoff, heredado del resumen de contexto)

| Problema | Fix aplicado |
|---|---|
| Tag de texto más ancho que su caja | Se acortaron/eliminaron los tags |
| Back-edge larga `archivo→codec` causaba `proper-crossing` y `endpoint-side-direction` | Se eliminó la arista por completo; el concepto pasó a una card en vez de una conexión |
| `alfabeto→huffman` atravesaba el nodo `informacion` (`clean-flow/edge-through-node`) | Se reubicó `informacion` de `row:0,col:4` a `row:1,col:3` |
| Layout manual por `pos` generaba muchos overlaps/crossings | Se cambió a `layout:{mode:"grid",...}` con `row`/`col` |
| `cellW`/`gapX` demasiado agresivos (110/14) causaban overlaps `<8px` | Se ajustó a los valores finales estables `cellW:100, cellH:125, gapX:50, gapY:18` |
| `composition/desktop-readability` (viewBox muy ancho para 1440px) | Se redujeron `cellW`/`gapX` y se acortaron 2 sublabels largos |
| `viewer/viewport-overflow` en `visual-check` (página más alta que el viewport en las 4 resoluciones) | Se redujo `cellH`/`gapY`; se recortaron los bullets de las cards |
| Post-checks-automáticos: inspección visual manual reveló 2 `labelAt` obsoletos con etiquetas flotando lejos de sus líneas, y 2 labels (`codec-fuente`, `codec-reporte`) técnicamente separados pero visualmente pegados | Se eliminaron TODOS los `labelAt`, se re-derivaron frescos de las sugerencias del validador bajo la geometría final, y se separaron manualmente en x los dos que aún chocaban (`codec-fuente:[390,297]`, `codec-reporte:[190,297]`) |

## Key Decisions

- **No git en Obsidian, nunca:** decisión explícita del usuario, no negociable. Todo el código vive en `D:\Proyectos\UD.Lab3.TeoriaInformacion`; Obsidian solo tiene notas/markdown de clase.
- **Commitear solo ejemplos curados, no los datos de prueba pesados:** `data/` (hasta 72,9 MB por archivo) y `reports/` están en `.gitignore`; solo los JSON+PNG de `examples/` (salida de `--reporte`/`--grafica`) se versionan como evidencia permanente.
- **Preservar el cómputo vectorizado de NumPy en el refactor POO:** se rechazó explícitamente modelar cada símbolo como un objeto individual — con millones de filas eso mataría el rendimiento. Las clases organizan el pipeline; el cómputo pesado sigue en arrays NumPy completos.
- **Declarar la reducción del video en vez de ocultarla:** en vez de forzar los 5 minutos completos a resolución original (impracticable con el decodificador puro-Python), se documentó explícitamente en el README la razón técnica (cuello de botella ~1µs/símbolo) y el alcance real (28,1s, 160×90).
- **Video RGB crudo sin contenedor, no un `.avi`/`.raw` con metadata:** se optó por un dump plano de frames RGB porque el códec opera sobre bytes crudos sin asumir formato — meter un contenedor habría introducido una estructura que el códec no está diseñado para modelar.
- **Diagrama de dataflow: `modo` en `row:1`, no en `row:0` ni `row:2`:** se rechazó la disposición "diamante" (huffman row0/perfil row2 convergiendo en modo) porque generaba un error `composition/ambiguous-corridor` — dos aristas (`alfabeto→huffman` y `perfil→modo`) compartían el mismo eje vertical en direcciones opuestas. La solución fue estructural (reposicionar el nodo), no geométrica (channelX/labelAt), tras comprobar que los parches geométricos no resolvían el problema de fondo.
- **`viewBox` del dataflow fijado en `[1080, 630]`:** 1080 es el mínimo que evita "Stages exceed viewBox width" (mínimo real reportado por el validador: 1068) y a la vez cumple `desktop-readability` a 1440px (que exige `viewBoxWidth <= ~1085` para que el texto más pequeño del nodo proyecte ≥6px). 630 de alto es el mínimo que evita el overflow vertical en `visual-check` a 1440×900 (se probó 720 → overflow de 330px; 600 → nodo fuera de rango; 650 → overflow de solo 8px; 630 → pasa limpio).
- **Supuestos declarados explícitamente en el README** (sección "Supuestos declarados") en vez de asumir en silencio, dado que solo se tiene la página 1/7 del enunciado: interpretación de "N bits/símbolo", alcance de "IA en el proceso", y definición operativa de "confiable".

## Evidence & Data

### Commits del repo (9 total, todos en `main`, orden cronológico)

| Hash | Fecha | Mensaje |
|---|---|---|
| `10fb282` | 2026-09-26 | Estructura inicial del Lab 3: códec adaptable de k bits |
| `cac3f79` | 2026-09-26 | Corre el códec sobre una imagen JPEG real y arregla Windows |
| `552ae59` | 2026-09-26 | Corre el códec sobre la misma imagen sin comprimir (BMP) |
| `608c5bf` | 2026-09-26 | Corre el códec sobre texto real (apuntes de clase) |
| `9e12fbb` | 2026-09-26 | Refactoriza tic_codec.py a POO para mejorar la lectura |
| `b01ed81` | 2026-09-26 | Documenta la organización en clases en el README |
| `3fec5b4` | 2026-09-26 | Corre el códec sobre audio real (voz), MP3 y WAV |
| `f6a8ca3` | 2026-09-26 | Corre el códec sobre video real (screen recording), MP4 y RGB |
| `048a473` | 2026-09-26 | Agrega diagramas Archify de arquitectura y flujo de datos del códec (17 archivos, +31 578) |

### Tabla comparativa final de las 7 fuentes (del README, sección "Comparación entre las cinco fuentes probadas")

| Fuente | Tamaño | k elegido | H (bits/símb.) | Razón | Ahorro |
|---|---|---|---|---|---|
| Imagen JPEG (comprimida) | 1,49 MB | 8 | 7,948 | 1,002 | 0,22% |
| Imagen BMP (cruda) | 36,58 MB | 32 | 15,533 | 1,714 | 41,64% |
| Texto (real) | 0,44 MB | 16 | 10,442 | 1,428 | 29,96% |
| Audio MP3 (comprimido) | 0,79 MB | 8 | 7,964 | 1,002 | 0,17% |
| Audio WAV (crudo) | 4,72 MB | 16 | 13,628 | 1,136 | 11,94% |
| Video MP4 (comprimido) | 1,44 MB | 8 | 7,826 | 1,018 | 1,81% |
| Video RGB (crudo, 160×90) | 69,56 MB | 512 | 8,119 | 43,565 | 97,70% |

Todas verificadas bit-exactas por SHA-256.

### Barridos crudos de video capturados en logs de terminal de esta sesión (no están en el README de forma tan granular)

k=8..256 (real 2m21.711s):
```
     k          N          U          H     H/k   log2N    KL(P‖U) bits red.   razón  estructura
     8 72,921,600        256      5.100  0.6375   26.12       2.90         0   1.560  no uniforme (alta redundancia)
    16 36,460,800     16,317      6.572  0.4108   25.12       9.43         0   2.416  no uniforme (alta redundancia)
    32 18,230,400     23,557      7.248  0.2265   24.12      24.75         0   4.357  no uniforme (alta redundancia)
    64  9,115,200     16,680      7.335  0.1146   23.12      56.66         0   8.535  no uniforme (alta redundancia)
   128  4,557,600     11,925      7.465  0.0583   22.12     120.54         0  16.308  no uniforme (alta redundancia)
   256  2,278,800      9,276      7.456  0.0291   21.12     248.54         0  29.888  no uniforme (alta redundancia)
```
k=512..4096 (real 0m44.169s):
```
     k          N          U          H     H/k   log2N    KL(P‖U) bits red.   razón  estructura
   512  1,139,400      7,873      8.119  0.0159   20.12     503.88         0  43.578  no uniforme (alta redundancia)
  1024    569,700     11,424      9.642  0.0094   19.12    1014.36         0  33.715  no uniforme (alta redundancia)
  2048    284,850     16,965     11.134  0.0054   18.12    2036.87         0  15.328  no uniforme (alta redundancia)
  4096    142,425     21,155     12.477  0.0030   17.12    4083.52         0   6.584  no uniforme (alta redundancia)
```
Nótese que 512 (no 4096) es el óptimo real por tamaño total de archivo — el README usa 512 como "k elegido" para esta fuente.

### Archivos de datos de prueba reales (todos en `data/`, gitignored — solo local)

| Archivo | Tamaño exacto (bytes) | Origen |
|---|---:|---|
| `imagen_prueba.jpg` | 1 486 484 | Foto real |
| `imagen_prueba.bmp` | 36 578 358 | Misma foto, convertida JPEG→BMP con Pillow |
| `texto_prueba.txt` | 435 588 | 125 notas `.md` reales del vault de Obsidian del usuario, concatenadas |
| `audio_prueba.mp3` | 786 126 | 2 clips de narración de voz real, concatenados |
| `audio_prueba.wav` | 4 715 180 | Decodificación PCM16 del MP3 anterior vía `soundfile`/libsndfile 1.2.2 |
| `video_prueba.mp4` | 1 444 096 | Grabación de pantalla real del propio usuario |
| `video_prueba.rgb` | 72 921 600 | Dump crudo RGB de los 1688 frames del MP4, redimensionados a 160×90 vía OpenCV, sin contenedor |

### `.gitignore` del repo

Excluye `data/` (los 7 archivos de la tabla anterior, hasta 72,9 MB cada uno) y `reports/` (scratch de corridas intermedias) — ninguno de los dos se sube nunca; solo los pares `*.json`/`*.png` curados en `examples/<fuente>/` quedan versionados como evidencia permanente y reproducible sin necesitar los archivos de datos originales.

### Iteraciones de validación del diagrama de dataflow (esta sesión, 7 rondas hasta 0 errores)

| Ronda | Error(es) principal(es) | Fix aplicado |
|---|---|---|
| 1 | Sublabel "imagen / audio / texto / video" muy ancho; nodos fuera de bounds; múltiples labels solapando nodos; viewBox insuficiente | Acortar sublabel a "archivo original"; fijar `viewBox: [1260, 640]` |
| 2 | 2 labels aún solapando nodos; 2 flujos verticales (`modo→archivo`, `archivo→decodificar`) con 0px de separación | `labelDy` en varios flujos; `channelX` distintos para los 2 flujos verticales |
| 3 | `micro-segment` (stub de 4px, mínimo 8px); mismo par de flujos verticales aún a 0px | channelX demasiado cerca del borde del nodo — insuficiente |
| 4 | `ambiguous-corridor`: `alfabeto→huffman` y `perfil→modo` comparten 228px de corredor en x=637.5 | **Fix estructural**: mover `modo` de `row:2` a `row:1`, `huffman` de `row:0` a `row:2` (luego revertido), reordenar todo el layout de stage3/stage4 |
| 5 | Nuevo layout: `ambiguous-corridor` con 75px de overlap en el mismo par (channelX 600 vs 675 insuficiente) | Simplificar: quitar `channelX` manual, dejar `alfabeto→huffman` recto en `row:0` compartido con `huffman`, `modo` solo en `row:1` |
| 6 | Cascada de labels solapando nodos/entre sí (`tamaño estimado` vs `escribe cabecera + secciones`, etc.) | Serie de `labelAt` explícitos tomados de las sugerencias literales del validador, iterando ~4 veces hasta que cada nueva posición no creaba un nuevo conflicto |
| 7 | `composition/desktop-readability`: viewBoxWidth 1260 muy ancho para 930px disponibles a 1440px con fuente de 7px | Reducir `viewBox` a `[1080, 720]` (930/1085 máximo calculado) |

Luego de esto, `validate --quality showcase` pasó (9/9, 0 errores). `visual-check` reveló overflow vertical (scrollHeight 1230-1384 vs innerHeight 900-1320 en las 4 resoluciones) → se redujo `viewBox` height de 720→600 (nodo `metricas` en row4 quedó fuera de rango, límite reportado "keep y between 104 and 526") → se subió a 650 (pasó validate, pero visual-check dio overflow de solo 8px en 1440×900) → bajado a 630 (pasa validate Y visual-check limpio en las 4 resoluciones × 2 temas). También se recortaron los bullets de las 3 cards de 1-2 líneas largas a 1 línea corta cada uno.

### Recibos de entrega (`deliver`) de ambos diagramas

- Arquitectura: SHA-256 spec + artifact, 9/9 checks, 0 errores/0 advertencias (de sesión anterior, heredado).
- Dataflow: spec SHA-256 `32f59ae8...`, 3884 bytes; artifact SHA-256 `17303c45...`, 810 701 bytes; `checksPassed: 9, checkCount: 9, compositionStatus: "pass", errors: 0, warnings: 0`.

## Code Analysis

`src/tic_codec.py` (877 líneas), estructura de clases final:

- `Fuente` (dataclass: `k`, `filas`, `longitud_original`; classmethods `desde_bytes`/`desde_archivo`; propiedad `.n`) — segmenta el archivo en símbolos de k bits.
- `Alfabeto` (dataclass: `simbolos`, `indices`, `frecuencias`; `.desde_filas`; propiedad `.U`; `.probabilidades()`; `.a_diccionario()`) — símbolos únicos vía `np.unique`.
- `PerfilBits` (dataclass: `p_uno`, `entropia_por_bit`; `.desde_filas`; propiedad `.constantes`) — detecta posiciones de bit constantes (redundancia determinista).
- `Informacion` (clase estática, sin estado: `entropia`, `entropia_binaria`, `kl_suavizada`, `clasificar`) — caja de herramientas de teoría de la información.
- `MetricasAntes` (dataclass; `.calcular()` classmethod; `.a_dict()`) — mide H, I, redundancia, KL(P‖U) antes de codificar.
- `MascaraRedundancia` (dataclass: `variables`, `valores_constantes`; `.extraer()`/`.insertar()`/`.a_hex()`/`.desde_hex()`) — separa bits constantes de variables.
- `HuffmanCanonico` (`.desde_frecuencias`, `_construir_longitudes`, `_codigos_canonicos`, `.empaquetar()`, `.decodificar()`, `.longitud_maxima`, `.longitud_media()`, `.kraft()`).
- `CabeceraTIC` (dataclass con las claves JSON exactas del formato original: `k,orig_len,n,U,modo,perdida,mascara_var,valores_const,sha256,secciones`).
- `ReporteBloque` (dataclass: `bloque,H_bloque,L_bloque,KL_bloque_vs_global,razon_acumulada`) — detecta no estacionariedad por bloques.
- `MetricasDespues` (dataclass; campo `ahorro_pct` mapeado a la clave JSON `"ahorro_%"`).
- `ReporteCodificacion` (dataclass: `antes,durante,despues`; `.imprimir()`,`.graficar()`,`.guardar_json()`).
- `CodecTIC` (`MAGIC=b"TIC1"`; `__init__(bloques=50)`; métodos públicos `.codificar()`,`.decodificar()`,`.barrido()`).
- `GeneradorFuentes` (static `uniforme`/`no_uniforme`/`estructurado`, classmethod `.generar()`) — fuentes sintéticas de prueba.

CLI (`main()`, `argparse`) sin cambios de flags/subcomandos respecto al script original de 522 líneas. Bloque de compatibilidad Windows al inicio: `if sys.platform == "win32": sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")`.

Formato del archivo `.tic` (constante `MAGIC = b"TIC1"` al inicio del archivo binario), cabecera JSON serializada por `CabeceraTIC.a_json()` con exactamente estas claves (invariante preservada del script original, verificada byte a byte en la regresión): `k, orig_len, n, U, modo, perdida, mascara_var, valores_const, sha256, secciones`. El campo `modo` toma valor `"huffman"` o `"bitstrip"` según cuál produzca el archivo más pequeño — la comparación de tamaños ES el punto exacto donde el enunciado pide "IA en el proceso" y hoy es una regla fija, no un modelo (ver Where We're Going, ítem 2). `CodecTIC.__init__(bloques=50)` — controla en cuántos bloques se divide la fuente para las métricas "durante" (detección de no estacionariedad vía $D_{KL}(\text{bloque}\|\text{global})$ por bloque, ver `ReporteBloque`). `--perdida n` activa cuantización con pérdida enmascarando los `n` bits menos significativos de cada símbolo antes de codificar, reportando MSE/PSNR en `MetricasDespues`; probado con `--perdida 3` y k=8: razón 3,44:1, PSNR 38,4 dB.

## Diagrama de arquitectura — inventario de componentes (`diagrams/tic_codec.architecture.json`, sesión previa a este handoff)

12 componentes en layout `grid` (7 columnas, `cellW:100, cellH:125, gapX:50, gapY:18`), agrupados en 2 boundaries (`region`):

| Componente | Tipo | Boundary |
|---|---|---|
| `cli` (CLI, argparse) | frontend | — |
| `generador` (GeneradorFuentes) | external | — |
| `codec` (CodecTIC, orquesta el pipeline) | backend | — |
| `fuente` (Fuente) | backend | "Análisis de la fuente" |
| `alfabeto` (Alfabeto) | backend | "Análisis de la fuente" |
| `perfil` (PerfilBits) | backend | "Análisis de la fuente" |
| `informacion` (Informacion, sin estado) | backend | "Análisis de la fuente" |
| `mascara` (MascaraRedundancia) | backend | "Codificación y formato .tic" |
| `huffman` (HuffmanCanonico) | backend | "Codificación y formato .tic" |
| `cabecera` (CabeceraTIC) | database | "Codificación y formato .tic" |
| `archivo` (Archivo .tic) | database | "Codificación y formato .tic" |
| `reporte` (ReporteCodificacion) | frontend | — |

13 conexiones, 3 cards ("Sin objetos por símbolo", "Selección controlada del modo", "Ciclo cerrado de verificación"), 3 vistas guiadas (`pipeline-codificar`, `analisis-fuente`, `formato-tic`).

## Files Changed

### Fuera del repo Git (Obsidian, sin versionar)
- `Codificacion_PCM_7bits.xlsx` — workbook de cuantificación PCM 7 bits, 100% fórmulas, 128 filas de intervalos 0-5V.
- `2026-09-26 - Lab 3 - Propuesta de diseño del sistema adaptable.md` — apunte de diseño siguiendo la plantilla del usuario.

### Repo `D:\Proyectos\UD.Lab3.TeoriaInformacion`
- `src/tic_codec.py` — refactor completo funcional→POO (522→877 líneas, 14 clases), sin cambio de comportamiento.
- `README.md` — creció de 0 a 260 líneas a lo largo de la sesión; última edición esta sesión agregó la sección "Diagramas".
- `docs/Codec_adaptable_documentacion_tecnica.pdf`, `docs/Codec_adaptable_para_principiantes.pdf` — copiados sin modificar desde Obsidian.
- `examples/{imagen_jpeg,imagen_bmp,texto,audio_mp3,audio_wav,video_mp4,video_rgb}/*.json,*.png` — 7 pares de resultados curados y comprometidos.
- `diagrams/tic_codec.architecture.{json,html}` + `tic_codec.architecture.visual-check.{1440x900,2048x1320}.{light,dark}.png` + `tic_codec.architecture.visual-check.{html,json}` — arquitectura de clases (sesión previa).
- `diagrams/tic_codec.dataflow.{json,html}` + `tic_codec.dataflow.visual-check.{1440x900,2048x1320}.{light,dark}.png` + `tic_codec.dataflow.visual-check.{html,json}` — pipeline antes/durante/después (esta sesión, nuevo). 17 archivos nuevos en total entre ambos diagramas, comprometidos en un solo commit (`048a473`, +31 578 líneas — la mayoría son los dos HTML autocontenidos de ~810 KB cada uno).
- `.gitignore` — excluye `data/` y `reports/`.

## User Feedback & Preferences

- "el rango es de 0 a 5v" — corrección concreta de rango de voltaje para el Excel PCM.
- "dame el excel usa las formulas para evitar calcular todos los segmentos" — preferencia explícita: fórmulas, no valores precalculados.
- "pero necesito el valor de todos los intervalos los voltajes de cada uno" — corrección: quería la tabla completa de 128 filas, no un resumen.
- "En la carpeta que te di existe algo llamado anexos en mi obsidian busca la carpeta lab 3 en esta encuantras mas contexto y una implementacion de lo que sze pidio con ese codigo crea una carpeta en mi carpeta de proyectos con la nomenclatura correspondiente y crea el repositorio de github en la carpeta proyectos **lo de obsidian no debe tener repositorios git**" — instrucción explícita y no negociable, verbatim, sobre separación estricta Obsidian/proyectos.
- "corre el códec sobre una imagen real de prueba" — pidió datos reales, no sintéticos.
- "sí, conviértela a BMP y corre la comparación" — pidió explícitamente el contraste comprimido/crudo.
- "sí, sigue con texto ahora" / "sí, sigue con audio" / "sí, sigue con video" — aprobaciones secuenciales para continuar con cada fuente restante.
- "no he leido el codigo, pero esta enfocado a poo? o es un archivo monolitico" — pregunta que llevó directamente al pedido de refactor.
- "comencemos con, refactorizar el codigo en poo y que sea mas facil de leer entiendo que sea un script monolitico pero esto mejoraria la lectura" — pidió refactor POO explícitamente, reconociendo que un script monolítico también es válido pero prefiriendo legibilidad.
- "usa archify para definir la arquitectura y los esquemas necesarios" — pidió explícitamente **más de un** diagrama ("los esquemas necesarios", plural) — esto es lo que motivó crear tanto el diagrama de arquitectura como el de dataflow en esta sesión/la anterior.
- Preferencia implícita observada en todo el hilo: el usuario valora que los supuestos no confirmados se declaren explícitamente por escrito (dado el enunciado incompleto), no que se asuman en silencio.
- "tenemos repositorio del lab que te di los apuntes con la nota que te comparti?" / "tenemos repositorio del lab?" — el usuario preguntó dos veces por el estado del repositorio antes de dar la instrucción explícita de crearlo; señal de que el repo/versionado del código era una preocupación temprana y persistente, no una idea tardía.
- "con tu nota creada, tengo una plantilla para apuntes crea uno con esta info" — el usuario tiene una plantilla estándar (`Plantilla - Apunte.md`) que espera se use para *cualquier* apunte nuevo de clase, no solo este — señal de una convención de documentación personal a respetar en futuros apuntes de este curso.
- Mensaje inicial extenso explicando en sus propias palabras la nomenclatura signo-segmento del PCM ("el primer bit es el signo el segundo un segmento...") — el usuario entiende el concepto pero usa terminología propia ("segmento" en vez de "intervalo"); aclaró él mismo que son equivalentes. Señal de que prefiere terminología de clase mezclada con la técnica, no una sola forma rígida.

## Where We're Going

1. Calcular explícitamente $I(X;Y)$ entre la fuente original y la reconstruida — hoy el código mide $D_{KL}$ y verifica SHA-256, pero el enunciado pide información mutua explícita.
2. Sustituir o complementar la selección de modo por regla fija (comparación de tamaños Huffman vs. bitstrip) con un componente que use un modelo real (p. ej. árbol de decisión) para recomendar k y el tipo de codificación — cubrir el punto de "IA en el proceso" del enunciado con algo más que una regla fija.
3. Interpretar los resultados ya obtenidos (tabla comparativa de 7 fuentes) en el contexto de redes 5G/6G — relación entre k elegido, latencia de codificación y ancho de banda ahorrado.
4. Confirmar con el profesor el significado exacto de "N bits/símbolo" y el alcance esperado de "IA en el proceso" (los supuestos actuales están declarados en el README pero no confirmados).
5. Conseguir las páginas 2-7 del enunciado y verificar que ninguno de los supuestos declarados las contradiga.

## Risks & Blockers

- Solo se tiene la página 1/7 del enunciado — cualquier trabajo sobre I(X;Y), IA o 5G/6G corre el riesgo de no alinear con el alcance real que pedían las páginas faltantes.
- El componente de "IA en el proceso" hoy es una regla fija de comparación de tamaños (no un modelo entrenado) — si el profesor exige explícitamente un modelo entrenado, el trabajo del punto 2 de "Where We're Going" es obligatorio, no opcional.
- El video de prueba se redujo de 5 min a 28,1s y de resolución original a 160×90 por el cuello de botella de rendimiento del decodificador Python puro (~1µs/símbolo) — está declarado en el README, pero si el profesor pide explícitamente el video a duración/resolución completas, sería necesario optimizar el decodificador (vectorizar la tabla de Huffman) o aceptar tiempos de ejecución de horas.
- `bd` (beads) no está disponible en este entorno, así que no hay tracking de tareas entre sesiones fuera de este handoff y el checklist manual del README.

## Open Questions

- ¿"N bits/símbolo" se refiere exactamente a la profundidad de codificación por símbolo (interpretación actual, análoga a la cuantificación PCM vista en clase) o a otra cosa que las páginas 2-7 del enunciado aclararían?
- ¿El "uso de IA en el proceso" que pide el enunciado espera un modelo de ML real y entrenado, o basta con un componente de decisión (regla o heurística) que el profesor considere "IA" en sentido amplio?

## Quick Start for Next Session

```bash
# Restore context — read this handoff and its paired plan
cat "D:\Proyectos\UD.Lab3.TeoriaInformacion\plans\handoffs\HANDOFF_standalone-b98b0026_lab3-tic-codec_2026-09-26.md"
cat "D:\Proyectos\UD.Lab3.TeoriaInformacion\plans\handoffs\PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-26.md"

# Key files to read first
D:\Proyectos\UD.Lab3.TeoriaInformacion\README.md          # todo el contexto del proyecto, sección "Próximos pasos"
D:\Proyectos\UD.Lab3.TeoriaInformacion\src\tic_codec.py    # el códec completo, 14 clases
D:\Proyectos\UD.Lab3.TeoriaInformacion\examples\video_rgb\*.json   # ejemplo de reporte con antes/durante/después

# Evidence / data files
D:\Proyectos\UD.Lab3.TeoriaInformacion\examples\*\*.json   # 7 reportes curados, base para cualquier métrica nueva

# Verify current state
cd "D:\Proyectos\UD.Lab3.TeoriaInformacion" && git status && git log --oneline -5
python src/tic_codec.py --help

# Next action
Leer el plan (PLAN_standalone-b98b0026_lab3-tic-codec_2026-09-26.md) y empezar por su Fase 1.
```
