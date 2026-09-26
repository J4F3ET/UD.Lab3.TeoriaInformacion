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
"""
import argparse, hashlib, heapq, json, math, struct, sys, time
import numpy as np

# La consola de Windows usa cp1252 por defecto, que no tiene los caracteres
# Unicode que se imprimen (─, ‖, …). Sin esto, cualquier comando falla con
# UnicodeEncodeError antes de mostrar resultados.
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")

MAGIC = b"TIC1"
K_BASE = [8, 16, 32, 64, 128, 256, 512, 1024, 2048]
K_EXT = [4096, 8192, 16384, 32768, 32888]


# ───────────────────────── símbolos y estadística ─────────────────────────
def a_simbolos(data: np.ndarray, k: int) -> np.ndarray:
    if k % 8 or k < 8:
        raise ValueError("k debe ser múltiplo de 8 (8, 16, ..., 32888...)")
    B = k // 8
    n = -(-len(data) // B)
    buf = np.zeros(n * B, dtype=np.uint8)
    buf[:len(data)] = data
    return buf.reshape(n, B)


def ids_simbolos(rows):
    """Símbolos únicos, índice de cada símbolo y frecuencias."""
    B = rows.shape[1]
    v = np.ascontiguousarray(rows).view(np.dtype((np.void, B))).ravel()
    u, inv, cnt = np.unique(v, return_inverse=True, return_counts=True)
    return u.view(np.uint8).reshape(-1, B), inv.ravel().astype(np.int64), cnt.astype(np.int64)


def entropia(cnt) -> float:
    p = cnt / cnt.sum()
    return float(-(p * np.log2(p)).sum())


def entropia_binaria(p):
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
    return np.nan_to_num(h)


def perfil_bits(rows):
    """P(bit=1) en cada una de las k posiciones del símbolo (MSB primero)."""
    n, B = rows.shape
    ones = np.zeros(B * 8, dtype=np.int64)
    paso = max(1, (1 << 24) // B)
    for s in range(0, n, paso):
        r = rows[s:s + paso]
        for b in range(8):
            ones[b::8] += ((r >> (7 - b)) & 1).sum(axis=0, dtype=np.int64)
    return ones / n


def kl_suavizada(cp, cq, alfa=0.5):
    """D(P||Q) en bits con suavizado aditivo sobre la unión de soportes (dict símbolo→cuenta)."""
    S = set(cp) | set(cq)
    Np, Nq = sum(cp.values()) + alfa * len(S), sum(cq.values()) + alfa * len(S)
    d = 0.0
    for s in S:
        p = (cp.get(s, 0) + alfa) / Np
        q = (cq.get(s, 0) + alfa) / Nq
        d += p * math.log2(p / q)
    return d


def cuentas_dict(rows):
    uniq, _, cnt = ids_simbolos(rows)
    return {bytes(u): int(c) for u, c in zip(uniq, cnt)}


def medir(rows, k):
    uniq, inv, cnt = ids_simbolos(rows)
    n, U = len(rows), len(cnt)
    H = entropia(cnt)
    p = cnt / n
    info = -np.log2(p)
    p1 = perfil_bits(rows)
    hb = entropia_binaria(p1)
    const = (p1 == 0) | (p1 == 1)
    m = {
        "k_bits": k, "N_simbolos": n, "alfabeto_observado_U": U,
        "H_bits_por_simbolo": H, "H_por_bit": H / k,
        "H_max_teorica_k": k, "H_max_observable_log2U": math.log2(U) if U > 1 else 0.0,
        "cota_muestral_log2N": math.log2(n) if n > 1 else 0.0,
        "informacion_total_bits": H * n,
        "autoinformacion_min_max": [float(info.min()), float(info.max())],
        "redundancia_R": 1 - H / k,
        "KL_P_vs_uniforme_k": k - H,
        "KL_P_vs_uniforme_observada": (math.log2(U) - H) if U > 1 else 0.0,
        "bits_constantes_redundantes": int(const.sum()),
        "bits_variables": int((~const).sum()),
        "suma_entropia_por_bit": float(hb.sum()),
        "informacion_mutua_entre_bits": float(hb.sum() - H),
        "fiabilidad_N_sobre_U": n / U,
        "estructura": clasificar(H, k, U, n),
    }
    return m, uniq, inv, cnt, p1, hb, const


def clasificar(H, k, U, n):
    if n / U < 2:
        return "casi todos los símbolos son únicos: estimación limitada por la muestra (H≈log2 N)"
    r = H / k
    if r > 0.97:
        return "uniforme (sin redundancia aprovechable)"
    if r > 0.75:
        return "levemente no uniforme"
    return "no uniforme (alta redundancia)"


# ───────────────────────── manejo de bits redundantes ─────────────────────────
def extraer_bits(rows, var_idx):
    """Empaqueta sólo las posiciones de bit variables de cada fila."""
    k = rows.shape[1] * 8
    paso = max(1, (1 << 25) // k)
    out, carry = [], np.zeros(0, np.uint8)
    for s in range(0, len(rows), paso):
        bits = np.unpackbits(rows[s:s + paso], axis=1)[:, var_idx].ravel()
        bits = np.concatenate([carry, bits])
        m = len(bits) // 8 * 8
        out.append(np.packbits(bits[:m]).tobytes())
        carry = bits[m:]
    if len(carry):
        out.append(np.packbits(carry).tobytes())
    return b"".join(out)


def insertar_bits(packed, n, k, var_idx, cvals):
    v = len(var_idx)
    allbits = np.unpackbits(np.frombuffer(packed, np.uint8))
    rows = np.empty((n, k // 8), np.uint8)
    paso = max(1, (1 << 25) // k)
    for s in range(0, n, paso):
        e = min(n, s + paso)
        full = np.tile(cvals, (e - s, 1))
        if v:
            full[:, var_idx] = allbits[s * v:e * v].reshape(e - s, v)
        rows[s:e] = np.packbits(full, axis=1)
    return rows


# ───────────────────────── Huffman canónico ─────────────────────────
def longitudes_huffman(cnt):
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


def codigos_canonicos(lens):
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


def empaquetar_codigos(inv, codes, lens):
    out, carry = [], np.zeros(0, np.uint8)
    paso = 1 << 20
    for s in range(0, len(inv), paso):
        idx = inv[s:s + paso]
        c, l = codes[idx], lens[idx]
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


def decodificar_huffman(payload, n, lens):
    lens = np.asarray(lens, np.int64)
    maxlen = int(lens.max())
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


# ───────────────────────── codificar ─────────────────────────
def codificar(entrada, salida, k, perdida=0, bloques=50, grafica=None, reporte=None):
    raw = np.fromfile(entrada, dtype=np.uint8)
    t0 = time.time()
    rows_orig = a_simbolos(raw, k)
    antes, uniq, inv, cnt, p1, hb, const = medir(rows_orig, k)

    data = raw
    if perdida:
        data = raw & np.uint8((0xFF << perdida) & 0xFF)
        rows = a_simbolos(data, k)
        m2, uniq, inv, cnt, p1, hb, const = medir(rows, k)
        antes["tras_cuantizar"] = {x: m2[x] for x in
                                   ("alfabeto_observado_U", "H_bits_por_simbolo", "bits_constantes_redundantes")}
    else:
        rows = rows_orig
    n, U = len(rows), len(cnt)
    var_idx = np.flatnonzero(~const)
    cvals = (p1 == 1).astype(np.uint8)
    v = len(var_idx)

    # ---- DURANTE: Huffman sobre el alfabeto observado, medido por bloques ----
    lens = longitudes_huffman(cnt)
    maxlen = int(lens.max())
    Lmed = float((cnt * lens).sum() / n)
    durante = []
    tam = max(1, -(-n // bloques))
    bits_acum = 0
    for b, s in enumerate(range(0, n, tam)):
        idx = inv[s:s + tam]
        ub, cb = np.unique(idx, return_counts=True)
        pb, pg = cb / cb.sum(), cnt[ub] / n
        bits_acum += int(lens[idx].sum())
        durante.append({
            "bloque": b, "H_bloque": entropia(cb), "L_bloque": float(lens[idx].mean()),
            "KL_bloque_vs_global": float((pb * np.log2(pb / pg)).sum()),
            "razon_acumulada": (s + len(idx)) * k / max(1, bits_acum),
        })

    # ---- selección controlada del modo ----
    tam_dicc = -(-U * v // 8)
    tam_huff = -(-int((cnt * lens).sum()) // 8) + U + tam_dicc if maxlen <= 64 else float("inf")
    tam_strip = -(-n * v // 8)
    modo = "huffman" if tam_huff < tam_strip else "bitstrip"

    if modo == "huffman":
        codes, _ = codigos_canonicos(lens)
        secciones = [lens.astype(np.uint8).tobytes(), extraer_bits(uniq, var_idx),
                     empaquetar_codigos(inv, codes, lens)]
    else:
        secciones = [b"", b"", extraer_bits(rows, var_idx)]
    header = {
        "k": k, "orig_len": int(len(raw)), "n": n, "U": U, "modo": modo, "perdida": perdida,
        "mascara_var": np.packbits(~const).tobytes().hex(),
        "valores_const": np.packbits(cvals).tobytes().hex(),
        "sha256": hashlib.sha256(data.tobytes()).hexdigest(),
        "secciones": [len(x) for x in secciones],
    }
    hb_json = json.dumps(header).encode()
    with open(salida, "wb") as f:
        f.write(MAGIC + struct.pack("<I", len(hb_json)) + hb_json)
        for x in secciones:
            f.write(x)
    t_cod = time.time() - t0
    tam_final = 8 + len(hb_json) + sum(len(x) for x in secciones)

    # ---- DESPUÉS: decodificar, verificar y medir ----
    t1 = time.time()
    rec = decodificar(salida, None, silencioso=True)
    t_dec = time.time() - t1
    rec_rows = a_simbolos(rec, k)
    flujo = np.frombuffer(b"".join(secciones[2:]), np.uint8)
    H8 = entropia(np.bincount(flujo, minlength=256)[np.bincount(flujo, minlength=256) > 0]) if len(flujo) else 0.0
    despues = {
        "modo_elegido": modo,
        "tamano_original_B": int(len(raw)), "tamano_codificado_B": tam_final,
        "razon_compresion": len(raw) / tam_final, "ahorro_%": 100 * (1 - tam_final / len(raw)),
        "bits_por_simbolo_real": tam_final * 8 / n,
        "L_media_huffman": Lmed, "eficiencia_H_sobre_L": antes_H(cnt) / Lmed,
        "redundancia_codigo_L_menos_H": Lmed - antes_H(cnt),
        "kraft_suma": float(np.sum(2.0 ** -lens)),
        "long_max_codigo": maxlen,
        "tamano_diccionario_B": tam_dicc, "tamano_estimado_huffman_B": tam_huff,
        "tamano_estimado_bitstrip_B": tam_strip,
        "H_flujo_codificado_bits_por_byte": H8,
        "KL_flujo_vs_uniforme_256": 8 - H8,
        "verificacion_sha256": hashlib.sha256(rec.tobytes()).hexdigest() == header["sha256"],
        "sin_perdida_exacta": bool(np.array_equal(rec, raw)),
        "tiempo_codificacion_s": t_cod, "tiempo_decodificacion_s": t_dec,
    }
    if perdida:
        co, cr = cuentas_dict(rows_orig), cuentas_dict(rec_rows)
        despues["KL_original_vs_reconstruido"] = kl_suavizada(co, cr)
        mse = float(np.mean((raw.astype(float) - rec.astype(float)) ** 2))
        despues["MSE_por_byte"] = mse
        despues["PSNR_dB"] = float("inf") if mse == 0 else 10 * math.log10(255 ** 2 / mse)
    else:
        despues["KL_original_vs_reconstruido"] = 0.0 if despues["sin_perdida_exacta"] else None

    imprimir(entrada, antes, durante, despues)
    if reporte:
        with open(reporte, "w", encoding="utf-8") as f:
            json.dump({"antes": antes, "durante": durante, "despues": despues}, f, indent=2, ensure_ascii=False)
    if grafica:
        graficar(grafica, k, durante, hb, cnt, antes, despues)
    return antes, durante, despues


def antes_H(cnt):
    return entropia(cnt)


# ───────────────────────── decodificar ─────────────────────────
def decodificar(entrada, salida, silencioso=False):
    with open(entrada, "rb") as f:
        blob = f.read()
    if blob[:4] != MAGIC:
        raise ValueError("no es un archivo TIC1")
    hl = struct.unpack("<I", blob[4:8])[0]
    h = json.loads(blob[8:8 + hl])
    k, n, U = h["k"], h["n"], h["U"]
    p = 8 + hl
    s1, s2, s3 = h["secciones"]
    sec_l, sec_d, sec_p = blob[p:p + s1], blob[p + s1:p + s1 + s2], blob[p + s1 + s2:p + s1 + s2 + s3]
    var = np.unpackbits(np.frombuffer(bytes.fromhex(h["mascara_var"]), np.uint8))[:k].astype(bool)
    cvals = np.unpackbits(np.frombuffer(bytes.fromhex(h["valores_const"]), np.uint8))[:k]
    var_idx = np.flatnonzero(var)
    if h["modo"] == "huffman":
        lens = np.frombuffer(sec_l, np.uint8).astype(np.int64)
        uniq = insertar_bits(sec_d, U, k, var_idx, cvals)
        rows = uniq[decodificar_huffman(sec_p, n, lens)]
    else:
        rows = insertar_bits(sec_p, n, k, var_idx, cvals)
    out = rows.ravel()[:h["orig_len"]]
    ok = hashlib.sha256(out.tobytes()).hexdigest() == h["sha256"]
    if salida:
        out.tofile(salida)
    if not silencioso:
        print(f"Decodificado {n} símbolos de {k} bits → {len(out)} bytes | SHA-256 {'OK' if ok else 'FALLÓ'}")
    return out


# ───────────────────────── barrido de k ─────────────────────────
def barrido(entrada, ks):
    raw = np.fromfile(entrada, dtype=np.uint8)
    print(f"\nArchivo: {entrada}  ({len(raw):,} bytes)\n")
    cab = f"{'k':>6} {'N':>10} {'U':>10} {'H':>10} {'H/k':>7} {'log2N':>7} {'KL(P‖U)':>10} {'bits red.':>9} {'razón':>7}  estructura"
    print(cab); print("─" * len(cab))
    filas = []
    for k in ks:
        rows = a_simbolos(raw, k)
        m, _, _, cnt, _, _, const = medir(rows, k)
        lens = longitudes_huffman(cnt)
        v = m["bits_variables"]
        huff = -(-int((cnt * lens).sum()) // 8) + len(cnt) + -(-len(cnt) * v // 8)
        strip = -(-len(rows) * v // 8)
        razon = len(raw) / min(huff, strip)
        print(f"{k:>6} {m['N_simbolos']:>10,} {m['alfabeto_observado_U']:>10,} {m['H_bits_por_simbolo']:>10.3f} "
              f"{m['H_por_bit']:>7.4f} {m['cota_muestral_log2N']:>7.2f} {m['KL_P_vs_uniforme_k']:>10.2f} "
              f"{m['bits_constantes_redundantes']:>9} {razon:>7.3f}  {m['estructura']}")
        filas.append({**m, "razon_estimada": razon})
    return filas


# ───────────────────────── generador de fuentes de prueba ─────────────────────────
def generar(tipo, salida, mb, semilla=0):
    rng = np.random.default_rng(semilla)
    n = int(mb * 1024 * 1024)
    if tipo == "uniforme":
        d = rng.integers(0, 256, n, dtype=np.uint8)
    elif tipo == "no_uniforme":
        p = 1.0 / np.arange(1, 257) ** 1.3
        d = rng.choice(256, n, p=p / p.sum()).astype(np.uint8)
    elif tipo == "estructurado":
        # 16 bloques de 256 B que se repiten: redundancia sólo visible con k grandes
        dic = rng.integers(0, 256, (16, 256), dtype=np.uint8)
        d = dic[rng.integers(0, 16, -(-n // 256))].ravel()[:n].copy()
        d[::4096] ^= 1  # algo de ruido
    else:
        raise ValueError("tipo: uniforme | no_uniforme | estructurado")
    d.tofile(salida)
    print(f"Generado {salida}: {n:,} bytes, fuente {tipo}")


# ───────────────────────── salida ─────────────────────────
def imprimir(nombre, a, d, z):
    f = lambda x: ("sí" if x else "no") if isinstance(x, bool) else f"{x:,.4f}" if isinstance(x, float) else f"{x:,}" if isinstance(x, int) else str(x)
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
    for r in (d[:3] + [None] + d[-3:]) if len(d) > 6 else d:
        if r is None:
            print("     ..."); continue
        print(f"  {r['bloque']:>6} {r['H_bloque']:>10.4f} {r['L_bloque']:>10.4f} "
              f"{r['KL_bloque_vs_global']:>13.5f} {r['razon_acumulada']:>11.3f}")
    print("\n[DESPUÉS]")
    for c, v in z.items():
        print(f"  {c:32} {f(v)}")


def graficar(ruta, k, d, hb, cnt, a, z):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))
    b = [r["bloque"] for r in d]
    ax[0, 0].plot(b, [r["H_bloque"] for r in d], label="H bloque")
    ax[0, 0].plot(b, [r["L_bloque"] for r in d], label="L Huffman")
    ax[0, 0].set_title("Durante: entropía vs longitud media"); ax[0, 0].set_xlabel("bloque")
    ax[0, 0].set_ylabel("bits/símbolo"); ax[0, 0].legend()
    ax[0, 1].plot(b, [r["KL_bloque_vs_global"] for r in d], color="tab:red")
    ax[0, 1].set_title("Durante: D_KL(bloque ‖ global)"); ax[0, 1].set_xlabel("bloque"); ax[0, 1].set_ylabel("bits")
    ax[1, 0].plot(hb, lw=0.6)
    ax[1, 0].set_title(f"Antes: entropía por posición de bit ({a['bits_constantes_redundantes']} bits redundantes)")
    ax[1, 0].set_xlabel("posición de bit en el símbolo"); ax[1, 0].set_ylabel("H(bit)"); ax[1, 0].set_ylim(-0.05, 1.05)
    p = np.sort(cnt)[::-1] / cnt.sum()
    ax[1, 1].loglog(np.arange(1, len(p) + 1), p)
    ax[1, 1].set_title("Antes: rango-frecuencia de símbolos"); ax[1, 1].set_xlabel("rango"); ax[1, 1].set_ylabel("p")
    fig.suptitle(f"k={k} | H={a['H_bits_por_simbolo']:.3f} | razón={z['razon_compresion']:.3f} | modo={z['modo_elegido']}")
    fig.tight_layout(); fig.savefig(ruta, dpi=130)
    print(f"\nGráfica guardada en {ruta}")


# ───────────────────────── CLI ─────────────────────────
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
        codificar(x.entrada, x.salida, x.k, x.perdida, x.bloques, x.grafica, x.reporte)
    elif x.cmd == "decodificar":
        decodificar(x.entrada, x.salida)
    elif x.cmd == "barrido":
        ks = [int(v) for v in x.ks.split(",")] if x.ks else K_BASE + (K_EXT if x.extendido else [])
        barrido(x.entrada, ks)
    else:
        generar(x.tipo, x.salida, x.mb)


if __name__ == "__main__":
    main()
