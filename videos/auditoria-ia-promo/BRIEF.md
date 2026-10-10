---
workflow: general-video
flow: automation
storyboard: yes
message: "La auditoría de llamadas que antes tomaba horas, ahora la hace la IA en este computador: usted solo revisa lo que importa."
destination: presentation
aspect: 1920x1080
language: es
audience: "Dirección y coordinación del call center (Angiografía de Occidente)"
length: 90s
angle: product-demo
---

## Intent

Video comercial tipo motion design de la app web local de **automatización de lectura y auditoría de llamadas**.
Debe verse profesional, "como si lo hubiera hecho un profesional", con animaciones llamativas y dinámicas
que muestren el proceso de punta a punta (pedido del usuario: estilo **dinámico y llamativo**).

Mostrar todas las funcionalidades que la app tiene hoy, y además dos funciones nuevas en concepto:

- un **chatbot** al que se le preguntan datos de las llamadas. En el video el usuario pregunta
  «¿cuál es la llamada más larga y por qué se demoró?» y luego «¿cuál es la llamada más corta?»;
- la opción de **enviar un correo** que notifica que la app está activa.

Cierra con un **panel de inconformidades** (no conformidades detectadas por el sistema).

## Assets

- src/llamadas/gui/static/ (index.html, style.css, app.js) — interfaz real de la app; referencia de layout, textos y tokens del estilo «Corporativo».
- LEEME.md y CONTEXT.md §16 — lista de funciones reales a mostrar.

## Customizations

- Música de fondo instrumental + textos en pantalla, sin voz en off. Primera elección: catálogo de HeyGen; no funcionó en este equipo (el CLI de HeyGen no existe para Windows y la descarga por credencial falló con «fetch failed»). **Fuente final elegida por el usuario: MusicGen local** (facebook/musicgen-small): base de 30 s generada en este equipo y extendida a 90 s con fundidos cruzados de 2 s, normalizada a −16 LUFS (`assets/bgm/track-90s.mp3`, volumen 0,55). Tono: corporativo tecnológico, enérgico, sin voz, ~112 bpm.
- **Efectos de sonido sutiles** (elegido por el usuario): biblioteca incluida de HyperFrames (Pixabay, sin atribución obligatoria) — whoosh en transiciones, clics del cursor, pops de aparición, tecleo en el chat, chime de éxito, notificación del correo, sparkle en el cierre; volumen 0,22–0,4.
- Chatbot y correo de notificación se muestran como funciones de la app (son nuevas: aún no están construidas en la app real).
- **Mascota (pedido del usuario tras aprobar los bocetos):** «Auri», mascota del chatbot que además guía la animación. Cuerpo redondo azul #001F78, cara-pantalla blanca con dos ojos, diadema de call center amarilla #E6B32A, antena con punto amarillo y boca de onda de audio que se anima al «hablar». Aparece en la presentación, señala cada paso en las escenas de la app, es el avatar del asistente en el chat y se despide en el cierre. Dibujada en SVG dentro del proyecto.

## Notes

- Funciones reales a mostrar: carga por arrastre de audios (.gsm/.mp3/.wav); análisis local sin internet (modos Rápido / Preciso / Solo reglas) con progreso y tiempo estimado; transcripción tipo chat con audio sincronizado y marcas de mensajes grabados/esperas; criterios con semáforos (✓ cumple, ✗ no cumple, ? revisar) y evidencia clicable que salta al audio; nota como rango y ≥80 % aprobado; error crítico E1 solo si el humano lo confirma; revisión humana Cumple/No cumple (Ctrl+S); descarte automático de llamadas cortadas (<20 s) o incompletas; búsqueda por ID, asesor y fecha; exportación a Excel con el formato de la matriz; estilos visuales (Liquid Glass, Aurora, Corporativo…) claro/oscuro; privacidad: todo local, botón eliminar llamada.
- Colores corporativos: azul #001F78, amarillo #E6B32A, gris #585C5E.
- Datos de ejemplo en pantalla: ficticios o anonimizados; nunca nombres reales de pacientes ni números de teléfono reales.
