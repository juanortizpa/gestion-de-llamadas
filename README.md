# Auditoría de llamadas con IA

Audita llamadas de atención al cliente (transcribe, separa asesor/cliente, evalúa la matriz de criterios y
permite revisión humana). **Local por defecto: sin internet al usar, sin costo, los audios no salen del equipo.**
Opcionalmente puede usar una IA externa (Groq o Gemini): entonces solo los *textos* de las llamadas salen del equipo.

## Inicio rápido: un solo archivo, en cualquier sistema operativo

Solo necesita **Python 3.12 o superior** e internet durante la instalación.

1. **Descargue el proyecto.** En GitHub, botón verde **Code → Download ZIP** y descomprímalo, o con Git: `git clone https://github.com/juanortizpa/gestion-de-llamadas.git`. El repositorio es **privado**: inicie sesión en GitHub con una cuenta que tenga acceso (pídala al equipo). Si `git clone` pide usuario y contraseña, use `gh auth login` (GitHub CLI) o un token personal en lugar de la contraseña.
   En Windows descomprímalo en una **ruta corta** (por ejemplo `C:\gdl`): dentro de `Descargas\...\gestion-de-llamadas-main\` algunas rutas pasan el límite de 260 caracteres de Windows y la descompresión falla.
2. **Instale Python si no lo tiene:**
   - Windows: `winget install --id Python.Python.3.12 -e` o [python.org](https://www.python.org/downloads/) (marque «Add python.exe to PATH»). Si al escribir `python` se abre la Microsoft Store, Python no está instalado: es solo un acceso directo de Windows.
   - macOS: `brew install python@3.12` o [python.org](https://www.python.org/downloads/). En macOS el comando es `python3`.
   - Ubuntu/Debian: `sudo apt install python3.12 python3.12-venv`.
3. **Ejecute el lanzador** dentro de la carpeta del proyecto:

| Sistema | Qué ejecutar |
|---|---|
| Windows | doble clic en **`Iniciar.bat`** |
| macOS / Linux | `./run.sh` (si no es ejecutable: `sh run.sh`) |
| Cualquiera | `python iniciar.py` (macOS/Linux: `python3 iniciar.py`) |

La **primera vez** el lanzador crea el entorno en `.venv/`, instala las dependencias (incluido ffmpeg, no hace falta instalarlo aparte)
y muestra el **menú de instalación**: IA **local** (descarga los modelos, ~5 GB) o **APIs externas** (descarga solo los modelos de voz,
~3,2 GB, y pide su clave). Las siguientes veces abre el programa directamente. Para cambiar de modo: `python iniciar.py --instalar`
(o `Instalar.bat`). Otras opciones: `--solo-preparar` (prepara y sale), `--puerto 9000`.

**Preguntas del menú** (Enter acepta el valor por defecto):

| Pregunta | Por defecto | Qué hace |
|---|---|---|
| `Elija una opcion [1-3]` | — | 1 = IA local, 2 = APIs externas (Groq o Gemini), 3 = salir |
| `¿Incluir modo Preciso (+4,5 GB, ...)? [s/N]` | No | Baja Qwen2.5-7B. Solo conviene con 16 GB de RAM |
| `¿Incluir busqueda semantica del Asistente (+150 MB)? [S/n]` | Sí | Modelo de embeddings para que el Asistente busque por significado |

Cada descarga muestra su porcentaje de avance; la de Qwen2.5-3B (~2 GB) puede tardar varios minutos con una conexión lenta. Al terminar, el programa se abre solo en `http://127.0.0.1:8765`.

**Cuánto tarda** (prueba del compañero, 2026-10-29; detalle en [docs/decisiones.md](docs/decisiones.md) §6):

| Equipo | De leer el README a ver la app | Analizar una llamada (modo Rápido) |
|---|---|---|
| Mac M1, 8 GB, Python ya instalado | ~5 min | 9,5 min para 87 s de audio |
| Windows, i5-1035G1, 8 GB, solo CPU, sin Python | ~22 min | ~11 min para 36 s de audio |

Sin GPU NVIDIA casi todo ese tiempo es la transcripción (Whisper large-v3 en CPU); la IA local suma entre 25 s y 4 min. La tarjeta *Rápido* lo aclara: el «menos de 1 min» es solo la IA; sin GPU la transcripción tarda más.

En Linux de Debian/Ubuntu puede hacer falta `sudo apt install python3-venv`. La parte local de la IA usa los binarios de
llama.cpp de cada sistema (Windows, macOS y Linux, x64 y arm64), que el instalador baja solo. Los pasos manuales de más abajo
quedan como alternativa para quien prefiera instalar a mano.

- Guía de uso para el auditor: [LEEME.md](LEEME.md)
- Detalle técnico y decisiones del proyecto: [CONTEXT.md](CONTEXT.md)
- Decisiones de la entrega, línea base y medición: [docs/decisiones.md](docs/decisiones.md) · casos de prueba en [eval/](eval/)
- Video de funcionalidades: [presentacion/Video_Auditoria_IA.mp4](presentacion/Video_Auditoria_IA.mp4)

## Inteligencia artificial: modelos, proveedor y por qué no usamos un agente

**No usamos un agente (bucle con herramientas) porque el problema no lo necesita.** El sistema está pensado para montarse en **infraestructura local** (el servidor o equipo de la entidad), sin costo por uso y sin que los audios salgan de ahí. La tarea es fija y conocida (los mismos 10 criterios de la matriz), así que el flujo es determinista:

1. **Código, sin IA:** transcripción (Whisper), separación de hablantes, mensajes grabados, tiempos de espera y reglas por criterio.
2. **IA, solo para lo ambiguo:** el modelo responde sí/no con una **cita literal** a los sub-criterios que las reglas no pudieron decidir; el código verifica que la cita exista y calcula la nota.
3. **Persona:** el auditor confirma o corrige; el error crítico (E1) solo lo confirma un humano.

En CPU local cada vuelta extra de un agente cuesta 10–60 s (el modelo de 3B lee ~40 tokens/s): un bucle con herramientas haría impredecible el tiempo de un lote de 80 llamadas/día sin mejorar el resultado, porque los pasos ya se conocen. Sin bucle no puede haber un «agente atrapado» gastando tokens: cada llamada hace un número acotado de consultas.

**Modelo de la demo: Groq `openai/gpt-oss-120b`** (`LLM_PROVIDER=groq` en `.env`). Se eligió por latencia (0,8 s por llamada a la IA), costo (≈ US$ 0,0002 por llamada auditada; 80 llamadas al día ≈ US$ 0,015) y fidelidad del JSON y las citas (100 % de las respuestas de la IA correctas en los casos dorados). El sistema sigue siendo **local por defecto**: la API externa es una opción del instalador.

**Modelos disponibles (misma interfaz; se elige en el instalador y en la app: modo Rápido o Preciso):**

| Modo | Modelo | Latencia de la IA por llamada* | Acierto en casos dorados* | Costo | Uso |
|---|---|---|---|---|---|
| Demo (API externa) | Groq `openai/gpt-oss-120b` | 0,8 s | 98,3 % | ≈ US$ 0,0002 / llamada | Demo y equipos sin GPU |
| Rápido (liviano, local) | Qwen2.5-3B-Instruct Q4_K_M (llama.cpp) | 0,9 s | 95,0 % | US$ 0 | Uso diario sin internet |
| Preciso (pesado, local) | Qwen2.5-7B-Instruct Q4_K_M (llama.cpp) | 2,5 s | 98,3 % | US$ 0 | Lotes largos o nocturnos |

\* Medianas de `eval/` del 2026-10-29 con datos sintéticos (Groq: 42 llamadas; locales: 1 repetición en una GPU RTX 3050 de 6 GB). Detalle, costo y metodología en [docs/decisiones.md](docs/decisiones.md). En un equipo **solo con CPU** (i5-8250U, 2026-10-05) el 3B tardó 49–64 s y el 7B 157–199 s por llamada.

**API externa (opcional y gratuita):** la capa de proveedor (`make_llm` en `src/llamadas/llm.py`) permite cambiar a **Groq (`openai/gpt-oss-120b`)** o **Google Gemini (`gemini-1.5-flash`)** con el mismo contrato, usando sus **planes gratuitos** (con límites de uso). Sirve para equipos sin recursos para un modelo local, y es donde podrían correr agentes en el futuro sin costo y sin cargar el equipo. Con API externa **los textos de las llamadas salen del equipo** (el instalador lo advierte). Se configura con `LLM_PROVIDER` y la clave en `.env` (ver [.env.example](.env.example)).

**Base de datos vectorial:** el Asistente usa una **base de datos vectorial** (SQLite con la extensión `sqlite-vec`, en `data/chat/index.db`) para buscar por significado en las llamadas, combinada con búsqueda por palabras (FTS5). No necesita servidor aparte. Por eso **no hay `docker-compose.yml`**: no hay base de datos ni servicios que levantar; todo vive en `data/` (ver [docs/decisiones.md](docs/decisiones.md) §3).

**Límites activos aunque no haya agente:**

| Límite | Dónde |
|---|---|
| Consultas por llamada | Acotadas: lotes de ≤4 preguntas, sin bucle |
| Timeout | 60 s por petición a la API externa; 180 s para que arranque el modelo local |
| Tokens | Máx. 900 por respuesta en la auditoría, 350 en el Asistente, 1.100 de contexto |
| Confirmación | Revisión humana antes de la nota final; E1 solo con confirmación humana |

Además: salida JSON forzada por esquema, temperatura 0 con semilla fija (reproducible) y validador de citas (una cita inventada se descarta y el criterio queda para revisión humana).

**Evidencia y trazas:** la línea base (4 cifras con mediana y fecha), la decisión sobre RAG y su medición están en [docs/decisiones.md](docs/decisiones.md). Los casos dorados y el script de medición están en [eval/](eval/) y se repiten con `python eval/run_eval.py` (`--suite rag` no gasta IA). La pestaña **Trazas** muestra en vivo cada llamada a la IA (modelo, segundos, tokens, citas aceptadas o descartadas) y los fallos.

## Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10/11, macOS o Linux (64 bits) | Windows 11 |
| Python | 3.12 | 3.12 |
| RAM | 8 GB | 16 GB (modo Preciso) |
| Disco libre | 8 GB | 15 GB |
| Internet | Solo para la instalación inicial | |

> Probado a mano en Windows 11 y en macOS (Apple M1, 8 GB; prueba del compañero del 2026-10-29, ver [docs/decisiones.md](docs/decisiones.md) §6).
> En Linux solo corren las pruebas automáticas de GitHub Actions (`.github/workflows/pruebas.yml`).

## Instalación manual paso a paso (alternativa; solo Windows PowerShell)

Abra **PowerShell** y ejecute cada bloque en orden.

### 1. Instalar Git, Python 3.12 y ffmpeg

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id Gyan.FFmpeg -e
```

Cierre y vuelva a abrir PowerShell para que reconozca los programas. Compruebe:

```powershell
git --version
py -3.12 --version
ffmpeg -version
```

### 2. Descargar el proyecto

El repositorio es **privado**: necesita una cuenta de GitHub con acceso (pídala al equipo). En Windows, `git clone` abre el navegador para iniciar sesión.

```powershell
cd $HOME\Desktop
git clone https://github.com/juanortizpa/gestion-de-llamadas.git "GESTION DE LLAMADAS"
cd "GESTION DE LLAMADAS"
```

### 3. Crear el entorno e instalar dependencias

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 3b. Atajo: menú de instalación (pasos 3 a 5 en uno)

Doble clic en **`Instalar.bat`** (crea el entorno si falta) y elija:

1. **Local**: descarga los modelos (~5 GB). Sin internet al usar; los audios y textos no salen del equipo. Pensado para empresas que ya tienen servidores o recursos: no hay costo por uso.
2. **APIs externas** (Groq GPT-OSS 120B o Gemini 1.5 Flash): no descarga modelos pesados, pero **los textos de las llamadas se envían al proveedor**. Pide la clave, la guarda en `.env` (local, no se versiona) y prueba la conexión.

Se puede repetir para cambiar de modo. Variables en [.env.example](.env.example). La base del Asistente es SQLite con `sqlite-vec` (búsqueda vectorial en el mismo archivo).

### 4. Descargar los modelos de IA (~5 GB, necesita internet)

Los modelos no están en git por su tamaño.

```powershell
.venv\Scripts\python.exe scripts\descargar_modelos.py
```

Descarga: Whisper *large-v3* (voz a texto; el modelo que indica `config/settings.toml`), los modelos de separación de hablantes, `llama.cpp` y Qwen2.5-3B (IA
local, modo *Rápido*). Es seguro repetirlo: lo que ya existe no se baja de nuevo.

Para el modo **Preciso** (más lento, ~3 min por llamada, más citas verificables) añada ~4,5 GB:

```powershell
.venv\Scripts\python.exe scripts\descargar_modelos.py --preciso
```

### 5. Configuración local (opcional)

```powershell
Copy-Item config\agents.example.toml config\agents.toml
notepad config\agents.toml
```

Escriba los nombres de los asesores. Ese archivo es privado y no se sube a git.

### 6. Verificar la instalación

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## Uso diario

1. Abra el programa: en Windows, doble clic en **`Iniciar.bat`** (`Iniciar_Auditoria.bat` es el mismo lanzador con el nombre antiguo); en macOS/Linux, `./run.sh`. Se abre `http://127.0.0.1:8765` en el navegador; no cierre la ventana de la consola mientras lo use.
2. **Cargar y analizar:** arrastre los audios (`.gsm`, `.mp3`, `.wav`) y pulse **Analizar**. Para probar hay 14 llamadas en `audios/`.
3. **Resultados y revisión:** abra cada llamada, resuelva los criterios con **?** y guarde.
4. **Exportar a Excel:** genera la matriz con el formato de `Matriz_Auditoria_Llamadas plantilla.xlsx`.
5. **Quejas:** registre y haga seguimiento a las quejas de usuarios (prioridad, fecha límite, responsable, estado); el sistema sugiere las llamadas donde el cliente se quejó.
6. **Trazas:** cada llamada a la IA en vivo (modelo, segundos, tokens, citas aceptadas o descartadas) y los fallos (429, timeout, IA caída).

Los datos (audios, transcripciones, resultados) se guardan en `data/`, que **no** se versiona.

### Línea de comandos (opcional)

```powershell
.venv\Scripts\python.exe -m llamadas gui                     # interfaz gráfica
.venv\Scripts\python.exe -m llamadas transcribe audio.mp3 --show
.venv\Scripts\python.exe -m llamadas audit --detail
.venv\Scripts\python.exe -m llamadas resolve --mode rapido   # IA local sobre criterios pendientes
```


### Asistente de consulta (opcional)

Pestaña **Asistente**: pregunta por conteos, rankings y listas (se calculan sin IA) o por lo que se dijo en las llamadas (busca fragmentos y los resume con la IA local, con fuentes). Sin configurar nada funciona buscando por palabras; para búsqueda semántica descargue el modelo de embeddings (~150 MB) y reindexe:

```powershell
.venv\Scripts\python.exe scripts\descargar_modelos.py --chat
.venv\Scripts\python.exe -m llamadas index          # actualiza el índice (también se hace solo al preguntar)
.venv\Scripts\python.exe -m llamadas chat "¿Qué asesor falla más la despedida?" --debug
```

Detalle y límites (aún sin probar con datos reales) en [CONTEXT.md §16.12](CONTEXT.md).

## Configuración

Todo en `config/`:

| Archivo | Para qué |
|---|---|
| `settings.toml` | Modelos, umbrales de reglas (p. ej. espera ≥ 60 s incumple G1), puerto de la IA, nota mínima 80 % |
| `rubric.toml` | Criterios de la matriz de auditoría |
| `lexicons.toml` | Frases y vocabulario que usan las reglas |
| `agents.toml` | Nombres de asesores (local, no versionado) |

El catálogo de sedes, direcciones y preparaciones sale de `Base_maestra_preparacion_examenes.xlsx` (raíz del proyecto).

## Estructura

```
src/llamadas/   código (audio, stt, diarize, rules/, llm, gui/)
config/         configuración
scripts/        utilidades (descargar_modelos.py, evaluaciones)
benchmarks/     mediciones de modelos
tests/          pruebas
videos/         proyecto fuente del video (HyperFrames)
audios/         14 llamadas reales para pruebas (solo con el repositorio privado)
data/           (local, ignorado) audios, transcripciones y resultados
models/         (local, ignorado) modelos descargados
```

## Privacidad

- Nunca suba a git audios, transcripciones, `data/`, `models/` ni `config/agents.toml` (ya están en `.gitignore`).
- La única excepción es `audios/`: 14 llamadas reales autorizadas para pruebas. Solo pueden estar mientras el repositorio sea **privado** y con acceso del equipo autorizado, y **no van en el ZIP de la entrega** (el «Download ZIP» de GitHub ya las excluye: `export-ignore` en `.gitattributes`).
- El servidor solo escucha en `127.0.0.1`. Active BitLocker en el disco.
- El botón **Eliminar llamada** borra audio, transcripción y resultados de esa llamada.

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `Repository not found` o error 404 al descargar | El repositorio es privado: inicie sesión con una cuenta que tenga acceso o pida al equipo que lo agreguen como colaborador |
| Tengo GPU NVIDIA y la IA local va lenta | El instalador baja llama.cpp para CPU. En Windows, descargue de [los releases de llama.cpp](https://github.com/ggml-org/llama.cpp/releases) `llama-bXXXX-bin-win-cuda-12.4-x64.zip` y `cudart-llama-bin-win-cuda-12.4-x64.zip` y descomprima los dos en `models/llm/llama-cuda/`: la aplicación lo usa sola si existe (así se midieron los modelos locales en la RTX 3050) |
| Falla la descompresión del ZIP («No se puede encontrar una parte de la ruta») | Descomprímalo en una ruta corta, por ejemplo `C:\gdl` |
| Escribir `python` abre la Microsoft Store | Python no está instalado: `winget install --id Python.Python.3.12 -e` |
| macOS/Linux: `python: command not found` | Use `python3 iniciar.py` o `./run.sh` |
| `ffmpeg no encontrado` | Reinstale con `winget install Gyan.FFmpeg` y abra una PowerShell nueva |
| «La IA local no está instalada» | Falta el paso 4; mientras tanto el sistema funciona solo con reglas |
| `py` o `python` no se reconoce | Cierre y abra PowerShell; si persiste, reinstale Python marcando «Add to PATH» |
| Error de ejecución de scripts en PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Va lento | Cierre otros programas; en Configuración ponga animaciones en «Suaves» y use modo *Rápido* |
| Errores de una llamada concreta | Revise `data/errores.log` |
