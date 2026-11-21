"use strict";
// Métricas page: cost, tokens, cache, latency, days, authors, noise, accuracy and runs; follows the position Planta broadcasts.
// Python builds every value; this file only lays the given numbers out as text and SVG geometry.

const view = { follow: "planta", mode: "live", at: 0, data: null, token: 0, timer: null, sig: "", busy: false, error: null };
const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel(CHANNEL) : null;
const CHART_W = 600;
const CHART_H = 120;
const RUN_STATUS = { ok: "Completa", aborted: "Abortada", interrupted: "Interrumpida", running: "En curso o sin informe" };
const MODE_LABEL = { agent: "Agentes", thresholds_only: "Solo umbrales" };
const HELD_NAMES = [
  ["snapshots", "snapshots"], ["notices", "avisos"], ["trace_lines", "líneas de traza"],
  ["evals", "evaluaciones"], ["run_reports", "informes de ejecución"],
];
const SECTION_LABEL = { alerts: "Alertas", news: "Novedades", causes: "Causas" };
const RESULT_LABEL = {
  hit: "acierto", missing: "faltante", extra: "sobrante", unscored: "sin evaluar", wrong_snapshot: "snapshot equivocado",
  duplicates: "duplicadas", missing_report: "informe faltante", unscored_report: "informe sin evaluar",
  motivo_mismatch: "motivo distinto", estado_mismatch: "estado distinto", severidad_mismatch: "severidad distinta",
  maxima_mismatch: "máxima distinta", target_missing: "caso faltante", categoria_mismatch: "categoría distinta",
  etapa_mismatch: "etapa distinta", evidence_missing: "evidencia faltante", evidence_not_loaded: "evidencia no cargada",
  evidence_not_available: "evidencia no disponible", evidence_not_verbatim: "evidencia no literal",
};
const AUTHOR_LABEL = { agent: "Texto del coordinador", template: "Texto de plantilla", unknown: "Autor sin traza" };
const AUTHOR_CLS = { agent: "c-coord", template: "c-tpl", unknown: "c-unk" };

const usd8 = (v) => `US$ ${v}`;
const num = (v) => (v === null || v === undefined ? null : Number(v));

function heldText(heldout) {
  const o = heldout && heldout.omitted;
  if (!o) return null;
  const parts = HELD_NAMES.filter(([k]) => o[k] > 0).map(([k, name]) => `${o[k]} ${name}`);
  return parts.length ? `Bloque reservado cerrado: se omitieron ${parts.join(", ")}` : null;
}

function renderBanners(p) {
  const list = [];
  if (view.error) list.push(banner("err", view.error));
  if (view.busy) list.push(banner("warn", "Registro ocupado, reintentando"));
  if (p) {
    if (p.registry === "missing") list.push(banner("info", "Registro no encontrado: todavía no hay datos"));
    if (p.trace_error) list.push(banner("err", `Traza ilegible: ${p.trace_error}`));
    const held = heldText(p.heldout);
    if (held) list.push(banner("info", held));
  }
  document.getElementById("banners").replaceChildren(...list);
}

function renderNow(p) {
  const following = view.follow === "planta";
  const small = following ? "siguiendo a Planta" : "en vivo";
  document.getElementById("now").replaceChildren(h("div", { class: "nowi" }, h("span", { class: "lbl" }, "Posición"),
    h("span", { class: "val" }, `${p.at} de ${p.latest}`, " ", h("small", {}, small))));
  const replay = following && view.mode === "replay";
  setLive(replay ? "Repetición" : "En vivo", replay ? "replay" : "on");
  const btn = document.getElementById("follow");
  btn.textContent = following ? "Seguir en vivo" : "Seguir a Planta";
  btn.className = "ghost small" + (following ? "" : " on");
}

function renderKpis(p) {
  const c = p.cost;
  const t = c.totals;
  let none = null;
  if (c.state === "thresholds_only") none = "Sin costo de modelo";
  else if (c.state === "trace_error") none = "Traza no disponible";
  const nz = p.noise.state === "ok" ? String(p.noise.errors) : "—";
  document.getElementById("mkpis").replaceChildren(
    kpiCard("Costo del modelo", t ? usd8(t.usd) : "—", none || "acumulado hasta la posición", null),
    kpiCard("Llamadas al modelo", t ? String(t.model_calls) : "—", none || "coordinador e investigador", null),
    kpiCard("Caché", t && t.cache_pct !== null ? `${t.cache_pct} %` : "—", none || "% del prompt leído de caché (entrada + caché)", null),
    kpiCard("Latencia del modelo", t ? `${numFmt.format(t.latency_ms)} ms` : "—", none || "suma de las llamadas al modelo (no es tiempo de reloj)", null),
    kpiCard("Ruido en vivo", nz, "informes repetidos y alertas duplicadas hasta la posición", p.noise.state === "ok" && p.noise.errors > 0 ? "warn" : null));
}

// Axis top rounded up to 1, 2, 2.5 or 5 times a power of ten; integer charts keep a whole midpoint.
function niceTop(v, int) {
  if (!(v > 0)) return int ? 2 : 1;
  const exp = 10 ** Math.floor(Math.log10(v));
  const f = v / exp;
  const top = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * exp;
  return int ? Math.max(2, Math.ceil(top / 2) * 2) : top;
}

// Hand-written SVG bar chart: stacked or grouped bars, an optional line, null drawn as a gap.
// The SVG stretches to its box ('preserveAspectRatio' none), so it holds no text; strokes do not scale.
function chartSvg(o) {
  const n = o.cats.length;
  const slot = CHART_W / n;
  const sums = o.cats.map((c) => {
    const v = c.parts.filter((x) => x !== null);
    return o.stacked ? v.reduce((a, b) => a + b, 0) : Math.max(0, ...v);
  });
  const lines = o.cats.map((c) => (c.line === undefined ? null : c.line));
  const top = o.max || niceTop(Math.max(0, ...sums, ...lines.filter((x) => x !== null)), o.int);
  const y = (v) => CHART_H - (v / top) * CHART_H;
  const nodes = [0.5, 1].map((f) => svgEl("line", { class: "cgrid", x1: 0, x2: CHART_W, y1: y(top * f), y2: y(top * f) }));
  const values = [];
  let gaps = false;
  o.cats.forEach((c, i) => {
    const x0 = i * slot;
    if (c.parts.every((x) => x === null)) {
      gaps = true;
      nodes.push(svgEl("rect", { class: "cgap", x: x0 + slot * 0.15, y: 0, width: slot * 0.7, height: CHART_H }));
      return;
    }
    let acc = 0;
    const k = c.parts.length;
    c.parts.forEach((v, j) => {
      if (v === null) return;
      const cls = `cb ${c.cls || o.series[j].cls}`;
      if (o.stacked) {
        const bw = slot * 0.7;
        if (v > 0) nodes.push(svgEl("rect", { class: cls, x: x0 + slot * 0.15, y: y(acc + v), width: bw, height: y(acc) - y(acc + v) }));
        acc += v;
      } else {
        const span = Math.min(slot * (k > 1 ? 0.8 : 0.6), CHART_W * 0.24);
        const bw = span / k;
        const x = x0 + (slot - span) / 2 + j * bw + (k > 1 ? bw * 0.06 : 0);
        const w = k > 1 ? bw * 0.88 : bw;
        if (v > 0) nodes.push(svgEl("rect", { class: cls, x, y: y(v), width: w, height: CHART_H - y(v) }));
        else nodes.push(svgEl("rect", { class: `${cls} czero`, x, y: CHART_H - 2, width: w, height: 2 }));
        values.push({ x: x + w / 2, v });
      }
    });
  });
  // One transparent column per category on top of the bars: hovering anywhere in it shows the exact numbers.
  const hovers = o.cats.map((c, i) => svgEl("rect", { class: "chov", x: i * slot, y: 0, width: slot, height: CHART_H, "data-tip": c.tip }));
  let d = "";
  let dots = "";
  lines.forEach((v, i) => {
    if (v === null) {
      d += " ";
      return;
    }
    const pen = d === "" || d.endsWith(" ") ? "M" : "L";
    const pt = `${(i + 0.5) * slot},${y(v)}`;
    d += `${pen}${pt}`;
    dots += `M${pt}h0`;
  });
  if (d.trim()) {
    nodes.push(svgEl("path", { class: "cline", d: d.trim(), fill: "none" }));
    nodes.push(svgEl("path", { class: "cdots", d: dots, fill: "none" }));
  }
  nodes.push(svgEl("line", { class: "cbase", x1: 0, x2: CHART_W, y1: CHART_H, y2: CHART_H }));
  nodes.push(...hovers);
  return { svg: svgEl("svg", { viewBox: `0 0 ${CHART_W} ${CHART_H}`, preserveAspectRatio: "none", role: "img", "aria-label": o.title }, nodes), top, gaps, values };
}

// Value labels as page text over the stretched SVG, placed in percent of the plot so they never distort.
function valueLayer(values, top, fmt) {
  return h("div", { class: "vlayer", "aria-hidden": "true" }, values.map(({ x, v }) => {
    const el = h("span", { class: "vlabel" }, fmt(v));
    el.style.left = `${(x / CHART_W) * 100}%`;
    el.style.bottom = `${(v / top) * 100}%`;
    return el;
  }));
}

// One floating tooltip for every chart, shown at once (the native SVG title waits about a second).
const tipBox = h("div", { class: "ctip hidden", role: "tooltip" });

function moveTip(ev) {
  const target = ev.target instanceof Element ? ev.target.closest("[data-tip]") : null;
  if (!target) {
    tipBox.classList.add("hidden");
    return;
  }
  tipBox.textContent = target.getAttribute("data-tip");
  tipBox.classList.remove("hidden");
  const pad = 14;
  const w = tipBox.offsetWidth;
  const left = ev.clientX + pad + w > window.innerWidth ? ev.clientX - pad - w : ev.clientX + pad;
  tipBox.style.left = `${Math.max(4, left)}px`;
  tipBox.style.top = `${ev.clientY + pad}px`;
}

// At most about ten x labels, each centred under its own bar slot.
function xLabels(o) {
  const step = o.labels ? 1 : Math.max(1, Math.ceil(o.cats.length / 10));
  const last = o.cats.length - 1;
  return h("div", { class: "xlabels" + (o.labels ? " cats" : "") },
    o.cats.map((c, i) => h("span", {}, i % step === 0 || (i === last && last % step >= step / 2) ? c.label : "")));
}

function chartPanel(o, fmt) {
  const head = h("div", { class: "panel-head" }, h("h2", {}, o.title), h("span", { class: "muted" }, o.sub || ""));
  if (!o.cats.length) return h("section", { class: "panel chart" }, head, h("div", { class: "empty" }, o.empty || "Sin datos todavía"));
  const { svg, top, gaps, values } = chartSvg(o);
  const keys = o.series.map((s) => h("span", {}, h("i", { class: `sw ${s.cls}${s.line ? " ln" : ""}` }), s.name));
  if (gaps) keys.push(h("span", { class: "gapkey" }, h("i", { class: "sw gap" }), "Sin dato"));
  const yaxis = h("div", { class: "yaxis", "aria-hidden": "true" }, [top, top / 2, 0].map((v) => h("span", {}, fmt(v))));
  const layer = o.labels ? valueLayer(values, top, fmt) : null;
  const plot = h("div", { class: "plot" }, yaxis, svg, layer, xLabels(o));
  return h("section", { class: "panel chart" }, head, h("div", { class: "legend" }, keys), plot);
}

// Horizontal bars with the count at the end: three categories compare better side by side than as columns.
function hbarPanel(title, rows) {
  const top = Math.max(1, ...rows.map((r) => r.value));
  const list = rows.map((r) => h("div", { class: "hrow" },
    h("span", { class: "hl" }, h("i", { class: `sw ${r.cls}` }), r.label),
    svgEl("svg", { class: "hbar", viewBox: "0 0 100 10", preserveAspectRatio: "none", role: "img", "aria-label": r.tip, "data-tip": r.tip },
      svgEl("rect", { class: "htrack", x: 0, y: 0, width: 100, height: 10 }),
      r.value > 0 ? svgEl("rect", { class: `cb ${r.cls}`, x: 0, y: 0, width: (r.value / top) * 100, height: 10 }) : null),
    h("span", { class: "hv" }, String(r.value))));
  return h("section", { class: "panel chart" }, h("div", { class: "panel-head" }, h("h2", {}, title)), h("div", { class: "hbars" }, list));
}

function costNote(c) {
  if (c.state === "thresholds_only") return "Sin costo de modelo";
  if (c.state === "trace_error") return "Traza ilegible: el costo no está disponible";
  return null;
}

function costPanels(p) {
  const c = p.cost;
  const note = costNote(c);
  if (note) {
    return [h("section", { class: "panel chart wide" }, h("div", { class: "panel-head" }, h("h2", {}, "Costo, tokens y latencia")),
      h("div", { class: "empty" }, note))];
  }
  const pts = c.points;
  const cat = (pt, parts, tip, extra) => ({ label: pt.snapshot_id, parts, tip: `${pt.snapshot_id}: ${tip}`, ...extra });
  const unplaced = c.unplaced_usd && Number(c.unplaced_usd) > 0 ? `Sin posición: ${usd8(c.unplaced_usd)}` : "";
  const cost = chartPanel({
    title: "Costo por snapshot", sub: unplaced, stacked: true,
    series: [{ name: "Investigador", cls: "c-inv" }, { name: "Coordinador", cls: "c-coord" }, { name: "Acumulado (línea)", cls: "c-cum", line: true }],
    cats: pts.map((pt) => cat(pt, pt.usd ? [num(pt.usd.investigator), num(pt.usd.coordinator)] : [null, null],
      pt.usd ? `investigador ${usd8(pt.usd.investigator)} · coordinador ${usd8(pt.usd.coordinator)} · acumulado ${usd8(pt.cumulative_usd)}` : `sin traza · acumulado ${usd8(pt.cumulative_usd)}`,
      { line: num(pt.cumulative_usd) })),
  }, (v) => `US$ ${v.toFixed(4)}`);
  const tokens = chartPanel({
    title: "Tokens por snapshot", stacked: true,
    series: [{ name: "Entrada", cls: "c-in" }, { name: "Salida", cls: "c-out" }, { name: "Caché leída", cls: "c-cache" },
      { name: "Escritura caché 5 min", cls: "c-w5" }, { name: "Escritura caché 1 h", cls: "c-w1" }],
    cats: pts.map((pt) => {
      const t = pt.tokens;
      return cat(pt, t ? [t.input, t.output, t.cache_read, t.cache_write_5m, t.cache_write_1h] : [null, null, null, null, null],
        t ? `entrada ${t.input} · salida ${t.output} · caché leída ${t.cache_read} · escritura 5 min ${t.cache_write_5m} · escritura 1 h ${t.cache_write_1h}` : "sin traza");
    }),
  }, (v) => numFmt.format(v));
  const cache = chartPanel({
    title: "Caché leída por snapshot", sub: "% del prompt", stacked: false, max: 100,
    series: [{ name: "Caché leída", cls: "c-cache" }],
    cats: pts.map((pt) => cat(pt, [num(pt.cache_pct)], pt.cache_pct === null ? "sin dato" : `${pt.cache_pct} %`)),
  }, (v) => `${v} %`);
  const latency = chartPanel({
    title: "Latencia del modelo por snapshot", stacked: false,
    series: [{ name: "Milisegundos", cls: "c-lat" }],
    cats: pts.map((pt) => cat(pt, [pt.latency_ms], pt.latency_ms === null ? "sin traza" : `${numFmt.format(pt.latency_ms)} ms`)),
  }, (v) => `${numFmt.format(v)} ms`);
  return [cost, tokens, cache, latency];
}

function dayPanels(p) {
  const days = chartPanel({
    title: "Avisos e informes por día", stacked: false, labels: true, int: true,
    series: [{ name: "Alertas", cls: "c-alert" }, { name: "Informes con novedades", cls: "c-news" }, { name: "Informes sin novedades", cls: "c-calm" }],
    cats: p.days.map((d) => ({
      label: d.label, parts: [d.alerts, d.reports_with_news, d.reports_without_news],
      tip: `${d.label}: ${d.alerts} alertas · ${d.reports} informes (${d.reports_with_news} con novedades, ${d.reports_without_news} sin novedades)`,
    })),
  }, (v) => String(v));
  const order = ["agent", "template", "unknown"];
  const authors = hbarPanel("Textos por autor",
    order.map((k) => ({ label: AUTHOR_LABEL[k], value: p.authors[k], cls: AUTHOR_CLS[k], tip: `${AUTHOR_LABEL[k]}: ${p.authors[k]}` })));
  return [days, authors];
}

function renderCharts(p) {
  document.getElementById("charts").replaceChildren(...costPanels(p), ...dayPanels(p));
}

function renderNoise(p) {
  const n = p.noise;
  let body;
  if (n.state === "invalid") {
    body = [h("div", { class: "empty" }, `No se pudo calcular: salida de avisos inválida (${n.error})`)];
  } else if (!n.errors) {
    body = [h("div", { class: "empty" }, "Sin ruido en los avisos emitidos hasta esta posición")];
  } else {
    body = [h("ul", { class: "noise" },
      n.repeats.map((r) => h("li", {}, `El informe ${r.turno_id} repite el caso ${r.case_id} del informe ${r.previous_turno_id}`)),
      n.duplicate_alerts.map((d) => h("li", {}, `El caso ${d.case_id} tiene ${d.alerts} alertas inmediatas`)))];
  }
  document.getElementById("noise").replaceChildren(
    h("div", { class: "panel-head" }, h("h2", {}, "Ruido en vivo"), h("span", { class: "muted" }, "hasta la posición, sin bloque reservado")), ...body);
}

function counts(o) {
  return Object.entries(o || {}).map(([k, v]) => `${RESULT_LABEL[k] || label(k)}: ${v}`).join(" · ");
}

function accuracyBody(a) {
  if (a.state === "none") {
    return [h("div", { class: "empty" }, "Sin evaluación para este registro"),
      h("p", { class: "muted pad" }, "Para generarla: ", h("code", {}, "uv run python evals/run_eval.py --registry <registro> --golden evals/golden"))];
  }
  if (a.state === "omitted") return [h("div", { class: "empty" }, "Evaluación omitida: incluye el bloque reservado")];
  const s = a.summary;
  let stale = "Vigencia: sin dato";
  let tone = "muted";
  if (a.stale === true) {
    stale = "Evaluación desactualizada";
    tone = "warn";
  } else if (a.stale === false) {
    stale = "Vigente";
    tone = "ok";
  }
  const facts = [
    ["Archivo", a.file], ["Evaluada", a.evaluated_at], ["Entregables evaluados", a.deliverables === null ? "sin dato" : a.deliverables],
    ["Entregables actuales", a.current_deliverables], ["Capacidades", s.capabilities.join(", ") || "—"],
    ["Turnos cubiertos", s.covered_shifts.join(", ") || "—"], ["Ruido evaluado", s.noise_errors],
    ["Errores bloqueantes", s.gating_errors], ["Código de salida", s.exit_code],
  ];
  const rows = Object.entries(s.sections).map(([name, sec]) => h("tr", {}, h("td", {}, SECTION_LABEL[name] || label(name)), h("td", {}, counts(sec.gated)), h("td", {}, counts(sec.not_gated))));
  const extra = [];
  if (a.earlier > 0) extra.push(`${a.earlier} evaluaciones anteriores`);
  if (a.unreadable > 0) extra.push(`${a.unreadable} archivos ilegibles`);
  return [
    h("p", { class: "stale" }, h("span", { class: `pill ${tone}` }, stale), extra.length ? h("small", { class: "muted" }, extra.join(" · ")) : null),
    h("dl", { class: "kv facts2" }, facts.map(([k, v]) => [h("dt", {}, k), h("dd", {}, String(v))])),
    h("table", { class: "act acc" }, h("thead", {}, h("tr", {}, h("th", {}, "Sección"), h("th", {}, "Bloqueantes"), h("th", {}, "No bloqueantes"))), h("tbody", {}, rows)),
  ];
}

function renderAccuracy(p) {
  document.getElementById("accuracy").replaceChildren(
    h("div", { class: "panel-head" }, h("h2", {}, "Exactitud evaluada"), h("span", { class: "muted" }, "última evaluación del registro, no sigue la posición")),
    h("div", { class: "pad" }, ...accuracyBody(p.accuracy)));
}

function renderRuns(p) {
  const r = p.runs;
  const rows = r.items.map((it) => h("tr", {},
    h("td", {}, it.file || "—"), h("td", {}, MODE_LABEL[it.mode] || label(it.mode)), h("td", {}, RUN_STATUS[it.status] || label(it.status)),
    h("td", {}, it.started_at), h("td", { class: "n" }, it.duration_seconds === null ? "—" : `${numFmt.format(it.duration_seconds)} s`)));
  const body = r.items.length
    ? h("table", { class: "act runs" }, h("thead", {}, h("tr", {}, ["Informe", "Modo", "Estado", "Inicio (UTC)", "Duración"].map((t, i) => h("th", { class: i === 4 ? "n" : null }, t)))), h("tbody", {}, rows))
    : h("div", { class: "empty" }, "Sin ejecuciones registradas");
  document.getElementById("runs").replaceChildren(
    h("div", { class: "panel-head" }, h("h2", {}, "Ejecuciones"), h("span", { class: "muted" }, r.unreadable > 0 ? `${r.unreadable} informes ilegibles` : "")),
    h("div", { class: "pad" }, body));
}

function render(p) {
  renderNow(p);
  renderBanners(p);
  const sig = JSON.stringify(p);
  if (sig === view.sig) return;
  view.sig = sig;
  renderKpis(p);
  renderCharts(p);
  renderNoise(p);
  renderAccuracy(p);
  renderRuns(p);
}

function url() {
  return "/api/metrics" + (view.follow === "planta" && view.mode === "replay" ? `?at=${view.at}` : "");
}

async function load() {
  const mine = ++view.token;
  try {
    const r = await getJson(url());
    if (mine !== view.token) return;
    if (r.busy) {
      view.busy = true;
      renderBanners(view.data);
      return;
    }
    view.busy = false;
    view.error = null;
    view.data = r.data;
    render(r.data);
  } catch (e) {
    if (mine !== view.token) return;
    view.busy = false;
    view.error = e.message;
    renderBanners(view.data);
    setLive("Sin conexión", "err");
  }
}

function schedule() {
  clearTimeout(view.timer);
  view.timer = setTimeout(refresh, POLL_MS);
}

async function refresh() {
  clearTimeout(view.timer);
  await load();
  schedule();
}

function toggleFollow() {
  view.follow = view.follow === "planta" ? "live" : "planta";
  view.sig = "";
  refresh();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("follow").addEventListener("click", toggleFollow);
  document.body.append(tipBox);
  document.addEventListener("mousemove", moveTip);
  document.addEventListener("mouseout", (ev) => {
    if (!ev.relatedTarget) tipBox.classList.add("hidden");
  });
  if (channel) {
    channel.addEventListener("message", (ev) => {
      const m = ev.data;
      if (!m || (m.mode !== "live" && m.mode !== "replay") || !Number.isInteger(m.at)) return;
      if (m.mode === view.mode && m.at === view.at) return;
      view.mode = m.mode;
      view.at = m.at;
      if (view.follow === "planta") refresh();
    });
  }
  refresh();
});
