# ADO Backup Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](Dockerfile)

> 🇪🇸 **¿Prefieres español?** → [README.es.md](README.es.md)

A Docker container that automatically backs up Azure DevOps (ADO) resources —
Git repositories, pipeline definitions and wikis — to a local volume. The
container runs continuously with an internal cron scheduler. All behaviour is
controlled by a single [`config.yaml`](config.yaml).

## What it backs up

| Resource  | How |
|-----------|-----|
| Git repos | Bare mirrors (`git clone --mirror`), incrementally updated |
| Pipelines | Build + release definitions exported as individual JSON files |
| Wikis     | Wiki metadata (`meta.json`) + pages as markdown |

## Quick start

```bash
git clone https://github.com/mainmind83/ado-backup.git
cd ado-backup
```

1. Create a PAT in Azure DevOps with the [required scopes](#required-pat-scopes).
2. Edit [`config.yaml`](config.yaml) (organization, projects, schedule, retention).
3. Provide the PAT via the `ADO_PAT` environment variable.
4. Build and run:

```bash
export ADO_PAT=your-pat-here
docker compose up -d --build
```

Logs stream to `docker logs` and to `/logs/backup.log` (rotated).

## Required PAT scopes

Create the PAT at **User settings → Personal access tokens → New Token** in
Azure DevOps. All scopes are **Read** only — the tool never writes to ADO.

| Scope (UI label)      | Permission | Used for                                  |
|-----------------------|------------|--------------------------------------------|
| Code                  | Read       | List repos and `git clone --mirror` over HTTPS |
| Build                 | Read       | Export build pipeline definitions          |
| Release               | Read       | Export release pipeline definitions        |
| Wiki                  | Read       | List wikis and export pages as markdown    |
| Project and Team      | Read       | Resolve `projects: ["*"]` to the project list |

Tips:

- Set a long **Expiration** (max 1 year). Calendar a renewal — when the PAT
  expires the container will fail with `ADOAuthError: authentication failed (401)`.
- If you scope `azure_devops.projects` to specific names (not `["*"]`) and have
  the project IDs hardcoded, **Project and Team** can be omitted — but listing
  by name still uses it, so leave it on unless you know you don't need it.
- Disable any resource you don't back up in [`config.yaml`](config.yaml)
  (`backup.resources`) and you can drop the matching scope.

## Updating

See [`UPDATING.md`](UPDATING.md) for the full upgrade flow on QNAP
Container Station (GUI-driven, no SSH required) plus the optional
SSH/scripted path and common troubleshooting (ZFS build errors, PAT
issues).

The container always logs its version in the startup banner
(`ADO Backup Tool vX.Y.Z starting`) and checks the GitHub Releases API
once per boot, so `tail logs/backup.log` is enough to see both the
current build and whether a newer release exists.

## Configuration

See [`config.yaml`](config.yaml) for the full annotated schema. Any value
written as `${VAR_NAME}` is resolved from the container environment at startup;
if the variable is missing the container exits with a clear error.

`config.yaml` is re-read at the start of every scheduled run, so edits to
`azure_devops` and `backup` take effect on the next run without restarting
the container. `schedule`, `run_on_start` and `logging` are bound at startup
and still require a restart. An invalid edit logs an error and skips that
run; the previous good run is preserved.

Key options:

- `schedule` — standard cron expression (default `0 2 * * *`, daily at 02:00).
- `run_on_start` — run one backup immediately on container start (default `false`).
- `azure_devops.projects` — list of project names, or `["*"]` for all projects.
- `backup.retention_days` — delete backups older than N days (`0` = keep forever).
- `backup.resources` — toggle `git` / `pipelines` / `wikis` independently.

## Deploying on QNAP (Container Station)

QNAP does not have the generic `/mnt/nas` paths used in
[`docker-compose.yml`](docker-compose.yml). Use
[`docker-compose.qnap.yml`](docker-compose.qnap.yml) instead, which maps QNAP
shared folders.

**1. Create shared folders** (or subfolders inside an existing one). The
example below uses an existing shared folder called `Almacen` with the project
grouped under `BACKUPs/ado/`:

| Path                                  | Purpose                                              |
|---------------------------------------|-------------------------------------------------------|
| `Almacen/BACKUPs/ado/app/`            | The whole project: `Dockerfile`, `src/`, `config.yaml`|
| `Almacen/BACKUPs/ado/data/`           | Backup destination (needs disk space)                 |
| `Almacen/BACKUPs/ado/logs/`           | Persisted logs                                        |

Copy the entire project into `Almacen/BACKUPs/ado/app/`. Shared folders are
reachable inside the NAS as `/share/<FolderName>` (a stable symlink) or
`/share/CACHEDEV1_DATA/<FolderName>`. Edit the host paths in
[`docker-compose.qnap.yml`](docker-compose.qnap.yml) if your folder layout
differs.

**2. Edit `config.yaml`** with your organization, projects and schedule. Leave
`pat: "${ADO_PAT}"` so the PAT comes from the environment, not the file.

**3. Put the PAT directly in `docker-compose.qnap.yml`.** The `environment:`
block already has an `ADO_PAT=...` line — replace the placeholder with your
real token. **Strip this line from the YAML before exporting or sharing it.**

> We evaluated two alternatives on Container Station and both failed in
> practice: `env_file:` pointing at a sibling `.env` fails because CS stages
> the compose in its own internal directory and does not copy the `.env`
> alongside (`The "ADO_PAT" variable is not set`); and the "Environment
> Variables" tab in *Create → Application* stores the value unmasked in CS's
> own config, so it's no more private than inlining it in the YAML. Putting
> the PAT in the YAML on the NAS (under SMB ACLs restricted to your user) is
> the pragmatic equilibrium.

**4. Create the application.** In Container Station → **Create → Application**,
paste the contents of [`docker-compose.qnap.yml`](docker-compose.qnap.yml). Its
`build:` directive points at the project folder on the NAS, so Container
Station builds the image from the `Dockerfile` automatically when the
application is created — no SSH required.

> Note: there is no GUI field to paste a `Dockerfile` itself — Container Station
> builds it via the `build:` directive in the pasted compose YAML, so the
> `Dockerfile` and source must physically exist in the `app/` folder.
> Building over SSH (`docker build -t ado-backup:latest .`) also works and is
> optional, not required.

**Notes:**

- The container runs as `root`, so it can write to QNAP shared folders without
  extra permission setup.
- `TZ` in [`docker-compose.qnap.yml`](docker-compose.qnap.yml) (default
  `Europe/Madrid`) controls the time zone the `schedule` cron expression is
  evaluated in — adjust it to your NAS.
- Set `run_on_start: true` in `config.yaml` for a first test run so you don't
  have to wait for the cron schedule.
- Watch progress in Container Station's log viewer, or tail
  `logs/backup.log` from File Station.

## Output layout

Each run creates a timestamped folder under the backup destination:

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

Git repos are backed up incrementally: an existing bare mirror from the most
recent run is copied forward and refreshed with `git remote update`, avoiding a
full re-clone every time.

### Restoring a repository

The on-disk format is a standard bare git mirror. To get a working copy back
from any timestamped backup:

```bash
git clone /path/to/backup/2024-06-15T020001/Project1/git/RepoA.git restored-repo
cd restored-repo
git checkout main
```

All branches, tags and history are preserved.

## Error handling

- Config validation errors or a missing PAT env var → container exits immediately.
- ADO authentication failure (401) → run is aborted, the previous backup is **not** deleted.
- A single resource failure (e.g. one repo) → logged, the run continues.
- Empty wikis / wikis with no published pages return HTTP 404 on the page API —
  this is logged as a **warning**, not an error, and the run continues.

## Development

```bash
pip install -r requirements-dev.txt
pytest -v
```

Run locally against a config file (instead of the default `/app/config.yaml`):

```bash
python src/main.py path/to/config.yaml
```

## Out of scope (v1.0)

Work items, artifacts, test plans, restore/import, multi-organization support,
non-PAT authentication, TFVC repositories.

## Contributing

Issues and pull requests are welcome. Please make sure `pytest -v` passes
before opening a PR, and add a test for any new behaviour.

## License

[MIT](LICENSE) © 2026 Fernando Zabalza Salvador
