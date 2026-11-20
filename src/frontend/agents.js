"use strict";
// Agentes page: per-snapshot agent activity; follows the position broadcast by Planta unless a snapshot is pinned.

const REASON = {
  no_text_needed: "No hace falta ningún texto: no hay avisos nuevos o salen por plantilla.",
  investigator_only: "Cierre de turno sin avisos: solo se revisa la bitácora.",
  proposals: "Cierre de turno: se revisa la bitácora y el coordinador decide sobre las propuestas.",
  text_needed: "Hay avisos que necesitan texto.",
};
const LANE = { code: "code", investigator: "inv", coordinator: "coord" };
const AGENT_NAME = { investigator: "Investigador", coordinator: "Coordinador" };
const view = { pinned: null, mode: "live", at: 0, data: null, token: 0, timer: null, sig: "", busy: false, error: null };
const channel = typeof BroadcastChannel === "function" ? new BroadcastChannel(CHANNEL) : null;

function renderBanners(p) {
  const list = [];
  if (view.error) list.push(banner("err", view.error));
  if (view.busy) list.push(banner("warn", "Registro ocupado, reintentando"));
  if (p) {
    if (p.trace_error) list.push(banner("err", `Traza ilegible: ${p.trace_error}`));
    const held = heldoutText(p.heldout);
    if (held) list.push(banner("info", held));
  }
  document.getElementById("banners").replaceChildren(...list);
}

function renderNow(p) {
  const el = document.getElementById("now");
  el.replaceChildren(h("div", { class: "nowi" }, h("span", { class: "lbl" }, "Posición"),
    h("span", { class: "val" }, `${p.at} de ${p.latest}`, " ", h("small", {}, view.pinned ? `fijado en ${view.pinned}` : "siguiendo a Planta"))));
  const live = view.mode === "live";
  setLive(live ? "En vivo" : "Repetición", live ? "on" : "replay");
}

function renderKpis(p) {
  const k = p.kpis;
  document.getElementById("akpis").replaceChildren(
    kpiCard("Investigador", k.investigator, "snapshots con revisión de bitácora", null),
    kpiCard("Coordinador", k.coordinator, "snapshots con textos o decisiones", null),
    kpiCard("Bloqueos de hooks", k.hook_blocks, "acciones frenadas por el código", k.hook_blocks > 0 ? "warn" : null),
    kpiCard("Costo del modelo", costText(k.cost), costHint(k.cost), null));
}

function pin(sid) {
  view.pinned = sid;
  history.replaceState(null, "", `#${sid}`);
  refresh();
}

function unpin() {
  view.pinned = null;
  history.replaceState(null, "", "/agentes");
  refresh();
}

function renderSteps(p) {
  const sel = p.selected ? p.selected.snapshot_id : null;
  document.getElementById("steps").replaceChildren(...p.snapshots.map((e) => {
    const tags = [];
    if (e.agents.includes("investigator")) tags.push(h("span", { class: "tag inv" }, "Investigador"));
    if (e.agents.includes("coordinator")) tags.push(h("span", { class: "tag coord" }, "Coordinador"));
    if (e.hook_blocks) tags.push(h("span", { class: "tag hook" }, `${e.hook_blocks} bloqueo${e.hook_blocks > 1 ? "s" : ""}`));
    if (!e.traced) tags.push(h("span", { class: "tag none" }, "Sin traza"));
    else if (!e.agents.length) tags.push(h("span", { class: "tag none" }, "Solo código"));
    if (e.previous_attempts > 0) tags.push(h("span", { class: "tag retry" }, `${e.previous_attempts} intento${e.previous_attempts > 1 ? "s" : ""} previo${e.previous_attempts > 1 ? "s" : ""}`));
    const li = h("li", { class: "step" + (e.snapshot_id === sel ? " sel" : "") + (e.agents.length ? "" : " quiet") },
      h("div", { class: "st-top" }, h("b", {}, e.snapshot_id), h("span", { class: "muted" }, e.turno_id || ""),
        h("span", { class: "st-usd" }, e.model_calls ? usd(e.usd) : "")),
      h("div", { class: "st-tags" }, tags));
    li.addEventListener("click", () => pin(e.snapshot_id));
    return li;
  }));
  document.getElementById("follow").className = "ghost small" + (view.pinned ? "" : " on");
}

function bubble(lane, kind, title, ...body) {
  return h("div", { class: `bub lane-${LANE[lane] || "code"} ${kind || ""}` }, h("div", { class: "bt" }, title), ...body);
}

function quote(text, src) {
  return h("blockquote", {}, text, src ? h("cite", {}, `Bitácora ${src}`) : null);
}

function errLine(e) {
  return e.is_error ? h("div", { class: "errline" }, `Error devuelto al agente: ${e.error}`) : null;
}

function logbookBubble(e) {
  const title = `Leyó la bitácora ${e.turno_id || "?"}`;
  if (!e.logbook) {
    return bubble(e.lane, e.is_error ? "bad" : "", title, h("p", { class: "muted" }, e.note || "no disponible"), errLine(e));
  }
  const pre = h("div", { class: "logbook" }, e.logbook.segments.map((sg) => (sg.mark ? h("mark", {}, sg.text) : sg.text)));
  const marks = e.logbook.segments.filter((sg) => sg.mark).length;
  return bubble(e.lane, e.is_error ? "bad" : "", title,
    h("details", { class: "lb" }, h("summary", {}, `Ver bitácora completa${marks ? ` · ${marks} cita${marks > 1 ? "s" : ""} resaltada${marks > 1 ? "s" : ""}` : ""}`), pre), errLine(e));
}

function proposalBubble(e) {
  const p = e.proposal && typeof e.proposal === "object" ? e.proposal : {};
  const kv = [];
  if (p.categoria) kv.push(h("span", {}, "Causa ", h("b", {}, label(p.categoria))));
  if (p.etapa) kv.push(h("span", {}, "Etapa ", h("b", {}, label(p.etapa))));
  if (p.modelo) kv.push(h("span", {}, "Alcance ", h("b", {}, [p.modelo, p.mercado || "todos los mercados"].join(" · "))));
  if (p.estado_causa) kv.push(h("span", {}, "Estado ", h("b", {}, label(p.estado_causa))));
  if (p.causa_activa) kv.push(h("span", {}, "Causa activa ", h("b", {}, label(p.causa_activa))));
  const what = { raise: "subir la severidad", set_cause: "asignar causa", lift: "levantar la causa" }[p.tipo] || label(p.tipo);
  return bubble(e.lane, "prop", `Propuesta ${p.id || ""}: ${what}`,
    kv.length ? h("div", { class: "kvline" }, kv) : null,
    p.fragmento ? quote(p.fragmento, p.bitacora) : h("code", {}, JSON.stringify(e.proposal)));
}

function toolBubble(e) {
  const err = errLine(e);
  switch (e.name) {
    case "apply_proposal":
      return bubble(e.lane, e.is_error ? "bad" : "", `Aplicó la propuesta ${e.proposal || "?"}`, err);
    case "emit_alert":
      return bubble(e.lane, "say alert", `Escribió la alerta inmediata · ${e.case_id || "?"}`, h("p", { class: "said" }, e.texto || ""), err);
    case "emit_shift_report":
      return bubble(e.lane, "say", "Escribió las novedades del informe de turno",
        e.items.map((x) => h("div", { class: "said-item" }, h("small", {}, x.case_id || "?"), h("p", { class: "said" }, x.texto || ""))), err);
    default:
      return bubble(e.lane, e.is_error ? "bad" : "", `Llamó a ${e.name}`, h("code", {}, e.arguments_json), err);
  }
}

function hookBubble(e) {
  const who = e.agent === "coordinator" ? "del coordinador" : "del investigador";
  return bubble("code", "hook", `Hook «${label(e.hook)}» bloqueó ${e.tool || "una acción"} ${who}`,
    h("p", { class: "errline" }, e.reason_es || e.reason),
    e.reason_es ? h("code", {}, e.reason) : null,
    h("small", { class: "muted" }, "El bloqueo vuelve al agente como error y el agente sigue sin esa acción."));
}

function eventNode(e) {
  switch (e.kind) {
    case "decision": {
      const names = e.agents.map((a) => AGENT_NAME[a] || a).join(" y ");
      return bubble("code", "", "Decisión del código",
        h("p", {}, REASON[e.decision_reason] || label(e.decision_reason) || label(e.decision)),
        e.required ? h("p", { class: "muted" }, `Avisos que necesitan texto: ${e.required}`) : null,
        names ? h("p", { class: "arrow" }, `→ llama a ${names}`) : h("p", { class: "arrow" }, "→ solo código, sin agentes"));
    }
    case "thinking":
      return bubble(e.lane, "think", "Razonamiento", e.texts.map((t) => h("p", { class: "thought" }, t)));
    case "logbook_read":
      return logbookBubble(e);
    case "proposal":
      return proposalBubble(e);
    case "no_proposals":
      return bubble(e.lane, "", "No encontró causas nuevas", h("p", { class: "muted" }, "Sin cita, no hay causa: queda no_declarada."));
    case "control_error":
      return bubble("code", "hook", "El código rechazó una propuesta", e.messages.map((m) => h("p", { class: "errline" }, m)));
    case "validation":
      return bubble("code", "ok", "Propuestas validadas contra las reglas",
        e.applied.length ? h("p", {}, `Aplicables: ${e.applied.join(", ")}`) : null,
        e.declined.length ? h("p", { class: "errline" }, `Rechazadas: ${e.declined.join(", ")}`) : null,
        h("p", { class: "arrow" }, "→ el coordinador decide si aplicarlas"));
    case "tool_call":
      return toolBubble(e);
    case "hook_block":
      return hookBubble(e);
    case "agent_cost":
      return h("div", { class: `meter lane-${LANE[e.lane] || "code"}` }, `${e.model_calls} llamadas · ${usd(e.usd)}`);
    case "registration":
      return bubble("code", "ok", "Registro de avisos",
        h("p", {}, `${e.agent} con texto del agente · ${e.template} con texto de plantilla`),
        e.report_id ? h("p", { class: "muted" }, `Informe ${e.report_id} guardado`) : null);
    default:
      return bubble(e.lane || "code", "", label(e.kind), h("code", {}, JSON.stringify(e)));
  }
}

const CODE_KINDS = new Set(["decision", "control_error", "validation", "hook_block", "registration"]);

function laneOf(e) {
  return CODE_KINDS.has(e.kind) ? "code" : LANE[e.lane] ? e.lane : "code";
}

// Consecutive events of one lane form a turn; each turn gets its own row so order reads top to bottom.
function turns(events) {
  const out = [];
  for (const e of events) {
    const lane = laneOf(e);
    const prev = out[out.length - 1];
    if (prev && prev.lane === lane) prev.events.push(e);
    else out.push({ lane, events: [e] });
  }
  return out.map((t) => h("div", { class: "trow" },
    h("div", { class: `turn lane-${LANE[t.lane]}` }, t.events.map(eventNode))));
}

function renderConvo(p) {
  const sel = p.selected;
  document.getElementById("convo-title").textContent = sel ? `Conversación · ${sel.snapshot_id}` : "Conversación";
  const sub = [];
  if (sel) {
    sub.push(`${sel.model_calls} llamadas al modelo · ${usd(sel.usd)}`);
    if (sel.previous_attempts > 0) sub.push(`${sel.previous_attempts} intentos previos`);
  }
  document.getElementById("convo-sub").textContent = sub.join(" · ");
  let nodes;
  if (!sel) {
    const text = view.pinned ? `El snapshot ${view.pinned} no está disponible en esta posición.` : "Todavía no hay snapshots procesados.";
    nodes = [h("div", { class: "empty" }, text)];
  } else if (!sel.events.length) {
    nodes = [h("div", { class: "empty" }, "Este snapshot no tiene traza de agentes.")];
  } else {
    nodes = turns(sel.events);
  }
  document.getElementById("convo").replaceChildren(...nodes);
}

function render(p) {
  renderNow(p);
  renderBanners(p);
  const sig = JSON.stringify(p);
  if (sig === view.sig) return;
  view.sig = sig;
  renderKpis(p);
  renderSteps(p);
  renderConvo(p);
}

function url() {
  const q = [];
  if (!view.pinned && view.mode === "replay") q.push(`at=${view.at}`);
  if (view.pinned) q.push(`snapshot=${view.pinned}`);
  return "/api/agents" + (q.length ? `?${q.join("&")}` : "");
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

function readHash() {
  const sid = location.hash.slice(1);
  if (SID.test(sid)) view.pinned = sid;
}

document.addEventListener("DOMContentLoaded", () => {
  readHash();
  document.getElementById("follow").addEventListener("click", unpin);
  window.addEventListener("hashchange", () => {
    readHash();
    refresh();
  });
  if (channel) {
    channel.addEventListener("message", (ev) => {
      const m = ev.data;
      if (!m || (m.mode !== "live" && m.mode !== "replay") || !Number.isInteger(m.at)) return;
      if (m.mode === view.mode && m.at === view.at) return;
      view.mode = m.mode;
      view.at = m.at;
      if (!view.pinned) refresh();
    });
  }
  refresh();
});
