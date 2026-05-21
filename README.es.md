# ADO Backup Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](Dockerfile)

> 🇬🇧 **Prefer English?** → [README.md](README.md)

Un contenedor Docker que hace backup automático de recursos de Azure DevOps
(ADO) — repositorios Git, definiciones de pipelines y wikis — a un volumen
local. El contenedor corre de forma continua con un planificador cron interno.
Todo el comportamiento se controla con un único [`config.yaml`](config.yaml).

## Qué hace backup

| Recurso   | Cómo |
|-----------|------|
| Repos Git | Bare mirrors (`git clone --mirror`), actualizados incrementalmente |
| Pipelines | Definiciones de build + release exportadas como JSON individuales |
| Wikis     | Metadatos del wiki (`meta.json`) + páginas en markdown |

## Inicio rápido

```bash
git clone https://github.com/mainmind83/ado-backup.git
cd ado-backup
```

1. Crea un PAT en Azure DevOps con los [scopes necesarios](#scopes-necesarios-del-pat).
2. Edita [`config.yaml`](config.yaml) (organización, proyectos, schedule, retención).
3. Proporciona el PAT mediante la variable de entorno `ADO_PAT`.
4. Construye y arranca:

```bash
export ADO_PAT=tu-pat-aqui
docker compose up -d --build
```

Los logs salen por `docker logs` y a `/logs/backup.log` (rotado).

## Scopes necesarios del PAT

Crea el PAT en **User settings → Personal access tokens → New Token** dentro
de Azure DevOps. Todos los scopes son de **lectura** — la herramienta nunca
escribe en ADO.

| Scope (etiqueta en UI)| Permiso  | Para qué                                    |
|-----------------------|----------|----------------------------------------------|
| Code                  | Read     | Listar repos y `git clone --mirror` por HTTPS|
| Build                 | Read     | Exportar definiciones de pipelines de build  |
| Release               | Read     | Exportar definiciones de pipelines de release|
| Wiki                  | Read     | Listar wikis y exportar páginas como markdown|
| Project and Team      | Read     | Resolver `projects: ["*"]` a la lista real   |

Consejos:

- Pon una **expiración** larga (máximo 1 año). Agenda la renovación — cuando
  el PAT expira el contenedor falla con `ADOAuthError: authentication failed (401)`.
- Si limitas `azure_devops.projects` a nombres concretos (no `["*"]`) y tienes
  los IDs de proyecto a mano, puedes omitir **Project and Team** — pero
  listar por nombre sigue usándolo, así que déjalo activado salvo que sepas
  que no lo necesitas.
- Desactiva cualquier recurso que no quieras respaldar en
  [`config.yaml`](config.yaml) (`backup.resources`) y podrás eliminar el
  scope correspondiente.

## Configuración

Mira [`config.yaml`](config.yaml) para el esquema completo anotado. Cualquier
valor escrito como `${VAR_NAME}` se resuelve desde el entorno del contenedor
en el arranque; si la variable falta, el contenedor sale con un error claro.

Opciones clave:

- `schedule` — expresión cron estándar (por defecto `0 2 * * *`, diaria a las 02:00).
- `run_on_start` — lanza un backup inmediato al arrancar (por defecto `false`).
- `azure_devops.projects` — lista de nombres de proyecto, o `["*"]` para todos.
- `backup.retention_days` — borra backups con más de N días (`0` = guardar siempre).
- `backup.resources` — activa/desactiva `git` / `pipelines` / `wikis` individualmente.

## Despliegue en QNAP (Container Station)

QNAP no tiene las rutas genéricas `/mnt/nas` que usa
[`docker-compose.yml`](docker-compose.yml). Usa
[`docker-compose.qnap.yml`](docker-compose.qnap.yml), que mapea carpetas
compartidas de QNAP.

**1. Crea carpetas compartidas** (o subcarpetas dentro de una existente). El
ejemplo siguiente usa una carpeta compartida existente llamada `Almacen` con
el proyecto agrupado bajo `BACKUPs/ado/`:

| Ruta                                  | Propósito                                              |
|---------------------------------------|---------------------------------------------------------|
| `Almacen/BACKUPs/ado/app/`            | El proyecto entero: `Dockerfile`, `src/`, `config.yaml` |
| `Almacen/BACKUPs/ado/data/`           | Destino del backup (necesita espacio en disco)          |
| `Almacen/BACKUPs/ado/logs/`           | Logs persistidos                                        |

Copia el proyecto entero dentro de `Almacen/BACKUPs/ado/app/`. Las carpetas
compartidas son accesibles dentro del NAS como `/share/<NombreCarpeta>` (un
symlink estable) o `/share/CACHEDEV1_DATA/<NombreCarpeta>`. Ajusta las rutas
en [`docker-compose.qnap.yml`](docker-compose.qnap.yml) si tu layout es
diferente.

**2. Edita `config.yaml`** con tu organización, proyectos y schedule. Deja
`pat: "${ADO_PAT}"` para que el PAT venga del entorno y no del fichero.

**3. Pon el PAT directamente en `docker-compose.qnap.yml`.** El bloque
`environment:` ya tiene una línea `ADO_PAT=...` — sustituye el placeholder
por tu token real. **Borra esa línea del YAML antes de exportarlo o
compartirlo.**

> Evaluamos dos alternativas en Container Station y ninguna funcionó bien:
> `env_file:` apuntando a un `.env` adyacente falla porque Container Station
> copia el compose a su directorio interno y NO arrastra el `.env`
> (`The "ADO_PAT" variable is not set`); y la pestaña "Environment Variables"
> del asistente *Create → Application* guarda el valor sin máscara en la
> config interna y lo muestra en claro en la GUI — no aporta nada real
> frente a tenerlo inline en el YAML. Mantener el PAT en el YAML dentro del
> NAS (con permisos SMB restringidos al usuario admin) es el equilibrio
> pragmático.

**4. Crea la aplicación.** En Container Station → **Create → Application**,
pega el contenido de [`docker-compose.qnap.yml`](docker-compose.qnap.yml).
Su directiva `build:` apunta a la carpeta del proyecto en el NAS, así que
Container Station construye la imagen desde el `Dockerfile` automáticamente
al crear la aplicación — no hace falta SSH.

> Nota: no hay un campo en la GUI para pegar un `Dockerfile` directamente —
> Container Station lo construye vía la directiva `build:` del compose pegado,
> así que `Dockerfile` y código fuente tienen que existir físicamente en la
> carpeta `app/`. Construir por SSH (`docker build -t ado-backup:latest .`)
> también funciona y es opcional, no obligatorio.

**Notas:**

- El contenedor corre como `root`, así que puede escribir en carpetas
  compartidas de QNAP sin configuración extra de permisos.
- `TZ` en [`docker-compose.qnap.yml`](docker-compose.qnap.yml) (por defecto
  `Europe/Madrid`) controla la zona horaria en la que se evalúa la expresión
  cron de `schedule` — ajústala a tu NAS.
- Pon `run_on_start: true` en `config.yaml` para una primera prueba sin tener
  que esperar al cron.
- Mira el progreso en el visor de logs de Container Station, o haz tail de
  `logs/backup.log` desde File Station.

## Estructura de salida

Cada ejecución crea una carpeta con timestamp dentro del destino del backup:

```
/backup/2024-06-15T020001/
└── Project1/
    ├── git/RepoA.git/                     # bare git mirror
    ├── pipelines/build/pipeline-101-Name.json
    ├── pipelines/release/release-1-Name.json
    └── wikis/Project1.wiki/
        ├── meta.json
        └── pages/Home.md
```

Los repos Git se respaldan incrementalmente: el bare mirror de la ejecución
anterior se copia adelante y se refresca con `git remote update`, evitando un
re-clone completo cada vez.

### Restaurar un repositorio

El formato en disco es un bare mirror de git estándar. Para recuperar una
copia de trabajo desde cualquier backup con timestamp:

```bash
git clone /ruta/al/backup/2024-06-15T020001/Project1/git/RepoA.git repo-restaurado
cd repo-restaurado
git checkout main
```

Todas las ramas, tags e historia quedan preservados.

## Manejo de errores

- Errores de validación del config o falta del PAT → el contenedor sale inmediatamente.
- Fallo de autenticación contra ADO (401) → la ejecución se aborta, el backup anterior **no** se borra.
- Fallo de un solo recurso (p.ej. un repo) → se loguea, la ejecución continúa.
- Wikis vacías o sin páginas publicadas devuelven HTTP 404 en la API de páginas — esto se loguea como **warning**, no error, y la ejecución continúa.

## Desarrollo

```bash
pip install -r requirements-dev.txt
pytest -v
```

Ejecutar localmente contra un fichero de config (en vez del
`/app/config.yaml` por defecto):

```bash
python src/main.py ruta/al/config.yaml
```

## Fuera de alcance (v1.0)

Work items, artefactos, test plans, restore/import, soporte multi-organización,
autenticación no-PAT, repositorios TFVC.

## Contribuir

Issues y pull requests son bienvenidos. Por favor asegúrate de que
`pytest -v` pasa antes de abrir una PR, y añade tests para cualquier
comportamiento nuevo.

## Licencia

[MIT](LICENSE) © 2026 Fernando Zabalza Salvador
