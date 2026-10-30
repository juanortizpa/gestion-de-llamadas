# Decisiones, datos y línea base

Registro único de la entrega (Momento 2). Aquí está **qué se construyó, por qué, y con qué cifras se sostiene**. Los números salen de `eval/` y se pueden regenerar con un comando (sección 5). Última medición: **2026-10-29** (RAG híbrido: **2026-10-30**).

> Alcance de este documento: arquitectura, decisión sobre RAG y línea base. Son datos **sintéticos** (llamadas inventadas, sin datos personales, hechas con `tests/synthetic/builder.py`): sirven para medir y comparar, **no** reemplazan la validación contra llamadas reales auditadas por humanos (D-19 en `CONTEXT.md` §17).

---

## 1. Línea base (4 cifras)

Medida con **Groq · `openai/gpt-oss-120b`**, la IA configurada en `.env` (`LLM_PROVIDER=groq`). Suite de auditoría: 14 casos dorados × 3 repeticiones = 42 llamadas a la IA, el 2026-10-29 a las 20:11. Asistente: 12 preguntas abiertas con IA, misma corrida. (Esa corrida ya incluye la corrección de las citas `【n】`; la de «llamada cortada» y el reintento ante 429 se hicieron después, ver §4.)

| # | Cifra | Mediana | n | Fecha |
|---|---|---|---|---|
| 1 | **Latencia de la IA por llamada** (auditoría) | **0,8 s** (mín. 0,5 · p90 1,1 · máx. 1,5) | 42 llamadas | 2026-10-29 |
| 2 | El README decía que el repositorio es privado | Ambos | **Corregido** el 2026-10-29 (entonces era público). Desde el 2026-10-30 el repositorio **sí es privado** porque contiene `audios/` con llamadas reales; el README lo explica y dice cómo autenticarse |
| 3 | **Acierto contra los casos dorados** | **98,3 %** de los criterios (118 de 120); la IA acertó **100 %** de sus respuestas (39 de 39) | 120 criterios por corrida (12 casos × 10) × 3 corridas; mediana de las corridas | 2026-10-29 |
| 4 | **Latencia del Asistente** (pregunta abierta, de la pregunta al final de la respuesta) | **0,62 s** (primer token 0,55 s) | 12 preguntas | 2026-10-29 |

Cifras que acompañan a las cuatro:

| Cifra | Valor |
|---|---|
| Costo estimado por llamada a la IA (mediana) | **US$ 0,000187** (tarifa Groq: US$ 0,15 entrada / 0,60 salida por millón de tokens, consultada el 2026-10-29). La suite completa de 42 llamadas costó **US$ 0,0086** |
| Costo estimado por pregunta del Asistente (mediana) | US$ 0,000198 (≈ 1.180 tokens de entrada y 29 de salida, **estimados**: el streaming no devuelve `usage`) |
| Pregunta del Asistente que se responde sin IA (conteos, rankings, listas) | **5 ms** (mediana, 3 preguntas) |
| Acierto del cierre de la llamada (finalizada / cortada / incompleta) | 92,9 % (39 de 42): fallaba siempre el mismo caso (llamada cortada); corregido después, ver hallazgo 4 |
| Criterios que quedaron pendientes para el humano | 1,7 % (2 de 120): son los dos casos donde la IA dijo «no hay evidencia» y, por diseño, un «no» de la IA nunca fija 0 |

**Cómo se definió «acierto»:** de cada caso se decide *por construcción* qué criterios deben salir 1 y cuáles 0 (p. ej. a la llamada buena se le quita la pregunta «¿necesita algo más?» → Z2 debe salir 0). Un criterio acierta si el sistema (reglas + IA, antes de la revisión humana) da el mismo valor; **un criterio que queda pendiente cuenta como no acertado**. El «acierto de la IA» mide solo lo que la IA respondió: acierta si dijo «sí» con una cita verificada cuando debía, o no encontró evidencia cuando no la había. La nota que ve el usuario siempre pasa además por una persona.

### Comparación con la IA local (misma suite, 1 repetición, medida a las 19:25–19:26, antes de las correcciones de §4)

| Motor | Latencia/llamada | Tokens/llamada | Acierto global | Acierto de la IA | Cierre | Costo |
|---|---|---|---|---|---|---|
| Groq `gpt-oss-120b` (3 rep.) | 0,8 s | 836,5 | 98,3 % | 100 % | 92,9 % | US$ 0,000187 / llamada |
| Local Qwen2.5-**7B** Q4 (RTX 3050 6 GB) | 2,5 s | 579 | 98,3 % | 100 % (13 de 13) | 85,7 % | US$ 0 |
| Local Qwen2.5-**3B** Q4 (RTX 3050 6 GB) | 0,9 s | 558 | 95,0 % | 69,2 % (9 de 13) | 85,7 % | US$ 0 |

El 3B inventó una cita en un caso y el validador la descartó (`cita_inventada_descartada`): es exactamente para eso que existe. Con una sola repetición y 13 respuestas por modelo, las diferencias pequeñas **no son concluyentes**; la de 3B frente al resto sí es clara.

---

## 2. Arquitectura y dónde interviene la IA

Aplicación web local (Python, solo biblioteca estándar en el servidor: `http.server`) en `127.0.0.1`. Las llamadas se procesan por lotes secuenciales y reanudables; los datos viven en archivos y SQLite dentro de `data/` (fuera de git).

```
audio (.gsm/.mp3/.wav)
  → ffmpeg → STT faster-whisper large-v3 (GPU/CPU)          código + modelo de voz, no es un LLM
  → detección de audio grabado (IVR, hold) + diarización     código (sherpa-onnx), roles por contenido
  → REGLAS deterministas por criterio (10 criterios)         código: léxicos, tiempos, catálogo de exámenes
        │ lo que quede en duda (sub-checks pendientes)
        ▼
  → IA: responde sí/no por sub-check con CITA LITERAL        LLM (aquí y solo aquí, junto con «¿cortó la llamada?»)
  → validador de citas: la cita debe existir en la transcripción   código (rapidfuzz ≥ 88)
  → revisión humana: confirma o corrige; E1 solo lo fija una persona
  → nota final calculada por código

Asistente de consulta (pestaña «Asistente»)
  pregunta → caché → ¿conteo/ranking/lista/ficha? → SQL sobre `calls`     código, sin IA (≈ 6 ms)
                   → si es abierta: búsqueda híbrida (FTS5 + vectores) → 6 fragmentos → LLM con citas [n] → verificación de citas
                   → si la IA no está disponible: se muestran los fragmentos tal cual
```

**Frontera de la IA.** El LLM nunca da una nota. Decide, a lo sumo, un sub-check por vez («¿el asesor comprende la necesidad del cliente?») y debe **citar**; si la cita no está en la transcripción, la respuesta se descarta. Medido: de los 10 criterios, las reglas dejan a la IA solo **C1** (y V2 cuando el asesor no verifica requisitos); los otros 8 se resuelven con código y no gastan IA. Un «no» de la IA no fija 0, solo deja una pista (los modelos pequeños decían «no» a casi todo; D-22).

**Proveedor y modelo.** Los tres motores comparten **la misma interfaz** (`chat_json` / `chat_stream` en `src/llamadas/llm.py`): Groq, Gemini y local (llama.cpp con Qwen2.5 3B/7B). La demo corre con **Groq · `openai/gpt-oss-120b`** (`LLM_PROVIDER=groq` en `.env`) por latencia (0,8 s por llamada frente a 2,5 s del 7B local en una RTX 3050), costo (≈ US$ 0,0002 por llamada auditada; auditar 80 llamadas al día costaría unos US$ 0,015) y fidelidad del JSON/citas (acierto de la IA 100 % frente a 69 % del 3B). El 7B local logró el mismo acierto en esta suite pequeña, a cambio de ser unas 3 veces más lento. El sistema sigue siendo **local por defecto** (D-01): con una API externa los textos de las llamadas **salen del equipo** (Ley 1581), el instalador lo advierte y la elección es del usuario.

**Patrón de integración.** *In-request* con hilo de fondo para el lote (la interfaz consulta el estado), y *streaming* NDJSON para el Asistente (los tokens salen a medida que llegan). No hay colas externas: D-03/D-14, un lote a la vez.

**Fallos que la aplicación maneja** (D-09): IA caída o sin clave → el lote sigue solo con reglas y los criterios quedan pendientes; JSON inválido → ese lote de preguntas queda pendiente sin romper las demás; respuesta de la IA cortada a mitad en el Asistente → se avisa y se muestran las fuentes; límite 429 / clave rechazada / timeout → mensaje legible sin cuerpo de la respuesta ni clave (`RemoteLLM._fail`).

**Trazas visibles.** La pestaña **Trazas** muestra, en vivo, cada llamada a la IA (modelo, segundos, tokens), cuántas citas se aceptaron y cuántas se descartaron por no estar en la transcripción, las consultas del Asistente (por dónde se respondió, fragmentos citados) y los fallos. Se guarda en `data/trazas.jsonl` (`src/llamadas/trace.py`).

---

## 3. Decisión sobre RAG

**Decisión: se usa RAG (búsqueda híbrida por palabras + vectores) solo en el Asistente; la auditoría NO usa RAG.**

**Por qué no en la auditoría.** Una llamada de ~6 min son ~700 tokens de entrada (medido, incluidas las preguntas). Cabe entera en cualquier contexto. Recortarla a fragmentos quitaría contexto justo donde la IA debe citar, y el validador comprueba la cita contra la transcripción completa. Aquí recuperar solo agrega riesgo.

**Por qué sí en el Asistente.** El corpus crece: 80 llamadas/día × ≈ 1.100 tokens (B3, `CONTEXT.md` §10.1) ≈ **88.000 tokens por día de llamadas** (proyección). En el modelo local el contexto es de 8.192 tokens (`settings.toml`): no cabe ni un día. Con RAG el contexto es **constante: 1.181 tokens** (mediana medida, 20 preguntas), sin importar cuántas llamadas haya. Para una pregunta sobre un solo día eso es unas 75 veces menos entrada que pegar todo (88.000 / 1.181, solo entrada, proyección); sobre un mes ya no cabe en 8k ni se justifica pagar 1,9 millones de tokens por pregunta.

**Alternativas descartadas.**
- *Pegar todas las transcripciones en el prompt:* no cabe en el modelo local y es 75× más caro/lento en el externo (cálculo arriba).
- *Solo SQL / sin IA:* se usa para todo lo estructurado (conteos, promedios, rankings, listas), que se responde en 6 ms y sin riesgo de alucinar. No alcanza para «¿qué dicen los clientes cuando…?», que busca contenido de la conversación.
- *Base vectorial externa (pgvector, Qdrant):* innecesaria a esta escala; SQLite con FTS5 + `sqlite-vec` en **un solo archivo** (D-04, D-33) no exige servidor ni Docker.

### Medición del RAG

Corpus sintético: 14 llamadas con temas distintos (claustrofobia, cancelación, horarios, reclamo, preparación de tomografía…), 166 fragmentos. 20 preguntas con la llamada y la frase donde está la respuesta; 12 *directas* (comparten palabras con el texto) y 8 *parafraseadas*. «Correcto» = alguno de los 6 fragmentos devueltos pertenece a la llamada esperada **y contiene la frase** que responde la pregunta.

| Métrica | Solo palabras (FTS5/BM25) · 2026-10-29 | **Híbrido** (FTS5 + vectores `multilingual-e5-small`) · 2026-10-30 |
|---|---|---|
| Llamada correcta en el 1.er resultado | 70 % (14 de 20) | **80 %** (16 de 20) |
| Llamada correcta en los 3 primeros | 75 % | 85 % |
| Llamada correcta entre los 6 devueltos | 85 % | 90 % |
| **Fragmento correcto entre los 6 devueltos** | 80 % (16 de 20) | **90 %** (18 de 20) |
| MRR del fragmento | 0,735 | **0,835** |
| Preguntas directas / parafraseadas (fragmento en top-6) | 83 % / 75 % | **100 %** / 75 % |

**Modo híbrido medido el 2026-10-30 en GitHub Actions** (workflow *Medicion RAG*, `.github/workflows/eval-rag.yml`): baja solo llama.cpp y `multilingual-e5-small` (~180 MB) y corre `python eval/run_eval.py --suite rag --engine ninguna`, sin IA de texto ni claves; mismo corpus y mismas 20 preguntas. Los vectores suben el fragmento correcto en top-6 de 80 % a **90 %** y el MRR de 0,735 a **0,835**, y las preguntas directas llegan a 100 %. Las parafraseadas **no mejoran** (75 %, 6 de 8): los 2 fallos que quedan son parafraseados (detalle por pregunta en el artefacto `eval-rag` de esa corrida). El umbral `min_cosine = 0,80` sigue sin calibrar con datos reales. Con este resultado se mantiene la decisión de usar búsqueda híbrida.

**Qué dicen los fallos de la búsqueda solo por palabras** (4 de 20):
1. *R03 «estacionamiento» y R08 «seguro médico»:* la transcripción dice «parqueadero» y «EPS». No comparten ninguna palabra; es el caso para el que sirven los vectores y es la razón de mantener el modo híbrido.
2. *R06 «preparación…» y R04 «esperar dos horas»:* el enrutador interpreta «preparación» como el criterio Z1 y «esperar» como G1 y **sube la puntuación** de los fragmentos de criterio de *todas* las llamadas (×1,4), que desplazan a la transcripción donde está la respuesta. Es un defecto real del Asistente que esta medición dejó a la vista. Sigue sin corregir.

**Límites de esta cifra.** 14 llamadas y 20 preguntas son una muestra pequeña (cada pregunta pesa 5 puntos) y con pocos distractores: con cientos de llamadas reales el resultado será peor, no mejor. Sirve como línea base para comparar cambios, no como promesa de calidad en producción.

---

## 4. Hallazgos de la medición

1. **La IA interviene poco, y eso es lo diseñado.** En 12 de los 14 casos lo único que las reglas dejan a la IA es C1 (9 de 10 criterios se resuelven con código). La IA no se usa «porque sí»: se usa donde el código no puede decidir.
2. **El validador de citas funciona.** El 3B local inventó una cita y fue descartada. Con Groq, 33 respuestas «sí» llevaron cita verificada y ninguna fue descartada.
3. **Citas `【1】` del Asistente: corregido.** `gpt-oss` escribe las citas con corchetes de ancho completo y el verificador solo reconocía `[1]`: avisaba «no cita ningún fragmento» aunque sí citó. `ChatEngine.verify` ahora las normaliza a `[1]` (y quita las que apuntan a un fragmento inexistente). Medido: respuestas con la llamada correcta citada **75 % → 83,3 %** (ya igual al conteo aceptando ambos formatos).
4. **Llamada cortada a media frase: corregido.** Había dos causas: (a) la regla de despedida daba por buena una despedida **a mitad de llamada** (un «con gusto, señora» en el turno 3) y saltaba la consulta a la IA; ahora la despedida solo vale si está en los últimos 3 turnos y la llamada no termina sin punto final; (b) a la IA no se le decía que la última frase quedó abierta, y ahora el prompt lo incluye. Resultado en el caso `A13_cortada`: antes «finalizada» en 3 de 3 corridas; ahora `cortada`, con la cita de la última frase verificada (probado con una llamada real a Groq; la suite completa **no se pudo repetir** por la cuota diaria, ver hallazgo 5). Hay pruebas unitarias (`tests/unit/test_defectos_demo.py`).
5. **Límites de Groq (429): reintento añadido, y una advertencia para la demo.** `RemoteLLM` ahora reintenta ante un 429 con espera creciente (4 s, 8 s; `retries` y `retry_wait_s` en `settings.toml`). Si el proveedor pide esperar más de 20 s no reintenta, porque es una cuota agotada, y lo dice: «La API externa agotó su cuota (429): vuelve a estar disponible en unos N min». Esto no es teórico: **el plan gratuito de Groq permite 200.000 tokens por día para este modelo y la propia evaluación lo agotó** (≈ 35.000 tokens por corrida completa de auditoría, más las pruebas). **Para la demo hay que llegar con la cuota intacta** (o con la IA local como respaldo): no repetir la suite el mismo día. Antes de este cambio, con 1 s de pausa entre casos hubo 16 respuestas 429 en 42 llamadas; con 4 s, ninguna.
6. **Tokens del Asistente estimados.** El streaming no devuelve `usage`; se estima con 3,6 caracteres por token. Los tokens de la auditoría sí son los reales que informa el proveedor.

---

## 5. Cómo reproducir

```bash
python eval/run_eval.py                         # auditoría + RAG + Asistente con la IA de .env (≈ US$ 0,01)
python eval/run_eval.py --suite rag             # solo la búsqueda: no gasta IA ni necesita clave
python eval/run_eval.py --engine local --mode preciso --reps 1
python eval/run_eval.py --pause 4               # si el proveedor responde 429
```

- **Casos dorados:** `eval/casos.py` (14 de auditoría, 14 llamadas y 20 preguntas de RAG), armados con `tests/synthetic/builder.py`. Lo esperado de cada caso se fija por construcción, nunca mirando lo que responde el sistema.
- **Resultados:** `eval/resultados/AAAA-MM-DD_HHMM_<motor>_<modelo>_detalle.csv` (una fila por llamada a la IA, criterio y pregunta), `resumen.csv` (acumulado con fecha) y `linea_base.json`.
- **RAG híbrido sin instalar nada:** en GitHub, *Actions → Medicion RAG → Run workflow*; el resultado sale en el resumen del job.
- **Precios:** `eval/precios.toml`. Si se cambia de modelo, agregar su tarifa.
- Todo se calcula en un directorio temporal; no toca `data/` ni las llamadas reales.

---

## 6. Prueba del compañero (reproducibilidad)

Regla de la entrega: otra persona descarga el proyecto, sigue **solo el README** y la aplicación debe arrancar. Se hicieron dos pruebas el 2026-10-29 con la versión de `main` de ese día, en modo **local** (Qwen2.5-3B, modo Rápido), con un audio sintético propio. No se entregó nada aparte del enlace al repositorio.

| | Prueba 1 (ensayo previo) | Prueba 2 (compañero) |
|---|---|---|
| Quién | Un agente de IA en el portátil de Harold, siguiendo solo el README | Daniel Barco en su equipo, con ayuda de un asistente de IA que siguió el README |
| Equipo | Windows 11 Home · Intel i5-1035G1 · 7,8 GB de RAM · NVIDIA MX330 de 2 GB | macOS 26.5 · Apple M1 · 8 GB de RAM |
| Python | No estaba: `winget install --id Python.Python.3.12 -e` (3.12.10) | Ya estaba (3.12, Homebrew) |
| Código | ZIP de GitHub (sin Git) | `git clone`, sin cuenta |
| Arranque | `python iniciar.py` | `./run.sh` |
| Menú | 1 Local · Preciso: no · búsqueda semántica: sí | Igual |
| **¿Levantó?** | **Sí** | **Sí** |

| Tramo | Windows | Mac |
|---|---|---|
| A. Del README al inicio de la descarga | 9 min 22 s (Python ~2 min, pip ~3,5 min) | 2 min 10 s (`.venv` y dependencias ~1 min) |
| B. Descarga de modelos | 12 min 22 s | 2 min 53 s |
| C. Fin de la descarga → aplicación abierta | ~20 s | ~2 s |
| **Total hasta ver la aplicación** | **~22 min** | **~5 min** |
| Analizar una llamada (Rápido) | 17 min 31 s para 36 s de audio (~11 min sin la descarga oculta del hallazgo 1) | 9 min 33 s para 87 s de audio (transcripción ~5 min, IA 25,7 s) |
| Pestaña Trazas | qwen2.5-3b · local · 263,9 s · 507 → 58 tokens, y 14,7 s · 419 → 60 tokens | qwen2.5-3b · local · 25,7 s · 629 → 33 tokens |

**Frente a la regla de 5 minutos:** en el Mac, con Python ya instalado, se cumple justo (~5 min). En el portátil Windows solo con CPU no: instalar Python y descargar los modelos con una conexión lenta se llevan casi todo el tiempo. La aplicación en sí arranca en segundos en los dos.

### Qué encontraron y qué se hizo

| # | Hallazgo | Dónde | Estado |
|---|---|---|---|
| 1 | El instalador bajaba Whisper `medium`, pero la aplicación usa `large-v3` (`settings.toml`): el primer análisis descargaba 2,9 GB sin avisar y necesitaba internet, aunque el README promete «sin internet al usar» | Windows (confirmado); Mac (aviso de HF Hub durante el análisis) | **Corregido:** `scripts/descargar_modelos.py` baja el modelo de `settings.toml`; tamaños reales en el menú y el README (~5 GB local, ~3,2 GB solo voz) |
| 2 | El README decía que el repositorio es privado | Ambos | **Corregido:** es público |
| 3 | El ZIP no se descomprimía por el límite de 260 caracteres de las rutas de Windows | Windows | **Documentado:** ruta corta (`C:\gdl`) en el inicio rápido y en Problemas frecuentes |
| 4 | No decía cómo descargar el proyecto | Windows | **Corregido:** Download ZIP o `git clone` |
| 5 | Instalar Python: winget solo aparecía en la sección manual; `python` abría la Microsoft Store; en macOS el comando es `python3` | Ambos | **Corregido** en el inicio rápido |
| 6 | Dos preguntas del menú sin documentar | Ambos | **Corregido:** tabla con los valores por defecto |
| 7 | La descarga de Qwen (~2 GB) no muestra progreso y parece colgada | Mac | **Corregido:** `descargar_modelos.py` muestra el porcentaje en todas las descargas; Qwen se baja con la misma función |
| 8 | «Menos de 1 min por llamada» no se cumple en CPU | Ambos | **Corregido:** tiempos medidos en el README, y la tarjeta *Rápido* aclara que el minuto es de la IA y que sin GPU la transcripción tarda más |
| 9 | `Iniciar.bat` e `Iniciar_Auditoria.bat` sin explicar; «Uso diario» solo para Windows | Ambos | **Corregido:** son el mismo lanzador; se añadió `./run.sh` |
| 10 | Los contadores de Resultados marcan 0 con 1 llamada «Para revisar» | Mac | **Corregido:** los números se animan con `requestAnimationFrame`; si el navegador pausa la animación (pestaña en segundo plano) se quedaban en el primer cuadro, 0. Ahora siempre queda el valor final. Causa deducida del código: no se reprodujo en el Mac |
| 11 | La GPU NVIDIA no se usó: el instalador baja llama.cpp para CPU | Windows | **Documentado:** el README explica cómo poner llama.cpp con CUDA en `models/llm/llama-cuda/` (la aplicación ya la prefiere si existe). No se automatizó en el instalador porque no se pudo verificar en un equipo con GPU |

**Resultado de la auditoría con el audio sintético:** las dos llamadas quedaron como «Motivo sin identificar», y en el Mac P1 (saludo) salió 0 aunque la asesora dijo la entidad y su nombre. Con voces sintéticas (en Windows solo había una voz en inglés) esto no mide la calidad del sistema; la calidad se mide en §1 con los casos dorados.

**Límites de la prueba.** Las dos se hicieron con apoyo de un asistente de IA que leyó el README y manejó la consola, y el audio se cargó con un script porque el asistente no puede arrastrar archivos. Demuestran que el README basta para instalar y usar la aplicación en dos sistemas operativos distintos; no miden la usabilidad para un auditor sin experiencia técnica.

---

## 7. Por qué no hay agente (para la sustentación)

La rúbrica evalúa un agente con herramientas propias, límites activos y una capa de proveedor desacoplada. **La decisión del equipo es no usar un bucle de agente**, y esta es la justificación, con evidencia:

1. **La tarea es fija.** Cada llamada se evalúa contra los mismos 10 criterios de la matriz, siempre en el mismo orden: transcribir → reglas → IA solo en lo dudoso → revisión humana. No hay que decidir «qué hacer a continuación». Un agente que elige herramientas agregaría pasos y variabilidad sin ganar nada.
2. **Lo medido lo respalda.** 8 de los 10 criterios se resuelven con código (§2). La IA responde sub-checks concretos con cita verificada, en 0,8 s y ~840 tokens por llamada (§1). Un bucle de agente multiplicaría las consultas y el costo, y abriría la puerta a respuestas sin cita.
3. **El «bucle ciego» no puede ocurrir.** Las consultas a la IA están acotadas de antemano: lotes de a lo sumo 4 preguntas sobre una lista fija de sub-checks (`auditor.py`). No hay ciclo que pueda repetirse sin fin.
4. **Trazabilidad con datos sensibles.** Con el flujo determinista, cada nota se explica por la regla o la cita que la produjo, y una persona la confirma. Cada paso que decide un modelo sería un paso más que auditar.

**Lo que sí cumple de la dimensión «agente»:**

| Exigencia de la rúbrica | Cómo se cumple | Dónde |
|---|---|---|
| Herramientas propias | Reglas por criterio, validador de citas, enrutador del Asistente (conteos y listas con SQL, sin IA) y búsqueda híbrida: funciones propias que la IA no reemplaza | `src/llamadas/rules/`, `auditor.py`, `chat/` |
| Límites activos | (1) consultas acotadas: lotes de ≤ 4 preguntas; (2) timeout de 60 s por petición externa y 180 s para arrancar la IA local; (3) tope de tokens: 900 en la auditoría, 350 por respuesta y 1.100 de contexto en el Asistente; (4) máximo 2 reintentos ante 429 y ninguno si la cuota está agotada. Además, una persona confirma cada nota | `config/settings.toml`, `llm.py` |
| Capa de proveedor desacoplada | Groq, Gemini y llama.cpp local con el mismo contrato (`chat_json` / `chat_stream`); se cambia con `LLM_PROVIDER` en `.env`, sin tocar código | `src/llamadas/llm.py` (`make_llm`) |
| Fallos sin traza | Timeout, JSON inválido, API caída, 401/403/429 y falta de clave: mensaje legible sin cuerpo de la respuesta ni clave, con pruebas automáticas | `RemoteLLM._fail`, `tests/unit/test_fallos_ia.py` |

**Si preguntan «¿cuándo sí usarían un agente?»:** cuando la tarea deje de ser fija. Por ejemplo, un Asistente que además de responder tenga que consultar otros sistemas (agenda, PQRS) y decidir en qué orden. Hoy esa elección la resuelve el enrutador con reglas, porque las rutas posibles son pocas y conocidas.
