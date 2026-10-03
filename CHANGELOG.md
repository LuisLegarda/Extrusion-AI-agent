# Cambios por versión

Formato: cada versión estable tiene su sección `## [X.Y.Z] - fecha`. Lo que está en desarrollo va en
`## [Sin publicar]` y se mueve a una versión al publicarla (ver [docs/DESARROLLO.md](docs/DESARROLLO.md)).

Numeración `MAYOR.MENOR.PARCHE`:
- **PARCHE** (0.2.**1**): correcciones sin cambios de configuración.
- **MENOR** (0.**3**.0): funciones nuevas; la configuración anterior se sigue leyendo.
- **MAYOR** (**1**.0.0): cambios que requieren reconfigurar o que no son compatibles con versiones anteriores.

## [Sin publicar]

### En desarrollo (rama `feature/problemas-proceso`)
- Problemas de proceso: captura de causas de paro y defectos de calidad por el operador, catálogos en la
  receta, paros planeados fuera del OEE, Pareto en el monitor y en el dashboard global con CSV.

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
