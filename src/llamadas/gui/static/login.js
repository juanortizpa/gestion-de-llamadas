"use strict";
/* Inicio de sesión y creación del administrador en el primer arranque. La contraseña solo viaja a este mismo equipo (127.0.0.1). */
(() => {
  const $ = s => document.querySelector(s);
  const logo = $("#logo"); // el logo es opcional: si no está, no se deja el hueco
  if (logo.complete && !logo.naturalWidth) logo.remove(); else logo.addEventListener("error", () => logo.remove());

  async function enviar(ruta, datos, err, btn) {
    err.hidden = true; btn.disabled = true;
    try {
      const r = await fetch(ruta, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.ok) { location.replace("/"); return; }
      err.textContent = d.error || "No se pudo iniciar sesión. Intente de nuevo.";
    } catch (e) {
      err.textContent = "No hay conexión con el programa. Compruebe que sigue abierto.";
    }
    err.hidden = false; btn.disabled = false;
  }

  $("#fLogin").addEventListener("submit", e => {
    e.preventDefault();
    enviar("/api/auth/login", { usuario: $("#lUsuario").value, clave: $("#lClave").value }, $("#lError"), $("#lBtn"));
  });

  $("#fAdmin").addEventListener("submit", e => {
    e.preventDefault();
    const err = $("#aError");
    if ($("#aClave").value !== $("#aClave2").value) { err.textContent = "Las dos contraseñas no coinciden."; err.hidden = false; $("#aClave2").focus(); return; }
    enviar("/api/auth/crear-admin", { nombre: $("#aNombre").value, usuario: $("#aUsuario").value.trim().toLowerCase(), clave: $("#aClave").value }, err, $("#aBtn"));
  });

  fetch("/api/auth/estado").then(r => r.json()).then(d => {
    if (d.sesion) { location.replace("/"); return; }
    const f = d.configurado ? $("#fLogin") : $("#fAdmin");
    f.hidden = false; f.querySelector("input").focus();
  }).catch(() => { $("#fLogin").hidden = false; });
})();
