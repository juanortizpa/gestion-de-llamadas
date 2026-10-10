# frame.md — diseño del video «Auditoría de Llamadas con IA»

Fuente de marca: estilo «Corporativo» de la app (`src/llamadas/gui/static/style.css`, líneas 71–80 y 387–416).

## Paleta (por rol)

| Rol | Hex | Origen |
|---|---|---|
| Fondo del video | `#071338` | derivado de `--pri` #001F78, oscurecido para que la ventana clara resalte |
| Fondo, glow | `#0B2A8A` (radial, 20–30 %) | `--pri` aclarado |
| Primario (marca) | `#001F78` | `--pri` |
| Acento (foco) | `#E6B32A` | `--acc` |
| Gris marca | `#585C5E` | `--gray` |
| Texto sobre fondo | `#F3F5FB` (blanco tintado) | — |
| Texto atenuado | `#9AA6C8` | — |
| Ventana de la app | `#FFFFFF` papel, `#ECEEF2` barra de pestañas, `#E8ECF8` suave primario | `--gray-bg`, `--pri-soft` |
| Semáforo: cumple | `#1E8E5A` | — |
| Semáforo: no cumple | `#C0392B` | — |
| Semáforo: revisar | `#D68910` | — |

Una sola tinta de acento: el amarillo marca el foco de cada escena (botón, cifra, palabra clave).

## Tipografía

| Rol | Familia | Pesos | Tamaños de video |
|---|---|---|---|
| Títulos cinéticos | Montserrat | 900 / 700 | 96–220 px |
| Interfaz de la app (reconstrucción) | "Segoe UI" (renderiza como Roboto) | 400 / 700 | 22–40 px dentro de la ventana |
| Etiquetas, códigos, metadatos | JetBrains Mono | 400 / 700 | 18–28 px |

## Formas y movimiento

- Ventana de la app: radio 22 px, borde inferior de la barra superior 4 px amarillo, sombra profunda azul.
- Botón primario: azul #001F78 con línea inferior amarilla (igual que la app).
- Easing base: `power3.out` para entradas, `power2.inOut` para cámara, `back.out(1.6)` solo para pops de chips.
- Dirección de las transiciones: hacia la izquierda (push-left) salvo cambios de nivel (zoom).

## Prohibido

- Nombres, documentos o teléfonos reales; códigos reales de asesor.
- Degradados violeta/cian, neón, texto con degradado.
- Texto menor a 18 px; texto visible menos de 2 s.
- Escenas estáticas: la ventana persiste y siempre hay movimiento ambiental leve.
