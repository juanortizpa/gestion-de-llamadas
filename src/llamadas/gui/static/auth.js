"use strict";
/* Sesión dentro de la aplicación. Se carga ANTES que app.js:
   - agrega el token CSRF a toda petición que modifica datos y vuelve al inicio de sesión si la sesión caducó;
   - muestra quién está conectado y el botón Salir;
   - en Configuración: cambiar la contraseña y, para el administrador, usuarios y bitácora de accesos. */
(() => {
  const cookie = n => (document.cookie.split("; ").find(c => c.startsWith(n + "=")) || "").slice(n.length + 1);
  const raw = window.fetch.bind(window);
  window.fetch = async (url, opt = {}) => {
    const m = (opt.method || "GET").toUpperCase();
    if (m !== "GET" && m !== "HEAD") opt = { ...opt, headers: { ...(opt.headers || {}), "X-CSRF-Token": cookie("gdl_csrf") } };
    const r = await raw(url, opt);
    if (r.status === 401 && !String(url).startsWith("/api/auth/")) location.replace("/login");
    return r;
  };

  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const ROL = { admin: "Administrador", auditor: "Auditor" };
  const EVENTO = { login: "Entró", logout: "Salió", login_fallido: "Contraseña o usuario incorrecto", login_bloqueado: "Intento con el usuario bloqueado",
    sesion_caducada: "Sesión caducada", usuario_creado: "Usuario creado", usuario_eliminado: "Usuario eliminado", clave_cambiada: "Cambió su contraseña",
    clave_fallida: "Falló al cambiar la contraseña", permiso_denegado: "Acción sin permiso", csrf_rechazado: "Petición rechazada", accion: "Acción",
    error_interno: "Error interno" };
  const post = async (ruta, datos, method = "POST") => {
    const r = await fetch(ruta, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos || {}) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || "No se pudo completar la acción.");
    return d;
  };
  const campo = (titulo, ayuda, input) => { const it = el("div", "set-item"), l = el("div", "set-lbl"); l.append(el("b", "", titulo), el("small", "", ayuda)); it.append(l, input); return it; };
  const entrada = (attrs) => Object.assign(el("input"), attrs);

  function barra(ses) {
    const box = document.querySelector(".top-actions"); if (!box) return;
    const quien = el("span", "hint", (ses.nombre || ses.usuario) + " · " + ROL[ses.rol]); quien.style.margin = "0"; quien.style.alignSelf = "center";
    const salir = el("button", "btn", "Salir"); salir.type = "button"; salir.title = "Cerrar la sesión en este navegador";
    salir.onclick = async () => { try { await post("/api/auth/salir"); } finally { location.replace("/login"); } };
    box.append(quien, salir);
  }

  function tarjetaClave(grid) {
    const card = el("div", "card"), head = el("div", "set-head"), tit = el("div");
    tit.append(el("h2", "", "Mi contraseña"), el("p", "", "Al cambiarla se cierran sus otras sesiones abiertas."));
    head.append(tit); card.append(head);
    const actual = entrada({ type: "password", autocomplete: "current-password" }), nueva = entrada({ type: "password", autocomplete: "new-password", minLength: 10 });
    const msg = el("span", "hint"), btn = el("button", "btn primary", "Cambiar contraseña"); btn.type = "button";
    btn.onclick = async () => {
      try { await post("/api/auth/clave", { actual: actual.value, nueva: nueva.value }); actual.value = nueva.value = ""; msg.textContent = "Contraseña cambiada."; }
      catch (e) { msg.textContent = e.message; }
    };
    const row = el("div", "row"); row.append(btn, msg);
    card.append(campo("Contraseña actual", "Para confirmar que es usted.", actual), campo("Contraseña nueva", "Mínimo 10 caracteres, con letras y números.", nueva), row);
    grid.append(card);
  }

  function tarjetaUsuarios(grid, ses) {
    const card = el("div", "card"), head = el("div", "set-head"), tit = el("div");
    tit.append(el("h2", "", "Usuarios y accesos"), el("p", "", "Cada persona entra con su propio usuario. El auditor analiza y revisa; solo el administrador elimina llamadas, cambia el correo y crea usuarios."));
    head.append(tit); card.append(head);
    const lista = el("div", "set-item"), msg = el("span", "hint");
    const usuario = entrada({ placeholder: "usuario (ej. lgomez)", autocomplete: "off", autocapitalize: "none", spellcheck: false });
    const nombre = entrada({ placeholder: "Nombre completo", autocomplete: "off", maxLength: 80 });
    const clave = entrada({ type: "password", placeholder: "Contraseña inicial (mínimo 10)", autocomplete: "new-password" });
    const rol = el("select"); rol.append(new Option("Auditor", "auditor"), new Option("Administrador", "admin"));
    const crear = el("button", "btn primary", "Crear usuario"); crear.type = "button";
    const hist = el("details", "sources"), histBody = el("div", "mail-hist");
    hist.append(el("summary", "", "Últimos accesos y acciones"), histBody);

    async function pintar() {
      const d = await (await fetch("/api/usuarios")).json();
      lista.replaceChildren();
      (d.usuarios || []).forEach(u => {
        const fila = el("div", "row"), txt = el("span", "", (u.nombre || u.usuario) + " (" + u.usuario + ") · " + ROL[u.rol]); txt.style.flex = "1";
        fila.append(txt);
        if (u.usuario !== ses.usuario) {
          const del = el("button", "btn danger", "Eliminar"); del.type = "button";
          del.onclick = async () => {
            if (!confirm("¿Eliminar el usuario " + u.usuario + "? Ya no podrá entrar.")) return;
            try { await post("/api/usuarios/" + u.usuario, null, "DELETE"); msg.textContent = "Usuario eliminado."; pintar(); } catch (e) { msg.textContent = e.message; }
          };
          fila.append(del);
        } else fila.append(el("span", "hint", "usted"));
        lista.append(fila);
      });
    }
    crear.onclick = async () => {
      try {
        await post("/api/usuarios", { usuario: usuario.value.trim().toLowerCase(), nombre: nombre.value, clave: clave.value, rol: rol.value });
        usuario.value = nombre.value = clave.value = ""; msg.textContent = "Usuario creado. Entréguele la contraseña en persona y pídale que la cambie."; pintar();
      } catch (e) { msg.textContent = e.message; }
    };
    hist.addEventListener("toggle", async () => {
      if (!hist.open) return;
      const d = await (await fetch("/api/accesos")).json();
      histBody.replaceChildren();
      (d.eventos || []).slice(0, 100).forEach(ev => histBody.append(el("div", "", ev.ts + " · " + (ev.usuario || "—") + " · " + (EVENTO[ev.evento] || ev.evento) +
        (ev.ruta ? " · " + ev.ruta : "") + (ev.sobre ? " · " + ev.sobre : ""))));
      if (!histBody.children.length) histBody.textContent = "Aún no hay registros.";
    });
    const nuevo = el("div", "set-item"), lbl = el("div", "set-lbl"); lbl.append(el("b", "", "Nuevo usuario"), el("small", "", "El usuario va en minúsculas, sin espacios."));
    const row = el("div", "row"); row.append(crear, msg);
    nuevo.append(lbl, usuario, nombre, clave, rol, row);
    card.append(lista, nuevo, hist);
    grid.append(card);
    pintar();
  }

  document.addEventListener("DOMContentLoaded", async () => {
    let ses = null;
    try { ses = (await (await raw("/api/auth/estado")).json()).sesion; } catch (e) { /* sin conexión: las demás peticiones avisarán */ }
    if (!ses) { location.replace("/login"); return; }
    window.SESION = ses;
    barra(ses);
    const mail = document.getElementById("mailCard"), grid = mail ? mail.parentElement : document.getElementById("view-config");
    if (!grid) return;
    tarjetaClave(grid);
    if (ses.rol === "admin") tarjetaUsuarios(grid, ses);
    else if (mail) mail.hidden = true; // el correo solo lo configura el administrador
  });
})();
