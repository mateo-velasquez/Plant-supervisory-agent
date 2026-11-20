"use strict";
// Planta page: live polling, replay controls and the position broadcast to the Agentes window.

const SPEEDS = { 1: 2000, 2: 1000, 4: 500, 8: 250 };
const AUTHOR = {
  agent: ["agent", "Texto del coordinador"],
  template: ["tpl", "Texto de plantilla"],
  unknown: ["unk", "Autor sin traza"],
};
const ui = { mode: "live", at: 0, playing: false, speed: 1, state: null, token: 0, timer: null, sig: "", busy: false, error: null };
const openIds = new Set();
const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel(CHANNEL) : null;

function stops() {
  return [0, ...(ui.state ? ui.state.positions : [])];
}

// Gap per position as bars from the zero line, newest at the right; null leaves the slot empty, zero is a tick.
function sparkline(series) {
  const n = Math.max(series.length, 12);
  const off = n - series.length;
  const H = 36;
  const svg = svgEl("svg", { class: "spark", viewBox: `0 0 ${n * 10} ${H}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  const vals = series.filter((v) => v !== null);
  const lo = Math.min(0, ...vals);
  const hi = Math.max(0, ...vals);
  const span = hi - lo || 1;
  const y = (v) => 3 + ((H - 6) * (hi - v)) / span;
  const y0 = y(0);
  const bw = n <= 16 ? 5 : 7;
  let last = -1;
  series.forEach((v, i) => {
    if (v !== null) last = i;
  });
  svg.append(svgEl("line", { class: "zero", x1: 0, x2: n * 10, y1: y0.toFixed(2), y2: y0.toFixed(2) }));
  series.forEach((v, i) => {
    if (v === null) return;
    const top = v === 0 ? y0 - 1 : Math.min(y(v), y0);
    const height = v === 0 ? 2 : Math.max(Math.abs(y(v) - y0), 2);
    const cls = "bar" + (v === 0 ? " nil" : "") + (i === last ? " last" : "");
    svg.append(svgEl("rect", { class: cls, x: ((off + i) * 10 + (10 - bw) / 2).toFixed(2), y: top.toFixed(2), width: bw, height: height.toFixed(2) }));
  });
  return svg;
}

function shiftOf(state) {
  return state.current;
}

function renderNow(s) {
  const el = document.getElementById("now");
  const cur = shiftOf(s);
  if (!cur) {
    el.replaceChildren(h("div", { class: "nowi" }, h("span", { class: "lbl" }, "Snapshot"), h("span", { class: "val" }, "Sin snapshots procesados")));
  } else {
    const shift = cur.turno_id ? `${cur.turno_id} ${cur.turno || ""} · ${cur.inicio || ""}–${cur.fin || ""}` : "—";
    el.replaceChildren(
      h("div", { class: "nowi" }, h("span", { class: "lbl" }, "Snapshot"),
        h("span", { class: "val" }, cur.snapshot_id, " ", h("small", {}, `${s.at} de ${s.total}`))),
      h("div", { class: "nowi" }, h("span", { class: "lbl" }, "Turno"), h("span", { class: "val" }, shift)),
      h("div", { class: "nowi" }, h("span", { class: "lbl" }, "Fecha"), h("span", { class: "val" }, cur.fecha || "—")));
  }
  const live = ui.mode === "live";
  setLive(live ? "En vivo" : "Repetición", live ? "on" : "replay");
  document.getElementById("complete").className = "live done" + (s.complete ? "" : " hidden");
}

function renderBanners(s) {
  const list = [];
  if (ui.error) list.push(banner("err", ui.error));
  if (ui.busy) list.push(banner("warn", "Registro ocupado, reintentando"));
  if (s) {
    if (s.registry === "missing") list.push(banner("warn", "Todavía no existe el registro de la corrida"));
    if (s.trace_error) list.push(banner("err", `Traza ilegible: ${s.trace_error}`));
    const held = heldoutText(s.heldout);
    if (held) list.push(banner("info", held));
  }
  document.getElementById("banners").replaceChildren(...list);
}

function snapCell(c, sh, current) {
  const cls = ["snap", c.processed && "done", current === c.snapshot_id && "current", c.alerts > 0 && "alert", c.report && "report"].filter(Boolean).join(" ");
  const shift = [sh.turno_id, sh.turno, sh.inicio && sh.fin ? `${sh.inicio}–${sh.fin}` : null].filter(Boolean).join(" ");
  const tip = [c.snapshot_id, shift, c.alerts > 0 ? `${c.alerts} alerta${c.alerts > 1 ? "s" : ""}` : null, c.report ? "informe emitido" : null].filter(Boolean).join(" · ");
  const b = h("button", { type: "button", class: cls, title: tip, "aria-label": tip }, c.alerts > 1 ? String(c.alerts) : "");
  if (c.seq === null) b.disabled = true;
  else b.addEventListener("click", () => goTo(c.seq));
  return b;
}

function renderDays(s) {
  const cur = s.current ? s.current.snapshot_id : null;
  const box = document.getElementById("days");
  box.className = "days" + (s.days.length > 4 ? " dense" : "");
  box.replaceChildren(...s.days.map((d) => {
    const today = d.shifts.some((sh) => sh.snapshots.some((c) => c.snapshot_id === cur));
    return h("div", { class: "day" + (today ? " today" : "") },
      h("div", { class: "day-h" }, d.label),
      h("div", { class: "day-shifts" }, d.shifts.map((sh) => {
        const active = sh.snapshots.some((c) => c.snapshot_id === cur);
        return h("div", { class: "shift" + (active ? " active" : "") },
          h("div", { class: "snaps" }, sh.snapshots.map((c) => snapCell(c, sh, cur))),
          h("div", { class: "meta" }, h("b", {}, sh.turno_id), h("span", { class: "tn" }, sh.turno || ""),
            h("span", { class: "hrs" }, `${sh.inicio}–${sh.fin}`)));
      })));
  }));
}

function renderKpis(s) {
  const k = s.kpis;
  document.getElementById("kpis").replaceChildren(
    kpiCard("Casos activos", k.active, `de ${k.combinations} combinaciones`, null),
    kpiCard("Críticos", k.critical, k.critical_combinations.join(", ") || "ninguno", k.critical > 0 ? "hot" : null),
    kpiCard("Alertas inmediatas", k.alerts, "una por caso escalado", k.alerts > 0 ? "hot" : null),
    kpiCard("Informes de turno", k.reports, `de ${k.shifts} turnos`, null),
    kpiCard("Costo del modelo", costText(k.cost), costHint(k.cost), null));
}

function renderCell(c) {
  const cs = c.case;
  if (!cs || c.status === "calm") {
    return h("div", { class: "cell calm" },
      h("div", { class: "row1" }, h("span", { class: "chip ok" }, "Sin caso"), h("span", {})),
      h("div", { class: "big" }, h("span", { class: "u" }, "Bajo umbral")),
      sparkline(c.series),
      h("div", { class: "facts" }, "Sin casos hasta este snapshot"));
  }
  const resolved = c.status === "resolved";
  return h("div", { class: `cell ${resolved ? "resolved" : "sev-" + cs.severidad}`, title: cs.case_id },
    h("div", { class: "row1" },
      h("span", { class: "chip" + (cs.estado === "escalado" ? " esc" : resolved ? " ok" : "") }, stateLabel(cs.estado)),
      resolved ? h("span", { class: "muted" }, `en ${cs.resolved_at}`) : h("span", { class: "sevtag" }, sevLabel(cs.severidad))),
    h("div", { class: "big" },
      h("span", { class: "u" }, `${signed(cs.gap_unidades)} u`),
      h("span", { class: "p" }, cs.gap_pct === null ? "" : `${signed(cs.gap_pct)} %`)),
    sparkline(c.series),
    h("div", { class: "facts" },
      h("span", {}, "Cuello ", h("b", {}, label(cs.etapa_cuello) || "—")),
      h("span", {}, "Retraso ", h("b", {}, cs.retraso_dias === null ? "—" : `${numFmt.format(cs.retraso_dias)} d`)),
      h("span", {}, "Causa ", h("b", {}, label(cs.causa), cs.etapa ? ` · ${label(cs.etapa)}` : "")),
      h("span", {}, "Desde ", h("b", {}, cs.opened_at))));
}

function renderMatrix(s) {
  const m = document.getElementById("matrix");
  m.style.setProperty("--cols", String(s.markets.length));
  const kids = [h("div", {}), ...s.markets.map((k) => h("div", { class: "mh" }, k))];
  for (const model of s.models) {
    kids.push(h("div", { class: "mh row" }, model));
    for (const k of s.markets) {
      const cell = s.cells.find((c) => c.modelo === model && c.mercado === k);
      kids.push(cell ? renderCell(cell) : h("div", { class: "cell calm" }));
    }
  }
  m.replaceChildren(...kids);
}

function authorBadge(author) {
  const [cls, text] = AUTHOR[author] || AUTHOR.unknown;
  return h("span", { class: `author ${cls}` }, text);
}

function openAgents(snapshotId) {
  const sid = snapshotId;
  if (!/^S[0-9]{3}$/.test(sid)) return;
  window.open(`/agentes#${sid}`, "agentes");
}

function jump(snapshotId) {
  const b = h("button", { type: "button", class: "jump" }, "Ver agentes ↗");
  b.addEventListener("click", () => openAgents(snapshotId));
  return b;
}

function evidence(list) {
  return (list || []).map((e) => h("blockquote", {}, e.fragmento, h("cite", {}, `Bitácora ${e.bitacora}`)));
}

function noticeDetails(n) {
  return h("dl", { class: "kv" },
    h("dt", {}, "Severidad"), h("dd", {}, `${sevLabel(n.severidad)} (máxima ${sevLabel(n.severidad_maxima)})`),
    h("dt", {}, "Estado"), h("dd", {}, stateLabel(n.estado)),
    h("dt", {}, "Motivo"), h("dd", {}, (n.motivo || []).map(label).join(", ") || "—"),
    h("dt", {}, "Origen"), h("dd", {}, label(n.origen)),
    h("dt", {}, "Causa"), h("dd", {}, label(n.causa.categoria), n.causa.etapa ? ` · ${label(n.causa.etapa)}` : ""),
    h("dt", {}, "Caso"), h("dd", {}, n.case_id));
}

function previewOf(n) {
  return h("p", { class: "preview" + (n.author === "agent" ? " by-agent" : "") }, n.texto);
}

function alertItem(f) {
  return [
    h("summary", {}, h("span", { class: "ico" }, "!"),
      h("div", {}, h("div", { class: "ttl" }, `${f.modelo} × ${f.mercado}`),
        h("div", { class: "sub" }, `Alerta inmediata · ${sevLabel(f.severidad)}`), previewOf(f)),
      h("span", { class: "when" }, f.snapshot_id)),
    h("div", { class: "body" },
      h("div", { class: "row1" }, authorBadge(f.author), jump(f.snapshot_id)),
      h("p", { class: "txt" }, f.texto), noticeDetails(f), ...evidence(f.evidencia)),
  ];
}

const ACTIVE_COLS = [["modelo", "Modelo"], ["mercado", "Mercado"], ["estado", "Estado"], ["severidad", "Sev."], ["gap_unidades", "Gap"], ["gap_pct", "%"], ["retraso_dias", "Retraso"], ["etapa_cuello", "Cuello"]];

function cellValue(key, v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return key === "gap_unidades" || key === "gap_pct" ? signed(v) : numFmt.format(v);
  if (typeof v === "object") return JSON.stringify(v);
  return key === "estado" ? stateLabel(v) : key === "severidad" ? sevLabel(v) : label(v);
}

function activeTable(rows) {
  return h("table", { class: "act" },
    h("thead", {}, h("tr", {}, ACTIVE_COLS.map(([, t]) => h("th", {}, t)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, ACTIVE_COLS.map(([k]) => h("td", { class: typeof r[k] === "number" ? "n" : "" }, cellValue(k, r[k])))))));
}

function reportItem(f) {
  const nov = f.novedades.length;
  const active = f.casos_activos.length;
  const first = nov ? f.novedades[0] : null;
  return [
    h("summary", {}, h("span", { class: "ico" }, "≡"),
      h("div", {}, h("div", { class: "ttl" }, `Informe de turno ${f.turno_id}`),
        h("div", { class: "sub" }, nov ? `${nov} novedad${nov > 1 ? "es" : ""} · ${active} casos activos` : `Sin novedades en este turno · ${active} casos activos`),
        first ? previewOf(first) : null),
      h("span", { class: "when" }, f.snapshot_id)),
    h("div", { class: "body" },
      nov ? h("div", { class: "sec" }, "Novedades") : h("p", { class: "txt muted" }, "Sin novedades en este turno"),
      nov ? h("div", { class: "news" }, f.novedades.map((n) => h("div", { class: `nw sev-${n.severidad}` },
        h("div", { class: "h" }, h("span", {}, `${n.modelo} × ${n.mercado}`), h("span", {}, `${stateLabel(n.estado)} · ${sevLabel(n.severidad)}`)),
        h("p", { class: "txt" }, n.texto),
        h("div", { class: "row1" }, authorBadge(n.author), h("span", {})),
        noticeDetails(n), ...evidence(n.evidencia)))) : null,
      h("div", { class: "row1" }, h("span", {}), jump(f.snapshot_id)),
      active ? h("div", { class: "sec" }, "Casos activos") : null,
      active ? activeTable(f.casos_activos) : null),
  ];
}

function feedItem(f) {
  const key = f.kind === "report" ? f.report_id : f.notice_id;
  const isReport = f.kind === "report";
  const el = h("details", { class: "item " + (isReport ? "report" : "alert"), open: openIds.has(key) }, ...(isReport ? reportItem(f) : alertItem(f)));
  el.addEventListener("toggle", () => (el.open ? openIds.add(key) : openIds.delete(key)));
  return h("li", {}, el);
}

function renderFeed(s) {
  document.getElementById("feed-count").textContent = s.feed.length ? `${s.feed.length} avisos` : "";
  document.getElementById("feed").replaceChildren(...(s.feed.length
    ? s.feed.map(feedItem)
    : [h("li", { class: "empty" }, "Todavía no hay avisos. Aparecen acá a medida que la serie avanza.")]));
}

function renderControls() {
  const s = ui.state;
  const st = stops();
  const idx = Math.max(0, st.indexOf(ui.at));
  const slider = document.getElementById("slider");
  slider.max = String(st.length - 1);
  slider.value = String(idx);
  slider.disabled = st.length < 2;
  document.getElementById("pos").textContent = s ? `${ui.at} de ${s.total}` : "";
  const play = document.getElementById("play");
  play.textContent = ui.playing ? "❚❚" : "▶";
  play.className = "ghost play" + (ui.playing ? " on" : "");
  document.getElementById("back").disabled = idx === 0;
  document.getElementById("fwd").disabled = idx >= st.length - 1;
  document.getElementById("golive").className = "ghost" + (ui.mode === "live" ? " on" : "");
  for (const b of document.querySelectorAll("#speeds button")) b.className = "seg" + (b.dataset.speed === String(ui.speed) ? " on" : "");
}

function render(s) {
  renderNow(s);
  renderBanners(s);
  const sig = JSON.stringify(s);
  if (sig !== ui.sig) {
    ui.sig = sig;
    renderDays(s);
    renderKpis(s);
    renderMatrix(s);
    renderFeed(s);
  }
  renderControls();
}

async function load() {
  const mine = ++ui.token;
  const url = ui.mode === "live" ? "/api/state" : `/api/state?at=${ui.at}`;
  try {
    const r = await getJson(url);
    if (mine !== ui.token) return;
    if (r.busy) {
      ui.busy = true;
      renderBanners(ui.state);
      return;
    }
    ui.busy = false;
    ui.error = null;
    ui.state = r.data;
    ui.at = r.data.at;
    if (ui.playing && ui.at >= r.data.latest) ui.playing = false;
    render(r.data);
    if (channel) channel.postMessage({ mode: ui.mode, at: ui.at });
  } catch (e) {
    if (mine !== ui.token) return;
    ui.busy = false;
    ui.error = e.message;
    renderBanners(ui.state);
    setLive("Sin conexión", "err");
  }
}

function schedule() {
  clearTimeout(ui.timer);
  ui.timer = setTimeout(tick, ui.playing ? SPEEDS[ui.speed] : POLL_MS);
}

async function tick() {
  if (ui.playing) {
    const st = stops();
    const next = st[st.indexOf(ui.at) + 1];
    if (next === undefined) ui.playing = false;
    else ui.at = next;
  }
  await load();
  schedule();
}

async function refresh() {
  clearTimeout(ui.timer);
  await load();
  schedule();
}

function goTo(at) {
  if (!Number.isInteger(at)) return;
  ui.mode = "replay";
  ui.at = at;
  ui.playing = false;
  return refresh();
}

function step(delta) {
  const st = stops();
  const idx = Math.max(0, st.indexOf(ui.at)) + delta;
  if (idx < 0 || idx >= st.length) return;
  goTo(st[idx]);
}

function togglePlay() {
  if (ui.playing) {
    ui.playing = false;
    renderControls();
    return;
  }
  const st = stops();
  const latest = st[st.length - 1];
  if (st.length < 2) return;
  ui.mode = "replay";
  if (ui.at >= latest) ui.at = 0;
  ui.playing = true;
  refresh();
}

function goLive() {
  ui.mode = "live";
  ui.playing = false;
  refresh();
}

function buildSpeeds() {
  const box = document.getElementById("speeds");
  for (const sp of Object.keys(SPEEDS)) {
    const b = h("button", { type: "button", class: "seg", "data-speed": sp }, `${sp}×`);
    b.addEventListener("click", () => {
      ui.speed = Number(sp);
      renderControls();
      if (ui.playing) schedule();
    });
    box.append(b);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  buildSpeeds();
  document.getElementById("back").addEventListener("click", () => step(-1));
  document.getElementById("fwd").addEventListener("click", () => step(1));
  document.getElementById("play").addEventListener("click", togglePlay);
  document.getElementById("golive").addEventListener("click", goLive);
  document.getElementById("slider").addEventListener("input", (e) => {
    const st = stops();
    const at = st[Number(e.target.value)];
    if (at !== undefined) goTo(at);
  });
  tick();
});
