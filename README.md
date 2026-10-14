# UD.Lab3.TeoriaInformacion — Códec adaptable de codificación y compresión

Lab 3 de **Teoría de la Información** (Ingeniería en Telemática, Universidad Distrital) — un sistema adaptable de codificación/decodificación/compresión por tamaño de símbolo, con métricas de teoría de la información antes, durante y después de codificar.

## ⚠️ Estado del enunciado
El enunciado del laboratorio se transcribió del tablero y **solo se tiene la página 1 de 7**. Todo lo documentado aquí sobre alcance y supuestos parte de esa única página; ver la sección "Supuestos" más abajo y el apunte de clase enlazado en Documentación.

## Enunciado (lo confirmado, pág. 1/7)
Diseñar un sistema adaptable para N ∈ {8, 16, 32, 64, 128, 256, 512, 1024, 2048} bits/símbolo que:
- Codifique y decodifique, comprima y descomprima fuentes de gran volumen: audio (1-2 min), video (5 min), texto, imagen (varias distintas).
- Muestre las 4 secuencias del proceso (codificada, comprimida, descomprimida, decodificada).
- Compare codificación **uniforme vs. no uniforme**, buscando eficiencia y confiabilidad.
- Use IA en algún punto del proceso.
- Identifique y elimine redundancia **de forma controlada**, y reconstruya la información verificando el resultado.
- Mida cantidad de información $I$, entropía $H$, información mutua $I(X;Y)$ y divergencia KL, interpretando los resultados.
- Contextualice todo en redes 5G/6G.

## Qué hay implementado: `src/tic_codec.py`
Un códec sin pérdida (con pérdida opcional) que modela **cualquier archivo** (imagen, video, audio, texto — se trabaja sobre bytes crudos) como una fuente discreta de símbolos de k bits, con k adaptable de 8 a 2048 (probado hasta 32 888, cualquier múltiplo de 8). Solo depende de NumPy (Matplotlib es opcional, para graficar).

### Organización del código (POO)
El script está organizado en clases, una por responsabilidad, en vez de funciones sueltas que se pasan arrays entre sí:

| Clase | Responsabilidad |
|---|---|
| `Fuente`, `Alfabeto`, `PerfilBits` | Segmentar el archivo en símbolos y calcular su estadística (alfabeto observado, perfil de entropía por bit) |
| `Informacion` | Caja de herramientas: entropía, información mutua $I(X;Y)$, entropía binaria, KL, clasificación uniforme/no uniforme (solo `staticmethod`, sin estado) |
| `MetricasAntes`, `MetricasDespues`, `ReporteBloque`, `ReporteCodificacion` | Dataclasses que reemplazan los diccionarios sueltos: imprimen, grafican y serializan a JSON |
| `MascaraRedundancia` | Separa bits constantes (redundancia determinista) de variables |
| `HuffmanCanonico` | Construcción, empaquetado y decodificación del código de Huffman |
| `CabeceraTIC` | La cabecera del formato `.tic`, antes un `dict` sin tipo construido a mano en dos sitios distintos |
| `CodecTIC` | Orquesta todo: `codificar()`, `decodificar()`, `barrido()` |
| `GeneradorFuentes` | Fuentes sintéticas de prueba |

Ningún símbolo individual se modela como objeto (con millones de filas eso mataría el rendimiento); las clases organizan el pipeline, y el cómputo pesado sigue vectorizado con NumPy exactamente igual que antes. El CLI, los nombres de comandos/flags y el formato del reporte JSON no cambiaron — se verificó por regresión corriendo los mismos casos de este README contra el código anterior, campo por campo, con resultado idéntico.

### Diagramas

Tres diagramas interactivos (HTML autocontenido, sin dependencias) documentan el diseño, generados con [Archify](https://github.com/tt-a1i/archify):

- [`diagrams/tic_codec.architecture.html`](diagrams/tic_codec.architecture.html) — arquitectura de clases: cómo `CodecTIC` orquesta `Fuente`/`Alfabeto`/`PerfilBits`/`Informacion` (análisis) y `MascaraRedundancia`/`HuffmanCanonico`/`CabeceraTIC` (formato `.tic`).
- [`diagrams/tic_codec.dataflow.html`](diagrams/tic_codec.dataflow.html) — flujo de datos antes/durante/después: de los bytes crudos al archivo `.tic` y de vuelta a la verificación por SHA-256.
- [`diagrams/tic_codec.teoria.html`](diagrams/tic_codec.teoria.html) — **de la teoría a la práctica**: mapa conceptual de H, I(x), R, KL(P‖U), I(X;Y) y confiabilidad, con la fórmula de cada uno, su idea intuitiva, cómo se relacionan entre sí y qué clase del código los calcula. Pensado para entender el proyecto sin haber leído antes ni la teoría ni el código.

Cada uno incluye vistas guiadas (`Guided views`), leyenda, y modo claro/oscuro. Las especificaciones fuente (`.json`) y las capturas de verificación visual quedan también en `diagrams/`.

### Pipeline
```
Bytes crudos → Segmentación (N × k/8) → Análisis ANTES (H, I, KL, perfil de bits)
            → Huffman + métricas DURANTE → Selección de modo → Archivo .tic
            → Decodificación + métricas DESPUÉS (verificación SHA-256)
```

1. **Segmentación:** el archivo se agrupa en símbolos de k/8 bytes.
2. **Identificación de símbolos:** `np.unique` da el alfabeto observado, sus frecuencias y el índice de cada símbolo.
3. **Análisis (ANTES):** entropía, autoinformación, redundancia, KL frente a la fuente uniforme, y el perfil de entropía por posición de bit (para detectar bits constantes/redundantes).
4. **Codificación (DURANTE):** longitudes de Huffman canónico sobre las frecuencias observadas; se miden H, longitud media y KL por bloques (para detectar no estacionariedad).
5. **Selección de modo:** compara el tamaño estimado de Huffman vs. un modo "bitstrip" (solo bits variables, sin codificación de entropía) y escribe el más pequeño — así nunca expande el archivo más allá de la cabecera.
6. **Decodificación (DESPUÉS):** reconstruye, verifica SHA-256 byte a byte y mide razón de compresión, eficiencia $\eta = H/\bar L$, entropía del flujo codificado y KL original vs. reconstruido.

### Cómo se cumple cada requisito

| Requisito del laboratorio | Cómo se cumple en el código |
|---|---|
| Codificar/decodificar grandes volúmenes | Procesamiento vectorizado por lotes; decodificación con tabla de hasta 2^16 entradas |
| k adaptable de 8 a 2048 (reto 32 888) | Parámetro `-k`, cualquier múltiplo de 8 |
| Imágenes, video, documentos | Se opera sobre los bytes crudos del archivo, sin asumir formato |
| Fuente uniforme o no uniforme | Clasificación automática por H/k y D_KL(P‖U); generador de fuentes sintéticas de ambos tipos |
| Identificar bits redundantes | Perfil de entropía binaria por posición; se eliminan del diccionario las posiciones constantes |
| Compresión controlada | Selección de modo por tamaño total estimado; `--perdida n` para cuantización explícita de LSB (con MSE/PSNR) |
| Medir I, H, I(X;Y), KL antes/durante/después | Tres grupos de métricas, reporte JSON y gráfica opcional. `I_XY` se reporta siempre: sin pérdida es igual a H por definición (Y=X exacto); con `--perdida` se mide la información mutua real entre fuente y reconstrucción |

**Pendiente de cubrir explícitamente en el código:** el punto de "uso de IA en el proceso" hoy es una selección de modo por regla fija (comparación de tamaños estimados), no un modelo entrenado — ver Próximos pasos.

## Uso

```bash
# generar una fuente sintética de prueba (uniforme | no_uniforme | estructurado)
python src/tic_codec.py generar estructurado data/prueba.bin --mb 4

# analizar sin codificar, para varios k
python src/tic_codec.py barrido data/prueba.bin --extendido

# codificar con un k concreto, guardando reporte JSON y gráfica
python src/tic_codec.py codificar data/prueba.bin reports/prueba.tic -k 2048 \
    --grafica reports/prueba.png --reporte reports/prueba.json

# compresión con pérdida controlada (anula los n LSB de cada byte)
python src/tic_codec.py codificar data/prueba.bin reports/prueba.tic -k 8 --perdida 3

# decodificar y verificar
python src/tic_codec.py decodificar reports/prueba.tic reports/salida.bin
```

Requisitos: `numpy` (obligatorio), `matplotlib` (solo si se usa `--grafica`), `soundfile` (solo para preparar fuentes de audio — decodificar/convertir formatos antes de pasárselas al códec, no lo usa `tic_codec.py` directamente).

## Interfaz gráfica (en construcción)

`src/app.py` es un backend Flask que expone el mismo códec como API JSON; la interfaz web (en `src/gui/`) la consume. No reimplementa nada: cada endpoint llama a `CodecTIC` / `GeneradorFuentes`.

```bash
pip install -r requirements.txt
python src/app.py
```

Abre http://127.0.0.1:5000. Lo que se sube o genera queda en `data/gui/<id>/` (ignorado por git).

| Endpoint | Entrada | Devuelve |
|---|---|---|
| `POST /api/subir` | multipart `archivo` | id, nombre, tamaño, tipo, SHA-256 |
| `POST /api/generar` | `{tipo, mb, semilla}` | lo mismo, para una fuente sintética |
| `POST /api/barrido` | `{id, conjunto: "base"\|"extendido"}` o `{id, ks: [...]}` | métricas "antes" y razón estimada por k, `mejor_k` |
| `POST /api/codificar` | `{id, k, perdida, bloques}` | reporte antes/durante/después, entropía por bit, curva rango-frecuencia, enlaces al `.tic` y al JSON |
| `POST /api/decodificar` | `{id, tic}` o multipart `archivo` (.tic) | cabecera, verificación SHA-256, `identico_al_original`, enlace al reconstruido |
| `GET /api/descargar/<id>/<nombre>` | — | el archivo |

## Primera corrida real: imagen JPEG
Se corrió el códec sobre una foto real (JPEG, 1 486 484 bytes, una de las capturas del tablero de clase). Resultados con k = 8 (`examples/imagen_jpeg/imagen_prueba.json`, gráfica en `imagen_prueba.png`):

| Métrica | Valor |
|---|---|
| H (bits/símbolo) | 7,948 |
| Redundancia R = 1 − H/k | 0,0065 |
| Razón de compresión | 1,0022 (prácticamente ninguna) |
| Eficiencia η = H/L̄ | 0,9962 |
| Verificación SHA-256 | ✅ idéntico byte a byte |

**Interpretación:** el JPEG ya viene comprimido por su propio formato, así que su entropía por byte está casi al máximo (7,95 de 8 bits posibles) y casi no queda redundancia que el códec pueda explotar — razón de compresión ≈ 1. Esto confirma exactamente la limitación que ya advertía la documentación técnica ("Formatos ya comprimidos"): para medir la redundancia real de una imagen hay que trabajar con píxeles crudos (BMP/PNG sin comprimir o YUV), no con el archivo JPEG ya codificado. La reconstrucción sí fue perfecta (SHA-256 y comparación byte a byte coinciden), que es lo que garantiza la fiabilidad del sistema aunque no haya ganancia de tamaño en este caso.

**Corrección aplicada:** `tic_codec.py` fallaba en Windows con `UnicodeEncodeError` (la consola usa cp1252 y el script imprime `─`/`‖`) — se agregó una reconfiguración de stdout/stderr a UTF-8 al inicio del script.

## Segunda corrida: la misma imagen sin comprimir (BMP)
La misma foto se convirtió a BMP (RGB crudo, sin compresión, con Pillow: `Image.open(...).save(..., "BMP")`) → 36 578 358 bytes, y se corrió un barrido de k antes de codificar (`examples/imagen_bmp/imagen_prueba_bmp.json`, gráfica en `imagen_prueba_bmp.png`):

| k (bits) | H (bits/símb.) | H/k | Razón estimada | Estructura |
|---|---|---|---|---|
| 8 | 7,611 | 0,951 | 1,047 | levemente no uniforme |
| 16 | 11,859 | 0,741 | 1,342 | no uniforme (alta redundancia) |
| **32** | **15,533** | **0,485** | **1,714** | **no uniforme (alta redundancia)** |
| 64 | 18,026 | 0,282 | 1,705 | no uniforme (alta redundancia) |
| 128+ | — | — | ~1,0 | casi todos los símbolos únicos (muestra insuficiente) |

Se codificó con k = 32 (el mejor candidato del barrido):

| Métrica | JPEG (k=8) | BMP (k=32) |
|---|---|---|
| Tamaño original | 1 486 484 B | 36 578 358 B |
| Tamaño codificado | 1 483 170 B | 21 347 192 B |
| **Razón de compresión** | **1,0022** | **1,7135** |
| **Ahorro** | 0,22 % | **41,64 %** |
| Eficiencia η = H/L̄ | 0,9962 | 0,9982 |
| Verificación SHA-256 | ✅ | ✅ |

**Interpretación:** al trabajar sobre los píxeles crudos (sin la compresión que ya aplica el formato JPEG), el códec sí encuentra y elimina redundancia real — 41,6 % de ahorro con k=32, symbol de 4 bytes (aprox. 1,33 píxeles RGB), que captura bien la correlación espacial entre píxeles vecinos (zonas planas del tablero blanco, la pared de ladrillo repetitiva). Con k=64 el ahorro es parecido (una razón estimada de 1,705); con k≥128 el alfabeto de símbolos crece más rápido que las repeticiones observables en una sola imagen de este tamaño, y deja de haber ganancia. Esto confirma la regla de adaptabilidad propuesta: **para imagen conviene una k intermedia (32-64), no la más grande del catálogo**, algo que solo se puede saber corriendo el barrido sobre cada fuente.

## Tercera corrida: texto real (apuntes de clase)
Fuente: 125 archivos `.md` de apuntes de universidad concatenados en un solo archivo (435 588 bytes de texto real en español, con Markdown y LaTeX — no es texto sintético). Barrido de k (`examples/texto/texto_prueba.json`, gráfica en `texto_prueba.png`):

| k (bits) | H (bits/símb.) | H/k | Razón estimada | Estructura |
|---|---|---|---|---|
| **8** | 5,778 | 0,722 | 1,378 | no uniforme (alta redundancia) |
| **16** | 10,442 | 0,653 | **1,429** | no uniforme (alta redundancia) |
| 32 | 14,366 | 0,449 | 1,000 | no uniforme, pero ya sin ganancia (alfabeto crece más rápido que las repeticiones) |
| 64+ | — | — | ~1,000 | casi todos los símbolos únicos |

Codificado con k = 16 (mejor razón del barrido):

| Métrica | Valor |
|---|---|
| Tamaño original | 435 588 B |
| Tamaño codificado | 305 075 B |
| **Razón de compresión** | **1,4278** |
| **Ahorro** | **29,96 %** |
| Eficiencia η | 0,9973 |
| Verificación SHA-256 / diff | ✅ idéntico byte a byte |

**Interpretación:** a diferencia de la imagen, el texto es no uniforme incluso a nivel de un solo byte (k=8: H=5,78 de 8 bits posibles, porque unas letras y símbolos son mucho más frecuentes que otros — el mismo fenómeno que el ejemplo de clase de VLC/Huffman, aquí a escala de un archivo real). El perfil de entropía por posición de bit con k=16 muestra algo revelador: las posiciones 0 y 8 (el bit más significativo de cada uno de los dos bytes del símbolo) tienen entropía casi nula, porque el texto es ASCII y ese bit casi siempre vale 0 — es exactamente el tipo de "bit constante/casi constante" que el enunciado pide identificar, aunque aquí no llega a ser perfectamente constante (por los acentos y símbolos especiales en UTF-8) y por eso no se cuenta como bit redundante eliminado.

## Cuarta corrida: audio real (voz), comprimido y sin comprimir
Fuente: 98,2 segundos de narración de voz real (grabaciones de un manual de usuario de otro proyecto, concatenadas — no es audio sintético), mono a 24 000 Hz. Igual que con la imagen, se probó la misma grabación en dos formatos: **MP3** (786 126 B, ya comprimido con pérdida por el propio códec de audio) y **WAV/PCM 16 bits** (4 715 180 B, sin comprimir), decodificado con `soundfile` (libsndfile) y guardado con `sf.write`.

Barrido de k sobre el WAV (`examples/audio_wav/audio_wav.json`):

| k (bits) | H (bits/símb.) | H/k | Razón estimada |
|---|---|---|---|
| 8 | 7,298 | 0,912 | 1,093 |
| **16** | 13,628 | 0,852 | **1,136** (mejor) |
| 32+ | — | — | ~1,000 (sin ganancia) |

Codificado con k=16 en el WAV y k=8 en el MP3:

| Métrica | MP3 (k=8) | WAV/PCM (k=16) |
|---|---|---|
| Tamaño original | 786 126 B | 4 715 180 B |
| Tamaño codificado | 784 769 B | 4 152 261 B |
| **Razón de compresión** | 1,0017 | **1,1356** |
| **Ahorro** | 0,17 % | **11,94 %** |
| Eficiencia η | 0,9982 | 0,9979 |
| Verificación SHA-256 | ✅ | ✅ |

**Interpretación:** el patrón se repite igual que con la imagen — el MP3 ya viene comprimido (con pérdida, además) por su propio formato, así que casi no queda redundancia de bajo nivel que un códec de entropía de orden cero pueda explotar. El WAV/PCM sí tiene redundancia real (11,94 % de ahorro), pero **mucho menos que la imagen BMP** (41,64 %). Esto es coherente con la limitación de "modelo de orden cero" que ya señalaba la documentación técnica: el habla tiene fuerte correlación entre muestras consecutivas (la onda no salta bruscamente de una muestra a la siguiente), pero Huffman por símbolo no aprovecha esa correlación temporal — solo la desigualdad en las frecuencias de amplitud. Un codificador diferencial (guardar la diferencia entre muestras consecutivas antes de Huffman) explotaría mejor esta redundancia, y queda anotado como mejora futura.

## Quinta corrida: video real (screen recording), comprimido y sin comprimir
Fuente: una grabación de pantalla real (28,1 s, 1280×720, 60 fps, contenido propio — no descargado ni sintético). Se probó igual que las anteriores: el **MP4** original (1 444 096 B, ya comprimido) y una versión **RGB cruda** (sin contenedor, un `.tofile()` de los frames como arreglo NumPy `(N, H, W, 3)` uint8) extraída con OpenCV.

**Ajuste de escala, declarado:** el enunciado pide 5 minutos de video, pero el decodificador de este códec es Python puro para el paso de Huffman (documentado como límite conocido: "~1 µs por símbolo"). Un video de 5 minutos a resolución completa sin comprimir pesa varios GB, y decodificarlo con este códec tomaría horas. Por eso se usó la grabación disponible (28,1 s) y, para la versión cruda, se redujo la resolución a 160×90 (72 921 600 B, manteniendo los 1688 frames completos, es decir toda la duración temporal real). El MP4 se probó a su resolución original (1280×720) porque ahí no hay que decodificar frame a frame — se mide directamente sobre los bytes comprimidos, igual que con el JPEG y el MP3.

Barrido de k sobre el RGB crudo (`examples/video_rgb/video_rgb.json`) — a diferencia de imagen y audio, aquí la redundancia **sigue creciendo hasta k=512**:

| k (bits) | H (bits/símb.) | H/k | Razón estimada |
|---|---|---|---|
| 8 | 5,100 | 0,638 | 1,560 |
| 16 | 6,572 | 0,411 | 2,416 |
| 32 | 7,248 | 0,226 | 4,357 |
| 64 | 7,335 | 0,115 | 8,535 |
| 128 | 7,465 | 0,058 | 16,308 |
| 256 | 7,456 | 0,029 | 29,888 |
| **512** | **8,119** | **0,016** | **43,578** (mejor) |
| 1024 | 9,642 | 0,009 | 33,715 |
| 2048 | 11,134 | 0,005 | 15,328 |
| 4096 | 12,477 | 0,003 | 6,584 |

Codificado con k=512 en el RGB y k=8 en el MP4:

| Métrica | MP4 (k=8) | RGB crudo (k=512) |
|---|---|---|
| Tamaño original | 1 444 096 B | 72 921 600 B |
| Tamaño codificado | 1 417 996 B | 1 673 857 B |
| **Razón de compresión** | 1,0184 | **43,565** |
| **Ahorro** | 1,81 % | **97,70 %** |
| Eficiencia η | 0,9968 | 0,9955 |
| Verificación SHA-256 | ✅ | ✅ |

**Interpretación:** este es, por lejos, el resultado con más redundancia explotada de las cuatro fuentes. Tiene sentido: un screen recording pasa la mayor parte del tiempo con grandes zonas de pantalla sin cambios entre un frame y el siguiente, así que muchos símbolos de 512 bits (64 bytes = ~21,3 píxeles RGB) se repiten idénticos miles de veces — es la misma razón por la que el ejemplo de la fuente sintética "estructurada" del proyecto original llegaba a 150:1. También confirma, con datos reales, por qué la **k óptima depende enteramente de la fuente**: 512 para este video, 32 para la imagen fija, 16 para audio y texto. Un sistema que solo probara k pequeñas se quedaría muy por debajo de la compresión real posible. La gráfica "durante" muestra además un salto claro alrededor del bloque 37 (H y L suben de golpe): corresponde al punto de la grabación donde cambia el contenido en pantalla, y el aumento de $D_{KL}(\text{bloque}\|\text{global})$ ahí mismo es justamente la métrica que el enunciado pide para detectar no estacionariedad.

## Comparación entre las cinco fuentes probadas

| Fuente | Tamaño | k elegido | H (bits/símb.) | Razón | Ahorro |
|---|---|---|---|---|---|
| Imagen JPEG (ya comprimida) | 1,49 MB | 8 | 7,948 | 1,002 | 0,22 % |
| Imagen BMP (píxeles crudos) | 36,58 MB | 32 | 15,533 | 1,714 | 41,64 % |
| Texto (apuntes reales) | 0,44 MB | 16 | 10,442 | 1,428 | 29,96 % |
| Audio MP3 (ya comprimido) | 0,79 MB | 8 | 7,964 | 1,002 | 0,17 % |
| Audio WAV (PCM crudo) | 4,72 MB | 16 | 13,628 | 1,136 | 11,94 % |
| Video MP4 (ya comprimido) | 1,44 MB | 8 | 7,826 | 1,018 | 1,81 % |
| Video RGB (crudo, 160×90) | 69,56 MB | 512 | 8,119 | 43,565 | 97,70 % |

Las siete reconstrucciones fueron bit-exactas (SHA-256). El patrón se sostiene en las tres fuentes con formato comprimido vs. crudo (imagen, audio, video): el formato ya comprimido no deja casi nada, y el crudo sí — pero cuánto depende de qué tipo de redundancia tiene la fuente (espacial 2D en imagen, temporal en audio, espacial+temporal combinadas en video) y de qué tan grande hay que hacer el símbolo para capturarla.

## Resultados experimentales de referencia
Con una fuente estructurada de 2 MB (16 bloques de 256 B repetidos con ruido):

| k (bits) | N | U | H (bits/símb.) | H/k | Razón |
|---|---|---|---|---|---|
| 8 | 2 097 152 | 256 | 7,951 | 0,9939 | 1,003 |
| 64 | 262 144 | 528 | 9,009 | 0,1408 | 6,99 |
| 256 | 65 536 | 144 | 7,041 | 0,0275 | 33,6 |
| 2048 | 8 192 | 32 | 4,335 | 0,0021 | 150 (real) |

Con `--perdida 3` y k = 8 sobre una fuente sintética: razón 3,44:1, PSNR 38,4 dB (corrida anterior a agregar $I(X;Y)$, no reproducida aquí por no tener registrado el archivo de origen exacto). Todas las decodificaciones sin pérdida pasaron la verificación SHA-256.

**Ejemplo real y reproducible con $I(X;Y)$** — `--perdida 3` y k = 8 sobre `data/imagen_prueba.bmp` (imagen real cruda, la misma de la sección de imagen más arriba): $H(X) = 7,611$ bits/símbolo, $I(X;Y) = 4,621$ bits/símbolo (estrictamente menor que H, como debe ser cuando la reconstrucción no es exacta), razón 1,7195:1, ahorro 41,84%, PSNR 35,67 dB. Reporte completo en [`examples/imagen_bmp_perdida3/imagen_bmp_perdida3.json`](examples/imagen_bmp_perdida3/imagen_bmp_perdida3.json). En los 7 casos sin pérdida documentados arriba, $I(X;Y) = H$ exactamente (columna `I_XY` de cada JSON), porque la reconstrucción es idéntica al original — no es un error de cálculo, es la definición de información mutua cuando $Y=X$.

## Supuestos declarados (por falta de las páginas 2-7 del enunciado)
- **"N bits/símbolo"** se interpreta como la profundidad de codificación por símbolo de la fuente (cuántos bits representan cada símbolo antes de comprimir), igual que en el ejercicio de cuantificación PCM visto en clase.
- **"IA en el proceso"** se interpreta como un componente que ayuda a decidir la codificación (ej. recomendar k o el tipo de codificación), no como un modelo generativo que reemplace la codificación.
- **"Confiable"** se interpreta como reconstrucción verificable con una métrica objetiva: bit-exacta (SHA-256) sin pérdida, o error medible (MSE/PSNR) con pérdida.

## Próximos pasos
- [ ] Confirmar con el profesor el significado exacto de "N bits/símbolo" y el alcance esperado de "IA".
- [ ] Conseguir las páginas 2 a 7 del enunciado y verificar que nada aquí las contradiga.
- [x] Imagen (JPEG y BMP) y texto real corridos y verificados — ver secciones de arriba.
- [x] Audio real (voz, 98 s, MP3 y WAV) corrido y verificado — ver sección de arriba.
- [x] Video real (screen recording, 28,1 s, MP4 y RGB crudo) corrido y verificado — ver sección de arriba. Duración y resolución reducidas frente a los 5 min pedidos, por el límite de rendimiento del decodificador en Python puro (declarado en esa sección); las 4 fuentes del enunciado (imagen, audio, texto, video) ya están cubiertas.
- [x] Calcular explícitamente $I(X;Y)$ entre la fuente original y la reconstruida — `Informacion.informacion_mutua()`, reportado como `I_XY` en todos los JSON (`= H` sin pérdida por definición; con `--perdida` se mide la información mutua real, ver ejemplo arriba).
- [ ] Sustituir/complementar la selección de modo por regla fija con un modelo simple (árbol de decisión, por ejemplo) que recomiende k y el tipo de codificación — para cubrir el punto de "IA en el proceso".
- [ ] Interpretar los resultados en el contexto de 5G/6G (relación entre k, latencia y ancho de banda).

## Documentación
- [`docs/Codec_adaptable_documentacion_tecnica.pdf`](docs/Codec_adaptable_documentacion_tecnica.pdf) — documentación técnica completa: fórmulas, formato del archivo `.tic`, Huffman canónico, límites del estimador de entropía.
- [`docs/Codec_adaptable_para_principiantes.pdf`](docs/Codec_adaptable_para_principiantes.pdf) — explicación introductoria del mismo códec.
- Apuntes de clase (Obsidian, no versionados aquí): teorema de la codificación de fuente, VLC/Huffman y la propuesta de diseño inicial del Lab 3.
