# Auditoría de Llamadas — guía rápida

Todo funciona **en este computador, sin internet y sin costo**. Los audios no salen de aquí.

## Cómo usarlo (3 pasos)

1. **Doble clic en `Iniciar_Auditoria.bat`.** Se abre el navegador. No cierre la ventana negra mientras trabaja.
2. **Pestaña 1 — Cargar y analizar:** arrastre los audios (`.gsm`, `.mp3`, `.wav`) y pulse **Analizar**.
   - *Rápido*: menos de 1 min por llamada con la IA · *Preciso*: unos 3 min · *Solo reglas*: lo más veloz, sin IA.
   - Puede dejar el computador trabajando. Si lo apaga, lo ya analizado queda guardado.
3. **Pestaña 2 — Resultados y revisión:** abra cada llamada. Verá la conversación (con el audio), cada criterio con su
   evidencia y la nota. Donde el sistema no estuvo seguro verá **?**: escuche el fragmento (clic en la cita) y decida
   **Cumple / No cumple**. Luego **Guardar revisión**.

   Al guardar, la ventana se cierra sola y la llamada queda resaltada en la lista. Atajo: **Ctrl + S**.
   Al terminar un análisis, **«Revisar esta llamada»** abre directamente la llamada recién analizada (si fueron varias,
   la lista muestra solo esas; «Ver todas las llamadas» quita el filtro).
   **Llamadas cortadas o incompletas:** en el detalle, arriba a la derecha, marque «Llamada cortada» o «Llamada incompleta»
   y guarde. La llamada no se audita, no cuenta en la nota promedio ni en «Para revisar», y sale en la hoja
   «Descartadas» del Excel. Se puede deshacer con «Auditar normal». Filtro en la lista: «Descartadas».
   **Descarte automático:** (1) toda llamada de **menos de 20 segundos** se marca sola como cortada; (2) con la IA activa,
   cada llamada se clasifica como finalizada, cortada o incompleta y las dos últimas se marcan solas, siempre con el motivo
   y una frase de la llamada como prueba. Las marcadas por el sistema se ven como «marcada automáticamente»; si no es
   correcto, abra la llamada, elija **«Auditar normal»** y guarde. Su decisión siempre reemplaza a la del sistema.
   **Buscar:** por ID de llamada, archivo, asesor o tipo, y por **fecha y hora de análisis** (desde / hasta, o los atajos
   «Última hora», «Hoy», «Últimos 7 días»). La columna **Analizada** muestra cuándo se procesó cada llamada.
4. **Pestaña Configuración:** elija el estilo visual (Liquid Glass, Glassmorfismo, Aurora, Neumorfismo, Minimalista,
   Clásico), la paleta de color, modo claro/oscuro, nivel de animaciones, su nombre de auditor y el modo de análisis por defecto.
   Si el equipo se siente lento, ponga las animaciones en **Suaves**.
   El estilo **Corporativo** usa los colores de Angiografía de Occidente (azul #001F78, amarillo #E6B32A, gris #585C5E)
   y el logo. El logo debe estar en `src/llamadas/gui/static/logo-angiografia.png`; sin ese archivo se muestra el ícono.

Cuando termine, **Exportar a Excel** genera la matriz con el mismo formato de su plantilla.

## Cómo leer la pantalla

| Símbolo | Significado |
|---|---|
| ✓ verde | Cumple |
| ✗ rojo | No cumple |
| ? amarillo | El sistema no pudo decidir: **falta su revisión** |
| – gris | No aplica a ese tipo de llamada |
| Círculo con borde azul | Lo decidió usted (reemplaza al sistema) |

- **Nota ≥ 80 % = Aprobado.** Un **error crítico** (E1) solo cuenta si usted lo confirma: entonces la nota es 0 %.
- La nota aparece como **rango** (por ejemplo 70–90 %) mientras haya criterios sin decidir.
- Los mensajes grabados (bienvenida, política de datos, música de espera) se detectan solos y **no se evalúan**.

## Reglas confirmadas por usted
- Preguntar «¿algo más en que le pueda colaborar?» es **obligatorio** (Z2).
- Pedir el documento **del paciente** es obligatorio, también con menores (V1).
- Esperas (hold) de **60 s o más** incumplen G1.
- Las sedes, direcciones y preparaciones salen de `Base_maestra_preparacion_examenes.xlsx` (actualícela y se usa de inmediato).

## Privacidad
- El programa solo escucha en este equipo (`127.0.0.1`). Active **BitLocker** en el disco.
- En cada llamada, el botón **🗑 Eliminar llamada** borra audio, transcripción y resultados.
- Los datos viven en la carpeta `data/` (no la comparta ni la suba a la nube).

## Si algo falla
- *«La IA local no está instalada»*: el sistema sigue con reglas y deja más criterios por revisar.
- Errores de una llamada concreta quedan en `data/errores.log`.
- Detalle técnico completo del proyecto: `CONTEXT.md`.
