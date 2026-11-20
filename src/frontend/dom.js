"use strict";
// Shared helpers. Stored values reach the DOM only as text nodes; no markup is ever built from strings.

const POLL_MS = 1500;
const CHANNEL = "plant-monitor";
const SVG_NS = "http://www.w3.org/2000/svg";
const BLOCKED_ATTR = /^(on|href|xlink:href|src|style|action|formaction)/i;
const STATE_LABEL = { abierto: "Abierto", en_seguimiento: "En seguimiento", escalado: "Escalado", resuelto: "Resuelto" };
const SEV_LABEL = { ninguna: "ninguna", media: "media", alta: "alta", critica: "crítica" };
const SID = /^S[0-9]{3}$/;
const numFmt = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1 });

function applyAttrs(el, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") {
      el.setAttribute("class", String(v));
      continue;
    }
    if (BLOCKED_ATTR.test(k)) throw new Error(`attribute not allowed: ${k}`);
    el.setAttribute(k, v === true ? "" : String(v));
  }
}

function appendKids(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
}

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  applyAttrs(el, attrs);
  appendKids(el, kids);
  return el;
}

function svgEl(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  applyAttrs(el, attrs);
  appendKids(el, kids);
  return el;
}

const label = (s) => String(s === null || s === undefined ? "" : s).replaceAll("_", " ");
const signed = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + numFmt.format(Math.abs(v));
const usd = (v) => `US$ ${Number(v || 0).toFixed(4)}`;
const sevLabel = (s) => SEV_LABEL[s] || label(s);
const stateLabel = (s) => STATE_LABEL[s] || label(s);

function costText(cost) {
  return cost ? usd(cost.usd) : "—";
}

function costHint(cost) {
  return cost ? `${cost.model_calls} llamadas · ${numFmt.format(cost.tokens)} tokens` : "Traza no disponible";
}

function heldoutText(heldout) {
  const o = heldout && heldout.omitted;
  if (!o || (o.snapshots === 0 && o.notices === 0 && o.trace_lines === 0)) return null;
  return `Bloque reservado cerrado: se omitieron ${o.snapshots} snapshots, ${o.notices} avisos y ${o.trace_lines} líneas de traza`;
}

// Fetches JSON; a 503 gives { busy: true } so the caller keeps its last good payload.
async function getJson(url) {
  let res;
  try {
    res = await fetch(url, { cache: "no-store" });
  } catch (e) {
    throw new Error("Sin conexión con el servidor");
  }
  if (res.status === 503) return { busy: true };
  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    body = null;
  }
  if (!res.ok) throw new Error(body && body.error ? body.error : `Error ${res.status}`);
  return { data: body };
}

function banner(kind, text) {
  return h("div", { class: `banner ${kind}`, role: kind === "err" ? "alert" : "status" }, text);
}

function kpiCard(lbl, num, hint, tone) {
  return h("div", { class: "panel kpi" + (tone ? ` ${tone}` : "") },
    h("div", {}, h("div", { class: "lbl" }, lbl), h("div", { class: "num" }, num), h("div", { class: "hint" }, hint)),
    h("div", { class: "bar" }));
}

function setLive(modeText, tone) {
  document.getElementById("live").className = `live ${tone}`;
  document.getElementById("live-text").textContent = modeText;
}
