# Audios para pruebas

14 llamadas reales del call center (cola 800197), grabadas el 2026-10-19, para probar la app con audio real.

> **Datos personales.** Son grabaciones reales con voces y datos de personas. Solo pueden estar en este repositorio mientras sea **privado**. No las incluyan en el ZIP de la entrega, no las compartan fuera del equipo y bórrenlas cuando terminen las pruebas.

- Los archivos se renombraron a `llamada_01.gsm` … `llamada_14.gsm` (ordenados por hora) para no publicar el número de teléfono que traía el nombre original. La correspondencia con el nombre original se guarda solo fuera del repositorio.
- Formato: GSM 6.10 sin cabecera, 8 kHz mono, como lo graba la central (Asterisk). Cada una dura ~3,3–4,1 min (unos 4,7 MB en total).
- Si la app no abre `.gsm` directamente, conviértanlos a WAV con ffmpeg:

  ```bash
  ffmpeg -f gsm -ar 8000 -ac 1 -i llamada_01.gsm llamada_01.wav
  ```
