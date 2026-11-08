# Calidad: curvas tasa-distorsión
Generado por `src/tasa_distorsion.py`. «I/H» = información mutua entre original y recuperado dividida por la entropía del original (100 % = sin pérdida).

## Imagen (4032×1387 píxeles, H = 7.4147 bits/byte)

| método | parámetro | bits/píxel | razón | PSNR dB | I/H % |
|---|---:|---:|---:|---:|---:|
| png (sin pérdida) | - | 4.370 | 5.49 | inf | 100.00 |
| jpeg | 10 | 0.156 | 153.71 | 32.89 | 41.75 |
| jpeg | 20 | 0.184 | 130.62 | 37.25 | 50.50 |
| jpeg | 30 | 0.219 | 109.69 | 39.52 | 54.55 |
| jpeg | 50 | 0.308 | 77.79 | 41.82 | 59.05 |
| jpeg | 70 | 0.468 | 51.33 | 44.27 | 64.52 |
| jpeg | 85 | 0.823 | 29.16 | 47.7 | 72.52 |
| jpeg | 95 | 1.288 | 18.63 | 55.82 | 89.57 |
| webp | 10 | 0.053 | 454.44 | 37.41 | 51.00 |
| webp | 30 | 0.071 | 336.19 | 39.17 | 54.45 |
| webp | 50 | 0.098 | 245.50 | 40.36 | 56.43 |
| webp | 70 | 0.134 | 179.23 | 41.24 | 58.09 |
| webp | 90 | 0.448 | 53.57 | 44.99 | 65.90 |
| cuantizar+zstd | 1 | 4.865 | 4.93 | 51.13 | 86.53 |
| cuantizar+zstd | 2 | 3.401 | 7.06 | 42.68 | 73.09 |
| cuantizar+zstd | 3 | 2.168 | 11.07 | 35.68 | 59.77 |
| cuantizar+zstd | 4 | 1.223 | 19.62 | 29.26 | 46.72 |
| cuantizar+zstd | 5 | 0.711 | 33.78 | 23.26 | 34.39 |

## Audio (2,357,568 muestras a 24000 Hz, H = 13.6279 bits/muestra)

| método | parámetro | kbps | bits/muestra | razón | SNR dB | I/H % |
|---|---:|---:|---:|---:|---:|---:|
| flac (sin pérdida) | - | 219.9 | 9.164 | 1.75 | inf | 100.00 |
| mp3 | 0.0 | 86.7 | 3.612 | 4.43 | 30.35 | 58.38 |
| mp3 | 0.25 | 64.0 | 2.667 | 6.00 | 25.68 | 56.08 |
| mp3 | 0.5 | 47.3 | 1.972 | 8.11 | 22.01 | 54.23 |
| mp3 | 0.75 | 37.8 | 1.573 | 10.17 | 20.26 | 52.94 |
| mp3 | 0.95 | 27.4 | 1.143 | 14.00 | 17.31 | 52.21 |
| cuantizar+flac | 2 | 174.8 | 7.284 | 2.20 | 67.41 | 85.43 |
| cuantizar+flac | 4 | 133.3 | 5.553 | 2.88 | 53.95 | 70.81 |
| cuantizar+flac | 6 | 95.7 | 3.986 | 4.01 | 41.53 | 56.26 |
| cuantizar+flac | 8 | 64.8 | 2.699 | 5.93 | 29.25 | 42.01 |
| cuantizar+flac | 10 | 42.0 | 1.750 | 9.14 | 17.15 | 28.21 |
