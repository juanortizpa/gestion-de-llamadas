"use strict";
/* Asistente de consulta. Usa $, el, api y openCall de app.js (se carga antes). La conversación NO se guarda en el navegador (puede contener datos personales). */
const CHAT = { ctx: null, history: [], ctl: null, busy: false, ready: false };
const SUGGEST = ["¿Cuántas llamadas hubo este mes?", "¿Qué asesor tiene la nota promedio más baja?", "¿Qué porcentaje de llamadas no cumple la despedida (Z2)?",
  "Dame las llamadas no aprobadas de la semana pasada", "¿Qué dicen los asesores cuando el cliente pide cancelar la cita?"];
const escHtml = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/* Markdown mínimo y seguro: primero se escapa todo el HTML; solo se reconocen **negrita**, _cursiva_, listas, tablas, [n] y [id](call:id) */
function inlineMd(t) {
  return escHtml(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[\s(])_(.+?)_(?=[\s).,;:]|$)/g, "$1<i>$2</i>")
    .replace(/\[([A-Za-z0-9_.-]{1,60})\]\(call:([A-Za-z0-9_.-]{1,60})\)/g, '<a href="#" class="call-link" data-id="$2">$1</a>')
    .replace(/\[(\d{1,2})\]/g, '<sup class="cite" data-n="$1">[$1]</sup>');
}
function renderMd(text) {
  const lines = text.split("\n"), out = []; let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (/^\s*\|/.test(ln) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      const cells = l => l.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      let h = "<div class='md-table'><table><thead><tr>" + cells(ln).map(c => `<th>${inlineMd(c)}</th>`).join("") + "</tr></thead><tbody>"; i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) { h += "<tr>" + cells(lines[i]).map(c => `<td>${inlineMd(c)}</td>`).join("") + "</tr>"; i++; }
      out.push(h + "</tbody></table></div>"); continue;
    }
    if (/^\s*[-*] /.test(ln)) {
      let h = "<ul>"; while (i < lines.length && /^\s*[-*] /.test(lines[i])) { h += `<li>${inlineMd(lines[i].replace(/^\s*[-*] /, ""))}</li>`; i++; }
      out.push(h + "</ul>"); continue;
    }
    if (ln.trim() === "") { i++; continue; }
    const para = []; while (i < lines.length && lines[i].trim() !== "" && !/^\s*(\||[-*] )/.test(lines[i])) para.push(inlineMd(lines[i++]));
    out.push("<p>" + para.join("<br>") + "</p>");
  }
  return out.join("");
}

function chatScroll() { const l = $("#chatLog"); l.scrollTop = l.scrollHeight; }
function addMsg(role) {
  const m = el("div", "msg " + role), b = el("div", "bubble"); m.append(b); $("#chatLog").append(m); chatScroll(); return { m, b };
}
async function refreshChatStatus() {
  try {
    const s = await api("/api/chat/status"), bits = [];
    bits.push(s.indexing?.running ? `Indexando ${s.indexing.done} de ${s.indexing.total}…` : `${s.calls} llamadas indexadas`);
    bits.push(s.vectors_enabled ? "búsqueda semántica activa" : "búsqueda por palabras (sin modelo de embeddings)");
    bits.push(s.busy_batch ? "IA ocupada con un análisis" : s.llm_available ? "IA lista" : "sin IA (solo fragmentos)");
    $("#chatStatus").textContent = bits.join(" · ");
  } catch (e) { $("#chatStatus").textContent = ""; }
}
function initChat() {
  refreshChatStatus();
  if (CHAT.ready) { $("#chatInput").focus(); return; }
  CHAT.ready = true;
  const box = $("#chatSuggest"); box.innerHTML = "";
  SUGGEST.forEach(q => { const b = el("button", "chipf", q); b.type = "button"; b.onclick = () => sendChat(q); box.append(b); });
  addMsg("bot").b.innerHTML = renderMd("Hola. Puedo **contar, comparar y listar** llamadas (sin gastar IA) y **buscar lo que se dijo** en las transcripciones. Si una respuesta usa la IA, verá las fuentes y puede abrirlas.");
}
function renderSources(wrap, sources) {
  if (!sources?.length) return;
  const det = el("details", "sources"); det.append(el("summary", "", `Fuentes (${sources.length})`));
  [...sources].sort((a, b) => (b.cited ? 1 : 0) - (a.cited ? 1 : 0) || a.n - b.n).forEach(s => {
    const it = el("div", "src" + (s.cited ? " cited" : "")); it.id = "src-" + wrap.dataset.mid + "-" + s.n;
    const head = el("div", "src-h"); head.append(el("b", "", `[${s.n}]`), el("span", "", " " + (s.ctx || "Llamada " + s.call_id)));
    const open = el("button", "btn ghost", "Abrir llamada"); open.type = "button"; open.onclick = () => openCall(s.call_id); head.append(open);
    it.append(head); if (s.snippet) it.append(el("blockquote", "", s.snippet)); det.append(it);
  });
  wrap.append(det); if (sources.some(s => s.cited)) det.open = true;
}

async function sendChat(q) {
  q = (q ?? $("#chatInput").value).trim();
  if (!q || CHAT.busy) return;
  CHAT.busy = true; $("#chatInput").value = ""; autoGrow(); $("#chatSend").hidden = true; $("#chatStop").hidden = false; $("#chatSuggest").hidden = true;
  addMsg("user").b.textContent = q;
  const { m, b } = addMsg("bot"); m.dataset.mid = String(Date.now()); b.classList.add("thinking"); b.textContent = "Buscando…";
  const meta = el("div", "meta"); let raw = "", raf = 0;
  const paint = () => { raf = 0; b.classList.remove("thinking"); b.innerHTML = renderMd(raw); chatScroll(); };
  CHAT.ctl = new AbortController();
  try {
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, signal: CHAT.ctl.signal,
      body: JSON.stringify({ question: q, ctx: CHAT.ctx, history: CHAT.history.slice(-2) }) });
    if (!r.ok || !r.body) throw new Error("el asistente no respondió (" + r.status + ")");
    const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await rd.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let k; while ((k = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!line) continue;
        const ev = JSON.parse(line);
        if (ev.type === "route") {
          const label = { directo: "Calculado sin IA", cache: "Respuesta reutilizada", busqueda: "Buscando en las llamadas" }[ev.route] ?? "";
          meta.innerHTML = (label ? `<span class="route">${label}</span>` : "") + (ev.filters || []).map(f => `<span class="chipf static">${escHtml(f)}</span>`).join("");
          if (meta.innerHTML) m.insertBefore(meta, b);
        } else if (ev.type === "token") { raw += ev.text; if (!raf) raf = requestAnimationFrame(paint);
        } else if (ev.type === "final_text") { raw = ev.text; paint();
        } else if (ev.type === "sources") { paint(); renderSources(m, ev.sources);
        } else if (ev.type === "error") { raw = ev.message; paint(); b.classList.add("err");
        } else if (ev.type === "done") {
          paint(); CHAT.ctx = ev.ctx;
          (ev.warnings || []).forEach(w => m.append(el("p", "warn-line", "⚠ " + w)));
          const st = ev.stats || {}, bits = [];
          if (st.ms != null) bits.push((st.ms / 1000).toFixed(1) + " s");
          if (st.fragments) bits.push(st.fragments + " fragmentos");
          if (st.cached) bits.push("de memoria");
          if (st.degraded) bits.push("IA no disponible");
          if (bits.length) m.append(el("p", "stats", bits.join(" · ")));
          CHAT.history.push({ q, a: raw.slice(0, 400) }); if (CHAT.history.length > 6) CHAT.history.shift();
        }
      }
    }
  } catch (e) {
    if (e.name === "AbortError") { raw += raw ? "\n\n_(detenido)_" : "_(detenido)_"; paint(); }
    else { raw = "No pude obtener respuesta: " + e.message; paint(); b.classList.add("err"); }
  } finally {
    CHAT.busy = false; CHAT.ctl = null; $("#chatSend").hidden = false; $("#chatStop").hidden = true; $("#chatSuggest").hidden = false; refreshChatStatus();
  }
}
function autoGrow() { const t = $("#chatInput"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; }
$("#chatForm").onsubmit = e => { e.preventDefault(); sendChat(); };
$("#chatInput").addEventListener("input", autoGrow);
$("#chatInput").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); } });
$("#chatStop").onclick = () => CHAT.ctl?.abort();
$("#chatLog").addEventListener("click", e => {
  const a = e.target.closest(".call-link"); if (a) { e.preventDefault(); openCall(a.dataset.id); return; }
  const c = e.target.closest(".cite"); if (c) {
    const msg = c.closest(".msg"), t = msg?.querySelector("#src-" + msg.dataset.mid + "-" + c.dataset.n);
    if (t) { t.closest("details").open = true; t.scrollIntoView({ block: "nearest", behavior: "smooth" }); t.classList.add("flash"); setTimeout(() => t.classList.remove("flash"), 1400); }
  }
});
