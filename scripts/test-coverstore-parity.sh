#!/usr/bin/env bash
# Parity test harness: compares legacy coverstore (web.py/gunicorn) responses
# against the FastAPI coverstore, endpoint by endpoint, via curl.
#
# Usage: scripts/test-coverstore-parity.sh
# Env:
#   OLD  base url of legacy coverstore (default http://localhost:7075)
#   NEW  base url of fastapi coverstore (default http://localhost:18075)

set -u

OLD=${OLD:-http://localhost:7075}
NEW=${NEW:-http://localhost:18075}

PASS=0
FAIL=0
KNOWN_DIFF=0

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

IMAGE="$TMP/logo.png"
cp "$(dirname "$0")/../static/logos/logo-en.png" "$IMAGE"

normalize_output() {
    perl -pe '
        s/[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?/<TS>/g;
        s/localhost:\d+/localhost:<PORT>/g;
        s/"id": \d+/"id": <ID>/g;
        s/"\d+(-[a-z]*)?"/"<ETAG>"/g;
        s/OLPARITY\d*M-[A-Za-z0-9]{5}/OLPARITY<RAND>/g;
    '
}

# canon <curl args...> -- prints a normalized representation of the response
canon() {
    local h="$TMP/hdr" b="$TMP/body"
    curl -sS -o "$b" -D "$h" "$@" >/dev/null 2>&1 || {
        echo "CURL_ERROR"
        return
    }
    echo "STATUS $(head -n1 "$h" | tr -d '\r' | awk '{print $2}')"
    tail -n +2 "$h" | tr -d '\r' |
        awk -F': ' 'NF>=2{key=tolower($1); val=substr($0, length($1)+3); print key": "val}' |
        grep -viE '^(date|server|connection|content-length|transfer-encoding|keep-alive):' |
        sed -E 's/^(expires|last-modified): .*/\1: <TS>/I' |
        LC_ALL=C sort
    if head -c 400 "$b" | LC_ALL=C grep -q '[^[:print:][:space:]]'; then
        echo "BODY-SHA $(sha256sum <"$b" | cut -c1-64)"
    else
        echo "BODY-BEGIN"
        cat "$b"
        echo "BODY-END"
    fi
}

run_case() {
    :
}

# Simpler approach: every CASE_* function prints canonical output for one base url.
run_pair() {
    local name=$1 fn=$2
    local o n
    o=$("$fn" "$OLD" | normalize_output)
    n=$("$fn" "$NEW" | normalize_output)
    if [ "$o" = "$n" ]; then
        PASS=$((PASS + 1))
        printf 'PASS  %s\n' "$name"
    else
        FAIL=$((FAIL + 1))
        printf 'FAIL  %s\n' "$name"
        diff <(printf '%s\n' "$o") <(printf '%s\n' "$n") | sed 's/^/      /'
    fi
}

run_known_diff() {
    local name=$1 fn=$2
    local o n
    o=$("$fn" "$OLD" | normalize_output)
    n=$("$fn" "$NEW" | normalize_output)
    if [ "$o" = "$n" ]; then
        PASS=$((PASS + 1))
        printf 'PASS  %s\n' "$name"
    else
        KNOWN_DIFF=$((KNOWN_DIFF + 1))
        printf 'DIFF? %s (known difference, see docs)\n' "$name"
        diff <(printf '%s\n' "$o") <(printf '%s\n' "$n") | head -12 | sed 's/^/      /'
    fi
}

# ---------- stateless cases ----------

c_index() { canon "$1/"; }
c_options_any() { canon -X OPTIONS "$1/b/id/123.jpg"; }
c_options_root() { canon -X OPTIONS "$1/"; }
c_404_unknown_path() { canon "$1/zzz"; }
c_json_miss_non_id_key() { canon "$1/b/flurb/123.json"; }
c_post_to_get_route() { canon -X POST "$1/b/query"; }
c_get_on_post_route() { canon "$1/b/upload2"; }

c_cover_missing_default_gif() { canon "$1/b/id/999999999.jpg"; }
c_cover_missing_default_false() { canon "$1/b/id/999999999.jpg?default=false"; }
c_cover_missing_default_url() { canon "$1/b/id/999999999.jpg?default=http://example.com/x.png"; }
c_cover_bad_id() { canon "$1/b/id/abc.jpg"; }
c_cover_bad_id_json() { canon "$1/b/id/abc.json"; }
c_cover_json_missing() { canon "$1/b/id/999999999.json"; }
c_cover_sized_missing() { canon "$1/b/id/999999999-M.jpg"; }
c_cover_unknown_key() { canon "$1/b/flurb/123.jpg"; }
c_cover_empty_category() { canon "$1//id/999999999.jpg"; }
c_cover_isbn_unknown() { canon "$1/b/isbn/notarealisbn-M.jpg"; }
c_cover_ia_missing_item() { canon "$1/b/ia/nosuchitemhere12345-M.jpg"; }
c_cover_ia_live_item() { canon "$1/b/ia/goody-M.jpg"; }

c_query_plain() { canon "$1/b/query"; }
c_query_details() { canon "$1/b/query?details=true"; }
c_query_ids() { canon "$1/b/query?cmd=ids"; }
c_query_callback() { canon "$1/b/query?callback=cb&limit=2"; }
c_query_limit_junk() { canon "$1/b/query?limit=junk&offset=-3"; }
c_query_other_categories() { canon "$1/w/query" && canon "$1/a/query" && canon "$1/zzz/query"; }

c_delete_no_id() { canon -X POST "$1/b/delete"; }
c_delete_bad_id() { canon -X POST "$1/b/delete" -d "id=zzz"; }
c_touch_no_id() { canon -X POST "$1/b/touch"; }

c_upload_no_fields() { canon -X POST "$1/b/upload"; }
c_upload_no_file() { canon -X POST "$1/b/upload" -F "olid=OLX"; }
c_upload_bad_source_url() { canon -X POST "$1/b/upload" -F "olid=OLX" -F "source_url=http://evil.example.com/x.jpg"; }

c_upload2_bad_image_ascii() { canon -X POST "$1/b/upload2" -d "olid=OLX&data=notanimage"; }
c_upload2_bad_source_url() { canon -X POST "$1/b/upload2" -F "olid=OLX" -F "source_url=http://evil.example.com/x.jpg"; }
c_upload2_text_part() { canon -X POST "$1/b/upload2" -F "olid=OLX" -F "data=notanimage"; }

# ---------- stateful flow (upload -> fetch -> touch -> delete) ----------

flow() {
    local base=$1
    local id resp etag lm sha_src h

    # 1. upload2 with a real png (multipart file part)
    resp=$(curl -sS -X POST "$base/b/upload2" -F "olid=OLPARITY1M" -F "data=@$IMAGE;type=image/png")
    echo "UPLOAD2_RESP: $resp"
    id=$(sed -n 's/.*"id": \([0-9]*\).*/\1/p' <<<"$resp")
    if [ -z "$id" ]; then
        echo "NO_ID_ABORT"
        return
    fi

    detail() { canon "$base/b/id/$id$1"; }
    image() { canon "$base/b/id/$id$1.jpg"; }

    echo "== details =="
    detail ".json"
    echo "== original =="
    image ""
    sha_src="sha256:$(sha256sum <"$IMAGE" | cut -c1-64)"
    echo "SOURCE_SHA $sha_src"

    echo "== sizes =="
    for s in S M L; do
        image "-$s"
    done

    echo "== conditional =="
    h="$TMP/cond_hdr"
    curl -sS -o /dev/null -D "$h" "$base/b/id/$id.jpg"
    etag=$(awk 'tolower($1)=="etag:"{print $2}' "$h" | tr -d '\r')
    lm=$(awk 'tolower($1)=="last-modified:"{sub(/^[^:]+: /,""); print}' "$h" | tr -d '\r')
    canon -H "If-None-Match: $etag" "$base/b/id/$id.jpg"
    canon -H "If-Modified-Since: $lm" "$base/b/id/$id.jpg"
    canon -H "If-None-Match: bogus-tag" "$base/b/id/$id.jpg" # miss -> full response

    echo "== lookup by olid via OL API (expect default-gif fallback) =="
    canon "$base/b/olid/OLPARITYNOPE-M.jpg"

    echo "== touch =="
    canon -X POST "$base/b/touch" -d "id=$id"

    echo "== delete with redirect =="
    canon -X POST "$base/b/delete" -d "id=$id&redirect_url=http://example.com/done"
    echo "== delete again without redirect =="
    canon -X POST "$base/b/delete" -d "id=$id"
    echo "== details after delete (legacy keeps deleted=false) =="
    detail ".json"
}

flow_upload_endpoint_success() {
    # Known difference: legacy 500s here because gunicorn's multipart parser
    # decodes file parts as UTF-8 text. The FastAPI version saves the upload,
    # which is what the legacy app logic intends.
    local base=$1
    canon -X POST "$base/b/upload" -F "olid=OLPARITY2M" -F "file=@$IMAGE;type=image/png"
}

flow_upload_source_url() {
    # Upload via an allowed external URL (downloads from itself).
    local base=$1
    local resp
    resp=$(curl -sS -X POST "$base/b/upload2" -F "olid=OLPARITY3M" -F "source_url=https://covers.openlibrary.org/b/id/1-M.jpg")
    echo "UPLOAD2_URL_RESP: $resp"
}

# ---------- isbn direct-DB regression fixture ----------

seed_isbn_fixture() {
    # Synthetic OL edition: /books/OLISBNHARNESSM with isbn_10=9999999901 and
    # covers [777002]. Requires the dev compose `db` service.
    docker compose exec -T db psql -U openlibrary -d openlibrary >/dev/null 2>&1 <<'SQL'
INSERT INTO thing (key, type, latest_revision)
SELECT '/books/OLISBNHARNESSM', t.id, 1 FROM thing t WHERE t.key = '/type/edition'
ON CONFLICT (key) DO NOTHING;
INSERT INTO data (thing_id, revision, data)
SELECT t.id, 1, '{"type": "/type/edition", "key": "/books/OLISBNHARNESSM", "covers": [777002]}'
FROM thing t WHERE t.key = '/books/OLISBNHARNESSM';
INSERT INTO edition_str (thing_id, key_id, value)
SELECT t.id, p.id, '9999999901'
FROM thing t JOIN property p ON p.type = t.type AND p.name = 'isbn_10'
WHERE t.key = '/books/OLISBNHARNESSM';
SQL

    if [ "$(docker compose exec -T db psql -U openlibrary -d coverstore -tAc "SELECT 1 FROM cover WHERE id=777002" 2>/dev/null | tr -d '[:space:]')" != "1" ]; then
        local mid
        mid=$(curl -sS -X POST "$NEW/b/upload2" -F "olid=OLISBNHARNESS" -F "data=@$IMAGE;type=image/png" | sed -n 's/.*"id": \([0-9]*\).*/\1/p')
        docker compose exec -T db psql -U openlibrary -d coverstore >/dev/null 2>&1 <<SQL
INSERT INTO cover (id, category_id, olid, filename, filename_s, filename_m, filename_l, author, ip, source_url, width, height, created, last_modified)
SELECT 777002, category_id, olid, filename, filename_s, filename_m, filename_l, author, ip, source_url, width, height, created, last_modified FROM cover WHERE id=$mid;
UPDATE log SET cover_id=777002 WHERE cover_id=$mid;
DELETE FROM cover WHERE id=$mid;
SQL
    fi
}

c_isbn_db_lookup_image() { canon "$1/b/isbn/9999999901-M.jpg"; }
c_isbn_db_lookup_json_redirect() { canon "$1/b/isbn/9999999901.json"; }

check_upload_accepts_binary() {
    # The legacy server 500s here (gunicorn multipart charset bug); the
    # FastAPI version must actually accept the upload.
    local out
    out=$(curl -sS -o /dev/null -w "%{http_code} %{redirect_url}" \
        -X POST "$NEW/b/upload" -F "olid=OLBINCHECK" -F "file=@$IMAGE;type=image/png")
    if [[ "$out" == *"errcode"* || "$out" != 303* ]]; then
        FAIL=$((FAIL + 1))
        printf 'FAIL  /b/upload accepts binary file part (got: %s)\n' "$out"
    else
        PASS=$((PASS + 1))
        printf 'PASS  /b/upload accepts binary file part\n'
    fi
}

# ---------- main ----------

main() {
    seed_isbn_fixture
    run_pair "GET /" c_index
    run_pair "OPTIONS arbitrary path" c_options_any
    run_pair "OPTIONS /" c_options_root
    run_pair "404 unknown path" c_404_unknown_path
    run_pair ".json miss on non-id key (returned 404)" c_json_miss_non_id_key
    run_pair "POST /b/query (405)" c_post_to_get_route
    run_pair "GET /b/upload2 (405)" c_get_on_post_route

    run_pair "cover missing -> default gif" c_cover_missing_default_gif
    run_pair "cover missing, default=false" c_cover_missing_default_false
    run_pair "cover missing, default=URL redirect" c_cover_missing_default_url
    run_pair "cover bad id" c_cover_bad_id
    run_pair "cover bad id .json (500)" c_cover_bad_id_json
    run_pair "cover .json missing" c_cover_json_missing
    run_pair "cover sized missing" c_cover_sized_missing
    run_pair "cover unknown key" c_cover_unknown_key
    run_pair "cover empty category" c_cover_empty_category
    run_pair "isbn unknown" c_cover_isbn_unknown
    run_pair "ia missing item" c_cover_ia_missing_item
    run_pair "ia live item redirect" c_cover_ia_live_item
    run_pair "isbn via direct-DB (regression)" c_isbn_db_lookup_image
    run_pair "isbn .json redirect (regression)" c_isbn_db_lookup_json_redirect

    run_pair "query plain" c_query_plain
    run_pair "query details=true" c_query_details
    run_pair "query cmd=ids" c_query_ids
    run_pair "query callback" c_query_callback
    run_pair "query junk limit/offset" c_query_limit_junk
    run_pair "query w/a/unknown categories" c_query_other_categories

    run_pair "delete without id" c_delete_no_id
    run_pair "delete with junk id" c_delete_bad_id
    run_pair "touch without id" c_touch_no_id

    run_pair "upload: no fields (400)" c_upload_no_fields
    run_pair "upload: no file (303 errcode=1)" c_upload_no_file
    run_pair "upload: bad source_url (303 errcode=2)" c_upload_bad_source_url

    run_pair "upload2: no data (400)" c_get_upload2_no_data
    run_pair "upload2: bad image urlencoded (legacy 500)" c_upload2_bad_image_ascii
    run_pair "upload2: bad source_url (400)" c_upload2_bad_source_url
    run_pair "upload2: text part (legacy 500)" c_upload2_text_part

    run_pair "flow: upload2 -> fetch -> touch -> delete" flow
    check_upload_accepts_binary
    run_known_diff "flow: /b/upload binary file part" flow_upload_endpoint_success
    run_pair "flow: upload2 via allowed source_url" flow_upload_source_url

    echo
    echo "Results: $PASS passed, $FAIL failed, $KNOWN_DIFF known differences"
    [ "$FAIL" -eq 0 ]
}

main "$@"
