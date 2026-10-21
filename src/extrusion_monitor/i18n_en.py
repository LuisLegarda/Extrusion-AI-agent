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
    # --- cámaras e indicadores físicos ---
    "Fuente:": "Source:", "Fuente": "Source", "📹 Cámaras…": "📹 Cameras…", "📷 Capturar": "📷 Capture",
    "Pantalla del HMI o una cámara que mira el tablero del equipo": "HMI screen or a camera looking at the machine panel",
    "Agregar o ajustar cámaras (USB o IP) para equipos sin pantalla legible":
        "Add or adjust cameras (USB or IP) for machines without a readable screen",
    "🖥 Pantalla del HMI": "🖥 HMI screen", "cámara": "camera", "Cámara": "Camera", "Cámaras": "Cameras",
    "Lectura": "Reading", "Probar lectura": "Test reading", "Indicadores físicos:": "Physical indicators:",
    "+ Luz / LED": "+ Light / LED", "+ Torre andon…": "+ Andon tower…", "+ Display 7 seg.": "+ 7-seg display",
    "+ Aguja": "+ Needle", "+ Barra de nivel": "+ Level bar",
    "Luz piloto, LED o una luz de torre andon: se reconoce por su color (y si parpadea)":
        "Pilot light, LED or an andon tower light: recognized by its color (and whether it blinks)",
    "Marca toda la torre: se crea una luz por cada color": "Mark the whole tower: one light is created per color",
    "Display de 7 segmentos de un controlador, sensor o contador (LED o LCD)":
        "7-segment display of a controller, sensor or counter (LED or LCD)",
    "Manómetro, termómetro de carátula o tacómetro": "Pressure gauge, dial thermometer or tachometer",
    "Bargraph de LED o indicador de nivel": "LED bargraph or level indicator",
    "Texto / números (OCR)": "Text / numbers (OCR)", "Display de 7 segmentos (LED o LCD)": "7-segment display (LED or LCD)",
    "Aguja (manómetro, carátula)": "Needle (gauge, dial)", "Barra de nivel / bargraph": "Level bar / bargraph",
    "display 7 seg.": "7-seg display", "aguja": "needle", "barra de nivel": "level bar", "luz / andon": "light / andon",
    "Reconocer": "Recognize", "Por imagen (forma y color)": "By image (shape and color)",
    "Por color (luz, LED, andon)": "By color (light, LED, andon)",
    "Por color tolera mejor los cambios de luz de una cámara y detecta el parpadeo":
        "By color copes better with a camera's lighting changes and detects blinking",
    "Detectar parpadeo (agrega «… parpadeando»)": "Detect blinking (adds “… blinking”)",
    "Ventana de parpadeo": "Blink window",
    "Ventana para decidir si parpadea (al menos dos encendidos y apagados)":
        "Window used to decide whether it blinks (at least two on/off changes)",
    "Display de 7 segmentos": "7-segment display", "Dígitos": "Digits", "automático": "automatic",
    "automática": "automatic", "Tipo de display": "Display type", "segmentos encendidos (LED)": "lit segments (LED)",
    "segmentos oscuros (LCD)": "dark segments (LCD)", "Inclinación": "Slant",
    "Marca solo los dígitos (sin unidades ni marco). Si el punto decimal no se ve, indica los decimales y activa «Reinsertar punto decimal».":
        "Mark only the digits (no units or frame). If the decimal point is not visible, set the decimals and enable “Reinsert decimal point”.",
    "Aguja": "Needle", "🎯 Calibrar: centro, mínimo y máximo (3 clics)": "🎯 Calibrate: center, minimum and maximum (3 clicks)",
    "Calibración": "Calibration", "Valor en la marca mínima": "Value at the minimum mark",
    "Valor en la marca máxima": "Value at the maximum mark", "aguja oscura": "dark needle", "aguja clara": "light needle",
    "Barra de nivel": "Level bar", "Dirección": "Direction", "sube (de abajo hacia arriba)": "rises (bottom to top)",
    "baja": "falls", "hacia la derecha": "to the right", "hacia la izquierda": "to the left", "Valor vacío": "Empty value",
    "Valor lleno": "Full value", "Relleno": "Fill", "lo lleno es claro / encendido": "filled part is bright / lit",
    "lo lleno es oscuro": "filled part is dark", "lista": "ready", "sin calibrar": "not calibrated",
    "Nueva luz / LED": "New light / LED", "Nuevo display de 7 segmentos": "New 7-segment display",
    "Nueva aguja": "New needle", "Nueva barra de nivel": "New level bar", "Nombre:": "Name:",
    "Torre andon": "Andon tower", "Colores de arriba hacia abajo, separados por coma:":
        "Colors from top to bottom, separated by commas:", "Rojo, Ámbar, Verde": "Red, Amber, Green",
    "Ahora enseña sus colores: con la luz apagada pulsa «Capturar estado actual como…» → «Apagado»; enciéndela y repite con su color.":
        "Now teach its colors: with the light off press “Capture current state as…” → “Off”; turn it on and repeat with its color.",
    "Torre creada. Enseña cada luz: «Capturar estado actual como…» con la luz apagada («Apagado») y encendida (su color).":
        "Tower created. Teach each light: “Capture current state as…” with the light off (“Off”) and on (its color).",
    "① Clic en el CENTRO (eje) de la aguja · Esc para cancelar": "① Click the CENTER (pivot) of the needle · Esc to cancel",
    "② Clic en la marca del valor MÍNIMO de la escala": "② Click the MINIMUM value mark of the scale",
    "③ Clic en la marca del valor MÁXIMO": "③ Click the MAXIMUM value mark",
    "Enseña al menos dos estados: apagado y encendido.": "Teach at least two states: off and on.",
    "Estado detectado": "Detected state", "distancia de color": "color distance",
    "El parpadeo se detecta durante el monitoreo (varios cuadros por segundo).":
        "Blinking is detected while monitoring (several frames per second).",
    "Display": "Display", "confianza": "confidence", "inclinación": "slant", "segmentos encendidos": "lit segments",
    "segmentos oscuros": "dark segments",
    "Ajusta la región para que cubra solo los dígitos, con poco margen.":
        "Adjust the region so it covers only the digits, with a small margin.",
    "Calibra la aguja: centro, marca mínima y marca máxima.": "Calibrate the needle: center, minimum mark and maximum mark.",
    "Nivel no distinguible": "Level cannot be distinguished", "Nivel": "Level", "Cámara sin imagen": "Camera without image",
    "📹 Cámaras (equipos sin pantalla)…": "📹 Cameras (machines without a screen)…",
    "Usa una cámara cuando el equipo no tiene una pantalla que se pueda capturar: displays de 7 segmentos o LCD, luces, torres andon, manómetros o barras de nivel. Colócala fija y de frente, con luz constante y sin reflejos; luego marca las variables sobre su imagen en el configurador.":
        "Use a camera when the machine has no screen that can be captured: 7-segment or LCD displays, lights, andon towers, gauges or level bars. Mount it fixed and facing the panel, with steady light and no glare; then mark the variables on its image in the configurator.",
    "+ Agregar": "+ Add", "Quitar": "Remove", "🔍 Buscar cámaras USB": "🔍 Find USB cameras", "Resolución": "Resolution",
    "Automática": "Automatic", "Rotación": "Rotation", "Exposición manual": "Manual exposure", "Análisis": "Analysis",
    " cuadros/s": " frames/s", "⬚ Corregir perspectiva (4 clics)": "⬚ Correct perspective (4 clicks)",
    "Quitar corrección": "Remove correction", "▶ Vista en vivo": "▶ Live view", "📷 Tomar imagen": "📷 Take image",
    "Imagen de la cámara (rotada):": "Camera image (rotated):",
    "Resultado (sobre esta imagen se marcan las variables):": "Result (variables are marked on this image):",
    "Si la cámara no está de frente: haz clic en las 4 esquinas del tablero o display y la imagen se endereza":
        "If the camera is not facing the panel: click the 4 corners of the panel or display and the image is straightened",
    "Los LED y displays brillantes se «queman» con la exposición automática: baja la exposición hasta que los segmentos se vean nítidos.":
        "LEDs and bright displays get “burned out” with automatic exposure: lower the exposure until the segments look sharp.",
    "En cámaras USB de Windows suele ir de -13 (muy oscura) a -1 (clara)":
        "On Windows USB cameras it usually ranges from -13 (very dark) to -1 (bright)",
    "Número de la cámara USB (0, 1…), dirección de una cámara IP (rtsp://usuario:clave@ip:554/…, http://ip/video) o «demo» (tablero simulado)":
        "USB camera number (0, 1…), IP camera address (rtsp://user:password@ip:554/…, http://ip/video) or “demo” (simulated panel)",
    "Buscando cámaras USB…": "Searching for USB cameras…", "Cámaras USB encontradas: ": "USB cameras found: ",
    "ninguna": "none", "Sin imagen": "No image", "perspectiva corregida": "perspective corrected", "Imagen": "Image",
    "Haz clic en la esquina": "Click the corner", "superior izquierda": "top left", "superior derecha": "top right",
    "inferior derecha": "bottom right", "inferior izquierda": "bottom left", "Quitar cámara": "Remove camera",
    "Apagado": "Off", "Cámara del tablero": "Panel camera", "Espejo": "Mirror", "sin espejo": "no mirror",
    "espejo horizontal": "horizontal mirror", "espejo vertical": "vertical mirror", "Controlador": "Driver",
    "DirectShow (más compatible)": "DirectShow (most compatible)", "Media Foundation": "Media Foundation",
    "Solo para cámaras USB en Windows: si una cámara no abre o se ve mal, prueba el otro":
        "Only for USB cameras on Windows: if a camera does not open or looks wrong, try the other one",
    "Enfoque fijo": "Fixed focus", "Brillo manual": "Manual brightness",
    "El autoenfoque suele «buscar» con los reflejos del vidrio: fíjalo cuando se vea nítido":
        "Autofocus tends to “hunt” with glass reflections: fix it once the image is sharp", "luz sin colores enseñados": "light without taught colors",
    "aguja no encontrada": "needle not found", "nivel no distinguible": "level cannot be distinguished",
    # --- servidor propio ---
    "Servidor propio (nube o servidor de planta)": "Own server (cloud or plant server)",
    "Enviar también al servidor": "Also send to the server", "Dirección del servidor:": "Server address:",
    "Clave de la línea:": "Line key:", "se obtiene con «Registrar esta línea…»": "obtained with “Register this line…”",
    "Registrar esta línea…": "Register this line…", "Registrar esta línea": "Register this line",
    "Pide la clave de registro del servidor (la tiene el administrador) y obtiene la clave de esta línea":
        "Asks for the server registration key (the administrator has it) and obtains this line's key",
    "Enviar el estado cada:": "Send the status every:",
    "Verificar el certificado HTTPS (desactívalo solo con certificados internos de prueba)":
        "Verify the HTTPS certificate (turn it off only with internal test certificates)",
    "Probar conexión": "Test connection",
    "Primero se guarda en disco y luego se envía: si la red falla, los datos esperan y se envían al volver. El servidor nunca envía órdenes a esta PC.":
        "Data is saved to disk first and then sent: if the network fails, it waits and is sent when it comes back. The server never sends commands to this PC.",
    "Indica la dirección del servidor.": "Enter the server address.", "Clave de registro del servidor:": "Server registration key:",
    "Sin enviar": "Not sent", "Conectando…": "Connecting…",
    # --- problemas de proceso ---
    "Problemas de proceso": "Process problems", "Últimos 30 días": "Last 30 days", "Últimos 90 días": "Last 90 days",
    "Últimas 24 h": "Last 24 h", "Últimos 7 días": "Last 7 days", "Problema de calidad": "Quality problem",
    "Problemas de calidad": "Quality problems", "Categoría:": "Category:", "Causa / defecto:": "Cause / defect:",
    "Causa / defecto": "Cause / defect", "Categoría": "Category", "Causa": "Cause", "Defecto": "Defect",
    "📊 Análisis (Pareto)": "📊 Analysis (Pareto)",
    "Clic en un paro (rojo) para seleccionarlo; arrastra las manijas o usa las barras para ajustar el inicio y el fin.":
        "Click a stop (red) to select it; drag the handles or use the sliders to adjust the start and end.",
    "Paros del turno (de al menos el tiempo del aviso) que aún no tienen causa.":
        "Shift stops (at least the prompt time) that still have no cause.",
    "Clasificar paro": "Classify stop", "Después": "Later",
    "Queda en la lista de paros sin clasificar": "It stays in the list of unclassified stops",
    "(sin operadores: agrégalos en Receta → Causas de paro y defectos)":
        "(no operators: add them in Recipe → Stop causes and defects)",
    "Selecciona el rango de tiempo en la línea de tiempo.": "Select the time range on the timeline.",
    "Elige la categoría y la causa (o el defecto).": "Choose the category and the cause (or the defect).",
    "Elige el operador.": "Choose the operator.", "¿Eliminar la captura seleccionada?": "Delete the selected entry?",
    "Línea": "Line", "Sin datos en el periodo": "No data in the period", "Incluir paros planeados": "Include planned stops",
    "Por causa / defecto": "By cause / defect", "Por categoría": "By category", "Por operador": "By operator",
    "Eliminar captura": "Delete entry",
    "Borra la captura seleccionada en la tabla (por ejemplo, si se capturó mal)":
        "Deletes the entry selected in the table (for example, if it was entered wrong)",
    "Exportar problemas de proceso": "Export process problems", "Doble clic para cambiar un nombre.": "Double-click to rename.",
    "Nueva categoría": "New category", "Causas de paro y defectos": "Stop causes and defects",
    "Catálogos que el operador usa para clasificar los paros y los problemas de calidad. Se guardan con la receta activa. Cambiar un nombre no altera las capturas ya hechas.":
        "Catalogs the operator uses to classify stops and quality problems. They are saved with the active recipe. Renaming does not change entries already made.",
    "Al reanudar la línea, avisar para clasificar el paro": "When the line restarts, prompt to classify the stop",
    "Solo paros de al menos": "Only stops of at least", "Nueva causa": "New cause", "Nuevo defecto": "New defect",
    "Operadores que pueden capturar (aparecen en una lista al capturar):":
        "Operators who can enter data (shown in a list when entering):",
    "Nuevo operador": "New operator", "Paro planeado": "Planned stop",
    "Los paros planeados (cambio de producto, comida…) no cuentan contra la Disponibilidad del OEE.":
        "Planned stops (product change, lunch…) do not count against OEE Availability.",
    "⏸ Causas de paro": "⏸ Stop causes", "✗ Defectos de calidad": "✗ Quality defects",
    "👷 Operadores y aviso": "👷 Operators and prompt", "+ Operador": "+ Operator",
    "Problemas de proceso · todas las líneas": "Process problems · all lines",
    "Las capturas las hace el operador en el monitor de cada línea (Problemas de proceso). Aquí solo se analizan y se descargan.":
        "Entries are made by the operator in each line's monitor (Process problems). Here they are only analyzed and downloaded.",
    "Líneas:": "Lines:", "Todas las líneas": "All lines", "Área": "Area", "Periodo:": "Period:", "⟳ Actualizar": "⟳ Refresh",
    "📉 Problemas de proceso": "📉 Process problems", "📉 Problemas de proceso (Pareto y CSV)…": "📉 Process problems (Pareto and CSV)…",
    "Pareto de paros y defectos capturados en las líneas, con descarga CSV":
        "Pareto of stops and defects entered on the lines, with CSV download",
    "⚠ Causas de paro y defectos…": "⚠ Stop causes and defects…", "📝 Clasificar ahora": "📝 Classify now",
    "La línea estuvo detenida <b>{m}</b> ({a}–{b}).<br>¿Cuál fue la causa?":
        "The line was stopped for <b>{m}</b> ({a}–{b}).<br>What was the cause?",
    "Problemas de calidad: <b>{n}</b> · scrap total <b>{s}</b> {u}": "Quality problems: <b>{n}</b> · total scrap <b>{s}</b> {u}",
    "Paros capturados: <b>{n}</b> · <b>{t}</b> (no planeados {u}, planeados {p})":
        "Stops entered: <b>{n}</b> · <b>{t}</b> (unplanned {u}, planned {p})",
    "{n} paros sin clasificar en el turno": "{n} unclassified stops in the shift",
    "{n} paros sin clasificar": "{n} unclassified stops",
    # --- control PID ---
    "Control": "Control", "Clic en el CAMPO del input (donde se escribe el valor)": "Click the input FIELD (where the value is typed)",
    "Clic en el botón de CONFIRMACIÓN del HMI (p. ej. «OK»)": "Click the HMI CONFIRMATION button (e.g. “OK”)",
    "Clic en el botón que SUBE el valor (+)": "Click the button that RAISES the value (+)",
    "Clic en el botón que BAJA el valor (−)": "Click the button that LOWERS the value (−)",
    "Simulación (calcula y registra, no escribe)": "Simulation (computes and logs, does not write)",
    "Asistido (propone; el operador aplica)": "Assisted (proposes; the operator applies)",
    "Automático (ajusta solo, dentro de los límites)": "Automatic (adjusts by itself, within the limits)",
    "Un lazo ajusta un <b>input del HMI</b> (p. ej. velocidad del capstan) para llevar una <b>medición</b> (p. ej. diámetro) a su objetivo. Al abrir el programa los lazos quedan desactivados: se activan en la página <b>Control</b>.":
        "A loop adjusts an <b>HMI input</b> (e.g. capstan speed) to bring a <b>measurement</b> (e.g. diameter) to its target. When the program opens, loops are deactivated: activate them on the <b>Control</b> page.",
    "Lazo": "Loop", "Modo al activarlo": "Mode when activated", "Medición a controlar": "Measurement to control",
    "Valor objetivo fijo": "Fixed target value", "Input del HMI que se ajusta": "HMI input to adjust",
    "Cómo se cambia el input en el HMI": "How the input is changed on the HMI",
    "Escribiendo el valor (clic en el campo, valor y Enter)": "Typing the value (click the field, value and Enter)",
    "Con botones + / −": "With + / − buttons", "Método": "Method", "Clics grabados": "Recorded clicks",
    "🎯 Campo": "🎯 Field", "🎯 Confirmación (opcional)": "🎯 Confirmation (optional)", "Sin confirmación": "No confirmation",
    "🎯 Botón +": "🎯 + button", "🎯 Botón −": "🎯 − button",
    "Seleccionar todo (Ctrl+A) antes de escribir": "Select all (Ctrl+A) before typing",
    "Cambio por cada clic de botón": "Change per button click",
    "Si el input está en otra pestaña: recorrido que lleva a ella (su regreso se usa al terminar). Se graba en «Recorrido automático».":
        "If the input is on another tab: tour that leads to it (its return is used at the end). It is recorded in “Tours”.",
    "Ruta a la pantalla del input": "Route to the input screen", "Esperar el valor en el HMI hasta": "Wait for the value on the HMI up to",
    "— está en la misma pantalla —": "— it is on the same screen —", "Ajuste": "Tuning",
    "Manual (valores de esta receta)": "Manual (values of this recipe)",
    "Aprendido de los cambios del operador": "Learned from the operator's changes", "Acción": "Action",
    "Si la medición está alta, SUBIR el input": "If the measurement is high, RAISE the input",
    "Si la medición está alta, BAJAR el input": "If the measurement is high, LOWER the input",
    "PID aprendido: 0.5 = más rápido · 1 = normal · 2 = más suave": "Learned PID: 0.5 = faster · 1 = normal · 2 = smoother",
    "Kp (input por unidad de error)": "Kp (input per unit of error)", "Ti (0 = sin integral)": "Ti (0 = no integral)",
    "Suavidad del PID aprendido": "Learned PID smoothness", "Copiar el PID aprendido a manual": "Copy the learned PID to manual",
    "Aprender de los cambios que haga el operador en el input": "Learn from the operator's changes to the input",
    "Observar la medición tras cada cambio": "Observe the measurement after each change",
    "Límites y seguridad": "Limits and safety", "según los decimales del input": "according to the input's decimals",
    "Input mínimo": "Minimum input", "Input máximo": "Maximum input", "Cambio máximo por ajuste": "Maximum change per adjustment",
    "Cambio máximo por minuto": "Maximum change per minute", "Redondear el input a": "Round the input to",
    "Banda muerta (error tolerado)": "Deadband (tolerated error)", "Tiempo mínimo entre ajustes": "Minimum time between adjustments",
    "Detener si hay una alarma en otra variable": "Stop if there is an alarm on another variable",
    "Detener si la línea está detenida": "Stop if the line is stopped",
    "No ajustar si el operador usó el HMI hace menos de": "Do not adjust if the operator used the HMI less than",
    "Tras un cambio del operador, esperar": "After an operator change, wait", "Medición vieja después de": "Measurement stale after",
    "Solo con comportamiento normal": "Only with normal behavior", "— no exigir —": "— not required —",
    "Lazo de control": "Control loop", "+ Lazo": "+ Loop", "Quitar lazo": "Remove loop",
    "Aún no hay cambios del operador observados para la receta activa.": "No operator changes observed yet for the active recipe.",
    "PID aprendido": "Learned PID", "Aún no hay suficientes observaciones.": "Not enough observations yet.",
    "Esc para cancelar": "Esc to cancel", "campo": "field", "confirmación": "confirmation", "no": "no",
    "Las observaciones no coinciden en la dirección: se necesitan más.": "The observations disagree on the direction: more are needed.",
    "Modo:": "Mode:", "Medición": "Measurement", "Objetivo": "Target", "Input en el HMI": "Input on the HMI",
    "✔ Aplicar": "✔ Apply", "✗ Ignorar": "✗ Ignore", "Input (eje derecho)": "Input (right axis)", "Propuesta": "Proposal",
    "■ Desactivar": "■ Deactivate", "▶ Activar": "▶ Activate",
    "El control ajusta inputs del HMI con límites y paros de seguridad. Al abrir el programa queda desactivado. Configura los lazos en Receta → Configurar receta → Control.":
        "Control adjusts HMI inputs with limits and safety stops. It is deactivated when the program opens. Configure the loops in Recipe → Configure recipe → Control.",
    "■ Detener todo el control": "■ Stop all control", "No hay lazos de control configurados.": "No control loops configured.",
    "Control: ajuste propuesto": "Control: proposed adjustment", "Activar control automático": "Activate automatic control",
    "Comportamiento aprendido: aún sin cambios del operador observados.": "Learned behavior: no operator changes observed yet.",
    "Simulación": "Simulation", "Asistido": "Assisted", "Automático": "Automatic", "Activo": "Active",
    "Desactivado": "Deactivated", "En espera": "Waiting", "Detenido por falla": "Stopped by fault",
    "Detenido por error": "Stopped by error", "Control detenido en todos los lazos": "Control stopped on all loops",
    "falta configurar la medición o el input": "the measurement or the input is not configured",
    "el input debe leerse de la pantalla del HMI": "the input must be read from the HMI screen",
    "sin objetivo (la receta no tiene nominal para la medición)": "no target (the recipe has no nominal for the measurement)",
    "la medición no está actualizada": "the measurement is not up to date", "el valor del input no está actualizado": "the input value is not up to date",
    "la línea está detenida": "the line is stopped", "hay una alarma activa": "there is an active alarm",
    "el comportamiento del proceso no es normal": "the process behavior is not normal",
    "el operador está usando el HMI": "the operator is using the HMI", "en el objetivo": "on target",
    "sin ajuste necesario": "no adjustment needed", "pantalla no disponible": "screen not available",
    "clics automáticos en pausa": "automatic clicks paused",
    "Aprendido ({n} cambios): la medición cambia {k} por unidad de input, retardo {th} s, constante {tau} s.":
        "Learned ({n} changes): the measurement changes {k} per input unit, delay {th} s, time constant {tau} s.",
    "PID sugerido: Kp {kp}, Ti {ti} s.": "Suggested PID: Kp {kp}, Ti {ti} s.", "¿Quitar el lazo «{n}»?": "Remove the loop “{n}”?",
    "Comportamiento aprendido ({n} cambios): {k} por unidad de input · retardo {th} s · constante {tau} s":
        "Learned behavior ({n} changes): {k} per input unit · delay {th} s · time constant {tau} s",
    "El programa va a cambiar «{i}» en el HMI dentro de los límites configurados ({lo} – {hi}).\n\n¿Activar?":
        "The program will change “{i}” on the HMI within the configured limits ({lo} – {hi}).\n\nActivate?",
    "«{n}» propone cambiar el input<br><b>{a} → {b}</b>": "“{n}” proposes changing the input<br><b>{a} → {b}</b>",
    # --- mejoras de interfaz ---
    "⏳ Paros por identificar": "⏳ Stops to identify", "📋 Capturas": "📋 Entries", "Calidad": "Quality",
    "Borra la captura seleccionada (por ejemplo, si se capturó mal)": "Deletes the selected entry (e.g. if it was entered wrong)",
    "Escribe la hora (hh:mm:ss) o usa las flechas": "Type the time (hh:mm:ss) or use the arrows",
    "Variables para SPC": "Variables for SPC",
    "Marca una variable para ver su distribución, capacidad (Cp, Cpk, Pp, Ppk) y carta de control.":
        "Check a variable to see its distribution, capability (Cp, Cpk, Pp, Ppk) and control chart.",
    "Límites de control y Cpk / Ppk": "Control limits and Cpk / Ppk",
    "LCS / LCI = media ± 3σ de corto plazo de los datos visibles (carta de individuos). Cpk y Ppk contra los límites de alarma de la receta.":
        "UCL / LCL = mean ± 3σ short-term of the visible data (individuals chart). Cpk and Ppk against the recipe's alarm limits.",
    "LCS": "UCL", "LCI": "LCL", "🖥 Variables del HMI": "🖥 HMI variables",
    "📹 Indicadores físicos (cámaras)": "📹 Physical indicators (cameras)", "Agregar o ajustar cámaras (USB o IP)": "Add or adjust cameras (USB or IP)",
    "+ Número (OCR)": "+ Number (OCR)", "+ Texto (OCR)": "+ Text (OCR)", "+ Selector por imagen": "+ Selector by image",
    "Display o pantalla con números legibles por OCR": "Display or screen with numbers readable by OCR",
    "Texto legible por OCR (p. ej. una etiqueta o mensaje)": "Text readable by OCR (e.g. a label or message)",
    "Interruptor o perilla: se reconoce su posición por imagen": "Switch or knob: its position is recognized by image",
    "Sin cámaras: agrega una con «📹 Cámaras…»": "No cameras: add one with “📹 Cameras…”",
    "Agrega una cámara con «📹 Cámaras…» para leer indicadores físicos.": "Add a camera with “📹 Cameras…” to read physical indicators.",
    "🏷 Identidad de la estación (logo, texto, línea)…": "🏷 Station identity (logo, text, line)…",
    "Identidad de la estación": "Station identity",
    "Logo, texto y número de línea: Configuración → Identidad de la estación": "Logo, text and line number: Settings → Station identity",
    "Logo de la empresa, un texto propio (p. ej. la planta o el área) y el número de línea. Se muestran arriba a la izquierda del programa. Son de este equipo, no de la receta.":
        "Company logo, your own text (e.g. the plant or area) and the line number. They are shown at the top left of the program. They belong to this PC, not to the recipe.",
    "Logo": "Logo", "Elegir imagen…": "Choose image…", "Quitar logo": "Remove logo", "Texto": "Text",
    "Número de línea": "Line number", "p. ej. Planta Monterrey · Extrusión": "e.g. Monterrey plant · Extrusion",
    "p. ej. Línea 3": "e.g. Line 3", "sin logo": "no logo", "Logo de la empresa": "Company logo",
    "Imágenes (*.png *.jpg *.jpeg *.bmp *.svg)": "Images (*.png *.jpg *.jpeg *.bmp *.svg)",
    # --- rediseño: barra superior, búsqueda, personal y tarjetas de estado ---
    "Buscar variable, acción, paro u hora…  (Ctrl+K)": "Search variable, action, stop or time…  (Ctrl+K)",
    "↑ ↓ elegir · Enter abrir · Esc cerrar": "↑ ↓ choose · Enter open · Esc close",
    "Ver tendencias en {t}": "View trends at {t}",
    "Marca esa hora en las gráficas": "Marks that time on the charts",
    "Capturar paro o defecto desde {t}": "Capture stop or defect from {t}",
    "Ver en Variables en vivo": "Show in Live variables",
    "Agregar a SPC": "Add to SPC",
    "Agregar a Correlación": "Add to Correlation",
    "sin lectura": "no reading",
    "Página": "Page",
    "receta activa": "active recipe",
    "Cambiar a esta receta (pide confirmación)": "Switch to this recipe (asks first)",
    "reciente": "recent",
    "inicio del turno": "shift start",
    "turno anterior": "previous shift",
    "Escribe una variable, página, acción, receta, paro o una hora":
        "Type a variable, page, action, recipe, stop or a time",
    "p. ej. «diámetro», «exportar», «ayer 14:30», «hace 2 h», «turno»":
        "e.g. “diameter”, “export”, “yesterday 14:30”, “2 h ago”, “shift”",
    "Receta": "Recipe",
    "Hora": "Time",
    "Alarma / evento": "Alarm / event",
    "Cambiar receta": "Change recipe",
    "¿Cambiar la receta activa a «{r}»?": "Change the active recipe to “{r}”?",
    "Turno desde {t}": "Shift since {t}",
    "Inicio del turno en curso (Configuración → KPI / OEE → turnos)":
        "Start of the current shift (Settings → KPI / OEE → shifts)",
    "Alarmas y avisos activos (clic: Alarmas y eventos)": "Active alarms and warnings (click: Alarms & events)",
    "Usuario en turno (operador o supervisor)": "User on shift (operator or supervisor)",
    "— Usuario —": "— User —",
    "✎ Editar personal…": "✎ Edit staff…",
    "👷 Personal (operadores y supervisores)…": "👷 Staff (operators and supervisors)…",
    "Personal (operadores y supervisores)": "Staff (operators and supervisors)",
    "Las personas de esta estación. Aparecen en la barra superior (quién está en turno) y al capturar "
    "paros y defectos. Son de este equipo, no de la receta; una persona inactiva se conserva en las capturas anteriores pero ya no aparece en las listas.":
        "The people at this station. They appear in the top bar (who is on shift) and when capturing stops "
        "and defects. They belong to this computer, not to the recipe; an inactive person is kept in past captures but no longer appears in the lists.",
    "Puesto": "Role",
    "Núm. de empleado": "Employee no.",
    "Operador": "Operator",
    "Supervisor": "Supervisor",
    "+ Supervisor": "+ Supervisor",
    "Nuevo supervisor": "New supervisor",
    "(sin personal: agrégalo en Configuración → Personal)": "(no staff: add them in Settings → Staff)",
    "Estado de la línea": "Line status",
    "Paros en el turno": "Stops this shift",
    "Paros por identificar": "Stops to identify",
    "Calidad del turno": "Shift quality",
    "OEE del turno": "Shift OEE",
    "sin datos de OEE": "no OEE data",
    "monitoreo detenido": "monitoring stopped",
    "configura el OEE": "set up OEE",
    "{d} detenido · {m} microparos": "{d} stopped · {m} micro-stops",
    "toca para clasificarlos": "tap to classify them",
    "todos clasificados": "all classified",
    "Causas de paro del turno": "Stop causes this shift",
    "Sin paros en el turno": "No stops this shift",
    "de paro": "stopped",
    "Otra": "Other",
    "Otras": "Others",
    "Sin identificar": "Unidentified",
    "Minutos de paro por causa en el turno (doble clic: Problemas de proceso)":
        "Stop minutes by cause this shift (double-click: Process problems)",
    "Tarjetas de estado arriba (marcha, paros, alarmas, calidad, OEE)":
        "Status cards on top (running, stops, alarms, quality, OEE)",
    # --- turnos y confirmación del usuario ---
    "Número de empleado": "Employee number",
    "Número de empleado y contraseña": "Employee number and password",
    "Elige a la persona que entra.": "Choose the person starting the shift.",
    "Esa persona no tiene número de empleado: asígnalo en Configuración → Personal.":
        "That person has no employee number: set it in Settings → Staff.",
    "El número de empleado no corresponde.": "The employee number does not match.",
    "Esa persona no tiene contraseña: asígnala en Configuración → Personal.":
        "That person has no password: set it in Settings → Staff.",
    "La contraseña no es correcta.": "The password is not correct.",
    "Contraseña de {n}": "Password for {n}",
    "Contraseña nueva": "New password",
    "Repetir": "Repeat",
    "Mínimo {n} caracteres. Se guarda cifrada (no se puede leer, solo reemplazar).":
        "At least {n} characters. It is stored encrypted (it cannot be read, only replaced).",
    "La contraseña debe tener al menos {n} caracteres.": "The password must have at least {n} characters.",
    "Las dos contraseñas no coinciden.": "The two passwords do not match.",
    "Turno": "Shift",
    "Contraseña": "Password",
    "👷 Personas": "👷 People",
    "🕒 Turnos": "🕒 Shifts",
    "🔐 Confirmación": "🔐 Confirmation",
    "Fin": "End",
    "+ Turno": "+ Shift",
    "Crear desde los inicios del OEE": "Create from the OEE shift starts",
    "Turnos con su horario. Asigna a cada persona su turno en la pestaña Personas (sin turno = puede "
    "entrar en cualquiera). Un turno que termina antes de empezar cruza la medianoche (p. ej. "
    "22:00–06:00).":
        "Shifts and their hours. Assign each person a shift in the People tab (no shift = can work "
        "any). A shift that ends before it starts crosses midnight (e.g. 22:00–06:00).",
    "Detectar el turno por la hora y, al empezar cada turno, pedir quién entra":
        "Detect the shift by the time and, when each shift starts, ask who is starting",
    "Confirmación del usuario que entra (también al cambiarlo en la barra superior)":
        "Confirmation of the person starting (also when changing it in the top bar)",
    "Todo es opcional. Con confirmación, cada persona necesita su número de empleado (y su "
    "contraseña, si se pide). Las contraseñas se guardan cifradas; si alguien la olvida, asígnale una "
    "nueva en la pestaña Personas.":
        "Everything is optional. With confirmation, each person needs an employee number (and a "
        "password, if required). Passwords are stored encrypted; if someone forgets theirs, assign a "
        "new one in the People tab.",
    "🔒 Cambiar…": "🔒 Change…",
    "Asignar…": "Set…",
    "Turno {n}": "Shift {n}",
    "Turnos": "Shifts",
    "La receta no tiene inicios de turno en KPI / OEE.": "The recipe has no shift starts in KPI / OEE.",
    "¿Reemplazar los turnos por los del OEE?": "Replace the shifts with the OEE ones?",
    "Cualquiera": "Any",
    "Para detectar el turno por la hora, agrega los turnos y su horario.":
        "To detect the shift by the time, add the shifts and their hours.",
    "Hay números de empleado repetidos.": "There are repeated employee numbers.",
    "Sin número de empleado: {n}": "No employee number: {n}",
    "Sin contraseña: {n}": "No password: {n}",
    "¿Guardar de todos modos?": "Save anyway?",
    "Personal": "Staff",
    "Cambio de turno": "Shift change",
    "Confirmar usuario": "Confirm user",
    "Empieza el <b>{s}</b>. ¿Quién entra?": "<b>{s}</b> is starting. Who is on shift?",
    "Confirma quién está en turno.": "Confirm who is on shift.",
    "Usuario": "User",
    "número de empleado": "employee number",
    "Más tarde": "Later",
    "Confirmar": "Confirm",
    "No hay personal para este turno: agrégalo en Configuración → Personal.":
        "There is no staff for this shift: add them in Settings → Staff.",
    # --- sesión de supervisor ---
    "🔒 Supervisor": "🔒 Supervisor",
    "Iniciar la sesión de supervisor para hacer cambios protegidos": "Sign in as supervisor to make protected changes",
    "Inicia la sesión de supervisor para hacer cambios protegidos.": "Sign in as supervisor to make protected changes.",
    "🔒 Requiere la sesión de supervisor: {r}": "🔒 Requires a supervisor session: {r}",
    "Lista de personal, turnos y esta protección": "Staff list, shifts and this protection",
    "Cambiar la receta activa, editar recetas y límites": "Change the active recipe, edit recipes and limits",
    "Variables, pantallas, recorridos, cámaras y configuración del control (Configurar receta)":
        "Variables, screens, tours, cameras and control settings (Recipe setup)",
    "Tablero de Inicio y dock (indicadores y gráficos)": "Home dashboard and dock (indicators and charts)",
    "Activar el control automático o cambiar su modo": "Turn on automatic control or change its mode",
    "Causas de paro, defectos y entrenamiento de comportamientos": "Stop causes, defects and behavior training",
    "Eliminar capturas de paros y defectos": "Delete stop and defect entries",
    "Identidad de la estación, exportación y servidor": "Station identity, export and server",
    "Detener el monitoreo y cerrar el programa": "Stop monitoring and close the program",
    "Inicio de sesión de supervisor": "Supervisor sign-in",
    "Se necesita un supervisor para: <b>{r}</b>": "A supervisor is needed for: <b>{r}</b>",
    "Iniciar sesión": "Sign in",
    "Número de empleado o contraseña incorrectos (o no es supervisor).":
        "Wrong employee number or password (or not a supervisor).",
    "Sesión de supervisor activa (clic: cerrar sesión)": "Supervisor session active (click: sign out)",
    "🔓 {n} · {m} min · cerrar sesión": "🔓 {n} · {m} min · sign out",
    "+ Usuario": "+ User",
    "Nuevo usuario": "New user",
    "Pedir el inicio de sesión de un supervisor (número de empleado y contraseña) para:":
        "Require a supervisor sign-in (employee number and password) to:",
    "La sesión de supervisor se cierra tras": "The supervisor session closes after",
    "sin usarse (o al cerrarla en la barra superior).": "without use (or when signing out in the top bar).",
    "🔐 Confirmación y supervisor": "🔐 Confirmation and supervisor",
    "Para pedir el inicio de sesión de supervisor, al menos un supervisor activo necesita número de "
    "empleado y contraseña.":
        "To require a supervisor sign-in, at least one active supervisor needs an employee number and "
        "a password.",
    # --- gráficas y aviso de supervisor ---
    "Variables de SPC y correlación y modelo de estabilidad mostrado":
        "SPC and correlation variables and the stability model shown",
    "Se requiere supervisor": "Supervisor required",
    "Para modificar esto se requiere la sesión de un supervisor.": "A supervisor session is required to change this.",
    "🔓 Iniciar sesión de supervisor": "🔓 Supervisor sign-in",
    "Arrastra para cambiar el alto de la gráfica (doble clic: alto automático)":
        "Drag to change the chart height (double-click: automatic height)",
    "🔒 Bloquear zoom de las gráficas con la rueda del ratón": "🔒 Lock chart zoom with the mouse wheel",
    # --- variables en vivo (mosaicos) ---
    "Clic derecho: gráfico, tamaño y tiempo · doble clic: graficar en Tendencias":
        "Right-click: chart, size and time · double-click: plot in Trends",
    "DATO VIEJO": "STALE",
    "SIN LÍMITES": "NO LIMITS",
    "Tolerancia {lo} … {hi}": "Tolerance {lo} … {hi}",
    "Aviso {lo} … {hi}": "Warning {lo} … {hi}",
    "lectura OK": "reading OK",
    "lectura con falla": "reading failed",
    "pantalla no visible ahora": "screen not visible now",
    "Filtrar variables…": "Filter variables…",
    "Sin pantalla": "No screen",
    "Gráfico": "Chart",
    "Tamaño": "Size",
    "Normal (1 × 1)": "Normal (1 × 1)",
    "Ancho (2 × 1)": "Wide (2 × 1)",
    "Grande (2 × 2)": "Large (2 × 2)",
    "Tiempo mostrado (gráfica e histograma)": "Time shown (chart and histogram)",
    "📈 Graficar en Tendencias": "📈 Plot in Trends",
    "Restablecer este mosaico": "Reset this tile",
    "Vista:": "View:",
    "▦ Mosaicos": "▦ Tiles",
    "☰ Tabla": "☰ Table",
    "Clic derecho en un mosaico: gráfico, tamaño y tiempo · doble clic: Tendencias":
        "Right-click a tile: chart, size and time · double-click: Trends",
    # --- dashboard global con el estilo del monitor ---
    "Buscar línea, área o estado…": "Search line, area or status…",
    "Líneas con alarma o aviso (clic: mostrar solo esas)": "Lines with alarm or warning (click: show only those)",
    "Reconocer avisos": "Acknowledge alerts",
    "Modo TV": "TV mode",
    "○ Carpeta de datos sin elegir": "○ Data folder not chosen",
    "● Sin acceso a la carpeta de datos": "● No access to the data folder",
    "● Carpeta de datos conectada · {n} líneas": "● Data folder connected · {n} lines",
    "No se puede leer la carpeta de datos: revisa la red o los permisos (⚙ Configuración).":
        "Cannot read the data folder: check the network or permissions (⚙ Settings).",
    # --- análisis estadístico ---
    "Datos": "Data",
    "Desde / hasta": "From / to",
    "Agrupar por": "Group by",
    "Todos": "All",
    "Solo": "Only",
    "Respuesta (Y)": "Response (Y)",
    "Opciones": "Options",
    "De la receta": "From recipe",
    "Toma los límites de alarma de la receta activa": "Takes the alarm limits of the active recipe",
    "Especificación": "Specification",
    "Barras del histograma": "Histogram bars",
    "Curva normal": "Normal curve",
    "Un panel por grupo (en lugar de superponer)": "One panel per group (instead of overlaying)",
    "Valor de las barras": "Bar value",
    "Valores individuales y rango móvil (I-MR)": "Individuals and moving range (I-MR)",
    "Medias y rangos de subgrupos (X̄-R)": "Subgroup means and ranges (X̄-R)",
    "Carta": "Chart",
    "Tamaño de subgrupo": "Subgroup size",
    "Resolución de la cuadrícula": "Grid resolution",
    "Las variables se comparan en los mismos instantes, cada tantos segundos":
        "Variables are compared at the same instants, every so many seconds",
    "Emparejar datos cada": "Pair data every",
    "Términos cuadráticos (curvatura)": "Quadratic terms (curvature)",
    "Interacciones entre factores": "Interactions between factors",
    "Capturas": "Entries",
    "Agrupar capturas por": "Group entries by",
    "Medir": "Measure",
    "Calcular": "Calculate",
    "＋ Nuevo análisis": "＋ New analysis",
    "Doble clic para cambiar el título": "Double-click to change the title",
    "Crea un análisis con «＋ Nuevo análisis»: estadística descriptiva, histogramas, cajas, gráficas de "
    "tiempo y de barras, normalidad, capacidad y Sixpack, cartas de control, comparación de turnos, días, "
    "meses u operadores, Pareto de paros y defectos, correlación, contorno y regresión con simulación de "
    "respuesta.<br><br>Cada análisis queda en el navegador: clic para verlo, doble clic para cambiarlo.":
        "Create an analysis with “＋ New analysis”: descriptive statistics, histograms, boxplots, time and "
        "bar charts, normality, capability and Sixpack, control charts, comparison of shifts, days, "
        "months or operators, Pareto of stops and defects, correlation, contour and regression with "
        "response simulation.<br><br>Each analysis stays in the navigator: click to view it, double-click "
        "to change it.",
    "Título del análisis": "Analysis title",
    "Colores de barras y líneas": "Bar and line colors",
    "Colores del tema": "Theme colors",
    "por": "by",
    "Cambiar el análisis": "Change the analysis",
    "Nuevo análisis": "New analysis",
    "Z (respuesta)": "Z (response)",
    "Título": "Title",
    "Factores (X): marca uno o varios": "Factors (X): check one or more",
    "El fin del periodo debe ser posterior al inicio.": "The end of the period must be after the start.",
    "Marca al menos dos variables.": "Check at least two variables.",
    "Marca al menos un factor (X) distinto de la respuesta.": "Check at least one factor (X) other than the response.",
    "Indica al menos un límite de especificación (LIE o LSE).": "Enter at least one specification limit (LSL or USL).",
    "Para comparar, agrupa (turno, día, mes, operador…) o marca dos o más variables.":
        "To compare, group (shift, day, month, operator…) or check two or more variables.",
    "🎨 Colores": "🎨 Colors",
    "Color de barras y líneas": "Bar and line color",
    "⟳ Recalcular": "⟳ Recalculate",
    "Vuelve a leer el historial": "Reads the history again",
    "⤓ Imagen": "⤓ Image",
    "Guardar el análisis como imagen PNG": "Save the analysis as a PNG image",
    "⤓ CSV": "⤓ CSV",
    "Guardar la tabla de resultados": "Save the results table",
    "Serie 1": "Series 1",
    "Guardar imagen": "Save image",
    "Guardar tabla": "Save table",
    "Marca hasta {n} variables": "Check up to {n} variables",
    "✎ Cambiar": "✎ Change",
    "Cambiar datos, variables u opciones": "Change data, variables or options",
    "⧉ Duplicar": "⧉ Duplicate",
    "Copia para probar otra variación": "Copy to try another variation",
    "Aa Renombrar": "Aa Rename",
    "Cambiar el título del análisis": "Change the analysis title",
    "🗑 Eliminar": "🗑 Delete",
    "Quitar el análisis del navegador": "Remove the analysis from the navigator",
    "No se pudo guardar el navegador: {e}": "Could not save the navigator: {e}",
    "Análisis estadístico": "Statistical analysis",
    "¿Quitar «{t}» del navegador?": "Remove “{t}” from the navigator?",
    "No hay datos de esas variables en el periodo elegido (con los filtros aplicados).":
        "There is no data for those variables in the chosen period (with the filters applied).",
    "Tipo de análisis": "Analysis type",
    "Navegador de análisis": "Analysis navigator",
    "No se pudo calcular: {e}": "Could not calculate: {e}",
    "datos": "data points",
    "{v}: Cpk {k} · Ppk {pk}. Se esperan {ppm} PPM fuera de especificación.":
        "{v}: Cpk {k} · Ppk {pk}. {ppm} PPM out of specification are expected.",
    "El modelo explica el <b>{r} %</b> de la variación de {y}.":
        "The model explains <b>{r} %</b> of the variation of {y}.",
    "Porcentaje": "Percent",
    " · datos promediados cada {s} s por ser muchos": " · data averaged every {s} s because there are many",
    "Estadística descriptiva": "Descriptive statistics",
    "<b>{h}</b>: media {m}, desviación estándar {s} (CV {cv} %), de {mn} a {mx}. La mitad de los datos "
    "está entre {q1} y {q3}.":
        "<b>{h}</b>: mean {m}, standard deviation {s} (CV {cv} %), from {mn} to {mx}. Half of the data is "
        "between {q1} and {q3}.",
    "Histograma de {v}": "Histogram of {v}",
    "Gráfica de caja de {v}": "Boxplot of {v}",
    "Gráfica de tiempo de {v}": "Time series of {v}",
    "{s} por grupo": "{s} by group",
    "Gráfica de intervalos (media e IC 95 %)": "Interval plot (mean and 95 % CI)",
    "Grupos": "Groups",
    "ANOVA de un factor": "One-way ANOVA",
    "<b>Hay diferencia significativa entre los grupos</b> (p = {p} < 0.05). Media más alta: <b>{a}</b> "
    "({ma}); más baja: <b>{b}</b> ({mb}). El factor explica el {r} % de la variación.":
        "<b>There is a significant difference between the groups</b> (p = {p} < 0.05). Highest mean: "
        "<b>{a}</b> ({ma}); lowest: <b>{b}</b> ({mb}). The factor explains {r} % of the variation.",
    "<b>No hay diferencia significativa</b> entre los grupos (p = {p} ≥ 0.05): las diferencias observadas "
    "pueden deberse al azar.":
        "<b>There is no significant difference</b> between the groups (p = {p} ≥ 0.05): the observed "
        "differences may be due to chance.",
    "Gráfica de probabilidad normal de {v}": "Normal probability plot of {v}",
    "<b>El proceso es capaz</b>": "<b>The process is capable</b>",
    "Capacidad del proceso de {v}": "Process capability of {v}",
    "Últimas 25 observaciones": "Last 25 observations",
    "Observación": "Observation",
    "Gráfica de capacidad": "Capability plot",
    "Carta X̄ (subgrupos de {n})": "X̄ chart (subgroups of {n})",
    "Carta de valores individuales (I)": "Individuals chart (I)",
    "Carta R": "R chart",
    "Carta de rango móvil (MR)": "Moving range chart (MR)",
    "Correlación de Pearson (r)": "Pearson correlation (r)",
    "Contorno de {z} contra {x} y {y}": "Contour of {z} vs {x} and {y}",
    "Coeficientes": "Coefficients",
    "Residuos contra ajustados": "Residuals vs fits",
    "Probabilidad normal de los residuos": "Normal probability of residuals",
    "Mueve los factores en la simulación para ver la respuesta esperada.":
        "Move the factors in the simulation to see the expected response.",
    "Superficie de respuesta: {y}": "Response surface: {y}",
    "Pareto de {k} por {b}": "Pareto of {k} by {b}",
    "% acumulado": "cumulative %",
    "<b>{k} de {n}</b> categorías concentran el 80 % ({top}). Atacar primero «{first}» ({pct} % del "
    "total) es lo que más reduce {m}.":
        "<b>{k} of {n}</b> categories make up 80 % ({top}). Tackling “{first}” first ({pct} % of the "
        "total) reduces {m} the most.",
    "Título de la gráfica": "Chart title",
    "Desv. est.": "StDev",
    "Mediana": "Median",
    "Rango IQ": "IQR",
    "Mínimo": "Minimum",
    "Máximo": "Maximum",
    "Grupo": "Group",
    "Se necesitan al menos dos grupos con datos: agrupa (turno, día, mes, operador…) o elige varias "
    "variables.":
        "At least two groups with data are needed: group (shift, day, month, operator…) or choose several "
        "variables.",
    "IC 95 % bajo": "95 % CI low",
    "IC 95 % alto": "95 % CI high",
    "Prueba t (Welch): diferencia de medias {d} (IC 95 %: {a} a {b}), t = {t}, p = {p}. ":
        "t-test (Welch): difference of means {d} (95 % CI: {a} to {b}), t = {t}, p = {p}. ",
    "Se necesitan al menos 8 datos con variación.": "At least 8 data points with variation are needed.",
    "Estadístico": "Statistic",
    "<b>Los datos siguen una distribución normal</b> (Anderson-Darling p = {p} ≥ 0.05): los índices de "
    "capacidad Cp/Cpk son confiables.":
        "<b>The data follow a normal distribution</b> (Anderson-Darling p = {p} ≥ 0.05): the Cp/Cpk "
        "capability indices are reliable.",
    "Datos del proceso": "Process data",
    "Índice": "Index",
    "Dentro (corto plazo)": "Within (short term)",
    "General (largo plazo)": "Overall (long term)",
    "<b>El proceso es apenas capaz</b> (mejorar la variación o el centrado)":
        "<b>The process is barely capable</b> (improve variation or centering)",
    "<b>El proceso no es capaz</b>": "<b>The process is not capable</b>",
    "superior": "upper",
    "inferior": "lower",
    "El proceso está <b>descentrado</b> hacia el límite {s}: centrarlo subiría el Cpk a ~{cp}.":
        "The process is <b>off-center</b> toward the {s} limit: centering it would raise Cpk to ~{cp}.",
    "La variación a largo plazo es mucho mayor que la de corto plazo (Ppk ≪ Cpk): hay cambios entre "
    "turnos, recetas o con el tiempo.":
        "Long-term variation is much larger than short-term (Ppk ≪ Cpk): there are changes between "
        "shifts, recipes or over time.",
    "Dentro": "Within",
    "Indica al menos un límite de especificación (LIE o LSE) y elige un rango con 5 datos o más.":
        "Enter at least one specification limit (LSL or USL) and choose a range with 5 or more data "
        "points.",
    "Indica al menos un límite de especificación y elige un rango con datos suficientes.":
        "Enter at least one specification limit and choose a range with enough data.",
    "Carta I": "I chart",
    "Carta de rango móvil": "Moving range chart",
    "Histograma de capacidad": "Capability histogram",
    "Gráfica de probabilidad normal": "Normal probability plot",
    "La carta I tiene <b>{n} puntos fuera de control</b>: el proceso no es estable y los índices pueden "
    "no representar el futuro.":
        "The I chart has <b>{n} out-of-control points</b>: the process is not stable and the indices may "
        "not represent the future.",
    "Las cartas no muestran puntos fuera de control: el proceso es estable.":
        "The charts show no out-of-control points: the process is stable.",
    "Los datos no son normales (p = {p}).": "The data are not normal (p = {p}).",
    "Datos insuficientes para la carta de control.": "Not enough data for the control chart.",
    "Prueba": "Test",
    "Puntos": "Points",
    "<b>Proceso estable</b>: ningún punto sale de los límites ni hay corridas.":
        "<b>Stable process</b>: no point is outside the limits and there are no runs.",
    "Se necesitan al menos dos variables con datos en los mismos momentos.":
        "At least two variables with data at the same moments are needed.",
    "fuerte": "strong",
    "directa": "positive",
    "inversa": "negative",
    "<b>{x}</b> y <b>{y}</b>: relación {s} {d} (r = {r}, p = {p})":
        "<b>{x}</b> and <b>{y}</b>: {s} {d} relationship (r = {r}, p = {p})",
    "Correlación no es causalidad: confirma con un cambio controlado.":
        "Correlation is not causation: confirm with a controlled change.",
    "Se necesitan las tres variables (X, Y, Z) con datos en los mismos momentos.":
        "The three variables (X, Y, Z) with data at the same moments are needed.",
    "{z} más alto ({zmax}) con {x} ≈ {xa} y {y} ≈ {ya}; más bajo ({zmin}) con {x} ≈ {xb} y {y} ≈ {yb}. "
    "Las zonas sin color no tienen datos.":
        "Highest {z} ({zmax}) with {x} ≈ {xa} and {y} ≈ {ya}; lowest ({zmin}) with {x} ≈ {xb} and {y} ≈ "
        "{yb}. Areas without color have no data.",
    "Se necesitan la respuesta (Y) y al menos un factor (X) con datos en los mismos momentos.":
        "The response (Y) and at least one factor (X) with data at the same moments are needed.",
    "No hay suficientes datos para ajustar el modelo.": "There is not enough data to fit the model.",
    "S = {s} · R² = {r2} % · R² ajustado = {r2a} % · F = {f} · p = {p} · N = {n}":
        "S = {s} · R² = {r2} % · adjusted R² = {r2a} % · F = {f} · p = {p} · N = {n}",
    "Término": "Term",
    "Coeficiente": "Coefficient",
    "Error est.": "SE",
    "¿Significativo?": "Significant?",
    "Gráfica de línea ajustada": "Fitted line plot",
    "Observado contra ajustado": "Observed vs fitted",
    "Ajustado": "Fitted",
    "Observado": "Observed",
    "Factores significativos (p < 0.05): {s}.": "Significant factors (p < 0.05): {s}.",
    "Ningún factor es significativo: el modelo no sirve para predecir.":
        "No factor is significant: the model is not useful for prediction.",
    "R² bajo: faltan factores importantes o la relación no es de este tipo.":
        "Low R²: important factors are missing or the relationship is of a different kind.",
    "No hay capturas en el rango elegido.": "There are no entries in the chosen range.",
    "La distribución es asimétrica (asimetría {a}): revisa la normalidad antes de calcular capacidad.":
        "The distribution is skewed (skewness {a}): check normality before calculating capability.",
    "Densidad": "Density",
    "Frecuencia": "Frequency",
    "La serie con menor variación es <b>{n}</b> (desv. est. {s}). Compara las medias y la dispersión de "
    "cada serie; para saber si la diferencia es real usa «Comparar grupos».":
        "The series with the least variation is <b>{n}</b> (StDev {s}). Compare the means and spread of "
        "each series; to know whether the difference is real use “Compare groups”.",
    "La caja muestra el 50 % central de los datos y la línea, la mediana; el punto es la media y las × "
    "son valores atípicos. Mayor dispersión: <b>{n}</b> (rango IQ {r}).":
        "The box shows the central 50 % of the data and the line the median; the dot is the mean and the "
        "× are outliers. Largest spread: <b>{n}</b> (IQR {r}).",
    "Sin tendencias marcadas en el periodo: los valores se mantienen alrededor de su media.":
        "No marked trends in the period: values stay around their mean.",
    "Entre grupos": "Between groups",
    "Error (dentro)": "Error (within)",
    "Total": "Total",
    "Valor p": "p-value",
    "<b>Los datos no siguen una distribución normal</b> (Anderson-Darling p = {p} < 0.05). Puede haber "
    "mezcla de condiciones (turnos, recetas, arranques) o una distribución sesgada: separa por grupo o "
    "interpreta Cp/Cpk con cuidado.":
        "<b>The data do not follow a normal distribution</b> (Anderson-Darling p = {p} < 0.05). There may "
        "be mixed conditions (shifts, recipes, start-ups) or a skewed distribution: split by group or "
        "interpret Cp/Cpk carefully.",
    "Desv. est. (dentro)": "StDev (within)",
    "Desv. est. (general)": "StDev (overall)",
    "Fuera de límites de control": "Outside control limits",
    "9 o más seguidos del mismo lado": "9 or more in a row on the same side",
    "Rango fuera de límites": "Range outside limits",
    "<b>Proceso fuera de control</b>: {a} puntos fuera de límites, {b} en corridas y {c} rangos fuera. "
    "Busca causas especiales en esos momentos (cambio de receta, arranque, material).":
        "<b>Process out of control</b>: {a} points outside limits, {b} in runs and {c} ranges out. Look "
        "for special causes at those moments (recipe change, start-up, material).",
    "moderada": "moderate",
    "débil": "weak",
    "(sin dato)": "(no data)",
    "<b>{v}</b> tiene una tendencia {d} de {s} {u}/h en el periodo.":
        "<b>{v}</b> is trending {d} by {s} {u}/h in the period.",
    "observadas": "observed",
    "esperadas": "expected",
    "IC 95 % de la media: {a} a {b} · IP 95 % de una lectura: {c} a {d}":
        "95 % CI of the mean: {a} to {b} · 95 % PI of a reading: {c} to {d}",
    "Ecuación de regresión": "Regression equation",
    "Simulación de respuesta": "Response simulation",
    "⚠ Fuera del rango de los datos: la predicción es una extrapolación.":
        "⚠ Outside the data range: the prediction is an extrapolation.",
    "Barras": "Bars",
    "a subir": "up",
    "a bajar": "down",
    "Media, desviación estándar, varianza, mínimo y máximo, rango, mediana, cuartiles, suma de cuadrados, "
    "asimetría y curtosis, por variable y grupo.":
        "Mean, standard deviation, variance, minimum and maximum, range, median, quartiles, sum of "
        "squares, skewness and kurtosis, by variable and group.",
    "Comparar grupos (t / ANOVA)": "Compare groups (t / ANOVA)",
    "¿Hay diferencia real entre turnos, días, meses, operadores o recetas? Gráfica de intervalos, ANOVA "
    "de un factor y prueba t.":
        "Is there a real difference between shifts, days, months, operators or recipes? Interval plot, "
        "one-way ANOVA and t-test.",
    "Prueba de normalidad": "Normality test",
    "Gráfica de probabilidad normal y prueba de Anderson-Darling.":
        "Normal probability plot and Anderson-Darling test.",
    "Histograma": "Histogram",
    "Distribución con curva normal; varias variables o grupos superpuestos o en paneles.":
        "Distribution with normal curve; several variables or groups overlaid or in panels.",
    "Gráfica de caja (boxplot)": "Boxplot",
    "Mediana, cuartiles y atípicos por variable o grupo.": "Median, quartiles and outliers by variable or group.",
    "Valores en el tiempo de una o varias variables.": "Values over time of one or several variables.",
    "Gráfica de barras": "Bar chart",
    "Media, mediana, suma, conteo o desviación por grupo.": "Mean, median, sum, count or deviation by group.",
    "Análisis de capacidad": "Capability analysis",
    "Cp, Cpk, Pp, Ppk, Cpm y PPM con histograma y curvas dentro y general.":
        "Cp, Cpk, Pp, Ppk, Cpm and PPM with histogram and within and overall curves.",
    "Capacidad Sixpack": "Capability Sixpack",
    "Cartas I y MR, últimas 25 observaciones, histograma, probabilidad normal y gráfica de capacidad.":
        "I and MR charts, last 25 observations, histogram, normal probability and capability plot.",
    "Carta de control (I-MR / X̄-R)": "Control chart (I-MR / X̄-R)",
    "Límites de control y puntos fuera de control o corridas.": "Control limits and out-of-control points or runs.",
    "Pareto de paros y defectos": "Pareto of stops and defects",
    "Paros o defectos capturados por causa, categoría, operador, turno, día o mes.":
        "Captured stops or defects by cause, category, operator, shift, day or month.",
    "Multivariable (matriz y correlación)": "Multivariable (matrix and correlation)",
    "Matriz de dispersión y correlación de Pearson entre varias variables.":
        "Scatter matrix and Pearson correlation between several variables.",
    "Gráfica de contorno": "Contour plot",
    "Cómo cambia una variable (Z) según otras dos (X, Y).": "How one variable (Z) changes with two others (X, Y).",
    "Regresión y simulación de respuesta": "Regression and response simulation",
    "Modelo de la respuesta según los factores (lineal, cuadrático, interacciones), significancia y "
    "simulador: mueve los factores y ve la respuesta esperada.":
        "Model of the response from the factors (linear, quadratic, interactions), significance and "
        "simulator: move the factors and see the expected response.",
    "Estadística básica": "Basic statistics",
    "Gráficas": "Graphs",
    "Paros y defectos": "Stops and defects",
    "Relaciones": "Relationships",
    "Personalizado": "Custom",
    "Suma": "Sum",
    "Conteo": "Count",
    "Desviación estándar": "Standard deviation",
    "Día": "Day",
    "Mes": "Month",
    "Minutos": "Minutes",
    "Número de capturas": "Number of entries",
    "Defectos de calidad": "Quality defects",
    "N": "N",
    "Desv. estándar": "StDev",
    "Varianza": "Variance",
    "Error estándar de la media": "SE of the mean",
    "Coef. de variación (%)": "Coef. of variation (%)",
    "Q1": "Q1",
    "Q3": "Q3",
    "Rango intercuartil": "Interquartile range",
    "Suma de cuadrados (corregida)": "Sum of squares (corrected)",
    "Suma de cuadrados (sin corregir)": "Sum of squares (uncorrected)",
    "Asimetría": "Skewness",
    "Curtosis": "Kurtosis",
    "Sin agrupar": "Not grouped",
    "Semana": "Week",
    "Hora del día": "Hour of day",
    # --- notificaciones y reportes de análisis ---
    "Notificaciones (correo y mensajes)": "Notifications (email and messages)",
    "Envía un aviso por correo, Telegram o un canal de Teams / Slack / Google Chat cuando ocurra alguna "
    "de las alertas elegidas. Es de esta estación (no de la receta). Los avisos salen aparte del "
    "monitoreo y se reintentan si no hay red.":
        "Sends a notice by email, Telegram or a Teams / Slack / Google Chat channel when any of the "
        "chosen alerts happens. It belongs to this station (not the recipe). Notices are sent apart from "
        "monitoring and retried if there is no network.",
    "Correo (SMTP)": "Email (SMTP)",
    "Servidor": "Server",
    "contraseña o contraseña de aplicación": "password or app password",
    "Usuario y contraseña": "User and password",
    "(el mismo usuario)": "(same user)",
    "Remitente": "Sender",
    "Destinatarios": "Recipients",
    "Telegram": "Telegram",
    "token del bot (de @BotFather)": "bot token (from @BotFather)",
    "Token": "Token",
    "ID del chat o grupo, separados por coma": "chat or group ID, comma separated",
    "Chats": "Chats",
    "Crea un bot con @BotFather, agrégalo al grupo y escribe ahí cualquier mensaje; el ID del chat "
    "aparece en https://api.telegram.org/bot<token>/getUpdates.":
        "Create a bot with @BotFather, add it to the group and write any message there; the chat ID "
        "appears at https://api.telegram.org/bot<token>/getUpdates.",
    "Teams / Slack / Google Chat (webhook)": "Teams / Slack / Google Chat (webhook)",
    "URL del webhook entrante del canal": "Incoming webhook URL of the channel",
    "URL": "URL",
    "✉ Enviar prueba": "✉ Send test",
    "📡 Canales": "📡 Channels",
    "El mismo aviso no se repite antes del tiempo de espera; cuando la condición se normaliza, un nuevo "
    "evento vuelve a avisar. El paro avisa también cuando la línea reanuda.":
        "The same notice is not repeated before the waiting time; when the condition returns to normal, a "
        "new event notifies again. Stops also notify when the line resumes.",
    "🔔 Alertas": "🔔 Alerts",
    "Tiempo de espera entre avisos iguales": "Waiting time between identical notices",
    "Pausar todos los avisos (mantenimiento, pruebas)": "Pause all notices (maintenance, tests)",
    "⚙ Opciones": "⚙ Options",
    "Puerto": "Port",
    "Enviar aviso cuando…": "Send a notice when…",
    "Límite": "Limit",
    "(todavía no se ha enviado nada en esta sesión)": "(nothing has been sent in this session yet)",
    "Activa y completa al menos un canal.": "Enable and fill in at least one channel.",
    "Notificaciones": "Notifications",
    "Para el correo falta el servidor o los destinatarios.": "The email server or recipients are missing.",
    "Últimos envíos": "Latest sends",
    "Guardar reporte PDF": "Save PDF report",
    "Reporte PDF de análisis": "Analysis PDF report",
    "Reporte de análisis estadístico": "Statistical analysis report",
    "Generar PDF": "Generate PDF",
    "Análisis que van en el reporte (en este orden):": "Analyses included in the report (in this order):",
    "Título del reporte": "Report title",
    "Análisis programado — {f}": "Scheduled analysis — {f}",
    "Se calcula solo con el periodo que terminó y se agrega al reporte PDF programado (carpeta de "
    "reportes; también por correo si está activado)":
        "It is calculated automatically with the period that just ended and added to the scheduled PDF "
        "report (reports folder; also by email if enabled)",
    "Programar": "Schedule",
    "📄 Reporte PDF": "📄 PDF report",
    "Junta varios análisis en un PDF para juntas o auditorías":
        "Combines several analyses in a PDF for meetings or audits",
    "Reporte PDF": "PDF report",
    "Reporte guardado:\n{p}": "Report saved:\n{p}",
    "📨 Notificaciones (correo y mensajes)…": "📨 Notifications (email and messages)…",
    "📨 Notificaciones…": "📨 Notifications…",
    "Enviar avisos por correo o mensaje de las alarmas elegidas": "Send email or message notices for the chosen alarms",
    "Variable fuera de límite (alarma)": "Variable out of limits (alarm)",
    "Variable en aviso (fuera de la tolerancia de aviso)": "Variable in warning (outside the warning tolerance)",
    "Error de lectura de una variable": "Variable reading error",
    "Pantalla del HMI o cámara sin imagen": "HMI screen or camera without image",
    "Paro de máquina": "Machine stop",
    "Tiempo de paro acumulado en el turno": "Accumulated stop time in the shift",
    "Desperdicio alto en una captura": "High scrap in an entry",
    "Desperdicio acumulado en el turno": "Accumulated scrap in the shift",
    "Cpk bajo (sostenido 5 min)": "Low Cpk (sustained 5 min)",
    "OEE bajo al cerrar el turno": "Low OEE at the end of the shift",
    "Comportamiento anormal (IA)": "Abnormal behavior (AI)",
    "Tendencia que alcanzará el límite": "Trend that will reach the limit",
    "Control automático detenido por seguridad o en alarma": "Automatic control stopped for safety or in alarm",
    "Cambio de receta": "Recipe change",
    "Monitoreo detenido o programa cerrado": "Monitoring stopped or program closed",
    "Reportes de análisis programados (adjunta el PDF)": "Scheduled analysis reports (attaches the PDF)",
    "s sin lectura": "s without reading",
    "min detenida": "min stopped",
    "min": "min",
    "(unidad de longitud)": "(length unit)",
    "Cpk menor que": "Cpk below",
    "% menor que": "% below",
    "Microsoft Teams": "Microsoft Teams",
    "Slack": "Slack",
    "Google Chat": "Google Chat",
    "Otro (JSON)": "Other (JSON)",
    "No programar": "Do not schedule",
    "Cada turno (turno anterior)": "Every shift (previous shift)",
    "Cada día (día anterior)": "Every day (previous day)",
    "Cada semana (semana anterior)": "Every week (previous week)",
    "Notificaciones por correo y mensajes": "Email and message notifications",
    "STARTTLS (puerto 587)": "STARTTLS (port 587)",
    "SSL/TLS (puerto 465)": "SSL/TLS (port 465)",
    "Sin cifrado": "No encryption",
    # --- protecciones del monitor ---
    "Respaldos y carpeta de datos (ver, crear o exportar)": "Backups and data folder (view, create or export)",
    "Selección de variables (SPC, correlación, Variables en vivo) y modelo de estabilidad mostrado":
        "Variable selection (SPC, correlation, Live variables) and the stability model shown",
    "Modo de los lazos de control y activar el control automático":
        "Control loop mode and turning on automatic control",
    "Causas de paro y defectos, y entrenar el comportamiento normal":
        "Stop causes and defects, and training normal behavior",
    "Identidad de la estación, exportación al dashboard global, servidor y vistas del programa":
        "Station identity, global dashboard export, server and program views",
    "Cerrar el programa": "Close the program",
    "El monitoreo está en ejecución. Si cierras el programa la línea deja de vigilarse.\n\n¿Cerrar de todos modos?":
        "Monitoring is running. If you close the program the line stops being watched.\n\nClose anyway?",
    "📐 Mostrar «Análisis estadístico» en el monitor": "📐 Show “Statistical analysis” in the monitor",
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
    # --- cámaras ---
    "Cámara «{}» sin imagen: {}. Se conservan los últimos datos.": "Camera “{}” without image: {}. The last data is kept.",
    "Cámara «{}» con imagen de nuevo: se reanuda la lectura": "Camera “{}” has an image again: reading resumes",
    "cámara sin imagen: {}": "camera without image: {}", "display ilegible («{}»)": "unreadable display (“{}”)",
    "no numérico («{}»)": "not numeric (“{}”)", "color no reconocido (más cercano «{}» {})":
        "color not recognized (closest “{}” {})", "{} parpadeando": "{} blinking",
    "error de lectura: {}": "reading error: {}", "{}: la cámara '{}' no existe": "{}: the camera '{}' does not exist",
    "«{}»: calibra la aguja (centro, mínimo y máximo)": "“{}”: calibrate the needle (center, minimum and maximum)",
    "«{}» tiene {} variables. Se quitarán también.\n¿Continuar?": "“{}” has {} variables. They will be removed too.\nContinue?",
    # --- servidor propio ---
    "Línea registrada como «{}». Pulsa Aceptar para empezar a enviar.":
        "Line registered as “{}”. Press OK to start sending.",
    "Servidor en línea (versión {}).": "Server online (version {}).",
    "Clave válida para la línea «{}».": "Valid key for line “{}”.", "Último envío hace {} s": "Last sent {} s ago",
    "{} lotes en espera": "{} batches waiting", "sin conexión con el servidor ({})": "no connection to the server ({})",
    "Clave de línea no válida": "Invalid line key", "Clave de registro incorrecta": "Wrong registration key",
    "El registro de líneas está desactivado en el servidor": "Line registration is disabled on the server",
    # --- control PID ---
    "próximo ajuste en {} s": "next adjustment in {} s", "ajustaría {} → {}": "would adjust {} → {}",
    "ajustado a {}": "adjusted to {}", "espera tras un cambio del operador ({} s)": "waiting after an operator change ({} s)",
    "el PID aprendido aún no tiene suficientes observaciones ({} de {})": "the learned PID does not have enough observations yet ({} of {})",
    "{} → {}: aplica o ignora": "{} → {}: apply or ignore",
    "Control «{}» (simulación): ajustaría «{}» {} → {} ({})": "Control “{}” (simulation): would adjust “{}” {} → {} ({})",
    "Control «{}»: «{}» {} → {} ({})": "Control “{}”: “{}” {} → {} ({})",
    "Control «{}» detenido: {}. Revisa el HMI y vuelve a activarlo.": "Control “{}” stopped: {}. Check the HMI and activate it again.",
    "Control «{}» detenido: {}": "Control “{}” stopped: {}",
    "Control «{}»: el operador cambió «{}» {} → {}; espera {} s": "Control “{}”: the operator changed “{}” {} → {}; waiting {} s",
    "Control «{}»: cambio de receta, espera antes de ajustar": "Control “{}”: recipe change, waiting before adjusting",
    "Control «{}»: la propuesta ya no es vigente; se recalcula": "Control “{}”: the proposal is no longer valid; recalculating",
    "el HMI no muestra el valor escrito ({}; se lee {})": "the HMI does not show the written value ({}; it reads {})",
    "el HMI no está en la pantalla del input («{}»)": "the HMI is not on the input screen (“{}”)",
    "Control «{}»: elige la medición a controlar": "Control “{}”: choose the measurement to control",
    "Control «{}»: elige el input del HMI que se ajusta": "Control “{}”: choose the HMI input to adjust",
    "Control «{}»: el input debe leerse de la pantalla del HMI": "Control “{}”: the input must be read from the HMI screen",
    "Control «{}»: indica los límites mínimo y máximo del input": "Control “{}”: set the input's minimum and maximum limits",
    "Control «{}»: indica el valor objetivo": "Control “{}”: set the target value",
    "Control «{}»: graba el clic del campo del input": "Control “{}”: record the click on the input field",
    "Control «{}»: graba los botones + y −": "Control “{}”: record the + and − buttons",
    "Control «{}»: el recorrido de la ruta no existe": "Control “{}”: the route tour does not exist",
}
