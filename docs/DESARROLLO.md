# Flujo de desarrollo, versiones y respaldos

## Ramas

| Rama | Para qué | Descarga |
|---|---|---|
| `main` | Lo estable: solo entra por *pull request* con las pruebas en verde | Cada versión `vX.Y.Z` queda publicada para siempre |
| `develop` | Integración: aquí se juntan las mejoras para probarlas en el HMI | Release **dev** (se reemplaza en cada push) |
| `feature/<nombre>` | Una mejora a la vez (p. ej. `feature/problemas-proceso`) | Solo el .zip como artefacto de Actions (30 días) |
| `fix/<nombre>` | Corrección urgente de una versión estable | Igual que `feature/*` |

```
feature/x ──PR──▶ develop ──(probado en el HMI)──PR──▶ main ──etiqueta vX.Y.Z──▶ versión estable
```

- Una rama `feature/*` nunca cambia la descarga del HMI. Así se puede dejar a medias sin riesgo.
- `main` y `develop` están protegidas en GitHub: no se pueden borrar ni reescribir, y para `main` las
  pruebas de Windows deben pasar antes de fusionar.
- Un trabajo grande se sube a su rama al final de cada sesión, aunque esté incompleto: es su respaldo.

## Descargas

- **Estable (producción):** https://github.com/LuisLegarda/Extrusion-AI-agent/releases/latest/download/ExtrusionMonitor-windows.zip
- **Prueba (develop):** https://github.com/LuisLegarda/Extrusion-AI-agent/releases/download/dev/ExtrusionMonitor-windows.zip
- **Una versión anterior:** https://github.com/LuisLegarda/Extrusion-AI-agent/releases → `ExtrusionMonitor-vX.Y.Z-windows.zip`

*Ayuda → Acerca de* muestra la versión y el canal. Ejemplo: `0.2.0` (estable) o `0.3.0 · prueba (develop a1b2c3d, …)`.

## Publicar una versión estable

1. En `develop`, sube `__version__` en `src/extrusion_monitor/__init__.py`. Mueve lo de *Sin publicar*
   en `CHANGELOG.md` a `## [X.Y.Z] - fecha`.
2. Abre un PR `develop → main` y fusiónalo cuando las pruebas pasen.
3. Crea la etiqueta:

   ```bash
   git tag vX.Y.Z origin/main
   ```

   ```bash
   git push origin vX.Y.Z
   ```

4. GitHub Actions comprueba que la etiqueta coincide con la versión y con el CHANGELOG. Después construye y
   publica la versión. Las notas de la versión salen del CHANGELOG.

## Actualizar el HMI

1. Cierra el monitor.
2. Descomprime el .zip nuevo **encima** de la carpeta actual y acepta reemplazar. La carpeta `data` del zip
   está vacía, así que no toca tu configuración ni tu historial.
3. Abre el programa. Al detectar una versión nueva, primero guarda un respaldo de la configuración.

**Volver a la versión anterior:** descarga `ExtrusionMonitor-vX.Y.Z-windows.zip` de *Releases* y descomprímelo
igual. Si la configuración quedó mal, restaura el respaldo previo (ver abajo).

## Respaldos

### Del código
Están en GitHub: cada commit, cada rama y cada versión etiquetada con su .exe. Para recuperar un estado
anterior basta su etiqueta o commit.

### De los datos de cada línea
Se guardan en `%LOCALAPPDATA%\ExtrusionMonitor\respaldos`, fuera de la carpeta del programa. Se conservan
los 15 más recientes.

- **Cuándo se crean:** automáticamente al abrir una versión nueva (`…-desde-v0.2.0.zip`) y una vez por semana.
  También a mano con *Archivo → 🛟 Crear respaldo de la configuración*.
- **Qué incluyen:** variables, pestañas, recetas, recorridos, comportamientos entrenados, plantillas de OCR,
  ajustes del dock, del Inicio y de la estación. No incluyen el historial (`history.sqlite`) ni los reportes,
  porque son grandes. Para respaldar el historial, copia `data\history.sqlite` con el programa cerrado.
- **Restaurar:** cierra el programa. Abre el .zip y copia el contenido de su carpeta `datos\` en la carpeta de
  datos (*Archivo → Abrir carpeta de datos*).

## Antes de fusionar (lista corta)

- [ ] Las pruebas pasan: `python -m pytest -q`
- [ ] Textos nuevos con su traducción en `i18n_en.py`
- [ ] Una configuración vieja se sigue cargando: campos nuevos con valor por omisión y validadores de migración
- [ ] `CHANGELOG.md` → *Sin publicar* actualizado
- [ ] Probado en el HMI desde la versión de prueba (para cambios de lectura, recorridos o dock)
