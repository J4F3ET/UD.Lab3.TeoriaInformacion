# Técnicas actuales frente al códec TIC
Generado por `src/comparar_tecnicas.py`. Todas las técnicas son sin pérdida. «1 byte dañado» = información entregada I(X;Y)/H(X) cuando se invierte un byte del archivo comprimido (promedio de tres posiciones: 25, 50 y 75 % del largo).

## texto — apuntes de clase, texto plano

435,588 bytes, H = 5.7777 bits/byte. Muestra: archivo completo.

| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |
|---|---:|---:|---:|---:|:---:|---:|
| lzma-6 | 2.708 | 63.07 | 1.33 | 17.24 | sí | 41.78 |
| zstd-19 | 2.656 | 62.35 | 1.39 | 166.44 | sí | 66.18 |
| bz2-9 | 2.533 | 60.53 | 3.11 | 6.77 | sí | 0.00 |
| zlib-9 | 2.476 | 59.62 | 4.08 | 77.84 | sí | 76.75 |
| zlib-6 | 2.474 | 59.58 | 7.05 | 72.13 | sí | 67.22 |
| zstd-3 | 2.451 | 59.20 | 63.05 | 301.17 | sí | 66.18 |
| tic (k=16) | 1.428 | 29.96 | 0.20 | 1.20 | sí | 60.66 |

## audio_wav — voz, PCM sin comprimir

4,715,180 bytes, H = 7.298 bits/byte. Muestra: el mismo audio reescrito como WAV PCM 16 bits (cabecera canónica).

| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |
|---|---:|---:|---:|---:|:---:|---:|
| flac | 1.746 | 42.72 | 22.74 | 46.47 | sí | 0.00 |
| bz2-9 | 1.345 | 25.63 | 4.63 | 7.21 | sí | 38.26 |
| lzma-6 | 1.300 | 23.09 | 1.90 | 10.49 | sí | 49.76 |
| zstd-19 | 1.198 | 16.56 | 1.32 | 142.50 | sí | 74.60 |
| zstd-3 | 1.168 | 14.38 | 25.11 | 134.02 | sí | 100.00 |
| zlib-6 | 1.167 | 14.32 | 10.02 | 127.51 | sí | 66.86 |
| zlib-9 | 1.167 | 14.31 | 6.30 | 70.76 | sí | 61.86 |
| tic (k=16) | 1.136 | 11.94 | 0.14 | 0.86 | sí | 50.38 |

## audio_mp3 — la misma voz, ya comprimida con MP3

786,126 bytes, H = 7.9644 bits/byte. Muestra: archivo completo.

| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |
|---|---:|---:|---:|---:|:---:|---:|
| zstd-19 | 1.022 | 2.16 | 3.66 | 1663.80 | sí | 77.78 |
| bz2-9 | 1.018 | 1.81 | 3.46 | 6.17 | sí | 0.00 |
| zlib-9 | 1.014 | 1.36 | 10.73 | 110.31 | sí | 99.83 |
| zlib-6 | 1.014 | 1.35 | 11.15 | 108.86 | sí | 79.76 |
| lzma-6 | 1.013 | 1.28 | 2.78 | 9.36 | sí | 49.89 |
| zstd-3 | 1.009 | 0.90 | 34.50 | 1777.82 | sí | 100.00 |
| tic (k=8) | 1.002 | 0.17 | 0.15 | 0.77 | sí | 100.00 |

## imagen_bmp — foto, píxeles sin comprimir

16,777,206 bytes, H = 7.4147 bits/byte. Muestra: franja superior de 4032×1387 píxeles de 4032×3024, guardada como BMP.

| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |
|---|---:|---:|---:|---:|:---:|---:|
| webp-sin-perdida | 8.277 | 87.92 | 1.59 | 46.25 | sí | 55.74 |
| png | 5.492 | 81.79 | 2.66 | 66.19 | sí | 0.00 |
| bz2-9 | 5.257 | 80.98 | 7.07 | 7.52 | sí | 44.85 |
| lzma-6 | 4.756 | 78.97 | 1.14 | 38.68 | sí | 49.93 |
| zstd-19 | 4.370 | 77.12 | 1.14 | 232.04 | sí | 58.66 |
| zlib-9 | 3.282 | 69.53 | 8.12 | 133.62 | sí | 58.80 |
| zlib-6 | 3.275 | 69.47 | 12.63 | 129.52 | sí | 59.08 |
| zstd-3 | 3.151 | 68.27 | 56.38 | 250.65 | sí | 75.60 |
| tic (k=32) | 1.672 | 40.20 | 0.30 | 1.49 | sí | 82.37 |

## imagen_jpg — la misma foto, ya comprimida con JPEG

1,486,484 bytes, H = 7.9479 bits/byte. Muestra: archivo completo.

| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |
|---|---:|---:|---:|---:|:---:|---:|
| bz2-9 | 1.016 | 1.59 | 3.71 | 5.72 | sí | 20.18 |
| zstd-19 | 1.003 | 0.32 | 3.95 | 813.23 | sí | 100.00 |
| tic (k=8) | 1.002 | 0.22 | 0.16 | 0.83 | sí | 100.00 |
| zlib-6 | 1.002 | 0.20 | 10.02 | 179.60 | sí | 99.95 |
| zlib-9 | 1.002 | 0.20 | 12.90 | 237.81 | sí | 99.95 |
| lzma-6 | 1.002 | 0.16 | 2.57 | 26.73 | sí | 83.25 |
| zstd-3 | 1.000 | -0.00 | 304.02 | 2705.38 | sí | 100.00 |

## video_rgb — grabación de pantalla, cuadros RGB crudos

16,777,216 bytes, H = 5.0432 bits/byte. Muestra: primeros 16 MB de 69.5 MB.

| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |
|---|---:|---:|---:|---:|:---:|---:|
| lzma-6 | 603.063 | 99.83 | 6.25 | 338.70 | sí | 32.31 |
| zstd-19 | 406.740 | 99.75 | 63.09 | 1671.66 | sí | 54.80 |
| zstd-3 | 321.144 | 99.69 | 1199.66 | 1236.86 | sí | 99.99 |
| bz2-9 | 86.440 | 98.84 | 2.70 | 17.02 | sí | 49.31 |
| tic (k=64) | 8.739 | 88.56 | 0.69 | 5.91 | sí | 67.81 |
| zlib-9 | 5.006 | 80.02 | 8.11 | 151.59 | sí | 65.47 |
| zlib-6 | 4.932 | 79.72 | 24.02 | 205.51 | sí | 78.50 |

## video_mp4 — la misma grabación, ya comprimida con H.264

1,444,096 bytes, H = 7.8261 bits/byte. Muestra: archivo completo.

| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |
|---|---:|---:|---:|---:|:---:|---:|
| zstd-19 | 1.168 | 14.36 | 3.49 | 976.67 | sí | 100.00 |
| lzma-6 | 1.159 | 13.74 | 2.75 | 10.77 | sí | 49.60 |
| zstd-3 | 1.135 | 11.89 | 43.00 | 1280.64 | sí | 100.00 |
| bz2-9 | 1.117 | 10.50 | 4.14 | 7.20 | sí | 21.24 |
| zlib-9 | 1.108 | 9.74 | 10.39 | 141.56 | sí | 99.92 |
| zlib-6 | 1.106 | 9.57 | 12.52 | 174.90 | sí | 99.71 |
| tic (k=8) | 1.018 | 1.81 | 0.18 | 0.88 | sí | 69.07 |
