"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const CODES = ["P1","P2","V1","V2","G1","G2","C1","C2","Z1","Z2"];
const SUBLABEL = {
  saludo:"Saluda", entidad:"Dice el nombre de la entidad", nombre_asesor:"Se presenta con su nombre", menciona_nombre_cliente:"Usa el nombre del cliente",
  solicita_documento:"Pide el documento", cliente_responde_numero:"El cliente da el número", asesor_valida_o_repite:"Repite o valida el número",
  pregunta_examen_orden_requisitos:"Pregunta por examen, orden o requisitos", hold_menor_al_limite:"Esperas menores a 60 s",
  sin_tiempo_muerto_largo:"Sin silencios largos", tiempo_muerto_total_aceptable:"Poco tiempo muerto en total",
  pocas_peticiones_de_repeticion:"No pide repetir demasiado", comprende_la_necesidad:"Entiende lo que necesita el cliente",
  sin_lenguaje_inadecuado:"Sin lenguaje inadecuado", uso_de_cortesia:"Usa palabras de cortesía",
  cita_agendada:"Confirma que quedó agendada", fecha:"Dice la fecha", hora:"Dice la hora", direccion_sede:"Dice la sede o dirección",
  medico_especialista:"Dice el médico o especialista", soportes_a_llevar:"Indica los soportes a llevar", preparacion:"Informa la preparación",
  cancelacion_confirmada:"Confirma la cancelación", pregunta_si_requiere_algo_mas:"Pregunta si necesita algo más", despedida_cordial:"Se despide cordialmente"
};
const TIPO = {nueva_cita:"Solicitud de cita", cancelacion:"Cancelación", confirmacion:"Confirmación de cita", informacion:"Información", desconocido:"Motivo sin identificar"};
let ST = {}, CALLS = [], FILTER = "todas", CUR = null, DRAFT = null, SNAP = "", pollT = null, FLASH_ID = null, FOCUS = null;

const fmt = s => { s = Math.round(s); return `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`; };
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
const icon = id => `<svg class="i"><use href="#i-${id}"/></svg>`;
async function api(path, opt) { const r = await fetch(path, opt); return r.json(); }
function toast(msg, kind = "") {
  const t = $("#toast"); t.className = "toast " + kind; t.innerHTML = kind === "ok" ? icon("check") : ""; t.append(msg);
  t.hidden = true; void t.offsetWidth; t.hidden = false; clearTimeout(t._t); t._t = setTimeout(() => t.hidden = true, 3200);
}

/* ---------------- preferencias (solo en este equipo) ---------------- */
const PREF_KEY = "auditoria.prefs";
const PREF_DEF = { style: "liquid", palette: "oceano", theme: "auto", motion: "completa", size: "normal", defMode: "rapido", auditor: "", after: "lista" };
let PREFS = { ...PREF_DEF };
try { PREFS = { ...PREF_DEF, ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") }; } catch (e) {}
try { if (!localStorage.getItem(PREF_KEY) && matchMedia("(prefers-reduced-motion: reduce)").matches) PREFS.motion = "suave"; } catch (e) {}
function savePrefs() { try { localStorage.setItem(PREF_KEY, JSON.stringify(PREFS)); } catch (e) {} }
function applyPrefs() {
  const d = document.documentElement;
  d.dataset.style = PREFS.style; d.dataset.palette = PREFS.palette; d.dataset.motion = PREFS.motion;
  if (PREFS.theme === "auto") delete d.dataset.theme; else d.dataset.theme = PREFS.theme;
  d.style.setProperty("--fs", PREFS.size === "grande" ? "18px" : "16px");
  requestAnimationFrame(moveGlider);
}
function setPref(k, v) { PREFS[k] = v; savePrefs(); applyPrefs(); renderConfig(); }

const STYLES = [
  ["corporativo", "Corporativo", "Colores y logo de Angiografía de Occidente: azul, amarillo y gris."],
  ["liquid", "Liquid Glass", "Cristal líquido con reflejos y fondo en movimiento."],
  ["glass", "Glassmorfismo", "Paneles esmerilados sobre manchas de color."],
  ["aurora", "Aurora", "Fondo de aurora que cambia de color lentamente."],
  ["neumorph", "Neumorfismo", "Relieve suave, como piezas de un mismo material."],
  ["minimal", "Minimalista", "Plano, limpio y sin sombras."],
  ["clasico", "Clásico", "Tarjetas blancas sobrias. El diseño original."],
];
const PALETTES = [["oceano", "Océano"], ["esmeralda", "Esmeralda"], ["violeta", "Violeta"], ["coral", "Coral"], ["ambar", "Ámbar"], ["grafito", "Grafito"]];
function segment(box, opts, cur, onPick) {
  box.innerHTML = "";
  opts.forEach(([v, l]) => { const b = el("button", v === cur ? "sel" : "", l); b.type = "button"; b.onclick = () => onPick(v); box.appendChild(b); });
}
function renderConfig() {
  const sg = $("#styleGrid"); sg.innerHTML = "";
  STYLES.forEach(([k, n, d]) => {
    const t = el("button", "style-tile" + (PREFS.style === k ? " sel" : "")); t.type = "button"; t.dataset.style = k; t.dataset.palette = PREFS.palette;
    t.innerHTML = `<div class="tile-stage"><span class="tb a"></span><span class="tb b"></span><span class="tb c"></span><div class="tile-card"><i></i><i class="s"></i><span></span></div></div>`;
    t.append(el("b", "", n), el("small", "", d)); t.onclick = () => setPref("style", k); sg.appendChild(t);
  });
  const corp = PREFS.style === "corporativo";
  $("#palGrid").classList.toggle("off", corp); $("#palNote").hidden = !corp;
  const pg = $("#palGrid"); pg.innerHTML = "";
  PALETTES.forEach(([k, n]) => { const s = el("button", "sw" + (PREFS.palette === k ? " sel" : "")); s.type = "button"; s.dataset.palette = k;
    s.append(el("i"), n); s.onclick = () => setPref("palette", k); pg.appendChild(s); });
  segment($("#themeSeg"), [["light", "Claro"], ["dark", "Oscuro"], ["auto", "Automático"]], PREFS.theme, v => setPref("theme", v));
  segment($("#motionSeg"), [["completa", "Completas"], ["suave", "Suaves"], ["off", "Ninguna"]], PREFS.motion, v => setPref("motion", v));
  segment($("#sizeSeg"), [["normal", "Normal"], ["grande", "Grande"]], PREFS.size, v => setPref("size", v));
  segment($("#defModeSeg"), [["rapido", "Rápido"], ["preciso", "Preciso"], ["externa", "IA externa"], ["sin", "Solo reglas"]], PREFS.defMode, v => { setPref("defMode", v); pickMode(v); });
  segment($("#afterSeg"), [["lista", "Volver a la lista"], ["siguiente", "Abrir la siguiente por revisar"]], PREFS.after, v => setPref("after", v));
  const pa = $("#prefAuditor"); if (document.activeElement !== pa) pa.value = PREFS.auditor;
  const si = $("#sysInfo"); si.innerHTML = "";
  const llm = ST.llm || {};
  const ext = ST.external || {};
  [["IA rápida (3B)", llm.rapido ? "Instalada" : "No instalada"], ["IA precisa (7B)", llm.preciso ? "Instalada" : "No instalada"],
   ["IA externa", ext.available ? `${ext.label} · lista` : "Sin clave (ejecute Instalar.bat)"],
   ["Nota para aprobar", (ST.pass_percent ?? 80) + " %"], ["Error crítico", "Solo lo confirma una persona"]].forEach(([k, v]) => {
    const li = el("li"); li.append(el("span", "", k), el("b", "", v)); si.appendChild(li);
  });
}
$("#prefAuditor").oninput = e => { PREFS.auditor = e.target.value.trim(); savePrefs(); };
$("#btnResetPrefs").onclick = () => { const keep = { defMode: PREFS.defMode, auditor: PREFS.auditor, after: PREFS.after };
  PREFS = { ...PREF_DEF, ...keep }; savePrefs(); applyPrefs(); renderConfig(); toast("Diseño original restablecido", "ok"); };
function pickMode(v) { const r = $(`input[name=mode][value="${v}"]`); if (r) r.checked = true; }

/* brillo del cristal que sigue al mouse (solo Liquid Glass) */
document.addEventListener("pointermove", e => {
  if (PREFS.style !== "liquid" || PREFS.motion !== "completa") return;
  const c = e.target.closest?.(".card,.kpi"); if (!c) return;
  const r = c.getBoundingClientRect(); c.style.setProperty("--mx", (e.clientX - r.left) + "px"); c.style.setProperty("--my", (e.clientY - r.top) + "px");
}, { passive: true });

function countUp(node, to, suffix = "") {
  if (typeof to !== "number" || PREFS.motion === "off") { node.textContent = to + (typeof to === "number" ? suffix : ""); return; }
  const t0 = performance.now(), dur = 700;
  const step = now => { const k = Math.min(1, (now - t0) / dur), v = Math.round(to * (1 - Math.pow(1 - k, 3))); node.textContent = v + suffix; if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

/* Notas técnicas del motor -> texto entendible */
const NOTE_RULES = [
  [/stt_baja_confianza/, "El saludo se oyó poco claro en la grabación: confírmelo escuchando el audio."],
  [/sin_digitos_transcritos/, "El cliente respondió, pero los números no se leen en la transcripción: escuche el audio."],
  [/sin_respuesta_con_numero/, "No se encontró que el cliente diera el número."],
  [/informativo/, ""], [/menciones=/, ""], [/esperas=/, ""], [/sin_palabras_clave/, ""], [/requiere_LLM/, ""],
  [/peticiones=/, ""], [/banderas_debiles=/, ""], [/marcadores_de_cortesia=/, ""],
  [/no exigido: no parece una consulta/, "No se exige médico: no parece una consulta médica."],
  [/no requiere preparacion/, null], [/REQUIERE preparacion/, null], [/examen no encontrado/, "El examen no está en la base maestra: no se sabe si requiere preparación."],
  [/LLM dijo 'sí' pero su cita no está/, "La IA dijo que sí, pero su cita no aparece en la conversación: se descartó."],
  [/LLM: sin evidencia/, "La IA no encontró evidencia: confirme escuchando."],
  [/silencio largo sin anunciar/, "Hubo un silencio largo sin avisar al cliente."],
  [/patron_presentacion|roster|inferido_por/, ""],
];
function friendly(note) {
  if (!note) return "";
  const parts = note.split(" | ").map(p => p.trim()).filter(Boolean).map(p => {
    for (const [re, txt] of NOTE_RULES) if (re.test(p)) return txt === null ? p.replace(/^'(.+)' (no )?(REQUIERE|requiere) preparacion.*$/i, (m, n, no) => `Examen «${n}»: ${no ? "no requiere" : "requiere"} preparación (base maestra).`).replace(/^(.+) no requiere preparacion.*$/, "Este examen no requiere preparación (base maestra).") : txt;
    return p;
  });
  return parts.filter(Boolean).join(" ");
}

/* ---------------- navegación ---------------- */
function moveGlider() {
  const a = $(".tab.active"), g = $("#glider"); if (!a || !g) return;
  g.style.left = a.offsetLeft + "px"; g.style.width = a.offsetWidth + "px";
}
window.addEventListener("resize", moveGlider);
function show(view) {
  $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + view));
  moveGlider();
  if (view === "resultados") loadCalls(true);
  if (view === "quejas") loadQuejas(true);
  if (view === "comentarios" && typeof initComentarios === "function") initComentarios();
  if (view === "config") { renderConfig(); if (typeof initVocab === "function") initVocab(); if (typeof initMail === "function") initMail(); }
  if (view === "asistente") initChat();
}
$("#tabs").onclick = e => { const b = e.target.closest(".tab"); if (!b) return; if (b.dataset.view === "resultados") FOCUS = null; show(b.dataset.view); };
/* «Ver resultados» lleva solo a las llamadas del último análisis; si fue una, la abre directamente */
$("#btnVer").onclick = async () => {
  const ids = (ST.job?.call_ids || []).slice();
  FOCUS = ids.length ? ids : null; FILTER = "todas";
  show("resultados");
  if (ids.length === 1) { await loadCalls(); openCall(ids[0]); }
};

/* ---------------- cargar ---------------- */
const drop = $("#drop"), fileIn = $("#file");
drop.onclick = () => fileIn.click();
drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") fileIn.click(); };
["dragenter","dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave","drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => upload([...e.dataTransfer.files]));
fileIn.onchange = () => { upload([...fileIn.files]); fileIn.value = ""; };

async function upload(files) {
  const ok = files.filter(f => /\.(gsm|mp3|wav)$/i.test(f.name));
  if (files.length !== ok.length) toast("Se omitieron archivos que no son .gsm, .mp3 o .wav");
  const box = $("#pending");
  for (const f of ok) {
    const chip = el("span", "file up", "⏳ " + f.name); box.appendChild(chip);
    const r = await fetch("/api/upload?name=" + encodeURIComponent(f.name), { method: "POST", body: f });
    chip.className = "file"; chip.textContent = (r.ok ? "✔ " : "✖ ") + f.name;
  }
  refreshState();
}

$("#btnLimpiar").onclick = async () => { await api("/api/clear_incoming", { method: "POST" }); refreshState(); };
$("#btnAnalizar").onclick = async () => {
  const mode = $('input[name=mode]:checked').value;
  // "externa" usa Groq/Gemini; Rápido/Preciso piden la IA local aunque el instalador haya dejado una API como predeterminada
  const body = mode === "sin" ? { use_llm: false, mode: "rapido" } : mode === "externa" ? { use_llm: true, mode: "rapido", engine: "externa" }
    : { use_llm: true, mode, engine: "local" };
  const r = await api("/api/process", { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) toast(r.error);
  refreshState();
};
$("#btnCancelar").onclick = async () => { await api("/api/cancel", { method: "POST" }); };

async function refreshState() {
  ST = await api("/api/state");
  const j = ST.job, files = ST.pending_files;
  const pend = $("#pending");
  if (!j.running) { pend.innerHTML = ""; files.forEach(n => pend.appendChild(el("span", "file", "📄 " + n))); }
  $("#btnAnalizar").disabled = j.running || files.length === 0;
  $("#btnAnalizar").innerHTML = icon("play") + (files.length ? ` Analizar ${files.length} llamada${files.length > 1 ? "s" : ""}` : " Analizar llamadas");
  $("#btnLimpiar").hidden = j.running || files.length === 0;
  const ext = ST.external || {}, localOk = ST.llm.rapido || ST.llm.preciso;
  if (!refreshState.init) {      // una sola vez: si el instalador dejó la IA externa (o no hay modelo local pero sí clave), se preselecciona
    refreshState.init = true;
    if (ST.default_engine === "externa" && PREFS.defMode === "rapido") pickMode("externa");
  }
  $("#extModeSmall").textContent = ext.available ? `${ext.label} en la nube: rápida y sin instalar modelos. Los textos de las llamadas salen del equipo.`
    : "Groq o Gemini en la nube. Aún sin clave: ejecute Instalar.bat y elija la opción 2.";
  const m = $('input[name=mode]:checked')?.value, hint = [];
  if (m === "externa") hint.push(ext.available ? `Se usará ${ext.label}; los textos de las llamadas se envían a ese proveedor.` : "Falta la clave de la IA externa: ejecute Instalar.bat y elija la opción 2.");
  else if (m !== "sin") {
    if (!localOk) hint.push(ext.available ? "La IA local no está instalada: use «IA externa» o «Solo reglas»." : "La IA local no está instalada: use «Solo reglas».");
    else if (!ST.llm[m]) hint.push("Ese modelo de IA no está instalado en este equipo.");
  }
  $("#modeHint").textContent = hint.join(" ");
  renderJob(j);
  clearTimeout(pollT);
  pollT = setTimeout(refreshState, j.running ? 1500 : 6000);
}
$$('input[name=mode]').forEach(i => i.onchange = refreshState);

function renderJob(j) {
  const card = $("#cardProgreso"), an = $("#cardAnalizar");
  const active = j.running || (j.total > 0 && j.finished);
  card.hidden = !active; an.style.opacity = j.running ? .5 : 1;
  if (!active) return;
  const pct = j.total ? Math.round(100 * j.done / j.total) : 0;
  $("#barFill").style.width = (j.running && j.done === 0 ? 4 : pct) + "%"; $("#barFill").classList.toggle("idle", !j.running);
  $("#progTitle").textContent = j.running ? "Analizando llamadas…" : (j.message === "Cancelado" ? "Análisis detenido" : "✅ ¡Análisis terminado!");
  $("#progCount").textContent = `${j.done} de ${j.total}`;
  const nAuto = (j.auto_discarded || []).length;
  $("#progEta").textContent = [j.running && j.eta_s != null ? `faltan unos ${Math.max(1, Math.round(j.eta_s / 60))} min` : "",
    j.skipped ? `${j.skipped} repetida(s) omitida(s)` : "", nAuto ? `${nAuto} descartada(s) automáticamente (cortada/incompleta)` : ""].filter(Boolean).join(" · ");
  $("#progFile").textContent = j.current || "—";
  const ol = $("#steps"); ol.innerHTML = "";
  j.stages.forEach((n, i) => {
    if (n.includes("IA") && !j.use_llm) return;
    const li = el("li", j.running ? (i < j.stage_idx ? "done" : i === j.stage_idx ? "now" : "") : "done", (i < j.stage_idx || !j.running ? "✔ " : "") + n);
    ol.appendChild(li);
  });
  $("#progMsg").textContent = j.message && j.message !== "Listo" ? j.message : "";
  const er = $("#progErrs"); er.innerHTML = ""; j.errors.forEach(e => er.appendChild(el("li", "", e)));
  $("#btnCancelar").hidden = !j.running; $("#btnVer").hidden = j.running;
  const nIds = (j.call_ids || []).length;
  $("#btnVer").textContent = nIds === 1 ? "Revisar esta llamada →" : nIds > 1 ? `Ver las ${nIds} llamadas analizadas →` : "Ver resultados →";
}

/* ---------------- resultados ---------------- */
async function loadCalls(animate) {
  CALLS = await api("/api/calls");
  const t = $("#callsTable");
  if (animate) { t.classList.add("enter"); clearTimeout(t._e); t._e = setTimeout(() => t.classList.remove("enter"), 1200); }
  renderResults(animate);
  if (FLASH_ID) { const r = $(`tr[data-id="${FLASH_ID}"]`); if (r) { r.classList.add("flash"); r.scrollIntoView({ block: "nearest", behavior: "smooth" }); } FLASH_ID = null; }
}
const FILTERS = [["todas","Todas"],["revisar","Para revisar"],["lista","Listas"],["revisada","Revisadas"],["noap","No aprobadas"],["descartada","Descartadas"],["sin_conversacion","Sin conversación"]];
const DESC_TXT = { cortada: "cortada", incompleta: "incompleta" };
function renderResults(animate) {
  const real = CALLS.filter(c => !c.sintetica);
  const act = real.filter(c => !c.descartada);   // las descartadas no cuentan en notas ni pendientes
  const aprob = act.filter(c => c.nota != null && c.nota >= ST.pass_percent).length;
  const notas = act.filter(c => c.nota != null).map(c => c.nota);
  const avg = notas.length ? Math.round(notas.reduce((a, b) => a + b, 0) / notas.length) : null;
  const rev = act.filter(c => c.estado_ui === "revisar").length;
  const sum = $("#summary"); sum.innerHTML = "";
  [["Llamadas a auditar", act.length, "", ""], ["Para revisar", rev, rev ? "warn" : "", ""], ["Aprobadas (≥ " + ST.pass_percent + "%)", aprob, "ok", ""], ["Nota promedio", avg == null ? "—" : avg, "", "%"]].forEach(([l, v, c, suf], i) => {
    const k = el("div", "kpi " + c); k.style.setProperty("--i", i); const b = el("b"); k.append(b, el("span", "", l)); sum.appendChild(k);
    if (animate) countUp(b, v, suf); else b.textContent = v + (typeof v === "number" ? suf : "");
  });
  const f = $("#filters"); f.innerHTML = "";
  FILTERS.forEach(([k, l]) => { const b = el("button", "chipf" + (FILTER === k ? " active" : ""), l); b.onclick = () => { FILTER = k; renderResults(); }; f.appendChild(b); });
  const q = norm($("#search").value.trim()), desde = $("#fDesde").value, hasta = $("#fHasta").value;
  const fb = $("#focusBar"); fb.hidden = !FOCUS;
  if (FOCUS) $("#focusTxt").textContent = FOCUS.length === 1 ? `la llamada ${FOCUS[0]}` : `las ${FOCUS.length} llamadas`;
  const rows = real.filter(c => (FOCUS ? FOCUS.includes(c.id) : true) &&
    (FILTER === "todas" || c.estado_ui === FILTER || (FILTER === "noap" && c.nota != null && c.nota < ST.pass_percent)) &&
    (!q || norm([c.id, c.archivo, c.agente, c.fecha, c.hora, TIPO[c.tipo] || "", fmtAnalyzed(c.analizada)].join(" ")).includes(q)) &&
    (!desde || (c.analizada || "").slice(0, 16) >= desde) && (!hasta || (c.analizada || "").slice(0, 16) <= hasta));
  sortRows(rows);
  const nd = real.length - act.length;
  $("#countLine").textContent = real.length ? `Mostrando ${rows.length} de ${real.length} llamadas analizadas${nd ? ` · ${nd} descartada${nd > 1 ? "s" : ""} (cortadas o incompletas, no se auditan)` : ""}.` : "";
  $("#empty").hidden = real.length > 0;
  const t = $("#callsTable"); t.innerHTML = "";
  if (!rows.length) { if (real.length) t.appendChild(el("tr")).appendChild(el("td", "empty", "Ninguna llamada coincide con la búsqueda.")); return; }
  const head = el("tr"); ["Llamada", "Analizada", "Tipo", "Criterios", "Nota", "Estado", ""].forEach(h => head.appendChild(el("th", "", h))); t.appendChild(head);
  rows.forEach((c, i) => {
    const tr = el("tr", "row-c" + (c.descartada ? " is-discarded" : "")); tr.onclick = () => openCall(c.id); tr.dataset.id = c.id; tr.style.setProperty("--i", i);
    const n = el("td", "callname"); n.append(el("b", "", "Llamada " + c.id), el("small", "", `${c.agente ? c.agente + " · " : ""}${c.fecha} ${c.hora} · ${fmt(c.duracion_s)} min`)); tr.appendChild(n);
    const an = el("td", "analyzed"); const [ad, at] = fmtAnalyzed(c.analizada).split(" "); an.append(ad || "—", el("small", "", at || "")); tr.appendChild(an);
    tr.appendChild(el("td", "", TIPO[c.tipo] || "—"));
    const d = el("td"); const dots = el("div", "dots");
    if (c.descartada) dots.appendChild(el("span", "dismissed", `No se audita: llamada ${DESC_TXT[c.descartada]}${c.descarte_origen === "automática" ? " (marcada automáticamente)" : ""}`));
    else CODES.forEach(code => {
      if (!c.criterios || !(code in c.criterios)) return;
      const v = c.criterios[code], w = el("div", "dotc");
      const cls = c.origen[code] === "n/a" ? "na" : v === 1 ? "ok" : v === 0 ? "bad" : "pend";
      const dot = el("span", "dot " + cls + (c.origen[code] === "humano" ? " hum" : ""), cls === "na" ? "–" : v === 1 ? "✓" : v === 0 ? "✗" : "?");
      dot.title = `${code} · ${(ST.guide[code] || [""])[0]} — ${cls === "na" ? "No aplica" : v === 1 ? "Cumple" : v === 0 ? "No cumple" : "Falta decidir"}${c.origen[code] === "humano" ? " (decidido por usted)" : ""}`;
      w.append(dot, el("span", "dotlbl", code)); dots.appendChild(w);
    });
    d.appendChild(dots); tr.appendChild(d);
    const nt = el("td"); nt.appendChild(el("span", "nota " + (c.nota == null ? "pend" : c.nota >= ST.pass_percent ? "ok" : "bad"), c.nota == null ? "Pendiente" : c.nota + "%")); tr.appendChild(nt);
    const es = { lista: "Lista", revisar: "Para revisar", revisada: "Revisada", sin_conversacion: "Sin conversación", error: "Con error", descartada: "Descartada" }[c.estado_ui];
    tr.appendChild(el("td")).appendChild(el("span", "pill " + c.estado_ui, es));
    tr.appendChild(el("td")).appendChild(el("button", "btn", c.estado_ui === "revisar" ? "Revisar →" : "Ver →")).type = "button";
    t.appendChild(tr);
  });
}
const norm = s => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
function fmtAnalyzed(iso) {
  if (!iso) return "";
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)} ${iso.slice(11, 16)}`;
}
const callKey = c => c.fecha ? c.fecha.split("/").reverse().join("") + c.hora : "";
function sortRows(rows) {
  const by = $("#sortSel").value;
  const cmp = { analizada: (a, b) => (b.analizada || "").localeCompare(a.analizada || ""),
    llamada: (a, b) => callKey(b).localeCompare(callKey(a)),
    nota: (a, b) => (a.nota ?? 101) - (b.nota ?? 101),
    id: (a, b) => a.id.localeCompare(b.id, "es", { numeric: true }) }[by];
  rows.sort(cmp);
}
const localIso = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
["search", "fDesde", "fHasta", "sortSel"].forEach(id => $("#" + id).addEventListener("input", () => renderResults()));
$("#quick").onclick = e => {
  const b = e.target.closest("[data-q]"); if (!b) return;
  const now = new Date(), d = new Date(now);
  if (b.dataset.q === "hora") d.setHours(now.getHours() - 1);
  if (b.dataset.q === "hoy") d.setHours(0, 0, 0, 0);
  if (b.dataset.q === "semana") { d.setDate(now.getDate() - 7); d.setHours(0, 0, 0, 0); }
  $("#fDesde").value = localIso(d); $("#fHasta").value = ""; $("#sortSel").value = "analizada";
  $$("#quick [data-q]").forEach(x => x.classList.toggle("active", x === b)); renderResults();
};
$("#btnClearSearch").onclick = () => {
  $("#search").value = ""; $("#fDesde").value = ""; $("#fHasta").value = ""; $("#sortSel").value = "analizada";
  $$("#quick [data-q]").forEach(x => x.classList.remove("active")); FILTER = "todas"; renderResults();
};
$("#btnFocusOff").onclick = () => { FOCUS = null; renderResults(); };
["fDesde", "fHasta"].forEach(id => $("#" + id).addEventListener("input", () => $$("#quick [data-q]").forEach(x => x.classList.remove("active"))));

/* ---------------- detalle ---------------- */
async function openCall(id) {
  const d = await api("/api/call/" + id);
  if (d.error) return toast("No se pudo abrir la llamada");
  CUR = d; CUR.id = id;
  DRAFT = JSON.parse(JSON.stringify({ criteria: d.review.criteria || {}, e1: d.review.e1 || null, discard: d.review.discard || null, agent: d.review.agent || "", auditor: d.review.auditor || "",
    motivo: d.review.motivo || "", obs: d.review.obs || "" }));
  $("#fAgent").value = DRAFT.agent; $("#fAuditor").value = DRAFT.auditor || PREFS.auditor; $("#fMotivo").value = DRAFT.motivo || (TIPO[d.audit.call_type?.type] && d.audit.call_type.type !== "desconocido" ? TIPO[d.audit.call_type.type] : ""); $("#fObs").value = DRAFT.obs;
  const a = d.audit, c = a.call;
  $("#dTitle").textContent = "Llamada " + id;
  $("#dSub").textContent = `${c.received_date ? c.received_date.slice(6, 8) + "/" + c.received_date.slice(4, 6) + "/" + c.received_date.slice(0, 4) : ""} · ${fmt(c.duration_s)} min · ${TIPO[a.call_type?.type] || "Sin conversación"}`;
  const pl = $("#player"); $("#noAudio").hidden = d.has_audio; pl.hidden = !d.has_audio; if (d.has_audio) pl.src = "/api/audio/" + id;
  const cr = $("#criteria"); cr.classList.add("enter"); clearTimeout(cr._e); cr._e = setTimeout(() => cr.classList.remove("enter"), 1100);
  renderTranscript(); renderCriteria(); renderScore(); renderDiscard();
  const m = $("#modal"); m.classList.remove("closing"); m.hidden = false; document.body.style.overflow = "hidden"; m.scrollTop = 0;
  const b = $("#btnSave"); b.disabled = false; b.classList.remove("done"); b.innerHTML = icon("check") + " Guardar revisión";
  $("#saveMsg").textContent = "Atajo: Ctrl + S guarda y cierra.";
  SNAP = snapshot();
}
const autoDiscard = () => CUR?.audit?.auto_discard || null;
/* Motivo vigente: lo que decidió el auditor; si no decidió, la marca automática (regla de 20 s o IA) */
const effDiscard = () => DRAFT.discard === "ninguna" ? null : (DRAFT.discard || autoDiscard()?.value || null);
function renderDiscard() {
  const box = $("#discardBox"), seg = $("#discardSeg"); seg.innerHTML = ""; const eff = effDiscard(), auto = autoDiscard();
  box.classList.toggle("on", !!eff); $("#rightCol").classList.toggle("discarded", !!eff);
  [["", "Auditar normal"], ["cortada", "Llamada cortada"], ["incompleta", "Llamada incompleta"]].forEach(([v, l]) => {
    const sel = (eff || "") === v;
    const b = el("button", sel ? "sel" + (v ? " sd" : "") : "", l); b.type = "button";
    b.onclick = () => { DRAFT.discard = v ? v : (auto ? "ninguna" : null); renderDiscard(); renderScore(); }; seg.appendChild(b);
  });
  const note = $("#discardNote"); note.innerHTML = ""; note.hidden = true;
  const comp = CUR.audit.completion;
  if (auto && DRAFT.discard == null) {
    note.hidden = false;
    note.append(el("b", "", auto.source === "regla" ? "Marcada automáticamente por regla: " : "Marcada automáticamente por la IA: "), auto.reason || "");
    if (auto.quote) { const q = el("span", "quote", `▶ ${fmt(auto.start)} “${auto.quote}”`); q.onclick = () => seek(auto.start, auto.turn_id); note.append(" ", q); }
    note.append(el("div", "std", "Si no es correcto, elija «Auditar normal» y guarde: su decisión reemplaza a la del sistema."));
  } else if (auto && DRAFT.discard === "ninguna") {
    note.hidden = false; note.append("Usted anuló la marca automática; la llamada se audita normalmente.");
  } else if (comp && !auto) {
    note.hidden = false;
    note.append(`La IA revisó el cierre: ${comp.estado || "sin respuesta"}${comp.motivo ? " · " + comp.motivo : ""}${comp.nota ? " · " + comp.nota : ""}.`);
  }
}
function snapshot() { return JSON.stringify([DRAFT.criteria, DRAFT.e1, DRAFT.discard, $("#fAgent").value, $("#fAuditor").value, $("#fMotivo").value, $("#fObs").value]); }
function isOpen() { const m = $("#modal"); return !m.hidden && !m.classList.contains("closing"); }
function closeModal(force) {
  if (!isOpen()) return;
  if (!force && snapshot() !== SNAP && !confirm("Tiene cambios sin guardar en esta llamada. ¿Salir sin guardar?")) return;
  const m = $("#modal"); $("#player").pause(); m.classList.add("closing");
  setTimeout(() => { m.hidden = true; m.classList.remove("closing"); document.body.style.overflow = ""; }, PREFS.motion === "off" ? 0 : 270);
  return loadCalls();
}
$("#btnBack").onclick = () => closeModal();
document.addEventListener("keydown", e => {
  if (!isOpen()) return;
  if (e.key === "Escape") closeModal();
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
});

function seek(t, turnId) {
  const p = $("#player"); if (CUR.has_audio) { p.currentTime = Math.max(0, t - 1); p.play(); }
  const b = $("#t" + turnId); if (b) { b.scrollIntoView({ block: "center", behavior: "smooth" }); b.classList.add("flash"); setTimeout(() => b.classList.remove("flash"), 2200); }
}
function renderTranscript() {
  const box = $("#transcript"); box.innerHTML = "";
  const turns = CUR.turns, holds = (CUR.audit.metrics?.hold_events || []);
  if (!turns.length) { box.appendChild(el("p", "empty", "No se detectó una conversación en esta llamada (solo ruido, música o mensajes grabados).")); return; }
  const rec = CUR.recorded.filter(r => r.kind === "ivr_inicial");
  if (rec.length) box.appendChild(el("div", "note", `🔔 Mensaje grabado de bienvenida / cola de espera (${fmt(rec[0].start)}–${fmt(rec[0].end)}) · no se evalúa`));
  turns.forEach(t => {
    const cls = t.speaker === "ASESOR" ? "A" : t.speaker === "CLIENTE" ? "C" : "D";
    const b = el("div", "bub " + cls); b.id = "t" + t.turn_id;
    const who = el("small"); who.append(el("span", "av", cls === "A" ? "A" : cls === "C" ? "C" : "?"),
      `${t.speaker === "ASESOR" ? "Asesor" : t.speaker === "CLIENTE" ? "Cliente" : "Sin identificar"} · ${fmt(t.start)} ▶`);
    b.style.animationDelay = Math.min(t.turn_id, 12) * 25 + "ms";
    who.onclick = () => seek(t.start, t.turn_id); b.append(who, document.createTextNode(t.text)); box.appendChild(b);
    holds.filter(h => h.turn_before === t.turn_id).forEach(h => {
      const n = el("div", "note hold" + (h.duration_s >= 60 ? " long" : ""), `⏳ Espera de ${Math.round(h.duration_s)} segundos${h.duration_s >= 60 ? " (supera el límite de 60 s)" : ""}`);
      box.appendChild(n);
    });
  });
}

function sysState(code) {
  const c = CUR.audit.criteria[code];
  if (!c.applicable) return "na";
  return c.score === 1 ? "ok" : c.score === 0 ? "bad" : "pend";
}
function curValue(code) {
  if (code in DRAFT.criteria) return DRAFT.criteria[code];
  const c = CUR.audit.criteria[code]; return c.score;
}
function renderCriteria() {
  const box = $("#criteria"); box.innerHTML = "";
  if (!CUR.audit.criteria || !Object.keys(CUR.audit.criteria).length) { box.appendChild(el("div", "card", "Esta llamada no tiene conversación evaluable.")); return; }
  const e1 = CUR.audit.critical_error, e1b = $("#e1box");
  e1b.hidden = e1.status === "none"; e1b.className = "card e1"; e1b.innerHTML = "";
  if (e1.status !== "none") {
    e1b.append(el("h3", "", "⚠ Posible error crítico (la nota sería 0 %)"));
    e1.findings.forEach(f => e1b.appendChild(el("p", "why", f.description)));
    e1b.appendChild(el("p", "hint", "El sistema solo propone esto; usted decide. Si se confirma, la llamada queda con nota 0 %."));
    const seg = el("div", "seg");
    [["confirmed", "Confirmar error crítico", "s0"], ["dismissed", "No es un error crítico", "s1"]].forEach(([v, l, cl]) => {
      const b = el("button", DRAFT.e1 === v ? "sel " + cl : "", l); b.onclick = () => { DRAFT.e1 = DRAFT.e1 === v ? null : v; renderCriteria(); renderScore(); }; seg.appendChild(b);
    });
    e1b.appendChild(seg);
  }
  CODES.forEach((code, i) => {
    const c = CUR.audit.criteria[code], st = sysState(code), g = CUR.guide[code] || [code, ""];
    const val = curValue(code), human = code in DRAFT.criteria;
    const card = el("div", "crit " + (val === 1 ? "ok" : val === 0 ? "bad" : "pend")); card.style.setProperty("--i", i);
    const h = el("div", "crit-h"); h.append(el("b", "code", code), el("span", "nm", g[0]), el("span", "sp"));
    h.appendChild(el("span", "tag" + (human ? " hum" : ""), human ? "Decidido por usted" : st === "na" ? "No aplica a este tipo de llamada" :
      "Sistema: " + (st === "ok" ? "cumple" : st === "bad" ? "no cumple" : "no pudo decidir")));
    card.appendChild(h); card.appendChild(el("p", "std", g[1]));
    if (c.sub_checks.length) {
      const ul = el("ul", "subs");
      c.sub_checks.forEach(s => {
        const li = el("li"); const k = s.passed === true ? "ok" : s.passed === false ? "bad" : "pend";
        li.appendChild(el("span", "ic " + k, k === "ok" ? "✔" : k === "bad" ? "✘" : "?"));
        const d = el("div"); d.appendChild(el("span", "", (SUBLABEL[s.id] || s.id) + (s.optional ? " (opcional)" : "") + (s.source === "llm" ? " · IA" : "")));
        const ev = s.evidence;
        if (ev && ev.quote) { const q = el("div", "quote", `▶ ${fmt(ev.start)} “${ev.quote.length > 110 ? ev.quote.slice(0, 110) + "…" : ev.quote}”`); q.onclick = () => seek(ev.start, ev.turn_id); d.appendChild(q); }
        else if (ev && ev.duration_s != null) d.appendChild(el("div", "quote", `⏱ ${ev.duration_s} s`));
        else if (ev && ev.longest_s != null) d.appendChild(el("div", "quote", `⏱ más largo: ${ev.longest_s} s`));
        else if (ev && ev.total_s != null) d.appendChild(el("div", "quote", `⏱ total: ${ev.total_s} s`));
        const fn = friendly(s.note); if (fn) d.appendChild(el("div", "std", fn));
        li.appendChild(d); ul.appendChild(li);
      });
      card.appendChild(ul);
    } else card.appendChild(el("p", "why", c.explanation));
    const seg = el("div", "seg"); seg.title = "Su decisión reemplaza la del sistema";
    [["", "Dejar lo del sistema"], [1, "✔ Cumple"], [0, "✘ No cumple"]].forEach(([v, l]) => {
      const sel = v === "" ? !human : human && DRAFT.criteria[code] === v;
      const b = el("button", sel ? "sel " + (v === 1 ? "s1" : v === 0 ? "s0" : "") : "", l);
      b.onclick = () => { if (v === "") delete DRAFT.criteria[code]; else DRAFT.criteria[code] = v; renderCriteria(); renderScore(); }; seg.appendChild(b);
    });
    const row = el("div", "row"); row.appendChild(seg); card.appendChild(row);
    box.appendChild(card);
  });
}
function renderScore() {
  const a = CUR.audit; const box = $("#dScore"); box.innerHTML = "";
  const eff = effDiscard();
  if (eff) { box._last = null; box.append(el("div", "big", "—"), el("small", "", `No se audita: llamada ${DESC_TXT[eff]}`)); return; }
  if (!a.criteria || !Object.keys(a.criteria).length) { box.appendChild(el("div", "big", "—")); return; }
  const vals = CODES.map(curValue), pend = vals.filter(v => v == null).length, pts = vals.filter(v => v === 1).length;
  const e1 = DRAFT.e1 || (a.critical_error.status !== "none" ? "cand" : null);
  let big, small;
  if (DRAFT.e1 === "confirmed") { big = "0%"; small = "No aprobado · error crítico"; }
  else if (pend) { big = `${pts * 10}–${(pts + pend) * 10}%`; small = `${pend} criterio${pend > 1 ? "s" : ""} por decidir`; }
  else { big = pts * 10 + "%"; small = pts * 10 >= ST.pass_percent ? "Aprobado" : "No aprobado"; if (e1 === "cand") small += " · revise el posible error crítico"; }
  const b = el("div", "big", big); if (!pend) b.style.color = DRAFT.e1 === "confirmed" || pts * 10 < ST.pass_percent ? "var(--bad)" : "var(--ok)";
  if (box._last && box._last !== big) b.classList.add("bump"); box._last = big;
  box.append(b, el("small", "", small));
}
async function save() {
  const btn = $("#btnSave"); if (btn.disabled) return;
  DRAFT.agent = $("#fAgent").value.trim(); DRAFT.auditor = $("#fAuditor").value.trim(); DRAFT.motivo = $("#fMotivo").value.trim(); DRAFT.obs = $("#fObs").value.trim();
  btn.disabled = true; btn.textContent = "Guardando…";
  let r;
  try { r = await api("/api/review/" + CUR.id, { method: "POST", body: JSON.stringify({ ...DRAFT, reviewed: true }) }); }
  catch (e) { r = { ok: false, error: "No hay conexión con el programa. Verifique que la ventana negra siga abierta." }; }
  if (!r.ok) {
    btn.disabled = false; btn.innerHTML = icon("check") + " Guardar revisión";
    $("#saveMsg").textContent = "No se guardó: " + (r.error || "error desconocido") + ". Intente de nuevo.";
    return;
  }
  if (DRAFT.auditor && !PREFS.auditor) { PREFS.auditor = DRAFT.auditor; savePrefs(); }
  const disc = effDiscard(), pend = disc ? 0 : CODES.map(curValue).filter(v => v == null).length, id = CUR.id;
  btn.classList.add("done"); btn.innerHTML = '<svg class="i check"><use href="#i-check"/></svg> Guardada';
  SNAP = snapshot(); FLASH_ID = id;
  setTimeout(async () => {
    await closeModal(true);
    toast(disc ? `Llamada ${id} descartada: ${DESC_TXT[disc]}, no se audita` : pend ? `Llamada ${id} guardada · quedan ${pend} criterio${pend > 1 ? "s" : ""} por decidir` : `Llamada ${id} guardada`, "ok");
    if (PREFS.after === "siguiente") {
      const next = CALLS.find(c => !c.sintetica && c.estado_ui === "revisar" && c.id !== id);
      if (next) setTimeout(() => openCall(next.id), 450); else toast("No quedan llamadas por revisar", "ok");
    }
  }, PREFS.motion === "off" ? 150 : 650);
}
$("#btnSave").onclick = save;
$("#btnDelete").onclick = async () => {
  if (!confirm("¿Eliminar esta llamada? Se borrarán el audio, la transcripción y los resultados. No se puede deshacer.")) return;
  await api("/api/call/" + CUR.id, { method: "DELETE" }); closeModal(true); toast("Llamada eliminada", "ok");
};

/* ---------------- quejas ---------------- */
let QJ = { quejas: [], sugeridas: [], opciones: null }, QFILTER = "activas", QCUR = null, QSNAP = "";
const QFILTERS = [["activas","Sin cerrar"],["abierta","Abiertas"],["en_gestion","En gestión"],["vencida","Vencidas"],["cerrada","Cerradas"],["todas","Todas"]];
const QF = ["usuario", "documento", "telefono", "fecha", "canal", "categoria", "asesor", "sede", "llamada", "descripcion", "plazo", "responsable", "respuesta"];
const qIn = k => $("#q" + k[0].toUpperCase() + k.slice(1));
const todayIso = () => localIso(new Date()).slice(0, 10);
const fmtDay = iso => iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "—";
const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return localIso(d).slice(0, 10); };
function leftTxt(plazo) {
  const d = Math.round((new Date(plazo + "T12:00:00") - new Date(todayIso() + "T12:00:00")) / 864e5);
  return d === 0 ? "Vence hoy" : d === 1 ? "Vence mañana" : `Faltan ${d} días`;
}
async function loadQuejas(animate) {
  try { QJ = await api("/api/quejas"); } catch (e) { return toast("No se pudieron cargar las quejas"); }
  fillQOptions(); renderQuejas(animate);
}
function fillQOptions() {
  const o = QJ.opciones; if (!o || $("#qCat").options.length > 1) return;
  const add = (sel, map) => Object.entries(map).forEach(([v, l]) => sel.appendChild(new Option(l, v)));
  add($("#qCat"), o.categorias); add($("#qPrio"), o.prioridades); add($("#qCategoria"), o.categorias); add($("#qCanal"), o.canales);
  o.asesores.forEach(n => $("#qAsesores").appendChild(new Option(n, n))); o.sedes.forEach(n => $("#qSedes").appendChild(new Option(n, n)));
}
function renderQuejas(animate) {
  if (typeof renderQStats === "function") renderQStats(QJ.stats);
  const all = QJ.quejas, o = QJ.opciones, hoy = todayIso();
  const n = k => all.filter(q => q.estado === k).length, venc = all.filter(q => q.vencida).length;
  const mes = all.filter(q => q.estado === "cerrada" && (q.cerrada_el || "").slice(0, 7) === hoy.slice(0, 7)).length;
  const sum = $("#qSummary"); sum.innerHTML = "";
  [["Abiertas", n("abierta"), n("abierta") ? "warn" : ""], ["En gestión", n("en_gestion"), ""], ["Vencidas", venc, venc ? "bad" : ""],
   ["Cerradas este mes", mes, "ok"], ["Detectadas en llamadas", QJ.sugeridas.length, QJ.sugeridas.length ? "warn" : ""]].forEach(([l, v, c], i) => {
    const k = el("div", "kpi " + c); k.style.setProperty("--i", i); const b = el("b"); k.append(b, el("span", "", l)); sum.appendChild(k);
    if (animate) countUp(b, v); else b.textContent = v;
  });
  const sb = $("#qSugs"); sb.innerHTML = ""; $("#qDetect").hidden = !QJ.sugeridas.length;
  QJ.sugeridas.forEach((s, i) => {
    const it = el("div", "q-sug"); it.style.setProperty("--i", i);
    const h = el("div", "q-sug-h");
    h.append(el("b", "", "Llamada " + s.llamada), el("small", "", [s.fecha && fmtDay(s.fecha), s.asesor, s.duracion_s != null ? fmt(s.duracion_s) + " min" : ""].filter(Boolean).join(" · ")));
    it.appendChild(h);
    s.hallazgos.slice(0, 3).forEach(f => {
      const q = el("div", "quote", `▶ ${fmt(f.start)} “${f.cita.length > 140 ? f.cita.slice(0, 140) + "…" : f.cita}”`);
      q.title = "Abrir la llamada en este punto"; q.onclick = () => qListen(s.llamada, f); it.appendChild(q);
    });
    const row = el("div", "row");
    const reg = el("button", "btn primary", "Registrar queja"); reg.type = "button"; reg.onclick = () => openQueja(null, s);
    const no = el("button", "btn ghost", "No es una queja"); no.type = "button";
    no.onclick = async () => { await api("/api/quejas/descartar/" + encodeURIComponent(s.llamada), { method: "POST" }); toast(`Llamada ${s.llamada}: no se volverá a sugerir`, "ok"); loadQuejas(); };
    row.append(reg, no); it.appendChild(row); sb.appendChild(it);
  });
  const f = $("#qFilters"); f.innerHTML = "";
  QFILTERS.forEach(([k, l]) => { const b = el("button", "chipf" + (QFILTER === k ? " active" : ""), l); b.type = "button"; b.onclick = () => { QFILTER = k; renderQuejas(); }; f.appendChild(b); });
  const q = norm($("#qSearch").value.trim()), cat = $("#qCat").value, pr = $("#qPrio").value;
  const rows = all.filter(x => (QFILTER === "todas" || (QFILTER === "activas" ? x.estado !== "cerrada" : QFILTER === "vencida" ? x.vencida : x.estado === QFILTER)) &&
    (!cat || x.categoria === cat) && (!pr || x.prioridad === pr) &&
    (!q || norm([x.id, x.usuario, x.documento, x.telefono, x.asesor, x.sede, x.llamada, x.responsable, x.descripcion].join(" ")).includes(q)));
  const PR = { alta: 0, media: 1, baja: 2 };
  rows.sort((a, b) => (a.estado === "cerrada") - (b.estado === "cerrada") || b.vencida - a.vencida || PR[a.prioridad] - PR[b.prioridad] || (a.plazo || "").localeCompare(b.plazo || ""));
  $("#qCount").textContent = all.length ? `Mostrando ${rows.length} de ${all.length} quejas${venc ? ` · ${venc} vencida${venc > 1 ? "s" : ""}` : ""}.` : "";
  $("#qEmpty").hidden = all.length > 0;
  const t = $("#qTable"); t.innerHTML = "";
  if (animate) { t.classList.add("enter"); clearTimeout(t._e); t._e = setTimeout(() => t.classList.remove("enter"), 1200); }
  if (!rows.length) { if (all.length) t.appendChild(el("tr")).appendChild(el("td", "empty", "Ninguna queja coincide con la búsqueda.")); return; }
  const head = el("tr"); ["Queja", "Fecha", "Categoría", "Asesor y sede", "Prioridad", "Plazo", "Estado", ""].forEach(h => head.appendChild(el("th", "", h))); t.appendChild(head);
  rows.forEach((x, i) => {
    const tr = el("tr", "row-c"); tr.dataset.id = x.id; tr.style.setProperty("--i", i); tr.onclick = () => openQueja(x);
    const nm = el("td", "callname");
    nm.append(el("b", "", `${x.id} · ${x.usuario || "Usuario sin nombre"}`), el("small", "", [x.documento && "Doc. " + x.documento, x.llamada && "Llamada " + x.llamada, o.canales[x.canal]].filter(Boolean).join(" · ")));
    tr.appendChild(nm);
    tr.appendChild(el("td", "analyzed", fmtDay(x.fecha)));
    tr.appendChild(el("td", "", o.categorias[x.categoria] || "—"));
    const as = el("td", "q-two"); as.append(el("span", "", x.asesor || "—"), el("small", "", x.sede)); tr.appendChild(as);
    tr.appendChild(el("td")).appendChild(el("span", "prio " + x.prioridad, o.prioridades[x.prioridad]));
    const pl = el("td", "analyzed" + (x.vencida ? " q-late" : ""));
    pl.append(fmtDay(x.plazo), el("small", "", x.estado === "cerrada" ? (x.cerrada_el ? "Cerrada el " + fmtDay(x.cerrada_el) : "") : x.vencida ? "Vencida" : x.plazo ? leftTxt(x.plazo) : ""));
    tr.appendChild(pl);
    tr.appendChild(el("td")).appendChild(el("span", "pill q-" + (x.vencida ? "vencida" : x.estado), x.vencida ? "Vencida" : o.estados[x.estado]));
    tr.appendChild(el("td")).appendChild(el("button", "btn", "Ver →")).type = "button";
    t.appendChild(tr);
  });
}
/* Fecha límite automática por prioridad (desde la fecha de la queja, o desde hoy si ya pasó); si el auditor la cambia, se respeta */
const qAutoPlazo = () => { const f = qIn("fecha").value || todayIso(); return addDays(f > todayIso() ? f : todayIso(), QJ.opciones.plazo_dias[QCUR.prioridad] || 8); };
function openQueja(q, sug) {
  if (!QJ.opciones) return;
  const base = q ? { ...q } : { fecha: todayIso(), canal: "llamada", categoria: "otro", prioridad: "media", estado: "abierta" };
  if (sug) Object.assign(base, { categoria: sug.categoria || "otro", prioridad: sug.prioridad || "media", llamada: sug.llamada, asesor: sug.asesor || "", fecha: sug.fecha || todayIso(),
    descripcion: "Detectada en la llamada: " + sug.hallazgos.map(h => `“${h.cita}” (${fmt(h.start)})`).join(" · ") });
  QCUR = { id: base.id || null, prioridad: base.prioridad, estado: base.estado, plazoAuto: !base.plazo, hits: sug ? sug.hallazgos : null };
  QF.forEach(k => qIn(k).value = base[k] || "");
  if (!base.plazo) qIn("plazo").value = qAutoPlazo();
  $("#qTitle").textContent = base.id ? `Queja ${base.id}` : "Nueva queja";
  $("#qSub").textContent = base.id ? `Registrada el ${fmtAnalyzed(base.creada || "")}${base.actualizada && base.actualizada !== base.creada ? " · actualizada el " + fmtAnalyzed(base.actualizada) : ""}`
    : "Los datos del usuario se guardan solo en este equipo.";
  $("#qDelete").hidden = !base.id;
  renderQSegs(); renderQEvidence();
  const b = $("#qSave"); b.disabled = false; b.classList.remove("done"); b.innerHTML = icon("check") + " Guardar queja";
  $("#qMsg").textContent = "Atajo: Ctrl + S guarda y cierra.";
  const m = $("#qModal"); m.classList.remove("closing"); m.hidden = false; document.body.style.overflow = "hidden"; m.scrollTop = 0;
  QSNAP = qSnapshot();
}
function renderQSegs() {
  const o = QJ.opciones;
  segment($("#qPrioSeg"), Object.entries(o.prioridades), QCUR.prioridad, v => { QCUR.prioridad = v; if (QCUR.plazoAuto) qIn("plazo").value = qAutoPlazo(); renderQSegs(); });
  segment($("#qEstadoSeg"), Object.entries(o.estados), QCUR.estado, v => { QCUR.estado = v; renderQSegs(); });
  $$("#qPrioSeg button").forEach((b, i) => b.dataset.v = Object.keys(o.prioridades)[i]);
  $$("#qEstadoSeg button").forEach((b, i) => b.dataset.v = Object.keys(o.estados)[i]);
  const late = QCUR.estado !== "cerrada" && qIn("plazo").value && qIn("plazo").value < todayIso();
  const st = $("#qState"); st.innerHTML = "";
  st.append(el("span", "pill q-" + (late ? "vencida" : QCUR.estado), late ? "Vencida" : o.estados[QCUR.estado]));
}
/* Citas de la llamada relacionada: un clic abre la llamada encima de la queja, en ese punto del audio */
function renderQEvidence() {
  const box = $("#qEvidencia"); box.innerHTML = "";
  const id = qIn("llamada").value.trim(); if (!id) return;
  (QCUR.hits || []).forEach(f => { const q = el("div", "quote", `▶ ${fmt(f.start)} “${f.cita}”`); q.title = "Escuchar este fragmento"; q.onclick = () => qListen(id, f); box.appendChild(q); });
  const row = el("div", "row"), b = el("button", "btn"); b.type = "button"; b.innerHTML = icon("play") + " Abrir la llamada "; b.append(id);
  b.onclick = () => qListen(id); row.appendChild(b); box.appendChild(row);
}
async function qListen(id, f) { await openCall(id); if (f && CUR?.id === id && isOpen()) seek(f.start, f.turn_id); }
const qSnapshot = () => JSON.stringify([QF.map(k => qIn(k).value), QCUR.prioridad, QCUR.estado]);
function qOpen() { const m = $("#qModal"); return !m.hidden && !m.classList.contains("closing"); }
function closeQueja(force) {
  if (!qOpen()) return;
  if (!force && qSnapshot() !== QSNAP && !confirm("Tiene cambios sin guardar en esta queja. ¿Salir sin guardar?")) return;
  const m = $("#qModal"); m.classList.add("closing");
  setTimeout(() => { m.hidden = true; m.classList.remove("closing"); document.body.style.overflow = ""; }, PREFS.motion === "off" ? 0 : 270);
}
async function saveQueja() {
  const btn = $("#qSave"); if (btn.disabled) return;
  const body = { id: QCUR.id, prioridad: QCUR.prioridad, estado: QCUR.estado };
  QF.forEach(k => body[k] = qIn(k).value.trim());
  if (!body.usuario && !body.descripcion) { $("#qMsg").textContent = "Escriba al menos el nombre del usuario o la descripción de la queja."; qIn("usuario").focus(); return; }
  btn.disabled = true; btn.textContent = "Guardando…";
  let r;
  try { r = await api("/api/quejas", { method: "POST", body: JSON.stringify(body) }); }
  catch (e) { r = { ok: false, error: "No hay conexión con el programa. Verifique que la ventana negra siga abierta." }; }
  if (!r.ok) {
    btn.disabled = false; btn.innerHTML = icon("check") + " Guardar queja";
    $("#qMsg").textContent = "No se guardó: " + (r.error || "error desconocido") + ". Intente de nuevo.";
    return;
  }
  btn.classList.add("done"); btn.innerHTML = '<svg class="i check"><use href="#i-check"/></svg> Guardada';
  QSNAP = qSnapshot();
  setTimeout(async () => {
    closeQueja(true); await loadQuejas();
    const tr = $(`#qTable tr[data-id="${r.queja.id}"]`); if (tr) { tr.classList.add("flash"); tr.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
    toast(`Queja ${r.queja.id} guardada`, "ok");
  }, PREFS.motion === "off" ? 150 : 650);
}
$("#btnNuevaQueja").onclick = () => openQueja(null);
$("#qBack").onclick = () => closeQueja();
$("#qSave").onclick = saveQueja;
$("#qDelete").onclick = async () => {
  if (!QCUR.id || !confirm(`¿Eliminar la queja ${QCUR.id}? No se puede deshacer.`)) return;
  await api("/api/quejas/" + encodeURIComponent(QCUR.id), { method: "DELETE" }); closeQueja(true); loadQuejas(); toast("Queja eliminada", "ok");
};
["qSearch", "qCat", "qPrio"].forEach(id => $("#" + id).addEventListener("input", () => renderQuejas()));
qIn("plazo").addEventListener("input", () => { QCUR.plazoAuto = false; renderQSegs(); });
qIn("fecha").addEventListener("input", () => { if (QCUR.plazoAuto) qIn("plazo").value = qAutoPlazo(); renderQSegs(); });
qIn("llamada").addEventListener("input", renderQEvidence);
document.addEventListener("keydown", e => {
  if (!$("#modal").hidden || !qOpen()) return; // con una llamada abierta encima, las teclas son de la llamada
  if (e.key === "Escape") closeQueja();
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveQueja(); }
});

applyPrefs();
pickMode(PREFS.defMode);
refreshState().then(renderConfig);
document.fonts?.ready.then(moveGlider);
