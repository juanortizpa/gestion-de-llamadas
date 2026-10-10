# CONTEXT.md — Sistema gratuito de auditoría automática de llamadas

> **Archivo vivo.** Es la memoria técnica del proyecto. Se actualiza cada vez que se toma una decisión importante de arquitectura (ver §17 "Registro de decisiones"). Si el código y este archivo se contradicen, hay que resolverlo y corregir el que esté mal.
>
> Creado: 2026-10-05 · Estado: **FASE DE DISEÑO — no hay código todavía.**
> Idioma de trabajo con el usuario: **español, siempre.**

---

## 1. Objetivo

Recibir llamadas telefónicas grabadas en `.gsm` (conversación de **dos personas**: asesor y cliente), procesarlas automáticamente y producir una **auditoría de calidad reproducible y con evidencia**: nota sobre 10 puntos + explicación por criterio + condición de error crítico (E1).

Principios de diseño (innegociables):

1. **$0/mes.** Todo el sistema principal corre con software libre, local, sin servicios de pago.
2. **Nada crítico depende de APIs gratuitas externas.** Pueden existir como *fallback opcional*, nunca como camino principal.
3. **Lo que se puede calcular, no se le pregunta a un LLM.** (timestamps, conteos, regex, umbrales).
4. **Cada puntaje tiene evidencia verificable** (cita textual + turno + tiempo).
5. **Reproducible y auditable:** misma entrada + mismas versiones ⇒ mismo resultado; se registran versiones de modelos, prompts y reglas.
6. **Privacidad primero:** datos de pacientes → procesamiento local por defecto.
7. **Estabilidad > velocidad.** Una llamada a la vez, cola persistente, reintentos.

## 2. Volumen y restricciones operativas

| Dato | Valor |
|---|---|
| Llamadas/día | ~80 |
| Duración | 5–8 min (promedio asumido 6,5 min) |
| Audio/día | 400–640 min (≈ 6,7–10,7 h; típico 8,7 h) |
| Hablantes | 2 (asesor / cliente) |
| Concurrencia | **No necesaria.** Cola secuencial |
| Costo mensual objetivo | **$0** |
| Prohibido | Ollama |
| GPU | No hay NVIDIA. Prohibido diseñar para CUDA |

### 2.1 Datos reales observados en las muestras (2026-10-05)

Carpetas en el proyecto: `llamadas auditadas/` (6 `.mp3` + plantilla Excel) y `llamadas no auditadas/` (11 `.gsm`). **Estos archivos contienen teléfonos de clientes y audio de pacientes: PII. No subirlos a ningún servicio ni a control de versiones.**

**Formato GSM verificado:** son GSM 06.10 *crudo* (frames de 33 bytes; todos los tamaños múltiplos de 33; primer nibble 0xD en cada frame) → 1650 B/s ≈ 13,2 kbps. Duración exacta = bytes / 1650.

**Duraciones reales (no coinciden con el supuesto inicial de 5–8 min):**
- 11 `.gsm` = **8 llamadas únicas + 3 duplicados exactos** (sufijo ` (1)`, mismo SHA-256) → el dedupe por hash es requisito real, no teórico.
- Únicas (min): 2,27 · 2,37 · 1,94 · 9,08 · 0,52 · 1,38 · 2,30 · 6,67 → total 26,5 min, **mediana ≈ 2,3 min**.
- Auditadas (duración **real** de los mp3, medida con ffprobe): 7,8 · 5,7 · 5,0 · 5,0 · 4,1 · 3,0 min (media 5,1). La columna *Duración* de la plantilla Excel **no coincide** (dice 3,0–4,1 min): está mal diligenciada o mide otra cosa.
- El usuario confirma (2026-10-05) que el promedio real es el declarado al inicio (5–8 min). Las 14 muestras dan media ≈ 4,1 min; **se planifica con 5–6,5 min** (conservador). 80 llamadas/día ≈ 6,7–8,7 h de audio.
- Los `.mp3` auditados son los mismos audios convertidos solo para poder escucharlos (confirmado por el usuario) y son **8 kHz mono**, igual que el GSM.

**Formato de nombre de archivo (Asterisk, cola):** `q-<cola>-<teléfono_cliente>-<AAAAMMDD>-<HHMMSS>-<epoch>.<uniqueid>.gsm`
- Prefijo `q-` = llamada de cola (entrante a una cola de agentes). Todas las muestras son `q-`. Dos colas distintas: `800197` y `8001971` (significado por confirmar, P-04/P-18; podrían ser las dos entidades/líneas).
- Teléfono del cliente → **PII**: enmascarar en resultados (`315***2931`).
- El nombre del agente **no** viene en el archivo; solo está en la plantilla manual. Sin ID de agente en metadatos.
- Las llamadas `.mp3` auditadas **no existen como `.gsm`**: no es posible saber si el mp3 tiene la misma calidad que el GSM original (P-19). El pipeline debe aceptar ambos formatos.

## 3. Hardware (primera versión)

- CPU Intel Core i5-8250U (4 núcleos / 8 hilos, 15 W TDP, AVX2, **sin AVX-512**)
- RAM 16 GB DDR4-2133 (ancho de banda de memoria limitado → cuello de botella de LLM local)
- GPU Intel UHD 620 (inútil para este proyecto; no contar con ella)
- SSD M.2 500 GB

✅ **Decidido (2026-10-05, D-10): solo Windows 11 Pro, nativo, sin Docker ni WSL.** Consecuencias: venv de Python; `ffmpeg` y `llama.cpp` (`llama-server`, binarios Windows CPU/AVX2) como ejecutables; el worker corre como tarea del Programador de tareas o servicio (NSSM); desactivar suspensión, plan de energía "Alto rendimiento", horas activas de Windows Update para evitar reinicios en medio del lote; BitLocker (disponible en Pro) obligatorio; rutas con espacios (`GESTION DE LLAMADAS`) → usar `pathlib` y comillas siempre.
⚠️ Es un portátil de 15 W: bajo carga sostenida habrá **throttling térmico** y el rendimiento real puede ser menor al de un benchmark corto.

## 4. Veredicto de la arquitectura propuesta originalmente

| Componente propuesto | Veredicto | Motivo |
|---|---|---|
| Linux | ✅ Mantener (o WSL2 si se queda en Windows) | Mejor rendimiento y menos fricción |
| **Docker** | ⚠️ **Posponer** | Para el MVP añade complejidad y, en Windows, overhead. Usar venv. Dockerizar cuando el pipeline sea estable |
| **n8n** | ❌ **Descartar del MVP (probablemente del todo)** | Una cola SQLite + worker Python hace lo mismo con menos RAM y más control. n8n usa licencia "fair-code" (no OSI). Solo reconsiderar para notificaciones/integraciones |
| Python | ✅ | Ecosistema de audio/ML |
| FFmpeg | ✅ | Estándar para decodificar GSM |
| faster-whisper | ✅ (con matices) | Mejor relación calidad/CPU. Elegir tamaño de modelo por benchmark |
| **pyannote** | ⚠️ **Candidato, no decisión** | Pesado en CPU, modelos "gated" en HuggingFace (requiere token una vez), entrenado con audio de mayor calidad que 8 kHz. Comparar con sherpa-onnx y, sobre todo, con **separación por canal** |
| Silero VAD | ✅ pero ya viene dentro de faster-whisper (`vad_filter`) | No hace falta etapa separada salvo para métricas de silencios |
| PostgreSQL | ❌ para MVP | SQLite (WAL) sobra para ~30k llamadas/año. Postgres solo si el dashboard multiusuario lo exige |
| LLM para todo | ❌ **Cambiar** | LLM solo para lo semántico y con salida restringida; lo demás, reglas |
| Dashboard | ⏳ Después | No construir hasta validar la calidad de la auditoría |

### La mejora arquitectónica más importante (verificar YA)

`.gsm` es el formato típico de **Asterisk**. Asterisk puede grabar **cada pierna por separado** (`Monitor` genera `-in` y `-out`; `MixMonitor` con opciones de canal separado). Si se consigue audio **estéreo/por canal (asesor vs cliente)**:

- **se elimina la diarización** (el error más probable y más costoso del pipeline),
- las métricas de interrupción, silencios y hold se vuelven casi exactas,
- la identificación asesor/cliente es trivial.

Si el audio es **mono mezclado**, la diarización es obligatoria y es el mayor riesgo técnico.

✅ **Confirmado por el usuario (D-11): los `.gsm` se entregan en MONO mezclado y no se pueden regenerar por canal.** La diarización es obligatoria; se diseña el pipeline para ese caso. Consecuencias: C1 (interrupciones) y G2 (latencias) basadas en solapes serán **ruidosas**; la asignación de roles debe apoyarse en contenido; toda confianza baja → `needs_review`. Se conserva la interfaz `diarization/` con opción `channels` por si algún día cambia la PBX.

## 5. Arquitectura técnica recomendada

```
 carpeta de entrada (.gsm)
        │  (watcher/polling + verificación de archivo estable + SHA-256 dedupe)
        ▼
 COLA PERSISTENTE (SQLite, tabla jobs con estados y reintentos)
        │
        ▼  worker secuencial, por ETAPAS (cada etapa carga su modelo, lo usa y lo libera)
 [1] Audio:     ffmpeg  .gsm → WAV 16 kHz mono PCM16 (si hay canales separados: 2 WAV)
 [2] Segmentos: VAD (Silero, integrado en faster-whisper)
 [3] Hablantes: (A) canales separados   |  (B) diarización 2 hablantes (sherpa-onnx / pyannote)
 [4] STT:       faster-whisper int8, español, word_timestamps, hotwords/initial_prompt con entidad
 [5] Alineación palabra↔hablante → turnos → asignación de roles (asesor/cliente) con confianza
 [6] Métricas por timestamps (hold, silencios, solapes, talk ratio, duración)
 [7] Motor de reglas → sub-checks determinísticos por criterio
 [8] LLM Auditor (llama.cpp, GGUF, salida JSON restringida) → solo sub-checks semánticos pendientes
 [9] Validador: JSON válido + cada cita existe literalmente en la transcripción
 [10] Agregador: puntaje, E1, estado (completed | needs_review | failed)
 [11] Persistencia: JSON en disco + SQLite; política de borrado de audio
```

**Modo de operación (D-14, decidido por el usuario): lote bajo demanda, NO servicio 24/7.** El portátil se enciende solo cuando hace falta y las llamadas se entregan manualmente (copiar archivos a `data/incoming/` o apuntar a una carpeta). Consecuencias:
- **No hay watcher ni servicio residente ni Programador de tareas.** Se lanza `llamadas process <carpeta>` a mano y termina al vaciar la cola.
- La cola SQLite sigue siendo útil, pero ahora para **reanudar**: si el equipo se apaga o se suspende a mitad del lote, al relanzar continúa donde quedó (cada etapa idempotente, por hash).
- No hay requisito de latencia en tiempo real → se puede escoger **más calidad a costa de tiempo** (modelo STT más grande, LLM mayor) si el tamaño del lote lo permite. Tamaño de lote y ventana de uso: P-10.
- Se debe poder **pausar/reanudar** con seguridad y mostrar progreso y ETA en consola.
- Vigilar que Windows no suspenda durante el lote (`powercfg`/`SetThreadExecutionState`); batería: ejecutar conectado a corriente.

Decisiones de ejecución:

- **Procesar por etapas, no por llamada completa, cuando haya lote acumulado** (ej. todas las STT, luego descargar Whisper, luego todos los LLM) para evitar recargar modelos 80 veces. Modo "por llamada" para flujo continuo. Decidir tras benchmark.
- **Una sola carga de LLM como servidor `llama-server`** (llama.cpp) con *prompt cache* del prefijo de rúbrica (idéntico en todas las llamadas).
- **Nunca ejecutar STT y LLM a la vez** (RAM y 4 núcleos físicos).
- Estados de job: `queued → converting → transcribing → diarizing → scoring → done | needs_review | failed`. Reintentos con backoff; las fallas no bloquean la cola.

## 6. Tecnologías: elegidas, candidatas y descartadas

> Las columnas son **evaluación cualitativa a priori, NO benchmarks medidos.** Toda cifra numérica de rendimiento es **ESTIMACIÓN** hasta correr §10.

### 6.1 Speech-to-text
| Opción | CPU/RAM | Velocidad | Precisión (ES, 8 kHz) | Costo | Privacidad | Facilidad | Estado |
|---|---|---|---|---|---|---|---|
| faster-whisper `small` int8 | Baja / ~1 GB | Alta | Media-baja (sufre con nombres y números) | $0 | Local | Alta | Candidato (piso) |
| faster-whisper `medium` int8 | Media / ~2–3 GB | Media | Media-alta | $0 | Local | Alta | **Candidato principal** |
| faster-whisper `large-v3` int8 | Alta / ~3–5 GB | Baja (puede ser > tiempo real en este CPU) | La mejor | $0 | Local | Alta | Solo si el benchmark lo permite |
| whisper.cpp | Similar | Similar | Igual que Whisper | $0 | Local | Media | Alternativa si faster-whisper falla |
| sherpa-onnx (Whisper/otros ONNX) | Baja-media | Media-alta | Por medir | $0 | Local | Media | A evaluar |
| Vosk/Kaldi | Muy baja | Muy alta | Baja | $0 | Local | Media | Descartado como principal (calidad) |
| distil-whisper | — | — | Variantes principales son solo inglés | $0 | Local | — | Descartado |
| Whisper vía API gratuita | Nula | Alta | Alta | Cuota variable | **Externa** | Alta | Solo fallback con datos anonimizados |

### 6.2 Diarización
| Opción | CPU/RAM | Velocidad | Precisión en telefonía 8 kHz | Privacidad | Facilidad | Estado |
|---|---|---|---|---|---|---|
| **Canales separados de la PBX** | Nula | Instantánea | Casi perfecta | Local | Depende de la PBX | **Preferida si es posible** |
| pyannote 3.1 (`num_speakers=2`) | Alta / 1–2 GB | Lenta en CPU | Buena en 2 hablantes, no garantizada en 8 kHz | Local (modelo gated, token una vez) | Media | Candidata |
| sherpa-onnx diarization | Media | Media-alta | Por medir | Local | Media | Candidata (más liviana) |
| VAD + embeddings (SpeechBrain ECAPA) + clustering k=2 | Media | Media | Por medir; requiere código propio | Local | Baja | Plan C |
| NeMo MSDD | Muy alta | Baja | Alta | Local | Baja | Descartado (pesado) |
| WhisperX (envoltorio) | Alta | Baja | — | Local | Media | Descartado (añade wav2vec2 y RAM) |

Ayuda adicional: la asignación de **rol** no necesita voz; se hace por contenido (quién dice la entidad/saludo guion) + quién habla primero (**depende de si la llamada es entrante o saliente**).

### 6.3 VAD
| Opción | Estado |
|---|---|
| Silero VAD (vía `vad_filter` de faster-whisper) | **Elegido** (sin etapa extra) |
| WebRTC VAD | Descartado (peor con ruido telefónico) |
| Segmentación de pyannote | Solo si se usa pyannote |
| Sin VAD | Descartado (alucinaciones de Whisper en silencios) |

### 6.4 LLM (solo criterios semánticos)
| Opción | RAM | Velocidad estimada en i5-8250U | Calidad en español | Privacidad | Estado |
|---|---|---|---|---|---|
| llama.cpp + GGUF 3–4B Q4 (clase Qwen/Gemma/Phi/Llama pequeños) | ~2.5–4 GB | ~6–10 tok/s gen (EST.) | Aceptable con preguntas sí/no cortas | Local | **Candidato principal** |
| llama.cpp + GGUF 7–8B Q4_K_M | ~5–6 GB | ~3–5 tok/s gen (EST.), prompt ~20–40 tok/s (EST.) | Mejor | Local | Candidato si el tiempo alcanza |
| Modelos 12B+ | >8 GB | Inviable en este equipo | — | Local | Descartado |
| Gemini / Groq / OpenRouter (cuota gratuita) | Nula | Alta | Alta | **Externa** (los planes gratuitos suelen permitir uso de datos para mejorar productos: verificar términos vigentes) | Solo fallback con texto anonimizado |
| Sin LLM (solo reglas) | Nula | Máxima | Cubre ~60–70 % de lo auditable | Local | **Modo degradado obligatorio** (el sistema debe funcionar así si el LLM falla) |
| Ollama | — | — | — | — | **Prohibido por el usuario** |

Los nombres exactos/versiones de modelos se fijan **después** del benchmark (el panorama cambia rápido; verificar disponibilidad y licencia al elegir).

### 6.5 Base de datos
| Opción | Estado |
|---|---|
| **SQLite (WAL)** | **Elegida** para cola + resultados |
| PostgreSQL | Pospuesta hasta tener dashboard multiusuario |
| Archivos JSON | Complemento (resultado completo por llamada), no sustituto |

### 6.6 Workflow / orquestación
| Opción | Estado |
|---|---|
| **Worker Python + cola SQLite + servicio del SO (systemd o Programador de tareas)** | **Elegida** |
| n8n | Descartada del MVP |
| Celery/Redis, Airflow, Prefect | Descartadas (sobredimensionadas) |

## 7. Capacidad: ¿aguanta el hardware 80 llamadas/día? (TODO ESTIMACIÓN)

Cálculos aritméticos (no benchmarks):

- Audio/día: 80 × 6,5 min = **520 min = 8,67 h** (rango 6,7–10,7 h).
- Tiempo disponible por llamada, procesando 80 en una ventana de:
  - 24 h → 1080 s/llamada (RTF total tolerable ≈ 2,8)
  - 12 h → 540 s/llamada (RTF total ≈ 1,4)
  - 8 h → 360 s/llamada (RTF total ≈ 0,92)
  (RTF = tiempo de proceso / duración del audio; llamada de 390 s).
- Estabilidad de la cola: si las llamadas llegan repartidas en 10 h, λ = 1 cada 7,5 min; si procesar una toma > 7,5 min la cola crece y se drena de noche. Si el tiempo de proceso medio es < tiempo entre llegadas, la latencia es ~ minutos; si llegan todas acumuladas, el último resultado sale tras (80 × tiempo por llamada).

Escenarios de tiempo total por llamada (**RTF y tok/s son SUPUESTOS a validar**):

| Configuración | STT | Diariz. | LLM | Total/llamada (EST.) | 80 llamadas (EST.) |
|---|---|---|---|---|---|
| small + canales separados + LLM 4B | ~2 min | 0 | ~3 min | ~5 min | ~6–7 h |
| medium + sherpa/pyannote + LLM 4B | ~4–5 min | ~1–2 min | ~3 min | ~9–10 min | ~12–13 h |
| large-v3 + pyannote + LLM 7B | ~9+ min | ~2 min | ~6–8 min | ~18–20 min | **~24–26 h → NO cabe** |
| medium + canales + solo reglas (sin LLM) | ~4–5 min | 0 | 0 | ~5 min | ~7 h |

**Recalculo con duración observada (≈3,5 min, a confirmar; ESTIMACIÓN):** 80 × 3,5 min = 280 min = **4,7 h de audio/día**. Con RTF total de ~1 (STT medium + diarización + LLM acotado) serían ~5 h por lote diario; con 3,5 min por llamada el presupuesto en una ventana de 8 h es 360 s/llamada frente a 210 s de audio (RTF total tolerable ≈ 1,7). Esto hace **más viable** `medium` e incluso explorar `large-v3` solo en llamadas cortas. Las tablas anteriores (6,5 min) quedan como caso pesimista. El almacenamiento real es menor (GSM = 1650 B/s: ~0,35 MB por llamada de 3,5 min → ~28 MB/día).

**Conclusión provisional:** secuencial 80/día es **viable en tiempo** con STT ≤ medium y LLM ≤ 4B (o LLM restringido), **no** viable con large-v3 + LLM 7B. El problema real de este hardware es la **calidad**, no el tiempo.

Recursos (estimaciones, picos por etapa — al ser secuencial no se suman):
- RAM: STT 1–5 GB; diarización 1–2 GB; LLM 3–6 GB. **Pico esperado < 8 GB** (cabe en 16 GB).
- CPU: usar los 4 núcleos físicos por etapa; `threads` ≈ 4–6. Vigilar throttling.
- Almacenamiento (cálculo): GSM 13 kbps = 1625 B/s → ~0,62 MB/llamada → **~50 MB/día → ~1,5 GB/mes → ~18 GB/año**. WAV 16 kHz PCM16 ≈ 12,5 MB/llamada ≈ 1 GB/día **temporal** (borrar tras procesar). Transcripción+JSON ≈ 50–150 KB/llamada → ≤ ~10 MB/día. 500 GB sobran.

## 8. Qué se resuelve con qué

Leyenda: **R** = regla determinística · **T** = timestamps/métricas · **L** = LLM · **ML** = machine learning propio · **H** = revisión humana.

**Sobre ML:** no se entrena ningún modelo propio en el MVP. "ML" aquí son solo modelos preentrenados (VAD, STT, diarización). Un posible uso futuro legítimo: **calibrar umbrales** (p. ej. G2) con ≥100–200 llamadas etiquetadas por humanos. Nada más.

| Código | Resolución | Cómo |
|---|---|---|
| **P1** Saludo guión | **R** primario, L solo si hay ambigüedad | Primeros turnos del asesor: saludo (buenos días/tardes/noches) + entidad (fuzzy match con rapidfuzz contra lista configurable; ASR suele deformar nombres de entidad) + autopresentación ("mi nombre es/le habla/habla con…" + nombre). Sub-checks: `saludo`, `entidad`, `nombre_asesor`. |
| **P2** Nombre cliente | **R + (T)** | Obtener nombre del cliente: metadatos si existen, si no extraerlo de la conversación. Contar menciones del nombre/apellido/“señor(a) X” en turnos del asesor. Umbral (≥1 o ≥2) → decisión pendiente P-07. |
| **V1** Conf. documento | **R**, L para ambigüedad | Patrón: asesor pide documento/cédula → cliente dicta dígitos (normalizar números hablados) → asesor repite/confirma. **Limitación:** sin acceso al sistema de agenda NO se puede verificar que el número sea correcto, solo que se solicitó y confirmó. |
| **V2** Valida datos/hist | **L** guiado por keywords (R) | Sub-checks: ¿preguntó tipo de examen? ¿antecedentes/requisitos previos (ayuno, orden médica, alergias… según dominio)? Respuestas sí/no + cita. |
| **G1** Control hold | **T puro** | Evento de hold = desde fin de frase del asesor que anuncia espera ("permítame un momento / lo pongo en espera…") hasta el siguiente turno del asesor al regresar. Duración > 60 s ⇒ falla. Independiente de si hay música de espera (la música confunde al VAD; por eso se usan los turnos, no la energía). Sin hold ⇒ cumple (n/a=cumple, ver P-06). |
| **G2** Agilidad sistema | **T** (+ calibración futura) | Proxy: silencios muertos no anunciados, nº de "un momento", latencia entre pedido del cliente y respuesta. **Es el criterio menos objetivo del conjunto**; definir con el usuario qué significa "agilidad" y calibrar con muestras humanas. |
| **C1** Escucha activa | **T + L** | T: solapes/interrupciones del asesor (fiables solo con canales separados; con diarización mono son ruidosas), ratio de habla. L: ¿repite preguntas ya respondidas?, ¿atiende la necesidad? |
| **C2** Tono y lenguaje | **R + L** (solo texto) | R: léxico (usted, por favor, con gusto, groserías, muletillas negativas). L: calificación de claridad/empatía. **Limitación:** el *tono de voz* (prosodia) NO se evalúa; solo lenguaje. Modelos de emoción en audio: no confiables, descartados. |
| **Z1** Conf. cita/solución | **L (extracción) + R (verificación)** | Slots obligatorios (D-12): `cita_agendada` (confirma que quedó agendada), `fecha`, `hora`, `direccion/sede`, `medico/especialista`, `soportes` (documentos a llevar: orden médica, autorización, documento, carné…) y `preparacion` **solo si el examen la requiere**. L extrae cada slot citando literalmente; R verifica que la cita exista en el texto y que fecha/hora no sean contradictorias. Z1 = 1 solo si todos los slots aplicables están presentes. Para saber si aplica `preparacion` se usa `config/exams_prep.yaml` (examen → requiere preparación: ayuno, contraste, vejiga llena…) que debe proveer el usuario (P-15); si el examen no está en el catálogo → `needs_review` en ese sub-check. |
| **Z2** Despedida guión | **R** (L de respaldo) | Últimos turnos del asesor: "¿algo más en que le pueda colaborar?" + despedida cordial. |
| **E1** Error crítico | **R + datos externos + H** | Ver §9. |

**Patrón general para L:** el LLM **no da puntajes**. Responde **preguntas atómicas sí/no** (un sub-check cada una) con `turn_id` + cita literal. Un agregador determinístico convierte sub-checks en puntaje. Temperatura 0, semilla fija, salida con gramática/JSON schema (llama.cpp GBNF), prompt y rúbrica versionados.

## 9. E1 — Error crítico (reglas cerradas)

El LLM **no decide libremente** qué es un error crítico. Existe un **catálogo cerrado** (`config/critical_errors.yaml`), cada código con detector propio:

| Código | Descripción | Detector |
|---|---|---|
| E1.a | No validó identidad antes de dar/agendar info | R: no hay secuencia pedido-documento+respuesta antes del primer turno donde se agenda/confirma datos del paciente |
| E1.b | Divulgó datos personales/clínicos a un tercero no validado | L propone candidato con cita → **siempre H** (muy propenso a falsos positivos) |
| E1.c | Cita no confirmada o inconsistente en la llamada | **Redefinido (D-12):** sin acceso al registro de la agenda (decisión del usuario) NO se verifica si la cita quedó *correcta* en el sistema. Solo se detecta: (i) la llamada era de agendamiento y el asesor nunca confirma que la cita quedó agendada, o (ii) el asesor da fecha/hora/sede contradictorias entre sí. (i) con detector R es candidato fuerte; (ii) → candidato a revisión humana. Limitación documentada: una cita mal digitada en el sistema es invisible para este sistema |
| E1.d… | Otros (a definir con el usuario, lista cerrada) | — |

Reglas:
- E1 **confirmado** (detector R con evidencia, o validado por H) ⇒ nota final **0 %**.
- E1 **candidato solo por LLM** o con baja confianza ⇒ estado `needs_review`; se informan ambos valores (`score_if_not_critical` y `0`). **Un LLM nunca pone un 0 definitivo por sí solo.**
- Toda activación incluye evidencia (turno, cita, tiempo) y el código del detector.

## 10. Benchmarks a ejecutar ANTES de construir (nada se asume)

| ID | Qué medir | Criterio de decisión |
|---|---|---|
| B0 | Inspeccionar 10 `.gsm` reales: `ffprobe`, ¿mono mezclado o canales separados?, ¿entrante/saliente?, ¿música en hold?, nombres de archivo/metadatos | Define si hay diarización |
| B1 | STT: small/medium/large-v3 int8, beam 1 vs 5, en 10 llamadas con transcripción manual de fragmentos: **WER** y **recall de elementos clave** (documento, nombre, entidad, fecha/hora); **RTF**; **RAM pico** | Elegir el modelo más pequeño que alcance recall aceptable de elementos clave |
| B2 | Diarización (si aplica): error de turnos/DER en 10 llamadas etiquetadas; accuracy de asignación de rol; RTF; RAM | pyannote vs sherpa-onnx vs clustering propio |
| B3 | LLM local: tok/s de prompt y generación, RAM, % de JSON válido, acuerdo con humano en 20 llamadas, con 2–3 tamaños | ¿3–4B alcanza o hace falta 7–8B? |
| B4 | Térmico: carga sostenida de 2 h; frecuencia de CPU en el tiempo | ¿Throttling invalida los tiempos? |
| B5 | End-to-end en 20 llamadas | Tiempo real por llamada y total proyectado a 80 |
| B6 | **Acuerdo sistema vs auditor humano** por criterio (% acuerdo y Cohen's kappa) en el *golden set* | Define qué criterios se automatizan y cuáles quedan con H |

### 10.1 Resultados medidos (2026-10-05) — i5-8250U, Windows 11, faster-whisper 1.2.1, int8, 4 hilos, beam 1, VAD activado

Entorno instalado: Python 3.12.10 (venv en `.venv/`), ffmpeg 9.0.2 (gyan.dev, vía winget), faster-whisper 1.2.1. Scripts en `benchmarks/`. **Nota técnica:** faster-whisper 1.2.1 falla con PyAV 19 (`metadata_errors`); solución adoptada: decodificar con ffmpeg → WAV 16 kHz y pasar un `numpy.float32` a `transcribe()` (no usar `av` para abrir archivos).

**B0 (inspección):** `.gsm` = GSM 06.10 crudo 8 kHz mono; ffmpeg lo decodifica con `-f gsm -ar 8000`. Los `.mp3` auditados: 8 kHz mono. Todas las llamadas son de cola (`q-`).

**B1 — Whisper `small` int8 (14 audios, 57 min):**

| Métrica | Resultado medido |
|---|---|
| RTF global | **0,19** (3427 s de audio en 657 s); rango por llamada 0,12–0,38 |
| RAM pico | **1,1 GB** |
| Carga del modelo | 2,8 s (tras descargarlo; la 1.ª descarga de 480 MB tardó ~10 min) |
| Descarga | ~0,8 MB/s: los modelos grandes tardan decenas de minutos la primera vez |

Con esto una llamada de 6,5 min ≈ 75 s de STT. **80 llamadas/día ≈ 1,7 h de STT con `small`** (vs. la estimación inicial de 2,6 h). Mucho mejor que lo temido.

**Hallazgos de calidad (revisión de transcripciones, `small`):**
1. **Cada llamada empieza con un mensaje grabado (IVR) de ~25–55 s**: aviso de WhatsApp + política de datos (Ley 1581/2012, Decreto 1377/2013) *antes* de que conteste el asesor. Hay que **detectarlo y excluirlo** de la evaluación (no es el asesor; P1 se mide después). Se detecta con plantilla de texto fija (coincidencia fuzzy) + es idéntico entre llamadas. Decisión D-17.
2. **`small` degrada nombres y frases clave**: "Nueva EPS" → "No, EPS"; "¿en qué le puedo servir?" → "¿Hasta la semana que le puedo servir?"; el nombre de la persona sale ininteligible. Confirma el riesgo R2: P1/P2/V1 no pueden depender de coincidencia literal de `small`. Falta medir `medium`.
3. **Llamada `2072433` (142 s) sin voz detectable**: ni con normalización de ganancia el VAD detecta habla (≈1–3 s). Probable abandono en cola/música/ruido. El sistema necesita estado **`no_speech`/`sin_conversacion`** que NO produzca una nota (D-18).
4. El archivo `.json` de salida guarda palabras con timestamps y probabilidad (útil para G1 y confianza).

**B2 — Diarización (sherpa-onnx 1.13.8: segmentación pyannote-3.0 ONNX + embedding `nemo titanet_small`, k=2, sin token de HuggingFace, 100 % offline):**

| Métrica | Resultado medido |
|---|---|
| RTF | **0,15** (≈ 55 s para una llamada de 6 min) |
| RAM pico | **0,4 GB** |
| Modelos | segmentación 6 MB + embedding 38 MB, descarga de GitHub (segundos) |

pyannote oficial (HuggingFace) **no se usó**: requiere aceptar términos y token; sherpa-onnx lo evita y es más liviano. Decisión provisional D-20.

**Calidad (sin ground truth numérico; revisión cualitativa alineando con la transcripción):**
1. En `1870590` (llamada auditada) la separación asesor/cliente es **plausible** (cliente = un hablante, asesor+IVR = el otro), con errores en turnos cortos ("sí", "bueno").
2. **Fallo grave en `2091394` (y probablemente otras con espera):** los mensajes grabados **secuestran un cluster**. En esa llamada el "segundo hablante" resultó ser la **voz grabada del hold** (frase de ~3 s repetida cada ~25 s) y asesor+cliente quedaron fundidos en uno. Probado con 3 embeddings distintos (titanet, wespeaker, 3dspeaker): el problema persiste → no es culpa del modelo de voz, es del audio.
3. **Solución que funcionó:** recortar el tramo previo al hold y re-diarizar → asesor y cliente se separan correctamente con `titanet_small` (con `wespeaker` no). Conclusión: **hay que eliminar el audio grabado (IVR inicial + loop de hold) antes de agrupar hablantes** (D-21).
4. El IVR inicial se agrupa con el *cliente* en esa llamada (voz de máquina cerca del cliente en el espacio de embeddings) y con el asesor en otra → no se puede decidir el rol por el cluster; se asigna por **contenido** (D-13).
5. Los segmentos de Whisper mezclan a veces dos hablantes (ej. respuesta del cliente + "permítame un momento" del asesor en un mismo segmento): hay que alinear **a nivel de palabra** (timestamps por palabra ya disponibles), no por segmento.

**Hallazgo clave para G1 (hold):** en `2091394` (no auditada) el asesor dice "permítame un momento, no me cuelgue" a los ~82 s y el audio queda en un **bucle del mensaje grabado** ("Gracias por comunicarse con Angiografía de Occidente… horarios de atención…") **hasta ~337 s ≈ 255 s de espera ⇒ G1 = 0** (límite 60 s). Whisper transcribe el bucle repetidamente, por lo que se puede **detectar con texto**: n-gramas repetidos periódicamente + plantilla del mensaje de espera; y delimitar el hold por timestamps. Es un caso real de falla G1 para el golden set (pendiente de que el auditor humano lo confirme).

**B1 — Whisper `medium` int8 (mismas 14 audios, beam 1):**

| Métrica | Resultado medido |
|---|---|
| RTF sin contención (9 de 14 llamadas) | **≈ 0,44–0,58** (0,93 en la llamada con bucle de hold). Las primeras 5 llamadas se midieron mientras corría otro proceso (RTF 0,47–1,35) → **no válidas**; el RTF global reportado de 0,63 está inflado |
| RAM pico | **2,65 GB** |
| Carga | 9,5 s (descarga inicial de 1,5 GB tardó ~1,5 h por la red) |

Estimación para 80 llamadas de 6,5 min (**extrapolación del RTF medido**): STT `medium` ≈ 3 min/llamada ≈ **4,3 h**; + diarización (0,15) ≈ 1,3 h → ≈ **5,6 h/día sin LLM**. Cabe en una sesión de lote.

**Calidad `medium` vs `small` (revisión cualitativa, mismas llamadas):**
- Mejora clara en frases clave: "Angiografía de **Occidente**, buen día. **Habla** María José Cuesta. ¿En qué le puedo servir?" (small: "accidente… La Blamaria"); "¿Qué **EPS** tiene?" (small: "¿Qué pese tiene?"); "Mi **nombre es** Yolanda…" (small: "Mi camino es…"); "Clínica Versalles" (small: "Crínica").
- **Pero `medium` omitió los dígitos del documento** ("10, 62, 331, 565") que `small` sí capturó, y aún escribe "9PS" por "Nueva EPS". Implicación: V1 **no puede depender de leer el número**; debe detectar el *evento* (asesor pide documento → cliente responde con una secuencia de números → asesor confirma), con ambos modelos como respaldo.
- El nombre del asesor salió bien en `medium` ("María José Cuesta", coincide con una agente de la plantilla) → viable cruzar con un **roster de asesores** (lista de nombres) para P1/P2. Pendiente que el usuario entregue la lista.

**B3 — LLM local, Qwen2.5-3B-Instruct Q4_K_M (llama.cpp b11433, binario Windows CPU/AVX2 `haswell`, 4 hilos):**

| Métrica | Resultado medido |
|---|---|
| Lectura de prompt (`llama-bench`) | **38–41 tok/s** |
| Generación | **10,7 tok/s** |
| RAM del modelo | ~2 GB (archivo 1,95 GiB) |
| Tiempo por llamada (10 sub-checks, JSON restringido por esquema) | **49–64 s** con 1000–1200 tokens de prompt y 230–300 de salida. 80 llamadas ≈ **1,2–1,4 h** (la transcripción sin IVR es corta) |
| JSON válido | 2/2 (100 %, esquema forzado con `response_format`) |
| Descarga | 369 s para 2 GB (≈5,5 MB/s: la red mejoró) |

**Calidad con 3B (2 llamadas, revisión manual — muestra mínima):** el formato es perfecto pero el contenido **no es confiable**: a veces responde `false` donde sí hay evidencia (P1), da citas que no están literalmente en el turno indicado (5 de 7 aciertos con cita fallida) y asoció la evidencia equivocada a V2 (citó un teléfono como "tipo de examen"). **El validador de citas atrapó las citas inexistentes** (justo para lo que se diseñó). Conclusión provisional: 3B sirve solo como respaldo/segunda opinión; se prueba 7B (≈ 2,3× más lento, estimado ≈ 2,5 min/llamada ≈ 3,3 h/80 llamadas) y se mantiene el principio de que reglas primero y LLM solo para ambigüedad.

**B3 — Qwen2.5-7B-Instruct Q4_K_M (mismas 2 llamadas y prompt):**

| Métrica | 3B | 7B |
|---|---|---|
| Tiempo por llamada | 49–64 s | **157–199 s** (≈3× más lento; mi estimación de 2,5 min fue optimista) |
| RAM del servidor (ctx 8192) | ~2–3 GB | **7,4 GB** |
| JSON válido | 100 % | 100 % |
| Citas verificables (llamada 1) | 3 de 7 respuestas `true` | **6 de 8** |
| Fallos | P1 no detectado; evidencia equivocada en V2 | P1 no detectado (el saludo del asesor sale garbled del STT/diarización); cita inventada en `Z2_algo_mas` (la frase no existe, el validador la rechazó) |

Proyección **ESTIMADA** para 80 llamadas: LLM 3B ≈ 1,3 h; **LLM 7B ≈ 4 h** (+ STT medium ≈ 4,3 h + diarización ≈ 1,3 h ⇒ **≈ 9–10 h por lote diario**, viable solo como lote nocturno/largo, y solo si el LLM se usa únicamente en los sub-checks ambiguos tras las reglas). Muestra de 2 llamadas: **no es una medición de precisión**. La mejora de 7B sobre 3B es real pero moderada; ningún modelo sustituye a las reglas ni al validador de citas. Decisión D-22.

**Pendiente de medir:** `large-v3`, WER con transcripción manual, térmico (B4), LLM (B3), térmico (B4), WER contra transcripción manual (hacen falta 1–2 min transcritos a mano de ~5 llamadas).

## 11. Golden set (requisito, no opcional)

Sin llamadas auditadas por humanos **no se puede saber si el sistema funciona.** Se necesitan ~30–50 llamadas con la nota de un auditor humano por criterio, y ~10 con transcripción manual (al menos fragmentos).

**Estado actual (2026-10-05):** el usuario dispone de **10 llamadas de muestra sin auditar** y **6 llamadas auditadas**. 6 llamadas sirven como *prueba de humo* (¿el sistema contradice groseramente al auditor?) y para calibrar reglas, **pero no permiten medir acuerdo estadísticamente** (kappa con n=6 no es interpretable). Plan: usar las 6 en desarrollo; pedir al auditor humano que audite el resto de las 10 (→ 16) y seguir acumulando hasta ≥30 antes de confiar en las cifras. Para medir WER se necesita transcripción manual de fragmentos (p. ej. 1–2 min por llamada en 5 llamadas), no la auditoría. Almacenar cifrado y fuera de control de versiones (contiene PII). Cada cambio de modelo/prompt/regla se re-evalúa contra este set.

### 11.1 Análisis de las 6 llamadas auditadas (plantilla `Matriz_Auditoria_Llamadas plantilla.xlsx`)

| Auditoría | Motivo | Puntaje | Fallos |
|---|---|---|---|
| AUD-001 | Solicitud cita médico general | 10/10 | — |
| AUD-002 | Cancelar cita | 10/10 | — |
| AUD-003 | Cardiología pediátrica | 9/10 | Z1 |
| AUD-004 | Información laboratorio / confirmación de cita | 10/10 | — |
| AUD-005 | Solicitud cita médico general | 8/10 | V1, V2 (obs.: "error de campaña") |
| AUD-006 | Solicitud cita médico general | 10/10 (la hoja muestra 10/11) | — |

Hallazgos críticos:
1. **Desbalance extremo:** 57 de 60 sub-evaluaciones = 1 (95 % cumple). Cero casos de E1, G1, G2, C1, C2, P1, P2, Z2 fallidos. Un "sistema" que respondiera todo 1 coincidiría ~95 %. **El acuerdo global es una métrica engañosa**; hay que medir *recall de fallos* por criterio, y para ello hacen falta llamadas donde el humano haya marcado 0. Solo hay 3 fallos en total (Z1×1, V1×1, V2×1): sirven como casos de prueba, no como validación.
2. **El auditor humano parece indulgente** o la muestra es de agentes buenos. Antes de automatizar, conviene medir si dos humanos coinciden (acuerdo inter-auditor).
3. **Defectos de la plantilla Excel:** la columna *Puntaje Máximo* crece por fila (10, 11, 12… hasta 33) en lugar de ser siempre 10 → la nota de AUD-006 sale 90,9 % en vez de 100 %. Corregir fórmula. La columna *E1* usa 0 = "sin error" (se interpreta como ausencia); confirmar la convención para no invertirla (P-20). El umbral de "Aprobado" no es visible (AUD-005 con 80 % figura aprobado; P-21).
4. **Motivos de llamada variados** (cita nueva, cancelación, información de laboratorio, confirmación, especialidad). La rúbrica no aplica igual a todas: p. ej. una cancelación no requiere "preparación" ni los mismos slots de Z1. **Se necesita una matriz de aplicabilidad criterio × tipo de llamada** (D-15, pendiente de definir con el usuario).
5. La plantilla trae solo 0/1 y observaciones libres; **no hay evidencia ni marcas de tiempo** del auditor humano. Para validar evidencia habrá que pedirle al auditor que anote, en al menos algunas llamadas, el minuto aproximado de cada fallo.

## 12. Privacidad y seguridad

- **Por defecto: 100 % local.** `allow_external_llm: false`.
- Los datos incluyen documentos de identidad, nombres, datos de pacientes y citas ⇒ **datos personales sensibles (salud)**. Si se opera en Colombia aplica la **Ley 1581 de 2012** (hábeas data) y normas reglamentarias; las transferencias internacionales tienen condiciones. **Validar con el área jurídica** antes de enviar *cualquier* dato real a terceros. (No es asesoría legal.)
- Las capas gratuitas de APIs (Gemini, etc.) suelen tener términos que permiten usar los datos para mejorar el producto: **no usar con datos reales.**
- Fallback externo permitido **solo** con texto anonimizado: dígitos largos → `[DOC]`, teléfonos → `[TEL]`, nombres → `[NOMBRE_CLIENTE]` (NER/regex; **la anonimización de nombres es imperfecta**, por lo que el fallback externo se considera de riesgo residual y está apagado por defecto). Todo resultado generado por fallback se marca `engine: remote` y se puede re-ejecutar localmente.
- **Cifrado de disco completo** (BitLocker/LUKS): el riesgo más realista es el robo/pérdida del portátil.
- Borrado: WAV temporal se elimina al terminar cada llamada; `.gsm` original según política de retención (propuesta: N días configurable, p. ej. 30; decidir en P-09); transcripción completa con retención definida; en el resultado/dashboard mostrar documentos **enmascarados** (`****6789`).
- No registrar texto de transcripciones en logs. Acceso a carpeta de datos restringido al usuario del servicio.
- Dependencia de red: los modelos se descargan **una vez**; luego el sistema debe correr **offline** (verificar con pyannote/HF).

## 13. Esquema JSON del resultado (v1, propuesto)

```json
{
  "schema_version": "1.0",
  "call": {
    "call_id": "uuid",
    "source_file": "nombre.gsm",
    "sha256": "…",
    "duration_s": 392.4,
    "direction": "inbound|outbound|unknown",
    "received_at": "2026-10-05T14:03:00-05:00",
    "processed_at": "2026-10-05T22:41:10-05:00",
    "metadata": { "agent_id": null, "caller_id_masked": null }
  },
  "pipeline": {
    "ffmpeg": "x.y", "stt_model": "faster-whisper-medium-int8", "stt_params_hash": "…",
    "diarization": "channels|sherpa-onnx|pyannote-3.1", "llm_model": "…gguf", "llm_sha256": "…",
    "rubric_version": "1.0", "prompt_version": "1.0", "rules_version": "1.0",
    "engines_used": { "llm": "local|remote|none" }
  },
  "status": "completed|needs_review|failed",
  "quality": {
    "asr_avg_confidence": 0.0, "diarization_confidence": 0.0, "role_confidence": 0.0,
    "warnings": ["audio_muy_corto", "baja_confianza_roles"]
  },
  "speakers": { "asesor": "SPEAKER_0|ch_in", "cliente": "SPEAKER_1|ch_out" },
  "transcript": [
    { "turn_id": 1, "speaker": "ASESOR", "start": 0.8, "end": 6.2, "text": "Buenos días, …" }
  ],
  "metrics": {
    "talk_ratio": { "asesor": 0.52, "cliente": 0.48 },
    "overlap_s": 4.1, "interruptions_by_agent": 1,
    "dead_air_total_s": 12.3, "longest_dead_air_s": 6.0,
    "hold_events": [ { "start": 120.4, "end": 151.0, "duration_s": 30.6, "announced": true,
                       "turn_start": 14, "turn_end": 15 } ]
  },
  "criteria": {
    "P1": {
      "score": 1, "max": 1, "method": "rule|time|llm|hybrid", "confidence": 0.93,
      "sub_checks": [
        { "id": "saludo", "passed": true, "source": "rule", "evidence": { "turn_id": 1, "quote": "Buenos días", "start": 0.8, "end": 1.6 } },
        { "id": "entidad", "passed": true, "source": "rule", "evidence": { "turn_id": 1, "quote": "…", "start": 1.7, "end": 3.0 } },
        { "id": "nombre_asesor", "passed": true, "source": "rule", "evidence": { "turn_id": 1, "quote": "mi nombre es Juan", "start": 3.1, "end": 4.9 } }
      ],
      "explanation": "El asesor saluda, indica la entidad y se identifica con nombre."
    },
    "V1": {
      "score": 0, "max": 1, "method": "hybrid", "confidence": 0.8,
      "sub_checks": [ { "id": "solicita_documento", "passed": false, "source": "rule", "evidence": null } ],
      "explanation": "No se encontró evidencia de solicitud y validación del documento."
    }
  },
  "critical_error": {
    "status": "none|candidate_pending_review|confirmed",
    "findings": [ { "code": "E1.a", "source": "rule|llm|human", "evidence": { "turn_id": 9, "quote": "…" } } ]
  },
  "score": {
    "points": 8, "max_points": 10, "percent_raw": 80.0,
    "percent_final": 80.0, "e1_override": false, "score_if_not_critical": 80.0
  },
  "human_review": { "required": false, "reasons": [] }
}
```

Regla de validación del resultado: toda `evidence.quote` debe aparecer (match exacto/difuso con umbral) en `transcript[turn_id].text`; si no, el sub-check se descarta y se reintenta o se marca `needs_review`.

## 14. Reglas de puntuación

- 10 criterios (P1,P2,V1,V2,G1,G2,C1,C2,Z1,Z2) × 1 punto = 10. **Binario** en el MVP (0 o 1); medios puntos solo si el usuario lo pide más adelante.
- Cada criterio = función determinística de sus sub-checks (ej. P1 = saludo ∧ entidad ∧ nombre). Se definen en `config/rubric.yaml` y se versionan.
- `percent_raw = puntos × 10`. Si E1 confirmado ⇒ `percent_final = 0`.
- Criterio no aplicable (ej. G1 sin hold): por defecto **cumple** (pendiente P-06).
- Si la calidad de ASR/diarización/rol es baja ⇒ no se inventa un puntaje: `needs_review`.

## 15. Estructura inicial del proyecto

```
gestion-llamadas/
├─ CONTEXT.md                  # este archivo (memoria técnica)
├─ README.md                   # (después) uso rápido
├─ pyproject.toml              # (después) dependencias fijadas
├─ config/
│  ├─ settings.yaml            # rutas, hilos, modelos, retención, flags (allow_external_llm=false)
│  ├─ rubric.yaml              # criterios, sub-checks, agregación
│  ├─ critical_errors.yaml     # catálogo cerrado E1
│  ├─ entity.yaml              # nombre(s) de la entidad + variantes ASR
│  └─ lexicons/                # saludos, despedidas, groserías, frases de hold…
├─ prompts/v1/                 # prompts versionados (un archivo por sub-check o grupo)
├─ schemas/
│  ├─ audit_result.schema.json
│  └─ transcript.schema.json
├─ src/llamadas/
│  ├─ intake/                  # watcher, estabilidad de archivo, dedupe SHA-256
│  ├─ queue/                   # SQLite jobs, estados, reintentos
│  ├─ audio/                   # ffmpeg/ffprobe
│  ├─ stt/                     # faster-whisper
│  ├─ diarization/             # canales | sherpa | pyannote (interfaz común)
│  ├─ roles/                   # asignación asesor/cliente
│  ├─ metrics/                 # hold, silencios, solapes
│  ├─ rules/                   # un módulo por criterio
│  ├─ llm/                     # cliente llama-server, gramáticas, fallback remoto (opcional)
│  ├─ validator/               # JSON schema + verificación de citas
│  ├─ scoring/                 # agregador + E1
│  ├─ storage/                 # SQLite + JSON + retención/borrado
│  ├─ pipeline.py              # orquestador por etapas
│  └─ cli.py                   # comandos: process, worker, report, bench
├─ tests/
│  ├─ unit/                    # reglas y métricas con transcripciones sintéticas
│  └─ golden/                  # evaluación contra auditoría humana
├─ benchmarks/                 # scripts B0–B6 + resultados .md
├─ docs/decisions/             # ADRs (opcional; el registro resumido está en §17)
└─ data/                       # NO versionar; cifrado de disco
   ├─ incoming/  processing/  processed/  failed/
   ├─ audio_tmp/  transcripts/  results/
   └─ golden_set/              # PII: restringido
```

## 16. MVP

**Alcance MVP (sin dashboard, sin n8n, sin Postgres, sin Docker):**
detectar `.gsm` → cola SQLite → ffmpeg → STT → (diarización o canales) → roles → métricas → reglas → LLM (solo lo semántico) → validación → JSON + SQLite → resumen en consola.

**Orden de construcción propuesto (cada paso se valida contra el golden set):**
0. Benchmarks B0–B4 (sin construir el sistema).
1. CLI de un archivo: `.gsm` → transcripción con timestamps.
2. Hablantes + roles.
3. Reglas/T: **P1, Z2, V1, G1** (los más determinísticos).
4. Resto de reglas + métricas (P2, C1-T, G2-T, C2-R).
5. LLM para V2, C1, C2, Z1 + validador de citas.
6. E1 con catálogo cerrado + estado `needs_review`.
7. Cola/worker continuo + política de borrado.

**NO construir todavía:** dashboard, autenticación, n8n, PostgreSQL, Docker, enrolamiento de voz de asesores, ML propio, detección de emociones en audio, concurrencia, tiempo real.

## 16.1 Plan por fases (definido 2026-10-05; sustituye al "orden de construcción" anterior)

| Fase | Contenido | Criterio de salida | Estado |
|---|---|---|---|
| **0 — Diseño y benchmarks** | Arquitectura, CONTEXT.md, B0/B1/B2 (inspección, STT, diarización) | Modelos y límites del hardware medidos | ✅ Hecha |
| **1 — Audio → transcripción estructurada** | `.gsm/.mp3` → ffmpeg → VAD/`no_speech` → STT medium (con caché) → detección y exclusión de audio grabado (IVR + mensajes en llamada) → diarización → alineación por palabra → asignación de roles por contenido → `*.transcript.json` + CLI `python -m llamadas transcribe` | Corre sobre las 14 muestras sin errores; IVR bien detectado; `needs_review` honesto cuando falla la separación; tests unitarios en verde | ✅ **Funcional (2026-10-05)**: 14/14 sin errores, 7 tests en verde. Resultado: 9 `completed`, 4 `needs_review` (3 por diarización sospechosa), 1 `no_speech`. **Separación de hablantes sigue siendo el punto débil** (ver §16.2). Mejora pendiente: etiquetado de rol por turno con ayuda de texto/LLM |
| **2 — Métricas y reglas determinísticas** | Holds (G1) por timestamps + anuncio del asesor, saludo/entidad/nombre (P1), documento (V1 por evento), despedida (Z2), nombre del cliente (P2), léxico de tono (C2-R), silencios (G2-T), clasificación del motivo de la llamada; sub-checks con evidencia y salida JSON del §13 | Cada regla probada con transcripciones reales + **simuladas con fallos** (D-19); comparación con las 6 auditadas | ✅ **Funcional (2026-10-06)**: 24 tests en verde (17 casos simulados), CLI `llamadas audit`. Acuerdo con el humano **79 % en lo decidido** y solo **1 de 3** fallos humanos detectados (ver §16.3). No es validación estadística |
| **3 — LLM Auditor y puntaje** | `llama-server` + GGUF; preguntas sí/no con cita literal para V2, C1, C2, Z1; validador de citas; catálogo E1; agregador (nota, E1, `needs_review`) | B3 medido; JSON válido ≥ 95 %; E1 nunca fijado solo por LLM | ✅ **Implementada (2026-10-06)**: `llm.py`, `auditor.py`, `review.py`, `export.py`, `jobs.py`; 10 tests. La IA 3B resuelve pocos pendientes de forma fiable (ver §16.4); la **nota final sale de la revisión humana** en la interfaz |
| **3b — Interfaz gráfica** | App web local (`llamadas gui` / `Iniciar_Auditoria.bat`): cargar audios, analizar con progreso, resultados con semáforos, revisión con audio y evidencia, exportar a Excel con el formato de la matriz | Un auditor sin conocimientos técnicos puede cargar → revisar → exportar | ✅ **Funcional (2026-10-06)** (ver §16.4). Pendiente: prueba de usabilidad con el usuario |
| **4 — Lote reanudable y salida** | Cola SQLite reanudable, `llamadas process <carpeta>` con progreso/ETA, borrado de WAV/política de retención, informe en consola/Excel con el formato de la plantilla | Procesar 80 llamadas de una vez sin intervención y reanudar tras apagado | ⏳ |
| **5 — Validación y ajuste** | Golden set ampliado, acuerdo por criterio (recall de fallos), calibrar umbrales, WER con transcripción manual | Informe de acuerdo sistema vs. humano; decidir qué criterios quedan automáticos | ⏳ |
| **6 — Producto** | Dashboard, historial, filtros, exportación, (n8n/PostgreSQL solo si hacen falta) | — | ⏳ (no empezar antes de la 5) |

### 16.2 Fase 1 — estado y hallazgos (2026-10-05)

Código en `src/llamadas/` (`audio`, `stt`, `recorded`, `diarize`, `transcript`, `roles`, `pipeline`, `__main__`), configuración en `config/settings.toml` y `config/lexicons.toml`, pruebas en `tests/unit/`, utilidades en `scripts/` (`seed_stt_cache.py`, `debug_recorded.py`, `debug_diar.py`, `eval_clusters.py`). Se ejecuta con `.venv\Scripts\python.exe -m llamadas transcribe <archivo|carpeta> --show`. Caché de STT en `data/cache/` (clave sha256+modelo) para no re-transcribir al iterar.

Hallazgos de la implementación:
1. **IVR más largo de lo que parecía.** En la cola `800197` (Nueva EPS probable) el mensaje inicial incluye además avisos de patologías oncológicas/embarazo y puede durar **hasta ~265 s** (cliente esperando en cola) antes de que conteste el asesor. Plantillas añadidas en `lexicons.toml`. El IVR mal transcrito se absorbe si *parece* IVR y pronto vuelve a coincidir; con una versión previa, la voz del asesor fue absorbida por error (corregido y cubierto con test).
2. **Separación de hablantes frágil cuando un hablante habla poco** (`2072716`, `2072690`: el cliente monologa y el asesor dice poco; el modelo de voz los funde). Mitigación: sobre-segmentar (num_clusters=3) y decidir el rol de cada cluster por **contenido**; si un rol queda con < 8 % de las palabras → `needs_review` (`diarizacion_sospechosa_un_rol_casi_sin_habla`). Es una limitación real del audio telefónico mono de 8 kHz, no un bug.
3. **Posible discrepancia con el auditor humano en `1870774` (AUD-001, 10/10):** el sistema detecta un hold de ~83 s (de ~333 s a ~416 s: el asesor dice "un momento" y suena audio grabado) ⇒ G1 debería ser 0. Falta que un humano lo escuche y lo confirme.
5. **Resultado de `eval_clusters.py` (k=2..6, 9 llamadas, métricas proxy sin ground truth):** con k=2 la separación colapsa en 5 de 9; con k≥3 mejora; k=5 arregla además `2072690`. En ~4 de 9 llamadas, un rol queda con <8 % de las palabras (cliente fundido con asesor): el modelo de voz no separa dos voces telefónicas cuando una habla poco. Esas llamadas salen `needs_review`. **Siguiente mejora candidata (Fase 1b/3):** usar la diarización solo para *segmentar* y etiquetar el rol de cada turno por contenido/estructura pregunta–respuesta (reglas + LLM).
6. **Costo de proceso medido de Fase 1** (con STT en caché): 10–40 s por llamada para audio de 2–9 min (diarización + roles).
4. Los segmentos grabados dentro de la llamada se llaman `grabado_en_llamada`: pueden ser bucle de hold **o** mensajes de cola. Decidir si es un hold (G1) es trabajo de la Fase 2.

### 16.3 Fase 2 — implementación y resultados (2026-10-06)

**Código:** `metrics.py` (huecos, holds, tiempo muerto), `rules/` (`identity` P1/P2/V1/V2, `flow` G1/G2/C1/C2, `closing` Z1/Z2, `critical` E1, `calltype`, `context`), `audit.py` (aplicabilidad, agregación, `percent_min–max`), CLI `python -m llamadas audit [--detail]`, salida `data/results/<id>.audit.json` (esquema `0.2-fase2`, parcial: sin LLM). Configuración: `config/settings.toml [rules]`, `config/lexicons.toml [rules]`, `config/rubric.toml` (aplicabilidad), `config/agents.toml` (roster, **no versionar**). Pruebas: `tests/unit/test_fase2.py` + `tests/synthetic/builder.py` (llamadas simuladas con fallos, `synthetic=True`). Comparación contra humanos: `scripts/compare_golden.py` + `tests/golden/auditadas.json`.

**Diseño:** cada criterio es una función de sub-checks con evidencia (turno, cita literal, tiempos). `score = None` (pendiente) cuando falta evidencia suficiente en vez de inventar un 0; la nota se informa como **rango** `percent_min–percent_max` hasta que el LLM/humano cierre los pendientes. E1 solo genera **candidatos** (D-07). Holds: hueco entre turnos humanos, clasificado `grabado` (solapa audio grabado en llamada) / `anunciado` ("permítame un momento" en los 2 turnos previos) / `silencio` (tiempo muerto); G1 falla si un hold ≥ 60 s.

**Resultado sobre las 6 auditadas (n=6; el humano puso 1 en 57 de 60):** acuerdo en lo decidido **37/47 = 79 %** (13 pendientes), **detecta 1 de 3 fallos humanos** (Z1 de AUD-003; no detecta V1/V2 de AUD-005). La línea base "todo cumple" ya da 95 %: **el sistema aún no supera a un clasificador trivial en acuerdo global**; lo que sí aporta son las evidencias y los casos que contradicen al humano. Desacuerdos restantes: P1/P2 (STT deforma saludo y nombres), V1 en 2 llamadas (pidió "registro civil/tarjeta de identidad" o el documento no consta en el texto), Z1 en llamadas de información.

**Hallazgos importantes:**
1. **G1 en `1870774` (AUD-001, humano=1): el sistema marca ~81 s de espera y la evidencia lo respalda.** Tras "¿Está le dando su momento?" (333,6 s) el audio contiene mensajes de cola grabados y conversación de fondo del asesor ("lo dejo para mañana…") hasta que el asesor vuelve (~416–428 s). Probable error/indulgencia del auditor humano; **pendiente que un humano lo escuche.**
2. **Bug encontrado y corregido:** `rapidfuzz.partial_ratio` devuelve 100 cuando un texto muy corto ("Y", "Sí.") está contenido en la frase buscada → falsos positivos (p. ej. C2 falló por la oración "Y"). Ahora se exige texto de tamaño comparable (≥ 60 % de la frase). Cubierto por la revisión con datos reales.
3. **Los asesores no dicen literalmente "¿algo más en que le pueda colaborar?"** en 5 de 6 llamadas con Z2=1 del humano. La exigencia literal queda **desactivada provisionalmente** (`z2_algo_mas_required=false`, D-25) hasta que el usuario decida el estándar (P-23). Con ella activa, Z2 fallaría en casi todas.
4. **El médico solo se exige en consultas** (una radiografía no tiene médico asignado): `consulta_words`. Aun así Z1 sigue siendo frágil en llamadas de información/laboratorio (clasificadas como `nueva_cita`).
5. **El STT deforma el saludo** ("La prensa es por la ciudad de Occidente", "gente de Golgoos"): si el saludo tiene `avg_prob < 0.8`, la *ausencia* de entidad/nombre queda **pendiente**, no fallo (D-26). Costo: más pendientes para el LLM.
6. **No sobre-ajustar:** los umbrales (G2: tiempo muerto 90 s total / 30 s individual) se subieron para que las 6 llamadas auditadas pasen; con n=6 y cero G2=0 humanos es **calibración sin poder de detección**. Se documenta como `calibration_pending`.

### 16.4 Fase 3 + interfaz gráfica (2026-10-06)

**Decisiones del usuario que cambiaron las reglas:** (1) preguntar "¿algo más?" es **obligatorio** (Z2; `z2_algo_mas_required=true`, revierte D-25); (2) la espera de `1870774` **sí era real** (~81 s; el auditor humano se equivocó) ⇒ G1 correcto, y la nota humana de AUD-001 en G1 debe corregirse; (3) pedir el **documento del paciente es obligatorio también con menores** (V1; ya aceptamos "registro civil/tarjeta de identidad"); (4) se entregó `Base_maestra_preparacion_examenes.xlsx` (25 procedimientos × sedes + 10 direcciones de IPS/clínicas).

**Base maestra (`catalog.py`):** lee el Excel (hoja 1: CUPS, procedimiento, sede, dirección, hora de llegada, documentos, preparación, medicamentos, acompañante, recomendaciones; hoja 2: direcciones). Uso en Z1: (a) `direccion_sede` se verifica contra los nombres de sedes del catálogo (se excluyen términos genéricos como "occidente"); (b) `preparacion` pasa de opcional a **obligatoria** si el examen detectado en la llamada figura en el catálogo y su preparación no empieza por "No requiere"; si el examen no está (el catálogo es parcial: p. ej. radiografía de rodilla no figura) queda opcional y se informa. Ruta configurable en `settings.toml [catalog]`.

**LLM (`llm.py`, `auditor.py`):** `LlamaServer` arranca/para `llama-server` bajo demanda (127.0.0.1); modos `rapido` (Qwen2.5-3B) y `preciso` (7B). Solo se pregunta lo **pendiente** (sub-checks con `passed=None`), en **lotes de ≤4 preguntas** (un lote de 10 fue truncado: JSON inválido), con ids tolerantes y salida con esquema. Validador: "sí" solo vale si la cita aparece (≥88 % aprox.) en la transcripción; "no" se acepta pero exige revisión; JSON inválido ⇒ queda pendiente; E1 intocable. Medido sobre las 13 auditorías con pendientes (3B, 26 preguntas): **3 "sí" verificados (12 %)**, 13 "no" (solo pistas), 10 citas inventadas/triviales descartadas. Tres ajustes salieron de esas pruebas: esquema con `enum` de ids y `minItems=maxItems` (con esquema abierto el 3B inventaba ids "C1.0…C1.8"; con el cerrado la salida bajó de 350 a 58 tokens), un "no" del LLM **no fija 0** (solo pista; el 3B decía "no" a casi todo) y la cita debe tener ≥3 palabras (aceptó "Sí señora" como evidencia). ⇒ **el 3B no sustituye a la revisión humana**; `preciso` (7B) es la opción para dejar corriendo de noche. Sin IA, el sistema sigue funcionando (modo degradado, D-09).

**Revisión humana y nota final (`review.py`):** el auditor confirma/corrige cada criterio y E1 en la interfaz; la decisión humana siempre gana; E1 confirmado ⇒ 0 %; mientras haya criterios sin decidir la nota es un **rango**; ≥ 80 % = Aprobado. Se guarda en `data/reviews/<id>.json` y alimenta el Excel (`export.py`, mismas columnas de la matriz; "Pend." donde falta decisión).

**Interfaz (`gui/`, `jobs.py`):** servidor local `http.server` en 127.0.0.1:8765 + página única (HTML/CSS/JS sin dependencias). Flujo "1 Cargar y analizar → 2 Resultados y revisión → Exportar". Procesamiento por lotes secuencial en un hilo (progreso por etapa, ETA, cancelar, errores por llamada sin detener el lote, omisión de duplicados por hash, reanudable). Detalle de llamada: transcripción como chat con marcas de mensajes grabados y esperas, reproductor de audio (WAV 8 kHz generado con ffmpeg, con Range), evidencias clicables que saltan al audio, tarjetas por criterio con la norma de la guía, semáforos, decisión Cumple/No cumple, panel de posible error crítico, datos de asesor/auditor/motivo/observaciones, botón de **eliminar llamada** (privacidad). Arranque: `Iniciar_Auditoria.bat` o `python -m llamadas gui`. Guía para el usuario: `LEEME.md`.

### 16.5 Capa de diseño y presentación (2026-10-06)

- **Interfaz:** sistema de tokens CSS (tema claro/oscuro × 6 paletas × 6 estilos: Liquid Glass, Glassmorfismo, Aurora, Neumorfismo, Minimalista, Clásico). Los estilos solo redefinen tokens, así las miniaturas de la pestaña **Configuración** son vistas previas reales. Preferencias en `localStorage` del navegador (`auditoria.prefs`), sin tocar el servidor. Animaciones con tres niveles (completas/suaves/ninguna) y respeto de `prefers-reduced-motion`; recomendado «Suaves» en el i5 si se siente lento (el desenfoque de fondo es costoso).
- **Guardar revisión:** al guardar, la ventana se cierra sola, aparece un aviso (con criterios aún pendientes) y la fila se resalta. Ctrl+S guarda; salir con cambios sin guardar pide confirmación; error de guardado no cierra la ventana. Opción en Configuración: abrir la siguiente llamada por revisar. El nombre del auditor se recuerda.
- **Presentación:** `presentacion/Presentacion_Auditoria_IA.html` (abre sin internet, salvo las tipografías) y copia publicada como Artifact privado. Las cifras de uso son **proyecciones** con calculadora ajustable (supuestos: 12 min manual vs 4 min con la app por llamada, 6 h efectivas de auditor); solo velocidad de proceso (≈5,6 h/80 llamadas, IA 20–60 s) viene de mediciones en 14 llamadas. Propone piloto de 4 semanas con criterios de éxito (≥85 % de coincidencia por criterio, ≤4 min de revisión).

### 16.6 Escala real de la operación (2026-10-06)

**Dato nuevo del usuario:** entran **1.000–2.000 llamadas/día** (no 80). El objetivo es auditar una **muestra representativa** con **máximo 2 h humanas al día**; hoy una persona no alcanza.
- Muestra (95 %, ±5 %, p = 0,5, corrección por población finita): **278 / 306 / 323** llamadas para 1.000 / 1.500 / 2.000. Con ±7 %: 165 / 174 / 179.
- A mano (12 min/llamada, supuesto): ≈56–65 h/día; en 2 h se auditan ≈10 (≈3 % de la muestra).
- Cómputo medido ≈4,2 min/llamada sin IA + ≈0,7 IA rápida ⇒ ≈4,9 min ⇒ **≈270 llamadas/día por equipo** (22 h). ±5 % exige **2 equipos** (o uno más potente); ±7 % cabe en uno.
- Para caber en 2 h la persona solo decide **excepciones**: meta ≤25 % de la muestra a ≈1,5 min cada una (≈1,9 h). **Riesgo:** en las 14 pruebas casi todas las llamadas dejaron algún criterio pendiente; bajar ese % es el trabajo principal del piloto.
- **Por construir:** selección aleatoria estratificada (asesor × franja horaria) de la muestra y cola de excepciones ordenada para la sesión de 2 h.
- **Tres escenarios definidos por el usuario** (presentación, diapositiva 4): (1) manual, **10 min/llamada** ⇒ 51 h para 306; (2) la persona descarga cada llamada (**3 min**) y la carga en la app, luego valida excepciones ⇒ 3,4 min/llamada ⇒ 17,2 h (la descarga manual es el cuello de botella); (3) la app **conectada al sistema de grabaciones** descarga sola y la persona solo valida excepciones ⇒ ≈1,9 h. Solo el 3 cabe en 2 h. El escenario 3 requiere acceso de lectura de TI a las grabaciones de la central (Asterisk) — **por construir**; hoy funciona el 2.

### 16.7 Llamadas cortadas/incompletas y descarte automático (2026-10-06)

- **Descarte manual:** el auditor marca «cortada» o «incompleta» (`review.discard`); la llamada no se audita, no cuenta en notas/pendientes y va a la hoja «Descartadas» del Excel. `discard: "ninguna"` anula una marca automática (la decisión humana siempre gana; `review.effective_discard`).
- **Regla del usuario (20 s):** `[rules] min_call_seconds = 20` en `settings.toml`; toda llamada con `duration_s < 20` queda con `audit.auto_discard = {value: cortada, source: regla}` (determinista, sin IA).
- **Clasificación por IA (`auditor.classify_completion`):** pregunta si la llamada **finalizó / se cortó / está incompleta** y marca sola las dos últimas (`auto_discard.source = ia`). Salvaguardas: (a) si las reglas ya vieron despedida y se oyen asesor y cliente ⇒ «finalizada» sin gastar IA; (b) cortada/incompleta exige **cita verificada** (≥3 palabras, mismo validador que los criterios): cita inventada ⇒ no se marca y se anota; (c) JSON inválido ⇒ no se marca; (d) siempre reversible desde el detalle («Auditar normal»). Se guarda `audit.completion` (estado, motivo, cita, origen) para trazabilidad. Corre antes de calificar criterios: si la marca, se omite la calificación por IA (ahorra tiempo). Con la IA apagada solo actúa la regla de 20 s.
- **Riesgo conocido:** el 3B ya mostró sesgos (decía «no» a casi todo). Un falso «cortada» oculta una llamada de la auditoría; por eso queda visible como «marcada automáticamente» y se mide en un simulacro sin guardar (ver resultado abajo) antes de confiar en ella a escala.

### 16.8 Reporte operativo: corte septiembre 2026 (2026-10-07)

Entregable de gestión (no es parte del motor de auditoría): `presentacion/Corte_Septiembre_2026.pptx` (12 diapositivas) y `presentacion/Analisis_Corte_Septiembre_2026.xlsx` (tablas de soporte, hoja `0_Supuestos`). Fuentes: `_base_Septiembre_2026_ISSABEL.xlsx` (jun–sep, hoja «base call isasabel») y la presentación de agosto (ene–may).

- **Definiciones validadas contra la presentación anterior:** NDA = contestadas ÷ recibidas (meta Angiografía 89 %, Nueva EPS 92 %). SLA = `ANTES DE 20 SEG` = CUMPLE ÷ recibidas (metas 75 % y 72 %). Abandono = abandonadas ÷ recibidas. Calidad «50 s–5 min» = duración entre 50 y 300 s ÷ contestadas.
- **Trimestres:** T1 = ene–mar (presentación); T2 = abr–may (presentación) + jun (base); T3 = jul–sep (base). La calidad 50 s–5 min solo existe desde junio.
- **Exclusión del sismo (10–12 ago):** reproduce las cifras de la presentación anterior (Angiografía 15.642 recibidas; Nueva EPS 19.726).
- **Chats (pestañas `td VOLUMEN CHAT` y `volumen chat`):** cuentan chats **atendidos**. Septiembre: Nueva EPS atendió 3.600 de 4.559 (79 %). El detalle horario por agente cuadra con la pestaña semanal; el total por agente del encabezado de la pestaña `td` no cuadra y se ignoró (2.613 y 962 para Nueva EPS, no 2.207 y 1.368).
- **Pendiente:** el tiempo promedio por chat (Liliana 14,5 min × 2.361 chats ≈ 570 h en un mes de 208 h) no es compatible con un chat a la vez. Validar la definición antes de fijar metas de capacidad.
- **Chats ene–sep y tipificación (2026-10-07, segunda entrega):** las diapositivas de chat (10–12) ya usan los reportes (3)–(6) de enero a septiembre; las de tipificación salen de `TipificacionAngiografia (6)`, `Tipificacionnuevaeps (6)` y `TipificacionPac (5)`, filtradas a jul–sep. Roles de chat: `COMERCIAL` = Angiografía, `AGENTE` = Nueva EPS, `AGENTE-PLANES-VOLUNTARIOS` = Planes. Las fechas de la tipificación vienen en dos formatos (ISO y día/mes): parsear cada uno por separado. Libro de soporte: `presentacion/Analisis_Chats_Tipificacion.xlsx`.
- **Pendiente de chat:** el reporte (7) asigna solo 1.010 de los 2.391 chats no atendidos de septiembre a una campaña.
- **No rehecho:** diapositivas 7–18 de la versión anterior (IVR, transcripción, trabajo en casa, ROI); sus datos no estaban en los archivos entregados.

### 16.9 Base de reunión por colaborador: casa vs oficina (2026-10-08)

Entregable de gestión: `presentacion/Base_Reunion_Colaboradores_Sep2026.xlsx` (hojas: Leeme, Colaboradores, Casa_vs_Oficina, Config_modalidad, Historico_mensual, Eventos_turnos, Control_datos). Generado con scripts fuera del repo (scratchpad); no forma parte del motor de auditoría.

- **Cruce por nombre, no por código:** los códigos de agente no coinciden entre archivos (p. ej. Karen Vargas 705/715/723; Diana Lozano 799/709). Nombres unificados en el script; variantes registradas en Control_datos.
- **Fuentes:** ISSABEL «base call isasabel» jun–sep (detalle por llamada; fuente principal jun–sep); ISSABEL «promedio 5 min» (ene–sep; fuente de ene–may); reporte de conexión, recesos y tipificación de septiembre. Jun, ago y sep cuadran por agente entre base e histórico; **julio no** (base 46.244 vs histórico 38.824; sin duplicados en la base): se usa la base.
- **Datos casa/oficina:** no hay registro diario. Evidencia: actas de jun–jul en «Núcleo profesional Oficina 11»; formulario «Necesidades de elementos» del 13/08/2026 (24 personas, mesa/silla/diadema); inventario de equipo/VPN/internet sin fecha de corte. Modalidad **propuesta**: oficina ene–jul, agosto «Por definir», casa sep (editable en Config_modalidad).
- **Hallazgo (solo descriptivo, no causal):** junio–julio (oficina) vs septiembre: ≤20 s 70,4 % → 78,9 %; 50 s–5 min 63,5 % → 64,5 %; duración 2,83 → 2,64 min; atendidas por persona-mes ~1.861 (ene–jul) → ~2.136 (sep) sin normalizar por días trabajados. Con 1 mes en casa no es concluyente.
- **Datos sensibles:** los archivos de «colaboradores» y la encuesta de abril traen cédulas, direcciones, fecha de nacimiento y datos de hijos. No se copiaron al entregable. Recomendar no duplicarlos en otras carpetas.
- **Pendientes:** (1) fecha real de inicio del trabajo en casa y si hubo casos mixtos; (2) confirmar si Valeria Perera es la misma persona que Valeria Perea (992 llamadas, sin solapamiento en el mismo minuto); (3) Liliana Pito, Katherine Mosquera, Meiby Araujo, Mery Sánchez y Luisa Villegas: cargos y si deben entrar en la base; (4) fecha de corte del inventario de equipo; (5) Tatiana Sánchez figura «trabajo en IPS» en el inventario: confirmar lugar real.

### 16.10 Evaluación de desempeño 2026: cuadros individuales y correos (2026-10-09)

Entregable de gestión (no es parte del motor de auditoría): `presentacion/Evaluacion_Desempeno_2026/` con `Resultados_Evaluacion_Desempeno_2026.xlsx` (hojas Consolidado, Correos y un cuadro imprimible por colaborador), `correos/*.eml` (26 borradores HTML, `X-Unsent: 1`, sin destinatario) y `generar_resultados.py` (uso: `python -I generar_resultados.py <excel_fuente> <carpeta_salida>`). Fuente: `Downloads/Evaluacion_desempeno_24_colaboradores 2026.xlsx`.

- **26 personas, no 24:** CUESTA ANGULO MARIA JOSE y DIAZ DIAZ ALBA MIREYA tienen notas 2026 pero sin fórmula/valor de promedio en el libro fuente; el promedio se recalcula con la misma regla (promedio de los 32 ítems; ≤9 Competente, >9 Excede).
- **Natalia Valencia:** el ítem 3 está vacío; su promedio 2026 es sobre 31 ítems (igual que hace el Excel fuente).
- **Comparación 2025→2026:** 23 de 26 bajan (rango −0,10 a −0,83); solo Tatiana Sánchez, Valeria Perea y María José Cuesta suben. Con la regla 2026, 21 de los puntajes 2025 serían «Excede»; hoy todos son «Competente». No se verificó si el instrumento 2025 (formulario) es el mismo de 2026.
- **Decisión del usuario (2026-10-09):** se quitó la columna «Variación» de cuadros, consolidado y correos (no exponer la caída generalizada).
- **Cargos confirmados por el usuario (2026-10-09):** Katherine Mosquera y Meiby Araujo = AUXILIAR DE AGENDAMIENTO; Mery Julieth Sánchez = LIDER DE AGENDAMIENTO; las otras 23 = AUXILIAR DE CALL CENTER (sin sufijo IPS/Angiografía). Fijados en el diccionario `CARGOS` del generador; ya no se leen del Excel fuente.
- **Pendiente:** correos electrónicos de los colaboradores (columna en hoja Correos) y la firma de los borradores.

## 17. Registro de decisiones

| Fecha | ID | Decisión | Motivo |
|---|---|---|---|
| 2026-10-05 | D-01 | Costo $0, sistema principal 100 % local; APIs externas solo fallback opcional y apagado por defecto | Requisito + privacidad |
| 2026-10-05 | D-02 | Sin Ollama; LLM local vía llama.cpp (GGUF) | Requisito del usuario |
| 2026-10-05 | D-03 | Procesamiento secuencial con cola persistente | Requisito + estabilidad |
| 2026-10-05 | D-04 | SQLite en vez de PostgreSQL para MVP | Volumen bajo, cero administración |
| 2026-10-05 | D-05 | n8n y Docker fuera del MVP | Complejidad/RAM sin beneficio ahora |
| 2026-10-05 | D-06 | LLM responde sub-checks sí/no con cita literal; puntaje lo calcula código | Reproducibilidad/auditabilidad |
| 2026-10-05 | D-07 | E1: catálogo cerrado; un LLM solo nunca fija 0 %; candidatos → revisión humana | Evitar libertad excesiva del LLM |
| 2026-10-05 | D-08 | Golden set humano obligatorio para validar | Sin él no hay forma de medir calidad |
| 2026-10-05 | D-09 | Modo degradado sin LLM debe existir | Resiliencia ante fallo del LLM/API |
| 2026-10-05 | D-10 | Plataforma: solo Windows 11 Pro nativo; sin Docker/WSL | Decisión del usuario |
| 2026-10-05 | D-11 | Audio mono mezclado confirmado → diarización obligatoria | Dato del usuario |
| 2026-10-05 | D-12 | Sin registro de agenda por ahora; "cita agendada" = el asesor confirma verbalmente y da fecha, hora, dirección, médico, soportes y preparación (si aplica). E1.c redefinido | Decisión del usuario |
| 2026-10-05 | D-14 | Modo lote bajo demanda: sin 24/7, sin watcher, entrega manual de archivos; cola SQLite solo para reanudar | Decisión del usuario |
| 2026-10-05 | D-15 | **Propuesto, sin confirmar:** matriz de aplicabilidad criterio × motivo de llamada (nueva cita / cancelación / información / confirmación); el motivo se clasifica automáticamente | Las 6 muestras tienen motivos distintos |
| 2026-10-05 | D-16 | "Guión" (P1/Z2) = **criterios**, no texto fijo: se evalúan con léxico de variantes + LLM de respaldo, no con coincidencia literal | Aclaración del usuario |
| 2026-10-05 | D-17 | Detectar y recortar el IVR inicial (aviso WhatsApp + política de datos) antes de roles/reglas; registrar su duración | Medido en muestras |
| 2026-10-05 | D-18 | Estado `no_speech` (sin conversación detectable) → sin nota, se informa aparte | Llamada 2072433 |
| 2026-10-05 | D-19 | Se pueden simular llamadas con fallos (autorizado por el usuario) para probar el motor de reglas; las simuladas se marcan `synthetic: true` y **nunca** cuentan como validación del golden set real | Faltan llamadas con fallos reales |
| 2026-10-05 | D-20 | Diarización provisional: sherpa-onnx (segmentación pyannote-3.0 ONNX + titanet_small, k=2). pyannote oficial descartado por token/gated y peso | B2: RTF 0,15, 0,4 GB, offline |
| 2026-10-05 | D-21 | Antes de diarizar: detectar y **excluir audio grabado** (IVR inicial y bucle de hold) por plantilla de texto/repetición; alinear hablante↔palabra a nivel de palabra | B2: el bucle de hold secuestra un cluster |
| 2026-10-05 | D-22 | LLM local: llama.cpp (`llama-server`, GGUF). 3B = respaldo rápido; 7B = calidad pero ≈3 min/llamada y 7,4 GB. Solo para sub-checks ambiguos tras reglas; **validador de citas obligatorio** (ya atrapó citas inventadas). Modelo final pendiente de medir sobre más llamadas | B3 (2 llamadas) |
| 2026-10-05 | D-23 | Diarización sobre-segmentada (`num_clusters=5`), rol por cluster según contenido; un rol con <8 % del habla ⇒ `needs_review` | `eval_clusters.py` |
| 2026-10-05 | D-24 | Fases 0–6 definidas (§16.1); Fase 1 implementada; Fase 2 siguiente | Petición del usuario |
| 2026-10-06 | D-25 | ~~Z2: "algo más" provisionalmente opcional~~ **REVERTIDA el mismo día**: el usuario decidió que "¿algo más?" es **obligatorio** (`z2_algo_mas_required=true`) | Decisión del usuario |
| 2026-10-06 | D-28 | Espera de `1870774` confirmada como real por el usuario (el auditor humano se equivocó); documento del paciente obligatorio también en menores; base maestra de preparaciones adoptada como fuente de sedes/preparación | Decisiones del usuario |
| 2026-10-06 | D-29 | Interfaz = app web local (stdlib, sin frameworks) en 127.0.0.1; nota final = revisión humana + sistema; E1 solo lo confirma un humano | Usuario pidió GUI amigable; D-07 |
| 2026-10-06 | D-31 | Llamadas < 20 s se descartan solas como cortadas; la IA clasifica finalizada/cortada/incompleta y marca sola las dos últimas (con cita verificada, reversible por el auditor) | Usuario |
| 2026-10-06 | D-30 | LLM en lotes ≤4 preguntas con ids tolerantes; JSON inválido ⇒ pendiente (no rompe el lote) | Fallo real: JSON truncado con 10 preguntas |
| 2026-10-06 | D-26 | Criterios que dependen del saludo: ausencia con STT de baja confianza = pendiente (no fallo). Nota final como rango min–max mientras haya pendientes | STT deforma nombres/entidad |
| 2026-10-06 | D-27 | Evidencia por coincidencia aproximada exige texto ≥60 % del tamaño de la frase (bug `partial_ratio`); medico solo en consultas | Revisión con datos reales |
| 2026-10-05 | D-13 | Llamadas entrantes y salientes; entidades: **Angiografía de Occidente** y **Nueva EPS** → `entity.yaml` con perfiles por entidad; roles por contenido, no por "quién habla primero" | Dato del usuario |

*(Agregar filas nuevas aquí cada vez que se decida algo importante. Modelo de STT/LLM/diarización: **sin decidir** hasta el benchmark.)*

## 18. Pendientes y preguntas abiertas

| ID | Pregunta / pendiente |
|---|---|
| P-01 | ~~Linux/Windows~~ **Resuelto: Windows (D-10).** Abierto: ¿el portátil es dedicado y estará encendido 24/7? |
| P-02 | ~~Mono/canales~~ **Resuelto: mono (D-11).** Abierto: ¿carpeta con las muestras y nomenclatura de los nombres de archivo? |
| P-03 | ~~Entrante/saliente~~ **Resuelto: ambas (D-13).** Abierto: ¿el nombre del archivo o algún metadato indica la dirección? |
| P-04 | Entidades: Angiografía de Occidente y Nueva EPS (D-13). Abierto: guion textual de saludo/despedida de **cada** entidad; ¿la rúbrica es idéntica para ambas?; ¿quién es "la entidad" cuando el asesor llama a nombre de Nueva EPS? |
| P-05 | ~~Registro de agenda~~ **Descartado por ahora (D-12).** Se reabre si se quiere detectar citas mal digitadas |
| P-23 | ~~Z2 "algo más"~~ **Resuelto: obligatorio (2026-10-06).** Nota: los auditores humanos de las 6 muestras no lo exigieron en 5 llamadas → conviene recalibrar al equipo humano |
| P-24 | ~~V1 menores~~ **Resuelto: documento del paciente obligatorio.** Abierto: ¿basta pedirlo sin que se vea el número en el texto? (hoy queda "pendiente" si el STT no transcribe los dígitos) |
| P-25 | ~~Espera de `1870774`~~ **Resuelto: era real.** Corregir la nota humana de AUD-001 en G1 (y en el golden set: `tests/golden/auditadas.json`) |
| P-26 | ~~Sedes y preparaciones~~ **Entregado** (`Base_maestra_preparacion_examenes.xlsx`). Abierto: el catálogo es parcial (25 procedimientos; faltan p. ej. radiografía de rodilla, tomografía de cráneo): ¿se ampliará? Hay 14 filas sin sede |
| P-17 | Volumen y duración reales por día (¿promedio 3–4 min como en las muestras o 5–8?) y tamaño típico del lote por sesión |
| P-18 | Significado de las colas `800197` vs `8001971` (¿entidades distintas? ¿Angiografía de Occidente vs Nueva EPS?) y cómo se dice el nombre de cada entidad al contestar (p. ej. "línea Angio") |
| P-19 | ¿Los `.mp3` auditados son conversiones del mismo `.gsm` original o vienen de otra fuente con mejor calidad? ¿Puedes tener el `.gsm` de esas 6? |
| P-20 | Convención de la columna E1 (¿0 = sin error?) y umbral de "Aprobado" |
| P-21 | Corregir fórmula de *Puntaje Máximo* en la plantilla (debe ser 10 fijo) |
| P-22 | Necesito llamadas con **fallos reales** auditados (incluidos G1, G2, C1, C2, P1, P2, Z2 y E1) para poder validar detección |
| P-15 | Catálogo de exámenes de Angiografía de Occidente que requieren preparación (ayuno, contraste, etc.) y de soportes por tipo de examen/EPS |
| P-16 | ¿Los 10 `.gsm` sin auditar pueden ser auditados por el humano que auditó los 6? ¿Dónde está la nota por criterio de esas 6? |
| P-06 | Criterio no aplicable (ej. sin hold): ¿cumple o se excluye? |
| P-07 | P2: ¿cuántas menciones del nombre exige el estándar? |
| P-08 | Z1: ¿qué slots son obligatorios (fecha, hora, especialista, sede, indicaciones)? |
| P-09 | Política de retención: ¿cuánto tiempo guardar GSM y transcripciones? ¿Quién puede verlos? |
| P-10 | Latencia requerida: ¿resultados el mismo día o al día siguiente? |
| P-11 | ¿Hay 30–50 llamadas ya auditadas por humanos y se pueden usar? ¿Con qué nivel de acuerdo humano-humano? |
| P-12 | G1/G2: definición operativa de "hold" y de "agilidad" (¿hay silencios sin anunciar que cuenten?) |
| P-13 | Lista cerrada de errores críticos (E1.d…) acordada con calidad |
| P-14 | Metadatos disponibles (ID asesor, campaña, teléfono, nombre cliente en CRM) |

## 19. Riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Diarización pobre en GSM 8 kHz mono → turnos mal asignados → criterios C1/P1/P2/V1 erróneos | Alta | Alto | Canales separados; role assignment por contenido; confianza → `needs_review` |
| R2 | STT falla en nombres/números/entidad (dígitos de cédula) | Alta | Alto | `initial_prompt`/hotwords, fuzzy match, modelo medium; medir recall de elementos clave |
| R3 | LLM local pequeño poco fiable en español → inconsistencias | Alta | Medio-Alto | Preguntas atómicas, gramática JSON, verificación de citas, mayoría de peso en reglas |
| R4 | Falta de golden set → imposible validar | Media | Muy alto | Exigirlo antes de confiar en el sistema |
| R5 | E1.c (cita mal agendada) no verificable solo con audio | Alta | Alto | Integrar registro de agenda o dejar E1.c a revisión humana |
| R6 | Throttling térmico del portátil | Media | Medio | B4; limitar hilos; ventana nocturna; refrigeración |
| R7 | Alucinaciones de Whisper en silencios/música de hold | Media | Medio | VAD, `condition_on_previous_text=False`, filtros de repetición |
| R8 | Fuga de datos sensibles (APIs externas, robo de equipo, logs) | Media | Muy alto | Local por defecto, cifrado de disco, enmascarado, sin texto en logs |
| R9 | Cuotas de APIs gratuitas cambian | Alta | Bajo (si es solo fallback) | No dependencia; modo degradado |
| R10 | Criterios subjetivos (G2, C1, C2) con baja concordancia humana → "auditoría" cuestionable | Media | Medio | Medir kappa; si es bajo, marcar como "asistido" |

## 20. Instrucciones para futuros agentes / LLM

1. **Lee este archivo completo antes de tocar nada.** Responde al usuario **siempre en español**.
2. **No introduzcas servicios de pago, Ollama ni dependencias de APIs externas en el camino principal.** El sistema debe funcionar offline y sin LLM (modo degradado).
3. **No asumas rendimiento.** Toda cifra de tiempo/RAM es estimación hasta que exista un benchmark en `benchmarks/`. Si midieron algo, actualiza §7 y §10.
4. **No pidas a un LLM lo que se pueda calcular** (timestamps, conteos, regex). El LLM responde sí/no con cita literal; el código calcula la nota.
5. **Nunca dejes que un LLM fije E1 por sí solo.** Usa el catálogo cerrado (§9).
6. **Toda puntuación lleva evidencia verificable** (turno + cita literal + tiempo). Valida que la cita exista.
7. **Versiona todo** lo que afecte resultados: modelo, prompt, rúbrica, reglas, parámetros. Guárdalo en `pipeline` del JSON.
8. **Privacidad:** no imprimas transcripciones en logs, no subas audios/transcripciones a ningún servicio externo ni a control de versiones, no uses datos reales en ejemplos (usa sintéticos).
9. **Cambios de arquitectura:** actualiza §6, §17 (nueva fila) y la fecha en el encabezado en el mismo cambio.
10. **Cuestiona.** Si una decisión previa parece mala, dilo y propón alternativa antes de implementarla; este proyecto prefiere arquitectura crítica a complacencia.
11. No escribas código de implementación hasta que el usuario lo autorice tras los benchmarks B0–B2.

## 21. Próximos pasos

1. Responder las preguntas P-01…P-14 (prioridad: P-02, P-05, P-11, P-01).
2. Reunir 10 `.gsm` de muestra (idealmente anonimizados) y ejecutar B0.
3. Definir y etiquetar el golden set (§11).
4. Ejecutar B1–B4 y decidir modelo de STT, diarización y LLM; registrar en §17.
5. Solo entonces: MVP paso 1.
