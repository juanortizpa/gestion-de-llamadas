# Auditoría de llamadas con IA

Audita llamadas de atención al cliente (transcribe, separa asesor/cliente, evalúa la matriz de criterios y
permite revisión humana). **100 % local: sin internet al usar, sin costo, los audios no salen del equipo.**

- Guía de uso para el auditor: [LEEME.md](LEEME.md)
- Detalle técnico y decisiones del proyecto: [CONTEXT.md](CONTEXT.md)
- Video de funcionalidades: [presentacion/Video_Auditoria_IA.mp4](presentacion/Video_Auditoria_IA.mp4)

## Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10/11 (64 bits) | Windows 11 |
| Python | 3.12 | 3.12 |
| RAM | 8 GB | 16 GB (modo Preciso) |
| Disco libre | 8 GB | 15 GB |
| Internet | Solo para la instalación inicial | |

> Los scripts de arranque (`.bat`) y `llama.cpp` están pensados para Windows. En Linux/macOS habría que
> adaptar `Iniciar_Auditoria.bat` y la ruta `server_exe` de `config/settings.toml`.

## Instalación paso a paso (una sola vez)

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

El repositorio es **privado**: necesita una cuenta de GitHub con acceso (Git le pedirá iniciar sesión en el navegador).

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

1. **Local**: descarga los modelos (~3 GB). Sin internet al usar; los audios y textos no salen del equipo. Pensado para empresas que ya tienen servidores o recursos: no hay costo por uso.
2. **APIs externas** (Groq Llama 3.3 70B o Gemini 1.5 Flash): no descarga modelos pesados, pero **los textos de las llamadas se envían al proveedor**. Pide la clave, la guarda en `.env` (local, no se versiona) y prueba la conexión.

Se puede repetir para cambiar de modo. Variables en [.env.example](.env.example). La base del Asistente es SQLite con `sqlite-vec` (búsqueda vectorial en el mismo archivo).

### 4. Descargar los modelos de IA (~3 GB, necesita internet)

Los modelos no están en git por su tamaño.

```powershell
.venv\Scripts\python.exe scripts\descargar_modelos.py
```

Descarga: Whisper *medium* (voz a texto), los modelos de separación de hablantes, `llama.cpp` y Qwen2.5-3B (IA
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

1. Doble clic en **`Iniciar_Auditoria.bat`** (abre `http://127.0.0.1:8765` en el navegador; no cierre la ventana negra).
2. **Cargar y analizar:** arrastre los audios (`.gsm`, `.mp3`, `.wav`) y pulse **Analizar**.
3. **Resultados y revisión:** abra cada llamada, resuelva los criterios con **?** y guarde.
4. **Exportar a Excel:** genera la matriz con el formato de `Matriz_Auditoria_Llamadas plantilla.xlsx`.
5. **Quejas:** registre y haga seguimiento a las quejas de usuarios (prioridad, fecha límite, responsable, estado); el sistema sugiere las llamadas donde el cliente se quejó.

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
data/           (local, ignorado) audios, transcripciones y resultados
models/         (local, ignorado) modelos descargados
```

## Privacidad

- Nunca suba a git audios, transcripciones, `data/`, `models/` ni `config/agents.toml` (ya están en `.gitignore`).
- El servidor solo escucha en `127.0.0.1`. Active BitLocker en el disco.
- El botón **Eliminar llamada** borra audio, transcripción y resultados de esa llamada.

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `ffmpeg no encontrado` | Reinstale con `winget install Gyan.FFmpeg` y abra una PowerShell nueva |
| «La IA local no está instalada» | Falta el paso 4; mientras tanto el sistema funciona solo con reglas |
| `py` o `python` no se reconoce | Cierre y abra PowerShell; si persiste, reinstale Python marcando «Add to PATH» |
| Error de ejecución de scripts en PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Va lento | Cierre otros programas; en Configuración ponga animaciones en «Suaves» y use modo *Rápido* |
| Errores de una llamada concreta | Revise `data/errores.log` |
