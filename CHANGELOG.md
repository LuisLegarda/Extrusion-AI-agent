# Cambios por versión

Formato: cada versión estable tiene su sección `## [X.Y.Z] - fecha`. Lo que está en desarrollo va en
`## [Sin publicar]` y se mueve a una versión al publicarla (ver [docs/DESARROLLO.md](docs/DESARROLLO.md)).

Numeración `MAYOR.MENOR.PARCHE`:
- **PARCHE** (0.2.**1**): correcciones sin cambios de configuración.
- **MENOR** (0.**3**.0): funciones nuevas; la configuración anterior se sigue leyendo.
- **MAYOR** (**1**.0.0): cambios que requieren reconfigurar o que no son compatibles con versiones anteriores.

## [Sin publicar]

### Posiciones de las variables en todas las recetas (rama `fix/posiciones-todas-las-recetas`)
- Cada receta guarda su propia copia de la configuración (pantallas, posiciones de las variables, recorridos).
  Al corregir una posición solo se guardaba en la receta activa, y al cargarse otra receta (p. ej. porque el
  HMI la muestra, con «Cargar automáticamente la receta del HMI») volvía la posición anterior. Ahora, al
  guardar la configuración, se pregunta si los cambios se aplican también a las demás recetas (recomendado).
- Cuando el programa cambia de receta (y con ella toda la configuración) lo avisa en la barra de estado.

## [0.3.1] - 2026-10-27

Corrección de la 0.3.0; no cambia la configuración.

### Purga del historial con conexión propia (rama `fix/purga-conexion-propia`)
- La limpieza horaria del historial usa su propia conexión a la base de datos y ya no toma el candado del
  monitoreo: en una PC con disco lento (o con el antivirus revisando el archivo) el monitoreo ya no puede
  quedarse esperando varios segundos. La prueba comprueba esto sin depender de tiempos.

## [0.3.0] - 2026-10-27

### Icono (rama `feature/icono`)
- Icono propio del monitor (anillo con tendencia y punto verde) y su pareja para el dashboard global, en los
  ejecutables y en las ventanas. El `.ico` lleva los tamaños estándar de Windows (16 a 256 px), con un dibujo
  simplificado de 16 a 32 px. Se regeneran con `python packaging/icon/make_icons.py`.
- La limpieza horaria del historial corre en un hilo aparte: el monitoreo ya no la espera (en una PC con disco
  lento podía tardar varios segundos).

### Exportar y traducciones (rama `feature/exportar-produccion`)
- «Exportar» en lugar de «Exportar CSV» en el monitor (historial: 24 h, 7 o 30 días), el dashboard (resumen de
  las líneas o sus datos por minuto de 24 h / 7 días), los problemas de proceso y el análisis estadístico (sus
  datos o su tabla de resultados). Al exportar se elige el formato:
  - **CSV** (como antes, para Excel en español);
  - **Excel** (.xlsx con números y fechas reales, encabezado fijo y filtros; sin dependencias nuevas);
  - **CSV para software estadístico (Minitab)**: separado por tabulaciones, punto decimal, «*» en los
    faltantes y nombres de columna válidos; opcionalmente se copia al portapapeles para pegarlo con Ctrl+V.
- Revisión completa de las traducciones al inglés (barrido del código y de cada ventana, diálogo y análisis):
  - el reporte PDF, las notificaciones y las conclusiones del analizador de planta ahora salen en inglés;
  - ~150 textos nuevos (exportar, Personal, Problemas de proceso, cámaras, validaciones, grupos del análisis);
  - las listas desplegables que se llenan después de abrir la ventana y los textos especiales de los campos
    numéricos («automático») también se traducen;
  - pruebas nuevas: todo `tr("…")` tiene traducción, sin claves repetidas y con los mismos campos `{…}`.
- El análisis estadístico exporta bien varias líneas con los mismos minutos (antes se mezclaban).
- La tarjeta de línea del dashboard ya no muestra la ruta de la carpeta compartida en su ayuda.

### Preparación para producción (misma rama; lista en [docs/PRODUCCION.md](docs/PRODUCCION.md))
- Historial: la purga horaria ya no recorre toda la tabla ni detiene el monitoreo (borra por bloques); exportar
  el historial usa el índice por variable.
- «Archivo › Restaurar respaldo…» (con sesión de supervisor): se aplica al volver a abrir, respaldando antes lo
  actual.
- Si `config.json` está dañado (p. ej. por un apagón), se recupera solo del último respaldo válido y se avisa;
  las escrituras de configuración se fuerzan a disco.
- Registro con rotación (5 MB × 5), errores no atrapados y cierres abruptos registrados, y mensaje visible si el
  programa no puede abrir.
- En Windows, si no se puede cifrar una contraseña o token de notificaciones, ya no se guarda legible.
- Limpieza: imports sin usar, código muerto y traducciones repetidas.
- «Configuración › Guardado de datos…»: cuánto se conservan el historial de esta PC y lo publicado para el
  dashboard global (3 meses, **6 meses por defecto**, 1 año o indefinido), con el espacio que ocupa y cuánto
  crece por día. Antes el historial se guardaba 90 días fijos y la carpeta del dashboard 30 días.

### Análisis del dashboard sin monitoreo (rama `fix/analisis-dashboard-sin-monitoreo`)
- El análisis estadístico del dashboard mostraba vacío cuando el monitor de la línea estaba abierto sin
  monitorear: al abrirlo se reescribía `status.json` sin la lista de variables. Ahora el monitor publica
  siempre el catálogo de variables de la receta y el dashboard también recupera las variables de los
  archivos de tendencia de la carpeta (sirve con datos de versiones anteriores).

### Mantenimiento, mapa y ajustes (rama `feature/mantenimiento-ajustes`)
- Mantenimiento del dashboard como administrador de preventivos y correctivos de solo lectura: clasifica los
  paros capturados en los monitores (por categoría y causa, con reglas ajustables), muestra indicadores
  (preventivos atrasados, eventos y horas, % de mantenimiento programado, MTTR correctivo, desperdicio), el
  estado de cada línea (último preventivo y correctivo, hace cuánto, MTBF) y la lista de registros. Las líneas
  aparecen solas; se pueden agregar líneas sin monitor. Se quitó la captura de equipos del dashboard.
- Mapa de planta con mosaicos por línea (como Variables en vivo): estado, OEE, producción del turno contra la
  meta, receta, velocidad, paros y alarmas, agrupados por área.
- Ventana «Nuevo análisis»: ya no se recortan opciones en pantallas angostas.
- Bloqueo del zoom con la rueda: activado por defecto y en el menú Configuración del monitor y del dashboard.

### Dashboard para ingeniería y gerencia (rama `feature/planta-gerencia`)
- Producción contra meta: producción por turno y por día de cada línea contra su meta, con % de cumplimiento.
  El monitor ahora publica cada minuto la producción acumulada del turno, el estado de la máquina y el usuario
  en turno.
- Metas por línea (o para todas) y semáforo del mes: OEE, disponibilidad, MTTR, desperdicio por día y
  cumplimiento de producción, contra el mes anterior.
- Costos: hora de paro y unidad de desperdicio; costo del paro, del desperdicio y total (costo de la mala
  calidad) por línea y en las conclusiones.
- Turnos y operadores: OEE y paros por turno en cada línea y ranking de operadores entre líneas.
- Mapa de planta: las líneas en su ubicación (plano de fondo opcional, se acomodan arrastrando), color por estado
  y parpadeo en alarma; también en modo TV.
- Mantenimiento: plan preventivo por equipo con horas de operación (amarillo al 80 %, rojo al 100 %, «servicio
  hecho») y fallas por causa con MTBF y MTTR.
- Reporte semanal automático del analizador (PDF) por correo o mensaje, el día y hora elegidos; también «Enviar
  ahora» y «📄 Reporte PDF» en el analizador.

### Dashboard: analizador de planta, problemas y análisis estadístico (rama `feature/dashboard-analisis`)
- Las secciones del dashboard se abren dentro de la misma ventana: Líneas, Analizador de planta, Problemas de
  proceso (antes era una ventana aparte) y Análisis estadístico.
- Analizador de planta: conclusiones automáticas ordenadas por importancia; indicadores por línea (OEE, pérdidas
  de disponibilidad, rendimiento y calidad, Δ contra el periodo anterior, estabilidad, índice 5.0, Cpk, paros,
  minutos de paro, MTTR, MTBF, desperdicio, alarmas por hora y costo del paro); gráficas de OEE y pérdidas,
  tiempo muerto, causas principales de la planta y tendencias diarias de OEE, estabilidad e índice 5.0; tabla de
  Industria 5.0 (personas, resiliencia, sostenibilidad).
- Análisis estadístico en el dashboard con los datos que publican los monitores (promedios por minuto), con
  filtro y agrupación por línea; el Pareto también agrupa por línea.
- «Reconocer avisos» ahora se llama «Silenciar avisos», muestra cuántas líneas están avisando y explica qué hace.

### Protecciones y detalles del monitor (rama `fix/protecciones-monitor`)
- Protegidas por defecto con la sesión de supervisor (además de las anteriores): exportación al dashboard
  global, identidad de la estación, modo de los lazos de control, causas de paro y defectos, entrenar el
  comportamiento normal, respaldos y carpeta de datos, y la selección de variables en Variables en vivo.
- Corregido: como operador, «Cargar automáticamente la receta del HMI» (menú Receta) dejaba el aviso de
  supervisor en bucle sin poder cancelarlo.
- Si el monitoreo está en marcha, cerrar el programa pide confirmación.
- Configuración → «Mostrar Análisis estadístico en el monitor» (se puede ocultar si se usa el del dashboard).

### Notificaciones y reportes de análisis (rama `feature/notificaciones-reportes`)
- Configuración → Notificaciones (y botón en Alarmas y eventos): avisos por correo (SMTP), Telegram o
  Teams / Slack / Google Chat (webhook) de las alertas elegidas: variable fuera de límite o en aviso, error de
  lectura (tras N s), pantalla o cámara sin imagen, paro de máquina (tras N min, y aviso al reanudar), paro
  acumulado del turno, desperdicio alto en una captura o en el turno, Cpk bajo sostenido, OEE bajo al cerrar el
  turno, comportamiento anormal, tendencia al límite, control automático detenido por seguridad, inicio de
  sesión de supervisor, cambio de receta, monitoreo detenido o programa cerrado y reportes programados.
- Tiempo de espera para no repetir el mismo aviso, pausa general, botón «Enviar prueba» e historial de envíos.
  Los envíos van en un hilo aparte con reintentos y quedan en el registro de eventos. Contraseñas y tokens se
  guardan cifrados (DPAPI de Windows). Protegido con la sesión de supervisor.
- Análisis estadístico: «📄 Reporte PDF» junta varios análisis (gráficas, tablas e interpretación) en un PDF.
- Análisis programados (cada turno, día o semana): se recalculan con el periodo que terminó, el PDF se guarda en
  la carpeta de reportes (`analisis/`) y, si se eligió, se envía por correo o Telegram.

### Análisis estadístico (rama `feature/analisis-estadistico`)
- Nueva sección lateral «Análisis estadístico» con navegador de análisis: crear, abrir con un clic, cambiar
  (doble clic), duplicar, renombrar y eliminar; se guardan en `<datos>/analisis/` y se recalculan con el historial.
- 14 análisis: estadística descriptiva (media, desv. estándar, varianza, mín/máx, rango, mediana, cuartiles,
  suma de cuadrados, asimetría, curtosis), comparar grupos (gráfica de intervalos, ANOVA y t de Welch),
  normalidad (Anderson-Darling), histograma (superpuesto o por panel), boxplot, gráfica de tiempo, barras,
  capacidad (Cp, Cpk, Pp, Ppk, Cpm, PPM), Capability Sixpack, cartas I-MR y X̄-R, Pareto de paros y defectos,
  matriz multivariable con correlación, contorno y regresión (lineal, cuadrática, interacciones) con
  simulación de respuesta.
- Datos por rango de fecha y hora, agrupados o filtrados por turno, día, semana, mes, hora, operador y receta.
  El usuario en turno se registra en el historial para poder agrupar por operador.
- Cada análisis trae una interpretación en lenguaje claro. Título del análisis y de cada gráfica (doble clic) y
  colores de barras y líneas editables; exportación a PNG y CSV.

### Dashboard global con el estilo del monitor (rama `feature/dashboard-estilo`)
- Barra lateral con logo, texto y línea de la estación (Líneas, Problemas de proceso, Reconocer avisos,
  Exportar CSV, Modo TV, Configuración) y barra superior con buscador, filtro, orden y campana de alarmas.
- Tarjetas de resumen con el estilo del monitor. La ruta de la carpeta de datos ya no se muestra: solo si está
  conectada y cuántas líneas hay.

### Variables en vivo con mosaicos (rama `feature/variables-mosaicos`)
- Variables en vivo muestra un mosaico por variable, agrupados por pantalla del HMI y con filtro: estado
  (OK / aviso / alarma / dato viejo), valor y unidad, referencia y desviación, tolerancia y calidad de lectura.
- Clic derecho en un mosaico: gráfico (valor con tendencia corta, gauge, barra con límites, gráfica de tiempo,
  histograma), tamaño (1×1, 2×1, 2×2) y tiempo mostrado. Doble clic: graficar en Tendencias. Se guarda solo;
  con la protección de supervisor, cambiarlo pide la sesión («Tablero y gráficos»).
- La tabla anterior sigue disponible con el botón «☰ Tabla»; la vista elegida se recuerda.

### Gráficas y bloqueos (rama `feature/graficas-y-bloqueos`)
- Acción protegida sin sesión de supervisor: aviso «Se requiere supervisor» con el botón para iniciar sesión ahí
  mismo (número de empleado y contraseña); al entrar, el cambio se permite.
- Protegidas también (por defecto): las variables de SPC y de correlación y el modelo de estabilidad mostrado.
- Tendencias, SPC y Control: el alto de cada gráfica se cambia arrastrando su barra inferior con el ratón
  (doble clic: alto automático); si ya no caben, la página se desplaza.
- Ver → «Bloquear zoom de las gráficas con la rueda del ratón»: la rueda desplaza la página en lugar de acercar.

### Detalles de interfaz (rama `fix/detalles-interfaz`)
- Al abrir el programa el buscador ya no queda seleccionado (se activa con un clic o Ctrl+K).
- La protección con supervisor se activa sola en cuanto hay un supervisor con número de empleado y contraseña
  (ya no hay casilla para encenderla): sin usuario o con un operador en turno no se permiten los cambios.
- Barra lateral sin barra de desplazamiento.
- Tendencias: la escala Y ya no se reajusta con cada lectura; crece si los datos se salen y solo se reduce
  cuando sobra mucho espacio (p. ej. al salir un pico del rango mostrado).

### Turnos y confirmación del usuario (rama `feature/turnos`)
- Configuración → Personal tiene tres pestañas: *Personas* (con turno asignado y contraseña), *Turnos* (nombre y
  horario; los que cruzan la medianoche, p. ej. 22:00–06:00, también; se pueden crear desde los inicios del OEE)
  y *Confirmación*.
- Opcional: detectar el turno por la hora y, al empezar cada turno, pedir quién entra (lista con las personas de
  ese turno; «Más tarde» vuelve a preguntar en 10 min).
- Opcional: confirmar al usuario con su número de empleado, o con número de empleado y contraseña; también al
  cambiarlo en la barra superior. Escribir el número elige a la persona. Las contraseñas se guardan cifradas
  (PBKDF2-SHA256 con sal); no se pueden leer, solo reemplazar.
- La barra superior muestra el turno detectado con su horario.
- Usuarios: «+ Usuario» crea un operador por defecto; el puesto (operador / supervisor) se cambia en la lista.
- Protección opcional con inicio de sesión de supervisor (número de empleado y contraseña) para: la lista de
  personal (siempre), cambiar o editar recetas, Configurar receta (variables, recorridos, cámaras, control) y el
  tablero de Inicio y el dock. Opcionales también: activar el control automático o cambiar su modo, catálogos de
  paros y comportamientos, eliminar capturas, identidad / exportación / servidor, y detener o cerrar el programa.
  Sin la sesión de supervisor iniciada, esas acciones simplemente no se permiten (no se abren las listas ni los
  diálogos y el selector de receta queda deshabilitado). La sesión se inicia con «🔒 Supervisor» en la barra
  superior, dura los minutos elegidos sin usarse y se cierra desde ahí o al cambiar el usuario en turno.
  Desactivar el control siempre se permite. No se puede guardar la protección sin un supervisor que pueda iniciar sesión.

### Rediseño de la interfaz (rama `feature/rediseno`)
- Tema claro renovado (tarjetas redondeadas, barra lateral blanca con la página activa resaltada) y el oscuro con
  el mismo estilo. Íconos de línea propios en lugar de emojis en la barra lateral. Gráficas y gauges sin cambios.
- Barra superior: búsqueda, inicio del turno, campana con las alarmas y avisos activos, y un solo selector del usuario
  en turno (operador o supervisor). Los menús Archivo, Receta… se quedan arriba como antes.
- Búsqueda (Ctrl+K): variables (valor y límites; graficar, SPC, correlación), páginas, cualquier acción de los
  menús, recetas (pide confirmación), horas escritas («14:30», «ayer 14:30», «hace 2 h», «turno»: marca la hora en
  Tendencias o captura un paro desde ahí), paros capturados y alarmas de los últimos 30 días. Sin acentos ni
  mayúsculas, tolera errores de tecleo y recuerda las búsquedas recientes.
- Personal de la estación (Configuración → Personal): operadores y supervisores con número de empleado y
  activo/inactivo; no dependen de la receta. La captura de paros propone al operador en turno.
- Inicio: tarjetas de estado compactas (estado de la línea, paros, por identificar, alarmas, calidad, OEE; se
  ocultan en «Personalizar tablero») y un mosaico nuevo con la dona de causas de paro del turno.

### Servidor propio, etapa 1 (rama `feature/servidor`)
- Envío opcional de cada línea a un servidor propio (nube o planta) por HTTPS, además de la carpeta compartida
  o en su lugar: cola en disco (no se pierde nada sin red), lotes sin duplicar al reenviar, gzip, solo conexiones
  de salida desde el HMI. Registro de la línea con una clave de registro.
- Servidor (`server/`): API FastAPI + PostgreSQL + HTTPS automático (Caddy) + respaldos diarios, en Docker.
  Claves por línea, claves de lectura y de administración, retención configurable.

### Cámaras para equipos sin HMI (integrado en `develop`)
- Fuente de imagen por cámara USB o IP (RTSP / HTTP MJPEG), con rotación, corrección de perspectiva y
  exposición manual; reconexión automática y aviso de cámara sin imagen.
- Lectores nuevos: displays de 7 segmentos (LED/LCD), luces y torres andon por color con detección de
  parpadeo, agujas (manómetros) y barras de nivel. Pantalla y cámaras se combinan en la misma línea.
- Cámara simulada en el modo demo.

### Mejoras de interfaz (rama `feature/mejoras-interfaz`)
- Problemas de proceso: inicio y fin del rango también se escriben (dd/MM hh:mm:ss); a la izquierda, dos listas:
  *Paros por identificar* y *Capturas* (paros y calidad, con eliminar).
- SPC de varias variables a la vez (hasta 4), con lista como en Tendencias.
- Tendencias: límites de control (LCS / LCI = media ± 3σ de corto plazo) y Cpk / Ppk de lo visible en cada gráfica.
- Menú *Ver* sin las páginas que ya están en la barra lateral (los atajos Ctrl+1…9 siguen).
- Configuración de variables en dos secciones: *Variables del HMI* e *Indicadores físicos (cámaras)*.
- Las preferencias de vista se guardan solas: gráficas de tendencias, rango y opciones, variables de SPC y de
  correlación, y la página abierta.
- Estabilidad: sin picos falsos al abrir el programa o cuando una variable deja de leerse (calentamiento de 1 min
  con datos completos y solo lecturas recientes); el % de estabilidad espera a tener suficientes puntos.
- Identidad de la estación: logo de la empresa, texto propio y número de línea arriba a la izquierda
  (*Configuración → Identidad de la estación*).

### Control PID con aprendizaje (integrado en `develop`)
- Lazos de control que ajustan un input del HMI (p. ej. velocidad del capstan) según una medición (diámetro)
  hacia el nominal de la receta. Solo para la pantalla del HMI: escribe el valor (clic en el campo, valor y
  Enter, con confirmación opcional) o usa botones + / −, con ruta opcional a otra pestaña.
- Modos *simulación*, *asistido* (propone y el operador aplica, también con aviso flotante) y *automático*.
- PID manual por receta o aprendido de los cambios del operador: se observa la respuesta de la medición y se
  ajusta un modelo de primer orden con retardo; el PID sale por la regla SIMC.
- Seguridad: desactivado al abrir, límites, paso máximo por ajuste y por minuto, banda muerta, intervalo
  mínimo, verificación del valor escrito, paro por alarma, línea detenida, operador usando el HMI, dato viejo,
  comportamiento anormal o cambio de receta, y botón *Detener todo el control* (Ctrl+Shift+X).
- Página *Control* y pestaña *Control* en la configuración. El estado del control viaja al dashboard global.

### Problemas de proceso (rama `feature/problemas-proceso`)
- Página nueva *Problemas de proceso*: el operador clasifica los paros desde la línea de tiempo del estado de
  la máquina (el rango del paro se propone solo y se ajusta con barras), con causa, scrap, operador y comentario.
  Un paro se puede dividir en tramos con causas distintas. También se capturan problemas de calidad (defectos).
- Catálogos de dos niveles (categoría → causa / defecto) y lista de operadores en *Receta → Causas de paro y
  defectos*. Los paros planeados no cuentan contra la Disponibilidad del OEE.
- Aviso al reanudar la línea tras un paro largo y contador de paros sin clasificar en la barra lateral.
- Pareto por causa, categoría u operador (tiempo, frecuencia o scrap), resumen, tabla y CSV para Excel.
- Dashboard global: botón *📉 Problemas de proceso* con el análisis de todas las líneas (o por área) y CSV.
- Las capturas viajan a la carpeta compartida (`<línea>/problems/`) y al servidor propio.

## [0.2.0] - 2026-10-03

Primera versión estable numerada: incluye todo lo probado en el HMI hasta el 2 de octubre de 2026.

### Infraestructura
- Versiones estables permanentes en GitHub (`vX.Y.Z`) y versión de prueba desde la rama `develop`.
- Dependencias con versiones fijas para que el .exe no cambie solo.
- Respaldo automático de la configuración al estrenar versión y cada semana (*Archivo → Crear respaldo*).
- Número de versión y canal en *Ayuda → Acerca de*.

### Monitor de la línea
- Lectura del HMI por OCR (Windows OCR y plantillas) con variantes de preprocesado y votación.
- Árbol de pestañas, pares consigna/medición, selectores, fórmulas y recorridos automáticos con disparadores.
- Recetas como perfil completo, autocarga desde el HMI y límites mín/máx.
- Tendencias, SPC, correlación y comportamiento aprendido (estabilidad).
- KPI/OEE del turno con huecos productivos e índice Industria 5.0.
- Reportes PDF automáticos.
- Tablero de Inicio configurable: valor, gauge, barra, tendencia, histograma y gráficas de tiempo de KPI.
- Dock al minimizar: barra compacta sobre el HMI, grosor ajustable, modo de solo valor y color.
- Español/inglés y tema claro/oscuro.

### Dashboard global (`DashboardGlobal.exe`)
- Exportación del estado de cada línea a una carpeta compartida.
- Tarjetas con 1 a 5 indicadores, plantilla y ajustes por línea, áreas, avisos, modo TV, CSV.
- Hasta 12 columnas con tamaño automático.

## [0.1.0] - 2026-09-25
- Fase 1: monitor de parámetros, recetas y tendencias por OCR del HMI.
