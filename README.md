# Monitor de extrusión: Fase 1

Aplicación de escritorio para Windows que corre en el HMI principal de una línea de extrusión.
Verifica parámetros, recetas y ajustes, y muestra las tendencias del proceso en tiempo real.

**Solo lee la pantalla (OCR).** No toca la base de datos ni el PLC, y no modifica el software del fabricante.
Todo se configura desde la propia aplicación: variables, regiones, páginas del HMI y tolerancias.
Por eso sirve para cualquier línea de extrusión.

## Qué hace

| Función | Detalle |
|---|---|
| Lectura en vivo | Captura la pantalla del HMI y lee con OCR las regiones configuradas. Se puede usar el OCR integrado de Windows, plantillas enseñadas o Tesseract. |
| Páginas del HMI | Una imagen ancla (por ejemplo, el título de la pantalla) identifica cada pantalla. Una variable solo se lee cuando su página está visible. |
| Filtros de lectura | Rango válido, salto máximo confirmado en 2 lecturas, confianza mínima, coma o punto decimal y corrección de confusiones típicas del OCR (O→0, l→1…). |
| Recetas | Nominal, tolerancia de aviso y tolerancia de alarma (absoluta o en %) por variable. Cada variable se compara contra la receta o contra la consigna leída del HMI. Las recetas se importan y exportan en CSV (compatible con Excel), y los valores actuales del HMI se pueden tomar como nominales. |
| Selección automática de receta | Si configuras una variable de texto con el nombre de la receta que muestra el HMI, la receta activa se elige sola y se avisa si no coincide. |
| Detección de errores | **Ajuste erróneo**: la consigna difiere de la receta. **Fuera de tolerancia**: el valor real se sale de su tolerancia. **Cambio de ajuste**: registra el valor anterior y el nuevo, e indica si se aleja de la receta. **Fallo de lectura**: la variable no se pudo leer o el dato es viejo. |
| Tendencias / SPC | Pendiente con prueba de significancia, tiempo estimado hasta el límite de alarma, reglas de Nelson sobre subgrupos y Cpk. |
| Anti-falsas alarmas | Confirmación durante N ciclos, histéresis del 10 %, efecto mínimo relativo a la tolerancia y hallazgos que se mantienen mientras la página no está visible. |
| Historial | SQLite propio (`history.sqlite`) con retención de 90 días. Exporta a CSV con una columna por variable. |

## Uso

```
ExtrusionMonitor.exe            # modo normal (lee la pantalla)
ExtrusionMonitor.exe --demo     # HMI simulado de línea de cable con fallas inyectadas
ExtrusionMonitor.exe --autostart
```

Configuración inicial en el HMI:

1. **⚙ Configurar variables → 📷 Capturar pantalla del HMI.** La app se oculta, toma la captura y vuelve.
2. **Páginas del HMI** (solo si el HMI tiene varias pantallas): marca el título de cada pantalla y pulsa *Nueva desde selección*.
3. **Variables:** marca el recuadro del valor y pulsa *Nueva desde selección*. Después define el tipo (real, consigna o texto), la unidad, la consigna asociada y el rango válido.
   Con *Probar OCR* compruebas la lectura. Si usas el motor de plantillas, *Enseñar caracteres…* le enseña la fuente del HMI.
4. **📋 Recetas:** crea la receta con el mismo nombre que muestra el HMI y llena nominales y tolerancias,
   o pulsa *Tomar valores actuales del HMI como nominales* con la máquina en un buen setup.
5. **▶ Iniciar.**

Los datos se guardan en `%LOCALAPPDATA%\ExtrusionMonitor`. Para usar el modo portátil, crea una carpeta `data` junto al `.exe`.

## Construir el .exe

- **Automático:** cada push ejecuta el workflow *Build Windows*, que pasa las pruebas y publica el artefacto `ExtrusionMonitor-windows`.
- **Manual en Windows:** `packaging\build_exe.bat`. El resultado queda en `dist\ExtrusionMonitor\`. Es un modo carpeta: copia la carpeta completa al HMI.

## Desarrollo

```
pip install -e .[dev]
python -m extrusion_monitor --demo
QT_QPA_PLATFORM=offscreen pytest
```

Estructura (`src/extrusion_monitor/`):

- `capture.py`: fuentes de imagen (pantalla, archivo, simulador).
- `ocr/`: motores OCR (`windows`, `template`, `tesseract`), preprocesado y conversión a número.
- `pages.py`: detección de la pantalla del HMI.
- `acquisition.py`: lectura y filtros de plausibilidad.
- `analysis/rules.py` y `analysis/trends.py`: verificación, tendencias y SPC.
- `engine.py`: ciclo de monitoreo en un hilo propio.
- `storage.py`: historial.
- `recipes.py`: recetas.
- `simulator.py`: HMI simulado.
- `ui/`: interfaz PySide6.

## Hoja de ruta

| Fase | Alcance | Estado |
|---|---|---|
| 1 | Verificación de parámetros y recetas, detección de ajustes erróneos, tendencias en tiempo real | **Esta versión** |
| 2 | Auto-ajuste de parámetros (escritura hacia el HMI/PLC con lazos y límites de seguridad) | Pendiente de definir |
| 3 | Auto-setup (cargar y verificar una receta completa y guiar el arranque) | Pendiente |
| 4 | Verificación física con cámaras en puntos críticos | Pendiente |
