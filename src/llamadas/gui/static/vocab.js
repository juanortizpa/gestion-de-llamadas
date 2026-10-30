"use strict";
/* Entrevista de vocabulario del dominio. Usa $, el, api, toast de app.js. */
const VOC = { ready: false, busy: false, data: null, shownQ: null };
async function vocPost(path, body) {
  const r = await fetch("/api/vocab/" + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const j = await r.json(); if (!r.ok || j.error) throw new Error(j.error || "Error " + r.status); return j;
}
function vocMsg(role, text) {
  const m = el("div", "msg " + role), b = el("div", "bubble"); b.textContent = text; m.append(b); $("#vocabLog").append(m);
  const l = $("#vocabLog"); l.scrollTop = l.scrollHeight; return { m, b };
}
function vocRender(d) {
  VOC.data = d;
  $("#vocabProg").innerHTML = "";
  Object.entries(d.areas_info).forEach(([k, label]) => { const s = el("span", d.coverage[k] ? "on" : "", k); s.title = label; $("#vocabProg").append(s); });
  $("#vocabProg").append(el("span", "", `${d.answers} respuestas · ${d.terms.length} términos`));
  const pend = d.pending, box = $("#vocabOpts"); box.innerHTML = "";
  if (pend && pend.question !== VOC.shownQ) {
    VOC.shownQ = pend.question;
    const { m } = vocMsg("bot", pend.question);
    if (pend.why) m.append(el("p", "vocab-why", "Para qué: " + pend.why));
  }
  if (pend && d.status === "active") (pend.options || []).forEach(o => { const b = el("button", "chipf", o); b.type = "button"; b.onclick = () => vocSend(o); box.append(b); });
  const paused = d.status === "paused" && !!pend;
  $("#vocabPause").textContent = paused ? "Seguir ampliando" : "Listo por ahora";
  $("#vocabPause").dataset.paused = paused ? "1" : "";
  $("#vocabInput").disabled = $("#vocabSend").disabled = $("#vocabSkip").disabled = paused;
  const know = $("#vocabKnow"); know.innerHTML = "";
  const rm = (kind, i) => { const x = el("button", "", "×"); x.type = "button"; x.setAttribute("aria-label", "Quitar"); x.onclick = () => vocEdit({ action: "remove", kind, index: i }); return x; };
  const grp = (title, kind, items, tag) => {
    if (!items.length) return;
    const g = el("div", "grp"); g.append(el("b", "", title));
    items.forEach((it, i) => {
      if (tag) {
        const t = el("span", "vtag", it.term);
        t.title = [it.category, it.note, (it.variants || []).length ? "Mal oído como: " + it.variants.join(", ") : ""].filter(Boolean).join(" · ");
        t.append(rm(kind, i)); g.append(t);
      } else { const l = el("div", "vline"); l.append(el("span", "", "• " + it), rm(kind, i)); g.append(l); }
    });
    know.append(g);
  };
  grp("Términos", "terms", d.terms, true); grp("Contexto", "context", d.context); grp("Qué debe esperarse oír", "predict", d.predict);
  if (!know.children.length) know.append(el("p", "hint", "Aún no hay nada. Responda las preguntas de la izquierda."));
  $("#vocabPrompt").textContent = d.prompt;
}
async function vocEdit(body) { try { vocRender(await vocPost("edit", body)); } catch (e) { toast(e.message, "err"); } }
async function vocSend(answer, skip) {
  if (VOC.busy) return;
  answer = (answer ?? $("#vocabInput").value).trim(); if (!answer && !skip) return;
  VOC.busy = true; $("#vocabInput").value = ""; $("#vocabOpts").innerHTML = "";
  vocMsg("user", skip ? "No sé / omitir" : answer);
  const th = vocMsg("bot", "Pensando…"); th.b.classList.add("thinking");
  try {
    const d = await vocPost("turn", { answer, skip: !!skip }); th.m.remove();
    const n = d.added ? d.added.terms.length + d.added.context.length + d.added.predict.length : 0;
    if (n) toast(`Aprendido: ${n} dato${n > 1 ? "s" : ""} nuevo${n > 1 ? "s" : ""}`);
    vocRender(d);
  } catch (e) { th.b.classList.remove("thinking"); th.b.classList.add("err"); th.b.textContent = e.message; }
  finally { VOC.busy = false; }
}
async function initVocab() {
  if (VOC.ready) return;
  VOC.ready = true;
  try {
    const d = await api("/api/vocab"); vocRender(d);
    if (!d.pending) {
      vocMsg("bot", "Hola. Voy a hacerle unas preguntas para aprender el vocabulario de sus llamadas. Responda con sus palabras o elija una opción; puede parar cuando quiera.");
      VOC.busy = true;
      const th = vocMsg("bot", "Preparando la primera pregunta…"); th.b.classList.add("thinking");
      try { const d2 = await vocPost("turn", {}); th.m.remove(); vocRender(d2); }
      catch (e) { th.b.classList.remove("thinking"); th.b.classList.add("err"); th.b.textContent = e.message; VOC.ready = false; }
      finally { VOC.busy = false; }
    }
  } catch (e) { VOC.ready = false; }
}
$("#vocabForm").onsubmit = e => { e.preventDefault(); vocSend(); };
$("#vocabInput").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); vocSend(); } });
$("#vocabSkip").onclick = () => vocSend("", true);
$("#vocabPause").onclick = async () => {
  try {
    if ($("#vocabPause").dataset.paused === "1") { VOC.shownQ = null; vocRender(await vocPost("status", { status: "active" })); }
    else { vocRender(await vocPost("status", { status: "paused" })); vocMsg("bot", "Listo por ahora. Lo aprendido ya se usa en las próximas transcripciones. Cuando quiera, pulse «Seguir ampliando»."); }
  } catch (e) { toast(e.message, "err"); }
};
$("#vocabAddBtn").onclick = () => { const v = $("#vocabAdd").value.trim(); if (v) { $("#vocabAdd").value = ""; vocEdit({ action: "add", value: v }); } };
$("#vocabReset").onclick = async () => {
  if (!confirm("¿Borrar todo el vocabulario y la entrevista?")) return;
  await vocEdit({ action: "reset" }); $("#vocabLog").innerHTML = ""; VOC.shownQ = null; VOC.ready = false; initVocab();
};
