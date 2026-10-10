"""Genera index.html (composición única de 90 s) para el video «Auditoría de Llamadas con IA».

Una sola composición con 14 escenas (.scene) + capas persistentes (fondo, mascota Auri).
Uso:  python tools/build_index.py
"""
from pathlib import Path
import html

ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ helpers
def esc(s):
    return html.escape(s, quote=False)


def chars(text, cls="ty"):
    """Texto letra por letra (cada letra oculta con display:none hasta su tl.set)."""
    out = []
    for ch in text:
        c = "&nbsp;" if ch == " " else esc(ch)
        out.append(f'<span class="{cls}">{c}</span>')
    return "".join(out)


def win(sid, title, sub, tab, body, style="", extra_cls=""):
    tabs = ""
    if tab:
        names = ["1 Cargar y analizar", "2 Resultados y revisión", "Configuración"]
        tabs = '<div class="tabs">' + "".join(
            f'<span class="tab{" on" if i == tab - 1 else ""}">{n}</span>' for i, n in enumerate(names)
        ) + "</div>"
    return f'''<div class="win {extra_cls}" id="{sid}" style="{style}">
  <div class="top"><span class="logo"></span><span class="ttl"><b>{title}</b><small>{sub}</small></span></div>
  {tabs}
  <div class="body">{body}</div>
</div>'''


CURSOR = '''<svg class="cursor" id="{id}" viewBox="0 0 40 52" width="44" height="58"><path d="M4 2 L4 40 L14 31 L21 48 L28 45 L21 29 L35 29 Z" fill="#FFFFFF" stroke="#001F78" stroke-width="3" stroke-linejoin="round"/></svg>'''


def cursor(cid):
    return CURSOR.replace("{id}", cid)


def bubble(bid, text, style):
    return f'<div class="bub-auri" id="{bid}" style="{style}"><i></i>{esc(text)}</div>'


AURI = '''<svg viewBox="0 0 200 200" width="100%" height="100%" overflow="visible">
  <ellipse id="auri-shadow" cx="100" cy="186" rx="46" ry="8" fill="#000A2E" opacity=".35"/>
  <g id="auri-body">
    <line x1="100" y1="44" x2="100" y2="22" stroke="#E6B32A" stroke-width="5" stroke-linecap="round"/>
    <circle id="auri-ant" cx="100" cy="16" r="8" fill="#E6B32A"/>
    <circle cx="100" cy="106" r="64" fill="#001F78"/>
    <circle cx="100" cy="106" r="64" fill="none" stroke="#2F4FC0" stroke-width="4" opacity=".7"/>
    <path d="M44 100 C44 52 156 52 156 100" fill="none" stroke="#E6B32A" stroke-width="9" stroke-linecap="round"/>
    <rect x="58" y="74" width="84" height="60" rx="24" fill="#EAF0FF"/>
    <g id="auri-eyes">
      <rect class="eye" x="76" y="88" width="13" height="20" rx="6.5" fill="#001F78"/>
      <rect class="eye" x="111" y="88" width="13" height="20" rx="6.5" fill="#001F78"/>
    </g>
    <g id="auri-mouth">
      <rect class="mb" x="83" y="116" width="5" height="7" rx="2.5" fill="#E6B32A"/>
      <rect class="mb" x="91" y="114" width="5" height="11" rx="2.5" fill="#E6B32A"/>
      <rect class="mb" x="99" y="112" width="5" height="15" rx="2.5" fill="#E6B32A"/>
      <rect class="mb" x="107" y="114" width="5" height="11" rx="2.5" fill="#E6B32A"/>
      <rect class="mb" x="115" y="116" width="5" height="7" rx="2.5" fill="#E6B32A"/>
    </g>
    <circle cx="38" cy="106" r="15" fill="#E6B32A"/>
    <circle cx="162" cy="106" r="15" fill="#E6B32A"/>
    <path d="M40 118 C44 150 64 160 82 156" fill="none" stroke="#E6B32A" stroke-width="5" stroke-linecap="round"/>
    <circle cx="84" cy="156" r="6" fill="#E6B32A"/>
    <g id="auri-arm">
      <path d="M156 140 C170 136 180 126 186 112" fill="none" stroke="#001F78" stroke-width="14" stroke-linecap="round"/>
      <circle cx="188" cy="108" r="12" fill="#EAF0FF" stroke="#001F78" stroke-width="5"/>
    </g>
  </g>
</svg>'''

# ------------------------------------------------------------------ scenes
S = []

# 01 — Gancho
S.append(f'''<div class="scene" id="s1"><div class="inner">
  <div class="meta" style="left:150px;top:120px">operación diaria · call center</div>
  <div id="s1-big" class="kbig">1.500</div>
  <div id="s1-big-lbl" class="biglbl">llamadas al día</div>
  <div id="s1-ten" class="kbig acc">10</div>
  <div id="s1-ten-lbl" class="biglbl">auditadas a mano</div>
  <div id="s1-recap"><s>1.500 llamadas al día</s> · <s>10 auditadas a mano</s></div>
  <div id="s1-q1" class="kbig">¿Y las otras</div>
  <div id="s1-q2" class="kbig acc"><span id="s1-count">1.490</span>?</div>
  <div id="s1-rule" class="rule"></div>
</div></div>''')

# 02 — Presentación
title_letters = "".join(f'<span class="lt">{"&nbsp;" if c == " " else esc(c)}</span>' for c in "Auditoría de Llamadas")
S.append(f'''<div class="scene" id="s2"><div class="inner">
  <div class="ghost" style="right:-80px;bottom:-60px">IA</div>
  <div class="meta" style="left:120px;top:110px">Angiografía de Occidente</div>
  <div id="s2-title" class="kbig">{title_letters}</div>
  <div id="s2-ia" class="kbig acc">con IA</div>
  <div id="s2-priv" class="mono">{chars("100 % en este computador · sin internet")}<span class="caret"></span></div>
</div></div>''')

# 03 — Cargar
body3 = f'''<p class="h2">1. Cargue las llamadas</p>
<div class="drop" id="s3-drop"><span class="drop-hint" id="s3-hint">Arrastre aquí audios .gsm, .mp3 o .wav</span>
  <span class="file" id="s3-f1">llamada_0451.gsm</span><span class="file" id="s3-f2">llamada_0452.mp3</span><span class="file" id="s3-f3">llamada_0453.wav</span></div>
<p class="h2" style="margin-top:34px">2. Analice</p>
<div class="row-sb"><span class="seg" id="s3-seg"><span class="seg-glider" id="s3-glider"></span><span class="segi">Rápido</span><span class="segi">Preciso</span><span class="segi">Solo reglas</span></span>
<span class="btn pri" id="s3-btn"><span id="s3-btn-a">▶ Analizar llamadas</span><span id="s3-btn-b">Analizando…</span></span></div>'''
S.append(f'''<div class="scene" id="s3"><div class="inner">
  {win("s3-win", "Auditoría de Llamadas", "Todo se procesa en este computador. Ningún audio sale de aquí.", 1, body3, "left:300px;top:90px;width:1320px;height:760px")}
  <div class="ripple" id="s3-r1"></div><div class="ripple" id="s3-r2"></div>
  {cursor("s3-cur")}
  {bubble("s3-bub", "Arrastre los audios y listo.", "left:300px;top:902px")}
</div></div>''')

# 04 — Procesando
steps = [("Audio convertido", "s4-st1"), ("Transcripción completa", "s4-st2"), ("Hablantes separados: asesor y cliente", "s4-st3"),
         ("Mensajes grabados y música de espera detectados", "s4-st4"), ("Criterios de la guía evaluados", "s4-st5")]
steps_html = "".join(f'<li id="{i}"><span class="dot run"><b>✓</b></span>{esc(t)}</li>' for t, i in steps)
body4 = f'''<p class="h2" id="s4-h">Analizando…</p>
<div class="bar"><i id="s4-fill"></i></div>
<div class="row-sb" style="margin-top:14px;font-size:26px;color:#4A5275"><span id="s4-cnt">Llamada <b id="s4-n">1</b> de 3</span>
<b style="color:#001F78" class="swap"><span id="s4-e1">Quedan ~3 min</span><span id="s4-e2">Quedan ~2 min</span><span id="s4-e3">Quedan ~1 min</span><span id="s4-e4">Listo ✓</span></b></div>
<ul class="steps">{steps_html}</ul>'''
S.append(f'''<div class="scene" id="s4"><div class="inner">
  {win("s4-win", "Auditoría de Llamadas", "Analizando en este equipo · sin internet", 1, body4, "left:300px;top:90px;width:1320px;height:760px")}
  {bubble("s4-bub", "Yo hago el trabajo pesado.", "left:300px;top:902px")}
</div></div>''')

# 05 — Transcripción
waves = "".join(f'<i style="height:{h}%"></i>' for h in [30, 62, 45, 82, 55, 35, 72, 22, 50, 78, 40, 66, 30, 58, 46, 26, 62, 36, 70, 44, 28, 60, 48, 34, 74, 52, 30, 64])
body5 = f'''<div class="split5">
  <div class="tx"><div class="tx-scroll" id="s5-scroll">
    <div class="band ivr" id="s5-ivr">Mensaje grabado (IVR) · 00:00–00:42</div>
    <div class="bub a" id="s5-b1">Buenos días, Angiografía de Occidente, le habla Laura. ¿En qué le puedo colaborar?</div>
    <div class="bub c" id="s5-b2">Quiero una cita para una ecografía.</div>
    <div class="bub a" id="s5-b3">Con gusto. ¿Me regala el documento del paciente?</div>
    <div class="bub c" id="s5-b4">Sí, claro, ya se lo doy.</div>
    <div class="bub a" id="s5-b5">Permítame un momento.</div>
    <div class="band hold" id="s5-hold">Espera · <b id="s5-holdn">81</b> s</div>
  </div></div>
  <div class="aud">
    <p class="h2">Audio</p>
    <div class="wave" id="s5-wave">{waves}<span class="head" id="s5-head"></span></div>
    <p class="atime" id="s5-time"><span id="s5-t1">▶ 00:48 / 06:10</span><span id="s5-t2">▶ 02:31 / 06:10</span></p>
    <p class="evl">Evidencia</p>
    <span class="ev" id="s5-ev">«permítame un momento» · 02:31</span>
  </div>
</div>'''
S.append(f'''<div class="scene" id="s5"><div class="inner">
  {win("s5-win", "Llamada 0453", "Asesor 12 · 6 min 10 s · Nueva cita", 0, body5, "left:240px;top:80px;width:1440px;height:790px")}
  <div class="ripple" id="s5-r1"></div>
  {cursor("s5-cur")}
  {bubble("s5-bub", "Cada hallazgo se puede escuchar.", "left:300px;top:902px")}
</div></div>''')

# 06 — Criterios
cards = [("ok", "✓", "P1", "Saludo e identificación", "Dijo entidad y nombre"),
         ("ok", "✓", "V1", "Documento del paciente", "Lo pidió a las 00:58"),
         ("bad", "✗", "G1", "Espera en línea", "81 s · supera 60 s"),
         ("warn", "?", "Z2", "¿Algo más?", "Revisar · escuchar 05:52")]
cards_html = "".join(f'''<div class="card" id="s6-c{i+1}"><span class="dot {k}" id="s6-d{i+1}"><b>{g}</b></span><div><span class="code">{c}</span><b>{esc(t)}</b><small>{esc(s)}</small></div></div>''' for i, (k, g, c, t, s) in enumerate(cards))
body6 = f'''<div class="split6"><div class="cards">{cards_html}</div>
<div class="score"><p class="rng" id="s6-rng"><span>70–90 %</span><i id="s6-strike"></i></p>
<div class="kbig sc" id="s6-sc"><span id="s6-num">70</span> %</div>
<span class="pill okp" id="s6-ok">Aprobado</span>
<p class="e1" id="s6-e1">Error crítico: solo si usted lo confirma</p></div></div>'''
S.append(f'''<div class="scene" id="s6"><div class="inner">
  {win("s6-win", "Llamada 0453 · Criterios", "Guía de auditoría · 10 criterios", 0, body6, "left:240px;top:80px;width:1440px;height:790px")}
  {bubble("s6-bub", "Califico con la guía de auditoría.", "left:300px;top:902px")}
</div></div>''')

# 07 — Revisión y descartes
rows7 = [("0453", "Asesor 12", "6:10", "85 %", '<span class="pill okp">Revisada</span>', ""),
         ("0457", "Asesor 07", "14:32", "60–80 %", '<span class="pill auto">Para revisar</span>', ""),
         ("0912", "Asesor 03", "0:14", "—", '<span class="pill cut">Cortada</span> <span class="pill auto">marcada automáticamente</span>', ' class="hi" id="s7-hi"'),
         ("0918", "Asesor 12", "3:48", "90 %", '<span class="pill okp">Aprobada</span>', "")]
rows_html = "".join(f'<tr{a}><td>{l}</td><td>{s}</td><td>{d}</td><td>{n}</td><td>{p}</td></tr>' for l, s, d, n, p, a in rows7)
body7 = f'''<table class="t" id="s7-tab" data-layout-allow-overlap><tr><th>Llamada</th><th>Asesor</th><th>Duración</th><th>Nota</th><th>Estado</th></tr>{rows_html}</table>'''
S.append(f'''<div class="scene" id="s7"><div class="inner">
  {win("s7-win", "Auditoría de Llamadas", "248 llamadas analizadas", 2, body7, "left:300px;top:90px;width:1320px;height:760px")}
  <div class="scrim" id="s7-scrim" data-layout-allow-overlap></div>
  <div class="modal" id="s7-modal" data-layout-allow-overlap>
    <div class="card big"><span class="dot warn" id="s7-dot"><b id="s7-q">?</b><b id="s7-k">✓</b></span><div><span class="code">Z2</span><b>¿Algo más en que le pueda colaborar?</b><small>Escuchar 05:52 · el asesor lo preguntó</small></div></div>
    <div class="row-sb" style="margin-top:26px"><span class="btn ok" id="s7-cumple">✓ Cumple</span><span class="btn">✗ No cumple</span><span class="btn pri" id="s7-save">Guardar revisión · Ctrl+S</span></div>
  </div>
  <div class="toast" id="s7-toast"><span class="okc">✓</span> Revisión guardada</div>
  <div class="ripple" id="s7-r1"></div><div class="ripple" id="s7-r2"></div>
  {cursor("s7-cur")}
  {bubble("s7-bub", "Usted decide solo las excepciones.", "left:300px;top:902px")}
</div></div>''')

# 08 — Chat: la más larga
q1 = "¿Cuál fue la llamada más larga y por qué se demoró?"
S.append(f'''<div class="scene" id="s8"><div class="inner">
  <div class="dimwin" id="s8-dim">{win("s8-win", "Auditoría de Llamadas", "248 llamadas analizadas", 2, '<div class="ph"></div><div class="ph"></div><div class="ph"></div><div class="ph"></div>', "left:0;top:0;width:100%;height:100%")}</div>
  <div class="chat" id="s8-chat">
    <div class="hd"><span class="avslot"></span><span>Asistente <small>pregunte por sus llamadas</small></span></div>
    <div class="bd">
      <div class="q" id="s8-q">{chars(q1)}<span class="caret"></span></div>
      <div class="think" id="s8-think"><span class="sp"></span><span class="shim">Buscando en 248 llamadas…</span></div>
      <div class="ans" id="s8-ans">
        <span class="big" id="s8-a1">Llamada 0457 · 14 min 32 s</span>
        <span class="al" id="s8-a2">Se demoró por:</span>
        <span class="li" id="s8-l1"><i></i>IVR de 4 min 25 s antes de que contestara el asesor</span>
        <span class="li" id="s8-l2"><i></i>Espera de 81 s sin anunciar</span>
        <span class="li" id="s8-l3"><i></i>3 transferencias entre áreas</span>
        <span class="chips" id="s8-ch"><span class="ev">Escuchar 05:33</span><span class="ev">Abrir llamada</span></span>
      </div>
    </div>
    <div class="inp" id="s8-inp"><span>Escriba una pregunta…</span><span class="send" id="s8-send">➤</span></div>
  </div>
  <div class="meta newtag" style="left:120px;top:960px">Nuevo · concepto</div>
  <div class="ripple" id="s8-r1"></div>
</div></div>''')

# 09 — Chat: la más corta
q2 = "¿Y la más corta?"
S.append(f'''<div class="scene" id="s9"><div class="inner">
  <div class="dimwin" id="s9-dim">{win("s9-win", "Auditoría de Llamadas", "248 llamadas analizadas", 2, '<div class="ph"></div><div class="ph"></div><div class="ph"></div><div class="ph"></div>', "left:0;top:0;width:100%;height:100%")}</div>
  <div class="chat" id="s9-chat">
    <div class="hd"><span class="avslot"></span><span>Asistente <small>pregunte por sus llamadas</small></span></div>
    <div class="bd">
      <div class="old" id="s9-old"><div class="q sm">{esc(q1)}</div><div class="ans sm"><b>Llamada 0457 · 14 min 32 s</b> · IVR, espera sin anunciar y 3 transferencias</div></div>
      <div class="q" id="s9-q">{chars(q2)}<span class="caret"></span></div>
      <div class="think" id="s9-think"><span class="sp"></span><span class="shim">Buscando…</span></div>
      <div class="ans" id="s9-ans">
        <span class="big" id="s9-a1">Llamada 0912 · 14 s</span>
        <span class="al" id="s9-a2">El cliente colgó antes del saludo.</span>
        <span class="al" id="s9-a3">Marcada como <b>cortada</b>: no cuenta en la nota.</span>
        <span class="chips" id="s9-ch"><span class="ev">Ver en la lista</span></span>
      </div>
    </div>
    <div class="inp"><span>Escriba una pregunta…</span><span class="send">➤</span></div>
  </div>
  <div class="meta newtag" style="left:120px;top:960px">Nuevo · concepto</div>
</div></div>''')

# 10 — Buscar y exportar
rows10 = [("0453", "Asesor 12", "85 %", "r-in"), ("0461", "Asesor 07", "70 %", "r-out"), ("0918", "Asesor 12", "90 %", "r-in"),
          ("0920", "Asesor 03", "75 %", "r-out"), ("0931", "Asesor 12", "80 %", "r-in")]
rows10_html = "".join(f'<tr class="r10 {k}"><td>{a}</td><td>{b}</td><td>{c}</td></tr>' for a, b, c, k in rows10)
body10 = f'''<div class="search" id="s10-search"><span class="mag"></span><span>{chars("Asesor 12 · Hoy")}</span><span class="caret"></span></div>
<table class="t" id="s10-tab"><tr><th>Llamada</th><th>Asesor</th><th>Nota</th></tr>{rows10_html}</table>
<div style="margin-top:26px"><span class="btn pri" id="s10-btn">⬇ Exportar a Excel</span></div>'''
xl_rows = [("0453", "1", "1", "0", "1", "85%"), ("0918", "1", "1", "1", "1", "90%"), ("0931", "1", "0", "1", "1", "80%")]
xl_html = "".join(f'<tr class="xr" id="s10-x{i+1}"><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td><td>{e}</td><td>{f}</td></tr>' for i, (a, b, c, d, e, f) in enumerate(xl_rows))
S.append(f'''<div class="scene" id="s10"><div class="inner">
  {win("s10-win", "Resultados", "Buscar por llamada, asesor o fecha", 2, body10, "left:150px;top:70px;width:840px;height:820px")}
  <div class="xl" id="s10-xl"><div class="bar1">Matriz de auditoría · septiembre.xlsx</div>
    <table><tr><th>Llamada</th><th>P1</th><th>V1</th><th>G1</th><th>Z2</th><th>Nota</th></tr>{xl_html}</table>
    <div class="tabsx"><span class="on">Auditorías</span><span>Descartadas</span></div></div>
  <div class="ripple" id="s10-r1"></div>
  {cursor("s10-cur")}
  {bubble("s10-bub", "Su matriz de auditoría, en un clic.", "left:300px;top:902px")}
</div></div>''')

# 11 — Estilos
body11 = '''<div class="kpis"><div class="kpi"><small>Llamadas</small><b>248</b></div><div class="kpi"><small>Aprobadas</small><b>201</b></div><div class="kpi"><small>Para revisar</small><b>31</b></div></div>
<div class="ph"></div><div class="ph"></div><div class="ph short"></div>'''
themes = [("theme-corp", "s11-w1"), ("theme-glass", "s11-w2"), ("theme-aurora", "s11-w3"), ("theme-dark", "s11-w4")]
wins11 = "\n".join(win(i, "Auditoría de Llamadas", "Configuración · Diseño", 3, body11, "left:420px;top:150px;width:1080px;height:640px", c) for c, i in themes)
S.append(f'''<div class="scene" id="s11"><div class="inner">
  <div class="meta" style="left:150px;top:96px">6 estilos · claro / oscuro</div>
  {wins11}
  <div class="theme-lbl"><span id="s11-l1" class="on">Corporativo</span><span id="s11-l2">Liquid Glass</span><span id="s11-l3">Aurora</span><span id="s11-l4">Oscuro</span></div>
  {bubble("s11-bub", "A su estilo.", "left:300px;top:902px")}
</div></div>''')

# 12 — Correo
S.append(f'''<div class="scene" id="s12"><div class="inner">
  {win("s12-win", "Configuración", "Notificaciones", 3, '<div class="row-sb set"><div><b>Notificar por correo</b><small>Avisar cada mañana que la app está activa</small></div><span class="toggle" id="s12-tg"><i id="s12-knob"></i></span></div><div class="row-sb set dim"><div><b>Destinatario</b><small>coordinacion@ejemplo.com</small></div></div>', "left:150px;top:200px;width:760px;height:430px")}
  <div class="env" id="s12-env"><i></i></div>
  <div class="mail" id="s12-mail"><div class="mh">Bandeja de entrada · coordinación</div><div class="mb">
    <p class="from" id="s12-m1">De: Auditoría de Llamadas · 07:00</p>
    <p class="subj" id="s12-m2"><span class="okc">✓</span> La app de auditoría está activa</p>
    <p class="txt" id="s12-m3">0 errores · 120 llamadas en cola · IA local lista</p></div></div>
  <div class="ripple" id="s12-r1"></div>
  {cursor("s12-cur")}
  <div class="meta newtag" style="left:150px;top:690px">Nuevo · concepto</div>
  {bubble("s12-bub", "Le aviso que todo está activo.", "left:300px;top:902px")}
</div></div>''')

# 13 — Inconformidades
bars = [("No pregunta «¿algo más?» (Z2)", 38, 1.0, True), ("Espera ≥ 60 s sin anunciar (G1)", 24, 0.63, False),
        ("No pide documento del paciente (V1)", 17, 0.45, False), ("Saludo incompleto (P1)", 11, 0.29, False)]
bars_html = "".join(f'''<div class="hbar"><span>{esc(t)}</span><div class="track"><i id="s13-b{i+1}" class="{"top" if top else ""}" style="width:{int(w*100)}%"></i></div><b id="s13-n{i+1}">{n}</b></div>''' for i, (t, n, w, top) in enumerate(bars))
S.append(f'''<div class="scene" id="s13"><div class="inner">
  <div class="meta newtag" style="left:150px;top:96px">Nuevo · concepto</div>
  <div class="kbig" id="s13-t">Inconformidades del período</div>
  <div class="bars" id="s13-bars">{bars_html}</div>
  <div class="tot" id="s13-tot"><div class="kbig acc" id="s13-90">0</div><div class="tl">inconformidades en 248 llamadas</div>
    <div class="rank" id="s13-rank"><b>Por asesor</b><span>Asesor A · 9</span><span>Asesor B · 7</span><span>Asesor C · 6</span></div></div>
  {bubble("s13-bub", "Esto es lo que más falla.", "left:300px;top:902px")}
</div></div>''')

# 14 — Cierre
S.append('''<div class="scene" id="s14"><div class="inner">
  <div class="ghost" style="left:-60px;bottom:-90px">importa</div>
  <div class="kbig" id="s14-l1">Usted revisa</div>
  <div class="kbig" id="s14-l2">lo que <span class="acc" id="s14-imp">importa.</span></div>
  <div class="lock" id="s14-lock"><span class="lg"></span><b>Auditoría de Llamadas con IA</b><span class="mono">· Angiografía de Occidente</span></div>
</div></div>''')

SCENES = "\n".join(S)

# ------------------------------------------------------------------ efectos de sonido (biblioteca incluida, Pixabay)
DUR = {"whoosh-short": .57, "impact-bass-1": 2.12, "pop": .72, "click-soft": .37, "typing": 1.5,
       "chime": 2.5, "notification": 2.46, "ping": 1.32, "sparkle": 1.8}
tq = 46.9 + len(q1) / 21          # fin de la pregunta 1 (igual que typeIn en la línea de tiempo)
tq2 = 56.5 + len(q2) / 14
cues = [(t, "whoosh-short", .3, None) for t in (5.75, 10.75, 17.75, 24.75, 32.75, 39.75, 45.8, 61.75, 71.75, 77.75, 85.75)]
cues += [(1.95, "pop", .25, None), (3.7, "impact-bass-1", .32, None)]
cues += [(t, "pop", .28, None) for t in (6.15, 7.45, 13.0, 13.25, 34.0, 34.9, 41.45, 65.15, 81.0)]
cues += [(t, "click-soft", .4, None) for t in (14.4, 15.7, 30.9, 41.4, 42.4, round(tq + .2, 2), 65.0, 73.5)]
cues += [(7.9, "typing", .22, 1.3), (46.9, "typing", .22, 1.5), (48.4, "typing", .22, round(tq - 48.4, 2)),
         (56.5, "typing", .22, round(tq2 - 56.5, 2)), (62.5, "typing", .22, .94)]
cues += [(23.6, "chime", .3, None), (37.5, "chime", .3, None), (42.7, "notification", .28, None), (75.0, "notification", .32, None)]
cues += [(round(tq + 1.85, 2), "ping", .25, None), (round(tq2 + 1.1, 2), "ping", .25, None), (87.15, "sparkle", .3, None)]
cues.sort()
AUDIO = "\n".join(
    f'  <audio id="sfx-{i:02d}" src="assets/sfx/{n}.mp3" data-start="{t}" data-duration="{d if d else DUR[n]}" '
    f'data-track-index="{10 + i % 4}" data-volume="{v}"></audio>'
    for i, (t, n, v, d) in enumerate(cues))

# ------------------------------------------------------------------ write
tpl = (ROOT / "tools" / "index.template").read_text(encoding="utf-8")
BGM = ('<audio id="bgm" src="assets/bgm/track-90s.mp3" data-start="0" data-duration="90" '
       'data-track-index="20" data-volume="0.55"></audio>')  # MusicGen local, extendida a 90 s
out = (tpl.replace("<!--SCENES-->", SCENES).replace("<!--AURI-->", AURI)
       .replace("<!--AUDIO-->", AUDIO).replace("<!--BGM-->", BGM))
(ROOT / "index.html").write_text(out, encoding="utf-8")
print("index.html escrito:", len(out), "bytes")
