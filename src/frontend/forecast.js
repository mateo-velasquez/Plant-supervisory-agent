"use strict";
// Pronóstico page: active early warnings, one small chart per combination and Anticipación; follows the position Planta broadcasts.
// Python builds every value; this file only lays the given numbers out as text and SVG geometry.

const view = { follow: "planta", mode: "live", at: 0, data: null, token: 0, timer: null, sig: "", busy: false, error: null };
const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel(CHANNEL) : null;
const CHART_W = 600;
const CHART_H = 120;
// Smallest vertical span in units, so a flat series does not look like noise blown up to full height.
const MIN_SPAN = 8;
const LEVELS = ["media", "alta", "critica"];
const STATUS_LABEL = {
  warm_up: "Calentando", no_target: "Sin objetivo", suppressed: "Suprimido", no_crossing: "Sin cruce previsto", warning: "Aviso",
};
const OUTCOME_LABEL = { fulfilled: "Cumplido", not_fulfilled: "No cumplido", pending: "Pendiente" };
const OUTCOME_CLS = { fulfilled: "ok", not_fulfilled: "warn", pending: "" };
const COUNT_LABEL = [
  ["fulfilled", "Cumplidos"], ["not_fulfilled", "No cumplidos"], ["pending", "Pendientes"],
  ["missed", "Cruce sin aviso previo"], ["no_forecast", "Cruce sin pronóstico posible"],
];
const HELD_NAMES = [
  ["snapshots", "snapshots"], ["notices", "avisos"], ["trace_lines", "líneas de traza"], ["forecast_rows", "filas de pronóstico"],
];

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
    else if (p.state === "unavailable") list.push(banner("info", "Esta corrida no tiene pronósticos"));
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

// One floating tooltip for every hover or keyboard-focus target, shown at once.
const tipBox = h("div", { class: "ctip hidden", role: "tooltip" });

function placeTip(text, x, y) {
  tipBox.textContent = text;
  tipBox.classList.remove("hidden");
  const pad = 14;
  const w = tipBox.offsetWidth;
  const left = x + pad + w > window.innerWidth ? x - pad - w : x + pad;
  tipBox.style.left = `${Math.max(4, left)}px`;
  tipBox.style.top = `${y + pad}px`;
}

function moveTip(ev) {
  const target = ev.target instanceof Element ? ev.target.closest("[data-tip]") : null;
  if (!target) {
    tipBox.classList.add("hidden");
    return;
  }
  placeTip(target.getAttribute("data-tip"), ev.clientX, ev.clientY);
}

function focusTip(ev) {
  const target = ev.target instanceof Element ? ev.target.closest("[data-tip]") : null;
  if (!target) return;
  const r = target.getBoundingClientRect();
  placeTip(target.getAttribute("data-tip"), r.left, r.bottom - 8);
}

// One fact per line, so the basis reads as a short list instead of a run-on sentence.
function basisTip(w) {
  const b = w.basis;
  const parts = [`ritmo ${b.rate} por snapshot`];
  parts.push(b.plan_per_snapshot === null ? "sin plan en el turno" : `plan ${b.plan_per_snapshot} por snapshot`);
  parts.push(`ventana ${b.window}`);
  if (b.threshold !== null) parts.push(`umbral ${label(w.target_level)} ${b.threshold} u`);
  return parts.join("\n");
}

function renderWarnings(p) {
  const head = h("div", { class: "panel-head" },
    h("div", { class: "fchead" }, h("h2", {}, "Avisos activos"), p.warnings.length ? h("span", { class: "count" }, String(p.warnings.length)) : null),
    h("span", { class: "muted" }, "pasa el cursor para ver la base del cálculo"));
  let body;
  if (!p.warnings.length) {
    body = h("div", { class: "empty fcempty" }, p.state === "ok" ? "Sin avisos activos en esta posición" : "Sin pronósticos");
  } else {
    body = h("ul", { class: "fcwarns" }, p.warnings.map((w) => h("li", { class: `fcwarn ${w.target_level}`, "data-tip": basisTip(w), tabindex: 0 },
      h("div", { class: "fcw-top" },
        h("span", { class: "fcw-name" }, `${w.modelo} · ${w.mercado}`),
        h("span", { class: "fcw-sev" }, `⚠ ${sevLabel(w.target_level)}`)),
      h("span", { class: "fcw-when" }, w.label))));
  }
  document.getElementById("warnings").replaceChildren(head, body);
}

// Step path through the points that carry a value; a missing value or a jump in x breaks the path.
function stepPath(pts, slot, y) {
  let d = "";
  let prev = null;
  for (const pt of pts) {
    if (pt.v === null) {
      prev = null;
      continue;
    }
    const x0 = pt.x - slot / 2;
    const x1 = pt.x + slot / 2;
    d += prev !== null && Math.abs(prev - x0) < 0.001 ? `V${y(pt.v)}H${x1}` : `M${x0},${y(pt.v)}H${x1}`;
    prev = x1;
  }
  return d;
}

function pointTip(pt) {
  const lines = pt.lines ? LEVELS.map((l) => `${sevLabel(l)} ${numFmt.format(-pt.lines[l])}`).join(" · ") : "sin umbrales (plan 0)";
  return `${pt.title}\nbrecha ${signed(pt.gap)} u\numbrales ${lines}`;
}

// Text label placed over the plot at a vertical fraction (0 top, 1 bottom); the SVG itself is stretched, so text lives in HTML.
function plotLabel(cls, text, frac) {
  const el = h("span", { class: cls }, text);
  el.style.top = `${frac * 100}%`;
  return el;
}

function cellHead(c) {
  const name = h("span", { class: "fcc-name" }, `${c.modelo} · ${c.mercado}`);
  if (c.warning) {
    return h("div", { class: "fcc-head" }, name,
      h("span", { class: `fcpill ${c.warning.target_level}` }, `${STATUS_LABEL.warning}: ${sevLabel(c.warning.target_level)} · ${c.warning.label}`));
  }
  return h("div", { class: "fcc-head" }, name, h("span", { class: "fcc-status" }, STATUS_LABEL[c.status] || "Sin fila en esta posición"));
}

function combinationCell(c, at) {
  const cls = "fccell" + (c.warning ? ` warn ${c.warning.target_level}` : "");
  const head = cellHead(c);
  const hist = c.history.map((r) => ({ seq: r.seq, x: 0, gap: r.gap, lines: r.lines, title: r.snapshot_id }));
  const proj = c.projection.map((r, i) => ({ seq: at + 1 + i, x: 0, gap: r.gap, lines: r.lines, title: `${r.snapshot_id} ${r.time} (proyección)` }));
  const all = [...hist, ...proj];
  if (!all.length) return h("div", { class: cls }, head, h("div", { class: "empty" }, "Sin datos todavía"));
  const first = all[0].seq;
  const last = all[all.length - 1].seq;
  const n = last - first + 1;
  const slot = CHART_W / n;
  for (const pt of all) pt.x = (pt.seq - first + 0.5) * slot;
  const vals = all.flatMap((pt) => [pt.gap, ...(pt.lines ? LEVELS.map((l) => pt.lines[l]) : [])]);
  const top = Math.max(0, ...vals);
  const lo = Math.min(top - MIN_SPAN, ...vals);
  const y = (v) => ((top - v) / (top - lo)) * CHART_H;
  const nodes = [];
  // Positions with no stored row are shaded, so a hole in the line reads as missing data, not as a break in the plant.
  const have = new Set(all.map((pt) => pt.seq));
  for (let s = first; s <= last; s += 1) {
    if (!have.has(s)) nodes.push(svgEl("rect", { class: "cgap", x: (s - first) * slot, y: 0, width: slot, height: CHART_H }));
  }
  const edge = hist.length ? (hist[hist.length - 1].seq - first + 1) * slot : 0;
  if (proj.length) {
    nodes.push(svgEl("rect", { class: "fczone", x: edge, y: 0, width: CHART_W - edge, height: CHART_H }));
    nodes.push(svgEl("line", { class: "fcnow", x1: edge, x2: edge, y1: 0, y2: CHART_H }));
  }
  nodes.push(svgEl("line", { class: "fczero", x1: 0, x2: CHART_W, y1: y(0), y2: y(0) }));
  const tags = [];
  const end = [...all].reverse().find((pt) => pt.lines);
  for (const l of LEVELS) {
    const d = stepPath(all.map((pt) => ({ x: pt.x, v: pt.lines ? pt.lines[l] : null })), slot, y);
    if (d) nodes.push(svgEl("path", { class: `fcl ${l}`, d, fill: "none" }));
    if (end) tags.push(plotLabel(`fctag ${l}`, sevLabel(l), y(end.lines[l]) / CHART_H));
  }
  // History is solid and breaks where a position is missing; the projection is dashed and starts at the last history point.
  let hd = "";
  hist.forEach((pt, i) => {
    hd += `${i > 0 && pt.seq === hist[i - 1].seq + 1 ? "L" : "M"}${pt.x},${y(pt.gap)}`;
  });
  if (hd) nodes.push(svgEl("path", { class: "fchist", d: hd, fill: "none" }));
  if (proj.length) {
    const anchor = hist.length && hist[hist.length - 1].seq === at ? [hist[hist.length - 1]] : [];
    const pd = [...anchor, ...proj].map((pt, i) => `${i === 0 ? "M" : "L"}${pt.x},${y(pt.gap)}`).join("");
    nodes.push(svgEl("path", { class: "fcproj", d: pd, fill: "none" }));
    nodes.push(svgEl("path", { class: "fcdots proj", d: proj.map((pt) => `M${pt.x},${y(pt.gap)}h0`).join(""), fill: "none" }));
  }
  if (hist.length) {
    nodes.push(svgEl("path", { class: "fcdots", d: hist.map((pt) => `M${pt.x},${y(pt.gap)}h0`).join(""), fill: "none" }));
    const now = hist[hist.length - 1];
    if (now.seq === at) nodes.push(svgEl("path", { class: "fcdots now", d: `M${now.x},${y(now.gap)}h0`, fill: "none" }));
  }
  for (const pt of all) nodes.push(svgEl("rect", { class: "chov", x: pt.x - slot / 2, y: 0, width: slot, height: CHART_H, "data-tip": pointTip(pt) }));
  const svg = svgEl("svg", { viewBox: `0 0 ${CHART_W} ${CHART_H}`, preserveAspectRatio: "none", role: "img", "aria-label": `${c.modelo} ${c.mercado}` }, nodes);
  const ticks = [0, lo];
  if (top > 0 && top / (top - lo) > 0.18) ticks.unshift(top);
  const yaxis = h("div", { class: "fcy", "aria-hidden": "true" }, ticks.map((v) => plotLabel("", numFmt.format(v), y(v) / CHART_H)));
  const over = h("div", { class: "fcover", "aria-hidden": "true" }, tags);
  const step = Math.max(1, Math.ceil(n / 5));
  // Ticks count back from the last point, so the newest projected snapshot is always labelled and spacing stays even.
  const xl = h("div", { class: "xlabels" }, Array.from({ length: n }, (_, k) => {
    const pt = all.find((q) => q.seq === first + k);
    return h("span", {}, pt && (n - 1 - k) % step === 0 ? pt.title.slice(0, 4) : "");
  }));
  return h("div", { class: cls }, head, h("div", { class: "fcplot" }, yaxis, svg, over, xl));
}

function chartsLegend() {
  return h("div", { class: "legend fclegend" },
    h("span", {}, h("i", { class: "sw ln c-hist" }), "Brecha real"),
    h("span", {}, h("i", { class: "sw ln dash c-proj" }), "Proyección"),
    ...LEVELS.map((l) => h("span", {}, h("i", { class: `sw ln c-${l}` }), `Umbral ${sevLabel(l)}`)));
}

function renderCharts(p) {
  const cells = p.combinations.map((c) => combinationCell(c, p.at));
  const body = cells.length ? h("div", { class: "fcgrid" }, cells) : h("div", { class: "empty fcempty" }, "Sin pronósticos para mostrar");
  document.getElementById("charts").replaceChildren(
    h("div", { class: "panel-head" }, h("h2", {}, "Brecha por combinación"), chartsLegend()), body);
}

function renderAnticipation(p) {
  const a = p.accuracy;
  // Tone only marks counts above zero: green for kept warnings, amber for misses; zero stays quiet.
  const tone = { fulfilled: "ok", not_fulfilled: "warn", missed: "warn" };
  const cards = COUNT_LABEL.map(([k, name]) => h("div", { class: `fcount ${a.counts[k] > 0 ? tone[k] || "" : "zero"}` },
    h("div", { class: "num" }, String(a.counts[k])), h("div", { class: "lbl" }, name)));
  cards.push(h("div", { class: "fcount lead" }, h("div", { class: "num" }, a.mean_lead_hours === null ? "—" : `${a.mean_lead_hours} h`),
    h("div", { class: "lbl" }, "Anticipación media")));
  const rows = a.episodes.map((e) => h("tr", {},
    h("td", { class: "fce-name" }, `${e.modelo} · ${e.mercado}`),
    h("td", {}, h("span", { class: `fclevel ${e.level}` }, sevLabel(e.level))),
    h("td", { class: "fce-id" }, e.first === e.last ? e.first : `${e.first}–${e.last}`),
    h("td", {}, h("span", { class: `pill ${OUTCOME_CLS[e.outcome] || ""}` }, OUTCOME_LABEL[e.outcome] || label(e.outcome))),
    h("td", { class: "fce-id" }, e.crossing === null ? "—" : e.crossing),
    h("td", { class: "n" }, e.lead_hours === null ? "—" : `${e.lead_hours} h`)));
  const table = a.episodes.length
    ? h("div", { class: "tablewrap" }, h("table", { class: "act fceps" },
      h("thead", {}, h("tr", {}, ["Combinación", "Nivel", "Avisos", "Resultado", "Cruce", "Anticipación"].map((t, i) => h("th", { class: i === 5 ? "n" : null }, t)))),
      h("tbody", {}, rows)))
    : h("div", { class: "empty" }, "Sin episodios de aviso hasta esta posición");
  document.getElementById("anticipation").replaceChildren(
    h("div", { class: "panel-head" }, h("h2", {}, "Anticipación"), h("span", { class: "muted" }, "aviso frente al cruce real, hasta la posición")),
    h("div", { class: "pad" }, h("div", { class: "fcounts" }, cards), table));
}

function render(p) {
  renderNow(p);
  renderBanners(p);
  const sig = JSON.stringify(p);
  if (sig === view.sig) return;
  view.sig = sig;
  renderWarnings(p);
  renderCharts(p);
  renderAnticipation(p);
}

function url() {
  return "/api/forecast" + (view.follow === "planta" && view.mode === "replay" ? `?at=${view.at}` : "");
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
  document.addEventListener("focusin", focusTip);
  document.addEventListener("focusout", () => tipBox.classList.add("hidden"));
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
