# Cambios por versión

Formato: cada versión estable tiene su sección `## [X.Y.Z] - fecha`. Lo que está en desarrollo va en
`## [Sin publicar]` y se mueve a una versión al publicarla (ver [docs/DESARROLLO.md](docs/DESARROLLO.md)).

Numeración `MAYOR.MENOR.PARCHE`:
- **PARCHE** (0.2.**1**): correcciones sin cambios de configuración.
- **MENOR** (0.**3**.0): funciones nuevas; la configuración anterior se sigue leyendo.
- **MAYOR** (**1**.0.0): cambios que requieren reconfigurar o que no son compatibles con versiones anteriores.

## [Sin publicar]

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
