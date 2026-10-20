"use strict";
/* Analisis de quejas, insignia de la pestaña, comentarios sobre la app y correo. Usa $, $$, el, api, toast, segment de app.js. */
const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) }).then(async r => {
  const j = await r.json(); if (!r.ok || j.error) throw new Error(j.error || "Error " + r.status); return j;
});

/* ---------- quejas: donde se concentran y si se responden a tiempo ---------- */
function bars(title, rows) {
  const box = el("div"); box.append(el("h3", "", title));
  if (!rows.length) { box.append(el("p", "hint", "Sin datos aún.")); return box; }
  const max = Math.max(...rows.map(r => r.n));
  rows.forEach(r => { const b = el("div", "bar"); b.append(el("span", "", r.clave), el("b", "", r.n)); const i = el("i"); i.style.width = Math.max(4, 100 * r.n / max) + "%"; b.append(i); box.append(b); });
  return box;
}
function renderQStats(st) {
  const box = $("#qStats"); if (!st || !st.total) { box.hidden = true; return; }
  box.hidden = false; box.innerHTML = "";
  const head = el("div", "set-head"); head.innerHTML = '<span class="mode-ic"><svg class="i"><use href="#i-target"/></svg></span>';
  const t = el("div"); t.append(el("h2", "", "Dónde se concentran las quejas"), el("p", "", "Para decidir qué corregir primero: categorías, asesores y sedes con más quejas."));
  head.append(t); box.append(head);
  const k = el("div", "qs-kpis");
  [[st.total, "quejas registradas"], [st.a_tiempo_pct == null ? "—" : st.a_tiempo_pct + " %", "cerradas a tiempo"], [st.dias_cierre == null ? "—" : st.dias_cierre + " d", "promedio hasta cerrar"]]
    .forEach(([v, l]) => { const d = el("div"); d.append(el("b", "", v), el("small", "", l)); k.append(d); });
  box.append(k);
  const g = el("div", "qs-grid"); g.append(bars("Por categoría", st.por_categoria), bars("Por asesor", st.por_asesor), bars("Por sede", st.por_sede)); box.append(g);
}
/* Insignia roja en «Quejas»: vencidas + posibles quejas detectadas sin revisar */
async function refreshBadge() {
  try {
    const q = await api("/api/quejas"), n = q.quejas.filter(x => x.vencida).length + q.sugeridas.length, tab = $('.tab[data-view="quejas"]');
    tab.querySelector(".badge")?.remove(); if (n) { const b = el("span", "badge", String(n)); b.title = "Quejas vencidas o por revisar"; tab.append(b); moveGlider(); }
  } catch (e) { /* sin insignia */ }
}
setTimeout(refreshBadge, 1500); setInterval(refreshBadge, 120000);

/* ---------- comentarios sobre la app ---------- */
const COM = { tipo: "sugerencia", ready: false };
function renderTipoSeg(tipos) { segment($("#cTipoSeg"), Object.entries(tipos), COM.tipo, v => { COM.tipo = v; renderTipoSeg(tipos); }); }
async function loadComentarios() {
  const d = await api("/api/comentarios"); COM.tipos = d.tipos; renderTipoSeg(d.tipos);
  const list = $("#cList"); list.innerHTML = "";
  $("#cCount").textContent = d.items.length ? `${d.items.length} comentario${d.items.length > 1 ? "s" : ""}, ${d.items.filter(c => c.estado === "nuevo").length} nuevo(s).` : "Aún no hay comentarios.";
  d.items.forEach(c => {
    const it = el("div", "c-item " + c.estado), h = el("div", "c-h");
    h.append(el("b", "", c.id), el("span", "", d.tipos[c.tipo] || c.tipo), el("span", "", c.fecha), el("span", "", [c.nombre, c.contacto].filter(Boolean).join(" · ")), el("span", "pill", d.estados[c.estado]));
    const act = el("div", "c-act");
    Object.entries(d.estados).filter(([k]) => k !== c.estado).forEach(([k, l]) => { const b = el("button", "btn ghost", "Marcar " + l.toLowerCase()); b.type = "button"; b.onclick = async () => { await post("/api/comentarios/" + c.id, { estado: k }); loadComentarios(); }; act.append(b); });
    const del = el("button", "btn ghost", "Eliminar"); del.type = "button";
    del.onclick = async () => { if (confirm("¿Eliminar el comentario " + c.id + "?")) { await fetch("/api/comentarios/" + c.id, { method: "DELETE" }); loadComentarios(); } };
    act.append(del); it.append(h, el("p", "", c.mensaje), act); list.append(it);
  });
}
async function initComentarios() { try { await loadComentarios(); } catch (e) { toast("No se pudieron cargar los comentarios"); } }
$("#cForm").onsubmit = async e => {
  e.preventDefault(); const btn = $("#cEnviar"), msg = $("#cMsg"); btn.disabled = true; msg.textContent = "";
  try {
    await post("/api/comentarios", { tipo: COM.tipo, mensaje: $("#cMensaje").value, nombre: $("#cNombre").value, contacto: $("#cContacto").value, vista: $(".tab.active")?.dataset.view || "" });
    $("#cMensaje").value = ""; toast("¡Gracias! Comentario guardado", "ok"); loadComentarios();
  } catch (err) { msg.textContent = err.message; }
  finally { btn.disabled = false; }
};

/* ---------- correo ---------- */
async function initMail() {
  try {
    const d = await api("/api/notify");
    $("#mailStatus").textContent = d.smtp ? `Correo listo: se envía desde ${d.sender} por ${d.host}.` : "El servidor de correo aún no está configurado: complete SMTP_HOST, SMTP_USER, SMTP_PASSWORD y SMTP_FROM en el archivo .env y reinicie la aplicación.";
    $("#mailTo").value = d.to.join(", ");
    const box = $("#mailEvents"); box.innerHTML = "";
    Object.entries(d.events_info).forEach(([k, l]) => { const lb = el("label"), cb = el("input"); cb.type = "checkbox"; cb.checked = d.events[k]; cb.dataset.k = k; lb.append(cb, " " + l); box.append(lb); });
    const h = $("#mailHist"); h.innerHTML = d.history.length ? "" : "Aún no se ha enviado ningún aviso.";
    d.history.forEach(x => h.append(el("div", x.ok ? "" : "bad", `${x.ts} · ${x.asunto}${x.ok ? "" : " — " + x.error}`)));
  } catch (e) { $("#mailStatus").textContent = ""; }
}
const mailBody = () => ({ to: $("#mailTo").value, events: Object.fromEntries($$("#mailEvents input").map(c => [c.dataset.k, c.checked])) });
$("#mailSave").onclick = async () => { try { await post("/api/notify", mailBody()); $("#mailMsg").textContent = "Guardado."; initMail(); } catch (e) { $("#mailMsg").textContent = e.message; } };
$("#mailTest").onclick = async () => {
  $("#mailMsg").textContent = "Enviando…";
  try { await post("/api/notify", mailBody()); await post("/api/notify/test"); $("#mailMsg").textContent = "Correo de prueba enviado. Revise su bandeja."; }
  catch (e) { $("#mailMsg").textContent = e.message; }
};
