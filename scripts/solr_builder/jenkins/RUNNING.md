# Running solr_builder (pinned Jenkins setup)

The Jenkins controller is fully defined in code in this directory — no setup
wizard, no manual plugin installs, nothing clicked in a UI except "Run".

| What | Where pinned |
|---|---|
| Jenkins core | `Dockerfile` → `FROM jenkins/jenkins:2.568.2-lts` |
| Plugins (+ transitives) | `plugins.txt`, baked in at build by `jenkins-plugin-cli` |
| Docker CLI / Compose in controller | `Dockerfile` → `ARG DOCKER_CLI_VERSION` / `ARG DOCKER_COMPOSE_VERSION` |
| Pipeline job | auto-created at first boot by `init.groovy.d/seed-solr-builder-job.groovy` |
| Admin password | `ADMIN_PASSWORD` env var at container startup (never baked into the image) |

## Run it

```bash
cd scripts/solr_builder
ADMIN_PASSWORD=<choose-a-password> docker compose --profile jenkins up -d jenkins
```

Wait ~15s for first boot (`docker logs -f solr_builder-jenkins-1` until
"Jenkins is fully up and running"), then:

1. Open http://localhost:8080 and log in as `admin` / your password.
2. The `solr-builder` job already exists — hit **Run** (defaults are sensible:
   all index types on, `MAX_CORES=18`).
3. Stage 1 downloads ~15GB of dumps into `/storage`; the full reindex takes hours.

## Upgrade Jenkins or plugins

1. Bump versions: `FROM` tag in `Dockerfile`, lines in `plugins.txt`, the two ARGs.
2. Rebuild and restart:
   ```bash
   docker compose --profile jenkins build jenkins
   ADMIN_PASSWORD=<...> docker compose --profile jenkins up -d jenkins
   ```
3. Sanity-check boot logs for plugin failures before running a reindex.

## Reset

```bash
docker rm -f solr_builder-jenkins-1                 # keeps jenkins-data volume
docker volume rm jenkins-data                       # full wipe (fresh Jenkins)
```

## Notes / gotchas

- Everything runs through the host's Docker socket — don't run two reindexes at
  once, and don't use this box for anything else.
- Editing `jenkins.yaml` requires an image rebuild (it's baked in).
- If git checkouts fail after any uid change, wipe stale workspaces:
  `rm -rf /var/lib/docker/volumes/jenkins-data/_data/jobs/solr-builder/workspace*`
- More history: `PROGRESS.md` in this directory.
