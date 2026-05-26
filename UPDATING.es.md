# Actualización a una nueva versión

Esta guía cubre cómo migrar un despliegue de ADO Backup a una release más
reciente. El contenedor muestra la versión que está corriendo en el banner
de arranque (`ADO Backup Tool vX.Y.Z starting`) y consulta la API de
GitHub Releases una vez en cada boot, así que con `tail logs/backup.log`
ya sabes tanto la versión actual como si hay una más nueva publicada.

Se documentan dos caminos, ambos completamente soportados — elige según
cómo prefieras gestionar el despliegue:

- **Vía Container Station GUI** — sin SSH, sin scripts; mantiene la app
  completamente gestionada por CS (vista Applications con todos los
  botones GUI-level, sin el warning de "externally created"). Recomendado
  si ya usas CS para gestionar tus contenedores QNAP.
- **Vía SSH / scripteada** — un comando por release, versión pineada por
  tag de git. Bueno para setups desatendidos o quien prefiera un script
  repetible. Rompe la gestión GUI de CS (la app pasa a mostrar
  "externally created"); elige un modelo y mantén la consistencia.

## Flujo por Container Station GUI (sin SSH)

1. **Consigue el código nuevo.** En tu equipo:
   - O hacer pull del último tag de
     <https://github.com/mainmind83/ado-backup> (`git fetch --tags &&
     git checkout vX.Y.Z`), o
   - Descargar el zip del source de la página de la release en GitHub.

2. **Copia los ficheros nuevos al NAS, *excluyendo* `config.yaml`.** El
   repo trae un `config.yaml` con valores placeholder; ese fichero también
   es el config operativo en el NAS, así que una copia ciega pisaría tu
   configuración real. Comando recomendado desde PowerShell:

   ```powershell
   robocopy "<repo-local>" "<smb-share>\app" /E `
       /XF config.yaml docker-compose.qnap.yml `
       /XD .git .pytest_cache __pycache__
   ```

   - `/XF config.yaml` protege tu config real.
   - `/XF docker-compose.qnap.yml` protege tu PAT inlineado.
   - `/XD .git .pytest_cache __pycache__` salta artefactos de desarrollo y
     el directorio git (no necesario para el build).

3. **Reconstruye desde Container Station.** Applications → `ado-backup` →
   **Reconstruir / Rebuild**. CS lee la directiva `build:` del compose,
   construye una imagen nueva y recrea el contenedor.

   > "Volver a crear" **no es** la opción correcta — solo recrea el
   > contenedor reutilizando la imagen cacheada, sin rebuild.

4. **Verifica.** Mira el log y busca el banner de la versión nueva:

   ```
   ================================================================
   ADO Backup Tool vX.Y.Z starting
     organization : ...
     projects     : ...
   ================================================================
   version check: vX.Y.Z is the latest release
   ```

   Si `version check` reporta una versión más nueva que el banner, la
   imagen sigue corriendo el código viejo — revisar el paso de Rebuild.

## Flujo por SSH / scripteado (opcional)

Para quien quiera actualizaciones de un solo comando y tenga `app/`
configurado como working copy de git, mira [`update.sh`](update.sh) en la
raíz del repo. Ejecuta git dentro de un contenedor `alpine/git` (sin
necesidad de instalar git en el host), pinea al tag dado y reconstruye
vía `docker compose`.

```
./update.sh v0.X.Y
```

**Caveat:** si originalmente creaste la app por la GUI de Container
Station, pasar a updates por SSH hará que CS marque la app como
"externally created" con un warning. Elige un modelo de gestión y
mantén la consistencia.

## Resolución de problemas

### `failed to solve: error creating zfs mount` durante el build

Bug conocido entre el docker de Container Station, BuildKit y el backend
ZFS en algunas firmwares de QTS. Workaround: forzar el builder legacy por
SSH y después reiniciar desde CS.

```
sudo DOCKER_BUILDKIT=0 docker build -t ado-backup:latest /share/<tu-share>/<ruta-app>
```

Cuando termine el build, pulsa **Restart** sobre la app en CS — al
recrear el contenedor cogerá la nueva imagen `ado-backup:latest`. No hace
falta hacer nada más por GUI.

### `Expecting value: line 3 column 1` u otros errores JSON al listar proyectos

ADO está devolviendo la página HTML de Sign-In (status 203 +
`text/html`) en vez de JSON. Casi siempre significa que el PAT está
revocado, caducado, o con un scope insuficiente. Comprueba la variable
desde dentro del contenedor:

```
sudo docker exec ado-backup sh -c 'echo "ADO_PAT length: ${#ADO_PAT}"'
```

- Length `0` → la variable no está. Comprobar que `ADO_PAT=<valor>` esté
  inlineado en tu `docker-compose.qnap.yml` (no el placeholder del repo).
- Length `52` → el PAT llega al contenedor pero ADO lo rechaza.
  Regeneralo en Azure DevOps con scopes `Code: Read` y
  `Project and Team: Read` (los dos son necesarios — solo `Code` permite
  `git clone` pero no la llamada REST que lista proyectos).

### La imagen vieja sigue corriendo tras Rebuild

Confirma qué hay dentro del contenedor, independientemente del disco:

```
sudo docker exec ado-backup grep "__version__" /app/src/main.py
sudo docker images ado-backup --format "{{.CreatedAt}}"
```

Si `__version__` no muestra la versión esperada, la imagen no se
reconstruyó. Causa más común en CS: usar "Volver a crear" en vez de
"Rebuild" — ver paso 3 arriba.

## Rollback

Cada carpeta timestamped bajo tu destino de backup es un snapshot
autocontenido (ver el README principal para detalles). El rollback **de
la herramienta** consiste en repetir el flujo de actualización con el
tag anterior. Los datos respaldados no se ven afectados por cambios de
versión de la tool.
