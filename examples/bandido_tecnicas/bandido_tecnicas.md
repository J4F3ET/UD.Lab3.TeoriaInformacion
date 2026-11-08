# El bandido elige la técnica de compresión
Generado por `src/bandido_tecnicas.py`: 173 bloques de 256 KB de los tramos uniforme, estructurado_256, texto, no_uniforme, estructurado_32, audio_wav, imagen_bmp, imagen_jpg. Brazos: ninguna, zlib-6, zstd-3, zstd-19, bz2-9, lzma-6.

| técnica | razón media por bloque | MB/s al comprimir |
|---|---:|---:|
| ninguna | 1.000 | — |
| zlib-6 | 12.039 | 12.63 |
| zstd-3 | 11.724 | 123.36 |
| zstd-19 | 13.652 | 1.35 |
| bz2-9 | 12.637 | 5.6 |
| lzma-6 | 16.213 | 2.75 |

## Recompensa: solo razón

| política | razón global | CPU s | arrepentimiento |
|---|---:|---:|---:|
| óptimo | 2.286 | 8.94 | 0.00 |
| siempre lzma-6 | 2.255 | 15.75 | 0.65 |
| siempre zstd-19 | 2.196 | 31.93 | 3.56 |
| bandido | 2.147 | 9.75 | 3.89 |
| siempre bz2-9 | 2.156 | 7.72 | 4.48 |
| siempre zlib-6 | 2.064 | 3.42 | 6.69 |
| siempre zstd-3 | 2.052 | 0.35 | 7.34 |
| aleatoria | 1.788 | 9.89 | 13.55 |
| siempre ninguna | 1.000 | 0.00 | 51.90 |

Qué elige el bandido en cada tramo (segunda mitad del tramo): uniforme → **zstd-19**, estructurado_256 → **zlib-6**, texto → **ninguna**, no_uniforme → **zstd-19**, estructurado_32 → **bz2-9**, audio_wav → **bz2-9**, imagen_bmp → **bz2-9**, imagen_jpg → **zlib-6**.

## Recompensa: 10 Mbps

| política | razón global | CPU s | tiempo total s | arrepentimiento |
|---|---:|---:|---:|---:|
| óptimo | 2.086 | 0.60 | 17.99 | 0.00 |
| siempre zstd-3 | 2.052 | 0.35 | 18.03 | 0.18 |
| bandido | 2.002 | 1.62 | 19.74 | 8.34 |
| siempre zlib-6 | 2.064 | 3.42 | 21.00 | 14.33 |
| siempre bz2-9 | 2.156 | 7.72 | 24.55 | 31.29 |
| aleatoria | 1.788 | 9.89 | 30.18 | 58.10 |
| siempre lzma-6 | 2.255 | 15.75 | 31.85 | 66.05 |
| siempre ninguna | 1.000 | 0.00 | 36.28 | 87.20 |
| siempre zstd-19 | 2.196 | 31.93 | 48.46 | 143.71 |

Qué elige el bandido en cada tramo (segunda mitad del tramo): uniforme → **ninguna**, estructurado_256 → **zstd-3**, texto → **ninguna**, no_uniforme → **zstd-3**, estructurado_32 → **zstd-3**, audio_wav → **zstd-3**, imagen_bmp → **zstd-3**, imagen_jpg → **zstd-3**.

## Recompensa: 100 Mbps

| política | razón global | CPU s | tiempo total s | arrepentimiento |
|---|---:|---:|---:|---:|
| óptimo | 2.026 | 0.30 | 2.09 | 0.00 |
| siempre zstd-3 | 2.052 | 0.35 | 2.12 | 1.38 |
| bandido | 1.952 | 1.38 | 3.24 | 19.44 |
| siempre ninguna | 1.000 | 0.00 | 3.63 | 73.35 |
| siempre zlib-6 | 2.064 | 3.42 | 5.18 | 111.69 |
| aleatoria | 1.788 | 9.89 | 11.92 | 153.78 |
| siempre lzma-6 | 2.255 | 15.75 | 17.36 | 220.31 |
| siempre bz2-9 | 2.156 | 7.72 | 9.41 | 239.28 |
| siempre zstd-19 | 2.196 | 31.93 | 33.58 | 246.35 |

Qué elige el bandido en cada tramo (segunda mitad del tramo): uniforme → **ninguna**, estructurado_256 → **zstd-3**, texto → **ninguna**, no_uniforme → **zstd-3**, estructurado_32 → **zstd-3**, audio_wav → **zstd-3**, imagen_bmp → **zstd-3**, imagen_jpg → **zstd-3**.

## Recompensa: 1 Gbps

| política | razón global | CPU s | tiempo total s | arrepentimiento |
|---|---:|---:|---:|---:|
| óptimo | 1.504 | 0.03 | 0.27 | 0.00 |
| bandido | 1.494 | 1.13 | 1.37 | 34.56 |
| siempre ninguna | 1.000 | 0.00 | 0.36 | 45.51 |
| siempre zstd-3 | 2.052 | 0.35 | 0.53 | 75.33 |
| aleatoria | 1.788 | 9.89 | 10.10 | 172.39 |
| siempre zlib-6 | 2.064 | 3.42 | 3.60 | 214.84 |
| siempre zstd-19 | 2.196 | 31.93 | 32.10 | 218.51 |
| siempre bz2-9 | 2.156 | 7.72 | 7.89 | 218.51 |
| siempre lzma-6 | 2.255 | 15.75 | 15.91 | 218.51 |

Qué elige el bandido en cada tramo (segunda mitad del tramo): uniforme → **ninguna**, estructurado_256 → **zstd-3**, texto → **ninguna**, no_uniforme → **ninguna**, estructurado_32 → **zstd-3**, audio_wav → **zstd-3**, imagen_bmp → **ninguna**, imagen_jpg → **zstd-3**.
