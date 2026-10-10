---
format: 1920x1080
duration: 90s
message: "La auditoría de llamadas que antes tomaba horas, ahora la hace la IA en este computador: usted solo revisa lo que importa."
arc: Gancho (el dolor en cifras) → Presentación → Demostración del flujo (cargar → analizar → leer → calificar → revisar) → Chatbot → Funciones de salida (Excel, estilos, correo) → Panel de inconformidades → Cierre
audience: Dirección y coordinación del call center (Angiografía de Occidente)
mode: collaborative
version: v1
---

## Decisiones

- **Mensaje:** la auditoría que antes tomaba horas la hace la IA en este computador; la persona solo revisa lo que importa.
- **Formato:** 16:9, 1920×1080, 90 s, sin voz en off, música instrumental de fondo, todo el texto en pantalla (español).
- **Hilo conductor (spine):** una sola ventana de la app que nunca desaparece. La cámara se acerca, recorre y se aleja de ella; las pestañas reales ("1 Cargar y analizar" → "2 Resultados y revisión" → "Configuración") marcan el avance. El chatbot se abre como panel lateral de la misma ventana.
- **Marca:** estilo «Corporativo» de la app. Azul #001F78 (primario), amarillo #E6B32A (acento), gris #585C5E. Fondo del video: azul noche tintado (#071338) para que la ventana clara de la app resalte. Tipografía de la app: Segoe UI Variable (texto/títulos) y Cascadia Mono (códigos de criterio).
- **Prohibido:** pantallas de ejemplo con nombres o teléfonos reales; degradados violeta/cian; texto que se lea en menos de 2 s; diapositivas estáticas (cada escena entra con movimiento y la ventana persiste); efectos que no expliquen el proceso.
- **Fallas a evitar:** el «slideshow» (cada escena una tarjeta nueva sin relación) y el «salvapantallas» (movimiento que no dice nada).
- **Pausa intencional:** la respuesta del chatbot a «¿por qué se demoró?» se sostiene quieta ~1,5 s para que se lea.
- **Veracidad:** las pantallas 03–07 y 10–11 reconstruyen la interfaz real (estilo Corporativo). El chatbot (08–09), el correo (12) y el panel de inconformidades (13) son funciones **nuevas en concepto**, dibujadas con el mismo diseño. Todos los datos de llamadas son **ficticios**.

## Locked

- Hoja de bocetos v1 confirmada por el usuario (composición, textos y colores de las 14 escenas).

## Changes from v1

- «La hoja está bien, puedes iniciar la animación, crea una mascota que va a ser la del chatbot y la que guía la animación.» → Se agrega **Auri**, mascota-guía: entra en 02 junto al sello; en 03–07 y 10–12 aparece en una esquina libre, apunta al foco y reacciona (asiente, celebra); en 08–09 es el avatar del «Asistente» y «habla» las respuestas; en 13 señala la barra mayor; en 14 saluda junto al mensaje final. No cambia la composición confirmada: ocupa espacio vacío de cada boceto.

## Frame 1 — Gancho: el volumen

- scene: Cifras grandes que cambian en el sitio: «1.500 llamadas al día» → «10 auditadas a mano» → «¿Y las otras 1.490?»
- duration: 6s
- poster: 4.5s
- transition_in: cut
- status: built
- voiceover: onscreen
- src: compositions/01-gancho.html
- blueprint: kinetic-type-beats
- why: Abre con el dolor en el lenguaje del espectador (volumen vs. capacidad). Cifras reales de la operación: 1.000–2.000 llamadas/día; en 2 h una persona audita ≈10.

## Frame 2 — Presentación

- scene: El signo de pregunta colapsa y de él se arma el sello «Auditoría de Llamadas con IA» + «100 % en este computador · sin internet»
- duration: 5s
- poster: 3.5s
- transition_in: morph
- status: built
- voiceover: onscreen
- src: compositions/02-presentacion.html
- blueprint: logo-assemble-lockup
- why: Entrega el valor en el segundo beat (reverse iceberg): la respuesta al dolor y la promesa de privacidad.

## Frame 3 — Cargar

- scene: La ventana de la app vuela al centro (pestaña «1 Cargar y analizar»). El cursor arrastra 3 archivos (.gsm, .mp3, .wav) a la zona de carga; elige el modo «Rápido» (Preciso / Solo reglas visibles) y pulsa «Analizar llamadas».
- duration: 7s
- poster: 5s
- transition_in: zoom-through
- status: built
- voiceover: onscreen
- src: compositions/03-cargar.html
- blueprint: cursor-ui-demo
- why: Primer contacto con el producto: cargar es arrastrar y soltar, sin pasos técnicos.

## Frame 4 — La IA trabaja

- scene: Barra de progreso Corporativa (azul→amarillo) con tiempo estimado; lista de etapas que se marcan: «Audio convertido» ✓ «Transcripción» ✓ «Hablantes separados» ✓ «Mensajes grabados y música de espera detectados» ✓ «Criterios evaluados» ✓
- duration: 7s
- poster: 5.5s
- transition_in: push-left
- status: built
- voiceover: onscreen
- src: compositions/04-procesando.html
- blueprint: agent-progress-theater
- why: Muestra que el trabajo pesado lo hace la máquina, en local.

## Frame 5 — Leer la llamada

- scene: Detalle de una llamada: transcripción tipo chat (Asesor / Cliente) que se desplaza; aparece una franja «Mensaje grabado (IVR)» y otra «Espera de 81 s». El cursor hace clic en una evidencia y el reproductor de audio salta a ese segundo (onda + cabezal).
- duration: 8s
- poster: 6s
- transition_in: push-left
- status: built
- voiceover: onscreen
- src: compositions/05-transcripcion.html
- blueprint: transcript-scroll-artifact-reveal
- why: La evidencia: cada hallazgo se puede escuchar; no es una caja negra.

## Frame 6 — Calificar

- scene: Las tarjetas de criterios se arman en cascada con semáforos (P1 ✓, V1 ✓, G1 ✗ «espera ≥ 60 s», Z2 ? «revisar»). La nota se muestra como rango «70–90 %» y luego cuenta hasta «85 % · Aprobado». Chip: «Error crítico: solo si usted lo confirma».
- duration: 7s
- poster: 5.5s
- transition_in: push-left
- status: built
- voiceover: onscreen
- src: compositions/06-criterios.html
- blueprint: grid-card-assemble
- why: El resultado: la matriz de la guía, calificada con evidencia y con el criterio humano al mando.

## Frame 7 — Revisión humana y descartes

- scene: El cursor decide «Cumple» en el criterio pendiente y pulsa «Guardar revisión» (Ctrl+S); aviso «Revisión guardada». Corte a la lista: una fila «0912 · 14 s» marcada «Cortada · marcada automáticamente».
- duration: 6s
- poster: 4s
- transition_in: push-left
- status: built
- voiceover: onscreen
- src: compositions/07-revision.html
- blueprint: cursor-ui-demo
- why: El humano solo decide las excepciones; las llamadas cortadas (< 20 s) se apartan solas.

## Frame 8 — Pregúntele a sus llamadas

- scene: Se abre el panel «Asistente» en la ventana. Se escribe: «¿Cuál fue la llamada más larga y por qué se demoró?». Estados «Buscando en 248 llamadas…». Respuesta: «Llamada 0457 · 14 min 32 s. Se demoró por: IVR de 4 min 25 s antes de contestar · espera en hold de 81 s sin anunciar · 3 transferencias.» con chips de evidencia que abren la llamada.
- duration: 10s
- poster: 8.5s
- transition_in: slide-in-right
- status: built
- voiceover: onscreen
- src: compositions/08-chat-larga.html
- blueprint: prompt-type-submit-generate
- why: Función nueva clave: consultar los datos en lenguaje natural y obtener el porqué, con evidencia.

## Frame 9 — La más corta

- scene: En el mismo hilo se escribe «¿Y la más corta?». Respuesta: «Llamada 0912 · 14 s. El cliente colgó antes del saludo. Marcada como cortada; no cuenta en la nota.»
- duration: 6s
- poster: 5s
- transition_in: cut
- status: built
- voiceover: onscreen
- src: compositions/09-chat-corta.html
- blueprint: prompt-type-submit-generate
- why: Cierra el ida y vuelta conversacional y conecta con el descarte automático (callback al frame 7).

## Frame 10 — Encontrar y exportar

- scene: Barra de búsqueda filtra «Asesor 12 · Hoy» (código ficticio). Clic en «Exportar a Excel»: la tabla vuela y se convierte en una hoja con el formato de la matriz (columnas de criterios, hoja «Descartadas»).
- duration: 6s
- poster: 4.5s
- transition_in: push-left
- status: built
- voiceover: onscreen
- src: compositions/10-exportar.html
- blueprint: cursor-ui-demo
- why: La salida que la coordinación ya usa: la matriz de auditoría lista en un clic.

## Frame 11 — A su estilo

- scene: La ventana queda fija en el centro y se re-viste en el sitio: Corporativo → Liquid Glass → Aurora → modo oscuro, cada uno en ~0,8 s.
- duration: 4s
- poster: 3s
- transition_in: cut
- status: built
- voiceover: onscreen
- src: compositions/11-estilos.html
- blueprint: fixed-anchor-cycle
- why: Beat de energía: la herramienta se adapta al equipo (seis estilos, claro/oscuro).

## Frame 12 — Siempre activa, siempre avisada

- scene: Interruptor «Notificar por correo» se enciende en Configuración. Un sobre sale volando y aterriza como correo: «✅ Auditoría de Llamadas está activa · 07:00 · 0 errores · 120 llamadas en cola».
- duration: 6s
- poster: 4.5s
- transition_in: push-left
- status: built
- voiceover: onscreen
- src: compositions/12-correo.html
- blueprint: cta-morph-press
- why: Función nueva: la coordinación sabe que el sistema está trabajando sin abrirlo.

## Frame 13 — Panel de inconformidades

- scene: Panel que se arma: título «Inconformidades del período». Barras que crecen: «No pregunta “¿algo más?” (Z2) 38» · «Espera ≥ 60 s sin anunciar (G1) 24» · «No pide documento del paciente (V1) 17» · «Saludo incompleto (P1) 11». Contador total «90 inconformidades en 248 llamadas» y mini-ranking por asesor con nombres ficticios («Asesor A», «Asesor B», «Asesor C»).
- duration: 8s
- poster: 6.5s
- transition_in: zoom-out
- status: built
- voiceover: onscreen
- src: compositions/13-inconformidades.html
- blueprint: dataviz-countup
- why: Cierre de valor: de llamadas sueltas a decisiones de mejora para el equipo.

## Frame 14 — Cierre

- scene: El panel se aleja y se condensa en el sello: «Usted revisa lo que importa.» + «Auditoría de Llamadas con IA · Angiografía de Occidente».
- duration: 4s
- poster: 3s
- transition_in: zoom-out
- status: built
- voiceover: onscreen
- src: compositions/14-cierre.html
- blueprint: logo-assemble-lockup
- why: Repite el mensaje como firma y deja la marca sostenida hasta el último cuadro.
