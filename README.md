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
| Medir I, H, KL antes/durante/después | Tres grupos de métricas, reporte JSON y gráfica opcional |

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

Requisitos: `numpy` (obligatorio), `matplotlib` (solo si se usa `--grafica`).

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

## Resultados experimentales de referencia
Con una fuente estructurada de 2 MB (16 bloques de 256 B repetidos con ruido):

| k (bits) | N | U | H (bits/símb.) | H/k | Razón |
|---|---|---|---|---|---|
| 8 | 2 097 152 | 256 | 7,951 | 0,9939 | 1,003 |
| 64 | 262 144 | 528 | 9,009 | 0,1408 | 6,99 |
| 256 | 65 536 | 144 | 7,041 | 0,0275 | 33,6 |
| 2048 | 8 192 | 32 | 4,335 | 0,0021 | 150 (real) |

Con `--perdida 3` y k = 8: razón 3,44:1, PSNR 38,4 dB. Todas las decodificaciones sin pérdida pasaron la verificación SHA-256.

## Supuestos declarados (por falta de las páginas 2-7 del enunciado)
- **"N bits/símbolo"** se interpreta como la profundidad de codificación por símbolo de la fuente (cuántos bits representan cada símbolo antes de comprimir), igual que en el ejercicio de cuantificación PCM visto en clase.
- **"IA en el proceso"** se interpreta como un componente que ayuda a decidir la codificación (ej. recomendar k o el tipo de codificación), no como un modelo generativo que reemplace la codificación.
- **"Confiable"** se interpreta como reconstrucción verificable con una métrica objetiva: bit-exacta (SHA-256) sin pérdida, o error medible (MSE/PSNR) con pérdida.

## Próximos pasos
- [ ] Confirmar con el profesor el significado exacto de "N bits/símbolo" y el alcance esperado de "IA".
- [ ] Conseguir las páginas 2 a 7 del enunciado y verificar que nada aquí las contradiga.
- [ ] Ejecutar el códec sobre las 4 fuentes reales pedidas (audio 1-2 min, video 5 min, texto, imágenes), no solo sobre fuentes sintéticas.
- [ ] Calcular explícitamente $I(X;Y)$ entre la fuente original y la reconstruida (hoy el código mide KL y verificación SHA-256, pero no reporta $I(X;Y)$ como tal).
- [ ] Sustituir/complementar la selección de modo por regla fija con un modelo simple (árbol de decisión, por ejemplo) que recomiende k y el tipo de codificación — para cubrir el punto de "IA en el proceso".
- [ ] Interpretar los resultados en el contexto de 5G/6G (relación entre k, latencia y ancho de banda).

## Documentación
- [`docs/Codec_adaptable_documentacion_tecnica.pdf`](docs/Codec_adaptable_documentacion_tecnica.pdf) — documentación técnica completa: fórmulas, formato del archivo `.tic`, Huffman canónico, límites del estimador de entropía.
- [`docs/Codec_adaptable_para_principiantes.pdf`](docs/Codec_adaptable_para_principiantes.pdf) — explicación introductoria del mismo códec.
- Apuntes de clase (Obsidian, no versionados aquí): teorema de la codificación de fuente, VLC/Huffman y la propuesta de diseño inicial del Lab 3.
