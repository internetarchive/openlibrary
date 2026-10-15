# Snippets POC: standalone iannotate on ol-home0

**Status:** experimental / throwaway. Hand-deployed, patch-deployed. Expect to delete it.

Stands up [ArchiveLabs/iannotate](https://github.com/ArchiveLabs/iannotate) (FastAPI + Postgres)
as a small standalone service on **ol-home0**, run the same way as the affiliate-server, and
reverse-proxies it behind openlibrary.org:

| Public URL                       | Backend                               | Notes |
|----------------------------------|---------------------------------------|-------|
| `openlibrary.org/snippets`       | — (placeholder)                       | Reserved for the future UI. |
| `openlibrary.org/api/snippets`   | iannotate `GET`/`POST /annotations`   | Data plane. |

**Auth/security for now (intentionally minimal):** nginx only honors `/api/snippets`
requests whose `Origin` is `archive.org` (i.e. BookReader); everything else gets `403`.
Only the `/snippets` and `/api/snippets` paths are exposed — iannotate's `/docs`, `/annotations`,
etc. are not reachable through openlibrary.org. No OL patron identity yet.

**Longer-term:** this service is expected to move to archive.org land, not OL. This POC is interim.

## Topology

`web_nginx` (serving openlibrary.org) runs on **ol-www0**; iannotate runs on **ol-home0** —
different hosts. So nginx reaches iannotate cross-host via a published port
(`http://ol-home0.us.archive.org:8000`), exactly like the affiliate-server — not via docker
service-name DNS.

## What's in this PR

1. `docker/web_nginx.conf` — a `map $http_origin $snippets_bad_origin` plus `location ^~ /api/snippets`
   (archive.org-gated, CORS + preflight, proxies to iannotate `/annotations`) and a `location ^~ /snippets`
   UI placeholder. Additive only; nothing existing is touched.
2. `docker/iannotate/compose.yaml` — standalone compose (web + postgres) to run iannotate manually on
   ol-home0. Deliberately **not** in `compose.production.yaml`.
3. This doc.

## Deploy (POC)

### 1. Start iannotate on ol-home0
```bash
ssh ol-home0.us.archive.org
sudo git clone https://github.com/ArchiveLabs/iannotate /opt/iannotate
cd /opt/openlibrary   # the openlibrary checkout on ol-home0
IANNOTATE_SRC=/opt/iannotate docker compose -f docker/iannotate/compose.yaml up -d --build
# sanity check locally on ol-home0:
curl -s localhost:8000/annotations    # -> []
```
Verify port `8000` is free on ol-home0 first (the affiliate-server uses `31337`). If taken,
change the published port in `docker/iannotate/compose.yaml` and the `proxy_pass` port in
`docker/web_nginx.conf` to match.

### 2. Ship the nginx routing to ol-www0
`web_nginx.conf` is mounted into the `web_nginx` container (profile `ol-www0`). Patch-deploy it:
```bash
SERVERS=ol-www0 SERVICE=web_nginx ./scripts/deployment/patchdeploy.sh <PR_NUMBER>
```
`patchdeploy.sh` validates `nginx -t` and reloads. (A normal weekly deploy also picks it up.)

### 3. Verify end-to-end
```bash
# preflight -> 204 with CORS headers
curl -i -X OPTIONS https://openlibrary.org/api/snippets \
  -H 'Origin: https://archive.org' -H 'Access-Control-Request-Method: POST'

# create (archive.org origin) -> stored
curl -i -X POST https://openlibrary.org/api/snippets \
  -H 'Origin: https://archive.org' -H 'Content-Type: application/json' \
  -d '{"username":"test","uri":"https://archive.org/details/x","annotation":"https://example.com/a/1","comment":"hi"}'

# read back
curl -s 'https://openlibrary.org/api/snippets?username=test' -H 'Origin: https://archive.org'

# non-archive origin -> 403
curl -i 'https://openlibrary.org/api/snippets' -H 'Origin: https://evil.example'
```

## Rollback
```bash
# on ol-home0
docker compose -f docker/iannotate/compose.yaml down          # add -v to drop the DB volume
# revert the nginx change on ol-www0 (patchdeploy supports un-applying)
SERVERS=ol-www0 SERVICE=web_nginx APPLY_OPTIONS='-R' ./scripts/deployment/patchdeploy.sh <PR_NUMBER>
```

## Caveats (POC-grade on purpose)
- Cross-host traffic is plain HTTP over the internal network (same as affiliate-server).
- Postgres uses default POC credentials and is internal-only (no host port). Rotate before any real use.
- `modsecurity` is disabled on `/api/snippets` so JSON POST bodies aren't inspected.
- Origin-gating is the only access control; add OL patron identity when this graduates past POC.
- `openlibrary.org/api/snippets` maps to iannotate's `/annotations`; the field names are iannotate's
  (`username`, `uri`, `annotation`, `openlibrary_work`, `openlibrary_edition`, `comment`, `private`).
