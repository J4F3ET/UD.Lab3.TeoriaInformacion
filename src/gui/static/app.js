// Interfaz del códec TIC: una sola página con 4 vistas que consumen la API de src/app.py.
// Sin dependencias: las gráficas se dibujan con SVG y divs para que funcione sin internet.
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const SVG = "http://www.w3.org/2000/svg";

// Estado de la sesión: la fuente activa, el último barrido, la elección de la IA y el último .tic.
const estado = { fuente: null, barrido: null, ia: null, tic: null, conjunto: "base" };

// ═════════ formato ═════════
const nf = (dec) => new Intl.NumberFormat("es-CO", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const num = (x, dec = 3) => (x === null || x === undefined ? "—" : nf(dec).format(x));
const ent = (x) => (x === null || x === undefined ? "—" : nf(0).format(x));
const bytes = (x) => `${ent(x)} B`;
const seg = (x) => `${num(x, 2)} s`;

function el(tag, attrs = {}, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const h of hijos) e.append(h);
  return e;
}

function svgEl(tag, attrs = {}) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

const ICONO_OK = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#56D27A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>';
const ICONO_MAL = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#FF8A80" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/></svg>';

// ═════════ API ═════════
async function api(ruta, cuerpo) {
  const opciones = { method: "POST" };
  if (cuerpo instanceof FormData) opciones.body = cuerpo;
  else {
    opciones.headers = { "Content-Type": "application/json" };
    opciones.body = JSON.stringify(cuerpo);
  }
  const r = await fetch(ruta, opciones);
  let datos = null;
  try { datos = await r.json(); } catch { /* respuesta no JSON (p. ej. 413) */ }
  if (!r.ok) throw new Error(datos?.error || `Error ${r.status} en ${ruta}`);
  return datos;
}

let temporizadorToast;
function avisar(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(temporizadorToast);
  temporizadorToast = setTimeout(() => (t.hidden = true), 7000);
}

// Ejecuta una llamada larga mostrando el indicador y deshabilitando los botones dados.
async function ocupado(indicador, botones, fn) {
  $(indicador).hidden = false;
  botones.forEach((b) => (b.disabled = true));
  try {
    return await fn();
  } catch (e) {
    avisar(e.message);
  } finally {
    $(indicador).hidden = true;
    botones.forEach((b) => (b.disabled = false));
  }
}

// ═════════ navegación ═════════
function mostrar(vista) {
  for (const b of $$(".pestanas button")) b.setAttribute("aria-selected", String(b.dataset.vista === vista));
  for (const v of $$("main > .vista")) v.hidden = v.id !== `v-${vista}`;
  window.scrollTo({ top: 0 });
}
$$("[data-vista]").forEach((b) => b.addEventListener("click", () => mostrar(b.dataset.vista)));
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ir]");
  if (b) mostrar(b.dataset.ir);
});

// ═════════ 1 · Fuente ═════════
function fijarFuente(meta) {
  estado.fuente = meta;
  estado.barrido = null;
  estado.ia = null;
  $("#res-ia").hidden = true;
  actualizarSugerencias();
  $("#fuente-nombre").textContent = meta.nombre;
  $("#fuente-origen").textContent = meta.origen === "subido" ? "Fuente activa · subida" : "Fuente activa · sintética";
  $("#fuente-tamano").textContent = bytes(meta.tamano_B);
  $("#fuente-tipo").textContent = meta.tipo;
  $("#fuente-sha").textContent = `${meta.sha256.slice(0, 12)}…`;
  $("#fuente-sha").title = meta.sha256;
  $("#ficha-fuente").hidden = false;
  $("#marca-sub").textContent = `${meta.nombre} · ${bytes(meta.tamano_B)}`;
  $$("[data-sin-fuente]").forEach((x) => (x.hidden = true));
  $("#res-barrido").hidden = true;
  $("#res-codificar").hidden = true;
}

async function subirFuente(archivo) {
  if (!archivo) return;
  const fd = new FormData();
  fd.append("archivo", archivo);
  const meta = await ocupado("#carga-subir", [], () => api("/api/subir", fd));
  if (meta) fijarFuente(meta);
}

function zonaArrastre(zona, input, alSoltar) {
  input.addEventListener("change", () => { alSoltar(input.files[0]); input.value = ""; });
  zona.addEventListener("dragover", (e) => { e.preventDefault(); zona.classList.add("encima"); });
  zona.addEventListener("dragleave", () => zona.classList.remove("encima"));
  zona.addEventListener("drop", (e) => {
    e.preventDefault();
    zona.classList.remove("encima");
    alSoltar(e.dataTransfer.files[0]);
  });
}
zonaArrastre($("#zona-fuente"), $("#archivo-fuente"), subirFuente);

$("#form-generar").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const boton = e.target.querySelector("button");
  const meta = await ocupado("#carga-subir", [boton], () =>
    api("/api/generar", { tipo: f.get("tipo"), mb: Number(f.get("mb")), semilla: Number(f.get("semilla")) }));
  if (meta) fijarFuente(meta);
});

// ═════════ 2 · Barrido ═════════
$$("[data-conjunto]").forEach((b) => b.addEventListener("click", () => {
  estado.conjunto = b.dataset.conjunto;
  $$("[data-conjunto]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  $("#campo-ks").hidden = estado.conjunto !== "propia";
}));

$("#btn-barrido").addEventListener("click", async () => {
  if (!estado.fuente) return mostrar("fuente");
  const cuerpo = { id: estado.fuente.id };
  if (estado.conjunto === "propia") {
    const ks = $("#ks-propia").value.split(/[\s,;]+/).filter(Boolean).map(Number);
    if (!ks.length || ks.some((k) => !Number.isInteger(k) || k <= 0 || k % 8)) {
      return avisar("La lista propia debe tener múltiplos positivos de 8, p. ej. 8, 64, 2048");
    }
    cuerpo.ks = ks;
  } else cuerpo.conjunto = estado.conjunto;
  const r = await ocupado("#carga-barrido", [$("#btn-barrido")], () => api("/api/barrido", cuerpo));
  if (r) pintarBarrido(r);
});

function pintarBarrido(r) {
  estado.barrido = r;
  const filas = r.resultados;
  const maxRazon = Math.max(...filas.map((f) => f.razon_estimada));
  const cols = `repeat(${filas.length}, minmax(0, 1fr))`;

  const barras = $("#barrido-barras");
  const ejes = $("#barrido-ejes");
  barras.style.gridTemplateColumns = ejes.style.gridTemplateColumns = cols;
  barras.replaceChildren();
  ejes.replaceChildren();
  for (const f of filas) {
    const mejor = f.k_bits === r.mejor_k;
    const plano = !mejor && f.razon_estimada < 1.005;  // sin ganancia
    const barra = el("div");
    barra.style.height = `${Math.max(2, (f.razon_estimada / maxRazon) * 200)}px`;
    barras.append(el("div", { class: `col${mejor ? " mejor" : ""}${plano ? " plano" : ""}`, title: `k = ${f.k_bits}` },
      el("span", { text: num(f.razon_estimada) }), barra));
    const esIA = estado.ia && f.k_bits === estado.ia.k_ia;
    ejes.append(el("span", { class: esIA ? "ia" : mejor ? "mejor" : "", text: esIA ? `${f.k_bits} · IA` : f.k_bits }));
  }
  $("#barrido-tiempo").textContent = `${filas.length} valores de k · ${seg(r.tiempo_s)}`;

  const tbody = $("#barrido-tabla");
  tbody.replaceChildren();
  for (const f of filas) {
    const mejor = f.k_bits === r.mejor_k;
    const estructura = el("td", { class: "izq", text: f.estructura });
    if (mejor) estructura.append(el("span", { class: "pastilla", text: "mejor" }));
    if (estado.ia && f.k_bits === estado.ia.k_ia) estructura.append(el("span", { class: "pastilla ia", style: "margin-left: 8px;", text: "IA" }));
    tbody.append(el("tr", { class: mejor ? "mejor" : "" },
      el("td", { class: "k", text: f.k_bits }),
      el("td", { text: ent(f.N_simbolos) }),
      el("td", { text: ent(f.alfabeto_observado_U) }),
      el("td", { text: num(f.H_bits_por_simbolo) }),
      el("td", { text: num(f.H_por_bit) }),
      el("td", { text: num(f.KL_P_vs_uniforme_k, 2) }),
      el("td", { text: f.bits_constantes_redundantes }),
      el("td", { class: "razon", text: num(f.razon_estimada) }),
      estructura,
      el("td", {}, el("button", { class: "enlace", type: "button", text: "Codificar", onclick: () => irACodificar(f.k_bits) })),
    ));
  }
  $("#res-barrido").hidden = false;
  actualizarSugerencias();
}

function irACodificar(k) {
  $("#form-codificar").elements.k.value = k;
  mostrar("codificar");
}

// ═════════ IA: bandido UCB (src/tic_bandido.py) ═════════
$("#btn-ia").addEventListener("click", async () => {
  if (!estado.fuente) return mostrar("fuente");
  const r = await ocupado("#carga-ia", [$("#btn-ia"), $("#btn-barrido")], () => api("/api/ia", { id: estado.fuente.id }));
  if (r) pintarIA(r);
});
$("#btn-codificar-ia").addEventListener("click", () => estado.ia && irACodificar(estado.ia.k_ia));

function pintarIA(r) {
  estado.ia = r;
  const p = r.parametros;
  const pol = r.resumen_politicas;
  $("#ia-k").textContent = r.k_ia;
  $("#ia-sub").textContent =
    `${p.bloques} bloques de ${ent(p.bloque_B / 1024)} KB · γ = ${num(p.gamma, 2)} · c = ${num(p.c, 2)} · ${seg(r.tiempo_s)}` +
    (p.bytes_analizados < estado.fuente.tamano_B ? ` · analiza los primeros ${bytes(p.bytes_analizados)}` : "");
  const dato = (etq, valor, ayuda) => el("div", { title: ayuda }, el("dt", { text: etq }), el("dd", { text: valor }),
    el("dd", { class: "ayuda", text: ayuda }));
  const optima = pol["óptimo"].razon_global;
  $("#ia-datos").replaceChildren(
    dato("Razón IA", num(pol.bandido.razon_global), `${num((100 * pol.bandido.razon_global) / optima, 0)} % del techo`),
    dato("Razón óptima por bloque", num(optima), "techo: mejor k en cada bloque"),
    dato("k fijo = 8", num(pol["k fijo = 8"].razon_global), "sin IA, k mínimo"),
    dato("Aleatoria", num(pol.aleatoria.razon_global), "k al azar en cada bloque"),
    dato("Barridos de reinicio", pol.bandido.barridos_reinicio, "veces que detectó un cambio"),
  );

  // Exploración: los primeros len(ks) bloques prueban cada k una vez; después, cada bloque
  // en que no elige su k favorito es exploración. Ese porcentaje es el equivalente práctico de ε.
  const nIni = Math.min(p.ks.length, r.secuencia.length);
  const resto = r.secuencia.slice(nIni);
  const explora = resto.filter((s) => s.k_bandido !== r.k_ia).length;
  const aciertos = resto.filter((s) => s.k_bandido === s.k_optimo).length;
  const pct = (a, b) => (b ? `${num((100 * a) / b, 0)} %` : "—");
  $("#ia-exploracion").replaceChildren(
    tarjeta("Exploración inicial", `${nIni} bloques`, "prueba cada k una vez"),
    tarjeta("Exploración observada (≈ ε)", pct(explora, resto.length), `${explora} de ${resto.length} bloques sin su k favorito`),
    tarjeta("Aciertos tras explorar", pct(aciertos, resto.length), `${aciertos} de ${resto.length} con el mejor k del bloque`),
    tarjeta("c · γ", `${num(p.c, 2)} · ${num(p.gamma, 2)}`, `curiosidad · olvido (memoria ≈ ${ent(1 / (1 - p.gamma))} bloques)`, "medio"),
  );
  $("#btn-codificar-ia").textContent = `Codificar con k = ${r.k_ia}`;

  let nota = `La IA elige un k por bloque usando solo la razón que mide el códec: explora cada k una vez y luego se queda con el que mejor le rinde. ` +
    `«k de la IA» es el que más eligió en la segunda mitad del flujo; el óptimo más frecuente por bloque fue k = ${r.k_optimo_bloques}.`;
  if (estado.barrido && estado.barrido.mejor_k !== r.k_ia) {
    nota += ` El barrido sobre el archivo completo prefiere k = ${estado.barrido.mejor_k}: con el archivo entero hay más repeticiones para los k grandes que dentro de un bloque.`;
  }
  $("#ia-nota").textContent = nota;

  $("#res-ia").hidden = false;
  pintarLineaTiempoIA(r);
  if (estado.barrido) pintarBarrido(estado.barrido);
  actualizarSugerencias();
}

// Una fila por k (eje y en escala log2) y una columna por bloque.
function pintarLineaTiempoIA(r) {
  const svg = $("#ia-svg");
  const ancho = Math.max(svg.clientWidth, 300);
  const alto = 252;
  svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
  svg.replaceChildren();
  const ks = r.parametros.ks;
  const fila = alto / ks.length;
  const y = (k) => alto - (ks.indexOf(k) + 0.5) * fila;
  const n = r.secuencia.length;
  const x = (b) => ((b + 0.5) / n) * ancho;
  // Franja de la exploración inicial (un bloque por k).
  const nIni = Math.min(ks.length, n);
  svg.append(svgEl("rect", { x: 0, y: 0, width: (nIni / n) * ancho, height: alto, fill: "rgba(196,161,255,0.08)", stroke: "rgba(196,161,255,0.4)", "stroke-dasharray": "4 3" }));
  const etiqueta = svgEl("text", { x: 6, y: 14, fill: "#C4A1FF", "font-size": 11, "font-family": "IBM Plex Sans, sans-serif" });
  etiqueta.textContent = "exploración inicial";
  svg.append(etiqueta);
  for (const k of ks) svg.append(svgEl("line", { x1: 0, y1: y(k), x2: ancho, y2: y(k), stroke: "#262D38" }));
  const radio = Math.max(2, Math.min(5, (ancho / n) * 0.35));
  for (const s of r.secuencia) {
    svg.append(svgEl("circle", { cx: x(s.bloque), cy: y(s.k_optimo), r: radio + 2, fill: "none", stroke: "#5AA9FF", "stroke-width": 1.5 }));
    svg.append(svgEl("circle", { cx: x(s.bloque), cy: y(s.k_bandido), r: radio, fill: "#C4A1FF" }));
    if (s.barrido_reinicio) {
      const cx = x(s.bloque);
      svg.append(svgEl("path", { d: `M${cx - 4},${alto} L${cx + 4},${alto} L${cx},${alto - 8} Z`, fill: "#C9D1D9" }));
    }
  }
  const aciertos = r.secuencia.filter((s) => s.k_bandido === s.k_optimo).length;
  svg.setAttribute("aria-label", `k elegido por la IA en ${n} bloques; coincide con el óptimo en ${aciertos}`);
  $("#ia-y").replaceChildren(...[...ks].reverse().map((k) => el("span", { text: k })));
  $("#ia-x").replaceChildren(el("span", { text: "0" }), el("span", { text: Math.floor((n - 1) / 2) }), el("span", { text: n - 1 }));
  $("#ia-x-titulo").textContent = `bloque del archivo (${ent(r.parametros.bloque_B / 1024)} KB cada uno) · ${aciertos} de ${n} con el mejor k`;
}

// Atajos en Codificar para usar el k de la IA o el del barrido.
function actualizarSugerencias() {
  const caja = $("#sugerencias");
  const botones = [];
  if (estado.ia) botones.push(el("button", { type: "button", class: "ia", text: `IA: k = ${estado.ia.k_ia}`, onclick: () => irACodificar(estado.ia.k_ia) }));
  if (estado.barrido) botones.push(el("button", { type: "button", text: `barrido: k = ${estado.barrido.mejor_k}`, onclick: () => irACodificar(estado.barrido.mejor_k) }));
  caja.replaceChildren(el("span", { text: "Sugerencias:" }), ...botones);
  caja.hidden = botones.length === 0;
}

// ═════════ 3 · Codificar ═════════
$("#form-codificar").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!estado.fuente) return mostrar("fuente");
  const f = new FormData(e.target);
  const k = Number(f.get("k"));
  if (!Number.isInteger(k) || k <= 0 || k % 8) return avisar("k debe ser múltiplo positivo de 8");
  const cuerpo = { id: estado.fuente.id, k, perdida: Number(f.get("perdida")), bloques: Number(f.get("bloques")) };
  const r = await ocupado("#carga-codificar", [e.target.querySelector("button")], () => api("/api/codificar", cuerpo));
  if (r) pintarCodificacion(r);
});

function tarjeta(etq, valor, pie, clase = "") {
  return el("div", { class: "tarjeta" },
    el("div", { class: "etq", text: etq }),
    el("div", { class: `valor ${clase}`, text: valor }),
    el("div", { class: "pie", text: pie }));
}

function pintarCodificacion(r) {
  const { antes: a, durante: d, despues: z } = r.reporte;
  const ok = z.verificacion_sha256;

  // banner de resultado
  const banner = $("#cod-banner");
  banner.className = `banner ${ok ? "ok" : "mal"}`;
  banner.innerHTML = `<div class="estado">${ok ? ICONO_OK : ICONO_MAL}<div><b></b><small></small></div></div>`;
  banner.querySelector("b").textContent = ok ? "SHA-256 verificado" : "SHA-256 FALLÓ";
  banner.querySelector("small").textContent = `${z.sin_perdida_exacta ? "Idéntico byte a byte" : "Reconstrucción con pérdida controlada"} · modo ${z.modo_elegido}`;
  const bloque = (etq, valor, clase) => el("div", {}, el("div", { class: "etq", text: etq }), el("div", { class: clase, text: valor }));
  banner.append(
    bloque("Razón", num(z.razon_compresion), "grande"),
    bloque("Ahorro", `${num(z["ahorro_%"], 2)} %`, "grande"),
    bloque("Tamaño", `${ent(z.tamano_original_B)} → ${bytes(z.tamano_codificado_B)}`, "mono"),
    el("div", { class: "acciones" },
      el("a", { class: "boton claro", href: r.tic.url, text: "Descargar .tic" }),
      el("a", { class: "boton borde", href: r.reporte_json.url, text: "Reporte JSON" })),
  );

  // ANTES
  $("#antes-sub").textContent = `la fuente, k = ${a.k_bits} · N = ${ent(a.N_simbolos)} símbolos`;
  const antes = [
    tarjeta("Entropía H", num(a.H_bits_por_simbolo), `bits/símbolo de ${a.k_bits}`),
    tarjeta("Redundancia R", num(a.redundancia_R), "1 − H/k"),
    tarjeta("KL(P‖U)", num(a.KL_P_vs_uniforme_k), "bits vs. uniforme en k"),
    tarjeta("Alfabeto U", ent(a.alfabeto_observado_U), `N/U = ${num(a.fiabilidad_N_sobre_U, 1)}`),
    tarjeta("Bits constantes", `${a.bits_constantes_redundantes} / ${a.k_bits}`, `I entre bits ${num(a.informacion_mutua_entre_bits)}`),
    tarjeta("Estructura", a.estructura.split(" (")[0], a.estructura.includes("(") ? a.estructura.split(" (")[1].replace(")", "") : "", "texto"),
  ];
  if (a.tras_cuantizar) {
    antes.push(tarjeta("H tras cuantizar", num(a.tras_cuantizar.H_bits_por_simbolo), `U = ${ent(a.tras_cuantizar.alfabeto_observado_U)}`));
  }
  $("#antes-tarjetas").replaceChildren(...antes);

  pintarPerfil(r.entropia_por_bit);
  pintarRangoFrecuencia(r.rango_frecuencia);
  pintarDurante(d);

  // DESPUÉS
  const despues = [
    tarjeta("Eficiencia η = H/L̄", num(z.eficiencia_H_sobre_L, 4), `L̄ = ${num(z.L_media_huffman)} bits`),
    tarjeta("I(X;Y)", num(z.I_XY), z.sin_perdida_exacta ? "= H: sin pérdida" : "< H: con pérdida"),
    tarjeta("H flujo codificado", num(z.H_flujo_codificado_bits_por_byte), "bits/byte de 8"),
    tarjeta("Kraft · L máx", `${num(z.kraft_suma, 1)} · ${z.long_max_codigo}`, "código prefijo"),
    tarjeta("Huffman vs bitstrip", `${z.tamano_estimado_huffman_B === null ? "∞" : ent(z.tamano_estimado_huffman_B)} / ${ent(z.tamano_estimado_bitstrip_B)}`, "bytes estimados", "medio"),
    tarjeta("Tiempo", `${num(z.tiempo_codificacion_s, 2)} / ${num(z.tiempo_decodificacion_s, 2)} s`, "codificar / decodificar", "medio"),
  ];
  const conPerdida = "MSE_por_byte" in z;
  if (conPerdida) {
    despues.push(
      tarjeta("MSE por byte", num(z.MSE_por_byte, 4), "error cuadrático medio"),
      tarjeta("PSNR", z.PSNR_dB === null ? "∞" : `${num(z.PSNR_dB, 2)} dB`, "10·log10(255²/MSE)"),
      tarjeta("KL(orig‖rec)", num(z.KL_original_vs_reconstruido, 4), "bits"),
    );
  }
  $("#despues-tarjetas").replaceChildren(...despues);
  $("#aviso-perdida").hidden = conPerdida;

  // el .tic queda listo para la vista Decodificar
  estado.tic = { id: estado.fuente.id, ...r.tic };
  $("#ultimo-tic-nombre").textContent = r.tic.nombre;
  $("#ultimo-tic-tamano").textContent = bytes(r.tic.tamano_B);
  $("#ultimo-tic").hidden = false;

  $("#res-codificar").hidden = false;
}

// Barras de H(bit) por posición; en naranja las casi constantes (H < 0,05).
function pintarPerfil(h) {
  const svg = $("#perfil-svg");
  svg.replaceChildren();
  const k = h.length;
  const ancho = 1000 / k;
  const hueco = k <= 64 ? ancho * 0.2 : 0;
  let casiConstantes = 0;
  h.forEach((v, i) => {
    const bajo = v < 0.05;
    if (bajo) casiConstantes++;
    const alto = Math.max(2, v * 220);
    svg.append(svgEl("rect", { x: i * ancho + hueco / 2, y: 220 - alto, width: Math.max(ancho - hueco, 0.5), height: alto, fill: bajo ? "#F0A04B" : "#5AA9FF" }));
  });
  svg.setAttribute("aria-label", `Entropía de cada una de las ${k} posiciones de bit; ${casiConstantes} casi constantes`);
  $("#perfil-sub").textContent = `${casiConstantes} de ${k} posiciones casi constantes (naranja)`;
  const marcas = [0, Math.round(k / 4), Math.round(k / 2), Math.round((3 * k) / 4), k - 1];
  $("#perfil-ejes").replaceChildren(...marcas.map((m) => el("span", { text: m })));
}

// Curva log-log de probabilidad por rango (Zipf: recta descendente).
function pintarRangoFrecuencia(puntos) {
  const svg = $("#rf-svg");
  svg.replaceChildren(...lineasGuia());
  const lx = puntos.map(([r]) => Math.log10(r));
  const ly = puntos.map(([, p]) => Math.log10(p));
  const xMax = Math.max(lx[lx.length - 1], 1);
  const yMax = Math.ceil(Math.max(...ly));
  const yMin = Math.min(Math.floor(Math.min(...ly)), yMax - 1);
  const pts = puntos.map((_, i) => `${(lx[i] / xMax) * 1000},${220 - ((ly[i] - yMin) / (yMax - yMin)) * 220}`).join(" ");
  svg.append(svgEl("polyline", { points: pts, fill: "none", stroke: "#5AA9FF", "stroke-width": 2, "vector-effect": "non-scaling-stroke" }));
  svg.setAttribute("aria-label", `Probabilidad de cada símbolo según su rango, de 1 a ${ent(puntos[puntos.length - 1][0])}`);
  $("#rf-sub").textContent = `${ent(puntos[puntos.length - 1][0])} símbolos distintos`;
  $("#rf-y").replaceChildren(el("span", { text: `1e${yMax}` }), el("span", { text: `1e${Math.round((yMax + yMin) / 2)}` }), el("span", { text: `1e${yMin}` }));
  $("#rf-x").replaceChildren(el("span", { text: "rango 1" }), el("span", { text: ent(Math.round(10 ** (xMax / 2))) }), el("span", { text: ent(Math.round(10 ** xMax)) }));
}

function lineasGuia() {
  return [0, 73, 147, 220].map((y) => svgEl("line", { x1: 0, y1: y, x2: 1000, y2: y, stroke: y === 220 ? "#3A4453" : "#262D38", "vector-effect": "non-scaling-stroke" }));
}

// H y L̄ por bloque comparten el eje izquierdo; la razón acumulada usa el derecho.
function pintarDurante(d) {
  const svg = $("#durante-svg");
  svg.replaceChildren(...lineasGuia());
  const n = d.length;
  const x = (i) => (n > 1 ? (i / (n - 1)) * 1000 : 500);
  const hl = d.flatMap((b) => [b.H_bloque, b.L_bloque]);
  let [lo, hi] = [Math.floor(Math.min(...hl)), Math.ceil(Math.max(...hl))];
  if (hi === lo) hi = lo + 1;
  const razones = d.map((b) => b.razon_acumulada);
  let [rlo, rhi] = [Math.min(...razones), Math.max(...razones)];
  const margen = Math.max((rhi - rlo) * 0.1, 0.05);
  rlo -= margen; rhi += margen;

  const linea = (valores, a, b, color, extra = {}) => svgEl("polyline", {
    points: valores.map((v, i) => `${x(i)},${220 - ((v - a) / (b - a)) * 220}`).join(" "),
    fill: "none", stroke: color, "stroke-width": 2, "vector-effect": "non-scaling-stroke", ...extra,
  });
  svg.append(
    linea(d.map((b) => b.L_bloque), lo, hi, "#F0A04B"),
    linea(d.map((b) => b.H_bloque), lo, hi, "#5AA9FF"),
    linea(razones, rlo, rhi, "#C9D1D9", { "stroke-width": 1.5, "stroke-dasharray": "6 4" }),
  );
  const ultima = razones[n - 1];
  svg.setAttribute("aria-label", `Entropía y longitud media por bloque; la razón acumulada termina en ${num(ultima)}`);

  const ticks = (a, b, dec) => [b, a + ((b - a) * 2) / 3, a + (b - a) / 3, a].map((v) => el("span", { text: num(v, dec) }));
  $("#durante-y").replaceChildren(...ticks(lo, hi, hi - lo < 6 ? 1 : 0));
  $("#durante-y2").replaceChildren(...ticks(rlo, rhi, 2));
  $("#durante-sub").textContent = `${n} bloques consecutivos del archivo`;

  const kl = d.map((b) => b.KL_bloque_vs_global);
  const iMax = kl.indexOf(Math.max(...kl));
  $("#durante-nota").textContent =
    `KL(bloque‖global) máxima en el bloque ${iMax} (${num(kl[iMax])} bits)` +
    `${kl[iMax] > 1 ? ": el archivo no es estacionario" : ""}; la razón acumulada termina en ${num(ultima)}.`;
}

// ═════════ 4 · Decodificar ═════════
function pintarDecodificacion(r) {
  const c = r.cabecera;
  const fila = (etq, valor, ancho) => el("div", { class: ancho ? "ancho" : "" }, el("dt", { text: etq }), el("dd", { text: valor }));
  $("#cab-datos").replaceChildren(
    fila("k", `${c.k} bits`), fila("Modo", c.modo),
    fila("N símbolos", ent(c.n)), fila("Alfabeto U", ent(c.U)),
    fila("Longitud original", bytes(c.orig_len)), fila("Pérdida", `${c.perdida} LSB`),
    fila("Secciones (longitudes · diccionario · flujo)", `${c.secciones.map(ent).join(" · ")} B`, true),
    fila("SHA-256 guardado", c.sha256, true),
  );
  $("#cab-datos").hidden = false;
  $("#cab-vacia").hidden = true;

  const ok = r.verificacion_sha256;
  const banner = $("#dec-banner");
  banner.className = `banner ${ok ? "ok" : "mal"}`;
  banner.innerHTML = `<div class="estado">${ok ? ICONO_OK : ICONO_MAL}<div><b></b><small></small></div></div>`;
  banner.querySelector("b").textContent = ok ? "SHA-256 OK" : "SHA-256 FALLÓ: el reconstruido no coincide con la huella";
  banner.querySelector("small").textContent = `${ent(c.n)} símbolos de ${c.k} bits → ${bytes(r.tamano_reconstruido_B)}`;
  banner.append(el("div", {}, el("div", { class: "etq", text: "Tiempo" }), el("div", { class: "mono", text: seg(r.tiempo_s) })));
  if ("identico_al_original" in r) {
    banner.append(el("div", {}, el("div", { class: "etq", text: "Frente al original" }),
      el("div", { class: "mono", text: r.identico_al_original ? "idéntico" : `distinto (pérdida ${c.perdida} LSB)` })));
  }
  banner.append(el("div", { class: "acciones" }, el("a", { class: "boton claro", href: r.reconstruido.url, text: "Descargar reconstruido" })));
  banner.hidden = false;
}

async function decodificar(cuerpo) {
  const r = await ocupado("#carga-decodificar", [$("#btn-decodificar")], () => api("/api/decodificar", cuerpo));
  if (r) pintarDecodificacion(r);
}

zonaArrastre($("#zona-tic"), $("#archivo-tic"), (archivo) => {
  if (!archivo) return;
  const fd = new FormData();
  fd.append("archivo", archivo);
  decodificar(fd);
});
$("#btn-decodificar").addEventListener("click", () => {
  if (estado.tic) decodificar({ id: estado.tic.id, tic: estado.tic.nombre });
});
