# Decisiones, datos y línea base

Registro único de la entrega (Momento 2). Aquí está **qué se construyó, por qué, y con qué cifras se sostiene**. Los números salen de `eval/` y se pueden regenerar con un comando (sección 5). Última medición: **2026-10-29**.

> Alcance de este documento: arquitectura, decisión sobre RAG y línea base. Son datos **sintéticos** (llamadas inventadas, sin datos personales, hechas con `tests/synthetic/builder.py`): sirven para medir y comparar, **no** reemplazan la validación contra llamadas reales auditadas por humanos (D-19 en `CONTEXT.md` §17).

---

## 1. Línea base (4 cifras)

Medida con **Groq · `openai/gpt-oss-120b`**, la IA configurada en `.env` (`LLM_PROVIDER=groq`). Suite de auditoría: 14 casos dorados × 3 repeticiones = 42 llamadas a la IA, el 2026-10-29 a las 19:25. Asistente: 12 preguntas abiertas con IA, misma fecha y hora.

| # | Cifra | Mediana | n | Fecha |
|---|---|---|---|---|
| 1 | **Latencia de la IA por llamada** (auditoría) | **0,8 s** (mín. 0,5 · p90 1,1 · máx. 1,4) | 42 llamadas | 2026-10-29 |
| 2 | **Tokens por llamada** (entrada + salida) | **834** (697 entrada + 135,5 salida; rango 664–1.231) | 42 llamadas | 2026-10-29 |
| 3 | **Acierto contra los casos dorados** | **98,3 %** de los criterios (118 de 120); la IA acertó **100 %** de sus respuestas (39 de 39) | 120 criterios por corrida (12 casos × 10) × 3 corridas; mediana de las corridas | 2026-10-29 |
| 4 | **Latencia del Asistente** (pregunta abierta, de la pregunta al final de la respuesta) | **0,60 s** (primer token 0,55 s) | 12 preguntas | 2026-10-29 |

Cifras que acompañan a las cuatro:

| Cifra | Valor |
|---|---|
| Costo estimado por llamada a la IA (mediana) | **US$ 0,000184** (tarifa Groq: US$ 0,15 entrada / 0,60 salida por millón de tokens, consultada el 2026-10-29). La suite completa de 42 llamadas costó **US$ 0,0088** |
| Costo estimado por pregunta del Asistente (mediana) | US$ 0,000198 (≈ 1.180 tokens de entrada y 29 de salida, **estimados**: el streaming no devuelve `usage`) |
| Pregunta del Asistente que se responde sin IA (conteos, rankings, listas) | **6 ms** (mediana, 3 preguntas) |
| Acierto del cierre de la llamada (finalizada / cortada / incompleta) | 92,9 % (39 de 42): falla siempre el mismo caso, ver hallazgo 4 |
| Criterios que quedaron pendientes para el humano | 1,7 % (2 de 120): son los dos casos donde la IA dijo «no hay evidencia» y, por diseño, un «no» de la IA nunca fija 0 |

**Cómo se definió «acierto»:** de cada caso se decide *por construcción* qué criterios deben salir 1 y cuáles 0 (p. ej. a la llamada buena se le quita la pregunta «¿necesita algo más?» → Z2 debe salir 0). Un criterio acierta si el sistema (reglas + IA, antes de la revisión humana) da el mismo valor; **un criterio que queda pendiente cuenta como no acertado**. El «acierto de la IA» mide solo lo que la IA respondió: acierta si dijo «sí» con una cita verificada cuando debía, o no encontró evidencia cuando no la había. La nota que ve el usuario siempre pasa además por una persona.

### Comparación con la IA local (misma suite, 1 repetición)

| Motor | Latencia/llamada | Tokens/llamada | Acierto global | Acierto de la IA | Cierre | Costo |
|---|---|---|---|---|---|---|
| Groq `gpt-oss-120b` (3 rep.) | 0,8 s | 834 | 98,3 % | 100 % | 92,9 % | US$ 0,000184 / llamada |
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

| Métrica (solo palabras, FTS5/BM25) | Resultado |
|---|---|
| Llamada correcta en el 1.er resultado | **70 %** (14 de 20) |
| Llamada correcta en los 3 primeros | 75 % |
| Llamada correcta entre los 6 devueltos | **85 %** |
| **Fragmento correcto entre los 6 devueltos** | **80 %** (16 de 20) |
| MRR del fragmento | 0,735 |
| Preguntas directas / parafraseadas (fragmento en top-6) | 83 % / 75 % |

**Las búsquedas vectoriales no se midieron:** el modelo de embeddings `multilingual-e5-small` no está instalado en este equipo, así que la medición corresponde al modo degradado (solo palabras). El script detecta el modelo y, si existe, mide el modo híbrido por sí solo (`scripts/descargar_modelos.py --chat` y luego `python eval/run_eval.py --suite rag`). Está documentado como pendiente, no como resultado.

**Qué dicen los fallos** (4 de 20):
1. *R03 «estacionamiento» y R08 «seguro médico»:* la transcripción dice «parqueadero» y «EPS». No comparten ninguna palabra; es el caso para el que sirven los vectores y es la razón de mantener el modo híbrido.
2. *R06 «preparación…» y R04 «esperar dos horas»:* el enrutador interpreta «preparación» como el criterio Z1 y «esperar» como G1 y **sube la puntuación** de los fragmentos de criterio de *todas* las llamadas (×1,4), que desplazan a la transcripción donde está la respuesta. Es un defecto real del Asistente que esta medición dejó a la vista (hallazgo 3).

**Límites de esta cifra.** 14 llamadas y 20 preguntas son una muestra pequeña (cada pregunta pesa 5 puntos) y con pocos distractores: con cientos de llamadas reales el resultado será peor, no mejor. Sirve como línea base para comparar cambios, no como promesa de calidad en producción.

---

## 4. Hallazgos de la medición

1. **La IA interviene poco, y eso es lo diseñado.** En 12 de los 14 casos lo único que las reglas dejan a la IA es C1 (9 de 10 criterios se resuelven con código). La IA no se usa «porque sí»: se usa donde el código no puede decidir.
2. **El validador de citas funciona.** El 3B local inventó una cita y fue descartada. Con Groq, 33 respuestas «sí» llevaron cita verificada y ninguna fue descartada.
3. **El Asistente pierde una cita válida con `gpt-oss`:** el modelo escribe las citas como `【1】` (corchetes de ancho completo) y el verificador solo reconoce `[1]`; avisa «la respuesta no cita ningún fragmento» aunque sí citó. Respuestas con la llamada correcta citada: **75 %** como las reconoce el producto frente a **83,3 %** aceptando ambos formatos. Arreglo de una línea en `ChatEngine.verify` (normalizar `【n】` → `[n]`); no se tocó por estar fuera del alcance de esta tarea.
4. **«Llamada cortada a media frase» no se detecta** (caso `A13_cortada`, 3 de 3 corridas, y también con 3B y 7B): la IA responde «finalizada». Es el único fallo de cierre con Groq (92,9 %). Pendiente: reforzar `classify_completion` o añadir una regla (última frase sin cierre).
5. **Límite de peticiones (429).** En una corrida previa con solo 1 s de pausa entre casos hubo **16 respuestas 429** en 42 llamadas (cifra de consola, ese CSV no se conservó); con 4 s de pausa, **0**. El script de medición reintenta con espera, pero la aplicación (`RemoteLLM`) **no reintenta**: ante un 429 muestra un mensaje legible y deja los criterios pendientes. Pendiente: reintento con espera exponencial en el proveedor.
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
- **Precios:** `eval/precios.toml`. Si se cambia de modelo, agregar su tarifa.
- Todo se calcula en un directorio temporal; no toca `data/` ni las llamadas reales.
