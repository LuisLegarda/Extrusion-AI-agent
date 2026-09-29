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
| Recorridos | Macros de uno o varios pasos grabadas en vivo, con clics verificados. Pueden leer cada pantalla y regresar. Se disparan cada X tiempo, si el HMI queda X tiempo fuera de una pantalla, si un selector cambia de estado o si un valor baja a cero. Opcionalmente muestran un aviso con cuenta regresiva: el operador puede posponer (vuelve a avisar tras X tiempo), y si lo ignora o acepta, se ejecuta. |
| Variables con fórmula | Variables calculadas a partir de otras: `vel / rpm`, `{zona_1} - {zona_1_sp}`, `max(z1, z2, z3) - min(z1, z2, z3)`, `si(rpm > 0, vel / rpm, 0)`. Se tratan como una medición más: receta, tolerancias, tendencias, reportes. |
| Reportes PDF | Se generan solos cuando una variable cruza un valor, pasa a un valor menor (p. ej. el contador de longitud del carrete se reinicia), cambia un valor o texto, un selector cambia de estado o se ejecuta un recorrido. Abarcan desde el fin del reporte anterior. Evalúan cada variable por especificación, Cpk mínimo o ambos (spec + Cpk), con resultado general. Pueden incluir gráficas, comportamiento, eventos y un CSV con los datos. El archivo se nombra con la fecha y hora o con el valor de una variable. Se guardan en `data\reports` junto al programa (configurable). Opción de reiniciar tendencias, estadística y comportamiento al generarlos. |
| Lectura robusta (automática) | Cada lectura prueba varias variantes de preprocesado: gris por luminancia, mínimo o máximo de color; binarización Otsu, adaptativa o sin binarizar; con y sin suavizado; polaridad por el fondo; recorte al texto. Un valor nuevo se acepta solo si dos variantes distintas coinciden; si no, se conserva el anterior. Recuerda la variante que funciona para cada variable, así en operación normal hace una sola lectura por campo. No requiere umbral manual. |
| Filtros de lectura | Rango válido, salto máximo confirmado en 2 lecturas, confianza mínima, coma o punto decimal y corrección de confusiones típicas del OCR (O→0, l→1…). |
| Recetas = perfil completo | Cada receta guarda toda la configuración: variables, regiones, pantallas y anclas, clics, recorridos, comportamientos entrenados, OEE y reportes. Al cargar la receta se reemplaza todo. |
| Recetas | Por variable: nominal con tolerancia de aviso y de alarma ± (absoluta o en %), o límites mínimo / máximo (pueden ser de un solo lado, p. ej. solo máximo). Cada variable se compara contra la receta o contra la consigna leída del HMI. Las recetas se importan y exportan en CSV (compatible con Excel), y los valores actuales del HMI se pueden tomar como nominales. |
| Selección automática de receta | Con una variable de texto que lee el nombre de la receta del HMI. En modo *Auto desde HMI*, se carga la receta del programa con el mismo nombre; si no existe, avisa y mantiene la actual. En modo manual, solo avisa. |
| Detección de errores | **Ajuste erróneo**: la consigna difiere de la receta. **Fuera de tolerancia**: el valor real se sale de su tolerancia. **Cambio de ajuste**: registra el valor anterior y el nuevo, e indica si se aleja de la receta. **Fallo de lectura**: la variable no se pudo leer o el dato es viejo. |
| Selectores | Variable tipo selector o indicador: se capturan imágenes de cada estado (ON/OFF, AUTO/MAN…) y se reconoce el estado actual por imagen, sin importar color o forma. La receta define el estado esperado. |
| Comportamiento aprendido | Se entrena con un periodo del historial. Aprende la variación normal de cada variable y la correlación entre varias, y en vivo avisa cuando una variable o una relación se sale de lo normal (distancia de Mahalanobis), aunque siga dentro de tolerancia. |
| Análisis en pantalla | Pestañas **Tendencias**: curva de consigna y proyección con banda; rango de tiempo de 5 min a 7 días (los rangos largos se leen del historial) y escala Y automática según los límites de la variable (un pico solo la amplía mientras está en pantalla). **Estadística**: histograma, Cp/Cpk/Pp/Ppk y carta X̄. **Correlación**: matriz y dispersión con regresión. **Comportamiento**: D²/umbral en el tiempo y contribución por variable. |
| Dashboard KPI / OEE | **Disponibilidad**: velocidad de línea ≤ umbral = detenida; los paros cortos son microparos. Un hueco sin datos (app cerrada o en pausa) cuenta como productivo si, al volver, la línea marcha y todo está en parámetros (hasta un límite configurable, por defecto 30 min). **Rendimiento**: velocidad real promedio / nominal (de la receta, de la consigna o fija). **Calidad**: metros conformes / metros producidos, con conformidad por variables en especificación y/o un indicador visual. Muestra OEE, TEEP, MTBF, MTTR, paros, metros, línea de tiempo del estado de la máquina con distribución y comparación con el periodo anterior (turno actual, 1 h, 8 h, 24 h, 7 días). |
| Industria 5.0 | **Factor humano**: carga de alarmas por hora (ISA-18.2) e intervenciones del operador. **Resiliencia**: tiempo en condición normal y recuperación media. **Sostenibilidad**: material conforme y tiempo sin producir. **Índice 5.0**: combina los tres. |
| Tendencias / SPC | Pendiente con prueba de significancia, tiempo estimado hasta el límite de alarma, reglas de Nelson sobre subgrupos y Cpk. |
| Anti-falsas alarmas | Confirmación durante N ciclos, histéresis del 10 %, efecto mínimo relativo a la tolerancia y hallazgos que se mantienen mientras la página no está visible. |
| Pantalla no disponible | Si la sesión se bloquea o el escritorio remoto se desconecta, la captura se renueva sola y la lectura se reanuda al volver. Si la resolución cambió respecto a la configurada, avisa en vez de leer regiones equivocadas. El tiempo sin pantalla cuenta en el OEE como hueco. |
| Historial | SQLite propio (`history.sqlite`) con retención de 90 días. Guarda cada valor cuando cambia o cada 20 s, para que no crezca sin medida. Exporta a CSV con una columna por variable. |

## Interfaz

- **Menú superior:** Archivo (iniciar/detener con F5, carpeta de datos), Receta (editar, receta activa, autocarga desde el HMI), Datos (exportar CSV, generar reporte), Entrenamiento (comportamiento), Recorridos (pausar, ejecutar ahora), Configuración (pestañas y variables, recorridos, KPI/OEE, reportes, general), Ver (páginas con Ctrl+1…8, siempre visible, pantalla completa con F11) y Ayuda.
- **Barra lateral:** Inicio, Variables en vivo, Tendencias, KPI / OEE, SPC, Correlación, Estabilidad (IA) y Alarmas y eventos (con el número de alarmas activas). Debajo están Recetas, Reportes (lista de PDF/CSV generados) y Configuración.
- **Inicio:** tablero general con indicadores tipo gauge: OEE del turno, índice 5.0, estabilidad (comportamiento aprendido), Cpk mínimo, % de variables en especificación y calidad de lectura. También muestra el estado de la máquina, las alarmas activas, las 6 variables con el Cpk más bajo y la franja de estado del turno. Un clic en un gauge abre su vista detallada.
- Solo se actualiza la página visible, para no cargar la PC.

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
   - *+ Selector*: marca el recuadro del selector. Luego, con el HMI en cada estado, pulsa *Capturar estado actual como…* (por ejemplo ON y después OFF).
   - *🧠 Entrenar comportamiento…* (también en la barra principal): elige las variables de referencia y el periodo del historial en que el proceso estuvo bien.
   - *Crear serie…* replica las variables seleccionadas con un desplazamiento, por ejemplo Cylinder 1 → Cylinder 2…5 o Head 1 → Head 8. Si antes marcas la posición del segundo elemento, el desplazamiento se calcula solo.
   - *Probar OCR* comprueba la lectura. Con la **lectura automática** (activa por defecto) muestra cuántas variantes coinciden.
   - *🩺 Diagnóstico de lectura* prueba todas las variables visibles y marca las débiles. En la ventana principal, la columna *Lectura* muestra el % de lecturas exitosas de cada variable. *Quitar marco del campo* elimina el recuadro de los campos del HMI.
   - Si usas el motor de plantillas, *Enseñar caracteres…* le enseña la fuente del HMI.
   - Marca solo el número. Si la unidad está dentro del recuadro (`300 °C`), se ignora, pero es mejor dejarla fuera.
4. **Recorridos (macros):** la app cambia de pestaña en el HMI con clics, puede leer cada pantalla y regresa.
   - *+ Nuevo* crea un recorrido. Agrega un paso por pantalla. En cada paso, pulsa *● Grabar clics (en vivo)* y haz clic en la captura sobre el botón: el clic se ejecuta en el HMI y la captura se actualiza.
   - Graba también los clics de *⌂ Regreso* y comprueba el recorrido con *▶ Probar este recorrido*.
   - **Disparadores** (cualquiera lo activa): cada X segundos, fuera de una pantalla durante X segundos, cambio de un selector (a un estado o a cualquiera), o un valor que baja a ≤ umbral.
   - **Cuenta regresiva** (opcional): aparece un aviso siempre visible. *Posponer* lo vuelve a mostrar tras X tiempo. *Ejecutar ahora*, o dejar que la cuenta termine, lo ejecuta.
   - **Seguridad:**
     - Solo hace clic en los puntos grabados, y solo si el botón se ve igual que al grabarlo.
     - Puede exigir una pantalla de inicio, y verifica que llegó a cada pantalla.
     - Sin cuenta regresiva, se pospone si el operador usó el mouse o el teclado en los últimos N segundos. Se interrumpe sin más clics si el operador toca el HMI a mitad del recorrido.
     - No hace clic si la ventana del monitor tapa el botón.
     - Mientras está abierto el configurador, el monitoreo se detiene.
   - En la barra: *⏸ Pausar recorrido* y *⟳ Recorrer ahora* (la flecha permite elegir el recorrido).
   - La ventana del monitor se excluye de las capturas de pantalla (Windows 10 2004+).
5. **KPI / OEE** (pestaña del configurador): elige la variable de velocidad de línea, el umbral de paro, la velocidad nominal, el tiempo de microparo, cómo se mide la calidad y los horarios de turno.
6. **Reportes** (pestaña del configurador): crea el reporte, agrega disparadores y variables y elige para cada una *En especificación* o *Cpk mínimo*, y si lleva gráfica, eventos y CSV. Elige los modelos de comportamiento a graficar, el nombre del archivo y la carpeta. *📄 Generar vista previa ahora* lo prueba. En la ventana principal, *📄 Reporte* lo genera a mano.
7. **📋 Recetas:** crea la receta con el mismo nombre que muestra el HMI y llena nominales y tolerancias,
   o pulsa *Tomar valores actuales del HMI como nominales* con la máquina en un buen setup.
   *📦 Guardar la configuración actual en esta receta* copia todo el setup (variables, recorridos, comportamiento, OEE, reportes) en la receta. Al guardar el configurador o entrenar un comportamiento, se actualiza la receta activa.
8. **▶ Iniciar.**

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
- `analysis/formula.py`: fórmulas seguras (sin `eval`).
- `scheduling.py` y `navigation.py`: disparadores y ejecución de recorridos.
- `reports.py`: reportes PDF/CSV en un hilo aparte.
- `profiles.py`: recetas como perfil completo.
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
