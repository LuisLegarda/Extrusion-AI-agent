# Monitor de extrusión: Fase 1

**⬇ Descargar para Windows:** [ExtrusionMonitor-windows.zip](https://github.com/LuisLegarda/Extrusion-AI-agent/releases/download/dev/ExtrusionMonitor-windows.zip). Se actualiza con cada push. Descomprime el archivo y ejecuta `ExtrusionMonitor\ExtrusionMonitor.exe`. Para probar sin la máquina, usa `ExtrusionMonitor.exe --demo`.

Aplicación de escritorio para Windows que corre en el HMI principal de una línea de extrusión.
Verifica parámetros, recetas y ajustes, y muestra las tendencias del proceso en tiempo real.

**Solo lee la pantalla (OCR).** No toca la base de datos ni el PLC, y no modifica el software del fabricante.
Todo se configura desde la propia aplicación: variables, regiones, páginas del HMI y tolerancias.
Por eso sirve para cualquier línea de extrusión.

## Qué hace

| Función | Detalle |
|---|---|
| Lectura en vivo | Captura la pantalla del HMI y lee con OCR las regiones configuradas. Se puede usar el OCR integrado de Windows, plantillas enseñadas o Tesseract. |
| Pestañas del HMI | Árbol libre de componente → pestaña → sub-pestaña. Una imagen ancla (forma y color) identifica cada pestaña, y sus variables se leen cuando está visible. |
| Recorrido automático | Macro grabada en vivo que navega por las pestañas con clics verificados, lee cada pantalla y regresa a la principal. |
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
   Se configura pestaña por pestaña: navega en el HMI a la pestaña, captura y define sus variables.
2. **Árbol de pestañas:** el árbol es libre: componente → pestaña → sub-pestaña (p. ej. `EXT1 › Overview`, `EXT1 › Temp.contr.`, `GAS`, `MEAS`).
   - *+ Pestaña / componente* crea un nodo raíz y *+ Sub-pestaña* crea un nodo dentro del seleccionado.
   - El **ancla** es una parte de la pantalla que solo se ve con esa pestaña activa, por ejemplo el botón `EXT1` resaltado en la barra inferior o el botón `Overview` seleccionado.
   - La comparación es de forma y color, así que distingue el botón seleccionado del que no lo está.
   - Un nodo sin ancla es una carpeta: agrupa y es visible cuando su padre lo es.
   - Lo que no tiene pestaña (por ejemplo el encabezado con Synchr., Diameter y Recipe) va en *Siempre visible*.
3. **Variables:** tú indicas qué es consigna y qué es medición; no depende del color.
   - *+ Par consigna / medición*: marcas primero la región de la consigna y después la del valor medido, y quedan vinculadas. En la ventana principal se ven en la misma fila.
   - *+ Medición*, *+ Consigna* y *+ Texto* crean variables sueltas.
   - *Crear serie…* replica las variables seleccionadas con un desplazamiento, por ejemplo Cylinder 1 → Cylinder 2…5 o Head 1 → Head 8. Si antes marcas la posición del segundo elemento, el desplazamiento se calcula solo.
   - *Probar OCR* comprueba la lectura. *Quitar marco del campo* elimina el recuadro de los campos del HMI.
   - Si usas el motor de plantillas, *Enseñar caracteres…* le enseña la fuente del HMI.
   - Marca solo el número. Si la unidad está dentro del recuadro (`300 °C`), se ignora, pero es mejor dejarla fuera.
4. **Recorrido automático (macro):** la app cambia de pestaña en el HMI con clics, lee cada pantalla y regresa a la principal.
   - Elige la *pantalla principal*. Debe tener ancla, por ejemplo el botón de la barra inferior resaltado.
   - Agrega un paso por pestaña. En cada paso, *● Grabar clics (en vivo)*: haz clic en la captura sobre el botón. El clic se ejecuta en el HMI y la captura se actualiza.
   - Graba también los clics de *⌂ Regreso a la principal* y comprueba todo con *▶ Probar recorrido completo*.
   - **Seguridad:**
     - Solo hace clic en los puntos grabados, y solo si el botón se ve igual que al grabarlo.
     - Solo inicia desde la pantalla principal y verifica que llegó a cada pantalla.
     - Se pospone si el operador usó el mouse o el teclado en los últimos N segundos, y se interrumpe sin más clics si el operador lo toca a mitad del recorrido.
     - No hace clic si la ventana del monitor tapa el botón.
     - Mientras está abierto el configurador, el monitoreo se detiene.
   - En la barra: *⏸ Pausar recorrido* y *⟳ Recorrer ahora*.
   - La ventana del monitor se excluye de las capturas de pantalla (Windows 10 2004+).
5. **📋 Recetas:** crea la receta con el mismo nombre que muestra el HMI y llena nominales y tolerancias,
   o pulsa *Tomar valores actuales del HMI como nominales* con la máquina en un buen setup.
6. **▶ Iniciar.**

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
