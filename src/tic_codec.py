#!/usr/bin/env python3
"""
tic_codec.py — Codificador / decodificador adaptable por tamaño de símbolo
Teoría de la Información — Ingeniería en Telemática

  k = 8, 16, 32, ..., 2048 bits por símbolo (reto: hasta 32 888 o más; cualquier múltiplo de 8)

Qué hace:
  1. Parte cualquier archivo (imagen, video, documento...) en símbolos de k bits.
  2. ANTES: mide cantidad de información, entropía, redundancia, KL frente a la
     fuente uniforme y el perfil de entropía por posición de bit.
  3. Identifica bits redundantes (posiciones constantes) y los elimina del diccionario.
  4. DURANTE: codifica por bloques midiendo H, longitud media L y KL(bloque || global).
  5. Elige de forma controlada el modo más compacto (Huffman canónico o bitstrip).
  6. DESPUÉS: decodifica, verifica SHA-256 y mide razón de compresión, eficiencia,
     entropía del flujo codificado y KL original vs reconstruido.

Uso:
  python tic_codec.py generar  estructurado prueba.bin --mb 4
  python tic_codec.py barrido  prueba.bin --extendido
  python tic_codec.py codificar prueba.bin prueba.tic -k 2048 --grafica g.png --reporte r.json
  python tic_codec.py decodificar prueba.tic salida.bin
  (opcional) --perdida n : compresión con pérdida controlada, anula n LSB de cada byte

Organización del código (POO)
──────────────────────────────
El pipeline es el mismo de siempre (segmentar → medir → codificar → escribir →
decodificar → verificar), pero cada responsabilidad vive en su propia clase en
vez de en funciones sueltas que se pasan arrays entre sí:

  Fuente              archivo → matriz de N símbolos de k bits
  Alfabeto            símbolos únicos observados, sus índices y frecuencias
  PerfilBits          P(bit=1) y entropía por posición de bit (detecta bits redundantes)
  Informacion         caja de herramientas: entropía, información mutua I(X;Y), KL, clasificación (solo staticmethods)
  MetricasAntes       resultado del análisis "antes" (dataclass, serializable a dict/JSON)
  MascaraRedundancia  separa/junta las posiciones de bit constantes vs. variables
  HuffmanCanonico     construcción, empaquetado y decodificación del código de Huffman
  CabeceraTIC         la cabecera JSON autocontenida del formato .tic
  ReporteBloque       una fila de las métricas "durante" (una por bloque)
  MetricasDespues     resultado de decodificar y verificar (dataclass)
  ReporteCodificacion junta antes/durante/después: imprime, grafica y guarda el JSON
  CodecTIC            orquesta todo lo anterior: codificar(), decodificar(), barrido()
  GeneradorFuentes    fuentes sintéticas de prueba (uniforme / no_uniforme / estructurado)

Ninguna clase modela un símbolo individual como objeto: con archivos de millones
de símbolos eso mataría el rendimiento. Las clases organizan el pipeline; el
cómputo pesado sigue vectorizado con NumPy exactamente igual que en la versión
original, función por función.

Glosario de nombres cortos que se repiten en todo el archivo
────────────────────────────────────────────────────────────
  k      bits por símbolo (8, 16, ..., 2048...)
  B      bytes por símbolo = k // 8
  n / N  cantidad de símbolos (filas) en que quedó partido el archivo
  U      cantidad de símbolos DISTINTOS observados (tamaño del alfabeto)
  H      entropía en bits por símbolo
  L      longitud media del código Huffman en bits por símbolo
  p, q   probabilidades (arrays o números entre 0 y 1)
  cnt    "count": cuántas veces aparece algo (frecuencia absoluta)
  idx    índices (posiciones dentro de un array)
  s      "start": primera fila del trozo que se está procesando en un ciclo
  paso   tamaño del trozo que se procesa por vuelta (para no usar toda la RAM)
  raw    los bytes crudos del archivo tal cual se leyeron
  rec    los bytes "reconstruidos" tras decodificar
  carry  bits sobrantes (menos de 8) que quedan de una vuelta y pasan a la siguiente

Modismos de Python/NumPy que aparecen mucho
───────────────────────────────────────────
  -(-a // b)     división entera REDONDEANDO HACIA ARRIBA (techo). `//` redondea
                 hacia abajo; negando antes y después se obtiene el techo.
                 Ej.: -(-10 // 3) = -(-4) = 4   (10/3 = 3,33 → 4).
  1 << m         2 elevado a la m (desplazar un 1 m posiciones a la izquierda).
  x >> m & 1     el bit número m de x contando desde la derecha (0 = el menos significativo).
  a[s:s + paso]  "rebanada": elementos desde s hasta s+paso-1 (si se pasa del final, se corta solo).
  a[b::8]        elementos b, b+8, b+16, ... (empieza en b y salta de 8 en 8).
  a[::-1]        el array invertido.
  for s in range(0, n, paso)
                 s toma los valores 0, paso, 2·paso, ... mientras sea < n.
                 Es la forma de recorrer un array grande "por trozos".
"""
from __future__ import annotations

import argparse, hashlib, heapq, json, math, struct, sys, time
from dataclasses import dataclass, asdict
import numpy as np

# La consola de Windows usa cp1252 por defecto, que no tiene los caracteres
# Unicode que se imprimen (─, ‖, …). Sin esto, cualquier comando falla con
# UnicodeEncodeError antes de mostrar resultados.
if sys.platform == "win32":
    # _s recorre las dos salidas de consola: la normal (stdout) y la de errores (stderr).
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")

# Valores de k del enunciado (K_BASE) y valores extra para el "reto" (K_EXT).
K_BASE = [8, 16, 32, 64, 128, 256, 512, 1024, 2048]
K_EXT = [4096, 8192, 16384, 32768, 32888]


# ═══════════════════════════ fuente y alfabeto ═══════════════════════════
@dataclass
class Fuente:
    """Bytes crudos de un archivo, reinterpretados como una matriz de N
    símbolos de k bits (k/8 bytes) cada uno. Si el archivo no es múltiplo
    exacto de k/8 bytes, se rellena con ceros al final."""
    k: int
    filas: np.ndarray       # (N, k//8) uint8
    longitud_original: int  # bytes reales del archivo, antes del relleno

    @classmethod
    def desde_bytes(cls, datos: np.ndarray, k: int, longitud_original: int | None = None) -> "Fuente":
        # `k % 8` es distinto de 0 si k no es múltiplo de 8 → en Python eso cuenta como True.
        if k % 8 or k < 8:
            raise ValueError("k debe ser múltiplo de 8 (8, 16, ..., 32888...)")
        B = k // 8                     # bytes por símbolo
        n = -(-len(datos) // B)        # cantidad de símbolos = techo(bytes / B)
        buf = np.zeros(n * B, dtype=np.uint8)  # buffer del tamaño exacto n·B, lleno de ceros
        buf[:len(datos)] = datos       # copia los datos al inicio; el final queda en 0 (relleno)
        filas = buf.reshape(n, B)      # misma memoria vista como tabla: n filas de B bytes
        # `A if cond else B` es el "if de una línea" de Python (operador ternario).
        return cls(k=k, filas=filas, longitud_original=len(datos) if longitud_original is None else longitud_original)

    @classmethod
    def desde_archivo(cls, ruta: str, k: int) -> "Fuente":
        # np.fromfile lee el archivo completo como un array de bytes (uint8 = 0..255).
        return cls.desde_bytes(np.fromfile(ruta, dtype=np.uint8), k)

    @property
    def n(self) -> int:
        # @property permite escribir `fuente.n` (sin paréntesis) como si fuera un atributo.
        return len(self.filas)


@dataclass
class Alfabeto:
    """Símbolos únicos observados en una Fuente: sus valores, a qué símbolo
    corresponde cada fila original y cuántas veces aparece cada uno."""
    simbolos: np.ndarray     # (U, B) uint8
    indices: np.ndarray      # (N,) int64 — índice en `simbolos` de cada fila
    frecuencias: np.ndarray  # (U,) int64

    @classmethod
    def desde_filas(cls, filas: np.ndarray) -> "Alfabeto":
        B = filas.shape[1]  # bytes por símbolo (número de columnas)
        # Truco: se "ve" cada fila de B bytes como UN solo valor opaco de B bytes
        # (tipo np.void). Así np.unique puede comparar filas completas de una vez,
        # en vez de tener que comparar byte por byte con un ciclo.
        v = np.ascontiguousarray(filas).view(np.dtype((np.void, B))).ravel()
        # np.unique devuelve tres cosas a la vez:
        #   u   → los valores distintos, ordenados (el alfabeto)
        #   inv → para cada fila original, la posición de su valor dentro de u
        #   cnt → cuántas veces aparece cada valor de u
        u, inv, cnt = np.unique(v, return_inverse=True, return_counts=True)
        # u.view(np.uint8).reshape(-1, B) deshace el truco: vuelve a bytes normales,
        # en una tabla de B columnas (el -1 significa "las filas que hagan falta").
        return cls(simbolos=u.view(np.uint8).reshape(-1, B),
                    indices=inv.ravel().astype(np.int64),
                    frecuencias=cnt.astype(np.int64))

    @property
    def U(self) -> int:
        return len(self.frecuencias)

    def probabilidades(self) -> np.ndarray:
        # Frecuencia relativa: cada cuenta dividida por el total (NumPy lo hace elemento a elemento).
        return self.frecuencias / self.frecuencias.sum()

    def a_diccionario(self) -> dict:
        """Símbolo (bytes) → cuenta. Usado para comparar distribuciones con D_KL."""
        # "Comprensión de diccionario": zip recorre en paralelo cada símbolo s y su cuenta c,
        # y por cada pareja se crea la entrada  bytes(s) → int(c).
        # Equivale a:  d = {};  for s, c in zip(...): d[bytes(s)] = int(c)
        return {bytes(s): int(c) for s, c in zip(self.simbolos, self.frecuencias)}


@dataclass
class PerfilBits:
    """Para cada una de las k posiciones de bit del símbolo (MSB primero):
    P(bit=1) observada y su entropía binaria h(p). Una posición con h(p)=0
    es una posición constante: redundancia determinista, no estadística."""
    p_uno: np.ndarray             # (k,) float
    entropia_por_bit: np.ndarray  # (k,) float

    @classmethod
    def desde_filas(cls, filas: np.ndarray) -> "PerfilBits":
        n, B = filas.shape  # n símbolos, B bytes cada uno
        # ones[i] = cuántas veces la posición de bit i (de las k = B·8) vale 1.
        ones = np.zeros(B * 8, dtype=np.int64)
        # Se procesan ~16 M bytes por vuelta (1 << 24 = 16 777 216) para no llenar la RAM.
        paso = max(1, (1 << 24) // B)
        # s = 0, paso, 2·paso, ...  →  r es el trozo de filas [s, s+paso).
        for s in range(0, n, paso):
            r = filas[s:s + paso]
            # b recorre las 8 posiciones dentro de cada byte (0 = bit más significativo).
            for b in range(8):
                # (r >> (7 - b)) & 1  extrae el bit b de TODOS los bytes del trozo a la vez.
                # .sum(axis=0) suma por columna → cuántos unos hay en cada byte del símbolo.
                # ones[b::8] son las posiciones b, b+8, b+16, ... = "el bit b de cada byte".
                ones[b::8] += ((r >> (7 - b)) & 1).sum(axis=0, dtype=np.int64)
        p_uno = ones / n  # proporción de unos por posición = P(bit = 1)
        return cls(p_uno=p_uno, entropia_por_bit=Informacion.entropia_binaria(p_uno))

    @property
    def constantes(self) -> np.ndarray:
        # Array de True/False: True donde el bit SIEMPRE fue 0 (p=0) o SIEMPRE fue 1 (p=1).
        # `|` es el "o" elemento a elemento entre arrays booleanos.
        return (self.p_uno == 0) | (self.p_uno == 1)


# ═══════════════════════════ teoría de la información ═══════════════════════════
class Informacion:
    """Caja de herramientas de teoría de la información: entropía, entropía
    binaria, divergencia KL con suavizado y la clasificación uniforme / no
    uniforme de una fuente. Sin estado — solo funciones agrupadas por tema."""

    @staticmethod
    def entropia(frecuencias: np.ndarray) -> float:
        # H = −Σ p·log2(p), calculado sobre todo el array de una sola vez (sin ciclo).
        p = frecuencias / frecuencias.sum()
        return float(-(p * np.log2(p)).sum())

    @staticmethod
    def informacion_mutua(indices_x: np.ndarray, indices_y: np.ndarray) -> float:
        """I(X;Y) en bits entre dos flujos de símbolos emparejados fila a fila
        (p. ej. fuente original vs. reconstruida tras una codificación con
        pérdida). Construye la distribución conjunta de forma vectorizada -sin
        iterar símbolo por símbolo, igual que el resto de la clase- y devuelve
        Σ p(x,y) log2(p(x,y) / (p(x)·p(y)))."""
        x = np.asarray(indices_x, dtype=np.int64)  # símbolo original de cada posición
        y = np.asarray(indices_y, dtype=np.int64)  # símbolo reconstruido en la misma posición
        n = len(x)
        # Ux, Uy = cantidad de símbolos distintos posibles en X y en Y.
        Ux, Uy = int(x.max()) + 1, int(y.max()) + 1
        # Cada pareja (x, y) se convierte en UN número único: x·Uy + y
        # (como juntar "fila" y "columna" en una sola casilla de una tabla Ux × Uy).
        clave = x * Uy + y
        # Contar cuántas veces aparece cada pareja = distribución conjunta sin ciclos.
        claves_unicas, cuentas = np.unique(clave, return_counts=True)
        # Recuperar x e y de cada clave: división entera (//) da x, el residuo (%) da y.
        xu, yu = claves_unicas // Uy, claves_unicas % Uy
        # np.bincount cuenta cuántas veces aparece cada entero 0, 1, 2, ... → marginales p(x), p(y).
        px = np.bincount(x, minlength=Ux) / n
        py = np.bincount(y, minlength=Uy) / n
        pxy = cuentas / n  # p(x, y) de cada pareja observada
        # px[xu] toma, para cada pareja, el p(x) de su x (indexar un array con otro array).
        return float((pxy * np.log2(pxy / (px[xu] * py[yu]))).sum())

    @staticmethod
    def entropia_binaria(p: np.ndarray) -> np.ndarray:
        # h(p) = −p·log2(p) − (1−p)·log2(1−p). Cuando p = 0 o p = 1 sale log2(0) → NaN;
        # `with np.errstate(...)` silencia esos avisos solo dentro de este bloque,
        # y np.nan_to_num convierte los NaN en 0 (que es el valor correcto de h(0) y h(1)).
        with np.errstate(divide="ignore", invalid="ignore"):
            h = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
        return np.nan_to_num(h)

    @staticmethod
    def kl_suavizada(cp: dict, cq: dict, alfa: float = 0.5) -> float:
        """D(P‖Q) en bits, con suavizado aditivo sobre la unión de soportes (dict símbolo→cuenta)."""
        # cp, cq: diccionarios símbolo → cuenta de las distribuciones P y Q.
        # S = todos los símbolos que aparecen en P o en Q (`|` entre sets = unión).
        S = set(cp) | set(cq)
        # Np, Nq: totales de cada distribución, sumando también el suavizado alfa por símbolo.
        Np, Nq = sum(cp.values()) + alfa * len(S), sum(cq.values()) + alfa * len(S)
        d = 0.0
        for s in S:
            # dict.get(s, 0) devuelve la cuenta de s, o 0 si ese símbolo no está.
            # Sumar alfa evita probabilidades 0 (que harían log2(p/0) = infinito).
            p = (cp.get(s, 0) + alfa) / Np
            q = (cq.get(s, 0) + alfa) / Nq
            d += p * math.log2(p / q)
        return d

    @staticmethod
    def clasificar(H: float, k: int, U: int, n: int) -> str:
        # n / U = cuántas veces se repite en promedio cada símbolo. Si es < 2, casi
        # no hay repeticiones y la entropía medida no es confiable.
        if n / U < 2:
            return "casi todos los símbolos son únicos: estimación limitada por la muestra (H≈log2 N)"
        r = H / k  # entropía por bit: 1 = totalmente uniforme, cerca de 0 = muy redundante
        if r > 0.97:
            return "uniforme (sin redundancia aprovechable)"
        if r > 0.75:
            return "levemente no uniforme"
        return "no uniforme (alta redundancia)"


@dataclass
class MetricasAntes:
    """Todo lo que se puede medir de la fuente ANTES de elegir cómo comprimirla."""
    k_bits: int
    N_simbolos: int
    alfabeto_observado_U: int
    H_bits_por_simbolo: float
    H_por_bit: float
    H_max_teorica_k: int
    H_max_observable_log2U: float
    cota_muestral_log2N: float
    informacion_total_bits: float
    autoinformacion_min: float
    autoinformacion_max: float
    redundancia_R: float
    KL_P_vs_uniforme_k: float
    KL_P_vs_uniforme_observada: float
    bits_constantes_redundantes: int
    bits_variables: int
    suma_entropia_por_bit: float
    informacion_mutua_entre_bits: float
    fiabilidad_N_sobre_U: float
    estructura: str
    tras_cuantizar: dict | None = None

    @classmethod
    def calcular(cls, fuente: Fuente, alfabeto: Alfabeto, perfil: PerfilBits) -> "MetricasAntes":
        # Asignación múltiple: n, k y U reciben cada uno el valor correspondiente de la derecha.
        n, k, U = fuente.n, fuente.k, alfabeto.U
        H = Informacion.entropia(alfabeto.frecuencias)
        info = -np.log2(alfabeto.probabilidades())  # autoinformación I(x) = −log2 p(x) de cada símbolo
        const = perfil.constantes                   # True en las posiciones de bit que nunca cambian
        return cls(
            k_bits=k, N_simbolos=n, alfabeto_observado_U=U,
            H_bits_por_simbolo=H, H_por_bit=H / k,
            H_max_teorica_k=k, H_max_observable_log2U=math.log2(U) if U > 1 else 0.0,
            cota_muestral_log2N=math.log2(n) if n > 1 else 0.0,
            informacion_total_bits=H * n,
            autoinformacion_min=float(info.min()), autoinformacion_max=float(info.max()),
            redundancia_R=1 - H / k,
            KL_P_vs_uniforme_k=k - H,
            KL_P_vs_uniforme_observada=(math.log2(U) - H) if U > 1 else 0.0,
            # const.sum() cuenta los True (True vale 1, False vale 0).
            bits_constantes_redundantes=int(const.sum()),
            # `~` invierte un array booleano: los True pasan a False y viceversa.
            bits_variables=int((~const).sum()),
            suma_entropia_por_bit=float(perfil.entropia_por_bit.sum()),
            informacion_mutua_entre_bits=float(perfil.entropia_por_bit.sum() - H),
            fiabilidad_N_sobre_U=n / U,
            estructura=Informacion.clasificar(H, k, U, n),
        )

    def a_dict(self) -> dict:
        d = {
            "k_bits": self.k_bits, "N_simbolos": self.N_simbolos,
            "alfabeto_observado_U": self.alfabeto_observado_U,
            "H_bits_por_simbolo": self.H_bits_por_simbolo, "H_por_bit": self.H_por_bit,
            "H_max_teorica_k": self.H_max_teorica_k,
            "H_max_observable_log2U": self.H_max_observable_log2U,
            "cota_muestral_log2N": self.cota_muestral_log2N,
            "informacion_total_bits": self.informacion_total_bits,
            "autoinformacion_min_max": [self.autoinformacion_min, self.autoinformacion_max],
            "redundancia_R": self.redundancia_R,
            "KL_P_vs_uniforme_k": self.KL_P_vs_uniforme_k,
            "KL_P_vs_uniforme_observada": self.KL_P_vs_uniforme_observada,
            "bits_constantes_redundantes": self.bits_constantes_redundantes,
            "bits_variables": self.bits_variables,
            "suma_entropia_por_bit": self.suma_entropia_por_bit,
            "informacion_mutua_entre_bits": self.informacion_mutua_entre_bits,
            "fiabilidad_N_sobre_U": self.fiabilidad_N_sobre_U,
            "estructura": self.estructura,
        }
        # Solo se agrega si se usó --perdida (si no, el campo queda en None y se omite).
        if self.tras_cuantizar is not None:
            d["tras_cuantizar"] = self.tras_cuantizar
        return d


# ═══════════════════════════ redundancia de bits ═══════════════════════════
@dataclass
class MascaraRedundancia:
    """Separa, para un símbolo de k bits, qué posiciones varían de una fuente
    a otra y cuáles son siempre iguales (redundancia determinista). Las
    constantes se eliminan del diccionario y del modo bitstrip sin afectar
    la entropía del símbolo — solo el costo de almacenar el alfabeto."""
    variables: np.ndarray            # (k,) bool — True si la posición varía
    valores_constantes: np.ndarray   # (k,) uint8 — valor cuando NO varía

    @classmethod
    def desde_perfil(cls, perfil: PerfilBits) -> "MascaraRedundancia":
        # Variables = las que NO son constantes. El valor fijo de una constante es 1
        # si P(bit=1) == 1, y 0 en cualquier otro caso (astype(np.uint8) pasa True/False a 1/0).
        return cls(variables=~perfil.constantes,
                    valores_constantes=(perfil.p_uno == 1).astype(np.uint8))

    @property
    def indices_variables(self) -> np.ndarray:
        # Posiciones (0..k-1) donde `variables` es True.
        return np.flatnonzero(self.variables)

    @property
    def num_variables(self) -> int:
        return int(self.variables.sum())

    def extraer(self, filas: np.ndarray) -> bytes:
        """Empaqueta sólo las posiciones de bit variables de cada fila."""
        var_idx = self.indices_variables  # qué columnas de bits se conservan
        k = filas.shape[1] * 8            # bits por fila
        paso = max(1, (1 << 25) // k)     # filas por trozo (~32 M bits por vuelta)
        # out = lista de pedazos de bytes ya listos; carry = bits sobrantes de la vuelta anterior.
        out, carry = [], np.zeros(0, np.uint8)
        for s in range(0, len(filas), paso):
            # 1) unpackbits: cada byte → 8 bits (0/1), así cada fila pasa a tener k columnas.
            # 2) [:, var_idx]: de TODAS las filas (:) se quedan solo las columnas variables.
            # 3) ravel(): aplana la tabla a una sola fila larga de bits.
            bits = np.unpackbits(filas[s:s + paso], axis=1)[:, var_idx].ravel()
            bits = np.concatenate([carry, bits])  # pega delante lo que sobró la vuelta pasada
            # m = la mayor cantidad de bits que es múltiplo de 8 (solo se empaquetan bytes completos).
            m = len(bits) // 8 * 8
            out.append(np.packbits(bits[:m]).tobytes())  # 8 bits → 1 byte
            carry = bits[m:]                             # los < 8 bits restantes esperan a la siguiente vuelta
        # Al final puede quedar un byte incompleto: packbits lo rellena con ceros a la derecha.
        if len(carry):
            out.append(np.packbits(carry).tobytes())
        return b"".join(out)  # une todos los pedazos en un solo bloque de bytes

    def insertar(self, empacado: bytes, n: int, k: int) -> np.ndarray:
        """Reconstruye n filas de k bits a partir de los bits variables empacados
        y los valores constantes guardados en la máscara."""
        var_idx = self.indices_variables
        v = len(var_idx)  # bits variables por fila
        allbits = np.unpackbits(np.frombuffer(empacado, np.uint8))  # todos los bits guardados, en fila
        filas = np.empty((n, k // 8), np.uint8)                     # resultado (se llena por trozos)
        paso = max(1, (1 << 25) // k)
        for s in range(0, n, paso):
            e = min(n, s + paso)  # "end": fila final (exclusiva) de este trozo
            # np.tile repite el patrón de valores constantes para cada una de las (e − s) filas:
            # así las posiciones constantes ya quedan con su valor correcto.
            full = np.tile(self.valores_constantes, (e - s, 1))
            if v:
                # Cada fila usó v bits: las filas s..e-1 ocupan los bits [s·v, e·v).
                # reshape los reparte en (e − s) filas de v columnas y se escriben
                # justo en las columnas variables.
                full[:, var_idx] = allbits[s * v:e * v].reshape(e - s, v)
            filas[s:e] = np.packbits(full, axis=1)  # vuelve a juntar cada 8 bits en un byte
        return filas

    def a_hex(self) -> tuple[str, str]:
        # Guarda la máscara y los valores constantes como texto hexadecimal (para la cabecera JSON).
        return (np.packbits(self.variables).tobytes().hex(),
                np.packbits(self.valores_constantes).tobytes().hex())

    @classmethod
    def desde_hex(cls, k: int, mascara_hex: str, valores_hex: str) -> "MascaraRedundancia":
        # Proceso inverso de a_hex. [:k] descarta los bits de relleno que agregó packbits.
        variables = np.unpackbits(np.frombuffer(bytes.fromhex(mascara_hex), np.uint8))[:k].astype(bool)
        valores = np.unpackbits(np.frombuffer(bytes.fromhex(valores_hex), np.uint8))[:k]
        return cls(variables=variables, valores_constantes=valores)


# ═══════════════════════════ Huffman canónico ═══════════════════════════
class HuffmanCanonico:
    """Código de Huffman canónico: basta con transmitir las longitudes de
    código (no el árbol) y el receptor reconstruye los mismos códigos, lo
    que además permite decodificar con tablas en vez de recorrer el árbol."""

    def __init__(self, longitudes: np.ndarray):
        self.longitudes = np.asarray(longitudes, dtype=np.int64)
        self.codigos, self.orden = self._codigos_canonicos(self.longitudes)

    @classmethod
    def desde_frecuencias(cls, frecuencias: np.ndarray) -> "HuffmanCanonico":
        return cls(cls._construir_longitudes(frecuencias))

    @staticmethod
    def _construir_longitudes(cnt) -> np.ndarray:
        # cnt[i] = frecuencia del símbolo i. Devuelve la longitud en bits del código de cada símbolo.
        U = len(cnt)
        if U == 1:
            return np.array([1], np.int64)  # un solo símbolo: basta 1 bit
        # Nodos del árbol: 0..U-1 son las hojas (símbolos); U..2U-2 son los nodos internos que se crean.
        # heap = cola de prioridad de parejas (frecuencia, nodo). `enumerate` da (posición, valor).
        heap = [(int(c), i) for i, c in enumerate(cnt)]
        heapq.heapify(heap)          # la ordena para que heappop saque siempre la menor frecuencia
        parent = [0] * (2 * U - 1)   # parent[nodo] = nodo padre (lista de 2U−1 ceros)
        nxt = U                      # id del siguiente nodo interno a crear
        # Algoritmo de Huffman: mientras quede más de un nodo, unir los dos menos frecuentes.
        while len(heap) > 1:
            c1, a = heapq.heappop(heap)  # el menos frecuente   (frecuencia c1, nodo a)
            c2, b = heapq.heappop(heap)  # el segundo menos frecuente
            parent[a] = parent[b] = nxt  # ambos pasan a ser hijos del nodo nuevo
            heapq.heappush(heap, (c1 + c2, nxt))
            nxt += 1
        # La raíz es el último nodo creado (2U−2) y tiene profundidad 0.
        # Se recorre desde 2U−3 hacia atrás hasta 0 (range con paso −1): como un padre
        # siempre se creó después que sus hijos, su profundidad ya está calculada.
        depth = [0] * (2 * U - 1)
        for node in range(2 * U - 3, -1, -1):
            depth[node] = depth[parent[node]] + 1
        # La profundidad de cada hoja es la longitud de su código. depth[:U] = solo las hojas.
        return np.array(depth[:U], np.int64)

    @staticmethod
    def _codigos_canonicos(lens):
        # lens[i] = longitud del código del símbolo i.
        # lexsort ordena los símbolos por longitud (y, si empatan, por su número):
        # `order` es la lista de símbolos del código más corto al más largo.
        order = np.lexsort((np.arange(len(lens)), lens))
        codes = [0] * len(lens)
        # code = siguiente código disponible; prev = longitud del código anterior.
        code, prev = 0, int(lens[order[0]])
        for i in order.tolist():
            l = int(lens[i])
            # Si este código es más largo que el anterior, se agregan ceros a la derecha
            # (desplazar a la izquierda l − prev bits). Así ningún código es prefijo de otro.
            code <<= (l - prev)
            codes[i] = code
            code += 1  # el siguiente símbolo de la misma longitud recibe el código consecutivo
            prev = l
        return np.array(codes, np.uint64), order

    @property
    def longitud_maxima(self) -> int:
        return int(self.longitudes.max())

    def longitud_media(self, frecuencias: np.ndarray) -> float:
        # L = Σ frecuencia·longitud / total  (promedio de bits por símbolo, ponderado).
        n = frecuencias.sum()
        return float((frecuencias * self.longitudes).sum() / n)

    def kraft(self) -> float:
        # Desigualdad de Kraft: Σ 2^(−longitud) ≤ 1 en todo código prefijo (= 1 si es completo).
        return float(np.sum(2.0 ** -self.longitudes))

    def empaquetar(self, indices: np.ndarray) -> bytes:
        # Escribe, uno detrás de otro, los códigos Huffman de todos los símbolos del archivo.
        # indices[j] = qué símbolo del alfabeto aparece en la posición j.
        out, carry = [], np.zeros(0, np.uint8)
        paso = 1 << 20  # ~1 millón de símbolos por vuelta
        for s in range(0, len(indices), paso):
            idx = indices[s:s + paso]
            # c = código de cada símbolo del trozo, l = cuántos bits mide ese código.
            c, l = self.codigos[idx], self.longitudes[idx]
            # Truco para "desplegar" todos los códigos a bits SIN un ciclo por símbolo.
            # Ejemplo con 2 símbolos: l = [3, 2]  (códigos de 3 y 2 bits → 5 bits en total).
            #   rep  = [0, 0, 0, 1, 1]   a qué símbolo pertenece cada uno de los 5 bits
            #   offs = [0, 3]            en qué bit empieza cada símbolo (suma acumulada − l)
            #   j    = [0, 1, 2, 0, 1]   número de bit DENTRO de su código
            #   sh   = [2, 1, 0, 1, 0]   cuánto desplazar el código para leer ese bit (MSB primero)
            rep = np.repeat(np.arange(len(idx)), l)
            offs = np.cumsum(l) - l
            j = np.arange(int(l.sum())) - offs[rep]
            sh = (l[rep] - 1 - j).astype(np.uint64)
            # Se extrae cada bit: (código >> desplazamiento) & 1.
            bits = ((c[rep] >> sh) & np.uint64(1)).astype(np.uint8)
            # Igual que en MascaraRedundancia.extraer: solo se empaquetan bytes completos
            # y los bits que sobran (carry) pasan a la siguiente vuelta.
            bits = np.concatenate([carry, bits])
            m = len(bits) // 8 * 8
            out.append(np.packbits(bits[:m]).tobytes())
            carry = bits[m:]
        if len(carry):
            out.append(np.packbits(carry).tobytes())
        return b"".join(out)

    def decodificar(self, payload: bytes, n: int) -> np.ndarray:
        # Lee n símbolos del flujo de bits `payload`. Es el único ciclo símbolo por símbolo
        # del programa (Huffman es de longitud variable: no se sabe dónde empieza el
        # siguiente código hasta haber leído el actual), así que usa una tabla para ir rápido.
        lens = self.longitudes
        maxlen = self.longitud_maxima
        # T = bits que se miran de una vez en la tabla rápida (máx. 16 → tabla de 65 536 casillas).
        T = min(maxlen, 16)
        order = np.lexsort((np.arange(len(lens)), lens)).tolist()  # mismo orden canónico que al codificar
        # Tabla rápida: al mirar los próximos T bits (número `peek`):
        #   tsym[peek] = qué símbolo es,  tlen[peek] = cuántos bits mide su código (0 = no cabe en T).
        tsym, tlen = [0] * (1 << T), [0] * (1 << T)
        # Para códigos más largos que T, por cada longitud l se guarda:
        #   first_code[l] = primer código de esa longitud, first_rank[l] = su posición en `order`,
        #   count[l] = cuántos códigos tienen esa longitud.
        first_code, first_rank, count = [0] * (maxlen + 1), [0] * (maxlen + 1), [0] * (maxlen + 1)
        # Se regeneran los códigos canónicos igual que en _codigos_canonicos.
        # enumerate da r = posición en el orden (0, 1, 2...) e i = el símbolo.
        code, prev = 0, int(lens[order[0]])
        for r, i in enumerate(order):
            l = int(lens[i])
            code <<= (l - prev)
            if count[l] == 0:
                first_code[l], first_rank[l] = code, r
            count[l] += 1
            if l <= T:
                # Un código de l bits corresponde a TODAS las ventanas de T bits que empiezan por él:
                # desde code·2^(T−l) hasta (code+1)·2^(T−l) − 1. Se llena todo ese rango de la tabla.
                a, b = code << (T - l), (code + 1) << (T - l)
                tsym[a:b] = [i] * (b - a)
                tlen[a:b] = [l] * (b - a)
            code += 1
            prev = l
        # Estado de la lectura:
        #   data = bytes a leer, L = cuántos bytes hay, pos = siguiente byte a leer,
        #   acc  = "acumulador" con los bits ya leídos y aún no usados, nb = cuántos bits tiene acc.
        data, L, pos, acc, nb = payload, len(payload), 0, 0, 0
        mask = (1 << T) - 1  # T unos seguidos: sirve para quedarse con los últimos T bits
        out = [0] * n
        for i in range(n):
            # Rellenar el acumulador con bytes nuevos hasta tener al menos maxlen bits.
            # (En Python `;` permite escribir varias instrucciones en la misma línea.)
            while nb < maxlen and pos < L:
                acc = (acc << 8) | data[pos]; pos += 1; nb += 8
            # peek = los próximos T bits (si quedan menos de T, se completan con ceros a la derecha).
            peek = ((acc >> (nb - T)) if nb >= T else (acc << (T - nb))) & mask
            l = tlen[peek]
            if l:
                # Caso rápido: el código cabe en T bits → la tabla da el símbolo directamente.
                # Se "consumen" l bits: nb baja y acc se queda solo con los bits no usados.
                out[i] = tsym[peek]; nb -= l; acc &= (1 << nb) - 1
                continue  # pasa al siguiente símbolo
            # Caso lento: el código mide más de T bits. Se prueba cada longitud l > T:
            # si los próximos l bits caen dentro del rango de códigos de esa longitud, es ese.
            for l in range(T + 1, maxlen + 1):
                c = (acc >> (nb - l)) if nb >= l else (acc << (l - nb))
                d = c - first_code[l]  # posición del código dentro de los de longitud l
                if 0 <= d < count[l]:
                    out[i] = order[first_rank[l] + d]; nb -= l; acc &= (1 << nb) - 1
                    break
            # `for ... else`: el bloque `else` de un for solo se ejecuta si el ciclo terminó
            # SIN hacer `break`, es decir, si ninguna longitud coincidió → datos dañados.
            else:
                raise ValueError("flujo Huffman corrupto")
        return np.array(out, np.int64)


# ═══════════════════════════ formato .tic ═══════════════════════════
@dataclass
class CabeceraTIC:
    """La cabecera JSON autocontenida del archivo .tic: todo lo que necesita
    el decodificador, sin parámetros externos."""
    k: int                 # bits por símbolo
    orig_len: int          # bytes del archivo original (para quitar el relleno al decodificar)
    n: int                 # cantidad de símbolos
    U: int                 # tamaño del alfabeto
    modo: str              # "huffman" o "bitstrip"
    perdida: int           # bits bajos anulados por byte (0 = sin pérdida)
    mascara_var: str       # hex: qué posiciones de bit varían
    valores_const: str     # hex: valor de las posiciones constantes
    sha256: str            # huella de los datos codificados, para verificar
    secciones: list[int]   # tamaño en bytes de las 3 secciones que siguen a la cabecera

    def a_json(self) -> bytes:
        # asdict convierte la dataclass en diccionario; json.dumps lo pasa a texto; encode a bytes.
        return json.dumps(asdict(self)).encode()

    @classmethod
    def desde_json(cls, blob: bytes) -> "CabeceraTIC":
        # `**dict` pasa cada clave del diccionario como argumento con nombre: cls(k=..., n=..., ...).
        return cls(**json.loads(blob))


# ═══════════════════════════ reportes ═══════════════════════════
@dataclass
class ReporteBloque:
    """Métricas de un bloque durante la codificación: entropía, longitud
    media de Huffman y KL frente a la distribución global del archivo."""
    bloque: int
    H_bloque: float
    L_bloque: float
    KL_bloque_vs_global: float
    razon_acumulada: float

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class MetricasDespues:
    """Resultado de escribir el .tic, decodificarlo y verificarlo."""
    modo_elegido: str
    tamano_original_B: int
    tamano_codificado_B: int
    razon_compresion: float
    ahorro_pct: float
    bits_por_simbolo_real: float
    L_media_huffman: float
    eficiencia_H_sobre_L: float
    redundancia_codigo_L_menos_H: float
    kraft_suma: float
    long_max_codigo: int
    tamano_diccionario_B: int
    tamano_estimado_huffman_B: float
    tamano_estimado_bitstrip_B: int
    H_flujo_codificado_bits_por_byte: float
    KL_flujo_vs_uniforme_256: float
    informacion_mutua_XY: float
    verificacion_sha256: bool
    sin_perdida_exacta: bool
    tiempo_codificacion_s: float
    tiempo_decodificacion_s: float
    KL_original_vs_reconstruido: float | None = None
    MSE_por_byte: float | None = None
    PSNR_dB: float | None = None

    def a_dict(self) -> dict:
        d = {
            "modo_elegido": self.modo_elegido,
            "tamano_original_B": self.tamano_original_B,
            "tamano_codificado_B": self.tamano_codificado_B,
            "razon_compresion": self.razon_compresion,
            "ahorro_%": self.ahorro_pct,
            "bits_por_simbolo_real": self.bits_por_simbolo_real,
            "L_media_huffman": self.L_media_huffman,
            "eficiencia_H_sobre_L": self.eficiencia_H_sobre_L,
            "redundancia_codigo_L_menos_H": self.redundancia_codigo_L_menos_H,
            "kraft_suma": self.kraft_suma,
            "long_max_codigo": self.long_max_codigo,
            "tamano_diccionario_B": self.tamano_diccionario_B,
            "tamano_estimado_huffman_B": self.tamano_estimado_huffman_B,
            "tamano_estimado_bitstrip_B": self.tamano_estimado_bitstrip_B,
            "H_flujo_codificado_bits_por_byte": self.H_flujo_codificado_bits_por_byte,
            "KL_flujo_vs_uniforme_256": self.KL_flujo_vs_uniforme_256,
            "I_XY": self.informacion_mutua_XY,
            "verificacion_sha256": self.verificacion_sha256,
            "sin_perdida_exacta": self.sin_perdida_exacta,
            "tiempo_codificacion_s": self.tiempo_codificacion_s,
            "tiempo_decodificacion_s": self.tiempo_decodificacion_s,
            "KL_original_vs_reconstruido": self.KL_original_vs_reconstruido,
        }
        # MSE y PSNR solo existen con pérdida (sin pérdida el error es 0 por definición).
        if self.MSE_por_byte is not None:
            d["MSE_por_byte"] = self.MSE_por_byte
            d["PSNR_dB"] = self.PSNR_dB
        return d


@dataclass
class ReporteCodificacion:
    """Junta las tres etapas de una corrida — antes / durante / después — y
    sabe imprimirse, graficarse y guardarse como JSON."""
    antes: MetricasAntes
    durante: list[ReporteBloque]
    despues: MetricasDespues

    def a_dict(self) -> dict:
        return {
            "antes": self.antes.a_dict(),
            # Comprensión de lista: aplica a_dict() a cada bloque b y junta los resultados en una lista.
            "durante": [b.a_dict() for b in self.durante],
            "despues": self.despues.a_dict(),
        }

    def guardar_json(self, ruta: str):
        # `with open(...)` abre el archivo y lo cierra solo al salir del bloque, aunque haya error.
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(self.a_dict(), f, indent=2, ensure_ascii=False)

    def imprimir(self, nombre: str):
        # `f` es una función de una línea (lambda) que da formato a un valor según su tipo.
        # Leída como if/elif normal equivale a:
        #   if es bool:   "sí" / "no"
        #   elif float:   con 4 decimales y separador de miles   (ej. 1,234.5678)
        #   elif int:     con separador de miles                 (ej. 1,234)
        #   else:         el valor convertido a texto
        # (se revisa bool antes que int porque en Python True/False también cuentan como int)
        f = lambda x: ("sí" if x else "no") if isinstance(x, bool) else f"{x:,.4f}" if isinstance(x, float) else f"{x:,}" if isinstance(x, int) else str(x)
        a = self.antes.a_dict()
        print(f"\n══════ {nombre} — k = {a['k_bits']} bits/símbolo ══════")
        print("\n[ANTES]")
        # c recorre, en este orden, los nombres de las métricas que se quieren mostrar.
        for c in ("N_simbolos", "alfabeto_observado_U", "H_bits_por_simbolo", "H_por_bit",
                  "H_max_observable_log2U", "cota_muestral_log2N", "informacion_total_bits",
                  "redundancia_R", "KL_P_vs_uniforme_k", "KL_P_vs_uniforme_observada",
                  "bits_constantes_redundantes", "informacion_mutua_entre_bits", "estructura"):
            # {c:32} rellena el nombre con espacios hasta 32 caracteres para alinear la columna.
            print(f"  {c:32} {f(a[c])}")
        if "tras_cuantizar" in a:
            print(f"  {'tras cuantizar (pérdida)':32} {a['tras_cuantizar']}")
        print("\n[DURANTE] (primeros y últimos bloques)")
        # {...:>6} alinea a la derecha en 6 caracteres (formato de tabla).
        print(f"  {'bloque':>6} {'H':>10} {'L':>10} {'KL(blq‖glob)':>13} {'razón acum':>11}")
        d = self.durante
        # Si hay más de 6 bloques, se muestran solo los 3 primeros (d[:3]), una marca None
        # para imprimir "..." y los 3 últimos (d[-3:]). Si hay 6 o menos, se muestran todos.
        for r in (d[:3] + [None] + d[-3:]) if len(d) > 6 else d:
            if r is None:
                print("     ..."); continue
            print(f"  {r.bloque:>6} {r.H_bloque:>10.4f} {r.L_bloque:>10.4f} "
                  f"{r.KL_bloque_vs_global:>13.5f} {r.razon_acumulada:>11.3f}")
        print("\n[DESPUÉS]")
        # .items() recorre el diccionario dando parejas (clave c, valor v).
        for c, v in self.despues.a_dict().items():
            print(f"  {c:32} {f(v)}")
        if self.despues.sin_perdida_exacta:
            print("  (I_XY = H: sin pérdida la reconstrucción es idéntica al original,")
            print("   así que I(X;Y) coincide con la entropía por definición -no es un error-)")

    def graficar(self, ruta: str, k: int, entropia_por_bit: np.ndarray, frecuencias: np.ndarray):
        # matplotlib se importa aquí adentro para que el resto del programa funcione aunque
        # no esté instalado; "Agg" dibuja directo a un archivo, sin abrir ventanas.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        d, a, z = self.durante, self.antes, self.despues  # alias cortos de las tres etapas
        fig, ax = plt.subplots(2, 2, figsize=(12, 8))     # cuadrícula de 2×2 gráficas; ax[fila, columna]
        b = [r.bloque for r in d]  # eje x: número de cada bloque
        ax[0, 0].plot(b, [r.H_bloque for r in d], label="H bloque")
        ax[0, 0].plot(b, [r.L_bloque for r in d], label="L Huffman")
        ax[0, 0].set_title("Durante: entropía vs longitud media"); ax[0, 0].set_xlabel("bloque")
        ax[0, 0].set_ylabel("bits/símbolo"); ax[0, 0].legend()
        ax[0, 1].plot(b, [r.KL_bloque_vs_global for r in d], color="tab:red")
        ax[0, 1].set_title("Durante: D_KL(bloque ‖ global)"); ax[0, 1].set_xlabel("bloque"); ax[0, 1].set_ylabel("bits")
        ax[1, 0].plot(entropia_por_bit, lw=0.6)
        ax[1, 0].set_title(f"Antes: entropía por posición de bit ({a.bits_constantes_redundantes} bits redundantes)")
        ax[1, 0].set_xlabel("posición de bit en el símbolo"); ax[1, 0].set_ylabel("H(bit)"); ax[1, 0].set_ylim(-0.05, 1.05)
        # Probabilidades ordenadas de mayor a menor ([::-1] invierte el orden ascendente de sort).
        p = np.sort(frecuencias)[::-1] / frecuencias.sum()
        ax[1, 1].loglog(np.arange(1, len(p) + 1), p)
        ax[1, 1].set_title("Antes: rango-frecuencia de símbolos"); ax[1, 1].set_xlabel("rango"); ax[1, 1].set_ylabel("p")
        fig.suptitle(f"k={k} | H={a.H_bits_por_simbolo:.3f} | razón={z.razon_compresion:.3f} | modo={z.modo_elegido}")
        fig.tight_layout(); fig.savefig(ruta, dpi=130)
        print(f"\nGráfica guardada en {ruta}")


# ═══════════════════════════ el códec ═══════════════════════════
class CodecTIC:
    """Orquesta el pipeline completo: segmentar, analizar, codificar (el
    modo más compacto entre Huffman y bitstrip), escribir el archivo .tic,
    decodificar y verificar. Las clases de arriba hacen el trabajo; esta
    clase solo decide el orden y arma los reportes."""

    # "Número mágico": los 4 primeros bytes de todo archivo .tic, para reconocer el formato.
    MAGIC = b"TIC1"

    def __init__(self, bloques: int = 50):
        self.bloques = bloques  # en cuántos tramos se divide el archivo para las métricas "durante"

    # ---- codificar ----
    def codificar(self, entrada: str, salida: str, k: int, perdida: int = 0,
                  grafica: str | None = None, reporte: str | None = None) -> ReporteCodificacion:
        t0 = time.time()  # hora de inicio, para medir cuánto tarda la codificación
        raw = np.fromfile(entrada, dtype=np.uint8)  # bytes originales del archivo

        # ---- ANTES: analizar la fuente original ----
        fuente_orig = Fuente.desde_bytes(raw, k)
        alfabeto_orig = Alfabeto.desde_filas(fuente_orig.filas)
        perfil_orig = PerfilBits.desde_filas(fuente_orig.filas)
        antes = MetricasAntes.calcular(fuente_orig, alfabeto_orig, perfil_orig)

        # `data` = los bytes que realmente se van a codificar (igual a raw si no hay pérdida).
        data = raw
        if perdida:
            # Pérdida controlada: se ponen en 0 los `perdida` bits menos significativos de cada byte.
            # (0xFF << perdida) & 0xFF arma la máscara; ej. perdida=3 → 11111000.
            # `&` entre el array y la máscara aplica el "y" bit a bit a todos los bytes a la vez.
            data = raw & np.uint8((0xFF << perdida) & 0xFF)
            fuente = Fuente.desde_bytes(data, k)
            alfabeto = Alfabeto.desde_filas(fuente.filas)
            perfil = PerfilBits.desde_filas(fuente.filas)
            m2 = MetricasAntes.calcular(fuente, alfabeto, perfil)  # métricas de la fuente ya cuantizada
            antes.tras_cuantizar = {
                "alfabeto_observado_U": m2.alfabeto_observado_U,
                "H_bits_por_simbolo": m2.H_bits_por_simbolo,
                "bits_constantes_redundantes": m2.bits_constantes_redundantes,
            }
        else:
            fuente, alfabeto, perfil = fuente_orig, alfabeto_orig, perfil_orig

        # ---- DURANTE: construir los codificadores y codificar ----
        n, U = fuente.n, alfabeto.U
        mascara = MascaraRedundancia.desde_perfil(perfil)
        huffman = HuffmanCanonico.desde_frecuencias(alfabeto.frecuencias)

        durante = self._metricas_durante(k, alfabeto, huffman)
        # _codificar_cuerpo devuelve 4 valores a la vez; se reciben en 4 variables.
        modo, tam_huff, tam_strip, secciones = self._codificar_cuerpo(fuente, alfabeto, mascara, huffman)

        mascara_var_hex, valores_const_hex = mascara.a_hex()
        cabecera = CabeceraTIC(
            k=k, orig_len=fuente_orig.longitud_original, n=n, U=U, modo=modo, perdida=perdida,
            mascara_var=mascara_var_hex, valores_const=valores_const_hex,
            sha256=hashlib.sha256(data.tobytes()).hexdigest(),
            secciones=[len(x) for x in secciones],  # tamaño en bytes de cada sección
        )
        cab_json = cabecera.a_json()
        # Estructura del archivo .tic:
        #   "TIC1" (4 B) | largo de la cabecera (4 B) | cabecera JSON | sección 1 | sección 2 | sección 3
        # struct.pack("<I", ...) escribe un entero sin signo de 4 bytes, formato little-endian.
        with open(salida, "wb") as f:
            f.write(self.MAGIC + struct.pack("<I", len(cab_json)) + cab_json)
            for x in secciones:
                f.write(x)
        t_cod = time.time() - t0  # segundos que tardó la codificación
        # 8 = 4 bytes de "TIC1" + 4 bytes del largo de la cabecera.
        # sum(len(x) for x in secciones) suma el tamaño de todas las secciones.
        tam_final = 8 + len(cab_json) + sum(len(x) for x in secciones)

        # ---- DESPUÉS: decodificar, verificar y medir ----
        t1 = time.time()
        rec = self.decodificar(salida, None, silencioso=True)  # bytes reconstruidos
        t_dec = time.time() - t1
        # Entropía del flujo ya comprimido, byte a byte: si la compresión es buena, se parece a
        # ruido uniforme (H8 cerca de 8 bits por byte). secciones[2:] = de la tercera en adelante.
        flujo = np.frombuffer(b"".join(secciones[2:]), np.uint8)
        conteo_bytes = np.bincount(flujo, minlength=256)  # cuántas veces aparece cada byte 0..255
        # conteo_bytes[conteo_bytes > 0] se queda solo con los bytes que sí aparecieron (evita log2(0)).
        H8 = Informacion.entropia(conteo_bytes[conteo_bytes > 0]) if len(flujo) else 0.0

        H_actual = Informacion.entropia(alfabeto.frecuencias)
        Lmed = huffman.longitud_media(alfabeto.frecuencias)

        # I(X;Y) entre la fuente original (X) y la reconstruida (Y):
        # sin pérdida, Y=X exactamente (lo verifica sin_perdida_exacta más abajo),
        # así que I(X;Y)=H(X) por definición -- calcularlo por la vía barata en
        # vez de construir el histograma conjunto solo para reconfirmarlo.
        # Con pérdida, Y sí difiere de X y se mide la información mutua real.
        if perdida:
            fuente_rec = Fuente.desde_bytes(rec, k)
            alfabeto_rec = Alfabeto.desde_filas(fuente_rec.filas)
            info_mutua_XY = Informacion.informacion_mutua(alfabeto_orig.indices, alfabeto_rec.indices)
        else:
            info_mutua_XY = Informacion.entropia(alfabeto_orig.frecuencias)

        despues = MetricasDespues(
            modo_elegido=modo,
            tamano_original_B=int(len(raw)), tamano_codificado_B=tam_final,
            razon_compresion=len(raw) / tam_final, ahorro_pct=100 * (1 - tam_final / len(raw)),
            bits_por_simbolo_real=tam_final * 8 / n,
            L_media_huffman=Lmed, eficiencia_H_sobre_L=H_actual / Lmed,
            redundancia_codigo_L_menos_H=Lmed - H_actual,
            kraft_suma=huffman.kraft(),
            long_max_codigo=huffman.longitud_maxima,
            # techo(U · bits_variables / 8): bytes que ocupa guardar el alfabeto sin los bits constantes.
            tamano_diccionario_B=-(-U * mascara.num_variables // 8),
            tamano_estimado_huffman_B=tam_huff, tamano_estimado_bitstrip_B=tam_strip,
            H_flujo_codificado_bits_por_byte=H8,
            KL_flujo_vs_uniforme_256=8 - H8,
            informacion_mutua_XY=info_mutua_XY,
            # ¿La huella SHA-256 de lo reconstruido coincide con la guardada en la cabecera?
            verificacion_sha256=hashlib.sha256(rec.tobytes()).hexdigest() == cabecera.sha256,
            # ¿Lo reconstruido es idéntico, byte a byte, al archivo original?
            sin_perdida_exacta=bool(np.array_equal(rec, raw)),
            tiempo_codificacion_s=t_cod, tiempo_decodificacion_s=t_dec,
        )
        if perdida:
            # co / cr = conteos de símbolos del original y del reconstruido, como diccionarios.
            co = alfabeto_orig.a_diccionario()
            cr = alfabeto_rec.a_diccionario()
            despues.KL_original_vs_reconstruido = Informacion.kl_suavizada(co, cr)
            # MSE = promedio del error al cuadrado, byte a byte. Se pasa a float para que
            # la resta no "dé la vuelta" (en uint8, 3 − 5 daría 254 en vez de −2).
            mse = float(np.mean((raw.astype(float) - rec.astype(float)) ** 2))
            despues.MSE_por_byte = mse
            # PSNR = 10·log10(255² / MSE) en decibeles; si no hay error (MSE = 0) es infinito.
            despues.PSNR_dB = float("inf") if mse == 0 else 10 * math.log10(255 ** 2 / mse)
        else:
            despues.KL_original_vs_reconstruido = 0.0 if despues.sin_perdida_exacta else None

        reporte_obj = ReporteCodificacion(antes=antes, durante=durante, despues=despues)
        reporte_obj.imprimir(entrada)
        if reporte:
            reporte_obj.guardar_json(reporte)
        if grafica:
            reporte_obj.graficar(grafica, k, perfil.entropia_por_bit, alfabeto.frecuencias)
        return reporte_obj

    def _metricas_durante(self, k: int, alfabeto: Alfabeto, huffman: HuffmanCanonico) -> list[ReporteBloque]:
        """H, longitud media de Huffman y KL(bloque‖global) por cada uno de
        self.bloques tramos consecutivos del archivo."""
        n = len(alfabeto.indices)
        tam = max(1, -(-n // self.bloques))  # símbolos por bloque = techo(n / cantidad de bloques)
        bits_acum = 0                         # bits Huffman usados desde el inicio hasta este bloque
        bloques = []
        # range(0, n, tam) da el inicio s de cada bloque (0, tam, 2·tam, ...);
        # enumerate le agrega el número de bloque b (0, 1, 2, ...).
        for b, s in enumerate(range(0, n, tam)):
            idx = alfabeto.indices[s:s + tam]  # símbolos de este bloque
            # ub = símbolos distintos del bloque, cb = cuántas veces aparece cada uno dentro del bloque.
            ub, cb = np.unique(idx, return_counts=True)
            pb = cb / cb.sum()                   # probabilidad de esos símbolos dentro del bloque
            pg = alfabeto.frecuencias[ub] / n    # probabilidad de esos mismos símbolos en todo el archivo
            # huffman.longitudes[idx] = longitud del código de cada símbolo del bloque.
            bits_acum += int(huffman.longitudes[idx].sum())
            bloques.append(ReporteBloque(
                bloque=b,
                H_bloque=Informacion.entropia(cb),
                L_bloque=float(huffman.longitudes[idx].mean()),
                KL_bloque_vs_global=float((pb * np.log2(pb / pg)).sum()),
                # Bits originales acumulados (símbolos · k) / bits Huffman acumulados.
                # max(1, ...) evita dividir entre 0.
                razon_acumulada=(s + len(idx)) * k / max(1, bits_acum),
            ))
        return bloques

    def _codificar_cuerpo(self, fuente: Fuente, alfabeto: Alfabeto,
                           mascara: MascaraRedundancia, huffman: HuffmanCanonico):
        """Estima el tamaño de Huffman vs. bitstrip y escribe el que resulte
        más chico — así el archivo nunca crece más allá de la cabecera."""
        # v = bits variables por símbolo (los que no son constantes).
        n, U, v = fuente.n, alfabeto.U, mascara.num_variables
        tam_dicc = -(-U * v // 8)  # bytes del diccionario: techo(U · v / 8)
        # Tamaño Huffman = techo(bits de todos los códigos / 8)
        #                  + U bytes (una longitud de código por símbolo) + diccionario.
        # Si algún código mide más de 64 bits no cabe en un entero de 64 → se descarta (infinito).
        tam_huff = (-(-int((alfabeto.frecuencias * huffman.longitudes).sum()) // 8) + U + tam_dicc
                    if huffman.longitud_maxima <= 64 else float("inf"))
        # Tamaño bitstrip = guardar cada símbolo tal cual, pero solo sus v bits variables.
        tam_strip = -(-n * v // 8)
        modo = "huffman" if tam_huff < tam_strip else "bitstrip"
        # El archivo siempre tiene 3 secciones:
        #   huffman  → [longitudes de código, diccionario de símbolos, flujo de códigos]
        #   bitstrip → [vacía, vacía, todos los símbolos con solo sus bits variables]
        if modo == "huffman":
            secciones = [huffman.longitudes.astype(np.uint8).tobytes(),
                         mascara.extraer(alfabeto.simbolos),
                         huffman.empaquetar(alfabeto.indices)]
        else:
            secciones = [b"", b"", mascara.extraer(fuente.filas)]
        return modo, tam_huff, tam_strip, secciones

    # ---- decodificar ----
    def decodificar(self, entrada: str, salida: str | None, silencioso: bool = False) -> np.ndarray:
        with open(entrada, "rb") as f:
            blob = f.read()  # todo el archivo .tic en memoria, como bytes
        if blob[:4] != self.MAGIC:
            raise ValueError("no es un archivo TIC1")
        # hl = "header length": bytes 4..7 del archivo = largo de la cabecera JSON.
        # struct.unpack devuelve una tupla; [0] toma su único elemento.
        hl = struct.unpack("<I", blob[4:8])[0]
        cabecera = CabeceraTIC.desde_json(blob[8:8 + hl])
        k, n, U = cabecera.k, cabecera.n, cabecera.U
        p = 8 + hl  # posición donde empieza la primera sección de datos
        s1, s2, s3 = cabecera.secciones  # tamaño de cada una de las 3 secciones
        # Se cortan las 3 secciones una tras otra:
        #   sec_l = longitudes de código, sec_d = diccionario, sec_p = "payload" (los datos codificados).
        sec_l, sec_d, sec_p = blob[p:p + s1], blob[p + s1:p + s1 + s2], blob[p + s1 + s2:p + s1 + s2 + s3]
        mascara = MascaraRedundancia.desde_hex(k, cabecera.mascara_var, cabecera.valores_const)
        if cabecera.modo == "huffman":
            longitudes = np.frombuffer(sec_l, np.uint8).astype(np.int64)
            huffman = HuffmanCanonico(longitudes)
            simbolos = mascara.insertar(sec_d, U, k)  # el alfabeto: U símbolos completos de k bits
            # huffman.decodificar da, para cada posición, el índice de su símbolo en el alfabeto;
            # indexar `simbolos` con ese array arma directamente todas las filas del archivo.
            filas = simbolos[huffman.decodificar(sec_p, n)]
        else:
            filas = mascara.insertar(sec_p, n, k)
        # ravel() aplana las filas a una sola tira de bytes; [:orig_len] quita el relleno del final.
        out = filas.ravel()[:cabecera.orig_len]
        ok = hashlib.sha256(out.tobytes()).hexdigest() == cabecera.sha256
        if salida:
            out.tofile(salida)
        if not silencioso:
            print(f"Decodificado {n} símbolos de {k} bits → {len(out)} bytes | SHA-256 {'OK' if ok else 'FALLÓ'}")
        return out

    # ---- estimación para un solo k, sin codificar ----
    @staticmethod
    def estimar(raw: np.ndarray, k: int) -> tuple[MetricasAntes, float]:
        """Métricas "antes" y razón de compresión ESTIMADA de `raw` con símbolos de k bits,
        sin escribir nada. Lo usan barrido() y el bandido de tic_bandido.py."""
        fuente = Fuente.desde_bytes(raw, k)
        alfabeto = Alfabeto.desde_filas(fuente.filas)
        perfil = PerfilBits.desde_filas(fuente.filas)
        m = MetricasAntes.calcular(fuente, alfabeto, perfil)
        huffman = HuffmanCanonico.desde_frecuencias(alfabeto.frecuencias)
        v = m.bits_variables
        # Mismas fórmulas de tamaño que en _codificar_cuerpo:
        #   huff  = techo(bits de códigos / 8) + U + techo(U · v / 8)
        #   strip = techo(n · v / 8)
        huff = -(-int((alfabeto.frecuencias * huffman.longitudes).sum()) // 8) + alfabeto.U + -(-alfabeto.U * v // 8)
        strip = -(-fuente.n * v // 8)
        return m, len(raw) / min(huff, strip)  # se usa el más chico de los dos modos

    # ---- barrido de k, sin codificar ----
    def barrido(self, entrada: str, ks: list[int]) -> list[dict]:
        # Para cada k de la lista `ks` calcula las métricas "antes" y ESTIMA la razón de
        # compresión (sin escribir ningún archivo), para comparar qué k conviene.
        raw = np.fromfile(entrada, dtype=np.uint8)
        print(f"\nArchivo: {entrada}  ({len(raw):,} bytes)\n")
        cab = f"{'k':>6} {'N':>10} {'U':>10} {'H':>10} {'H/k':>7} {'log2N':>7} {'KL(P‖U)':>10} {'bits red.':>9} {'razón':>7}  estructura"
        print(cab); print("─" * len(cab))  # "─" * n repite el carácter n veces (línea separadora)
        resultados = []
        for k in ks:
            m, razon = self.estimar(raw, k)
            print(f"{k:>6} {m.N_simbolos:>10,} {m.alfabeto_observado_U:>10,} {m.H_bits_por_simbolo:>10.3f} "
                  f"{m.H_por_bit:>7.4f} {m.cota_muestral_log2N:>7.2f} {m.KL_P_vs_uniforme_k:>10.2f} "
                  f"{m.bits_constantes_redundantes:>9} {razon:>7.3f}  {m.estructura}")
            d = m.a_dict()
            d["razon_estimada"] = razon
            resultados.append(d)
        return resultados


# ═══════════════════════════ fuentes sintéticas ═══════════════════════════
class GeneradorFuentes:
    """Fuentes de prueba sintéticas: uniforme, no uniforme (Zipf) o
    estructurada (bloques que se repiten, con algo de ruido)."""

    @staticmethod
    def uniforme(n: int, rng: np.random.Generator) -> np.ndarray:
        # n bytes al azar, todos los valores 0..255 igual de probables. rng = generador aleatorio.
        return rng.integers(0, 256, n, dtype=np.uint8)

    @staticmethod
    def no_uniforme(n: int, rng: np.random.Generator) -> np.ndarray:
        # Ley de Zipf: el valor i-ésimo tiene probabilidad proporcional a 1 / i^1.3
        # (unos pocos valores muy frecuentes y muchos raros).
        p = 1.0 / np.arange(1, 257) ** 1.3
        return rng.choice(256, n, p=p / p.sum()).astype(np.uint8)

    @staticmethod
    def estructurado(n: int, rng: np.random.Generator, bloque: int = 256) -> np.ndarray:
        # 16 bloques de `bloque` bytes (256 por defecto) que se repiten: redundancia sólo
        # visible cuando k alcanza el tamaño del bloque (k = 8 · bloque).
        dic = rng.integers(0, 256, (16, bloque), dtype=np.uint8)  # "diccionario" de 16 bloques al azar
        # rng.integers(0, 16, cantidad) elige al azar cuál de los 16 bloques va en cada lugar;
        # dic[...] los pone uno tras otro; ravel() los aplana y [:n] recorta a n bytes exactos.
        d = dic[rng.integers(0, 16, -(-n // bloque))].ravel()[:n].copy()
        # d[::4096] = uno de cada 4096 bytes; `^= 1` invierte su último bit (XOR con 1).
        d[::4096] ^= 1  # algo de ruido
        return d

    @classmethod
    def generar(cls, tipo: str, salida: str, mb: float, semilla: int = 0):
        # Semilla fija → siempre se genera exactamente el mismo archivo (resultados reproducibles).
        rng = np.random.default_rng(semilla)
        n = int(mb * 1024 * 1024)  # megabytes → bytes
        if tipo == "uniforme":
            d = cls.uniforme(n, rng)
        elif tipo == "no_uniforme":
            d = cls.no_uniforme(n, rng)
        elif tipo == "estructurado":
            d = cls.estructurado(n, rng)
        else:
            raise ValueError("tipo: uniforme | no_uniforme | estructurado")
        d.tofile(salida)
        print(f"Generado {salida}: {n:,} bytes, fuente {tipo}")


# ═══════════════════════════ CLI ═══════════════════════════
def main():
    # argparse define los comandos y opciones que acepta el programa desde la terminal.
    # ap = el analizador principal; sp = los subcomandos (codificar, decodificar, barrido, generar).
    # c, d, b, g = el analizador de cada subcomando; x = los argumentos ya leídos de la terminal.
    ap = argparse.ArgumentParser(description="Códec adaptable k bits/símbolo con métricas de información")
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("codificar"); c.add_argument("entrada"); c.add_argument("salida")
    # choices=range(0, 8) → --perdida solo acepta 0..7.
    c.add_argument("-k", type=int, default=8); c.add_argument("--perdida", type=int, default=0, choices=range(0, 8))
    c.add_argument("--bloques", type=int, default=50); c.add_argument("--grafica"); c.add_argument("--reporte")
    d = sp.add_parser("decodificar"); d.add_argument("entrada"); d.add_argument("salida")
    b = sp.add_parser("barrido"); b.add_argument("entrada"); b.add_argument("--extendido", action="store_true")
    b.add_argument("--ks", help="lista propia, ej. 8,64,2048,32888")
    g = sp.add_parser("generar"); g.add_argument("tipo"); g.add_argument("salida"); g.add_argument("--mb", type=float, default=2)
    x = ap.parse_args()
    if x.cmd == "codificar":
        CodecTIC(bloques=x.bloques).codificar(x.entrada, x.salida, x.k, x.perdida, x.grafica, x.reporte)
    elif x.cmd == "decodificar":
        CodecTIC().decodificar(x.entrada, x.salida)
    elif x.cmd == "barrido":
        # Si se pasó --ks "8,64,2048": split(",") → ["8", "64", "2048"] y cada uno se pasa a int.
        # Si no, se usa K_BASE, más K_EXT si se pidió --extendido (sumar listas las concatena).
        ks = [int(v) for v in x.ks.split(",")] if x.ks else K_BASE + (K_EXT if x.extendido else [])
        CodecTIC().barrido(x.entrada, ks)
    else:
        GeneradorFuentes.generar(x.tipo, x.salida, x.mb)


# Este bloque solo se ejecuta si el archivo se corre directamente (python tic_codec.py ...),
# no cuando otro archivo lo importa.
if __name__ == "__main__":
    main()
