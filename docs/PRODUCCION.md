# Preparación para producción

Lista de verificación antes de publicar una versión estable (`vX.Y.Z` en `main`). Lo marcado ya está hecho en
el código; lo demás necesita una decisión o una prueba en la planta.

## Hecho

### Historial (SQLite)
- [x] Índices: `samples(var, ts)`, `events(ts)`, `oee(ts)`, `problems(start)`. Las consultas de tendencias,
      SPC y análisis usan el índice (≈1 ms por variable y hora con 20 millones de filas).
- [x] La purga horaria ya no recorre toda la tabla: borra por bloques de `rowid` y suelta el candado entre
      bloques. Antes, con 90 días de datos, detenía el monitoreo unos segundos cada hora.
- [x] Exportar el historial completo consulta variable por variable con el índice: el tiempo depende del
      periodo pedido, no del tamaño de la base.
- [x] Plazo configurable («Configuración › Guardado de datos»): 3 meses, 6 meses (por defecto), 1 año o
      indefinido. Con lectura cada 2 s y ~50 variables el historial crece ~100 MB por día (≈18 GB en 6 meses):
      la ventana muestra lo que ocupa y cuánto crece en esa PC.
- [x] Versión 0.3.0.

### Archivos y respaldos
- [x] Escritura atómica con `fsync` de la configuración y el estado: un apagón no deja el archivo vacío.
- [x] Si `config.json` está dañado, se aparta (`config.dañado-<fecha>.json`) y se recupera del respaldo más
      reciente que sea válido; al abrir se avisa.
- [x] «Archivo › Restaurar respaldo…» (con sesión de supervisor): se aplica al volver a abrir el programa,
      respaldando antes lo actual.

### Errores y registro
- [x] Registro con rotación (`app.log` / `fleet.log`, 5 MB × 5).
- [x] Las excepciones no atrapadas (botones, temporizadores, hilos) quedan en el registro; un cierre abrupto
      de bajo nivel deja su rastro en `app-fallo.log`.
- [x] Si el programa no puede abrir, lo dice en una ventana con la ruta del registro.

### Seguridad
- [x] Contraseñas de personal con PBKDF2-SHA256; contraseñas y tokens de notificaciones con DPAPI. En Windows,
      si DPAPI falla, el secreto **no se guarda** (antes se guardaba en base64, legible).
- [x] El dashboard no muestra la ruta de la carpeta compartida.

### Código
- [x] Sin nombres indefinidos ni imports sin usar (`ruff check --select F,E9`), sin código muerto conocido.
- [x] Traducciones: todo `tr("…")` tiene su traducción; sin claves repetidas; reporte PDF, notificaciones y
      conclusiones en el idioma de la interfaz (pruebas en `tests/test_i18n.py`).

## Pendiente (decidir o probar en planta)

1. **Ejecutable de Windows.** Agregar icono y datos de versión (Propiedades › Detalles) en el `.spec`, y
   firmar el ejecutable con un certificado de código para evitar avisos de SmartScreen / antivirus.
2. **CI.** Agregar `ruff check --select F,E9` al flujo de GitHub Actions para que no regresen referencias rotas.
3. **Prueba de resistencia en la PC del HMI** (24–72 h): memoria estable, tamaño del registro y del historial,
   OCR de Windows, DPAPI, carpeta compartida en red y reconexión tras cortes de red o de energía.
4. **Minitab.** Confirmar con la versión y la configuración regional de la planta que las fechas
   `AAAA-MM-DD hh:mm:ss` se reconocen como fecha al pegar.
