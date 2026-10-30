"use strict";
/* Pestaña «Trazas»: cada llamada a la IA (modelo, segundos, tokens), qué citas se aceptaron o descartaron y qué falló.
   Se actualiza sola cada 2 s mientras la pestaña está abierta. Usa $, el, api, post de app.js / extras.js. */
const TRZ = { timer: null, open: new Set() };
const TRZ_KIND = { llm: "IA", auditoria: "Auditoría", asistente: "Asistente" };

function trzKpis(r) {
  const box = $("#trzKpis"); box.innerHTML = "";
  [[r.llamadas_ia, "llamadas a la IA"], [r.mediana_s == null ? "—" : r.mediana_s + " s", "mediana por llamada"],
   [r.mediana_tokens == null ? "—" : r.mediana_tokens, "tokens por llamada (mediana)"], [r.fallos, "fallos"],
   [r.citas_aceptadas, "citas aceptadas"], [r.citas_descartadas, "citas descartadas"]]
    .forEach(([v, l], i) => { const d = el("div"); d.append(el("b", "", v), el("small", "", l)); if (i === 3 && r.fallos) d.classList.add("bad"); box.append(d); });
}
function trzResult(e) {
  if (e.status === "error") return ["✖ " + (e.error || "falló"), "bad"];
  if (e.kind === "auditoria") {
    const bits = [`✔ ${e.aceptadas} ${e.aceptadas === 1 ? "cita aceptada" : "citas aceptadas"}`];
    if (e.descartadas) bits.push(`✖ ${e.descartadas} ${e.descartadas === 1 ? "descartada" : "descartadas"} (no estaba en la transcripción)`);
    if (e.sin_evidencia) bits.push(`${e.sin_evidencia} sin evidencia`);
    if (e.lotes_invalidos) bits.push(`${e.lotes_invalidos} lote(s) con JSON inválido`);
    if (e.cierre) bits.push("cierre: " + e.cierre + (e.cierre_aplicado ? " (aplicado)" : ""));
    return [bits.join(" · "), e.descartadas || e.lotes_invalidos ? "warn" : "ok"];
  }
  if (e.kind === "asistente") {
    const bits = [{ directo: "calculado sin IA", cache: "de memoria", busqueda: "búsqueda + IA", vacio: "sin datos" }[e.ruta] || e.ruta];
    if (e.fragmentos) bits.push(`${e.fragmentos} fragmentos, ${e.citados} citados`);
    if (e.degradado) bits.push("IA no disponible: " + e.degradado);
    return [bits.join(" · "), e.degradado || (e.avisos || []).length ? "warn" : "ok"];
  }
  return ["✔ ok", "ok"];
}
function trzRow(e) {
  const tr = el("tr", "trz-" + e.kind);
  const [res, cls] = trzResult(e);
  const secs = e.kind === "asistente" ? (e.ms != null ? (e.ms / 1000).toFixed(1) : "—") : (e.secs != null ? e.secs : "—");
  const tok = e.kind === "llm" && e.status === "error" ? "—" : e.kind === "llm" ? `${e.prompt_tokens ?? "?"} → ${e.completion_tokens ?? "?"}${e.tokens_estimados ? " (est.)" : ""}`
    : e.kind === "asistente" && e.tokens_prompt_est ? `${e.tokens_prompt_est} → ${e.tokens_respuesta_est ?? "—"} (est.)` : "";
  const what = el("td"); what.append(el("span", "pill-k " + e.kind, TRZ_KIND[e.kind] || e.kind), " ", el("span", "", e.label));
  if (e.call_id && e.kind === "llm") what.append(el("small", "", " · llamada " + e.call_id));
  const model = e.kind === "llm" ? `${e.modelo}${e.motor && e.motor !== "local" ? " · " + e.motor : " · local"}` : "";
  const detail = (e.detalle || []).length || (e.avisos || []).length;
  const r = el("td", "trz-res " + cls, res);
  if (detail) {
    const b = el("button", "link", TRZ.open.has(e.id) ? "ocultar" : "detalle"); b.type = "button";
    b.onclick = () => { TRZ.open.has(e.id) ? TRZ.open.delete(e.id) : TRZ.open.add(e.id); trzDraw(); };
    r.append(" ", b);
  }
  tr.append(el("td", "", e.ts.slice(11)), what, el("td", "", model), el("td", "num", secs), el("td", "num", tok), r);
  if (TRZ.open.has(e.id) && detail) {
    const d = el("tr", "trz-det"), td = el("td"); td.colSpan = 6;
    const lines = (e.detalle || []).map(x => `${x.id}: ${({ si_verificado: "✔ cita verificada", cita_inventada_descartada: "✖ cita inventada, descartada",
      no_sin_evidencia: "la IA no encontró evidencia", sin_respuesta: "sin respuesta" })[x.result] || x.result}`).concat((e.avisos || []).map(w => "⚠ " + w));
    td.append(el("pre", "", lines.join("\n"))); d.append(td); return [tr, d];
  }
  return [tr];
}
let TRZ_LAST = null;
function trzDraw() {
  if (!TRZ_LAST) return;
  const body = $("#trzBody"); body.innerHTML = "";
  const evs = TRZ_LAST.eventos.slice().reverse();
  $("#trzEmpty").hidden = evs.length > 0;
  evs.forEach(e => trzRow(e).forEach(n => body.append(n)));
  trzKpis(TRZ_LAST.resumen);
}
async function trzLoad() {
  try { TRZ_LAST = await api("/api/trazas?limit=150"); trzDraw(); } catch (e) { /* el servidor se reinicia: se reintenta */ }
}
function initTrazas() {
  trzLoad();
  clearInterval(TRZ.timer);
  TRZ.timer = setInterval(() => { if ($("#view-trazas").classList.contains("active")) trzLoad(); else { clearInterval(TRZ.timer); TRZ.timer = null; } }, 2000);
}
$("#trzClear").onclick = async () => { if (confirm("¿Borrar las trazas guardadas? Las llamadas y las notas no se tocan.")) { await post("/api/trazas/limpiar"); TRZ.open.clear(); trzLoad(); } };
