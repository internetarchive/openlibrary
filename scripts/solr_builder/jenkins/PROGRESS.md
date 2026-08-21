# Jenkins Upgrade Progress Log

> Work log for the "pinned, code-defined Jenkins setup" for solr_builder.
> Target: Jenkins **2.568.2-lts**, all plugins pinned, JCasC + seed job in code.
> Context: prior manual attempts and their failures are documented in
> `/problems-solutions.md` (blueocean plugin hell, CSRF crumbs, version skew).

## Decisions (confirmed with user)

- [x] Replace existing half-broken `jenkins` container (2.541.3) on ports 8080/50000
- [x] Drop Blue Ocean entirely (deprecated; source of most documented pain)
- [x] Start via compose profile: `docker compose --profile jenkins up -d jenkins`
- [x] Verify with smoke test + real job dry-run (INDEX_* off)

## Pinned versions (resolved against stable update center for core 2.568.2)

| Component | Version | Source |
|---|---|---|
| Jenkins LTS core | 2.568.2 | updates.jenkins.io/stable |
| workflow-aggregator | 608.v67378e9d3db_1 | update center |
| docker-workflow | 653.v2f2c08eff0ec | update center |
| git | 5.10.1 | update center |
| configuration-as-code | 2117.vc05a_0b_e6b_f4e | update center |
| pipeline-stage-view | 2.41 | update center |
| Docker CLI (controller) | 29.7.2 | download.docker.com static |
| Docker Compose plugin (controller) | v5.5.0 | github.com/docker/compose releases |

Deliberately excluded: `docker` plugin (cloud/agent provisioning only — not needed
for `agent { docker {} }`, and the cause of documented dependency hell), Blue Ocean.

## Steps

### 1. Create progress file
- [x] This file

### 2. Resolve pins
- [x] Plugin versions vs core 2.568.2
- [x] Docker CLI / compose binary URLs verified reachable (docker-29.7.2.tgz, compose v5.5.0)

### 3. Author files (`scripts/solr_builder/jenkins/`)
- [x] `Dockerfile`
- [x] `plugins.txt`
- [x] `jenkins.yaml`
- [x] `init.groovy.d/seed-solr-builder-job.groovy`

### 4. Compose + README
- [x] `jenkins` service added to `compose.yaml` (profile-gated)
- [x] README edits **deferred** by user request — see "Deferred README changes" below; apply once setup is verified working

### 5. Build image
- [x] `docker build` succeeds (proves all pins resolve) — 68 plugins baked

### 6. Swap containers + boot assertions
- [x] Old volume backed up to `jenkins-data-pre-pinning-backup`
- [x] Old container removed
- [x] New container up via compose profile
- [x] No plugin load failures in logs
- [x] JCasC applied cleanly
- [x] "Jenkins is fully up and running" (~15s boot)
- [x] API login works, CSRF crumb obtainable

### 7. Seed job assertion
- [x] `/job/solr-builder/config.xml` confirms GitSCM (`internetarchive/openlibrary`, `*/master`) + scriptPath `scripts/solr_builder/Jenkinsfile`

## Verification evidence

- Build #4 console: `ol  Built`, Cython `.so` compiled for cpython-314,
  `optimize=true` → `"status":0`, `Finished: SUCCESS`

- Build: 68 plugin .jpi files in image; `docker --version` → 29.7.2; `docker compose version` → v5.5.0
- Boot log: `SEEDER: created job 'solr-builder'`; no SEVERE/ERROR after fix
- API: `GET /api/json` as admin → OK; crumb issuer responds
- Seed job config.xml: correct URL/branch/scriptPath
- Smoke job `smoke-dind`: SUCCESS — agent container listed host containers via socket, read /storage
- CSRF note for future API users: crumbs are session-bound; fetch crumb and POST with the same cookie jar

### 8. DinD smoke test
- [x] Pipeline through real agent image `openlibrary/solr-builder:latest`
- [x] `docker ps` works from inside agent container (socket accessible); `/storage` readable; result SUCCESS

### 9. Real job dry-run
- [x] Triggered with all INDEX_*=false (build #4)
- [x] Setup stage green (db+adminer up, solr up, olbase pulled, ol image built, Cython compiled, optimize status=0) — **SUCCESS**
- [x] Test containers/volumes cleaned up; smoke-dind job deleted

### 10. Wrap-up
- [x] pre-commit unavailable on this host (no pip / needs host Py3.14 per AGENTS.md); manual checks passed: YAML valid, no trailing whitespace, EOF newlines
- [ ] Final summary / diff review

## Issues encountered

1. **JCasC symbol**: `loggedInAuthenticationStrategy` doesn't exist in 2.568.2;
   correct symbol is `loggedInUsersCanDoAnything` (verified via class strings).
   Lesson: editing baked-in `jenkins.yaml` requires an image rebuild.
2. **Volume mount semantics**: mounting the named volume a second time
   (`jenkins-data:/var/lib/docker/volumes/jenkins-data`) is NOT equivalent to the
   legacy host bind (`/var/lib/docker/volumes/jenkins-data:...`). The former nests
   writes under `_data/_data`. The Jenkinsfile's HOST_SOLR_BUILDER_DIR trick needs
   the host-path bind. Fixed in compose.yaml.
3. **Agent uid**: docker-workflow starts build containers with the controller's uid.
   As uid 1000, the agent's docker CLI failed with `mkdir /.docker: permission denied`
   during `docker compose build ol`. Fixed with `user: root` on the service
   (matches legacy deployment behavior).
4. **Stale workspace ownership**: after switching uid, the leftover mixed-ownership
   workspace broke git (`fatal: not in a git directory`). Fix: wipe
   `jobs/<job>/workspace*` after changing uids.
5. **API quirks on 2.568.2**:
   - Fresh pipeline jobs are not parameterized until first run; params were added
     via script console.
   - `ParametersDefinitionProperty` moved from `jenkins.model` to `hudson.model`.
   - CSRF crumbs are session-bound: fetch crumb and POST with the same cookie jar.

## Deferred README changes (`scripts/solr_builder/README.md`)

Apply these once the whole setup is verified working, so the README reflects reality:

1. **Replace "Steps" 1–3** (blueocean `docker run` + setup wizard + manual pipeline
   creation) with:
   ```bash
   cd scripts/solr_builder
   ADMIN_PASSWORD=<choose-a-password> docker compose --profile jenkins up -d jenkins
   ```
   Then: open http://localhost:8080, log in as `admin`, the `solr-builder` job
   already exists — just hit Run. Note stage 1 downloads ~15GB of dumps to `/storage`.
2. **Update Notes**: drop the Blue Ocean bullet; add that everything is pinned
   (core in `jenkins/Dockerfile` FROM, plugins in `jenkins/plugins.txt`, Docker CLI +
   compose ARGs) and upgrades = bump versions + `docker compose --profile jenkins build jenkins`;
   add that admin creds come from `ADMIN_PASSWORD` env at runtime (never baked in).
3. **"Possible Issues" cleanup**:
   - Delete the "SCM field is blank" entry (job is seeded automatically now)
   - Delete the Groovy Pipeline `NoSuchMethodError` entry (pinned versions make it moot)
   - Rework the `dockerfile agent` entry: only `Docker Pipeline` plugin needed; fix =
     add to `plugins.txt` + rebuild image (no UI clicking)
4. **"Editing the Jenkins Pipeline" section**: remove the `-v "$HOME:/home"` restart
   workaround sentence (no longer how you edit); keep fork-branch advice.
5. **"Resetting" section**: add Jenkins container removal line:
   `docker rm -f -v solr_builder-jenkins-1` (note: keeps `jenkins-data` volume unless `-v`).
6. **New section on `--skip-ia-metadata`**: now fully supported in the pipeline
   (Jenkinsfile `SKIP_IA_METADATA` param → compose env passthrough on the `ol`
   service → `index-type.sh` → `solr_builder.py`). Documented in
   `jenkins/RUNNING.md`; mirror a short version into the main README when it
   gets updated. Bonus: the env passthrough also makes the Jenkinsfile's
   existing `CHUNK_ETA=70/35` values actually reach `index-type.sh` (they
   previously never propagated into the container).

## Verification evidence

- Build #4 console: `ol  Built`, Cython `.so` compiled for cpython-314,
  `optimize=true` → `"status":0`, `Finished: SUCCESS`

(appended as steps complete)
