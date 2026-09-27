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
"""
from __future__ import annotations

import argparse, hashlib, heapq, json, math, struct, sys, time
from dataclasses import dataclass, asdict
import numpy as np

# La consola de Windows usa cp1252 por defecto, que no tiene los caracteres
# Unicode que se imprimen (─, ‖, …). Sin esto, cualquier comando falla con
# UnicodeEncodeError antes de mostrar resultados.
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")

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
        if k % 8 or k < 8:
            raise ValueError("k debe ser múltiplo de 8 (8, 16, ..., 32888...)")
        B = k // 8
        n = -(-len(datos) // B)
        buf = np.zeros(n * B, dtype=np.uint8)
        buf[:len(datos)] = datos
        filas = buf.reshape(n, B)
        return cls(k=k, filas=filas, longitud_original=len(datos) if longitud_original is None else longitud_original)

    @classmethod
    def desde_archivo(cls, ruta: str, k: int) -> "Fuente":
        return cls.desde_bytes(np.fromfile(ruta, dtype=np.uint8), k)

    @property
    def n(self) -> int:
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
        B = filas.shape[1]
        v = np.ascontiguousarray(filas).view(np.dtype((np.void, B))).ravel()
        u, inv, cnt = np.unique(v, return_inverse=True, return_counts=True)
        return cls(simbolos=u.view(np.uint8).reshape(-1, B),
                    indices=inv.ravel().astype(np.int64),
                    frecuencias=cnt.astype(np.int64))

    @property
    def U(self) -> int:
        return len(self.frecuencias)

    def probabilidades(self) -> np.ndarray:
        return self.frecuencias / self.frecuencias.sum()

    def a_diccionario(self) -> dict:
        """Símbolo (bytes) → cuenta. Usado para comparar distribuciones con D_KL."""
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
        n, B = filas.shape
        ones = np.zeros(B * 8, dtype=np.int64)
        paso = max(1, (1 << 24) // B)
        for s in range(0, n, paso):
            r = filas[s:s + paso]
            for b in range(8):
                ones[b::8] += ((r >> (7 - b)) & 1).sum(axis=0, dtype=np.int64)
        p_uno = ones / n
        return cls(p_uno=p_uno, entropia_por_bit=Informacion.entropia_binaria(p_uno))

    @property
    def constantes(self) -> np.ndarray:
        return (self.p_uno == 0) | (self.p_uno == 1)


# ═══════════════════════════ teoría de la información ═══════════════════════════
class Informacion:
    """Caja de herramientas de teoría de la información: entropía, entropía
    binaria, divergencia KL con suavizado y la clasificación uniforme / no
    uniforme de una fuente. Sin estado — solo funciones agrupadas por tema."""

    @staticmethod
    def entropia(frecuencias: np.ndarray) -> float:
        p = frecuencias / frecuencias.sum()
        return float(-(p * np.log2(p)).sum())

    @staticmethod
    def informacion_mutua(indices_x: np.ndarray, indices_y: np.ndarray) -> float:
        """I(X;Y) en bits entre dos flujos de símbolos emparejados fila a fila
        (p. ej. fuente original vs. reconstruida tras una codificación con
        pérdida). Construye la distribución conjunta de forma vectorizada -sin
        iterar símbolo por símbolo, igual que el resto de la clase- y devuelve
        Σ p(x,y) log2(p(x,y) / (p(x)·p(y)))."""
        x = np.asarray(indices_x, dtype=np.int64)
        y = np.asarray(indices_y, dtype=np.int64)
        n = len(x)
        Ux, Uy = int(x.max()) + 1, int(y.max()) + 1
        clave = x * Uy + y
        claves_unicas, cuentas = np.unique(clave, return_counts=True)
        xu, yu = claves_unicas // Uy, claves_unicas % Uy
        px = np.bincount(x, minlength=Ux) / n
        py = np.bincount(y, minlength=Uy) / n
        pxy = cuentas / n
        return float((pxy * np.log2(pxy / (px[xu] * py[yu]))).sum())

    @staticmethod
    def entropia_binaria(p: np.ndarray) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            h = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
        return np.nan_to_num(h)

    @staticmethod
    def kl_suavizada(cp: dict, cq: dict, alfa: float = 0.5) -> float:
        """D(P‖Q) en bits, con suavizado aditivo sobre la unión de soportes (dict símbolo→cuenta)."""
        S = set(cp) | set(cq)
        Np, Nq = sum(cp.values()) + alfa * len(S), sum(cq.values()) + alfa * len(S)
        d = 0.0
        for s in S:
            p = (cp.get(s, 0) + alfa) / Np
            q = (cq.get(s, 0) + alfa) / Nq
            d += p * math.log2(p / q)
        return d

    @staticmethod
    def clasificar(H: float, k: int, U: int, n: int) -> str:
        if n / U < 2:
            return "casi todos los símbolos son únicos: estimación limitada por la muestra (H≈log2 N)"
        r = H / k
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
        n, k, U = fuente.n, fuente.k, alfabeto.U
        H = Informacion.entropia(alfabeto.frecuencias)
        info = -np.log2(alfabeto.probabilidades())
        const = perfil.constantes
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
            bits_constantes_redundantes=int(const.sum()),
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
        return cls(variables=~perfil.constantes,
                    valores_constantes=(perfil.p_uno == 1).astype(np.uint8))

    @property
    def indices_variables(self) -> np.ndarray:
        return np.flatnonzero(self.variables)

    @property
    def num_variables(self) -> int:
        return int(self.variables.sum())

    def extraer(self, filas: np.ndarray) -> bytes:
        """Empaqueta sólo las posiciones de bit variables de cada fila."""
        var_idx = self.indices_variables
        k = filas.shape[1] * 8
        paso = max(1, (1 << 25) // k)
        out, carry = [], np.zeros(0, np.uint8)
        for s in range(0, len(filas), paso):
            bits = np.unpackbits(filas[s:s + paso], axis=1)[:, var_idx].ravel()
            bits = np.concatenate([carry, bits])
            m = len(bits) // 8 * 8
            out.append(np.packbits(bits[:m]).tobytes())
            carry = bits[m:]
        if len(carry):
            out.append(np.packbits(carry).tobytes())
        return b"".join(out)

    def insertar(self, empacado: bytes, n: int, k: int) -> np.ndarray:
        """Reconstruye n filas de k bits a partir de los bits variables empacados
        y los valores constantes guardados en la máscara."""
        var_idx = self.indices_variables
        v = len(var_idx)
        allbits = np.unpackbits(np.frombuffer(empacado, np.uint8))
        filas = np.empty((n, k // 8), np.uint8)
        paso = max(1, (1 << 25) // k)
        for s in range(0, n, paso):
            e = min(n, s + paso)
            full = np.tile(self.valores_constantes, (e - s, 1))
            if v:
                full[:, var_idx] = allbits[s * v:e * v].reshape(e - s, v)
            filas[s:e] = np.packbits(full, axis=1)
        return filas

    def a_hex(self) -> tuple[str, str]:
        return (np.packbits(self.variables).tobytes().hex(),
                np.packbits(self.valores_constantes).tobytes().hex())

    @classmethod
    def desde_hex(cls, k: int, mascara_hex: str, valores_hex: str) -> "MascaraRedundancia":
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
        U = len(cnt)
        if U == 1:
            return np.array([1], np.int64)
        heap = [(int(c), i) for i, c in enumerate(cnt)]
        heapq.heapify(heap)
        parent = [0] * (2 * U - 1)
        nxt = U
        while len(heap) > 1:
            c1, a = heapq.heappop(heap)
            c2, b = heapq.heappop(heap)
            parent[a] = parent[b] = nxt
            heapq.heappush(heap, (c1 + c2, nxt))
            nxt += 1
        depth = [0] * (2 * U - 1)
        for node in range(2 * U - 3, -1, -1):
            depth[node] = depth[parent[node]] + 1
        return np.array(depth[:U], np.int64)

    @staticmethod
    def _codigos_canonicos(lens):
        order = np.lexsort((np.arange(len(lens)), lens))
        codes = [0] * len(lens)
        code, prev = 0, int(lens[order[0]])
        for i in order.tolist():
            l = int(lens[i])
            code <<= (l - prev)
            codes[i] = code
            code += 1
            prev = l
        return np.array(codes, np.uint64), order

    @property
    def longitud_maxima(self) -> int:
        return int(self.longitudes.max())

    def longitud_media(self, frecuencias: np.ndarray) -> float:
        n = frecuencias.sum()
        return float((frecuencias * self.longitudes).sum() / n)

    def kraft(self) -> float:
        return float(np.sum(2.0 ** -self.longitudes))

    def empaquetar(self, indices: np.ndarray) -> bytes:
        out, carry = [], np.zeros(0, np.uint8)
        paso = 1 << 20
        for s in range(0, len(indices), paso):
            idx = indices[s:s + paso]
            c, l = self.codigos[idx], self.longitudes[idx]
            rep = np.repeat(np.arange(len(idx)), l)
            offs = np.cumsum(l) - l
            j = np.arange(int(l.sum())) - offs[rep]
            sh = (l[rep] - 1 - j).astype(np.uint64)
            bits = ((c[rep] >> sh) & np.uint64(1)).astype(np.uint8)
            bits = np.concatenate([carry, bits])
            m = len(bits) // 8 * 8
            out.append(np.packbits(bits[:m]).tobytes())
            carry = bits[m:]
        if len(carry):
            out.append(np.packbits(carry).tobytes())
        return b"".join(out)

    def decodificar(self, payload: bytes, n: int) -> np.ndarray:
        lens = self.longitudes
        maxlen = self.longitud_maxima
        T = min(maxlen, 16)
        order = np.lexsort((np.arange(len(lens)), lens)).tolist()
        tsym, tlen = [0] * (1 << T), [0] * (1 << T)
        first_code, first_rank, count = [0] * (maxlen + 1), [0] * (maxlen + 1), [0] * (maxlen + 1)
        code, prev = 0, int(lens[order[0]])
        for r, i in enumerate(order):
            l = int(lens[i])
            code <<= (l - prev)
            if count[l] == 0:
                first_code[l], first_rank[l] = code, r
            count[l] += 1
            if l <= T:
                a, b = code << (T - l), (code + 1) << (T - l)
                tsym[a:b] = [i] * (b - a)
                tlen[a:b] = [l] * (b - a)
            code += 1
            prev = l
        data, L, pos, acc, nb = payload, len(payload), 0, 0, 0
        mask = (1 << T) - 1
        out = [0] * n
        for i in range(n):
            while nb < maxlen and pos < L:
                acc = (acc << 8) | data[pos]; pos += 1; nb += 8
            peek = ((acc >> (nb - T)) if nb >= T else (acc << (T - nb))) & mask
            l = tlen[peek]
            if l:
                out[i] = tsym[peek]; nb -= l; acc &= (1 << nb) - 1
                continue
            for l in range(T + 1, maxlen + 1):
                c = (acc >> (nb - l)) if nb >= l else (acc << (l - nb))
                d = c - first_code[l]
                if 0 <= d < count[l]:
                    out[i] = order[first_rank[l] + d]; nb -= l; acc &= (1 << nb) - 1
                    break
            else:
                raise ValueError("flujo Huffman corrupto")
        return np.array(out, np.int64)


# ═══════════════════════════ formato .tic ═══════════════════════════
@dataclass
class CabeceraTIC:
    """La cabecera JSON autocontenida del archivo .tic: todo lo que necesita
    el decodificador, sin parámetros externos."""
    k: int
    orig_len: int
    n: int
    U: int
    modo: str
    perdida: int
    mascara_var: str
    valores_const: str
    sha256: str
    secciones: list[int]

    def a_json(self) -> bytes:
        return json.dumps(asdict(self)).encode()

    @classmethod
    def desde_json(cls, blob: bytes) -> "CabeceraTIC":
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
            "durante": [b.a_dict() for b in self.durante],
            "despues": self.despues.a_dict(),
        }

    def guardar_json(self, ruta: str):
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(self.a_dict(), f, indent=2, ensure_ascii=False)

    def imprimir(self, nombre: str):
        f = lambda x: ("sí" if x else "no") if isinstance(x, bool) else f"{x:,.4f}" if isinstance(x, float) else f"{x:,}" if isinstance(x, int) else str(x)
        a = self.antes.a_dict()
        print(f"\n══════ {nombre} — k = {a['k_bits']} bits/símbolo ══════")
        print("\n[ANTES]")
        for c in ("N_simbolos", "alfabeto_observado_U", "H_bits_por_simbolo", "H_por_bit",
                  "H_max_observable_log2U", "cota_muestral_log2N", "informacion_total_bits",
                  "redundancia_R", "KL_P_vs_uniforme_k", "KL_P_vs_uniforme_observada",
                  "bits_constantes_redundantes", "informacion_mutua_entre_bits", "estructura"):
            print(f"  {c:32} {f(a[c])}")
        if "tras_cuantizar" in a:
            print(f"  {'tras cuantizar (pérdida)':32} {a['tras_cuantizar']}")
        print("\n[DURANTE] (primeros y últimos bloques)")
        print(f"  {'bloque':>6} {'H':>10} {'L':>10} {'KL(blq‖glob)':>13} {'razón acum':>11}")
        d = self.durante
        for r in (d[:3] + [None] + d[-3:]) if len(d) > 6 else d:
            if r is None:
                print("     ..."); continue
            print(f"  {r.bloque:>6} {r.H_bloque:>10.4f} {r.L_bloque:>10.4f} "
                  f"{r.KL_bloque_vs_global:>13.5f} {r.razon_acumulada:>11.3f}")
        print("\n[DESPUÉS]")
        for c, v in self.despues.a_dict().items():
            print(f"  {c:32} {f(v)}")
        if self.despues.sin_perdida_exacta:
            print("  (I_XY = H: sin pérdida la reconstrucción es idéntica al original,")
            print("   así que I(X;Y) coincide con la entropía por definición -no es un error-)")

    def graficar(self, ruta: str, k: int, entropia_por_bit: np.ndarray, frecuencias: np.ndarray):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        d, a, z = self.durante, self.antes, self.despues
        fig, ax = plt.subplots(2, 2, figsize=(12, 8))
        b = [r.bloque for r in d]
        ax[0, 0].plot(b, [r.H_bloque for r in d], label="H bloque")
        ax[0, 0].plot(b, [r.L_bloque for r in d], label="L Huffman")
        ax[0, 0].set_title("Durante: entropía vs longitud media"); ax[0, 0].set_xlabel("bloque")
        ax[0, 0].set_ylabel("bits/símbolo"); ax[0, 0].legend()
        ax[0, 1].plot(b, [r.KL_bloque_vs_global for r in d], color="tab:red")
        ax[0, 1].set_title("Durante: D_KL(bloque ‖ global)"); ax[0, 1].set_xlabel("bloque"); ax[0, 1].set_ylabel("bits")
        ax[1, 0].plot(entropia_por_bit, lw=0.6)
        ax[1, 0].set_title(f"Antes: entropía por posición de bit ({a.bits_constantes_redundantes} bits redundantes)")
        ax[1, 0].set_xlabel("posición de bit en el símbolo"); ax[1, 0].set_ylabel("H(bit)"); ax[1, 0].set_ylim(-0.05, 1.05)
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

    MAGIC = b"TIC1"

    def __init__(self, bloques: int = 50):
        self.bloques = bloques

    # ---- codificar ----
    def codificar(self, entrada: str, salida: str, k: int, perdida: int = 0,
                  grafica: str | None = None, reporte: str | None = None) -> ReporteCodificacion:
        t0 = time.time()
        raw = np.fromfile(entrada, dtype=np.uint8)

        fuente_orig = Fuente.desde_bytes(raw, k)
        alfabeto_orig = Alfabeto.desde_filas(fuente_orig.filas)
        perfil_orig = PerfilBits.desde_filas(fuente_orig.filas)
        antes = MetricasAntes.calcular(fuente_orig, alfabeto_orig, perfil_orig)

        data = raw
        if perdida:
            data = raw & np.uint8((0xFF << perdida) & 0xFF)
            fuente = Fuente.desde_bytes(data, k)
            alfabeto = Alfabeto.desde_filas(fuente.filas)
            perfil = PerfilBits.desde_filas(fuente.filas)
            m2 = MetricasAntes.calcular(fuente, alfabeto, perfil)
            antes.tras_cuantizar = {
                "alfabeto_observado_U": m2.alfabeto_observado_U,
                "H_bits_por_simbolo": m2.H_bits_por_simbolo,
                "bits_constantes_redundantes": m2.bits_constantes_redundantes,
            }
        else:
            fuente, alfabeto, perfil = fuente_orig, alfabeto_orig, perfil_orig

        n, U = fuente.n, alfabeto.U
        mascara = MascaraRedundancia.desde_perfil(perfil)
        huffman = HuffmanCanonico.desde_frecuencias(alfabeto.frecuencias)

        durante = self._metricas_durante(k, alfabeto, huffman)
        modo, tam_huff, tam_strip, secciones = self._codificar_cuerpo(fuente, alfabeto, mascara, huffman)

        mascara_var_hex, valores_const_hex = mascara.a_hex()
        cabecera = CabeceraTIC(
            k=k, orig_len=fuente_orig.longitud_original, n=n, U=U, modo=modo, perdida=perdida,
            mascara_var=mascara_var_hex, valores_const=valores_const_hex,
            sha256=hashlib.sha256(data.tobytes()).hexdigest(),
            secciones=[len(x) for x in secciones],
        )
        cab_json = cabecera.a_json()
        with open(salida, "wb") as f:
            f.write(self.MAGIC + struct.pack("<I", len(cab_json)) + cab_json)
            for x in secciones:
                f.write(x)
        t_cod = time.time() - t0
        tam_final = 8 + len(cab_json) + sum(len(x) for x in secciones)

        # ---- DESPUÉS: decodificar, verificar y medir ----
        t1 = time.time()
        rec = self.decodificar(salida, None, silencioso=True)
        t_dec = time.time() - t1
        flujo = np.frombuffer(b"".join(secciones[2:]), np.uint8)
        conteo_bytes = np.bincount(flujo, minlength=256)
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
            tamano_diccionario_B=-(-U * mascara.num_variables // 8),
            tamano_estimado_huffman_B=tam_huff, tamano_estimado_bitstrip_B=tam_strip,
            H_flujo_codificado_bits_por_byte=H8,
            KL_flujo_vs_uniforme_256=8 - H8,
            informacion_mutua_XY=info_mutua_XY,
            verificacion_sha256=hashlib.sha256(rec.tobytes()).hexdigest() == cabecera.sha256,
            sin_perdida_exacta=bool(np.array_equal(rec, raw)),
            tiempo_codificacion_s=t_cod, tiempo_decodificacion_s=t_dec,
        )
        if perdida:
            co = alfabeto_orig.a_diccionario()
            cr = alfabeto_rec.a_diccionario()
            despues.KL_original_vs_reconstruido = Informacion.kl_suavizada(co, cr)
            mse = float(np.mean((raw.astype(float) - rec.astype(float)) ** 2))
            despues.MSE_por_byte = mse
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
        tam = max(1, -(-n // self.bloques))
        bits_acum = 0
        bloques = []
        for b, s in enumerate(range(0, n, tam)):
            idx = alfabeto.indices[s:s + tam]
            ub, cb = np.unique(idx, return_counts=True)
            pb = cb / cb.sum()
            pg = alfabeto.frecuencias[ub] / n
            bits_acum += int(huffman.longitudes[idx].sum())
            bloques.append(ReporteBloque(
                bloque=b,
                H_bloque=Informacion.entropia(cb),
                L_bloque=float(huffman.longitudes[idx].mean()),
                KL_bloque_vs_global=float((pb * np.log2(pb / pg)).sum()),
                razon_acumulada=(s + len(idx)) * k / max(1, bits_acum),
            ))
        return bloques

    def _codificar_cuerpo(self, fuente: Fuente, alfabeto: Alfabeto,
                           mascara: MascaraRedundancia, huffman: HuffmanCanonico):
        """Estima el tamaño de Huffman vs. bitstrip y escribe el que resulte
        más chico — así el archivo nunca crece más allá de la cabecera."""
        n, U, v = fuente.n, alfabeto.U, mascara.num_variables
        tam_dicc = -(-U * v // 8)
        tam_huff = (-(-int((alfabeto.frecuencias * huffman.longitudes).sum()) // 8) + U + tam_dicc
                    if huffman.longitud_maxima <= 64 else float("inf"))
        tam_strip = -(-n * v // 8)
        modo = "huffman" if tam_huff < tam_strip else "bitstrip"
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
            blob = f.read()
        if blob[:4] != self.MAGIC:
            raise ValueError("no es un archivo TIC1")
        hl = struct.unpack("<I", blob[4:8])[0]
        cabecera = CabeceraTIC.desde_json(blob[8:8 + hl])
        k, n, U = cabecera.k, cabecera.n, cabecera.U
        p = 8 + hl
        s1, s2, s3 = cabecera.secciones
        sec_l, sec_d, sec_p = blob[p:p + s1], blob[p + s1:p + s1 + s2], blob[p + s1 + s2:p + s1 + s2 + s3]
        mascara = MascaraRedundancia.desde_hex(k, cabecera.mascara_var, cabecera.valores_const)
        if cabecera.modo == "huffman":
            longitudes = np.frombuffer(sec_l, np.uint8).astype(np.int64)
            huffman = HuffmanCanonico(longitudes)
            simbolos = mascara.insertar(sec_d, U, k)
            filas = simbolos[huffman.decodificar(sec_p, n)]
        else:
            filas = mascara.insertar(sec_p, n, k)
        out = filas.ravel()[:cabecera.orig_len]
        ok = hashlib.sha256(out.tobytes()).hexdigest() == cabecera.sha256
        if salida:
            out.tofile(salida)
        if not silencioso:
            print(f"Decodificado {n} símbolos de {k} bits → {len(out)} bytes | SHA-256 {'OK' if ok else 'FALLÓ'}")
        return out

    # ---- barrido de k, sin codificar ----
    def barrido(self, entrada: str, ks: list[int]) -> list[dict]:
        raw = np.fromfile(entrada, dtype=np.uint8)
        print(f"\nArchivo: {entrada}  ({len(raw):,} bytes)\n")
        cab = f"{'k':>6} {'N':>10} {'U':>10} {'H':>10} {'H/k':>7} {'log2N':>7} {'KL(P‖U)':>10} {'bits red.':>9} {'razón':>7}  estructura"
        print(cab); print("─" * len(cab))
        resultados = []
        for k in ks:
            fuente = Fuente.desde_bytes(raw, k)
            alfabeto = Alfabeto.desde_filas(fuente.filas)
            perfil = PerfilBits.desde_filas(fuente.filas)
            m = MetricasAntes.calcular(fuente, alfabeto, perfil)
            huffman = HuffmanCanonico.desde_frecuencias(alfabeto.frecuencias)
            v = m.bits_variables
            huff = -(-int((alfabeto.frecuencias * huffman.longitudes).sum()) // 8) + alfabeto.U + -(-alfabeto.U * v // 8)
            strip = -(-fuente.n * v // 8)
            razon = len(raw) / min(huff, strip)
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
        return rng.integers(0, 256, n, dtype=np.uint8)

    @staticmethod
    def no_uniforme(n: int, rng: np.random.Generator) -> np.ndarray:
        p = 1.0 / np.arange(1, 257) ** 1.3
        return rng.choice(256, n, p=p / p.sum()).astype(np.uint8)

    @staticmethod
    def estructurado(n: int, rng: np.random.Generator) -> np.ndarray:
        # 16 bloques de 256 B que se repiten: redundancia sólo visible con k grandes
        dic = rng.integers(0, 256, (16, 256), dtype=np.uint8)
        d = dic[rng.integers(0, 16, -(-n // 256))].ravel()[:n].copy()
        d[::4096] ^= 1  # algo de ruido
        return d

    @classmethod
    def generar(cls, tipo: str, salida: str, mb: float, semilla: int = 0):
        rng = np.random.default_rng(semilla)
        n = int(mb * 1024 * 1024)
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
    ap = argparse.ArgumentParser(description="Códec adaptable k bits/símbolo con métricas de información")
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("codificar"); c.add_argument("entrada"); c.add_argument("salida")
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
        ks = [int(v) for v in x.ks.split(",")] if x.ks else K_BASE + (K_EXT if x.extendido else [])
        CodecTIC().barrido(x.entrada, ks)
    else:
        GeneradorFuentes.generar(x.tipo, x.salida, x.mb)


if __name__ == "__main__":
    main()
