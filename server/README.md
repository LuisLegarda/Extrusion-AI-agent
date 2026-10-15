# Servidor propio del monitor de extrusión

Recibe el estado, las alarmas, los eventos, las tendencias y las capturas de problemas de cada línea. Los guarda
en una base de datos y los pone a disposición del dashboard web (etapa 2) y de otras herramientas por una API.

```
Monitor (HMI) ──HTTPS (solo salida)──▶ Caddy (HTTPS) ──▶ API ──▶ PostgreSQL
                                                                   └─▶ respaldos diarios
```

## Qué necesitas

### Opción A: un servidor en la planta (recomendado para empezar)

| | Mínimo (10–20 líneas) | Para crecer (50–100 líneas) |
|---|---|---|
| Equipo | Mini PC o servidor con **4 núcleos, 8 GB RAM y SSD de 256 GB** | 8 núcleos, 16 GB RAM, SSD de 512 GB–1 TB |
| Sistema | **Ubuntu Server 24.04 LTS** (gratis) | Igual |
| Red | IP fija en la red de la planta, alcanzable desde los HMI | Igual. Conviene un UPS |

- **Ventajas:** los datos no salen de la planta, no hay costo mensual y funciona aunque se caiga internet.
- **Desventaja:** para verlo desde fuera de la planta hace falta VPN o publicarlo con dominio.

### Opción B: un servidor en la nube (VPS)

- **Proveedor:** cualquiera con Ubuntu: DigitalOcean, Hetzner, AWS Lightsail, Azure, Google Cloud.
- **Tamaño:** 2 vCPU y 4 GB RAM alcanzan para 10–20 líneas (unos US$10–25 al mes). Se agranda sin reinstalar.
- **Dominio:** un dominio o subdominio, por ejemplo `monitor.miempresa.com`, apuntando a la IP del VPS.
- **Ventaja:** se ve desde cualquier lugar.
- **Requisito:** los HMI necesitan salida a internet por HTTPS (puerto 443). Pide permiso a TI.

### Espacio en disco (aproximado)

| Datos por línea | Al día | Al año |
|---|---|---|
| Tendencias (1 punto por minuto, 50 variables) | ~3 MB | ~1 GB |
| Eventos | < 1 MB | < 300 MB |

Con 20 líneas y un año de historial, unos 25 GB. El estado actual se sobrescribe y no ocupa espacio.

## Instalación (Ubuntu, unos 20 minutos)

1. Instala Docker:

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   ```

2. Copia la carpeta `server/` del repositorio al servidor y entra en ella:

   ```bash
   git clone https://github.com/LuisLegarda/Extrusion-AI-agent.git && cd Extrusion-AI-agent/server
   ```

3. Crea tu configuración y edítala. Aquí van la dirección, la contraseña de la base de datos y la clave de registro de líneas:

   ```bash
   cp .env.example .env && nano .env
   ```

   Para generar contraseñas seguras:

   ```bash
   openssl rand -base64 30
   ```

4. Arranca todo. Se reinicia solo si se apaga el servidor:

   ```bash
   docker compose up -d
   ```

5. Crea tu clave de administrador y guárdala:

   ```bash
   docker compose exec api python -m extrusion_server.cli crear-clave "Administrador" --rol admin
   ```

6. Comprueba que responde: abre `https://TU-DIRECCIÓN/api/v1/health` en el navegador.

### HTTPS

- **Con dominio:** Caddy saca y renueva solo un certificado gratuito de Let's Encrypt. El dominio debe apuntar al
  servidor y los puertos 80 y 443 deben estar abiertos.
- **Red interna sin dominio:** pon en `.env` la IP del servidor, por ejemplo `SITE_ADDRESS=192.168.1.50`.
  Caddy genera un certificado interno. En el monitor, desmarca *Verificar el certificado HTTPS*, o instala el
  certificado raíz de Caddy en los HMI (más seguro).
- `SITE_ADDRESS=:80` (sin cifrado) solo para una primera prueba.

## Conectar cada línea

1. Abre en el HMI *Configuración → 🌐 Dashboard global (exportación)…*.
2. En *Servidor propio*, escribe la dirección (`https://monitor.miempresa.com`).
3. Pulsa *Registrar esta línea…* y escribe la clave de registro (`ENROLL_KEY` de tu `.env`). El servidor devuelve
   la clave propia de la línea y el monitor la guarda.
4. Marca *Enviar también al servidor* y pulsa *Aceptar*. La carpeta compartida puede seguir activa al mismo tiempo.

Cuando termines de registrar las líneas, puedes vaciar `ENROLL_KEY` en `.env` y aplicar el cambio:

```bash
docker compose up -d
```

Así nadie más puede registrar líneas.

## Administración

Los comandos se ejecutan dentro de `server/`, en el servidor. Se usa siempre el mismo prefijo,
`docker compose exec api python -m extrusion_server.cli`, seguido del comando:

| Para | Comando |
|---|---|
| Ver las líneas y su último envío | `lineas` |
| Nueva clave de una línea (la anterior deja de servir) | `clave-linea L01` |
| Desactivar una línea | `desactivar-linea L01` |
| Clave de lectura para un dashboard o herramienta | `crear-clave "Ingeniería" --rol viewer` |
| Ver o revocar claves | `claves` · `revocar-clave 3` |

Por ejemplo, para ver las líneas registradas:

```bash
docker compose exec api python -m extrusion_server.cli lineas
```

- **Actualizar el servidor:**

  ```bash
  git pull && docker compose up -d --build
  ```

- **Respaldos:** se hacen solos cada día en `server/respaldos/` y se conservan 14 días. Copia esa carpeta a otro
  equipo o disco.

  Para restaurar un respaldo:

  ```bash
  docker compose exec -T db pg_restore -U extrusion -d extrusion --clean < respaldos/ARCHIVO.dump
  ```

## API (para el dashboard web y otras herramientas)

| Método | Ruta | Clave |
|---|---|---|
| GET | `/api/v1/health` | — |
| POST | `/api/v1/register` | clave de registro (`X-Enroll-Key`) |
| POST | `/api/v1/ingest` | clave de la línea |
| GET | `/api/v1/lines` · `/lines/{id}/status` · `/events` · `/trend` · `/problems` | viewer |
| POST | `/api/v1/admin/lines/{id}/token` · `/disable` | admin |

La documentación interactiva está en `https://TU-DIRECCIÓN/docs`.

## Seguridad

- **Conexión:** el HMI solo abre conexiones de salida hacia el servidor. No hay puertos abiertos en el HMI y el
  servidor nunca envía órdenes a la máquina.
- **Claves:** cada línea tiene su propia clave. En la base de datos solo se guarda su hash, y una clave robada se
  revoca sin tocar las demás.
- **Datos:** viajan cifrados (HTTPS) y comprimidos.
- **Servidor:** mantén Ubuntu actualizado.

  ```bash
  sudo apt update && sudo apt upgrade
  ```

  Si el servidor está en internet, deja abiertos solo los puertos 80 y 443.
