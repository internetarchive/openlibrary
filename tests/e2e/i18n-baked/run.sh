#!/bin/bash
# End-to-end check that translations baked into olbase reach the pages production serves,
# and that the dev path (checkout mounted over /openlibrary) still serves the committed .po.
#
# Usage (from the repository root): I18N_REF=<full openlibrary-i18n SHA> tests/e2e/i18n-baked/run.sh
#
# Steps, each with an expected outcome; the script exits 1 if any outcome differs:
#   1. build olbase-e2e:candidate (docker/Dockerfile.olbase, I18N_REF) and
#      olbase-e2e:control (the same Dockerfile with the pull step removed)
#   2. read each image's openlibrary/i18n; check the candidate's manifest names I18N_REF
#   3. build the fixture from those two directories plus the pages' English text
#   4. baked path  (no code mount) + candidate: baked assertions PASS
#   5. baked path  (no code mount) + control:   english_before assertions FAIL, others pass
#   6. dev path    (checkout mount) + candidate: committed assertions PASS
#   7. dev path    (checkout mount) + candidate: english_before baked assertions FAIL
# Pages are requested from web.py directly, as production serves them (web on :8080).
# fast_web is not started: under the dev stack's LOCAL_DEV it imports debugpy, which only
# the dev image installs, and it reads the same /openlibrary/openlibrary/i18n anyway.
# Containers run in their own compose project and ports and are stopped on exit
# (not removed); images and volumes are left in place.
set -euo pipefail

: "${I18N_REF:?set I18N_REF to the full openlibrary-i18n commit SHA to bake}"
[[ $I18N_REF =~ ^[0-9a-f]{40}$ ]] || { echo "I18N_REF must be a full 40-character SHA" >&2; exit 2; }
LANGS=${I18N_E2E_LANGS:-es,pl,hr,ja}
KEPT=${I18N_E2E_KEPT:-az}
PROJECT=${E2E_PROJECT:-pr13070-e2e}
export E2E_WEB_PORT=${E2E_WEB_PORT:-18090}
HERE=tests/e2e/i18n-baked
# Docker can only bind-mount paths under the VM's shared directory, so keep scratch in the tree.
WORK=$(mktemp -d "$PWD/.probe-i18n-e2e-XXXXXXXX")
echo "work dir: $WORK"

compose() {  # compose <baked|dev> <image> args...
    local overlay=$HERE/compose.yaml
    [ "$1" = dev ] && overlay=$HERE/compose.dev.yaml
    OLIMAGE=$2 OL_MOUNT_DIR=$WORK/checkout docker compose -p "$PROJECT" \
        -f compose.yaml -f compose.override.yaml -f "$overlay" "${@:3}"
}

CURRENT=(baked olbase-e2e:candidate)
trap 'compose "${CURRENT[@]}" stop >/dev/null 2>&1 || true' EXIT

RESULTS=()
record() { RESULTS+=("$1|$2|$3"); }  # step | expected | actual

# --- 1. images -----------------------------------------------------------------------
# Build from a fresh clone of HEAD, as CI does: the Dockerfile's `make git` needs a real
# .git directory, and a worktree's .git is a file pointing outside the build context.
git clone -q --no-hardlinks . "$WORK/ctx"
git -C "$WORK/ctx" checkout -q "$(git rev-parse HEAD)"
git -C "$WORK/ctx" submodule update -q --init vendor/infogami
grep -c 'i18n-pull-translations.sh' docker/Dockerfile.olbase | grep -qx 1
grep -v 'i18n-pull-translations.sh' docker/Dockerfile.olbase > "$WORK/Dockerfile.control"
docker build -f "$WORK/ctx/docker/Dockerfile.olbase" --build-arg I18N_REF="$I18N_REF" -t olbase-e2e:candidate "$WORK/ctx"
docker build -f "$WORK/Dockerfile.control" -t olbase-e2e:control "$WORK/ctx"

# --- 2. what each image contains -----------------------------------------------------
for img in candidate control; do
    mkdir -p "$WORK/$img"
    docker run --rm --entrypoint tar "olbase-e2e:$img" -c -C /openlibrary/openlibrary i18n | tar -x -C "$WORK/$img"
done
grep -qx "sha	$I18N_REF" "$WORK/candidate/i18n/openlibrary-i18n.txt" \
    || { echo "candidate manifest does not name $I18N_REF" >&2; cat "$WORK/candidate/i18n/openlibrary-i18n.txt" >&2; exit 1; }
for lang in ${LANGS//,/ }; do
    grep -qx "$lang	installed" "$WORK/candidate/i18n/openlibrary-i18n.txt" \
        || { echo "candidate did not install $lang" >&2; exit 1; }
done
[ ! -e "$WORK/control/i18n/openlibrary-i18n.txt" ] || { echo "control image unexpectedly pulled translations" >&2; exit 1; }

# --- stack helpers -------------------------------------------------------------------
up() {  # up <baked|dev> <image>
    CURRENT=("$1" "$2")
    compose "$1" "$2" up -d --force-recreate web
    for _ in $(seq 120); do
        curl -fsS -o /dev/null "http://localhost:$E2E_WEB_PORT/account/login" && return 0
        sleep 5
    done
    echo "stack did not come up" >&2
    compose "$1" "$2" logs --tail 50 web >&2
    exit 1
}

check_mounts() {  # check_mounts <baked|dev> <image>: liveness, before any assertion
    local id mounted image
    id=$(compose "$1" "$2" ps -q web)
    mounted=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/openlibrary"}}yes{{end}}{{end}}' "$id")
    image=$(docker inspect -f '{{.Config.Image}}' "$id")
    [ "$image" = "$2" ] || { echo "web runs $image, expected $2" >&2; exit 1; }
    if [ "$1" = baked ] && [ -n "$mounted" ]; then echo "web has a mount on /openlibrary in the baked run" >&2; exit 1; fi
    if [ "$1" = dev ] && [ -z "$mounted" ]; then echo "web has no checkout mount in the dev run" >&2; exit 1; fi
}

playwright() {  # playwright <label> <baked|committed>; records per-class outcome
    local out=$WORK/$1.json
    PLAYWRIGHT_JSON_OUTPUT_NAME=$out OL_BASE_URL="http://localhost:$E2E_WEB_PORT" \
        I18N_E2E_FIXTURE=$WORK/fixture.json I18N_E2E_EXPECT=$2 \
        npx playwright test tests/e2e/i18n-baked.spec.ts --project=desktop --reporter=json >/dev/null || true
    python3 "$HERE/summarize.py" "$out"
}

# --- 3. fixture ----------------------------------------------------------------------
git archive HEAD | (mkdir -p "$WORK/checkout" && tar -x -C "$WORK/checkout")
cp -R vendor/infogami/. "$WORK/checkout/vendor/infogami/"
python3 "$HERE/make_fixture.py" candidates --committed "$WORK/control/i18n" --baked "$WORK/candidate/i18n" \
    --langs "$LANGS" --kept "$KEPT" > "$WORK/candidates.json"
up baked olbase-e2e:candidate
check_mounts baked "${CURRENT[1]}"
OL_BASE_URL="http://localhost:$E2E_WEB_PORT" I18N_E2E_DISCOVER=$WORK/visible.json \
    npx playwright test tests/e2e/i18n-baked.spec.ts --project=desktop
python3 "$HERE/make_fixture.py" select --candidates "$WORK/candidates.json" --visible "$WORK/visible.json" > "$WORK/fixture.json"

# --- 4. baked path, candidate: all pass ----------------------------------------------
record "baked path + candidate" "all pass" "$(playwright 4-baked-candidate baked)"

# --- 5. baked path, control: english_before fails ------------------------------------
up baked olbase-e2e:control
check_mounts baked "${CURRENT[1]}"
record "baked path + control (no pull)" "english_before fail; both, kept pass" "$(playwright 5-baked-control baked)"

# --- 6/7. dev path, candidate --------------------------------------------------------
up dev olbase-e2e:candidate
check_mounts dev "${CURRENT[1]}"
compose dev olbase-e2e:candidate exec -T web make i18n >/dev/null
compose dev olbase-e2e:candidate restart web >/dev/null
up dev olbase-e2e:candidate
record "dev path + candidate, expect committed" "all pass" "$(playwright 6-dev-committed committed)"
record "dev path + candidate, expect baked" "english_before fail; both, kept pass" "$(playwright 7-dev-baked baked)"


# --- summary -------------------------------------------------------------------------
echo
echo "openlibrary-i18n $I18N_REF, fixture: $WORK/fixture.json"
status=0
for row in "${RESULTS[@]}"; do
    IFS='|' read -r step expected actual <<< "$row"
    verdict=OK; [ "$expected" = "$actual" ] || { verdict=MISMATCH; status=1; }
    printf '%-42s expected: %-40s actual: %-40s %s\n' "$step" "$expected" "$actual" "$verdict"
done
exit $status
