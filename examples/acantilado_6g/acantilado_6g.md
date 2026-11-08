# 6G en una gráfica: todo o nada contra degradación gradual

Generado por `src/acantilado_6g.py`. **Es una simulación de la idea, no 6G implementado.**

## La idea, para cualquiera

Hoy (5G) una imagen se manda en una **cadena**: primero se comprime (JPEG), después se protege con un código contra errores y por último se transmite. Cada eslabón depende del anterior. Si el ruido de la radio pasa de cierto punto, el código ya no puede corregir, el JPEG llega con errores y **no se puede abrir: se pierde entero**. Es como un archivo .zip: o abre perfecto o dice «archivo dañado». A eso se le llama **efecto acantilado**.

La idea que se estudia para 6G es **juntar la compresión y la protección en un solo paso** (codificación conjunta fuente-canal; con redes neuronales se llama DeepJSCC). La imagen se manda casi «en analógico»: lo importante con más fuerza, los detalles con menos. Con más ruido llega **más borrosa, pero llega**. Es como ver una foto a través de niebla: más niebla, menos nitidez, pero siempre se ve algo.

## El experimento

La misma imagen (512×512, grises) por un canal con ruido, con el mismo ancho de banda (0.25 usos del canal por píxel) y la misma potencia:

- **Digital (como 5G):** JPEG + un código de canal *ideal* (en el límite de Shannon, mejor que cualquiera real). Diseñado para 12 dB, le caben 16,689 bytes: JPEG con calidad 64 (16,608 B). También se prueba diseñado para 5 y 20 dB.
- **Analógico (idea de 6G, estilo SoftCast, sin red neuronal):** la imagen en frecuencias (DCT), se mandan los 64 de 256 trozos con más energía, cada uno con la fuerza que le corresponde.

| Calidad de la señal (SNR) | Digital, diseñado a 12 dB: PSNR / info. | Analógico: PSNR / info. |
|---:|---|---|
| 2 dB | 13.65 dB / 0.0 % | 26.56 dB / 26.8 % |
| 6 dB | 13.65 dB / 0.0 % | 28.87 dB / 32.0 % |
| 10 dB | 13.65 dB / 0.0 % | 30.97 dB / 37.56 % |
| 11 dB | 13.65 dB / 0.0 % | 31.31 dB / 38.6 % |
| 12 dB | 37.41 dB / 58.88 % | 31.65 dB / 39.89 % |
| 16 dB | 37.41 dB / 58.88 % | 32.76 dB / 44.92 % |
| 20 dB | 37.41 dB / 58.88 % | 33.27 dB / 48.73 % |
| 25 dB | 37.41 dB / 58.88 % | 33.54 dB / 52.36 % |
| 30 dB | 37.41 dB / 58.88 % | 33.62 dB / 54.2 % |

«Info.» = I(X;Y)/H(X): qué parte de la información de los píxeles llega al receptor.

## Qué se ve

- **El acantilado.** El digital diseñado a 12 dB entrega su JPEG completo desde 12 dB, pero a 11 dB entrega **nada** (gris, 0 % de información). Un decibel de diferencia es todo o nada.
- **La meseta.** Por encima de su diseño el digital no mejora: aunque la señal sea excelente, sigue entregando el mismo JPEG. Para aprovechar la señal buena habría que haber elegido otro diseño antes de transmitir, y adivinar mal tira la imagen.
- **La rampa.** El analógico mejora de a poco con cada decibel, sin saltos: nunca se cae del todo. A 4 dB, donde el digital no entrega nada, el analógico ya da 27.8 dB: se lee la pizarra. Tiene techo (unos 33,6 dB) porque solo caben las frecuencias más importantes: los detalles finos quedan fuera desde el principio.
- **El precio.** Justo en su punto de diseño el digital gana: a 16 dB entrega 37.41 dB contra 32.76 del analógico. Separar compresión y protección es lo óptimo (Shannon) *si se conoce la señal de antemano*. En un celular que se mueve la señal cambia todo el tiempo: el digital tiene que elegir un diseño y arriesgarse; el analógico no elige nada y funciona en todas. 6G cambia algo de calidad máxima por no caerse nunca.

## Cómo se relaciona con el resto del trabajo

- Es el mismo fenómeno que la prueba de **1 byte dañado** del bloque A: bz2, FLAC o PNG entregaban 0 % con un solo byte malo. Encadenar compresión y protección amplifica un error pequeño.
- El **compresor con pérdida para IoT** (5G, `predictivo_iot`) y las **curvas tasa-distorsión** son la otra mitad de la idea de 6G (comunicación semántica): mandar lo que importa y medir con I(X;Y) cuánto se entrega.

## Límites

- Simulación con ruido gaussiano, sin desvanecimiento ni pérdidas de paquetes. El código digital es ideal (favorece al digital: uno real necesita 1–2 dB más).
- El analógico es SoftCast (2011), no DeepJSCC: sin red neuronal. DeepJSCC aprende la transformación y gana más calidad, pero la forma de la curva (rampa sin acantilado) es la misma.
- No corre sobre la red 5G del lab: UERANSIM simula la radio sin capa física, no hay señal que modular.
