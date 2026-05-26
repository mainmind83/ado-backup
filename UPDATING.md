# Updating to a new version

This guide covers how to move an existing ADO Backup deployment to a newer
release. The container prints its running version in the startup banner
(`ADO Backup Tool vX.Y.Z starting`) and checks the GitHub Releases API once
at boot, so tailing `logs/backup.log` is enough to confirm both the current
build and whether a newer release exists.

Two paths are documented and both are fully supported — choose based on
how you prefer to manage the deployment:

- **Container Station GUI flow** — no SSH, no scripting; keeps the
  application fully managed by CS (Applications view with all the
  GUI-level buttons, no "externally created" warning). Recommended if
  you already use CS to manage your QNAP containers.
- **SSH / scripted flow** — one command per release, version-pinned via
  git tags. Good for unattended setups or anyone who prefers a
  repeatable script. Breaks CS's GUI management of the app (the
  application will show "externally created"); pick one model and stick
  with it.

## Container Station GUI flow (no SSH required)

1. **Get the new source.** On your workstation, either:
   - Pull the latest tag of <https://github.com/mainmind83/ado-backup>
     (e.g. `git fetch --tags && git checkout vX.Y.Z`), or
   - Download the source archive of the release from the GitHub Releases
     page.

2. **Copy the new source files to the NAS, *excluding* `config.yaml`.**
   The repository ships a `config.yaml` with placeholder values; that file
   is also the live, user-edited config on the NAS, so a blanket copy would
   overwrite your real settings. Recommended commands from PowerShell:

   ```powershell
   robocopy "<local-repo>" "<smb-share>\app" /E `
       /XF config.yaml docker-compose.qnap.yml `
       /XD .git .pytest_cache __pycache__
   ```

   - `/XF config.yaml` protects your live config.
   - `/XF docker-compose.qnap.yml` protects your inlined PAT.
   - `/XD .git .pytest_cache __pycache__` skips dev artefacts and the
     git directory (not needed by the build).

3. **Rebuild via Container Station.** Applications → `ado-backup` →
   **Reconstruir / Rebuild**. CS reads the `build:` directive in the
   compose, builds a fresh image, and recreates the container.

   > "Volver a crear" (Recreate) is **not** the right option — it reuses
   > the cached image without rebuilding.

4. **Verify.** Tail the log and look for the new version banner:

   ```
   ================================================================
   ADO Backup Tool vX.Y.Z starting
     organization : ...
     projects     : ...
   ================================================================
   version check: vX.Y.Z is the latest release
   ```

   If `version check` reports a newer release than the banner, the image
   is still running the old code — recheck the Rebuild step.

## SSH / scripted flow (optional)

For users who want one-command updates and have set up their `app/` as a
git working copy, see [`update.sh`](update.sh) at the repository root. It
runs git inside an `alpine/git` container (no host git installation
required), pins to the given tag, and rebuilds via `docker compose`.

```
./update.sh v0.X.Y
```

**Caveat:** if you originally created the application via Container
Station's GUI, switching to SSH-managed updates will cause CS to display
"externally created" warnings for the application. Pick one management
model and stick with it.

## Troubleshooting

### `failed to solve: error creating zfs mount` during build

A known interaction between Container Station's docker, BuildKit and the
ZFS storage backend on some QTS firmware. Workaround: force the legacy
builder via SSH, then restart in CS.

```
sudo DOCKER_BUILDKIT=0 docker build -t ado-backup:latest /share/<your-share>/<path-to-app>
```

After the build succeeds, click **Restart** on the application in CS — it
will pick up the new `ado-backup:latest` image when recreating the
container. No further GUI action needed.

### `Expecting value: line 3 column 1` or other JSON errors when listing projects

ADO is returning the HTML sign-in page (status 203 + `text/html`) instead
of JSON. Almost always means the PAT was revoked, expired, or has too
narrow a scope. Probe the response from inside the container:

```
sudo docker exec ado-backup sh -c 'echo "ADO_PAT length: ${#ADO_PAT}"'
```

- Length `0` → the env var is missing. Check that `ADO_PAT=<value>` is
  inlined in your `docker-compose.qnap.yml` (not the repo placeholder).
- Length `52` → the PAT made it to the container but is rejected.
  Regenerate in Azure DevOps with scopes `Code: Read` and
  `Project and Team: Read` (both are required — Code alone allows
  `git clone` but not the REST API call that lists projects).

### Old image keeps running after Rebuild

Confirm what's actually inside the container, independent of what's on
disk:

```
sudo docker exec ado-backup grep "__version__" /app/src/main.py
sudo docker images ado-backup --format "{{.CreatedAt}}"
```

If `__version__` doesn't show the expected value, the image was not
rebuilt. The most common cause on CS is using "Volver a crear" instead of
"Rebuild" — see step 3 above.

## Rolling back

Each timestamped backup folder under your backup destination is a
self-contained snapshot (see the main README for details). Rollback of
the **tool itself** is a matter of repeating the update flow with the
previous tag. Backed-up data is unaffected by tool version changes.
