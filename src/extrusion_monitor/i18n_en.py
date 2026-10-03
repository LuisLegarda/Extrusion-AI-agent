"""Traducción al inglés (clave = texto original en español)."""

EN: dict[str, str] = {
    # --- navegación y menús ---
    "Inicio": "Home", "Variables en vivo": "Live variables", "Tendencias": "Trends", "KPI / OEE": "KPI / OEE",
    "SPC": "SPC", "Correlación": "Correlation", "Estabilidad (IA)": "Stability (AI)",
    "Alarmas y eventos": "Alarms & events", "Recetas": "Recipes", "Reportes": "Reports",
    "Configuración": "Settings", "&Archivo": "&File", "&Receta": "&Recipe", "&Datos": "&Data",
    "&Entrenamiento": "&Training", "Reco&rridos": "&Tours", "&Configuración": "&Configuration", "&Ver": "&View",
    "A&yuda": "&Help", "▶ Iniciar monitoreo": "▶ Start monitoring", "■ Detener monitoreo": "■ Stop monitoring",
    "Cargar automáticamente la receta del HMI": "Load the HMI recipe automatically",
    "⏸ Pausar recorridos": "⏸ Pause tours",
    "Detiene los clics automáticos en el HMI (se siguen leyendo los datos visibles)":
        "Stops automatic clicks on the HMI (visible data is still read)",
    "📌 Siempre visible": "📌 Always on top", "⟳ Ejecutar recorrido ahora": "⟳ Run tour now",
    "📄 Generar reporte ahora": "📄 Generate report now", "📂 Abrir carpeta de datos": "📂 Open data folder",
    "Salir": "Exit", "📋 Editar recetas…": "📋 Edit recipes…", "Receta activa": "Active recipe",
    "⤓ Exportar historial a CSV…": "⤓ Export history to CSV…", "📂 Abrir carpeta de reportes": "📂 Open reports folder",
    "🧠 Entrenar comportamiento…": "🧠 Train behavior…", "Ver estabilidad (comportamiento)": "View stability (behavior)",
    "Configurar recorridos…": "Configure tours…", "Pantalla completa": "Full screen", "Manual de uso": "User manual",
    "Acerca de…": "About…", "Acerca de": "About", "Pestañas y variables…": "Tabs and variables…",
    "Pestañas y variables": "Tabs and variables", "Recorridos…": "Tours…", "Recorrido automático": "Tours",
    "KPI / OEE…": "KPI / OEE…", "Reportes…": "Reports…", "General…": "General…", "General": "General",
    "Idioma": "Language", "🎨 Tema": "🎨 Theme", "Monitor de extrusión": "Extrusion monitor", "Tema": "Theme", "Claro": "Light", "Oscuro": "Dark",
    "Monitor de línea": "Line monitor", "DETENIDO": "STOPPED", "Auto desde HMI": "Auto from HMI",
    "Receta:": "Recipe:", "— sin receta —": "— no recipe —", "  DEMO": "  DEMO",
    " — MODO DEMO (HMI simulado)": " — DEMO MODE (simulated HMI)",
    "<b>Monitor de extrusión</b><br>Verificación de parámetros, recetas, tendencias, KPI/OEE y reportes a partir "
    "de la pantalla del HMI.<br>Solo lee la pantalla: no modifica el PLC ni el software del fabricante.":
        "<b>Extrusion monitor</b><br>Parameter and recipe verification, trends, KPI/OEE and reports from the HMI "
        "screen.<br>It only reads the screen: it does not modify the PLC or the manufacturer's software.",
    "Exportar historial (últimas 24 h)": "Export history (last 24 h)", "Exportado": "Exported",
    "Se exportaron {n} registros.": "{n} records exported.",
    "Rango:": "Range:", "  ⚠ fuera de alarma": "  ⚠ outside alarm", "Desde": "Since", "Nivel": "Level",
    "Regla": "Rule", "Descripción": "Description", "Recorrido: desactivado": "Tour: disabled",
    "Recorrido: EN PAUSA": "Tour: PAUSED", "FALLÓ": "FAILED", "OK": "OK", "pospuesto": "postponed",
    "Recorridos: {n} activos, pendiente": "Tours: {n} active, pending",
    "Recorrido {name}{when}: {state}": "Tour {name}{when}: {state}",
    "sin páginas definidas": "no pages defined", "Página HMI: {pages}": "HMI page: {pages}",
    "OCR: {engine} · lecturas {ok}/{total}": "OCR: {engine} · reads {ok}/{total}",
    "Ciclo: {ms} ms · {time}": "Cycle: {ms} ms · {time}",
    "medición": "measurement", "proyección": "projection", "consigna": "setpoint", "Sin variables": "No variables",
    "Primero configura las variables a leer del HMI.": "First configure the variables to read from the HMI.",
    "  (desactivado)": "  (disabled)", "Sin reportes: créalos en ⚙ Configurar → Reportes":
        "No reports: create them in ⚙ Settings → Reports", "Abrir carpeta de reportes": "Open reports folder",
    "PROCESO OK": "PROCESS OK", "AVISO": "WARNING", "ALARMA": "ALARM", "INFO": "INFO",
    "{n} alarmas · {m} avisos": "{n} alarms · {m} warnings",
    "Pantalla no disponible: {e}": "Screen unavailable: {e}",
    "● En monitoreo": "● Monitoring", "○ Detenido": "○ Stopped",
    "Receta: {r}": "Recipe: {r}", "Última lectura: {t}": "Last reading: {t}",
    "🔔  Alarmas y eventos": "🔔  Alarms & events", "🔔  Alarmas y eventos ({n})": "🔔  Alarms & events ({n})",
    "Hallazgos activos": "Active findings", "en {m} min: {v}": "in {m} min: {v}", "Hallazgos activos ({n})": "Active findings ({n})",
    "Registro de eventos": "Event log",
    "Variables a graficar": "Variables to plot", "(máx. {n})": "(max. {n})",
    "Tiempo mostrado. Más allá de la ventana en memoria se lee del historial.":
        "Time shown. Beyond the in-memory window, data is read from history.",
    "Escala Y automática (según límites)": "Automatic Y scale (by limits)",
    "La escala se ajusta a los límites de la variable y a los datos visibles; un pico solo la amplía mientras "
    "está en pantalla. Desmárcala para hacer zoom manual con el mouse.":
        "The scale follows the variable limits and the visible data; a spike only widens it while it is on "
        "screen. Uncheck it to zoom manually with the mouse.",
    "Marca la casilla de una variable para graficar su tendencia.": "Check a variable to plot its trend.",
    "5 min": "5 min", "15 min": "15 min", "30 min": "30 min", "1 h": "1 h", "4 h": "4 h", "8 h": "8 h",
    "24 h": "24 h", "7 días": "7 days",
    # --- inicio ---
    "Estado de la máquina": "Machine status", "Alarmas y avisos activos": "Active alarms and warnings",
    "Cpk por variable (las 6 más bajas)": "Cpk by variable (lowest 6)", "Estado del turno": "Shift status",
    "\n(clic para ver el detalle)": "\n(click for details)",
    "Sin datos: se necesitan límites en la receta y lecturas en la ventana de tendencia.":
        "No data: recipe limits and readings in the trend window are needed.",
    "OEE (turno)": "OEE (shift)", "Disponibilidad × Rendimiento × Calidad del turno en curso":
        "Availability × Performance × Quality of the current shift",
    "Índice 5.0": "5.0 index", "Factor humano (carga de alarmas), resiliencia y sostenibilidad del turno":
        "Human factor (alarm load), resilience and sustainability of the shift",
    "Estabilidad": "Stability", "% del tiempo (últimos 30 min) en que el comportamiento aprendido fue normal":
        "% of time (last 30 min) the learned behavior was normal",
    "Cpk mínimo (proceso)": "Minimum Cpk (process)",
    "El Cpk más bajo de las variables con límites (ventana de tendencia)":
        "Lowest Cpk of the variables with limits (trend window)",
    "En especificación": "In specification",
    "% de las variables verificadas que están dentro de tolerancia ahora":
        "% of checked variables currently within tolerance",
    "Calidad de lectura": "Reading quality",
    "% de las variables visibles leídas correctamente en el último ciclo":
        "% of visible variables read correctly in the last cycle",
    "Sin límites o sin datos suficientes": "No limits or not enough data", "Sin receta o sin límites":
        "No recipe or no limits", "comportamiento normal": "normal behavior",
    "✔ Sin alarmas ni avisos activos": "✔ No active alarms or warnings", "Sin variables visibles": "No visible variables",
    "Sin datos frescos de los modelos": "No fresh data for the models",
    "Entrena un comportamiento (menú Entrenamiento)": "Train a behavior (Training menu)",
    "Configura el OEE (Configuración → KPI / OEE)": "Set up OEE (Configuration → KPI / OEE)",
    "● Monitoreo detenido": "● Monitoring stopped", "Cpk": "Cpk",
    "{ok} de {n} variables": "{ok} of {n} variables", "{ok} de {n} leídas": "{ok} of {n} read",
    "{a} alarmas/h · normal {p}": "{a} alarms/h · normal {p}",
    "desde hace {d}": "for {d}", "Velocidad: <b>{v}</b>{nom} {u}": "Speed: <b>{v}</b>{nom} {u}",
    "Receta: <b>{r}</b>": "Recipe: <b>{r}</b>",
    "Producido en el turno: <b>{t}</b> (conforme {g})": "Produced this shift: <b>{t}</b> (good {g})",
    "Paros: <b>{s}</b> · microparos: <b>{m}</b> · detenido {d}": "Stops: <b>{s}</b> · microstops: <b>{m}</b> · stopped {d}",
    "Hallazgos: <b style='color:{ca}'>{a} alarmas</b> · <b style='color:{cw}'>{w} avisos</b>":
        "Findings: <b style='color:{ca}'>{a} alarms</b> · <b style='color:{cw}'>{w} warnings</b>",
    # --- estados OEE ---
    "En marcha": "Running", "Lento": "Slow", "Microparo": "Microstop", "Paro": "Stopped",
    "Sin datos (productivo)": "No data (productive)", "Sin datos": "No data",
    # --- KPI ---
    "Turno actual": "Current shift", "Última hora": "Last hour", "Últimas 8 h": "Last 8 h",
    "Últimas 24 h": "Last 24 h", "Últimos 7 días": "Last 7 days", "Otros KPIs": "Other KPIs",
    "Distribución": "Distribution", "Industria 5.0 · personas, resiliencia y sostenibilidad":
        "Industry 5.0 · people, resilience and sustainability",
    "Periodo:": "Period:", "OEE": "OEE", "Disponibilidad × Rendimiento × Calidad": "Availability × Performance × Quality",
    "Disponibilidad": "Availability", "Rendimiento": "Performance", "Calidad": "Quality",
    "Tiempo en marcha / tiempo planificado. Velocidad ≤ umbral = línea detenida.":
        "Run time / planned time. Speed ≤ threshold = line stopped.",
    "Velocidad real promedio / velocidad nominal (los microparos cuentan como velocidad 0).":
        "Average actual speed / nominal speed (microstops count as speed 0).",
    "Longitud producida en condición conforme / longitud total.": "Length produced in good condition / total length.",
    "Actual": "Current", "Anterior": "Previous", "Resumen": "Summary", "Estado": "Status", "Duración": "Duration",
    "Veces": "Count", "Factor humano": "Human factor",
    "Carga de alarmas por hora según ISA-18.2: ≤6/h manejable": "Alarms per hour per ISA-18.2: ≤6/h manageable",
    "Resiliencia": "Resilience", "% del tiempo con el proceso en condición normal (sin avisos)":
        "% of time with the process in normal condition (no warnings)",
    "Sostenibilidad": "Sustainability", "Material conforme, penalizado por tiempo detenido":
        "Good material, penalized by downtime",
    "variables en especificación": "variables in specification", "indicador visual": "visual indicator",
    "variables en especificación e indicador visual": "variables in specification and visual indicator",
    "TEEP": "TEEP", "MTBF": "MTBF", "MTTR": "MTTR", "Paros": "Stops", "Microparos": "Microstops",
    "Detenido": "Stopped", "Producido": "Produced", "Conforme": "Good", "Desperdicio": "Scrap",
    "Vel. promedio": "Avg. speed", "Vel. nominal": "Nominal speed", "Sin datos en el periodo.": "No data in the period.",
    "Periodo anterior": "Previous period",
    "<b>Índice 5.0: <span style='color:{color}; font-size:16px'>{idx}</span></b> / 100<br>"
    "Alarmas y avisos: {aph}/h (ISA-18.2 recomienda ≤ 6/h) · intervenciones del operador: {iph}/h<br>"
    "Tiempo en condición normal: {normal} · recuperación media: {rec}<br>"
    "Desperdicio: {scrap} ({slen} {unit}) · tiempo detenido: {stop}":
        "<b>5.0 index: <span style='color:{color}; font-size:16px'>{idx}</span></b> / 100<br>"
        "Alarms and warnings: {aph}/h (ISA-18.2 recommends ≤ 6/h) · operator interventions: {iph}/h<br>"
        "Time in normal condition: {normal} · mean recovery: {rec}<br>"
        "Scrap: {scrap} ({slen} {unit}) · downtime: {stop}",
    "Velocidad: {v} · paro si ≤ {s} · microparo &lt; {m} s · calidad por {q}":
        "Speed: {v} · stop if ≤ {s} · microstop &lt; {m} s · quality by {q}",
    "Estado actual: <b style='color:{c}'>{s}</b> desde hace {d}": "Current status: <b style='color:{c}'>{s}</b> for {d}",
    "<b>Configura el OEE</b> en ⚙ Configurar variables → pestaña «KPI / OEE»: elige la variable de velocidad de "
    "línea, la velocidad nominal y cómo se mide la calidad.":
        "<b>Set up OEE</b> in ⚙ Settings → «KPI / OEE» tab: choose the line speed variable, the nominal speed and "
        "how quality is measured.",
    # --- análisis ---
    "NORMAL": "NORMAL", "ANORMAL": "ABNORMAL", "MUY ANORMAL": "VERY ABNORMAL", "Variable:": "Variable:",
    "Distribución (ventana de tendencia)": "Distribution (trend window)",
    "Carta de control X̄ (medias por subgrupo)": "X̄ control chart (subgroup means)",
    "Datos insuficientes: se necesitan al menos 5 lecturas en la ventana de tendencia.":
        "Not enough data: at least 5 readings in the trend window are needed.",
    "LIE": "LSL", "LSE": "USL", "LCS": "UCL", "LCI": "LCL", "LC": "CL", "media": "mean", "objetivo": "target",
    "Variables a comparar": "Variables to compare", "Dispersión": "Scatter", "Marca al menos 2 variables.":
        "Check at least 2 variables.", "Datos insuficientes en la ventana de tendencia.": "Not enough data in the trend window.",
    "Modelo:": "Model:", "Desviación respecto a lo normal (D² / umbral)": "Deviation from normal (D² / threshold)",
    "Contribución por variable (%)": "Contribution by variable (%)",
    "No hay modelos. Crea uno en ⚙ Configurar variables → «Entrenar comportamiento…» o con el botón 🧠 Comportamiento.":
        "There are no models. Create one in the Training menu → «Train behavior…».",
    " (significativa)": " (significant)",
    "<br><i>Sin límites de alarma en la receta: no se calcula Cp/Cpk.</i>":
        "<br><i>No alarm limits in the recipe: Cp/Cpk is not calculated.</i>",
    "no aplica a la receta activa": "does not apply to the active recipe",
    "esperando datos vigentes de todas sus variables": "waiting for current data of all its variables",
    " (inactivo)": " (inactive)", "inactivo": "inactive", "umbral": "threshold", "alarma": "alarm",
    "ninguna": "none", "Sin evaluación: {r}.": "Not evaluated: {r}.", "Relaciones rotas: {b}": "Broken relationships: {b}",
    "n = {n} · media = {mean} · σ total = {s} · σ corto plazo = {sw} · mín/máx = {mn} / {mx}<br>"
    "Cp = {cp} · Cpk = {cpk} · Pp = {pp} · Ppk = {ppk} · fuera de límites estimado = {out} %<br>"
    "Tendencia = {slope} · tiempo estimado al límite = {eta} · reglas SPC: {rules}":
        "n = {n} · mean = {mean} · σ overall = {s} · σ short term = {sw} · min/max = {mn} / {mx}<br>"
        "Cp = {cp} · Cpk = {cpk} · Pp = {pp} · Ppk = {ppk} · estimated out of limits = {out} %<br>"
        "Trend = {slope} · estimated time to limit = {eta} · SPC rules: {rules}",
    # --- tabla de variables ---
    "Variable": "Variable", "Consigna": "Setpoint", "Medición": "Measurement", "Unidad": "Unit",
    "Referencia": "Reference", "Desv.": "Dev.", "Tol. aviso / alarma": "Warn / alarm tol.",
    "Tendencia /min": "Trend /min", "Lectura": "Reading", "→ estable": "→ stable",
    "Marca la casilla para graficar la tendencia": "Check to plot the trend", "vía recorrido": "via tour",
    "sin dato": "no data", "esperado «{e}»": "expected «{e}»", "no visible": "not visible", "receta": "recipe",
    # --- reportes ---
    "📄 Generar ahora": "📄 Generate now", "Reportes generados": "Generated reports", "⟳ Actualizar": "⟳ Refresh",
    "📂 Abrir carpeta": "📂 Open folder", "⚙ Configurar reportes": "⚙ Configure reports", "Fecha": "Date",
    "Archivo": "File", "Tipo": "Type", "Carpeta": "Folder",
    "{n} archivos · doble clic para abrir · carpetas: {d}": "{n} files · double-click to open · folders: {d}",
    "Variable cruza un valor": "Variable crosses a value", "Valor pasa a uno menor": "Value drops",
    "Valor / texto cambia": "Value / text changes", "Selector cambia de estado": "Selector changes state",
    "Se ejecuta un recorrido": "A tour runs",
    "El reporte PDF se genera solo cuando ocurre alguno de sus disparadores y abarca desde el fin del reporte "
    "anterior hasta ese momento. Cada variable se evalúa por especificación (todas las lecturas dentro de los "
    "límites de la receta) o por Cpk mínimo; el resultado general es conforme si todas lo son.":
        "The PDF report is generated automatically when any of its triggers occurs and covers from the end of the "
        "previous report up to that moment. Each variable is evaluated by specification (all readings within the "
        "recipe limits) or by minimum Cpk; the overall result passes if all of them pass.",
    "Activado": "Enabled", "Tiempo mínimo entre reportes": "Minimum time between reports",
    "Periodo máximo (primer reporte)": "Maximum period (first report)",
    "Reiniciar tendencias, estadística y comportamiento al generarlo":
        "Reset trends, statistics and behavior when generated",
    "Disparadores (cualquiera genera el reporte)": "Triggers (any of them generates the report)",
    "+ Disparador": "+ Trigger", "Quitar": "Remove", "Variables y estados del reporte": "Report variables and states",
    "+ Agregar": "+ Add", "Gráfica de comportamiento (modelos entrenados)": "Behavior chart (trained models)",
    "Salida": "Output", "Incluir también eventos generales (recetas, recorridos, reportes)":
        "Also include general events (recipes, tours, reports)",
    "Exportar los datos de las variables marcadas en CSV": "Export the checked variables' data to CSV",
    "Nombre del archivo": "File name", "Abrir carpeta": "Open folder", "📄 Generar vista previa ahora": "📄 Generate preview now",
    "Genera el reporte con los datos desde el último reporte, sin mover el inicio del siguiente":
        "Generates the report with data since the last report, without moving the start of the next one",
    "Fecha y hora": "Date and time", "Cpk mínimo": "Minimum Cpk", "Spec + Cpk mínimo": "Spec + minimum Cpk",
    "Carpeta de reportes": "Reports folder", "vista previa": "preview", "Reporte:": "Report:", "+ Nuevo": "+ New",
    "Variable / recorrido": "Variable / tour", "Condición": "Condition", "Valor / estado": "Value / state",
    "Evaluación": "Evaluation", "Cpk mín.": "Min. Cpk", "Gráfica": "Chart", "Eventos": "Events", "CSV": "CSV",
    "cualquier recorrido": "any tour", "Reporte": "Report", "Agrega al menos una variable al reporte.":
        "Add at least one variable to the report.", "cualquier estado": "any state", " cambio mayor a": " change above",
    " baja más de": " drops more than", "cambio mayor a": "change above", "baja más de": "drops more than",
    "Se dispara cuando el valor es menor que la lectura anterior por más de esta cantidad (0 = cualquier baja). "
    "Útil para contadores que se reinician, como la longitud del carrete.":
        "Triggers when the value is lower than the previous reading by more than this amount (0 = any drop). "
        "Useful for counters that reset, such as the reel length.",
    "  (sin entrenar)": "  (untrained)", "En especificación ": "In specification ",
    "Generado: {p}": "Generated: {p}", "No se pudo generar: {e}": "Could not generate: {e}",
    # --- recorridos ---
    "Si no respondes, se ejecuta al terminar la cuenta.": "If you do not respond, it runs when the countdown ends.",
    "▶ Ejecutar ahora": "▶ Run now", "⏸ Posponer": "⏸ Postpone",
    "<b>Se ejecutará el recorrido «{n}»</b><br>{r}": "<b>The tour «{n}» will run</b><br>{r}",
    "Un recorrido hace clics grabados en el HMI (uno o varios pasos), puede leer los datos de cada pantalla y "
    "regresar. Se dispara cada X tiempo, si el HMI queda fuera de una pantalla, si un selector cambia o si un valor "
    "baja a cero. <b>Seguridad:</b> solo hace clic donde grabaste y si el botón se ve igual; se pospone si el "
    "operador está usando el HMI.":
        "A tour performs recorded clicks on the HMI (one or several steps), can read the data of each screen and "
        "return. It triggers every X time, if the HMI stays away from a screen, if a selector changes or if a value "
        "drops to zero. <b>Safety:</b> it only clicks where you recorded and if the button looks the same; it is "
        "postponed while the operator is using the HMI.",
    "Ajustes": "Settings", "Nombre": "Name", "Leer las variables de cada pantalla visitada":
        "Read the variables of each visited screen", "Iniciar solo desde": "Start only from",
    "Pantalla de regreso (verificada)": "Return screen (verified)", "Operador inactivo al menos": "Operator idle at least",
    "Reintentos al verificar pantalla": "Retries when verifying a screen",
    "Disparadores (cualquiera activa el recorrido)": "Triggers (any of them starts the tour)", "Cada": "Every",
    "Fuera de la pantalla": "Away from screen", "durante": "for", "Si el selector cambia": "If the selector changes",
    "a": "to", "Si el valor baja a": "If the value drops to",
    "Avisar con cuenta regresiva (el operador puede posponer)": "Warn with a countdown (the operator can postpone)",
    "Cuenta regresiva": "Countdown", "Al posponer, volver a avisar tras": "When postponed, warn again after",
    "Pasos (en orden)": "Steps (in order)", "+ Paso a esta pestaña": "+ Step to this tab",
    "Espera tras el clic": "Wait after click", "● Grabar clics (en vivo)": "● Record clicks (live)",
    "Cada clic en la captura se ejecuta también en el HMI y se recaptura la pantalla":
        "Each click on the capture is also executed on the HMI and the screen is recaptured",
    "Borrar clics": "Clear clicks", "▶ Probar este recorrido": "▶ Test this tour", "(sin verificar)": "(not verified)",
    "■ Terminar grabación": "■ Stop recording", "Recorrido:": "Tour:", "Eliminar paso": "Delete step",
    "— cualquier pantalla —": "— any screen —", "— no verificar —": "— do not verify —", "— no —": "— no —",
    "Paso": "Step", "Primero crea las pestañas en «Pestañas y variables».": "First create the tabs in «Tabs and variables».",
    "El recorrido no tiene pasos": "The tour has no steps", "Recorrido incompleto": "Incomplete tour",
    "Duplicar": "Duplicate", "Eliminar": "Delete", "Activado ": "Enabled ",
    "GRABANDO: haz clic en la captura sobre el botón del HMI. El clic se ejecuta en el HMI y la captura se "
    "actualiza. Pulsa «Terminar grabación» al llegar a la pantalla.":
        "RECORDING: click on the capture over the HMI button. The click is executed on the HMI and the capture "
        "is updated. Press «Stop recording» when you reach the screen.",
    "Activo": "Active",
    # --- OEE (configuración) ---
    "<b>OEE = Disponibilidad × Rendimiento × Calidad</b><br>• <b>Disponibilidad</b>: tiempo en marcha / tiempo "
    "planificado (velocidad ≤ umbral = línea detenida; los paros cortos son microparos y cuentan en el "
    "rendimiento).<br>• <b>Rendimiento</b>: velocidad real promedio / velocidad nominal.<br>• <b>Calidad</b>: "
    "longitud producida en condición conforme / longitud total.":
        "<b>OEE = Availability × Performance × Quality</b><br>• <b>Availability</b>: run time / planned time "
        "(speed ≤ threshold = line stopped; short stops are microstops and count in performance).<br>• "
        "<b>Performance</b>: average actual speed / nominal speed.<br>• <b>Quality</b>: length produced in good "
        "condition / total length.",
    "Calcular OEE": "Calculate OEE", "Variable de velocidad de línea": "Line speed variable",
    "Detenida si velocidad ≤": "Stopped if speed ≤", "Velocidad nominal": "Nominal speed", "Valor fijo": "Fixed value",
    " % de la nominal": " % of nominal", "Marcha lenta por debajo de": "Slow below", "Microparo: paro menor a":
        "Microstop: stop shorter than", "Unidad de la velocidad": "Speed unit",
    "Tiempo sin datos cuenta como productivo si al volver todo está en parámetros":
        "Time without data counts as productive if everything is within parameters on return",
    "…hasta un hueco de": "…up to a gap of", "Conforme cuando": "Good when", "Indicador": "Indicator",
    "Estado bueno": "Good state", "Los avisos también cuentan como no conforme (por defecto solo alarmas)":
        "Warnings also count as not good (by default only alarms)", "Inicio de turnos": "Shift start times",
    "— elegir —": "— choose —", "— ninguno —": "— none —", "Nominal de la receta": "Recipe nominal",
    "Consigna leída del HMI": "Setpoint read from the HMI", "Todas las mediciones dentro de especificación":
        "All measurements within specification", "Indicador visual (selector) en estado bueno":
        "Visual indicator (selector) in good state", "Ambos": "Both",
    "OEE: elige la variable de velocidad de línea": "OEE: choose the line speed variable",
    "OEE: indica la velocidad nominal fija": "OEE: enter the fixed nominal speed",
    "OEE: elige el indicador de calidad y su estado bueno": "OEE: choose the quality indicator and its good state",
    "Meta de OEE": "OEE target",
    # --- recetas ---
    "Nominal": "Nominal", "Modo": "Mode", "Aviso ±": "Warning ±", "Alarma ±": "Alarm ±", "Aviso mín": "Warning min",
    "Aviso máx": "Warning max", "Alarma mín": "Alarm min", "Alarma máx": "Alarm max", "Comparar contra": "Compare against",
    "Datos del producto": "Product data",
    "Modo <b>±</b>: nominal y tolerancias de aviso/alarma (en unidades o en %). Modo <b>mín / máx</b>: límites "
    "absolutos; deja vacío un lado para un límite de un solo lado (p. ej. solo máximo). Sin nominal ni límites la "
    "variable no se verifica. «Comparar contra consigna» evalúa el valor real frente a la consigna leída del HMI "
    "(modo ±).":
        "Mode <b>±</b>: nominal and warning/alarm tolerances (in units or %). Mode <b>min / max</b>: absolute "
        "limits; leave one side empty for a one-sided limit (e.g. maximum only). Without a nominal or limits the "
        "variable is not checked. «Compare against setpoint» evaluates the actual value against the setpoint "
        "read from the HMI (± mode).",
    "Tomar valores actuales del HMI como nominales": "Take current HMI values as nominals",
    "📦 Guardar la configuración actual en esta receta": "📦 Save the current configuration in this recipe",
    "La receta guarda todo: variables, pantallas, recorridos, OEE, reportes y comportamientos. Al cargarla se "
    "restaura esa configuración.": "The recipe stores everything: variables, screens, tours, OEE, reports and "
                                   "behaviors. Loading it restores that configuration.",
    "Guardar": "Save", "Cancelar": "Cancel", "Nombre de la receta (igual al que muestra el HMI):":
        "Recipe name (the same one shown by the HMI):", "Nueva receta": "New recipe", "Duplicar receta": "Duplicate recipe",
    "Renombrar receta": "Rename recipe", "Importar receta": "Import recipe", "Exportar receta": "Export recipe",
    "Nueva": "New", "Renombrar": "Rename", "Importar CSV…": "Import CSV…", "Exportar CSV…": "Export CSV…",
    "± absoluta": "± absolute", "± % de la referencia": "± % of reference", "mín / máx": "min / max",
    "Nombre en uso": "Name in use", "Inicia el monitoreo para tener valores actuales.": "Start monitoring to get current values.",
    "consigna del HMI": "HMI setpoint", "Tolerancias": "Tolerances", "Error al importar": "Import error",
    "Valor inválido": "Invalid value", "Descripción ": "Description ",
    # --- comportamiento ---
    "Entrenar comportamiento normal": "Train normal behavior",
    "Elige un periodo en que el proceso trabajó bien. La app aprende la <b>variación normal</b> de cada variable "
    "y, si eliges 2 o más, <b>cómo se mueven juntas</b> (correlación). En vivo avisa cuando una variable o una "
    "relación entre ellas se sale de lo aprendido, aunque siga dentro de tolerancia.":
        "Choose a period in which the process ran well. The app learns the <b>normal variation</b> of each "
        "variable and, if you choose 2 or more, <b>how they move together</b> (correlation). Live, it warns when a "
        "variable or a relationship between them departs from what was learned, even if still within tolerance.",
    "Activo (evaluar en el monitoreo)": "Active (evaluate during monitoring)",
    "Periodo de entrenamiento (del historial)": "Training period (from history)", "Últimos": "Last", "días": "days",
    "Rango": "Range", "Resolución": "Resolution", "Sensibilidad": "Sensitivity",
    "1 = umbral aprendido; mayor = menos avisos; menor = más sensible":
        "1 = learned threshold; higher = fewer warnings; lower = more sensitive",
    "Margen del umbral": "Threshold margin", "Variación normal por variable": "Normal variation per variable",
    "Solo con la receta": "Only with recipe", "🧠 Entrenar": "🧠 Train", "Sin entrenar": "Untrained",
    "Guardar modelo": "Save model", "Cerrar": "Close", "Modelos": "Models", "Nuevo": "New",
    "Variables de referencia": "Reference variables", "Variación normal aprendida": "Learned normal variation",
    "Media": "Mean", "Mín": "Min", "Máx": "Max", "Rango normal": "Normal range",
    "Correlación entre variables (rojo = suben juntas, azul = una sube y otra baja)":
        "Correlation between variables (red = rise together, blue = one rises and the other falls)",
    "sin entrenar": "untrained", "(no hay receta activa)": "(no active recipe)", "Variables": "Variables",
    "Marca al menos una variable.": "Check at least one variable.", "Periodo": "Period",
    "El inicio debe ser anterior al fin.": "The start must be before the end.",
    "Sin entrenar: elige variables y periodo y pulsa «Entrenar».": "Untrained: choose variables and period and press «Train».",
    "Entrena el modelo antes de guardarlo.": "Train the model before saving it.", "Guardado.": "Saved.",
    "Comportamiento normal": "Normal behavior", "No se pudo entrenar": "Could not train",
    "<br>Sin relaciones fuertes entre las variables.": "<br>No strong relationships between the variables.",
    "horas": "hours", "minutos": "minutes",
    # --- diagnóstico OCR ---
    "Diagnóstico de lectura": "Reading diagnosis", "Valor": "Value", "Acuerdo": "Agreement",
    "Otras lecturas": "Other readings", "Recomendación": "Recommendation", "Débil": "Weak", "Falla": "Fails",
    "Cada variable visible se lee con todas las variantes de preprocesado. Un acuerdo alto significa lectura "
    "estable; bajo, que conviene ajustar la región.":
        "Each visible variable is read with every preprocessing variant. High agreement means a stable reading; "
        "low means the region should be adjusted.",
    "Ninguna variante leyó un número: revisa que la región cubra el número.":
        "No variant read a number: check that the region covers the number.",
    "Define un rango válido para descartar lecturas imposibles.": "Set a valid range to discard impossible readings.",
    "Ajusta la región solo al número (sin unidad ni marco).": "Fit the region to the number only (no unit or frame).",
    # --- configurador ---
    "Configuración de variables y lectura del HMI": "Variables and HMI reading setup",
    "fórmula": "formula", "Medición (valor real)": "Measurement (actual value)",
    "Consigna (parámetro establecido)": "Setpoint (set parameter)", "Texto (p. ej. nombre de receta)":
        "Text (e.g. recipe name)", "Selector / indicador (estado por imagen)": "Selector / indicator (state by image)",
    "Fórmula (calculada de otras variables)": "Formula (calculated from other variables)",
    "Arrastra con el botón izquierdo para marcar una región · rueda = zoom · botón central = desplazar · clic en "
    "una región para seleccionarla":
        "Drag with the left button to mark a region · wheel = zoom · middle button = pan · click a region to select it",
    "Crear serie": "Create series", "Copias a crear": "Copies to create", "Desplazamiento X por copia": "X offset per copy",
    "Desplazamiento Y por copia": "Y offset per copy", "Texto del nombre a numerar": "Name text to number",
    "Primer número": "First number", "Crear": "Create", "Pestaña seleccionada": "Selected tab", "Dentro de": "Inside",
    "sin ancla (carpeta: visible si su padre lo es)": "no anchor (folder: visible if its parent is)", "Ancla": "Anchor",
    "Usar selección como ancla": "Use selection as anchor", "Quitar ancla": "Remove anchor",
    "Umbral de coincidencia": "Match threshold", "Probar en la captura": "Test on capture",
    "Variable seleccionada": "Selected variable", "Reinsertar punto decimal si el OCR lo pierde":
        "Reinsert the decimal point if OCR loses it", "Quitar marco del campo": "Remove field frame",
    "Lectura automática robusta (recomendado: sin umbral manual)": "Robust automatic reading (recommended: no manual threshold)",
    "Prueba varias formas de preparar la imagen y acepta el valor cuando coinciden. Recuerda la que funciona para "
    "esta variable.": "Tries several ways to prepare the image and accepts the value when they agree. It remembers "
                      "the one that works for this variable.",
    "Analizar tendencia": "Analyze trend",
    "p. ej. vel / rpm   ·   {z1} - {z1_sp}   ·   max(z1, z2) - min(z1, z2)":
        "e.g. vel / rpm   ·   {z1} - {z1_sp}   ·   max(z1, z2) - min(z1, z2)",
    "Usa los ID de las variables. Funciones: abs, min, max, avg, round, sqrt, log, exp, pow, clamp, si(cond, a, "
    "b). Operadores + - * / ** % y comparaciones.":
        "Use the variable IDs. Functions: abs, min, max, avg, round, sqrt, log, exp, pow, clamp, si(cond, a, b). "
        "Operators + - * / ** % and comparisons.",
    "Estados del selector": "Selector states", "Capturar estado actual como…": "Capture current state as…",
    "Eliminar estado": "Delete state", "Coincidencia mínima": "Minimum match", "Prueba de lectura": "Reading test",
    "Nombre de la máquina": "Machine name", "1 = monitor principal, 0 = todos los monitores":
        "1 = main monitor, 0 = all monitors", "Monitor a capturar": "Monitor to capture",
    "Intervalo de muestreo": "Sampling interval", "Motor OCR": "OCR engine", "Ruta a tesseract.exe (opcional)":
        "Path to tesseract.exe (optional)", "Tesseract": "Tesseract", " ciclos": " cycles",
    "Confirmación de hallazgos": "Finding confirmation", "Fallos de lectura para avisar": "Read failures before warning",
    "Dato viejo después de": "Data is stale after", "Ventana de tendencia": "Trend window",
    "Horizonte de predicción": "Prediction horizon", "Subgrupo SPC": "SPC subgroup",
    "Variable con nombre de receta": "Recipe name variable", "Sonido al activarse una alarma": "Sound when an alarm is raised",
    "Abrir captura del HMI": "Open HMI capture", "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)":
        "Images (*.png *.jpg *.jpeg *.bmp *.webp)", "Guardar captura": "Save capture",
    "medición + consigna": "measurement + setpoint", "— siempre visible —": "— always visible —",
    "— ninguna —": "— none —", "Nueva pestaña": "New tab", "— raíz —": "— root —", " (siempre visible)": " (always visible)",
    "Nuevo par consigna / medición": "New setpoint / measurement pair", "Estado del selector": "Selector state",
    "Nombre del estado que se ve ahora (p. ej. ON, OFF, AUTO, MAN):": "Name of the state shown now (e.g. ON, OFF, AUTO, MAN):",
    "Nueva fórmula": "New formula", "Nombre de la variable calculada:": "Name of the calculated variable:",
    "Fórmula": "Formula", "<br>El motor de plantillas aún no conoce caracteres: usa «Enseñar caracteres…».":
        "<br>The template engine does not know any characters yet: use «Teach characters…».",
    "Enseñar caracteres": "Teach characters", "Escribe exactamente lo que muestra la región:":
        "Type exactly what the region shows:",
    "Se copian las variables seleccionadas desplazando sus regiones.\nConsejo: marca en la captura la posición del "
    "segundo elemento antes de abrir este diálogo y el desplazamiento se calcula solo.":
        "The selected variables are copied by offsetting their regions.\nTip: mark the position of the second "
        "element on the capture before opening this dialog and the offset is calculated automatically.",
    "📷 Capturar pantalla del HMI": "📷 Capture HMI screen", "Abrir imagen…": "Open image…",
    "Guardar captura…": "Save capture…", "Ajustar vista": "Fit view", "+ Pestaña / componente": "+ Tab / component",
    "Nuevo nodo raíz (p. ej. EXT1, GAS, MEAS)": "New root node (e.g. EXT1, GAS, MEAS)", "+ Sub-pestaña": "+ Sub-tab",
    "Nodo dentro de la pestaña seleccionada (p. ej. Overview)": "Node inside the selected tab (e.g. Overview)",
    "+ Par consigna / medición": "+ Setpoint / measurement pair",
    "Marca primero la consigna y después el valor medido; quedan vinculados":
        "Mark the setpoint first and then the measured value; they are linked",
    "+ Medición": "+ Measurement", "Variable medida sin consigna": "Measured variable without setpoint",
    "+ Consigna": "+ Setpoint", "Parámetro establecido sin medición": "Set parameter without measurement",
    "+ Texto": "+ Text", "Texto, p. ej. el nombre de la receta": "Text, e.g. the recipe name", "+ Fórmula": "+ Formula",
    "Variable calculada con otras, p. ej. «vel / rpm» o «max(z1, z2, z3) - min(z1, z2, z3)»":
        "Variable calculated from others, e.g. «vel / rpm» or «max(z1, z2, z3) - min(z1, z2, z3)»",
    "+ Selector": "+ Selector", "Selector, interruptor o indicador: se reconoce su estado por imagen (ON/OFF, AUTO/MAN…)":
        "Selector, switch or indicator: its state is recognized by image (ON/OFF, AUTO/MAN…)",
    "Crear serie…": "Create series…", "🩺 Diagnóstico de lectura": "🩺 Reading diagnosis",
    "Selecciona una pestaña o una variable del árbol.": "Select a tab or a variable in the tree.",
    "El ancla es una parte de la pantalla que solo se ve cuando la pestaña está activa,\np. ej. el botón de la "
    "pestaña resaltado o el título. Sin ancla, el nodo solo agrupa.":
        "The anchor is a part of the screen that is only visible when the tab is active,\ne.g. the highlighted tab "
        "button or the title. Without an anchor, the node only groups.",
    "automático": "automatic", "sin límite": "no limit", "texto claro sobre fondo oscuro": "light text on dark background",
    "texto oscuro sobre fondo claro": "dark text on light background", "Pestaña": "Tab",
    "Consigna vinculada": "Linked setpoint", "Decimales": "Decimals", "Separador decimal": "Decimal separator",
    "Valor mínimo válido": "Minimum valid value", "Valor máximo válido": "Maximum valid value",
    "Salto máx. entre lecturas": "Max. jump between readings", "Contraste": "Contrast", "Escala OCR": "OCR scale",
    "Umbral binario": "Binary threshold", "Región": "Region",
    "Pon el selector en cada estado en el HMI, captura la pantalla y pulsa «Capturar estado actual». Se reconoce "
    "por imagen: sirve para cualquier color o forma.":
        "Put the selector in each state on the HMI, capture the screen and press «Capture current state». It is "
        "recognized by image: it works with any color or shape.",
    "Asignar selección como región": "Assign selection as region", "Probar OCR": "Test OCR",
    "Enseñar caracteres…": "Teach characters…", "OCR de Windows (recomendado)": "Windows OCR (recommended)",
    "Plantillas enseñadas (más preciso para fuentes fijas)": "Taught templates (more accurate for fixed fonts)",
    "Tesseract (requiere tesseract.exe)": "Tesseract (requires tesseract.exe)",
    "Siempre visible (sin pestaña)": "Always visible (no tab)", "Sub-pestaña": "Sub-tab",
    "Selecciona primero la pestaña o componente padre.": "First select the parent tab or component.",
    "Selección": "Selection", "Primero captura la pantalla y marca una región.": "First capture the screen and mark a region.",
    "ID duplicado": "Duplicate ID", "Captura": "Capture", "Primero captura la pantalla del HMI.":
        "First capture the HMI screen.", "Selecciona en el árbol las variables a replicar.":
        "Select the variables to replicate in the tree.", "Revisa la configuración": "Check the configuration",
    "¿Usar la región marcada como ancla de la pestaña?\n(Debe verse solo cuando la pestaña está activa, p. ej. su "
    "botón resaltado)": "Use the marked region as the tab anchor?\n(It must only be visible when the tab is active, "
                       "e.g. its highlighted button)",
    " (copia)": " (copy)", " copia": " copy", "Captura al menos un estado del selector.": "Capture at least one selector state.",
    "<br>Lectura débil: ajusta la región (solo el número, sin la unidad).":
        "<br>Weak reading: adjust the region (the number only, without the unit).",
    "No se pudo enseñar": "Could not teach", "Error": "Error", "pestaña": "tab", "VISIBLE": "VISIBLE",
    "no válido": "invalid", "no numérico": "not numeric", "no reconocido": "not recognized",
    "Selector": "Selector", "Texto": "Text", "Serie": "Series", "texto": "text", "selector": "selector",
    "carpeta": "folder", "ancla de pestaña": "tab anchor", "consigna": "setpoint", "Sin lectura válida": "No valid reading",
    # --- tablero de Inicio configurable ---
    "✎ Personalizar tablero": "✎ Customize dashboard",
    "Elige qué indicadores y variables se muestran y con qué tipo de gráfico":
        "Choose which indicators and variables are shown and with which chart type",
    "El tablero está vacío: usa «✎ Personalizar tablero» para agregar indicadores.":
        "The dashboard is empty: use “✎ Customize dashboard” to add indicators.",
    "Valor actual": "Current value", "Gauge": "Gauge", "Barra con límites": "Bar with limits", "Tendencia": "Trend",
    "Histograma (distribución)": "Histogram (distribution)",
    "{chart}\n(clic para ver el detalle)": "{chart}\n(click for details)",
    "Elige una variable (✎ Personalizar)": "Choose a variable (✎ Customize)",
    "La variable ya no existe": "The variable no longer exists", "Ref {v} ({src})": "Ref {v} ({src})",
    "dato viejo": "stale data", "Esperado: {s}": "Expected: {s}", "Datos insuficientes": "Not enough data",
    "n = {n}": "n = {n}", "media {m}": "mean {m}",
    "Personalizar tablero de Inicio": "Customize Home dashboard", "Columnas del tablero:": "Dashboard columns:",
    "<b>Mosaicos</b> (en orden: de izquierda a derecha y de arriba abajo)":
        "<b>Tiles</b> (in order: left to right, top to bottom)",
    "+ Variable": "+ Variable", "+ Indicador": "+ Indicator", "Restablecer tablero por defecto": "Reset to default dashboard",
    "Contenido:": "Content:", "Variables:": "Variables:", "Gráfico:": "Chart:", "Título:": "Title:",
    " col.": " col.", " filas": " rows", "Tamaño (ancho × alto):": "Size (width × height):",
    "Rango de tiempo:": "Time range:", "Escala (mín. / máx.):": "Scale (min / max):", "auto": "auto",
    "Vacío = automática: límites de la receta con margen y datos recientes.":
        "Empty = automatic: recipe limits with margin and recent data.",
    "indicador": "indicator", "texto/selector": "text/selector", "Indicadores": "Indicators",
    "Todos los indicadores del sistema ya están en el tablero.": "All system indicators are already on the dashboard.",
    "Restablecer": "Reset", "¿Reemplazar el tablero por el diseño por defecto?": "Replace the dashboard with the default layout?",
    "Tendencia: hasta {n} variables en la misma gráfica.": "Trend: up to {n} variables in the same chart.",
    "Una variable. Los gráficos disponibles dependen de su tipo: las de texto y los selectores muestran su estado actual.":
        "One variable. The available charts depend on its type: text variables and selectors show their current state.",
    "Ese indicador ya está en el tablero.": "That indicator is already on the dashboard.",
    "La tendencia solo admite variables numéricas.": "Trends only accept numeric variables.",
    "Revisa el tablero": "Check the dashboard",
    "Hay mosaicos de variable sin variable elegida.": "Some variable tiles have no variable selected.",
    "La escala máxima debe ser mayor que la mínima.": "The scale maximum must be greater than the minimum.",
    "✎ Personalizar tablero de Inicio…": "✎ Customize Home dashboard…",
    # --- guardar configuración ---
    "Cambios sin guardar": "Unsaved changes",
    "Hay cambios sin guardar (recorridos, variables u otros ajustes).\n\n¿Salir sin guardar? Se perderán los cambios.":
        "There are unsaved changes (tours, variables or other settings).\n\nLeave without saving? The changes will be lost.",
    "No se puede guardar": "Cannot save", "Corrige primero:": "Fix first:",
    "Se encontraron estos puntos pendientes:": "These items are pending:",
    "¿Guardar de todos modos? Lo que esté incompleto no funcionará hasta corregirlo.":
        "Save anyway? Anything incomplete will not work until it is fixed.",
    "Receta no actualizada": "Recipe not updated",
    "La configuración quedó guardada, pero si cambias de receta y vuelves se cargará la versión anterior. Cierra "
    "programas que tengan abierta la carpeta de datos y vuelve a guardar.":
        "The configuration was saved, but if you switch recipes and come back the previous version will be loaded. "
        "Close programs that have the data folder open and save again.",
    # --- dashboard global ---
    "🌐 Dashboard global (exportación)…": "🌐 Global dashboard (export)…",
    "Dashboard global (exportación)": "Global dashboard (export)",
    "Esta línea escribe su estado, alarmas, eventos y tendencias en una carpeta compartida. El dashboard global "
    "(DashboardGlobal.exe) lee esa carpeta y muestra todas las líneas.\nLa escritura va en un proceso "
    "aparte: si la red falla, el monitoreo sigue y los datos se envían al volver.":
        "This line writes its status, alarms, events and trends to a shared folder. The global dashboard "
        "(DashboardGlobal.exe) reads that folder and shows every line.\nWriting runs separately: if the "
        "network fails, monitoring continues and the data is sent when it comes back.",
    "Exportar al dashboard global": "Export to the global dashboard", "Carpeta compartida:": "Shared folder:",
    "Examinar…": "Browse…", "Nombre de la línea:": "Line name:", "ID de la línea (carpeta):": "Line ID (folder):",
    "Nombre de la carpeta de esta línea; debe ser único en la planta.":
        "Folder name for this line; it must be unique in the plant.",
    "Actualizar el estado cada:": "Update the status every:", "Un punto de tendencia cada:": "One trend point every:",
    "Conservar eventos y tendencias:": "Keep events and trends for:", " días": " days", " s": " s",
    "Probar escritura": "Test write", "Exportación desactivada.": "Export disabled.",
    "Escribiendo en: {p}": "Writing to: {p}", "Indica la carpeta compartida.": "Enter the shared folder.",
    "Carpeta compartida": "Shared folder", "Dashboard global: OK": "Global dashboard: OK",
    "Dashboard global: sin acceso": "Global dashboard: no access",
    "Dashboard global de líneas": "Global line dashboard", "📂 Carpeta compartida…": "📂 Shared folder…",
    "Carpeta compartida de las líneas": "Shared folder of the lines", "Buscar línea…": "Search line…",
    "Todas": "All", "Con alarma o aviso": "With alarm or warning", "Detenidas": "Stopped",
    "Sin comunicación": "No communication", "Gravedad": "Severity", "OEE (menor primero)": "OEE (lowest first)",
    "Orden:": "Sort:", "Líneas": "Lines", "Con alarma": "In alarm", "OEE promedio (turno)": "Average OEE (shift)",
    "En línea": "Online", "Retrasada": "Delayed", "Programa cerrado": "Program closed",
    "Monitoreando": "Monitoring", "Monitoreo detenido": "Monitoring stopped", "OEE sin configurar": "OEE not set up",
    "✔ Sin alarmas": "✔ No alarms", "{n} alarmas": "{n} alarms", "{n} avisos": "{n} warnings",
    "Actualizado {a}": "Updated {a}", "hace": "ago", "hace {n} s": "{n} s ago", "hace {n} min": "{n} min ago",
    "hace {n} h": "{n} h ago", "hace {n} días": "{n} days ago", "(sin elegir)": "(not chosen)",
    "Alarmas activas": "Active alarms", "Elige una línea para ver su detalle.": "Choose a line to see its details.",
    "<b>Alarmas y avisos recientes de la planta</b>": "<b>Recent plant alarms and warnings</b>",
    "Elige la carpeta compartida donde escriben las líneas (📂 Carpeta compartida…).":
        "Choose the shared folder the lines write to (📂 Shared folder…).",
    "Ninguna línea ha escrito todavía en esta carpeta.": "No line has written to this folder yet.",
    "No se puede leer la carpeta: {e}": "Cannot read the folder: {e}",
    "Paros: <b>{s}</b> · microparos: <b>{m}</b>": "Stops: <b>{s}</b> · microstops: <b>{m}</b>",
    "{n} puntos (media por minuto; la banda es el mínimo y máximo)":
        "{n} points (per-minute mean; the band is the minimum and maximum)",
    # --- dashboard global: configuración e indicadores ---
    "Barra": "Bar", "Gráfica de tiempo": "Time chart", "Indicador (OEE, calidad, Cpk…)": "Indicator (OEE, quality, Cpk…)",
    "Producción del turno": "Shift production", "Configuración del dashboard global": "Global dashboard settings",
    "Restablecer indicadores por defecto": "Reset to default indicators",
    "Indicadores (todas las líneas)": "Indicators (all lines)", "Por línea": "Per line",
    "Carpeta de datos de las líneas:": "Line data folder:", "Carpeta de datos de las líneas": "Line data folder",
    "Actualizar cada:": "Refresh every:", "«Sin comunicación» después de:": "“No communication” after:",
    "Columnas por tarjeta:": "Columns per card:", "Agrupar las líneas por área": "Group lines by area",
    "Sonido": "Sound", "Cuando una línea entra en alarma": "When a line goes into alarm",
    "Cuando una línea se detiene": "When a line stops",
    "Cuando una línea pierde comunicación": "When a line loses communication",
    "Modo TV: cambiar de página cada:": "TV mode: change page every:",
    "(la que publica la línea)": "(the one published by the line)", "Área:": "Area:",
    "Indicadores propios para esta línea": "Own indicators for this line",
    "Variable por su ID (o nombre). Las líneas del mismo tipo la comparten; si una línea no la tiene, el indicador lo indica.":
        "Variable by its ID (or name). Lines of the same type share it; if a line lacks it, the indicator says so.",
    "Estos indicadores se muestran en la tarjeta de todas las líneas. Si una línea es distinta, dale indicadores "
    "propios en la pestaña «Por línea».":
        "These indicators are shown on every line's card. If a line is different, give it its own indicators in the "
        "“Per line” tab.",
    "Ancho de cada tarjeta, en columnas de indicadores.": "Width of each card, in indicator columns.",
    "Columnas de indicadores de cada tarjeta. El tamaño de las tarjetas y de sus indicadores se ajusta solo al ancho de la ventana.":
        "Indicator columns of each card. The size of the cards and of their indicators adjusts itself to the window width.",
    "<b>Avisos</b> (la tarjeta parpadea hasta que se le da clic)": "<b>Alerts</b> (the card blinks until it is clicked)",
    "<b>Indicadores de la tarjeta</b> (1 a {n}, en orden)": "<b>Card indicators</b> (1 to {n}, in order)",
    "Cada línea admite hasta {n} indicadores.": "Each line supports up to {n} indicators.",
    "La tarjeta necesita al menos un indicador.": "The card needs at least one indicator.",
    "(ninguna línea ha escrito en la carpeta todavía)": "(no line has written to the folder yet)",
    "(sin área)": "(no area)", "Falta la carpeta": "Folder missing",
    "Indica la carpeta donde escriben las líneas.": "Enter the folder the lines write to.",
    "Indicador:": "Indicator:", "Periodo:": "Period:", "Turno actual": "Current shift", "+ Agregar": "+ Add",
    "<b>Líneas</b>": "<b>Lines</b>", "Sin datos aún": "No data yet",
    "conforme {g} · paros {s}": "conforming {g} · stops {s}", "No existe en esta línea": "Not available on this line",
    "Ahora": "Now", "Sin área": "No area", "Alarmas activas": "Active alarms",
    "⚙ Configuración": "⚙ Settings", "Carpeta de datos, indicadores, áreas y avisos": "Data folder, indicators, areas and alerts",
    "✔ Reconocer avisos": "✔ Acknowledge alerts", "Detiene el parpadeo de las tarjetas": "Stops the cards from blinking",
    "Detiene el parpadeo de las tarjetas (Ctrl+K)": "Stops the cards from blinking (Ctrl+K)",
    "⤓ Exportar CSV": "⤓ Export CSV", "Estado y OEE de todas las líneas": "Status and OEE of every line",
    "📺 Modo TV (F11)": "📺 TV mode (F11)", "Pantalla completa con páginas que rotan": "Full screen with rotating pages",
    "Elige la carpeta donde escriben las líneas (⚙ Configuración).": "Choose the folder the lines write to (⚙ Settings).",
    "Exportar resumen de líneas": "Export line summary", "entró en alarma": "went into alarm", "se detuvo": "stopped",
    "perdió comunicación": "lost communication", "Página {p} de {n}": "Page {p} of {n}", "{n} líneas": "{n} lines",
    "{n} con alarma": "{n} in alarm", "Área / nave:": "Area / building:", "p. ej. Nave 2": "e.g. Building 2",
    "Carpeta": "Folder", "&Archivo": "&File", "Variable:": "Variable:", "Rango:": "Range:",
    "linea": "line", "area": "area", "comunicacion": "communication", "estado": "status", "receta": "recipe",
    "disponibilidad_%": "availability_%", "rendimiento_%": "performance_%", "calidad_%": "quality_%",
    "producido": "produced", "conforme": "conforming", "unidad": "unit", "paros": "stops", "alarmas": "alarms",
    "avisos": "warnings", "actualizado": "updated",
    # --- indicadores ---
    "Disponibilidad (turno)": "Availability (shift)", "Rendimiento (turno)": "Performance (shift)",
    "Calidad (turno)": "Quality (shift)",
    "Tiempo en marcha / tiempo planificado del turno": "Running time / planned time of the shift",
    "Velocidad real promedio / velocidad nominal del turno": "Average actual speed / nominal speed of the shift",
    "Metros conformes / metros producidos en el turno": "Conforming meters / meters produced in the shift",
    "detenido {d}": "stopped {d}", "{v} de {n} promedio": "{v} of {n} average",
    "{g} de {t} conformes": "{g} of {t} conforming", "Gauge": "Gauge",
    "🌐 Idioma / Language": "🌐 Language / Idioma",
    # --- niveles y reglas ---
    "AJUSTE_RECETA": "RECIPE_SETTING", "CAMBIO_AJUSTE": "SETTING_CHANGE", "CAMBIO_SELECTOR": "SELECTOR_CHANGE",
    "COMPORTAMIENTO": "BEHAVIOR", "LECTURA": "READING", "PANTALLA": "SCREEN", "RECETA": "RECIPE",
    "RECETA_HMI": "HMI_RECIPE", "RECORRIDO": "TOUR", "REPORTE": "REPORT", "SIN_RECETA": "NO_RECIPE",
    "TENDENCIA": "TREND", "TOLERANCIA": "TOLERANCE", "CONFORME": "CONFORMING", "NO CONFORME": "NON-CONFORMING",
    "sin evaluación": "not evaluated", "SIN EVALUACIÓN": "NOT EVALUATED",
    # --- mensajes del motor sin valores ---
    "No hay receta activa: solo se registran valores": "No active recipe: values are only recorded",
    "Pantalla disponible de nuevo: se reanuda la lectura": "Screen available again: reading resumes",
    "los clics automáticos solo están disponibles en Windows": "automatic clicks are only available on Windows",
    "el operador está usando el HMI": "the operator is using the HMI", "Solo disponible en Windows": "Only available on Windows",
    "regreso de emergencia": "emergency return", "regreso": "return", "detenido": "stopped",
    "carácter dudoso dentro del número": "doubtful character inside the number", "no numérico": "not numeric",
    "variantes en desacuerdo": "variants disagree", "sin lectura válida": "no valid reading",
    "página no visible": "page not visible", "faltan datos de entrada": "missing input data",
    "resultado no válido (p. ej. división entre 0)": "invalid result (e.g. division by 0)",
    "salto sin confirmar": "unconfirmed jump", "selector sin estados capturados": "selector without captured states",
    "sin datos recientes": "no recent data",
    "la pantalla está en negro (sesión bloqueada o escritorio remoto desconectado)":
        "the screen is black (locked session or disconnected remote desktop)",
    "punto atípico (>3σ)": "outlier (>3σ)",
    "9 subgrupos del mismo lado de la referencia": "9 subgroups on the same side of the reference",
    "6 subgrupos en aumento": "6 subgroups increasing", "6 subgrupos en descenso": "6 subgroups decreasing",
    "La fórmula está vacía": "The formula is empty", "Solo se permiten números": "Only numbers are allowed",
    "el mínimo de aviso debe estar dentro del rango de alarma": "the warning minimum must be inside the alarm range",
    "el máximo de aviso debe estar dentro del rango de alarma": "the warning maximum must be inside the alarm range",
    "la tolerancia de aviso debe ser menor o igual que la de alarma":
        "the warning tolerance must be less than or equal to the alarm tolerance",
    "El OCR de Windows solo está disponible en Windows": "Windows OCR is only available on Windows",
    "No hay paquete de idioma OCR instalado en Windows": "No OCR language pack is installed in Windows",
    "No se encontró tesseract.exe": "tesseract.exe was not found",
    "No se pudo codificar la imagen": "The image could not be encoded",
    "el ancho y alto deben ser > 0": "width and height must be > 0",
    "Estado detectado": "Detected state", "Exportar CSV": "Export CSV",
    # --- dock ---
    "▭ Dock al minimizar…": "▭ Dock when minimized…", "▭ Minimizar a dock": "▭ Minimize to dock",
    "Dock al minimizar": "Dock when minimized", "Dock": "Dock",
    "Al minimizar el programa queda una barra compacta, siempre visible sobre el HMI, con el estado de la máquina y "
    "los indicadores elegidos. No aparece en la lectura de pantalla ni estorba a los recorridos. Se arrastra desde la "
    "agarradera (⠿); doble clic en ella restaura el programa.":
        "When the program is minimized a compact bar stays always visible over the HMI, with the machine status and "
        "the chosen indicators. It does not appear in the screen reading and does not get in the way of tours. Drag "
        "it by the grip (⠿); double-click the grip to restore the program.",
    "Mostrar el dock al minimizar": "Show the dock when minimized", "Posición:": "Position:",
    "Superior": "Top", "Inferior": "Bottom", "Izquierda": "Left", "Derecha": "Right",
    "Volver a centrar en el borde": "Center on the edge again",
    "Olvida la posición a la que se arrastró el dock": "Forgets the position the dock was dragged to",
    "Tamaño:": "Size:", "Chico": "Small", "Mediano": "Medium", "Grande": "Large",
    "Grosor:": "Thickness:", "Delgado": "Thin", " px": " px",
    "Con este grosor no caben gráficas: cada indicador se muestra como nombre y valor, con color según su rango.":
        "Charts do not fit at this thickness: each indicator is shown as name and value, colored by its range.",
    "Con menos de {n} px los indicadores pasan a solo valor con color.":
        "Below {n} px the indicators switch to value only, with color.",
    "Al acercar el mouse se desvanece y deja pasar los clics al HMI":
        "When the mouse approaches it fades out and lets clicks through to the HMI",
    "Parpadear y mostrar el mensaje al aparecer una alarma": "Blink and show the message when an alarm appears",
    "<b>Indicadores del dock</b> (en orden)": "<b>Dock indicators</b> (in order)",
    "Restaurar el programa": "Restore the program",
    "Arrastra para mover el dock · doble clic para restaurar el programa":
        "Drag to move the dock · double-click to restore the program",
    # --- menús (misma estructura en el monitor y en el dashboard global) ---
    "Configurar receta": "Recipe setup", "A&cciones": "&Actions", "C&onfiguración": "&Settings", "&Líneas": "&Lines",
    "📋 Recetas y límites…": "📋 Recipes and limits…", "Configuración de la receta": "Recipe configuration",
    "Reportes automáticos…": "Automatic reports…", "Lectura y análisis (general)…": "Reading and analysis (general)…",
    "🧠 Comportamiento (entrenar)…": "🧠 Behavior (train)…", "✎ Tablero de Inicio…": "✎ Home dashboard…",
    "⟳ Actualizar ahora": "⟳ Refresh now", "⤓ Exportar resumen a CSV…": "⤓ Export summary to CSV…",
    "Indicadores de las tarjetas…": "Card indicators…", "Líneas y áreas…": "Lines and areas…",
    "Filtro": "Filter", "Orden": "Sort", "Agrupar por área": "Group by area",
    "🔔 Sonido de avisos": "🔔 Alert sound", "⚙ Carpeta de datos y avisos…": "⚙ Data folder and alerts…",
    "Panel de detalle de la línea": "Line detail panel", "Panel de alarmas de la planta": "Plant alarms panel",
    "📺 Modo TV": "📺 TV mode",
    "<b>Dashboard global de líneas</b><br>Estado, indicadores y alarmas de todas las líneas a partir de la carpeta "
    "de datos compartida.<br>Solo lee los archivos que publican las líneas: no modifica nada en ellas.":
        "<b>Global line dashboard</b><br>Status, indicators and alarms of every line from the shared data folder."
        "<br>It only reads the files the lines publish: it changes nothing on them.",
    "coma": "comma", "punto": "point", "real": "actual", "— elegir —": "— choose —", "— ninguno —": "— none —",
    "calibre=12 AWG; material=PVC; color=negro": "gauge=12 AWG; material=PVC; color=black",
    "Aceptar": "OK", "Cancelar": "Cancel",
    "Sin lectura válida": "No valid reading", "Fórmula válida →": "Valid formula →", "Entrenado": "Trained",
    "Nombre de la pestaña:": "Tab name:", "Nombre de la variable (p. ej. «Cylinder 1»):": "Variable name (e.g. “Cylinder 1”):",
    "Lectura débil: ajusta la región (solo el número, sin la unidad).":
        "Weak reading: adjust the region (the number only, without the unit).",
    # --- versiones y respaldos ---
    "Versión": "Version", "🛟 Crear respaldo de la configuración": "🛟 Back up the configuration",
    "📂 Abrir carpeta de respaldos": "📂 Open backups folder", "Respaldo": "Backup", "Respaldo creado": "Backup created",
    "No se pudo crear el respaldo": "The backup could not be created",
}

# Textos con valores: la clave es la plantilla en español («{}» = valor) y el resultado su traducción.
# Los valores capturados también se traducen si son, a su vez, un texto conocido.
EN_PATTERNS: dict[str, str] = {
    # --- avisos de la interfaz ---
    "¿Eliminar el modelo «{}»?": "Delete the model “{}”?", "¿Eliminar la receta «{}»?": "Delete the recipe “{}”?",
    "¿Eliminar el reporte «{}»?": "Delete the report “{}”?", "¿Eliminar el recorrido «{}»?": "Delete the tour “{}”?",
    "¿Eliminar {} pestañas y {} variables?": "Delete {} tabs and {} variables?",
    "¿Eliminar {} pestañas?": "Delete {} tabs?", "¿Eliminar {} variables?": "Delete {} variables?",
    "Ya existe la receta «{}».": "The recipe “{}” already exists.",
    "Ya existe una variable con ID «{}».": "A variable with ID “{}” already exists.",
    "Al guardar, «{}» tendrá la configuración actual completa (variables, pantallas, recorridos, OEE, reportes y "
    "comportamientos).": "On save, “{}” will get the complete current configuration (variables, screens, tours, OEE, "
                        "reports and behaviors).",
    "Reporte «{}»: no tiene variables": "Report “{}”: it has no variables", "Valor de «{}»": "Value of “{}”",
    "No se pudo generar: {}": "Could not generate: {}", "Selección: x={} y={} {}×{}": "Selection: x={} y={} {}×{}",
    "Nombre de la pestaña dentro de «{}»:": "Name of the tab inside “{}”:",
    "Nombre de la variable dentro de «{}» (p. ej. «Cylinder 1»):": "Name of the variable inside “{}” (e.g. “Cylinder 1”):",
    "① Marca la región de la CONSIGNA de «{}» (Esc para cancelar)": "① Mark the SETPOINT region of “{}” (Esc to cancel)",
    "② Ahora marca la región de la MEDICIÓN (valor real) de «{}»": "② Now mark the MEASUREMENT (actual value) region of “{}”",
    "Se crearon {} variables.": "{} variables were created.", "Expresión (usa los ID):\n{}": "Expression (use the IDs):\n{}",
    "con los valores actuales ({})": "with the current values ({})",
    "Fórmula válida. Usa: {}. Para ver el resultado inicia el monitoreo (faltan: {}).":
        "Valid formula. Uses: {}. Start monitoring to see the result (missing: {}).",
    "Se aprendieron {} caracteres. Conocidos: {}": "{} characters were learned. Known: {}",
    "Motor {} (automático): texto «{}»": "Engine {} (automatic): text “{}”",
    "Motor {} (automático):": "Engine {} (automatic):",
    "Motor {}: texto «{}» · confianza {}": "Engine {}: text “{}” · confidence {}",
    "Motor {} (motor «{}» no disponible{}; se usa «{}»): texto «{}» · confianza {}":
        "Engine {} (engine “{}” not available{}; using “{}”): text “{}” · confidence {}",
    "en {} variantes. Ajusta la región para que cubra solo el número.":
        "in {} variants. Adjust the region so that it covers only the number.",
    "· {} de {} variantes coinciden ({} %)": "· {} of {} variants agree ({} %)",
    "· {} de {} variantes coinciden ({} %) · otras lecturas: {}": "· {} of {} variants agree ({} %) · other readings: {}",
    "· coincidencias: {}": "· matches: {}", "esperado: {}": "expected: {}", "Estado detectado: {}": "Detected state: {}",
    "Valor inválido: {}": "Invalid value: {}", "Error OCR: {}": "OCR error: {}",
    "con {} muestras del {} al {} (cada {} s). Umbral D² = {}.": "with {} samples from {} to {} (every {} s). D² threshold = {}.",
    "débiles ·": "weak ·", "sin lectura (solo variables de las pestañas visibles)": "no reading (only variables on visible tabs)",
    "Pestañas sin imagen ancla: {}": "Tabs without anchor image: {}",
    "Recorrido: {} clics sin imagen del botón; vuelve a grabarlos": "Tour: {} clicks without button image; record them again",
    "{} clics sin imagen del botón: vuelve a grabarlos": "{} clicks without button image: record them again",
    # --- validación de la configuración ---
    "IDs de página duplicados: {}": "Duplicate page IDs: {}", "IDs de variable duplicados: {}": "Duplicate variable IDs: {}",
    "Página «{}»: el padre '{}' no existe": "Page “{}”: parent '{}' does not exist",
    "Página «{}»: el árbol tiene un ciclo": "Page “{}”: the tree has a cycle",
    "{}: la página '{}' no existe": "{}: page '{}' does not exist", "{}: la consigna '{}' no existe": "{}: setpoint '{}' does not exist",
    "{}: '{}' no es de tipo consigna": "{}: '{}' is not a setpoint", "{}: la pestaña '{}' no existe": "{}: tab '{}' does not exist",
    "{}: no tiene pasos": "{}: it has no steps", "{} paso {}: la pestaña '{}' no existe": "{} step {}: tab '{}' does not exist",
    "{} paso {}: «{}» necesita un ancla para verificar la llegada": "{} step {}: “{}” needs an anchor to verify arrival",
    "{} paso {}: no tiene clics grabados": "{} step {}: it has no recorded clicks",
    "{}: graba los clics de regreso": "{}: record the return clicks", "{}: la variable '{}' no existe": "{}: variable '{}' does not exist",
    "{}: el disparador necesita una variable existente": "{}: the trigger needs an existing variable",
    "{}: el recorrido '{}' no existe": "{}: tour '{}' does not exist",
    "{}: la variable del nombre de archivo no existe": "{}: the file-name variable does not exist",
    "La variable de nombre de receta '{}' debe existir y ser de tipo texto": "The recipe-name variable '{}' must exist and be of type text",
    "Fórmula «{}»: {}": "Formula “{}”: {}", "Sintaxis inválida: {}": "Invalid syntax: {}",
    "Variable desconocida: «{}»": "Unknown variable: “{}”", "Elemento no permitido en la fórmula: {}": "Element not allowed in the formula: {}",
    "Solo se permiten las funciones: {}": "Only these functions are allowed: {}", "Referencia circular: {}": "Circular reference: {}",
    "el mínimo de {} es mayor que el máximo": "the {} minimum is greater than the maximum",
    "Recorrido «{}»": "Tour “{}”", "Reporte «{}»": "Report “{}”",
    # --- hallazgos y eventos del motor ---
    "Normalizado: {}": "Back to normal: {}", "«{}»: {}": "“{}”: {}",
    "«{}»: valor {} fuera de límites ({})": "“{}”: value {} out of limits ({})",
    "«{}»: consigna {} fuera de límites ({})": "“{}”: setpoint {} out of limits ({})",
    "Ajuste erróneo «{}»: consigna {} fuera de límites ({})": "Wrong setting “{}”: setpoint {} out of limits ({})",
    "Ajuste erróneo «{}»: consigna {}, receta {} (Δ {}, tolerancia ±{})": "Wrong setting “{}”: setpoint {}, recipe {} (Δ {}, tolerance ±{})",
    "«{}» fuera de tolerancia: {} vs receta {} (Δ {}, tolerancia ±{})": "“{}” out of tolerance: {} vs recipe {} (Δ {}, tolerance ±{})",
    "«{}» fuera de tolerancia: {} vs consigna {} (Δ {}, tolerancia ±{})": "“{}” out of tolerance: {} vs setpoint {} (Δ {}, tolerance ±{})",
    "«{}» tiende a salir de tolerancia en ~{} min ({}/min)": "“{}” is trending out of tolerance in ~{} min ({}/min)",
    "mín {}": "min {}", "máx {}": "max {}", "mín {}, máx {}": "min {}, max {}",
    "No se puede leer «{}» ({})": "Cannot read “{}” ({})",
    "El HMI muestra la receta «{}» pero la activa es «{}»": "The HMI shows recipe “{}” but the active one is “{}”",
    "Cambio de selector «{}»: {} → {}": "Selector change “{}”: {} → {}",
    "Selector «{}» en «{}»; la receta espera «{}»": "Selector “{}” at “{}”; the recipe expects “{}”",
    "Cambio de ajuste «{}»: {} → {}": "Setting change “{}”: {} → {}",
    "Cambio de ajuste «{}»: {} → {} (fuera de los límites de la receta)": "Setting change “{}”: {} → {} (outside the recipe limits)",
    "Cambio de ajuste «{}»: {} → {} (dentro de receta)": "Setting change “{}”: {} → {} (within recipe)",
    "Cambio de ajuste «{}»: {} → {} (se aleja de la receta: {})": "Setting change “{}”: {} → {} (moving away from the recipe: {})",
    "Comportamiento «{}»: {}": "Behavior “{}”: {}",
    "desviación {}× lo normal; principal: {}": "deviation {}× normal; main: {}",
    "{} fuera de su variación normal (z={})": "{} outside its normal variation (z={})",
    "se rompió la relación {} ↔ {} ({}σ)": "the relation {} ↔ {} broke ({}σ)",
    "Receta activa: {}": "Active recipe: {}", "Receta activa: ninguna": "Active recipe: none",
    "Receta activa: {} (configuración completa de la receta cargada)": "Active recipe: {} (complete recipe configuration loaded)",
    "Receta activa: {} (se le asignó la configuración actual)": "Active recipe: {} (the current configuration was assigned to it)",
    "El HMI muestra la receta «{}»; cárgala manualmente (modo manual)": "The HMI shows recipe “{}”; load it manually (manual mode)",
    "La receta «{}» que muestra el HMI no existe en el programa; se mantiene «{}»":
        "The recipe “{}” shown by the HMI does not exist in the program; “{}” is kept",
    "No se pudo guardar la configuración en la receta «{}»: {}": "The configuration could not be saved to recipe “{}”: {}",
    "Pantalla no disponible: {}. Se conservan los últimos datos.": "Screen not available: {}. The last data is kept.",
    "Pantalla no disponible: {}": "Screen not available: {}", "Fallo de captura: {}": "Capture failure: {}",
    "no se puede capturar la pantalla ({})": "cannot capture the screen ({})",
    "la resolución actual es {}×{} y las regiones se configuraron en {}×{}; conéctate al HMI con esa resolución (en "
    "Escritorio remoto: Mostrar → Configuración de pantalla)":
        "the current resolution is {}×{} and the regions were set up at {}×{}; connect to the HMI with that resolution "
        "(in Remote Desktop: Display → Display configuration)",
    "Reporte «{}» falló: {}": "Report “{}” failed: {}", "Reporte «{}» ({}): {}": "Report “{}” ({}): {}",
    # --- recorridos ---
    "Recorrido «{}»: {}": "Tour “{}”: {}", "Recorrido «{}» {}": "Tour “{}” {}", "Recorrido «{}» en {} s: {}": "Tour “{}” in {} s: {}",
    "{} pantallas leídas": "{} screens read", "{} pantallas leídas ({})": "{} screens read ({})",
    "{} pasos ejecutados": "{} steps executed", "{} pasos ejecutados ({})": "{} steps executed ({})",
    "cada {} s": "every {} s", "fuera de «{}» {} s": "away from “{}” {} s", "selector {} → {}": "selector {} → {}",
    "valor bajó a {}": "value dropped to {}", "pospuesto: {}": "postponed: {}",
    "pospuesto: operador activo hace {} s": "postponed: operator active {} s ago",
    "pospuesto: el HMI no está en «{}»": "postponed: the HMI is not at “{}”",
    "paso {}": "step {}", "paso {}: no se llegó a «{}»": "step {}: “{}” was not reached",
    "regreso: no se llegó a «{}»": "return: “{}” was not reached",
    "{}, clic {}: el botón no coincide con el grabado ({})": "{}, click {}: the button does not match the recorded one ({})",
    "{} · se regresó a la pantalla de inicio": "{} · returned to the home screen",
    "{} · no se pudo regresar a la principal ({})": "{} · could not return to the main screen ({})",
    "la ventana del monitor tapa el botón en ({}, {}); muévela o minimízala":
        "the monitor window covers the button at ({}, {}); move or minimize it",
    "fuera de rango válido ({})": "outside the valid range ({})", "estado no reconocido (mejor «{}» {})": "state not recognized (best “{}” {})",
    # --- comportamiento / OCR ---
    "Sin datos en el periodo para: {}": "No data in the period for: {}",
    "Solo hay {} muestras alineadas; se necesitan al menos {}. Amplía el periodo o reduce la resolución.":
        "There are only {} aligned samples; at least {} are needed. Widen the period or reduce the resolution.",
    "No se pudo pasar la imagen al OCR de Windows: {}": "The image could not be passed to Windows OCR: {}",
    "El OCR de Windows no pasó la autoprueba (leyó «{}»)": "Windows OCR did not pass the self-test (it read “{}”)",
    "Paquetes winrt no disponibles: {}": "winrt packages not available: {}",
    "El OCR de Windows falló en la autoprueba: {}": "Windows OCR failed the self-test: {}",
    "Se detectaron {} caracteres en la imagen pero el texto tiene {}. Ajusta la región o el umbral.":
        "{} characters were detected in the image but the text has {}. Adjust the region or the threshold.",
    "No se pudo leer la imagen {}": "The image {} could not be read",
}
